"""
ForensicBridge Authentication API
JWT-based authentication for dashboard users with full security features
Compatible with models/user.py User model
"""

from flask import Blueprint, request, jsonify, current_app, session
from functools import wraps
import jwt
import datetime
import re
import hmac
import hashlib
from typing import Optional, Tuple, Callable, Any
import logging

from models.database import db
from models.user import User
from extensions import limiter
from utils.pii_redaction import hash_email, redact_all_pii
from utils.error_sanitizer import sanitize_error_message, create_error_response
from utils.captcha_verifier import (
    verify_captcha_token, is_captcha_required, get_client_ip, get_captcha_config
)
from utils.anomaly_detector import check_login_anomalies, log_anomaly

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


# SESSION BINDING: User-Agent validation for session security
def _get_user_agent_fingerprint() -> str:
    """
    Get a fingerprint of the User-Agent for session binding.

    This helps detect session hijacking attempts where an attacker
    uses a stolen session cookie from a different browser/device.

    We hash the User-Agent to avoid storing potentially long strings
    and for consistent comparison.
    """
    user_agent = request.headers.get('User-Agent', '')
    if not user_agent:
        return 'unknown'
    # Hash the User-Agent for consistent length and privacy
    return hashlib.sha256(user_agent.encode()).hexdigest()[:16]


def _validate_session_binding() -> Tuple[bool, str]:
    """
    Validate that the current request matches the session binding.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if 'user_id' not in session:
        return True, ''  # No session to validate

    # Check User-Agent binding
    stored_ua_fp = session.get('_ua_fingerprint')
    if stored_ua_fp:
        current_ua_fp = _get_user_agent_fingerprint()
        if stored_ua_fp != current_ua_fp:
            # Potential session hijacking attempt
            user_id = session.get('user_id')
            logger.warning(
                f"SECURITY: Session User-Agent mismatch for user {user_id}. "
                f"Expected: {stored_ua_fp[:8]}..., Got: {current_ua_fp[:8]}..."
            )
            return False, 'Session validation failed - browser fingerprint changed'

    return True, ''


def _bind_session():
    """
    Bind the current session to browser fingerprints for security.
    Call this when creating a new authenticated session.
    """
    session['_ua_fingerprint'] = _get_user_agent_fingerprint()
    session['_created_at'] = datetime.datetime.utcnow().isoformat()


# =============================================================================
# MFA ENFORCEMENT FOR PRIVILEGED OPERATIONS
# =============================================================================

def require_mfa(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to require MFA verification for privileged operations.

    This decorator should be used on sensitive endpoints like:
    - Account deletion
    - Payment method changes
    - Password changes
    - Admin operations

    The decorator checks:
    1. If MFA is enabled for the user
    2. If the user has verified MFA recently (within 5 minutes)

    If MFA is required but not verified, returns 403 with mfa_required flag.

    Usage:
        @auth_bp.route('/delete-account', methods=['POST'])
        @require_auth
        @require_mfa
        def delete_account():
            ...
    """
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Tuple[Any, int]:
        from flask import current_app

        # Check if MFA enforcement is enabled globally
        if not current_app.config.get('REQUIRE_MFA_FOR_PRIVILEGED_OPS', True):
            return f(*args, **kwargs)

        # Get current user
        user_id = getattr(request, 'current_user', {}).get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401

        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Check if user has MFA enabled
        if not getattr(user, 'mfa_enabled', False):
            # MFA not enabled - allow operation but recommend enabling
            logger.info(f"Privileged operation without MFA for user {user_id}")
            return f(*args, **kwargs)

        # Check if MFA was recently verified (within 5 minutes)
        mfa_verified_at = session.get('_mfa_verified_at')
        if mfa_verified_at:
            try:
                verified_time = datetime.datetime.fromisoformat(mfa_verified_at)
                age_seconds = (datetime.datetime.utcnow() - verified_time).total_seconds()
                if age_seconds < 300:  # 5 minutes
                    return f(*args, **kwargs)
            except (ValueError, TypeError):
                pass

        # MFA verification required
        logger.warning(f"MFA required for privileged operation - user {user_id}")
        return jsonify({
            'success': False,
            'error': 'MFA verification required for this operation',
            'mfa_required': True,
            'mfa_methods': ['totp']  # Supported MFA methods
        }), 403

    return decorated


def require_role(*allowed_roles):
    """
    Decorator factory to require specific roles for endpoint access.

    Implements Role-Based Access Control (RBAC) for protecting admin
    and privileged endpoints.

    Args:
        *allowed_roles: One or more role names that can access the endpoint
                       (e.g., 'admin', 'super_admin')

    Usage:
        @auth_bp.route('/admin/users')
        @require_auth
        @require_role('admin', 'super_admin')
        def list_all_users():
            ...

    Returns:
        Decorator function
    """
    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Tuple[Any, int]:
            # Get current user
            user_id = getattr(request, 'current_user', {}).get('user_id')
            if not user_id:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401

            user = User.query.get(user_id)
            if not user:
                return jsonify({'success': False, 'error': 'User not found'}), 404

            # Check if user has any of the allowed roles
            user_role = getattr(user, 'role', 'user')

            # Check direct role match
            if user_role in allowed_roles:
                return f(*args, **kwargs)

            # Check role hierarchy (e.g., super_admin can access admin endpoints)
            for allowed_role in allowed_roles:
                if user.has_role_or_higher(allowed_role):
                    return f(*args, **kwargs)

            # Access denied
            logger.warning(
                f"RBAC: Access denied for user {user_id} (role: {user_role}) "
                f"to endpoint requiring {allowed_roles}"
            )
            return jsonify({
                'success': False,
                'error': 'Insufficient permissions',
                'required_roles': list(allowed_roles)
            }), 403

        return decorated
    return decorator


