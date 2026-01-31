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
from datetime import datetime, timedelta
import requests
import logging
import secrets

qbo_bp = Blueprint('qbo', __name__, url_prefix='/api/qbo')
logger = logging.getLogger(__name__)

# Intuit OAuth endpoints
INTUIT_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
INTUIT_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
INTUIT_REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"


@qbo_bp.route('/connect')
@login_required
def connect_qbo():
    """
    Initiate OAuth flow with QuickBooks Online
    
    Redirects user to Intuit's authorization page
    """
    try:
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)
        session['qbo_oauth_state'] = state
        
        # Get credentials from config
        client_id = current_app.config.get('QBO_CLIENT_ID')
        redirect_uri = current_app.config.get('QBO_REDIRECT_URI')
        
        if not client_id:
            return jsonify({
                'success': False,
                'error': 'QuickBooks integration not configured'
            }), 500
        
        # Build authorization URL
        auth_url = (
            f"{INTUIT_AUTH_URL}"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope=com.intuit.quickbooks.accounting"
            f"&state={state}"
        )
        
        logger.info(f"User {current_user.id} initiating QBO OAuth flow")
        
        return redirect(auth_url)
        
    except Exception as e:
        logger.exception(f"Failed to initiate QBO OAuth: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to initiate QuickBooks connection'
        }), 500


@qbo_bp.route('/callback')
@login_required
def qbo_callback():
    """
    Handle OAuth callback from QuickBooks
    
    Exchanges authorization code for access/refresh tokens
    """
    try:
        # Get callback parameters
        code = request.args.get('code')
        realm_id = request.args.get('realmId')
        state = request.args.get('state')
        error = request.args.get('error')
        
        # Check for errors
        if error:
            logger.warning(f"QBO OAuth error: {error}")
            frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:3000')
            return redirect(f"{frontend_url}/settings?qbo=error&message={error}")
        
        # Verify state for CSRF protection
        stored_state = session.pop('qbo_oauth_state', None)
        if not stored_state or state != stored_state:
            logger.warning("QBO OAuth state mismatch - possible CSRF attack")
            return jsonify({'error': 'Invalid state parameter'}), 400
        
        if not code or not realm_id:
            return jsonify({'error': 'Missing authorization code or realm ID'}), 400
        
        # Exchange code for tokens
        client_id = current_app.config.get('QBO_CLIENT_ID')
        client_secret = current_app.config.get('QBO_CLIENT_SECRET')
        redirect_uri = current_app.config.get('QBO_REDIRECT_URI')
        
        # MED-08 FIX: Add timeout to external HTTP calls
        response = requests.post(
            INTUIT_TOKEN_URL,
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': redirect_uri
            },
            auth=(client_id, client_secret),
            headers={'Accept': 'application/json'},
            timeout=(10, 30)  # (connect timeout, read timeout)
        )
        
        if response.status_code != 200:
            logger.error(f"QBO token exchange failed: {response.text}")
            return jsonify({'error': 'Token exchange failed'}), 400
        
        tokens = response.json()

        # Calculate token expiration
        expires_in = tokens.get('expires_in', 3600)
        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # CRITICAL FIX: Store tokens securely using encrypted setter
        # Direct assignment bypasses encryption - must use set_qbo_tokens() method
        current_user.set_qbo_tokens(
            access_token=tokens.get('access_token'),
            refresh_token=tokens.get('refresh_token'),
            realm_id=realm_id,
            expires_at=token_expires_at
        )
        
        db.session.commit()
        
        logger.info(f"User {current_user.id} connected to QBO realm {realm_id}")
        
        # Redirect to frontend with success
        frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:3000')
        return redirect(f"{frontend_url}/settings?qbo=connected")
        
    except Exception as e:
        logger.exception(f"QBO OAuth callback failed: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to complete QuickBooks connection'
        }), 500


