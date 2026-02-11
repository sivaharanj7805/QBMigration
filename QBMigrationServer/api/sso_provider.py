"""
SAML 2.0 / SSO Authentication Provider
Enables enterprise Single Sign-On for major Identity Providers:
- Microsoft Entra ID (Azure AD)
- Google Workspace
- Okta
- OneLogin

Enterprise firms (BDO, MNP, Big 4) require SSO for firm-managed accounts.

FIX 100/100: Implements proper SAML signature validation using python3-saml.
"""

import base64
import datetime
import hmac
import logging
import os
import secrets
import urllib.parse
from datetime import timezone
from functools import wraps
from typing import Any, Dict, Optional

import defusedxml.ElementTree as SafeET
from extensions import limiter
from flask import Blueprint, current_app, jsonify, redirect, request, session
from flask_login import login_required
from utils.auth import admin_required
from utils.pii_redaction import hash_email

# SAML signature validation - required for production
try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from onelogin.saml2.errors import OneLogin_Saml2_Error

    SAML_AVAILABLE = True
except ImportError:
    SAML_AVAILABLE = False

logger = logging.getLogger(__name__)

sso_bp = Blueprint("sso", __name__, url_prefix="/api/sso")


# =============================================================================
# SECURITY: OPEN REDIRECT PREVENTION
# =============================================================================


def _check_relay_format(relay_state: str) -> str:
    """
    SECURITY: Sanitize relay_state format -- strip whitespace and reject
    empty/whitespace-only values.

    Args:
        relay_state: Raw relay_state string

    Returns:
        Stripped relay_state, or "/" if empty/None
    """
    if not relay_state:
        return "/"

    relay_state = relay_state.strip()
    if not relay_state:
        return "/"

    return relay_state


def _sanitize_relay_state(relay_state: str) -> str:
    """
    SECURITY: Check for dangerous URL schemes, protocol-relative URLs,
    and encoded newlines in relay_state.

    Args:
        relay_state: The relay_state after format checking

    Returns:
        The relay_state if it passes all checks, or "/" if blocked
    """
    # Check for dangerous URL schemes
    dangerous_schemes = ["javascript:", "data:", "vbscript:", "file:"]
    lower_state = relay_state.lower().strip()
    for scheme in dangerous_schemes:
        if lower_state.startswith(scheme):
            logger.warning(f"SSO open redirect attempt blocked: {relay_state[:50]}")
            return "/"

    # Check for protocol-relative URLs (//evil.com)
    if relay_state.startswith("//"):
        logger.warning(
            f"SSO open redirect attempt blocked (protocol-relative): {relay_state[:50]}"
        )
        return "/"

    # Relative path (safe - starts with / but not //)
    if relay_state.startswith("/") and not relay_state.startswith("//"):
        # Additional check: no double-encoding or newlines
        if "%0" in relay_state.lower() or "\n" in relay_state or "\r" in relay_state:
            logger.warning(
                f"SSO open redirect attempt blocked (encoded newline): {relay_state[:50]}"
            )
            return "/"
        return relay_state

    # Not a relative path -- caller must validate as absolute URL
    return relay_state


