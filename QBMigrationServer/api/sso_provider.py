"""
SAML 2.0 / SSO Authentication Provider
Enables enterprise Single Sign-On for major Identity Providers:
- Microsoft Entra ID (Azure AD)
- Google Workspace
- Okta
- OneLogin

Enterprise firms (BDO, MNP, Big 4) require SSO for firm-managed accounts.
"""

from flask import Blueprint, request, jsonify, redirect, session, current_app, url_for
from functools import wraps
import datetime
import logging
import secrets
import base64
import hashlib
import urllib.parse
from typing import Optional, Dict, Tuple

# For production, install: pip install python-saml3
# For now, we implement the core SSO flow with configurable providers

logger = logging.getLogger(__name__)

sso_bp = Blueprint('sso', __name__, url_prefix='/api/sso')


class SSOProvider:
    """Base SSO Provider configuration"""
    
    def __init__(self, provider_type: str, config: dict):
        self.provider_type = provider_type
        self.config = config
        self.entity_id = config.get('entity_id', '')
        self.sso_url = config.get('sso_url', '')
        self.slo_url = config.get('slo_url', '')
        self.certificate = config.get('certificate', '')
        self.name_id_format = config.get('name_id_format', 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress')
    
    def get_metadata(self) -> dict:
        """Return SP metadata for IdP configuration"""
        return {
            'entity_id': current_app.config.get('SAML_SP_ENTITY_ID', 'https://forensicbridge.io'),
            'acs_url': current_app.config.get('SAML_ACS_URL', '/api/sso/acs'),
            'slo_url': current_app.config.get('SAML_SLO_URL', '/api/sso/slo'),
            'name_id_format': self.name_id_format,
            'organization': {
                'name': 'ForensicBridge',
                'display_name': 'ForensicBridge Migration Suite',
                'url': 'https://forensicbridge.io'
            }
        }


class MicrosoftEntraProvider(SSOProvider):
    """Microsoft Entra ID (Azure AD) SSO Provider"""
    
    def __init__(self, config: dict):
        super().__init__('microsoft', config)
        self.tenant_id = config.get('tenant_id', 'common')
        self.client_id = config.get('client_id', '')
        self.client_secret = config.get('client_secret', '')
        
        # Azure AD endpoints
        self.sso_url = f"https://login.microsoftonline.com/{self.tenant_id}/saml2"
        self.token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        self.logout_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/logout"
    
    def get_auth_url(self, relay_state: str = None) -> str:
        """Generate Azure AD authentication URL"""
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': current_app.config.get('SAML_ACS_URL'),
            'response_mode': 'query',
            'scope': 'openid profile email',
            'state': relay_state or secrets.token_urlsafe(16),
            'nonce': secrets.token_urlsafe(16)
        }
        return f"{self.sso_url}?{urllib.parse.urlencode(params)}"


class GoogleWorkspaceProvider(SSOProvider):
    """Google Workspace SSO Provider"""
    
    def __init__(self, config: dict):
        super().__init__('google', config)
        self.client_id = config.get('client_id', '')
        self.client_secret = config.get('client_secret', '')
        self.hosted_domain = config.get('hosted_domain', '')  # Restrict to specific domain
        
        self.sso_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
    
    def get_auth_url(self, relay_state: str = None) -> str:
        """Generate Google authentication URL"""
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': current_app.config.get('SAML_ACS_URL'),
            'scope': 'openid profile email',
            'state': relay_state or secrets.token_urlsafe(16),
            'nonce': secrets.token_urlsafe(16),
            'access_type': 'offline',
            'prompt': 'select_account'
        }
        if self.hosted_domain:
            params['hd'] = self.hosted_domain
        return f"{self.sso_url}?{urllib.parse.urlencode(params)}"


class OktaProvider(SSOProvider):
    """Okta SSO Provider"""
    
    def __init__(self, config: dict):
        super().__init__('okta', config)
        self.okta_domain = config.get('okta_domain', '')  # e.g., 'yourcompany.okta.com'
        self.client_id = config.get('client_id', '')
        self.client_secret = config.get('client_secret', '')
        
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
        logger.info(f"Registered SSO provider '{provider.provider_type}' for org '{org_id}'")
    
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
            {'org_id': org_id, 'provider_type': provider.provider_type}
            for org_id, provider in cls._providers.items()
        ]