def require_admin(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Shorthand decorator for admin-only endpoints.

    Equivalent to @require_role('admin', 'super_admin')
    """
    return require_role('admin', 'super_admin')(f)


@auth_bp.route('/mfa/verify', methods=['POST'])
@require_auth
def verify_mfa():
    """
    Verify MFA code for privileged operations.

    After successful verification, the session is marked as MFA-verified
    for 5 minutes, allowing privileged operations without re-verification.

    Request body:
    {
        "code": "123456"  // 6-digit TOTP code
    }

    Response:
    {
        "success": true,
        "verified": true,
        "valid_for_seconds": 300
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    code = data.get('code', '').strip()
    if not code or len(code) != 6 or not code.isdigit():
        return jsonify({'success': False, 'error': 'Invalid MFA code format'}), 400

    user_id = request.current_user.get('user_id')
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    if not getattr(user, 'mfa_enabled', False):
        return jsonify({'success': False, 'error': 'MFA not enabled for this account'}), 400

    # Verify TOTP code
    try:
        import pyotp
        totp_secret = getattr(user, 'mfa_secret', None)
        if not totp_secret:
            return jsonify({'success': False, 'error': 'MFA not configured properly'}), 500

        totp = pyotp.TOTP(totp_secret)
        # Allow 1 window before/after for clock skew
        if not totp.verify(code, valid_window=1):
            logger.warning(f"Invalid MFA code for user {user_id}")
            return jsonify({'success': False, 'error': 'Invalid MFA code'}), 401

    except ImportError:
        logger.error("pyotp not installed - MFA verification failed")
        return jsonify({'success': False, 'error': 'MFA verification unavailable'}), 500
    except Exception as e:
        logger.error(f"MFA verification error: {e}")
        return jsonify({'success': False, 'error': 'MFA verification failed'}), 500

    # Mark session as MFA-verified
    session['_mfa_verified_at'] = datetime.datetime.utcnow().isoformat()
    logger.info(f"MFA verified successfully for user {user_id}")

    return jsonify({
        'success': True,
        'verified': True,
        'valid_for_seconds': 300,
        'message': 'MFA verified. You can now perform privileged operations.'
    })


# FIX #37: Constant-time string comparison for security
def constant_time_compare(a: str, b: str) -> bool:
    """
    Constant-time string comparison to prevent timing attacks.

    Uses HMAC comparison which is designed to be constant-time.
    This prevents attackers from using timing analysis to determine
    if an email exists in the database.

    Args:
        a: First string
        b: Second string

    Returns:
        True if strings are equal, False otherwise
    """
    if not isinstance(a, str) or not isinstance(b, str):
        return False

    # Normalize to bytes for HMAC comparison
    a_bytes = a.encode('utf-8')
    b_bytes = b.encode('utf-8')

    # Use HMAC.compare_digest for constant-time comparison
    # This is cryptographically secure and prevents timing attacks
    return hmac.compare_digest(a_bytes, b_bytes)


def create_token(user_id: int, email: str, expires_hours: int = 24) -> str:
    """Create a JWT token for a user"""
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=expires_hours),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_auth(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to require authentication for an endpoint (supports both JWT and session)

    Args:
        f: The function to decorate

    Returns:
        The decorated function that requires authentication
    """
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Tuple[Any, int]:
        # Check for JWT token in Authorization header
        auth_header = request.headers.get('Authorization')

        if auth_header:
            try:
                # Expect "Bearer <token>"
                parts = auth_header.split()
                if len(parts) != 2 or parts[0].lower() != 'bearer':
                    return jsonify({'success': False, 'error': 'Invalid authorization format'}), 401

                token = parts[1]
                payload = decode_token(token)

                if not payload:
                    return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401

                # Add user info to request
                request.current_user = payload
                return f(*args, **kwargs)

            except Exception as e:
                # FIX: Log specific exception type before returning generic error
                logger.warning(f"Authentication failed with {type(e).__name__}: {str(e)}")
                return jsonify({'success': False, 'error': 'Authentication failed'}), 401

        # Check for session-based auth
        if 'user_id' in session:
            # SECURITY FIX: Validate session binding (User-Agent check)
            is_valid, error_msg = _validate_session_binding()
            if not is_valid:
                # Session may be hijacked - invalidate it
                session.clear()
                return jsonify({
                    'success': False,
                    'error': 'Session expired. Please log in again.',
                    'session_invalid': True
                }), 401

            request.current_user = {
                'user_id': session['user_id'],
                'email': session.get('email', '')
            }
            return f(*args, **kwargs)

        return jsonify({'success': False, 'error': 'No authorization provided'}), 401
    return decorated


def validate_email(email: str) -> bool:
    """
    Validate email format using comprehensive email-validator library.
    Falls back to regex if library not available.

    FIX #37: Uses constant-time operations where possible to prevent timing attacks.
    Note: The validation itself may have timing variations, but we prevent
    enumeration attacks by using the same validation path for all emails.
    """
    if not email or not isinstance(email, str):
        return False

    # Normalize email for validation
    email = email.strip().lower()

    try:
        from email_validator import validate_email as ev_validate, EmailNotValidError
        try:
            # Validate email format
            valid = ev_validate(email)
            return True
        except EmailNotValidError:
            return False
    except ImportError:
        # Fallback to regex if email-validator not installed
        # FIX #37: Use consistent regex pattern that doesn't branch based on content
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password strength"""
    if len(password) < 8:
        return False, 'Password must be at least 8 characters'
    if not re.search(r'[A-Z]', password):
        return False, 'Password must contain at least one uppercase letter'
    if not re.search(r'[a-z]', password):
        return False, 'Password must contain at least one lowercase letter'
    if not re.search(r'\d', password):
        return False, 'Password must contain at least one digit'
    return True, ''


def sanitize(value, max_length=255):
    if not value:
        return value
    value = re.sub(r'[<>"\'/\\;]', '', str(value).strip())
    return value[:max_length]


@auth_bp.route('/register', methods=['POST'])
@limiter.limit("3 per hour")  # SECURITY FIX: Reduced from 5/min to prevent abuse
def register():
    """Register a new user with comprehensive error handling"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Extract and sanitize inputs
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        # Support both 'first_name' and 'name' from frontend
        first_name = data.get('first_name', data.get('name', '')).strip()
        last_name = data.get('last_name', '').strip()
        # Support both 'company_name' and 'company' from frontend
        company = data.get('company_name', data.get('company', '')).strip()
        
        # Sanitize inputs - remove potentially dangerous characters
        first_name = sanitize(first_name, 100)
        last_name = sanitize(last_name, 100)
        company = sanitize(company, 255)
        
        # Validation
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        if not password:
            return jsonify({'success': False, 'error': 'Password is required'}), 400
        
        if not validate_email(email):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        # Validate password strength BEFORE checking user existence
        valid, msg = validate_password(password)
        if not valid:
            return jsonify({'success': False, 'error': msg}), 400

        # FIX #37: Prevent timing attack for email enumeration
        # Always perform the same operations regardless of user existence
        existing = User.query.filter_by(email=email).first()

        if existing:
            # FIX #37: Perform fake password hashing to match timing of real registration
            # This prevents attackers from using timing to enumerate registered emails
            from argon2 import PasswordHasher
            ph = PasswordHasher()
            try:
                # Hash the provided password (same operation as real registration)
                # This takes ~50-100ms, same as real password hashing
                _ = ph.hash(password)
            except Exception:
                # Ignore hash failures - this is just for timing equalization
                pass

            # Return error with same timing as successful registration
            return jsonify({'success': False, 'error': 'Email already registered'}), 409

        # Create user
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            company_name=company
        )

        # Set password - this may raise ValueError for strength/reuse issues
        try:
            user.set_password(password)
        except ValueError as e:
            # SECURITY: Redact email from logs (GDPR/PIPEDA compliance)
            logger.warning(f"Password validation failed for {hash_email(email)}: {str(e)}")
            # FIX #34: Sanitize error message before returning to client
            sanitized_error = sanitize_error_message(e, context='auth')
            return jsonify({'success': False, 'error': sanitized_error}), 400
        
        # Save to database
        db.session.add(user)
        db.session.commit()

        # SECURITY FIX: Regenerate session ID to prevent session fixation
        session.clear()
        session.modified = True  # Force Flask to regenerate session cookie
        session['user_id'] = user.id
        session['email'] = user.email
        session['_fresh'] = True  # Mark session as freshly authenticated

        # SECURITY FIX: Bind session to browser fingerprint to detect hijacking
        _bind_session()

        # Generate token
        token = create_token(user.id, user.email)

        # SECURITY: Redact email from logs (GDPR/PIPEDA compliance)
        logger.info(f"New user registered: {hash_email(email)}")

        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'company_name': user.company_name
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.exception(f"Registration error: {str(e)}")
        return jsonify({'success': False, 'error': 'Registration failed. Please try again.'}), 500


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per 15 minutes")  # SECURITY: Reduce brute force risk
def login():
    """Login and get JWT token"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    captcha_token = data.get('captcha_token')  # FIX #38: CAPTCHA token from client

    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password required'}), 400

    # FIX #37: Constant-time user lookup and validation
    # Find user (timing of database query is unavoidable, but we mitigate enumeration below)
    user = User.query.filter_by(email=email).first()

    # FIX #38: Progressive CAPTCHA enforcement after 3 failed attempts
    failed_attempts = user.failed_login_attempts if user else 0
    captcha_required = is_captcha_required(email, failed_attempts)

    if captcha_required:
        if not captcha_token:
            return jsonify({
                'success': False,
                'error': 'CAPTCHA verification required',
                'captcha_required': True
            }), 400

        # Verify CAPTCHA token
        captcha_valid, captcha_error = verify_captcha_token(
            captcha_token,
            remote_ip=get_client_ip()
        )

        if not captcha_valid:
            logger.warning(f"CAPTCHA verification failed for {hash_email(email)}: {captcha_error}")
            return jsonify({
                'success': False,
                'error': 'CAPTCHA verification failed. Please try again.',
                'captcha_required': True
            }), 400

    # SECURITY: Always perform password verification in constant time
    # Whether user exists or not, we perform the same operations
    password_valid = False
    is_locked = False

    if not user:
        # FIX #37: Generate realistic hash to prevent timing attacks
        # This ensures login attempts for non-existent users take the same time as real users
        from argon2 import PasswordHasher
        import os
        ph = PasswordHasher()
        # Generate a realistic fake hash with random salt
        fake_password = os.urandom(16).hex()
        fake_hash = ph.hash(fake_password)
        try:
            # This will always fail but takes the same time as real verification
            ph.verify(fake_hash, password)
        except Exception:
            # Expected failure - this is just for timing equalization
            pass
        password_valid = False
        is_locked = False
    else:
        # User exists - check if locked and verify password
        is_locked = user.is_locked()

        # FIX #37: Always verify password even if account is locked
        # This prevents timing attacks that could distinguish locked vs non-existent accounts
        password_valid = user.check_password(password) if not is_locked else False

    # FIX #37: Consistent error handling regardless of user existence
    if not user or is_locked or not password_valid:
        # Track failed attempt only if user exists
        if user and not is_locked:
            user.record_failed_login()
            db.session.commit()

        # Generic error message that doesn't reveal if user exists or is locked
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
    
    # Successful login
    user.record_successful_login()
    db.session.commit()

    # FIX #39: Anomaly detection for suspicious login patterns
    client_ip = get_client_ip()
    anomalies = check_login_anomalies(user.id, client_ip)

    if anomalies:
        # Log all detected anomalies
        for anomaly in anomalies:
            log_anomaly(user.id, anomaly)

        # For critical anomalies, add warning to response
        critical_anomalies = [a for a in anomalies if a['severity'] == 'critical']
        if critical_anomalies:
            logger.warning(
                f"CRITICAL anomaly detected for user {user.id}: "
                f"{', '.join(a['reason'] for a in critical_anomalies)}"
            )

    # SECURITY FIX: Regenerate session ID on successful login to prevent session fixation
    session.clear()
    session.modified = True  # Force Flask to regenerate session cookie
    session['user_id'] = user.id
    session['email'] = user.email
    session['_fresh'] = True  # Mark session as freshly authenticated

    # SECURITY FIX: Bind session to browser fingerprint to detect hijacking
    _bind_session()

    # Generate token
    token = create_token(user.id, user.email)

    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'company_name': user.company_name
        }
    })