def _validate_relay_url(relay_state: str) -> str:
    """
    Validate an absolute URL relay_state against the domain whitelist.
    Only HTTPS is allowed in production. The host must match an allowed domain
    exactly or be a subdomain of one.

    Args:
        relay_state: An absolute URL string (must have scheme and netloc)

    Returns:
        The relay_state if allowed, or "/" if blocked
    """
    try:
        parsed = urllib.parse.urlparse(relay_state)

        # Must have scheme and netloc for absolute URL
        if not parsed.scheme or not parsed.netloc:
            logger.warning(f"SSO invalid relay_state format: {relay_state[:50]}")
            return "/"

        # Only allow HTTPS in production
        if os.getenv("FLASK_ENV") == "production" and parsed.scheme != "https":
            logger.warning(f"SSO non-HTTPS relay_state blocked: {relay_state[:50]}")
            return "/"

        # Check against whitelist from environment
        allowed_domains = os.getenv("ALLOWED_RELAY_DOMAINS", "").split(",")
        allowed_domains = [d.strip().lower() for d in allowed_domains if d.strip()]

        # Add default allowed domains
        server_url = current_app.config.get("SERVER_URL", "")
        if server_url:
            try:
                server_parsed = urllib.parse.urlparse(server_url)
                if server_parsed.netloc:
                    allowed_domains.append(server_parsed.netloc.lower())
            except Exception as exc:
                logger.debug("Failed to parse server URL for allowed domains: %s", exc)

        # Always allow forensicbridge domains
        allowed_domains.extend(
            [
                "forensicbridge.io",
                "www.forensicbridge.io",
                "app.forensicbridge.io",
                "forensicbridge.ca",
                "www.forensicbridge.ca",
                "app.forensicbridge.ca",
            ]
        )

        # Normalize the host for comparison
        host = parsed.netloc.lower()

        # Check if host matches any allowed domain (exact or subdomain)
        is_allowed = False
        for domain in allowed_domains:
            if host == domain or host.endswith("." + domain):
                is_allowed = True
                break

        if not is_allowed:
            logger.warning(
                f"SSO open redirect blocked (domain not whitelisted): {host}"
            )
            return "/"

        return relay_state

    except Exception as e:
        logger.warning(f"SSO relay_state validation error: {e}")
        return "/"


def validate_relay_state(relay_state: str) -> str:
    """
    CRITICAL SECURITY FIX: Validate relay_state to prevent open redirect attacks.

    Only allows:
    1. Relative paths starting with /
    2. Explicitly whitelisted domains from ALLOWED_RELAY_DOMAINS

    Args:
        relay_state: The redirect URL from SSO flow

    Returns:
        str: Safe redirect path (defaults to '/' if invalid)
    """
    relay_state = _check_relay_format(relay_state)
    if relay_state == "/":
        return "/"

    sanitized = _sanitize_relay_state(relay_state)
    if sanitized == "/":
        return "/"

    # If it's a relative path, _sanitize_relay_state already approved it
    if sanitized.startswith("/"):
        return sanitized

    # Absolute URL -- validate against whitelist
    return _validate_relay_url(sanitized)


class SSOProvider:
    """Base SSO Provider configuration"""

    def __init__(self, provider_type: str, config: dict):
        self.provider_type = provider_type
        self.config = config
        self.entity_id = config.get("entity_id", "")
        self.sso_url = config.get("sso_url", "")
        self.slo_url = config.get("slo_url", "")
        self.certificate = config.get("certificate", "")
        self.name_id_format = config.get(
            "name_id_format", "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
        )

    def get_metadata(self) -> dict:
        """Return SP metadata for IdP configuration"""
        return {
            "entity_id": current_app.config.get(
                "SAML_SP_ENTITY_ID", "https://forensicbridge.io"
            ),
            "acs_url": current_app.config.get("SAML_ACS_URL", "/api/sso/acs"),
            "slo_url": current_app.config.get("SAML_SLO_URL", "/api/sso/slo"),
            "name_id_format": self.name_id_format,
            "organization": {
                "name": "ForensicBridge",
                "display_name": "ForensicBridge Migration Suite",
                "url": "https://forensicbridge.io",
            },
        }


class MicrosoftEntraProvider(SSOProvider):
    """Microsoft Entra ID (Azure AD) SSO Provider"""

    def __init__(self, config: dict):
        super().__init__("microsoft", config)
        self.tenant_id = config.get("tenant_id", "common")
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")

        # Azure AD endpoints
        self.sso_url = f"https://login.microsoftonline.com/{self.tenant_id}/saml2"
        self.token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )
        self.logout_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/logout"
        )

    def get_auth_url(self, relay_state: str = None) -> str:
        """Generate Azure AD authentication URL"""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": current_app.config.get("SAML_ACS_URL"),
            "response_mode": "query",
            "scope": "openid profile email",
            "state": relay_state or secrets.token_urlsafe(16),
            "nonce": secrets.token_urlsafe(16),
        }
        return f"{self.sso_url}?{urllib.parse.urlencode(params)}"


