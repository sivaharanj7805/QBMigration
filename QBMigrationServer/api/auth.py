"""
Authentication API Endpoints
- User registration with validation
- Login with rate limiting
- 2FA support
- Account lockout protection
- XSS prevention
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models.database import db
from models.user import User
from argon2 import PasswordHasher
from markupsafe import escape
import logging
import re

# Initialize blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Initialize password hasher
ph = PasswordHasher()


def sanitize_input(text, max_length=100):
    """
    Sanitize user input to prevent XSS and injection attacks
    
    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ''
    
    # Convert to string
    text = str(text)
    
    # Remove all HTML tags
    text = re.sub(r'<[^>]*>', '', text)
    
    # Remove dangerous characters
    text = re.sub(r'[<>"\'\\/]', '', text)
    
    # Remove script-related keywords
    dangerous_patterns = [
        r'javascript:',
        r'on\w+\s*=',  # onclick, onerror, etc
        r'<script',
        r'</script',
        r'eval\s*\(',
        r'expression\s*\(',
    ]
    for pattern in dangerous_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Escape any remaining special characters
    text = escape(text)
    
    # Limit length
    return text[:max_length]


@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per hour")
def register():
    """
    Register new user
    
    Request JSON:
        {
            "email": "user@example.com",
            "password": "SecurePass123",
            "first_name": "John",
            "last_name": "Doe",
            "company_name": "Company Inc",
            "phone": "+1234567890"
        }
    
    Returns:
        201: User created successfully
        400: Invalid input
        409: Email already registered
    """
    try:
        data = request.get_json()
        
        # Get inputs
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        company_name = data.get('company_name', '').strip()
        phone = data.get('phone', '').strip()
        
        # CRITICAL: Sanitize all text inputs to prevent XSS
        first_name_original = first_name
        last_name_original = last_name
        company_name_original = company_name
        
        first_name = sanitize_input(first_name, 50)
        last_name = sanitize_input(last_name, 50)
        company_name = sanitize_input(company_name, 100)
        phone = sanitize_input(phone, 20)
        
        # CRITICAL: Reject if sanitization removed everything (XSS attempt)
        if first_name_original and not first_name:
            logger.warning(f"XSS attempt in first_name from {request.remote_addr}: {first_name_original}")
            return jsonify({
                'success': False,
                'error': 'Invalid characters in first name. Please use only letters and spaces.'
            }), 400
        
        if last_name_original and not last_name:
            logger.warning(f"XSS attempt in last_name from {request.remote_addr}: {last_name_original}")
            return jsonify({
                'success': False,
                'error': 'Invalid characters in last name. Please use only letters and spaces.'
            }), 400
        
        if company_name_original and not company_name:
            logger.warning(f"XSS attempt in company_name from {request.remote_addr}: {company_name_original}")
            return jsonify({
                'success': False,
                'error': 'Invalid characters in company name.'
            }), 400
        
        # Validate email
        if not email or '@' not in email:
            return jsonify({
                'success': False,
                'error': 'Valid email is required'
            }), 400
        
        # Additional email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            logger.warning(f"Invalid email format in registration: {email}")
            return jsonify({
                'success': False,
                'error': 'Invalid email format'
            }), 400
        
        # Validate password
        if not password:
            return jsonify({
                'success': False,
                'error': 'Password is required'
            }), 400
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            logger.warning(f"Registration attempt for existing email: {email} from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Email already registered'
            }), 409
        
        # Create new user
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            company_name=company_name,
            phone=phone
        )
        
        # Set password (validates strength automatically)
        try:
            user.set_password(password)
        except ValueError as e:
            logger.warning(f"Weak password in registration for {email}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
        
        # Save user
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"New user registered: {email} from {request.remote_addr}")
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Registration error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred during registration'
        }), 500


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """
    User login
    
    Request JSON:
        {
            "email": "user@example.com",
            "password": "password123",
            "totp_token": "123456"  # Optional, if 2FA enabled
        }
    
    Returns:
        200: Login successful
        401: Invalid credentials
        400: Account locked or CAPTCHA required
    """
    try:
        data = request.get_json()
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        totp_token = data.get('totp_token', '')
        
        # Validate inputs
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email and password are required'
            }), 400
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        # SECURITY: Always check password even if user doesn't exist
        # (prevents user enumeration via timing attacks)
        if not user:
            # Dummy password check to maintain constant time
            ph.hash('dummy_password_to_prevent_timing_attack')
            logger.warning(f"Login attempt for non-existent user: {email} from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Invalid email or password'
            }), 401
        
        # Check if account is locked
        if user.is_locked():
            logger.warning(f"Login attempt for locked account: {email} from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Account is temporarily locked due to multiple failed login attempts. Please try again in 15 minutes.'
            }), 400
        
        # Check if account is active
        if not user.is_active:
            return jsonify({
                'success': False,
                'error': 'Account is disabled'
            }), 401
        
        # Verify password
        if not user.check_password(password):
            # CRITICAL FIX: Track failed attempt
            user.record_failed_login()
            db.session.commit()
            
            attempts_remaining = max(0, 5 - user.failed_login_attempts)
            logger.warning(f"Failed login attempt for {email}. {attempts_remaining} attempts remaining.")
            
            return jsonify({
                'success': False,
                'error': f'Invalid email or password. {attempts_remaining} attempts remaining.'
            }), 401
        
        # Check 2FA if enabled
        if user.mfa_enabled:
            if not totp_token:
                return jsonify({
                    'success': False,
                    'error': '2FA token required',
                    'require_2fa': True
                }), 400
            
            if not user.verify_2fa_token(totp_token):
                user.record_failed_login()
                db.session.commit()
                
                return jsonify({
                    'success': False,
                    'error': 'Invalid 2FA token'
                }), 401
        
        # Login successful
        user.record_successful_login()
        db.session.commit()
        
        login_user(user)
        
        logger.info(f"User logged in: {email} from {request.remote_addr}")
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'company_name': user.company_name,
                'mfa_enabled': user.mfa_enabled
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred during login'
        }), 500


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    User logout
    
    Returns:
        200: Logout successful
    """
    try:
        email = current_user.email
        logout_user()
        
        logger.info(f"User logged out: {email}")
        
        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred during logout'
        }), 500


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """
    Get current user information
    
    Returns:
        200: User information
    """
    try:
        return jsonify({
            'success': True,
            'user': {
                'id': current_user.id,
                'email': current_user.email,
                'first_name': current_user.first_name,
                'last_name': current_user.last_name,
                'company_name': current_user.company_name,
                'mfa_enabled': current_user.mfa_enabled,
                'email_verified': current_user.email_verified
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Get current user error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred'
        }), 500


@auth_bp.route('/enable-2fa', methods=['POST'])
@login_required
def enable_2fa():
    """
    Enable 2FA for current user
    
    Returns:
        200: 2FA enabled, returns secret and QR code URL
    """
    try:
        secret, qr_url, backup_codes = current_user.enable_2fa()
        db.session.commit()
        
        logger.info(f"2FA enabled for user: {current_user.email}")
        
        return jsonify({
            'success': True,
            'secret': secret,
            'qr_code_url': qr_url,
            'backup_codes': backup_codes
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Enable 2FA error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while enabling 2FA'
        }), 500


@auth_bp.route('/disable-2fa', methods=['POST'])
@login_required
def disable_2fa():
    """
    Disable 2FA for current user
    
    Returns:
        200: 2FA disabled
    """
    try:
        current_user.disable_2fa()
        db.session.commit()
        
        logger.info(f"2FA disabled for user: {current_user.email}")
        
        return jsonify({
            'success': True,
            'message': '2FA disabled successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Disable 2FA error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while disabling 2FA'
        }), 500