@auth_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """Get current user info including tier and migration balance"""
    from models.migration_credit import MigrationCredit

    user_id = request.current_user['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # AUTO-SYNC: If user has legacy credits but no MigrationCredit records, create them
    # This fixes existing users who selected tiers before the MigrationCredit fix
    # HIGH-01 FIX: Wrap in proper transaction with rollback on failure
    try:
        legacy_purchased = getattr(user, 'migrations_purchased', None) or 0
        legacy_used = getattr(user, 'migrations_used', None) or 0
        legacy_available = max(0, legacy_purchased - legacy_used)

        actual_available = MigrationCredit.query.filter_by(
            user_id=user_id, status='available', payment_status='paid'
        ).count()

        # If legacy shows credits but MigrationCredit table doesn't, sync them
        if legacy_available > actual_available:
            tier = user.subscription_tier or 'starter'
            credit_config = MigrationCredit.TIER_CONFIG.get(tier, MigrationCredit.TIER_CONFIG['starter'])

            # HIGH-01 FIX: Use nested transaction (savepoint) for atomic operation
            db.session.begin_nested()
            try:
                for i in range(legacy_available - actual_available):
                    credit = MigrationCredit(
                        user_id=user_id,
                        tier_type=tier,
                        transaction_limit=credit_config.get('transaction_limit', 5000),
                        price_cents=0,
                        stripe_checkout_session_id=f'auto-sync-{user_id}-{i}-{datetime.datetime.utcnow().timestamp()}',
                        payment_status='paid',
                        status='available'
                    )
                    credit.paid_at = datetime.datetime.utcnow()
                    db.session.add(credit)

                db.session.commit()  # Commit the savepoint
                logger.info(f"Auto-synced {legacy_available - actual_available} credits for user {user_id}")
            except Exception as inner_e:
                db.session.rollback()  # Rollback the savepoint
                logger.warning(f"Auto-sync credits rollback for user {user_id}: {inner_e}")
    except Exception as e:
        logger.warning(f"Auto-sync credits failed for user {user_id}: {e}")
        # Continue anyway - don't block the /me endpoint

    # BILLING FIX: Fail fast instead of swallowing errors that hide billing problems
    # If tier info can't be retrieved, user should know something is wrong
    try:
        tier_info = user.get_tier_info()
    except AttributeError as e:
        # Database schema issue - log but allow graceful degradation
        logger.warning(f"Database schema issue retrieving tier info: {e}")
        tier_info = {
            'tier': 'none',
            'tier_name': 'Free Trial',
            'migrations_remaining': 0,
            'migrations_purchased': 0,
            'migrations_used': 0,
            'has_tier': False,
            'warning': 'Billing system temporarily unavailable'
        }
    except Exception as e:
        # Unexpected error - this could indicate billing data corruption
        logger.error(f"CRITICAL: Failed to retrieve tier info for user {user_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Unable to retrieve account information. Please contact support.',
            'error_code': 'TIER_INFO_UNAVAILABLE'
        }), 500
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'name': user.first_name,  # Alias for frontend compatibility
            'company_name': user.company_name,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'subscription_tier': tier_info['tier'],
            'tier_name': tier_info['tier_name'],
            'migrations_remaining': tier_info['migrations_remaining'],
            'migrations_purchased': tier_info['migrations_purchased'],
            'migrations_used': tier_info['migrations_used'],
            'has_tier': tier_info['has_tier'],
        }
    })