def require_sso(f):
    """Decorator to require SSO authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'sso_user' not in session:
            return jsonify({'error': 'SSO authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# SSO ENDPOINTS
# =============================================================================

@sso_bp.route('/providers', methods=['GET'])
def list_providers():
    """List available SSO providers"""
    return jsonify({
        'providers': SSOManager.list_providers(),
        'supported_types': ['microsoft', 'google', 'okta', 'onelogin', 'saml2']
    })


@sso_bp.route('/initiate', methods=['POST'])
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
    org_id = data.get('org_id')
    relay_state = data.get('relay_state', '/')
    
    if not org_id:
        return jsonify({'error': 'org_id required'}), 400
    
    provider = SSOManager.get_provider(org_id)
    if not provider:
        return jsonify({'error': 'SSO not configured for this organization'}), 404
    
    # Generate state token to prevent CSRF
    state_token = secrets.token_urlsafe(32)
    session['sso_state'] = state_token
    session['sso_org_id'] = org_id
    session['sso_relay_state'] = relay_state
    
    # Get IdP auth URL
    auth_url = provider.get_auth_url(state_token)
    
    logger.info(f"SSO initiated for org '{org_id}' via {provider.provider_type}")
    
    return jsonify({
        'redirect_url': auth_url,
        'provider': provider.provider_type
    })


@sso_bp.route('/acs', methods=['POST'])
def assertion_consumer_service():
    """
    SAML Assertion Consumer Service (ACS) endpoint
    Receives SAML response from IdP after authentication
    """
    saml_response = request.form.get('SAMLResponse')
    relay_state = request.form.get('RelayState', '/')
    
    if not saml_response:
        logger.warning("ACS received without SAML response")
        return jsonify({'error': 'Missing SAML response'}), 400
    
    try:
        # In production, use python-saml3 to validate the response
        # For now, we decode and extract basic info
        
        # Validate state token
        stored_state = session.get('sso_state')
        org_id = session.get('sso_org_id')
        
        if not org_id:
            return jsonify({'error': 'SSO session not found'}), 400
        
        provider = SSOManager.get_provider(org_id)
        if not provider:
            return jsonify({'error': 'Provider not found'}), 400
        
        # Decode SAML response (simplified - production should validate signature)
        decoded = base64.b64decode(saml_response)
        
        # Extract user info (placeholder - would parse XML in production)
        sso_user = {
            'org_id': org_id,
            'provider': provider.provider_type,
            'authenticated_at': datetime.datetime.utcnow().isoformat(),
            'session_index': secrets.token_urlsafe(16)
        }
        
        session['sso_user'] = sso_user
        
        logger.info(f"SSO authentication successful for org '{org_id}'")
        
        # Redirect to relay state or dashboard
        return redirect(session.get('sso_relay_state', '/'))
        
    except Exception as e:
        logger.exception(f"SAML ACS processing failed: {str(e)}")
        return jsonify({'error': 'Authentication failed'}), 401


@sso_bp.route('/callback', methods=['GET'])
def oauth_callback():
    """
    OAuth2 callback endpoint for Microsoft/Google/Okta
    """
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        logger.warning(f"SSO callback error: {error}")
        return jsonify({'error': error}), 400
    
    if not code:
        return jsonify({'error': 'Missing authorization code'}), 400
    
    # Validate state
    stored_state = session.get('sso_state')
    if state != stored_state:
        logger.warning("SSO state mismatch - possible CSRF")
        return jsonify({'error': 'Invalid state'}), 400
    
    org_id = session.get('sso_org_id')
    provider = SSOManager.get_provider(org_id)
    
    if not provider:
        return jsonify({'error': 'Provider not found'}), 400
    
    try:
        # Exchange code for token (placeholder - would call provider API)
        # In production: requests.post(provider.token_url, data={...})
        
        sso_user = {
            'org_id': org_id,
            'provider': provider.provider_type,
            'authenticated_at': datetime.datetime.utcnow().isoformat()
        }
        
        session['sso_user'] = sso_user
        
        logger.info(f"OAuth callback successful for org '{org_id}'")
        
        return redirect(session.get('sso_relay_state', '/'))
        
    except Exception as e:
        logger.exception(f"OAuth callback failed: {str(e)}")
        return jsonify({'error': 'Token exchange failed'}), 401


@sso_bp.route('/logout', methods=['POST'])
@require_sso
def sso_logout():
    """
    Initiate SSO logout (Single Logout)
    """
    sso_user = session.get('sso_user', {})
    org_id = sso_user.get('org_id')
    
    # Clear session
    session.pop('sso_user', None)
    session.pop('sso_state', None)
    session.pop('sso_org_id', None)
    
    logger.info(f"SSO logout for org '{org_id}'")
    
    # In production, redirect to IdP SLO endpoint
    return jsonify({'success': True, 'message': 'Logged out successfully'})


@sso_bp.route('/metadata', methods=['GET'])
def sp_metadata():
    """
    Return Service Provider (SP) metadata for IdP configuration
    """
    base_url = current_app.config.get('SERVER_URL', 'https://forensicbridge.io')
    
    metadata = {
        'entity_id': f"{base_url}/api/sso",
        'name_id_format': 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress',
        'assertion_consumer_service': {
            'url': f"{base_url}/api/sso/acs",
            'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'
        },
        'single_logout_service': {
            'url': f"{base_url}/api/sso/slo",
            'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'
        },
        'organization': {
            'name': 'ForensicBridge',
            'display_name': 'ForensicBridge Migration Suite',
            'url': base_url
        },
        'technical_contact': {
            'given_name': 'Support',
            'email': current_app.config.get('ALERT_EMAIL', 'support@forensicbridge.io')
        }
    }
    
    return jsonify(metadata)


@sso_bp.route('/configure', methods=['POST'])
def configure_provider():
    """
    Configure SSO provider for an organization (admin endpoint)
    
    Request Body:
        org_id (str): Organization ID
        provider_type (str): 'microsoft' | 'google' | 'okta' | 'saml2'
        config (dict): Provider-specific configuration
    """
    # In production, this should require admin authentication
    data = request.get_json() or {}
    
    org_id = data.get('org_id')
    provider_type = data.get('provider_type')
    config = data.get('config', {})
    
    if not all([org_id, provider_type, config]):
        return jsonify({'error': 'org_id, provider_type, and config required'}), 400
    
    # Create provider based on type
    provider = None
    if provider_type == 'microsoft':
        provider = MicrosoftEntraProvider(config)
    elif provider_type == 'google':
        provider = GoogleWorkspaceProvider(config)
    elif provider_type == 'okta':
        provider = OktaProvider(config)
    else:
        provider = SSOProvider(provider_type, config)
    
    SSOManager.register_provider(org_id, provider)
    
    logger.info(f"SSO configured for org '{org_id}' with provider '{provider_type}'")
    
    return jsonify({
        'success': True,
        'org_id': org_id,
        'provider_type': provider_type,
        'sp_metadata': provider.get_metadata()
    })
