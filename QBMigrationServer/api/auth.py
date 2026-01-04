from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models.database import db
from models.user import User
from utils.validators import validate_email, validate_password

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    """Register new user"""
    
    data = request.get_json()
    
    # Validate input
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    company_name = data.get('company_name', '').strip()
    
    # Validate email
    if not validate_email(email):
        return jsonify({'success': False, 'error': 'Invalid email address'}), 400
    
    # Validate password
    valid, error = validate_password(password)
    if not valid:
        return jsonify({'success': False, 'error': error}), 400
    
    # Check if user exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({'success': False, 'error': 'Email already registered'}), 409
    
    # Create user
    user = User(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        company_name=company_name
    )
    
    db.session.add(user)
    db.session.commit()
    
    # TODO: Send verification email
    
    current_app.logger.info(f"New user registered: {email}")
    
    return jsonify({
        'success': True,
        'message': 'Account created successfully',
        'user': user.to_dict()
    }), 201


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    remember = data.get('remember', False)
    
    # Find user
    user = User.query.filter_by(email=email).first()
    
    if not user or not user.check_password(password):
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
    
    if not user.is_active:
        return jsonify({'success': False, 'error': 'Account is disabled'}), 403
    
    # Login user
    login_user(user, remember=remember)
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    current_app.logger.info(f"User logged in: {email}")
    
    return jsonify({
        'success': True,
        'message': 'Logged in successfully',
        'user': user.to_dict()
    }), 200


@auth_bp.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    """Logout user"""
    
    email = current_user.email
    logout_user()
    
    current_app.logger.info(f"User logged out: {email}")
    
    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    }), 200


@auth_bp.route('/api/auth/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current user info"""
    
    return jsonify({
        'success': True,
        'user': current_user.to_dict()
    }), 200


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password"""
    
    data = request.get_json()
    
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    # Verify current password
    if not current_user.check_password(current_password):
        return jsonify({'success': False, 'error': 'Current password is incorrect'}), 401
    
    # Validate new password
    valid, error = validate_password(new_password)
    if not valid:
        return jsonify({'success': False, 'error': error}), 400
    
    # Update password
    current_user.set_password(new_password)
    db.session.commit()
    
    current_app.logger.info(f"Password changed: {current_user.email}")
    
    return jsonify({
        'success': True,
        'message': 'Password changed successfully'
    }), 200