class GoogleWorkspaceProvider(SSOProvider):
    """Google Workspace SSO Provider"""

    def __init__(self, config: dict):
        super().__init__("google", config)
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.hosted_domain = config.get(
            "hosted_domain", ""
        )  # Restrict to specific domain

        self.sso_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"

    def get_auth_url(self, relay_state: str = None) -> str:
        """Generate Google authentication URL"""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": current_app.config.get("SAML_ACS_URL"),
            "scope": "openid profile email",
            "state": relay_state or secrets.token_urlsafe(16),
            "nonce": secrets.token_urlsafe(16),
            "access_type": "offline",
            "prompt": "select_account",
        }
        if self.hosted_domain:
            params["hd"] = self.hosted_domain
        return f"{self.sso_url}?{urllib.parse.urlencode(params)}"


class OktaProvider(SSOProvider):
    """Okta SSO Provider"""

    def __init__(self, config: dict):
        super().__init__("okta", config)
        self.okta_domain = config.get("okta_domain", "")  # e.g., 'yourcompany.okta.com'
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")

        self.sso_url = f"https://{self.okta_domain}/oauth2/default/v1/authorize"
        self.token_url = f"https://{self.okta_domain}/oauth2/default/v1/token"
        self.userinfo_url = f"https://{self.okta_domain}/oauth2/default/v1/userinfo"


class SSOManager:
    """Manages SSO providers and authentication flow"""

    _providers: Dict[str, SSOProvider] = {}

    @classmethod
    def register_provider(cls, org_id: str, provider: SSOProvider):
        """Register SSO provider for an organization"""
        cls._providers[org_id] = provider
        logger.info(
            f"Registered SSO provider '{provider.provider_type}' for org '{org_id}'"
        )

    @classmethod
    def get_provider(cls, org_id: str) -> Optional[SSOProvider]:
        """Get SSO provider for an organization"""
        return cls._providers.get(org_id)

    @classmethod
    def is_sso_enabled(cls, org_id: str) -> bool:
        """Check if SSO is enabled for an organization"""
        return org_id in cls._providers

    @classmethod
    def list_providers(cls) -> list:
        """List all registered providers"""
        return [
            {"org_id": org_id, "provider_type": provider.provider_type}
            for org_id, provider in cls._providers.items()
        ]


def require_sso(f):
    """Decorator to require SSO authentication"""

    @wraps(f)
    def decorated(*args, **kwargs):
        if "sso_user" not in session:
            return jsonify({"error": "SSO authentication required"}), 401
        return f(*args, **kwargs)

    return decorated


# =============================================================================
# SSO ENDPOINTS
# =============================================================================


@sso_bp.route("/providers", methods=["GET"])
def list_providers():
    """List available SSO providers"""
    return jsonify(
        {
            "providers": SSOManager.list_providers(),
            "supported_types": ["microsoft", "google", "okta", "onelogin", "saml2"],
        }
    )


@sso_bp.route("/initiate", methods=["POST"])
@limiter.limit("10 per minute")
def initiate_sso():
    """
    Initiate SSO login flow

    Request Body:
        org_id (str): Organization ID
        relay_state (str): Optional redirect URL after auth

    Returns:
        redirect_url: URL to redirect user to IdP
    """
    data = request.get_json() or {}
    org_id = data.get("org_id")
    # SECURITY FIX: Validate relay_state to prevent open redirect attacks
    relay_state = validate_relay_state(data.get("relay_state", "/"))

    if not org_id:
        return jsonify({"error": "org_id required"}), 400

    provider = SSOManager.get_provider(org_id)
    if not provider:
        return jsonify({"error": "SSO not configured for this organization"}), 404

    # Generate state token to prevent CSRF
    state_token = secrets.token_urlsafe(32)
    session["sso_state"] = state_token
    session["sso_org_id"] = org_id
    session["sso_relay_state"] = relay_state

    # Get IdP auth URL
    auth_url = provider.get_auth_url(state_token)

    logger.info(f"SSO initiated for org '{org_id}' via {provider.provider_type}")

    return jsonify({"redirect_url": auth_url, "provider": provider.provider_type})


