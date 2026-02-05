"""
QuickBooks Online OAuth Integration API

Handles OAuth2 flow for connecting to QuickBooks Online:
- /api/qbo/connect - Initiate OAuth flow
- /api/qbo/callback - Handle OAuth callback
- /api/qbo/disconnect - Disconnect from QBO
- /api/qbo/status - Check connection status
"""

from flask import Blueprint, request, redirect, jsonify, session, current_app, url_for
from flask_login import login_required, current_user
from models.database import db
from datetime import datetime, timedelta, timezone
import requests
import logging
import secrets
import urllib.parse

qbo_bp = Blueprint("qbo", __name__, url_prefix="/api/qbo")
logger = logging.getLogger(__name__)

# Intuit OAuth endpoints
INTUIT_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
INTUIT_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
INTUIT_REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"


@qbo_bp.route("/connect")
@login_required
def connect_qbo():
    """
    Initiate OAuth flow with QuickBooks Online

    Redirects user to Intuit's authorization page
    """
    try:
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)
        session["qbo_oauth_state"] = state

        # Get credentials from config
        client_id = current_app.config.get("QBO_CLIENT_ID")
        redirect_uri = current_app.config.get("QBO_REDIRECT_URI")

        if not client_id:
            return (
                jsonify(
                    {"success": False, "error": "QuickBooks integration not configured"}
                ),
                500,
            )

        # Build authorization URL with proper URL encoding
        # CRITICAL FIX: URL encode all parameters to prevent injection attacks
        auth_params = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "com.intuit.quickbooks.accounting",
                "state": state,
            }
        )
        auth_url = f"{INTUIT_AUTH_URL}?{auth_params}"

        logger.info(f"User {int(current_user.get_id())} initiating QBO OAuth flow")

        return redirect(auth_url)

    except Exception as e:
        logger.exception(f"Failed to initiate QBO OAuth: {str(e)}")
        return (
            jsonify(
                {"success": False, "error": "Failed to initiate QuickBooks connection"}
            ),
            500,
        )


@qbo_bp.route("/callback")
@login_required
def qbo_callback():
    """
    Handle OAuth callback from QuickBooks

    Exchanges authorization code for access/refresh tokens
    """
    try:
        # Get callback parameters
        code = request.args.get("code")
        realm_id = request.args.get("realmId")
        state = request.args.get("state")
        error = request.args.get("error")

        # Check for errors
        if error:
            logger.warning(f"QBO OAuth error: {error}")
            frontend_url = current_app.config.get(
                "FRONTEND_URL", "http://localhost:3000"
            )
            # CRITICAL FIX: Use whitelist-based sanitization to prevent XSS and information disclosure
            from utils.error_sanitizer import (
                sanitize_qbo_error_for_url,
                get_qbo_user_message,
            )

            safe_error = sanitize_qbo_error_for_url(error)
            user_message = urllib.parse.quote(get_qbo_user_message(error))
            return redirect(
                f"{frontend_url}/settings?qbo=error&code={safe_error}&message={user_message}"
            )

        # Verify state for CSRF protection
        stored_state = session.pop("qbo_oauth_state", None)
        if not stored_state or state != stored_state:
            logger.warning("QBO OAuth state mismatch - possible CSRF attack")
            return jsonify({"error": "Invalid state parameter"}), 400

        if not code or not realm_id:
            return jsonify({"error": "Missing authorization code or realm ID"}), 400

        # Exchange code for tokens
        client_id = current_app.config.get("QBO_CLIENT_ID")
        client_secret = current_app.config.get("QBO_CLIENT_SECRET")
        redirect_uri = current_app.config.get("QBO_REDIRECT_URI")

        # MED-08 FIX: Add timeout to external HTTP calls
        response = requests.post(
            INTUIT_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
            timeout=(10, 30),  # (connect timeout, read timeout)
        )

        if response.status_code != 200:
            logger.error(f"QBO token exchange failed: {response.text}")
            return jsonify({"error": "Token exchange failed"}), 400

        tokens = response.json()

        # Calculate token expiration
        expires_in = tokens.get("expires_in", 3600)
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # CRITICAL FIX: Store tokens securely using encrypted setter
        # Direct assignment bypasses encryption - must use set_qbo_tokens() method
        current_user.set_qbo_tokens(
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            realm_id=realm_id,
            expires_at=token_expires_at,
        )

        db.session.commit()

        logger.info(
            f"User {int(current_user.get_id())} connected to QBO realm {realm_id}"
        )

        # Redirect to frontend with success
        frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:3000")
        return redirect(f"{frontend_url}/settings?qbo=connected")

    except Exception as e:
        logger.exception(f"QBO OAuth callback failed: {str(e)}")
        db.session.rollback()
        return (
            jsonify(
                {"success": False, "error": "Failed to complete QuickBooks connection"}
            ),
            500,
        )


