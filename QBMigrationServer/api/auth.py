from flask import Blueprint, request, jsonify, current_app, g
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models.database import db
from models.user import User
from datetime import datetime
import logging
import re
import hashlib
import requests

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


def validate_email(email):
    """Validate email format"""
    if not email:
        return False, "Email is required"
    
    if len(email) > 255:
        return False, "Email too long (max 255 characters)"
    
    # RFC 5322 simplified regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    
    return True, None


def validate_password(password):
    """Validate password strength"""
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    
    if len(password) > 128:
        return False, "Password too long (max 128 characters)"
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    
    if not (has_upper and has_lower and has_digit):
        return False, "Password must contain uppercase, lowercase, and number"
    
    # Check for common passwords
    common_passwords = ['password', '12345678', 'qwerty', 'abc123', 'password123']
    if password.lower() in common_passwords:
        return False, "Password is too common"
    
    return True, None


def verify_recaptcha(token):
    """
    Verify reCAPTCHA token
    
    Args:
        token: reCAPTCHA response token
        
    Returns:
        bool: True if valid
    """
    if not current_app.config.get('RECAPTCHA_SECRET_KEY'):
        logger.warning("reCAPTCHA not configured, skipping verification")
        return True
    
    try:
        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={
                'secret': current_app.config.get('RECAPTCHA_SECRET_KEY'),
                'response': token,
                'remoteip': request.remote_addr
            },
            timeout=5
        )
        
        result = response.json()
        return result.get('success', False)
        
    except Exception as e:
        logger.error(f"reCAPTCHA verification failed: {str(e)}")
        return False


def generate_device_fingerprint():
    """Generate device fingerprint for tracking"""
    components = [
        request.headers.get('User-Agent', ''),
        request.headers.get('Accept-Language', ''),
        request.headers.get('Accept-Encoding', ''),
        request.remote_addr
    ]
    
    fingerprint_string = '|'.join(components)
    return hashlib.sha256(fingerprint_string.encode()).hexdigest()


def sanitize_string(value, max_length=255):
    """Sanitize string input"""
    if not value:
        return ""
    
    value = value.replace('\x00', '')
    value = value.strip()
    
    if len(value) > max_length:
        value = value[:max_length]
    
    return value


def should_require_captcha(user):
    """
    Determine if CAPTCHA should be required
    
    Args:
        user: User object (or None)
        
    Returns:
        bool: True if CAPTCHA required
    """
    if not user:
        return False
    
    threshold = current_app.config.get('CAPTCHA_THRESHOLD', 3)
    return user.failed_login_attempts >= threshold


@auth_bp.route('/api/auth/register', methods=['POST'])
@limiter.limit("5 per hour")
def register():
    """
    Register new user
    
    Rate Limited: 5 requests per hour
    
    Request Body:
        email (str): User email
        password (str): User password (min 8 chars, uppercase, lowercase, digit)
        first_name (str, optional): First name
        last_name (str, optional): Last name
        company_name (str, optional): Company name
        captcha_token (str, optional): reCAPTCHA token (if enabled)
    
    Returns:
        201: User created successfully
        400: Invalid input
        409: Email already registered
        429: Too many requests
        500: Server error
    """
    try:
        # Validate content type
        if not request.is_json:
            logger.warning(f"Non-JSON registration attempt from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Content-Type must be application/json'
            }), 400
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is empty'
            }), 400
        
        # Sanitize inputs
        email = sanitize_string(data.get('email', ''), max_length=255).lower()
        password = data.get('password', '')
        first_name = sanitize_string(data.get('first_name', ''), max_length=100)
        last_name = sanitize_string(data.get('last_name', ''), max_length=100)
        company_name = sanitize_string(data.get('company_name', ''), max_length=255)
        
        # Validate email
        is_valid, error = validate_email(email)
        if not is_valid:
            logger.warning(f"Invalid email in registration: {email} from {request.remote_addr}")
            return jsonify({'success': False, 'error': error}), 400
        
        # Validate password
        is_valid, error = validate_password(password)
        if not is_valid:
            logger.warning(f"Weak password in registration for {email}")
            return jsonify({'success': False, 'error': error}), 400
        
        # Check if user exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            logger.warning(f"Registration attempt for existing email: {email} from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Email already registered'
            }), 409
        
        # Create user
        try:
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                company_name=company_name
            )
            user.set_password(password)
            
            # Generate verification token
            verification_token = user.generate_verification_token()
            
            db.session.add(user)
            db.session.commit()
            
            logger.info(f"New user registered: {email} from {request.remote_addr}")
            
            # TODO: Send verification email
            # send_verification_email(user.email, verification_token)
            
            return jsonify({
                'success': True,
                'message': 'Account created successfully. Please check your email to verify your account.',
                'user': user.to_dict(),
                'verification_required': True
            }), 201
            
        except ValueError as e:
            logger.error(f"Password validation error for {email}: {str(e)}")
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
        
    except Exception as e:
        logger.exception(f"Registration error: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Registration failed. Please try again.'
        }), 500