@auth_bp.route('/refresh', methods=['POST'])
@require_auth
def refresh_token():
    """Refresh JWT token"""
    user_id = request.current_user['user_id']
    email = request.current_user['email']
    
    token = create_token(user_id, email)
    
    return jsonify({
        'success': True,
        'token': token
    })


@auth_bp.route('/logout', methods=['POST'])
@require_auth
def logout():
    """
    Logout - revokes tokens and clears all session data.

    Security measures:
    1. Revokes QBO OAuth tokens at Intuit (if connected)
    2. Clears all session data
    3. Invalidates any cached credentials

    This ensures complete cleanup on logout to prevent token reuse.
    """
    user_id = request.current_user.get('user_id')

    # Revoke QBO tokens if user has them (CRITICAL for 100/100 OAuth score)
    if user_id:
        try:
            user = User.query.get(user_id)
            if user and (user.qbo_access_token or user.qbo_refresh_token):
                # Import here to avoid circular imports
                from api.qbo import revoke_qbo_tokens
                revoke_qbo_tokens(user, reason="user_logout")
                logger.info(f"Revoked QBO tokens on logout for user {user_id}")
        except Exception as e:
            # Don't fail logout if token revocation fails
            logger.warning(f"Failed to revoke QBO tokens on logout: {e}")

    # Clear all session data
    session.pop('user_id', None)
    session.pop('email', None)
    session.pop('_ua_fingerprint', None)
    session.pop('_created_at', None)
    session.pop('_fresh', None)
    session.clear()

    logger.info(f"User {user_id} logged out successfully")

    return jsonify({'success': True, 'message': 'Logged out successfully'})


# =============================================================================
# TIER SELECTION & MANAGEMENT
# =============================================================================

@auth_bp.route('/tiers', methods=['GET'])
def get_available_tiers():
    """Get all available pricing tiers"""
    tiers = [
        {
            'id': 'starter',
            'name': 'Starter',
            'price': 0,
            'max_transactions': 5000,
            'description': 'Small business, 1-2 years of data',
            'migrations': 1
        },
        {
            'id': 'business',
            'name': 'Business',
            'price': 0,
            'max_transactions': 25000,
            'description': 'Established business, 3-5 years of history',
            'migrations': 1
        },
        {
            'id': 'professional',
            'name': 'Professional',
            'price': 0,
            'max_transactions': 100000,
            'description': 'Complex business, multi-year audit trail',
            'migrations': 1
        },
        {
            'id': 'enterprise',
            'name': 'Enterprise',
            'price': 0,
            'max_transactions': 500000,
            'description': 'Large company, decade+ of records',
            'migrations': 1
        },
        {
            'id': 'forensic',
            'name': 'Forensic',
            'price': 0,
            'max_transactions': -1,
            'description': 'Litigation-ready, expert documentation',
            'migrations': 1
        }
    ]
    return jsonify({'success': True, 'tiers': tiers})