def revoke_qbo_tokens(user, reason: str = "user_disconnect"):
    """
    Revoke all QBO OAuth tokens for a user at the Intuit server.

    This is a standalone function so it can be called from:
    - /api/qbo/disconnect endpoint
    - /api/auth/logout endpoint (full session cleanup)
    - Account deletion flows

    Args:
        user: User model instance with QBO tokens
        reason: Reason for revocation (for logging)

    Returns:
        bool: True if revocation succeeded or no tokens to revoke
    """
    if not user:
        return True

    client_id = current_app.config.get("QBO_CLIENT_ID")
    client_secret = current_app.config.get("QBO_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.warning(
            "QBO client credentials not configured - skipping token revocation"
        )
        return True

    tokens_revoked = 0
    errors = []

    # CRITICAL FIX: Use decrypted token getters, NOT raw encrypted column values.
    # user.qbo_access_token contains Fernet ciphertext - Intuit needs the plaintext.
    # Previously sent encrypted garbage to Intuit, causing silent revocation failure.

    # Revoke access token first (if present)
    access_token = (
        user.get_qbo_access_token() if hasattr(user, "get_qbo_access_token") else None
    )
    if access_token:
        try:
            response = requests.post(
                INTUIT_REVOKE_URL,
                data={"token": access_token},
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
                timeout=(10, 30),
            )
            if response.status_code in (200, 204):
                tokens_revoked += 1
                logger.info(f"Revoked QBO access token for user {user.id} ({reason})")
            else:
                logger.warning(
                    f"QBO access token revocation returned {response.status_code}"
                )
        except Exception as e:
            errors.append(f"access_token: {str(e)}")
            logger.warning(f"Failed to revoke QBO access token: {e}")

    # Revoke refresh token (if present)
    refresh_token = (
        user.get_qbo_refresh_token() if hasattr(user, "get_qbo_refresh_token") else None
    )
    if refresh_token:
        try:
            response = requests.post(
                INTUIT_REVOKE_URL,
                data={"token": refresh_token},
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
                timeout=(10, 30),
            )
            if response.status_code in (200, 204):
                tokens_revoked += 1
                logger.info(f"Revoked QBO refresh token for user {user.id} ({reason})")
            else:
                logger.warning(
                    f"QBO refresh token revocation returned {response.status_code}"
                )
        except Exception as e:
            errors.append(f"refresh_token: {str(e)}")
            logger.warning(f"Failed to revoke QBO refresh token: {e}")

    if errors:
        logger.warning(f"QBO token revocation had errors for user {user.id}: {errors}")

    return len(errors) == 0