@qbo_bp.route('/disconnect', methods=['POST'])  # MED-14 FIX: Remove GET method for state-changing operation
@login_required
def disconnect_qbo():
    """
    Disconnect from QuickBooks Online

    Revokes OAuth tokens and clears stored credentials.
    Required by Intuit for App Store listing.

    MED-14 FIX: Changed from POST+GET to POST only to prevent CSRF via GET requests.
    """
    try:
        # Revoke token at Intuit if we have one
        if current_user.qbo_refresh_token:
            client_id = current_app.config.get('QBO_CLIENT_ID')
            client_secret = current_app.config.get('QBO_CLIENT_SECRET')
            
            try:
                # MED-08 FIX: Add timeout to external HTTP calls
                requests.post(
                    INTUIT_REVOKE_URL,
                    data={'token': current_user.qbo_refresh_token},
                    auth=(client_id, client_secret),
                    headers={'Accept': 'application/json'},
                    timeout=(10, 30)  # (connect timeout, read timeout)
                )
            except Exception as revoke_error:
                # Log but don't fail - we'll clear locally anyway
                logger.warning(f"Failed to revoke QBO token: {str(revoke_error)}")
        
        # Clear stored tokens
        realm_id = current_user.qbo_realm_id  # Save for logging
        current_user.qbo_access_token = None
        current_user.qbo_refresh_token = None
        current_user.qbo_realm_id = None
        current_user.qbo_token_expires_at = None
        current_user.qbo_connected_at = None
        
        db.session.commit()
        
        logger.info(f"User {current_user.id} disconnected from QBO (realm: {realm_id})")
        
        return jsonify({
            'success': True,
            'message': 'Successfully disconnected from QuickBooks Online'
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to disconnect QBO: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to disconnect from QuickBooks'
        }), 500


@qbo_bp.route('/status')
@login_required
def qbo_status():
    """
    Check QuickBooks Online connection status
    
    Returns connection state and token validity
    """
    try:
        is_connected = bool(current_user.qbo_refresh_token)
        is_expired = False
        
        if current_user.qbo_token_expires_at:
            is_expired = datetime.utcnow() > current_user.qbo_token_expires_at
        
        return jsonify({
            'success': True,
            'connected': is_connected,
            'realm_id': current_user.qbo_realm_id,
            'connected_at': current_user.qbo_connected_at.isoformat() if current_user.qbo_connected_at else None,
            'token_expired': is_expired,
            'needs_reauth': is_connected and is_expired
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get QBO status: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get connection status'
        }), 500


@qbo_bp.route('/refresh', methods=['POST'])
@login_required
def refresh_qbo_token():
    """
    Refresh expired QBO access token
    
    Uses refresh token to get new access token
    """
    try:
        if not current_user.qbo_refresh_token:
            return jsonify({
                'success': False,
                'error': 'Not connected to QuickBooks'
            }), 400
        
        client_id = current_app.config.get('QBO_CLIENT_ID')
        client_secret = current_app.config.get('QBO_CLIENT_SECRET')
        
        # MED-08 FIX: Add timeout to external HTTP calls
        response = requests.post(
            INTUIT_TOKEN_URL,
            data={
                'grant_type': 'refresh_token',
                'refresh_token': current_user.qbo_refresh_token
            },
            auth=(client_id, client_secret),
            headers={'Accept': 'application/json'},
            timeout=(10, 30)  # (connect timeout, read timeout)
        )
        
        if response.status_code != 200:
            logger.error(f"QBO token refresh failed: {response.text}")
            return jsonify({
                'success': False,
                'error': 'Token refresh failed - please reconnect'
            }), 400
        
        tokens = response.json()

        # Calculate token expiration
        expires_in = tokens.get('expires_in', 3600)
        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # CRITICAL FIX: Update tokens using encrypted setter
        # Direct assignment bypasses encryption - must use set_qbo_tokens() method
        current_user.set_qbo_tokens(
            access_token=tokens.get('access_token'),
            refresh_token=tokens.get('refresh_token') or current_user.get_qbo_refresh_token(),
            realm_id=current_user.qbo_realm_id,
            expires_at=token_expires_at
        )
        
        db.session.commit()
        
        logger.info(f"User {current_user.id} refreshed QBO token")
        
        return jsonify({
            'success': True,
            'message': 'Token refreshed successfully'
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to refresh QBO token: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to refresh token'
        }), 500