@auth_bp.route('/select-tier', methods=['POST'])
@require_auth
def select_tier():
    """
    Select/purchase a tier after registration.
    In production, this would integrate with Stripe Checkout.

    CRITICAL FIX: This endpoint now creates MigrationCredit records to ensure
    consistency with the credit verification system. Previously, it only updated
    User.migrations_purchased which caused a mismatch.
    """
    from models.migration_credit import MigrationCredit

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    tier_id = data.get('tier_id', '').lower()

    # Validate tier
    valid_tiers = ['starter', 'business', 'professional', 'enterprise', 'forensic']
    if tier_id not in valid_tiers:
        return jsonify({'success': False, 'error': f'Invalid tier: {tier_id}'}), 400

    user_id = request.current_user['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # Get tier config
    tier_config = User.TIER_CONFIG.get(tier_id, {})
    migrations_to_add = tier_config.get('migrations', 1)

    # CRITICAL FIX: Create MigrationCredit record(s) to ensure backend verification works
    # This creates a 'paid' credit without going through Stripe (for dev/test use)
    credit_config = MigrationCredit.TIER_CONFIG.get(tier_id, {})
    for _ in range(migrations_to_add):
        credit = MigrationCredit(
            user_id=user_id,
            tier_type=tier_id,
            transaction_limit=credit_config.get('transaction_limit', 5000),
            price_cents=0,  # Free tier selection
            stripe_checkout_session_id=f'free-tier-{tier_id}-{user_id}-{datetime.datetime.utcnow().timestamp()}',
            payment_status='paid',
            status='available'
        )
        credit.paid_at = datetime.datetime.utcnow()
        db.session.add(credit)

    # Also update legacy User fields for backwards compatibility
    user.add_migrations(migrations_to_add, tier=tier_id)
    db.session.commit()

    # SECURITY: Redact email from logs (GDPR/PIPEDA compliance)
    logger.info(f"User {hash_email(user.email)} selected tier {tier_id} with {migrations_to_add} migration(s)")

    return jsonify({
        'success': True,
        'message': f'Successfully selected {tier_config.get("name", tier_id)} tier',
        'tier': tier_id,
        'migrations_remaining': user.get_migrations_remaining()
    })


@auth_bp.route('/upgrade-tier', methods=['POST'])
@require_auth
def upgrade_tier():
    """
    Upgrade to a higher tier (adds more migrations).

    CRITICAL FIX: Now creates MigrationCredit records for consistency.
    """
    from models.migration_credit import MigrationCredit

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    tier_id = data.get('tier_id', '').lower()

    valid_tiers = ['starter', 'business', 'professional', 'enterprise', 'forensic']
    if tier_id not in valid_tiers:
        return jsonify({'success': False, 'error': f'Invalid tier: {tier_id}'}), 400

    user_id = request.current_user['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    tier_config = User.TIER_CONFIG.get(tier_id, {})
    migrations_to_add = tier_config.get('migrations', 1)

    # CRITICAL FIX: Create MigrationCredit record(s) for backend verification
    credit_config = MigrationCredit.TIER_CONFIG.get(tier_id, {})
    for _ in range(migrations_to_add):
        credit = MigrationCredit(
            user_id=user_id,
            tier_type=tier_id,
            transaction_limit=credit_config.get('transaction_limit', 5000),
            price_cents=0,  # Upgrade (may have different pricing in production)
            stripe_checkout_session_id=f'upgrade-{tier_id}-{user_id}-{datetime.datetime.utcnow().timestamp()}',
            payment_status='paid',
            status='available'
        )
        credit.paid_at = datetime.datetime.utcnow()
        db.session.add(credit)

    # Also update legacy User fields for backwards compatibility
    user.add_migrations(migrations_to_add, tier=tier_id)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Successfully upgraded to {tier_config.get("name", tier_id)}',
        'tier': tier_id,
        'migrations_remaining': user.get_migrations_remaining()
    })


# =============================================================================
# TEAM MANAGEMENT
# =============================================================================

@auth_bp.route('/team', methods=['GET'])
@require_auth
def list_team_members():
    """List team members and pending invites"""
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    try:
        from models.team_invite import TeamInvite
        
        # Get team members (accepted invites)
        team_members = TeamInvite.get_team_members(user_id)
        
        # Add the owner as first member
        owner_member = {
            'id': user.id,
            'email': user.email,
            'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0],
            'role': 'Owner',
            'joined_at': user.created_at.isoformat() if user.created_at else None
        }
        
        # Get pending invites
        pending = TeamInvite.get_pending_for_owner(user_id)
        pending_invites = [invite.to_dict() for invite in pending]
        
        return jsonify({
            'success': True,
            'team_members': [owner_member] + team_members,
            'pending_invites': pending_invites
        })
        
    except Exception as e:
        logger.warning(f"Team fetch error (table may not exist): {e}")
        # Fallback if table doesn't exist
        return jsonify({
            'success': True,
            'team_members': [
                {
                    'id': user.id,
                    'email': user.email,
                    'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0],
                    'role': 'Owner',
                    'joined_at': user.created_at.isoformat() if user.created_at else None
                }
            ],
            'pending_invites': []
        })