@qbo_bp.route(
    "/disconnect", methods=["POST"]
)  # MED-14 FIX: Remove GET method for state-changing operation
@login_required
def disconnect_qbo():
    """
    Disconnect from QuickBooks Online

    Revokes OAuth tokens at Intuit AND clears stored credentials locally.
    Required by Intuit for App Store listing.

    MED-14 FIX: Changed from POST+GET to POST only to prevent CSRF via GET requests.
    """
    try:
        # Revoke tokens at Intuit (both access and refresh)
        revoke_qbo_tokens(current_user, reason="user_disconnect")

        # Clear stored tokens
        realm_id = current_user.qbo_realm_id  # Save for logging
        current_user.qbo_access_token = None
        current_user.qbo_refresh_token = None
        current_user.qbo_realm_id = None
        current_user.qbo_token_expires_at = None
        current_user.qbo_connected_at = None

        db.session.commit()

        logger.info(
            f"User {int(current_user.get_id())} disconnected from QBO (realm: {realm_id})"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Successfully disconnected from QuickBooks Online",
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(f"Failed to disconnect QBO: {str(e)}")
        db.session.rollback()
        return (
            jsonify(
                {"success": False, "error": "Failed to disconnect from QuickBooks"}
            ),
            500,
        )


@qbo_bp.route("/status")
@login_required
def qbo_status():
    """
    Check QuickBooks Online connection status

    Returns connection state and token validity
    """
    try:
        # Use realm_id for connection check (qbo_refresh_token is Fernet ciphertext,
        # but checking it as truthy is fine for boolean presence - realm_id is more explicit)
        is_connected = bool(
            current_user.qbo_realm_id and current_user.qbo_refresh_token
        )
        is_expired = False

        if current_user.qbo_token_expires_at:
            is_expired = datetime.now(timezone.utc) > current_user.qbo_token_expires_at

        return (
            jsonify(
                {
                    "success": True,
                    "connected": is_connected,
                    "realm_id": current_user.qbo_realm_id,
                    "connected_at": (
                        current_user.qbo_connected_at.isoformat()
                        if current_user.qbo_connected_at
                        else None
                    ),
                    "token_expired": is_expired,
                    "needs_reauth": is_connected and is_expired,
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(f"Failed to get QBO status: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to get connection status"}),
            500,
        )


@qbo_bp.route("/refresh", methods=["POST"])
@login_required
def refresh_qbo_token():
    """
    Refresh expired QBO access token

    Uses refresh token to get new access token
    """
    try:
        if not current_user.qbo_refresh_token:
            return (
                jsonify({"success": False, "error": "Not connected to QuickBooks"}),
                400,
            )

        client_id = current_app.config.get("QBO_CLIENT_ID")
        client_secret = current_app.config.get("QBO_CLIENT_SECRET")

        # CRITICAL FIX: Decrypt refresh token before sending to Intuit.
        # current_user.qbo_refresh_token is Fernet ciphertext - Intuit needs plaintext.
        decrypted_refresh_token = current_user.get_qbo_refresh_token()
        if not decrypted_refresh_token:
            logger.error("Failed to decrypt QBO refresh token - token may be corrupted")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Token decryption failed - please reconnect to QuickBooks",
                    }
                ),
                400,
            )

        # MED-08 FIX: Add timeout to external HTTP calls
        response = requests.post(
            INTUIT_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": decrypted_refresh_token,
            },
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
            timeout=(10, 30),  # (connect timeout, read timeout)
        )

        if response.status_code != 200:
            logger.error(f"QBO token refresh failed: {response.text}")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Token refresh failed - please reconnect",
                    }
                ),
                400,
            )

        tokens = response.json()

        # Calculate token expiration
        expires_in = tokens.get("expires_in", 3600)
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # CRITICAL FIX: Update tokens using encrypted setter
        # Direct assignment bypasses encryption - must use set_qbo_tokens() method
        current_user.set_qbo_tokens(
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token")
            or current_user.get_qbo_refresh_token(),
            realm_id=current_user.qbo_realm_id,
            expires_at=token_expires_at,
        )

        db.session.commit()

        logger.info(f"User {int(current_user.get_id())} refreshed QBO token")

        return (
            jsonify({"success": True, "message": "Token refreshed successfully"}),
            200,
        )

    except Exception as e:
        logger.exception(f"Failed to refresh QBO token: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": "Failed to refresh token"}), 500
