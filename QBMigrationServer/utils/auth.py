from functools import wraps
from flask import jsonify
from flask_login import current_user

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        
        if not current_user.is_admin:
            return jsonify({'error': 'Admin privileges required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def verified_required(f):
    """Decorator to require verified email"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401

        # CRIT-01 FIX: User model has 'email_verified' not 'is_verified'
        if not current_user.email_verified:
            return jsonify({'error': 'Email verification required'}), 403

        return f(*args, **kwargs)

    return decorated_function