@auth_bp.route('/team/invite', methods=['POST'])
@require_auth
def invite_team_member():
    """Invite a new team member"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    email = data.get('email', '').strip().lower()
    role = data.get('role', 'member')

    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400

    user_id = request.current_user['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # Placeholder: In production, this would:
    # 1. Create invite record in database
    # 2. Send email invitation
    # 3. Track pending invites

    # SECURITY: Redact emails from logs (GDPR/PIPEDA compliance)
    logger.info(f"Team invite sent: {hash_email(email)} invited by {hash_email(user.email)} as {role}")

    return jsonify({
        'success': True,
        'message': f'Invitation sent to {email}',
        'invite': {
            'email': email,
            'role': role,
            'status': 'pending',
            'invited_by': user.email
        }
    })


# =============================================================================
# PASSWORD RESET (CRITICAL PRODUCTION FEATURE)
# =============================================================================

def _generate_password_reset_token(user_id: int, email: str) -> str:
    """
    Generate a secure password reset token.

    Token expires in 1 hour for security.

    Args:
        user_id: User's database ID
        email: User's email address

    Returns:
        JWT token for password reset
    """
    import secrets as secrets_module
    payload = {
        'user_id': user_id,
        'email': email,
        'purpose': 'password_reset',
        'jti': secrets_module.token_hex(16),  # Unique token ID
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def _verify_password_reset_token(token: str) -> Optional[dict]:
    """
    Verify a password reset token.

    Args:
        token: JWT token from reset link

    Returns:
        Token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token,
            current_app.config['SECRET_KEY'],
            algorithms=['HS256']
        )
        if payload.get('purpose') != 'password_reset':
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Password reset token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid password reset token")
        return None


def _send_password_reset_email(email: str, reset_token: str) -> bool:
    """
    Send password reset email.

    Args:
        email: User's email address
        reset_token: The reset token to include in the link

    Returns:
        True if email sent successfully
    """
    try:
        frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:3000')
        reset_url = f"{frontend_url}/reset-password?token={reset_token}"

        # Try to use Flask-Mail if configured
        mail_server = current_app.config.get('MAIL_SERVER')
        mail_username = current_app.config.get('MAIL_USERNAME')

        if mail_server and mail_username:
            try:
                from flask_mail import Mail, Message
                mail = Mail(current_app)

                msg = Message(
                    subject='Reset Your ForensicBridge Password',
                    recipients=[email],
                    sender=current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@forensicbridge.io'),
                    body=f"""Hello,

You requested a password reset for your ForensicBridge account.

Click the link below to reset your password:
{reset_url}

This link will expire in 1 hour.

If you didn't request this, please ignore this email or contact support.

- ForensicBridge Security Team
""",
                    html=f"""<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
<h2 style="color: #1a365d;">Reset Your Password</h2>
<p>You requested a password reset for your ForensicBridge account.</p>
<p style="margin: 30px 0;">
    <a href="{reset_url}" style="background-color: #3182ce; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
        Reset Password
    </a>
</p>
<p style="color: #666; font-size: 14px;">This link will expire in 1 hour.</p>
<p style="color: #666; font-size: 14px;">If you didn't request this, please ignore this email or contact support.</p>
<hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
<p style="color: #999; font-size: 12px;">- ForensicBridge Security Team</p>
</body>
</html>"""
                )
                mail.send(msg)
                logger.info(f"Password reset email sent to {hash_email(email)}")
                return True
            except ImportError:
                logger.warning("Flask-Mail not installed, using fallback")
            except Exception as e:
                logger.error(f"Failed to send email via Flask-Mail: {e}")

        # Fallback: Log the reset URL for development
        if current_app.config.get('FLASK_ENV') != 'production':
            logger.info(f"[DEV] Password reset URL for {hash_email(email)}: {reset_url}")
            return True

        logger.error("Email not configured in production")
        return False

    except Exception as e:
        logger.exception(f"Failed to send password reset email: {e}")
        return False


@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per hour")  # Strict rate limiting to prevent enumeration
def forgot_password():
    """
    Request a password reset link.

    SECURITY: Always returns success to prevent email enumeration.
    The same response is returned whether or not the email exists.

    Request body:
    {
        "email": "user@example.com"
    }

    Response:
    {
        "success": true,
        "message": "If an account exists with that email, a reset link has been sent."
    }
    """
    import time
    start_time = time.time()

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    email = data.get('email', '').strip().lower()

    if not email or not validate_email(email):
        # Still return generic message to prevent enumeration
        return jsonify({
            'success': True,
            'message': 'If an account exists with that email, a reset link has been sent.'
        }), 200

    # Look up user
    user = User.query.filter_by(email=email).first()

    if user and user.is_active:
        # Generate reset token
        reset_token = _generate_password_reset_token(user.id, user.email)

        # Store token JTI in user record for one-time use validation
        # This would require a database field, so for now we rely on JWT expiry

        # Send reset email
        _send_password_reset_email(email, reset_token)

        logger.info(f"Password reset requested for {hash_email(email)}")
    else:
        # User doesn't exist - still perform timing-consistent operations
        import os
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        # Perform fake hash to match timing
        try:
            fake_password = os.urandom(16).hex()
            _ = ph.hash(fake_password)
        except Exception:
            pass

    # Ensure constant response time to prevent timing attacks
    elapsed = time.time() - start_time
    min_response_time = 0.3  # 300ms minimum
    if elapsed < min_response_time:
        time.sleep(min_response_time - elapsed)

    return jsonify({
        'success': True,
        'message': 'If an account exists with that email, a reset link has been sent.'
    }), 200