@auth_bp.route('/api/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """
    Login user with CAPTCHA and device fingerprinting
    
    Rate Limited: 10 requests per minute
    Account Lockout: 5 failed attempts = 15 minute lockout
    CAPTCHA: Required after 3 failed attempts
    
    Request Body:
        email (str): User email
        password (str): User password
        totp_token (str, optional): 2FA token (if enabled)
        captcha_token (str, optional): reCAPTCHA token (if required)
    
    Returns:
        200: Login successful
        401: Invalid credentials, account locked, or 2FA required
        400: Invalid input or CAPTCHA required
        429: Too many requests
        500: Server error
    """
    try:
        # Validate content type
        if not request.is_json:
            logger.warning(f"Non-JSON login attempt from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Content-Type must be application/json'
            }), 400
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is empty'
            }), 400
        
        email = sanitize_string(data.get('email', ''), max_length=255).lower()
        password = data.get('password', '')
        totp_token = data.get('totp_token', '')
        captcha_token = data.get('captcha_token', '')
        
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email and password required'
            }), 400
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        # Check if CAPTCHA required
        if should_require_captcha(user):
            if not captcha_token:
                return jsonify({
                    'success': False,
                    'error': 'CAPTCHA verification required',
                    'captcha_required': True
                }), 400
            
            if not verify_recaptcha(captcha_token):
                if user:
                    user.failed_captcha_attempts += 1
                    db.session.commit()
                
                logger.warning(f"Failed CAPTCHA for {email} from {request.remote_addr}")
                return jsonify({
                    'success': False,
                    'error': 'CAPTCHA verification failed',
                    'captcha_required': True
                }), 400
        
        # Check if account is locked
        if user and user.is_locked():
            minutes_remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60)
            logger.warning(f"Login attempt for locked account: {email} from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': f'Account locked due to too many failed attempts. Try again in {minutes_remaining} minutes.',
                'locked_until': user.locked_until.isoformat() if user.locked_until else None
            }), 401
        
        # Verify password
        if not user or not user.check_password(password):
            if user:
                user.increment_failed_login()
                remaining_attempts = 5 - user.failed_login_attempts
                
                if remaining_attempts > 0:
                    logger.warning(f"Failed login attempt for {email}. {remaining_attempts} attempts remaining.")
                else:
                    logger.warning(f"Account locked after 5 failed attempts: {email}")
                
                # Check if CAPTCHA should now be required
                if should_require_captcha(user):
                    return jsonify({
                        'success': False,
                        'error': 'Invalid credentials. CAPTCHA now required.',
                        'captcha_required': True,
                        'attempts_remaining': remaining_attempts
                    }), 401
            else:
                logger.warning(f"Login attempt for non-existent user: {email} from {request.remote_addr}")
            
            return jsonify({
                'success': False,
                'error': 'Invalid email or password'
            }), 401
        
        # Check if account is active
        if not user.is_active:
            logger.warning(f"Login attempt for inactive account: {email}")
            return jsonify({
                'success': False,
                'error': 'Account is disabled. Please contact support.'
            }), 401
        
        # Check 2FA if enabled
        if user.mfa_enabled:
            if not totp_token:
                return jsonify({
                    'success': False,
                    'error': '2FA token required',
                    'mfa_required': True
                }), 401
            
            if not user.verify_2fa_token(totp_token):
                user.increment_failed_login()
                logger.warning(f"Invalid 2FA token for {email}")
                return jsonify({
                    'success': False,
                    'error': 'Invalid 2FA token',
                    'mfa_required': True
                }), 401
        
        # Generate device fingerprint
        device_fingerprint = generate_device_fingerprint()
        
        # Check for new device
        if user.last_device_fingerprint and user.last_device_fingerprint != device_fingerprint:
            logger.info(f"New device detected for {email}. Old: {user.last_device_fingerprint[:8]}, New: {device_fingerprint[:8]}")
            # TODO: Send security alert email
            # send_new_device_alert(user.email, request.remote_addr)
        
        # Successful login - reset failed attempts
        user.reset_failed_login()
        user.update_login_info(request.remote_addr, device_fingerprint)
        
        # Log in user
        login_user(user, remember=True)
        
        logger.info(f"User logged in: {email} from {request.remote_addr}")
        
        return jsonify({
            'success': True,
            'message': 'Logged in successfully',
            'user': user.to_dict(),
            'new_device': user.last_device_fingerprint != device_fingerprint if user.last_device_fingerprint else False
        }), 200
        
    except Exception as e:
        logger.exception(f"Login error: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Login failed. Please try again.'
        }), 500


@auth_bp.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    """Logout user"""
    try:
        email = current_user.email
        logout_user()
        
        logger.info(f"User logged out: {email} from {request.remote_addr}")
        
        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        }), 200
        
    except Exception as e:
        logger.exception(f"Logout error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Logout failed'
        }), 500


@auth_bp.route('/api/auth/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged in user"""
    try:
        return jsonify({
            'success': True,
            'user': current_user.to_dict()
        }), 200
        
    except Exception as e:
        logger.exception(f"Get current user error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get user'
        }), 500