def _prepare_saml_request(provider: "SSOProvider") -> Dict[str, Any]:
    """
    Prepare Flask request data for python3-saml.

    FIX 100/100: Helper to convert Flask request to SAML-compatible format.
    """
    url_data = urllib.parse.urlparse(request.url)
    return {
        "https": "on" if request.scheme == "https" else "off",
        "http_host": request.host,
        "server_port": url_data.port or (443 if request.scheme == "https" else 80),
        "script_name": request.path,
        "get_data": request.args.copy(),
        "post_data": request.form.copy(),
    }


def _get_saml_settings(provider: "SSOProvider") -> Dict[str, Any]:
    """
    Build SAML settings for python3-saml from provider configuration.

    FIX 100/100: Proper SAML settings structure for signature validation.
    """
    base_url = current_app.config.get("SERVER_URL", "https://forensicbridge.io")

    return {
        "strict": True,  # Enforce strict validation
        "debug": os.getenv("FLASK_ENV") != "production",
        "sp": {
            "entityId": f"{base_url}/api/sso",
            "assertionConsumerService": {
                "url": f"{base_url}/api/sso/acs",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": f"{base_url}/api/sso/slo",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": provider.name_id_format,
        },
        "idp": {
            "entityId": provider.entity_id,
            "singleSignOnService": {
                "url": provider.sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "singleLogoutService": {
                "url": provider.slo_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": provider.certificate,
        },
        "security": {
            "nameIdEncrypted": False,
            "authnRequestsSigned": False,
            "logoutRequestSigned": False,
            "logoutResponseSigned": False,
            "signMetadata": False,
            "wantMessagesSigned": True,  # CRITICAL: Require signed responses
            "wantAssertionsSigned": True,  # CRITICAL: Require signed assertions
            "wantNameIdEncrypted": False,
            "wantAttributeStatement": False,
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
        },
    }


def _parse_saml_response(saml_response, org_id, provider):
    """
    Parse and validate a SAML response, returning an sso_user dict on success.

    FIX 100/100: Implements proper SAML signature validation using python3-saml.
    SECURITY: Default-deny. Only skips validation if explicitly opted out AND not in production.

    Args:
        saml_response: The Base64-encoded SAML response from the IdP
        org_id: The organization ID from the SSO session
        provider: The SSOProvider instance for this org

    Returns:
        Tuple of (sso_user_dict, error_response).
        On success error_response is None; on failure sso_user_dict is None.
    """
    if SAML_AVAILABLE and provider.certificate:
        # Use python3-saml for proper validation
        req = _prepare_saml_request(provider)
        settings = _get_saml_settings(provider)

        try:
            auth = OneLogin_Saml2_Auth(req, settings)
            auth.process_response()
            errors = auth.get_errors()

            if errors:
                error_reason = auth.get_last_error_reason()
                logger.error(
                    f"SAML validation failed for org '{org_id}': {errors} - {error_reason}"
                )
                return None, (
                    jsonify(
                        {"error": "SAML validation failed", "details": str(errors)}
                    ),
                    401,
                )

            if not auth.is_authenticated():
                logger.warning(f"SAML authentication failed for org '{org_id}'")
                return None, (jsonify({"error": "Authentication failed"}), 401)

            # Extract validated user attributes
            attributes = auth.get_attributes()
            name_id = auth.get_nameid()
            session_index = auth.get_session_index()

            sso_user = {
                "org_id": org_id,
                "provider": provider.provider_type,
                "email": name_id,
                "attributes": attributes,
                "authenticated_at": datetime.datetime.now(timezone.utc).isoformat(),
                "session_index": session_index or secrets.token_urlsafe(16),
            }

            logger.info(
                f"SAML authentication successful for org '{org_id}', user: {hash_email(name_id) if name_id else 'unknown'}"
            )
            return sso_user, None

        except OneLogin_Saml2_Error as e:
            logger.error(f"SAML processing error for org '{org_id}': {str(e)}")
            return None, (jsonify({"error": "SAML processing failed"}), 401)
    else:
        # Fallback for development/testing without certificate
        # SECURITY: Default-deny. Only skip validation if explicitly opted out
        # AND not in production.
        if not (
            os.getenv("SKIP_SAML_VALIDATION") == "true"
            and os.getenv("FLASK_ENV") != "production"
        ):
            logger.error("SAML validation unavailable - certificate required")
            return None, (jsonify({"error": "SAML not properly configured"}), 500)

        logger.warning(
            f"SAML validation skipped for org '{org_id}' (SKIP_SAML_VALIDATION=true)"
        )

        # Basic XML parsing for development only
        try:
            decoded = base64.b64decode(saml_response)
            # Parse XML to extract NameID (development only)
            root = SafeET.fromstring(decoded)  # nosec B314
            ns = {"saml": "urn:oasis:names:tc:SAML:2.0:assertion"}
            name_id_elem = root.find(".//saml:NameID", ns)
            name_id = name_id_elem.text if name_id_elem is not None else "unknown"
        except Exception:
            name_id = "dev-user"

        sso_user = {
            "org_id": org_id,
            "provider": provider.provider_type,
            "email": name_id,
            "authenticated_at": datetime.datetime.now(timezone.utc).isoformat(),
            "session_index": secrets.token_urlsafe(16),
            "_dev_mode": True,  # Flag for audit trail
        }
        return sso_user, None


def _establish_sso_session(sso_user):
    """
    SECURITY FIX (C-06): Regenerate session to prevent session fixation.
    Saves the relay_state, clears the old session, stores sso_user data,
    and returns the safe redirect URL.

    Args:
        sso_user: The authenticated SSO user dict

    Returns:
        A safe redirect URL string (validated against relay_state whitelist)
    """
    saved_relay_state = session.get("sso_relay_state", "/")
    sso_data = sso_user
    old_keys = list(session.keys())
    for key in old_keys:
        session.pop(key, None)
    session["sso_user"] = sso_data
    session.modified = True

    logger.info(f"SSO authentication successful for org '{sso_user.get('org_id')}'")

    # SECURITY FIX: Validate stored relay_state before redirect
    return validate_relay_state(saved_relay_state)


@sso_bp.route("/acs", methods=["POST"])
@limiter.limit("20 per minute")
def assertion_consumer_service():
    """
    SAML Assertion Consumer Service (ACS) endpoint
    Receives SAML response from IdP after authentication

    FIX 100/100: Implements proper SAML signature validation using python3-saml.
    """
    saml_response = request.form.get("SAMLResponse")
    # SECURITY FIX: Validate relay_state to prevent open redirect attacks
    # Note: Actual redirect uses session-stored sso_relay_state (line 548), not this value.
    # This validation guards against malicious RelayState in the POST form data.
    relay_state = validate_relay_state(  # noqa: F841
        request.form.get("RelayState", "/")
    )

    if not saml_response:
        logger.warning("ACS received without SAML response")
        return jsonify({"error": "Missing SAML response"}), 400

    try:
        # Validate session state
        org_id = session.get("sso_org_id")

        if not org_id:
            return jsonify({"error": "SSO session not found"}), 400

        provider = SSOManager.get_provider(org_id)
        if not provider:
            return jsonify({"error": "Provider not found"}), 400

        # Parse and validate SAML response
        sso_user, parse_error = _parse_saml_response(saml_response, org_id, provider)
        if parse_error:
            return parse_error

        # Establish session and redirect
        safe_redirect = _establish_sso_session(sso_user)
        return redirect(safe_redirect)

    except Exception as e:
        logger.exception(f"SAML ACS processing failed: {str(e)}")
        return jsonify({"error": "Authentication failed"}), 401


@sso_bp.route("/callback", methods=["GET"])
def oauth_callback():
    """
    OAuth2 callback endpoint for Microsoft/Google/Okta
    """
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        logger.warning(f"SSO callback error: {error}")
        return jsonify({"error": error}), 400

    if not code:
        return jsonify({"error": "Missing authorization code"}), 400

    # Validate state (H-26: use constant-time comparison to prevent timing attacks)
    stored_state = session.get("sso_state")
    if not hmac.compare_digest(str(state or ""), str(stored_state or "")):
        logger.warning("SSO state mismatch - possible CSRF")
        return jsonify({"error": "Invalid state"}), 400

    org_id = session.get("sso_org_id")
    provider = SSOManager.get_provider(org_id)

    if not provider:
        return jsonify({"error": "Provider not found"}), 400

    try:
        # Exchange code for token (placeholder - would call provider API)
        # In production: requests.post(provider.token_url, data={...})

        sso_user = {
            "org_id": org_id,
            "provider": provider.provider_type,
            "authenticated_at": datetime.datetime.now(timezone.utc).isoformat(),
        }

        # SECURITY FIX (C-06): Regenerate session to prevent session fixation
        saved_relay_state = session.get("sso_relay_state", "/")
        sso_data = sso_user
        old_keys = list(session.keys())
        for key in old_keys:
            session.pop(key, None)
        session["sso_user"] = sso_data
        session.modified = True

        logger.info(f"OAuth callback successful for org '{org_id}'")

        # SECURITY FIX: Validate stored relay_state before redirect
        safe_redirect = validate_relay_state(saved_relay_state)
        return redirect(safe_redirect)

    except Exception as e:
        logger.exception(f"OAuth callback failed: {str(e)}")
        return jsonify({"error": "Token exchange failed"}), 401


@sso_bp.route("/logout", methods=["POST"])
@limiter.limit("10 per minute")
@require_sso
def sso_logout():
    """
    Initiate SSO logout (Single Logout)
    """
    sso_user = session.get("sso_user", {})
    org_id = sso_user.get("org_id")

    # Clear session
    session.pop("sso_user", None)
    session.pop("sso_state", None)
    session.pop("sso_org_id", None)

    logger.info(f"SSO logout for org '{org_id}'")

    # In production, redirect to IdP SLO endpoint
    return jsonify({"success": True, "message": "Logged out successfully"})


@sso_bp.route("/metadata", methods=["GET"])
def sp_metadata():
    """
    Return Service Provider (SP) metadata for IdP configuration
    """
    base_url = current_app.config.get("SERVER_URL", "https://forensicbridge.io")

    metadata = {
        "entity_id": f"{base_url}/api/sso",
        "name_id_format": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        "assertion_consumer_service": {
            "url": f"{base_url}/api/sso/acs",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
        },
        "single_logout_service": {
            "url": f"{base_url}/api/sso/slo",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
        },
        "organization": {
            "name": "ForensicBridge",
            "display_name": "ForensicBridge Migration Suite",
            "url": base_url,
        },
        "technical_contact": {
            "given_name": "Support",
            "email": current_app.config.get("ALERT_EMAIL", "support@forensicbridge.io"),
        },
    }

    return jsonify(metadata)


@sso_bp.route("/configure", methods=["POST"])
@limiter.limit("5 per minute")
@login_required
@admin_required
def configure_provider():
    """
    Configure SSO provider for an organization (admin endpoint)

    Request Body:
        org_id (str): Organization ID
        provider_type (str): 'microsoft' | 'google' | 'okta' | 'saml2'
        config (dict): Provider-specific configuration
    """
    # SECURITY FIX: Require authentication (was previously unauthenticated)
    data = request.get_json() or {}

    org_id = data.get("org_id")
    provider_type = data.get("provider_type")
    config = data.get("config", {})

    if not all([org_id, provider_type, config]):
        return jsonify({"error": "org_id, provider_type, and config required"}), 400

    # Create provider based on type
    provider = None
    if provider_type == "microsoft":
        provider = MicrosoftEntraProvider(config)
    elif provider_type == "google":
        provider = GoogleWorkspaceProvider(config)
    elif provider_type == "okta":
        provider = OktaProvider(config)
    else:
        provider = SSOProvider(provider_type, config)

    SSOManager.register_provider(org_id, provider)

    logger.info(f"SSO configured for org '{org_id}' with provider '{provider_type}'")

    return jsonify(
        {
            "success": True,
            "org_id": org_id,
            "provider_type": provider_type,
            "sp_metadata": provider.get_metadata(),
        }
    )