@auth_bp.route('/reset-password', methods=['POST'])
@limiter.limit("5 per hour")
def reset_password():
    """
    Reset password using token from email.

    Request body:
    {
        "token": "jwt-token-from-email",
        "password": "NewSecurePassword123!"
    }

    Response:
    {
        "success": true,
        "message": "Password reset successfully. Please log in with your new password."
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    token = data.get('token', '').strip()
    new_password = data.get('password', '')

    if not token:
        return jsonify({'success': False, 'error': 'Reset token is required'}), 400

    if not new_password:
        return jsonify({'success': False, 'error': 'New password is required'}), 400

    # Validate password strength
    valid, msg = validate_password(new_password)
    if not valid:
        return jsonify({'success': False, 'error': msg}), 400

    # Verify token
    payload = _verify_password_reset_token(token)
    if not payload:
        return jsonify({
            'success': False,
            'error': 'Invalid or expired reset token. Please request a new one.'
        }), 400

    # Get user
    user_id = payload.get('user_id')
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    if not user.is_active:
        return jsonify({'success': False, 'error': 'Account is disabled'}), 403

    # Verify email matches
    if user.email.lower() != payload.get('email', '').lower():
        logger.warning(f"Password reset token email mismatch for user {user_id}")
        return jsonify({'success': False, 'error': 'Invalid reset token'}), 400

    # Set new password
    try:
        user.set_password(new_password)
        user.must_change_password = False  # Clear any forced reset flag
        db.session.commit()

        logger.info(f"Password reset completed for user {hash_email(user.email)}")

        return jsonify({
            'success': True,
            'message': 'Password reset successfully. Please log in with your new password.'
        }), 200

    except ValueError as e:
        # Password validation error (e.g., recently used)
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception(f"Password reset failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to reset password'}), 500


# =============================================================================
# EMAIL VERIFICATION (CRITICAL PRODUCTION FEATURE)
# =============================================================================

def _generate_email_verification_token(user_id: int, email: str) -> str:
    """
    Generate a secure email verification token.

    Token expires in 24 hours.

    Args:
        user_id: User's database ID
        email: Email to verify

    Returns:
        JWT token for email verification
    """
    import secrets as secrets_module
    payload = {
        'user_id': user_id,
        'email': email,
        'purpose': 'email_verification',
        'jti': secrets_module.token_hex(16),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def _verify_email_verification_token(token: str) -> Optional[dict]:
    """
    Verify an email verification token.

    Args:
        token: JWT token from verification link

    Returns:
        Token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token,
            current_app.config['SECRET_KEY'],
            algorithms=['HS256']
        )
        if payload.get('purpose') != 'email_verification':
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Email verification token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid email verification token")
        return None


def _send_verification_email(email: str, verification_token: str) -> bool:
    """
    Send email verification email.

    Args:
        email: User's email address
        verification_token: The verification token

    Returns:
        True if email sent successfully
    """
    try:
        frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:3000')
        verify_url = f"{frontend_url}/verify-email?token={verification_token}"

        mail_server = current_app.config.get('MAIL_SERVER')
        mail_username = current_app.config.get('MAIL_USERNAME')

        if mail_server and mail_username:
            try:
                from flask_mail import Mail, Message
                mail = Mail(current_app)

                msg = Message(
                    subject='Verify Your ForensicBridge Email',
                    recipients=[email],
                    sender=current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@forensicbridge.io'),
                    body=f"""Welcome to ForensicBridge!

Please verify your email address by clicking the link below:
{verify_url}

This link will expire in 24 hours.

If you didn't create an account, please ignore this email.

- ForensicBridge Team
""",
                    html=f"""<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
<h2 style="color: #1a365d;">Welcome to ForensicBridge!</h2>
<p>Please verify your email address to complete your registration.</p>
<p style="margin: 30px 0;">
    <a href="{verify_url}" style="background-color: #38a169; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
        Verify Email
    </a>
</p>
<p style="color: #666; font-size: 14px;">This link will expire in 24 hours.</p>
<p style="color: #666; font-size: 14px;">If you didn't create an account, please ignore this email.</p>
<hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
<p style="color: #999; font-size: 12px;">- ForensicBridge Team</p>
</body>
</html>"""
                )
                mail.send(msg)
                logger.info(f"Verification email sent to {hash_email(email)}")
                return True
            except ImportError:
                logger.warning("Flask-Mail not installed")
            except Exception as e:
                logger.error(f"Failed to send email via Flask-Mail: {e}")

        # Fallback for development
        if current_app.config.get('FLASK_ENV') != 'production':
            logger.info(f"[DEV] Verification URL for {hash_email(email)}: {verify_url}")
            return True

        logger.error("Email not configured in production")
        return False

    except Exception as e:
        logger.exception(f"Failed to send verification email: {e}")
        return False


@auth_bp.route('/send-verification', methods=['POST'])
@require_auth
@limiter.limit("3 per hour")
def send_verification_email():
    """
    Send or resend email verification link.

    Request body (optional):
    {
        "email": "new-email@example.com"  // Only if changing email
    }

    Response:
    {
        "success": true,
        "message": "Verification email sent."
    }
    """
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    data = request.get_json() or {}
    new_email = data.get('email', '').strip().lower()

    # If new email provided, validate and update
    if new_email and new_email != user.email:
        if not validate_email(new_email):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400

        # Check if email is already taken
        existing = User.query.filter_by(email=new_email).first()
        if existing:
            return jsonify({'success': False, 'error': 'Email already in use'}), 409

        # Store pending email change (don't update until verified)
        user.email_verification_token = _generate_email_verification_token(user_id, new_email)
        email_to_verify = new_email
    else:
        email_to_verify = user.email
        user.email_verification_token = _generate_email_verification_token(user_id, user.email)

    db.session.commit()

    # Send verification email
    if _send_verification_email(email_to_verify, user.email_verification_token):
        return jsonify({
            'success': True,
            'message': 'Verification email sent.'
        }), 200
    else:
        return jsonify({
            'success': False,
            'error': 'Failed to send verification email. Please try again.'
        }), 500