@auth_bp.route('/api/auth/verify/<token>', methods=['GET'])
def verify_email(token):
    """Verify email address"""
    try:
        user = User.query.filter_by(verification_token=token).first()
        
        if not user:
            logger.warning(f"Invalid verification token from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Invalid or expired verification token'
            }), 400
        
        if user.verify_email(token):
            logger.info(f"Email verified for user: {user.email}")
            return jsonify({
                'success': True,
                'message': 'Email verified successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Verification token expired'
            }), 400
        
    except Exception as e:
        logger.exception(f"Email verification error: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Verification failed'
        }), 500


@auth_bp.route('/api/auth/2fa/enable', methods=['POST'])
@login_required
def enable_2fa():
    """Enable two-factor authentication"""
    try:
        if current_user.mfa_enabled:
            return jsonify({
                'success': False,
                'error': '2FA already enabled'
            }), 400
        
        secret, qr_url, backup_codes = current_user.enable_2fa()
        
        logger.info(f"2FA enabled for user: {current_user.email}")
        
        return jsonify({
            'success': True,
            'message': '2FA enabled successfully',
            'secret': secret,
            'qr_code_url': qr_url,
            'backup_codes': backup_codes
        }), 200
        
    except Exception as e:
        logger.exception(f"Enable 2FA error: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to enable 2FA'
        }), 500


@auth_bp.route('/api/auth/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    """Disable two-factor authentication"""
    try:
        data = request.get_json() or {}
        totp_token = data.get('totp_token', '')
        
        if not totp_token:
            return jsonify({
                'success': False,
                'error': '2FA token required to disable'
            }), 400
        
        if not current_user.verify_2fa_token(totp_token):
            return jsonify({
                'success': False,
                'error': 'Invalid 2FA token'
            }), 401
        
        current_user.disable_2fa()
        
        logger.info(f"2FA disabled for user: {current_user.email}")
        
        return jsonify({
            'success': True,
            'message': '2FA disabled successfully'
        }), 200
        
    except Exception as e:
        logger.exception(f"Disable 2FA error: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to disable 2FA'
        }), 500


@auth_bp.route('/api/auth/captcha-config', methods=['GET'])
def get_captcha_config():
    """Get reCAPTCHA site key"""
    return jsonify({
        'enabled': bool(current_app.config.get('RECAPTCHA_SITE_KEY')),
        'site_key': current_app.config.get('RECAPTCHA_SITE_KEY')
    }), 200