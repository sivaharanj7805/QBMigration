"""
ForensicBridge Authentication API
JWT-based authentication for dashboard users
"""

from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import jwt
import datetime
import secrets
import re
from typing import Optional, Tuple

from models import db, User
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
    """Decorator to require authentication for an endpoint"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'No authorization header'}), 401
        
        try:
            # Expect "Bearer <token>"
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != 'bearer':
                return jsonify({'error': 'Invalid authorization format'}), 401
            
            token = parts[1]
            payload = decode_token(token)
            
            if not payload:
                return jsonify({'error': 'Invalid or expired token'}), 401
            
            # Add user info to request
            request.current_user = payload
            
        except Exception as e:
            return jsonify({'error': 'Authentication failed'}), 401
        
        return f(*args, **kwargs)
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
    """Register a new user"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    name = data.get('name', '').strip()
    company = data.get('company', '').strip()
    
    # Validation
    if not email or not password or not name:
        return jsonify({'error': 'Email, password, and name are required'}), 400
    
    if not validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400
    
    valid, msg = validate_password(password)
    if not valid:
        return jsonify({'error': msg}), 400
    
    # Check if user exists
    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({'error': 'Email already registered'}), 409
    
    # Create user
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        name=name,
        company=company
    )
    
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create user'}), 500
    
    # Generate token
    token = create_token(user.id, user.email)
    
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'company': user.company
        }
    }), 201


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """Login and get JWT token"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    # Find user
    user = User.query.filter_by(email=email).first()
    
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid email or password'}), 401
    
    # Generate token
    token = create_token(user.id, user.email)
    
    # Update last login
    user.last_login = datetime.datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'company': user.company
        }
    })


@auth_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """Get current user info"""
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'company': user.company,
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
    """Logout (client-side token handling)"""
    # JWT tokens are stateless, so logout is handled client-side
    # This endpoint exists for API consistency
    return jsonify({'success': True})