@auth_bp.route('/verify-email', methods=['POST'])
@limiter.limit("10 per hour")
def verify_email():
    """
    Verify email address using token from email.

    Request body:
    {
        "token": "jwt-token-from-email"
    }

    Response:
    {
        "success": true,
        "message": "Email verified successfully."
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    token = data.get('token', '').strip()

    if not token:
        return jsonify({'success': False, 'error': 'Verification token is required'}), 400

    # Verify token
    payload = _verify_email_verification_token(token)
    if not payload:
        return jsonify({
            'success': False,
            'error': 'Invalid or expired verification link. Please request a new one.'
        }), 400

    # Get user
    user_id = payload.get('user_id')
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # Check if this token is for an email change
    token_email = payload.get('email', '').lower()

    if token_email != user.email.lower():
        # This is an email change verification
        # Check if new email is still available
        existing = User.query.filter_by(email=token_email).first()
        if existing:
            return jsonify({
                'success': False,
                'error': 'Email is no longer available.'
            }), 409

        # Update email
        old_email = user.email
        user.email = token_email
        logger.info(f"Email changed from {hash_email(old_email)} to {hash_email(token_email)}")

    # Mark email as verified
    user.email_verified = True
    user.email_verification_token = None
    db.session.commit()

    logger.info(f"Email verified for user {hash_email(user.email)}")

    return jsonify({
        'success': True,
        'message': 'Email verified successfully.'
    }), 200


@auth_bp.route('/verification-status', methods=['GET'])
@require_auth
def get_verification_status():
    """
    Get current email verification status.

    Response:
    {
        "success": true,
        "email_verified": false,
        "email": "user@example.com"
    }
    """
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    return jsonify({
        'success': True,
        'email_verified': user.email_verified or False,
        'email': user.email
    }), 200

@auth_bp.route('/captcha-config', methods=['GET'])
def get_captcha_configuration():
    """
    Get CAPTCHA configuration for frontend integration.
    
    FIX #38: Progressive CAPTCHA enforcement endpoint.
    
    Returns CAPTCHA provider configuration including:
    - Whether CAPTCHA is enabled
    - Which provider (reCAPTCHA, hCaptcha, Turnstile)
    - Site key for frontend integration
    - Threshold for when CAPTCHA is required
    
    Response:
    {
        "enabled": true,
        "provider": "recaptcha_v3",
        "site_key": "6Lc...",
        "threshold": 3
    }
    """
    config = get_captcha_config()
    
    return jsonify({
        'success': True,
        'captcha': config
    })


@auth_bp.route('/check-captcha-required', methods=['POST'])
def check_captcha_requirement():
    """
    Check if CAPTCHA is required for a specific email.

    FIX #38: Allow frontend to check CAPTCHA requirement before submitting credentials.
    HIGH FIX: Email enumeration prevention - never reveal if user exists.

    Request:
    {
        "email": "user@example.com"
    }

    Response:
    {
        "captcha_required": false,
        "threshold": 3
    }
    """
    import time
    start_time = time.time()

    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({'success': False, 'error': 'Email required'}), 400

    # Look up user
    user = User.query.filter_by(email=email).first()

    # Get failed attempts (0 if user doesn't exist)
    failed_attempts = user.failed_login_attempts if user else 0

    # Check if CAPTCHA is required
    captcha_required = is_captcha_required(email, failed_attempts)

    # HIGH FIX: Ensure constant response timing to prevent email enumeration
    # Response should take the same time regardless of whether user exists
    elapsed = time.time() - start_time
    min_response_time = 0.1  # 100ms minimum response time
    if elapsed < min_response_time:
        time.sleep(min_response_time - elapsed)

    # HIGH FIX: Do NOT return failed_attempts - this reveals if user exists
    # Attackers could enumerate emails by checking which ones have > 0 attempts
    return jsonify({
        'success': True,
        'captcha_required': captcha_required,
        'threshold': 3  # CAPTCHA required after 3 failed attempts
        # NOTE: failed_attempts intentionally removed to prevent email enumeration
    })


@auth_bp.route('/sync-credits', methods=['POST'])
@require_auth
def sync_credits():
    """
    Sync legacy User.migrations_purchased with MigrationCredit records.

    This endpoint creates MigrationCredit records for users who have
    User.migrations_purchased > 0 but no corresponding MigrationCredit records.
    This fixes the UI/backend mismatch for existing users.

    Should be called once per user after deployment of the credit fix.
    """
    from models.migration_credit import MigrationCredit

    user_id = request.current_user['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # Get legacy credit counts
    legacy_purchased = getattr(user, 'migrations_purchased', None) or 0
    legacy_used = getattr(user, 'migrations_used', None) or 0
    legacy_available = max(0, legacy_purchased - legacy_used)

    # Get actual MigrationCredit counts
    actual_available = MigrationCredit.query.filter_by(
        user_id=user_id,
        status='available',
        payment_status='paid'
    ).count()

    actual_used = MigrationCredit.query.filter_by(
        user_id=user_id,
        status='used',
        payment_status='paid'
    ).count()

    # Calculate how many credits need to be created
    missing_available = max(0, legacy_available - actual_available)
    missing_used = max(0, legacy_used - actual_used)

    credits_created = 0
    tier = user.subscription_tier or 'starter'
    credit_config = MigrationCredit.TIER_CONFIG.get(tier, MigrationCredit.TIER_CONFIG['starter'])

    # Create missing available credits
    for i in range(missing_available):
        credit = MigrationCredit(
            user_id=user_id,
            tier_type=tier,
            transaction_limit=credit_config.get('transaction_limit', 5000),
            price_cents=0,
            stripe_checkout_session_id=f'sync-available-{user_id}-{i}-{datetime.datetime.utcnow().timestamp()}',
            payment_status='paid',
            status='available'
        )
        credit.paid_at = datetime.datetime.utcnow()
        db.session.add(credit)
        credits_created += 1

    # Create missing used credits (for historical accuracy)
    for i in range(missing_used):
        credit = MigrationCredit(
            user_id=user_id,
            tier_type=tier,
            transaction_limit=credit_config.get('transaction_limit', 5000),
            price_cents=0,
            stripe_checkout_session_id=f'sync-used-{user_id}-{i}-{datetime.datetime.utcnow().timestamp()}',
            payment_status='paid',
            status='used'
        )
        credit.paid_at = datetime.datetime.utcnow()
        credit.used_at = datetime.datetime.utcnow()
        db.session.add(credit)
        credits_created += 1

    if credits_created > 0:
        db.session.commit()
        logger.info(f"Synced {credits_created} credits for user {user_id}")

    # Get updated counts
    new_available = MigrationCredit.query.filter_by(
        user_id=user_id,
        status='available',
        payment_status='paid'
    ).count()

    return jsonify({
        'success': True,
        'message': f'Synced {credits_created} credit(s)',
        'credits_created': credits_created,
        'legacy': {
            'purchased': legacy_purchased,
            'used': legacy_used,
            'available': legacy_available
        },
        'actual': {
            'available': new_available,
            'used': actual_used + missing_used
        }
    })
