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
from typing import Optional, Tuple

from models.database import db
from models.user import User
from extensions import limiter

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


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


def require_auth(f):
    """Decorator to require authentication for an endpoint (supports both JWT and session)"""
    @wraps(f)
    def decorated(*args, **kwargs):
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
                return jsonify({'success': False, 'error': 'Authentication failed'}), 401
        
        # Check for session-based auth
        if 'user_id' in session:
            request.current_user = {
                'user_id': session['user_id'],
                'email': session.get('email', '')
            }
            return f(*args, **kwargs)
        
        return jsonify({'success': False, 'error': 'No authorization provided'}), 401
    return decorated


def validate_email(email: str) -> bool:
    """Validate email format"""
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


@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    """Register a new user with comprehensive error handling"""
    import logging
    logger = logging.getLogger(__name__)
    
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
        import re
        def sanitize(value, max_length=255):
            if not value:
                return value
            value = re.sub(r'[<>"\'/\\;]', '', str(value).strip())
            return value[:max_length]
        
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
        
        # Validate password strength BEFORE creating user
        valid, msg = validate_password(password)
        if not valid:
            return jsonify({'success': False, 'error': msg}), 400
        
        # Check if user exists
        existing = User.query.filter_by(email=email).first()
        if existing:
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
            logger.warning(f"Password validation failed for {email}: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 400
        
        # Save to database
        db.session.add(user)
        db.session.commit()
        
        # Create session
        session['user_id'] = user.id
        session['email'] = user.email
        
        # Generate token
        token = create_token(user.id, user.email)
        
        logger.info(f"New user registered: {email}")
        
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
@limiter.limit("10 per minute")
def login():
    """Login and get JWT token"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password required'}), 400
    
    # Find user
    user = User.query.filter_by(email=email).first()
    
    # Check if user exists (constant-time comparison to prevent enumeration)
    if not user:
        # Still check a fake password to prevent timing attacks
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        try:
            ph.verify("$argon2id$v=19$m=65536,t=3,p=4$dummy$dummyhash", password)
        except:
            pass
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
    
    # Check if account is locked
    if user.is_locked():
        return jsonify({
            'success': False, 
            'error': 'Account is locked due to too many failed attempts. Please try again later.'
        }), 401
    
    # Verify password
    if not user.check_password(password):
        # Track failed attempt
        user.record_failed_login()
        db.session.commit()
        
        # Check if now locked
        if user.failed_login_attempts >= 5:
            return jsonify({
                'success': False,
                'error': 'Account is locked due to too many failed attempts. Please try again later.'
            }), 401
        
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
    
    # Successful login
    user.record_successful_login()
    db.session.commit()
    
    # Create session
    session['user_id'] = user.id
    session['email'] = user.email
    
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
    """Get current user info"""
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    return jsonify({
        'success': True,
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'company_name': user.company_name,
        'created_at': user.created_at.isoformat() if user.created_at else None
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
    """Logout - clears session"""
    # Clear session
    session.pop('user_id', None)
    session.pop('email', None)
    session.clear()
    
    return jsonify({'success': True})