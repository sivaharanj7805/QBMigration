import os
from functools import wraps

from flask import jsonify
from flask_login import current_user


def admin_required(f):
    """Decorator to require admin privileges.

    Checks both:
    1. Role-based: user.is_admin() (role hierarchy)
    2. Email-based: ADMIN_EMAILS environment variable (comma-separated)
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401

        # Check role-based admin
        if current_user.is_admin():
            return f(*args, **kwargs)

        # Check email-based admin (ADMIN_EMAILS env var)
        admin_emails = os.environ.get("ADMIN_EMAILS", "")
        if admin_emails:
            email_list = [e.strip().lower() for e in admin_emails.split(",") if e.strip()]
            if current_user.email.lower() in email_list:
                return f(*args, **kwargs)

        return jsonify({"error": "Admin privileges required"}), 403

    return decorated_function


def verified_required(f):
    """Decorator to require verified email"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401

        # CRIT-01 FIX: User model has 'email_verified' not 'is_verified'
        if not current_user.email_verified:
            return jsonify({"error": "Email verification required"}), 403

        return f(*args, **kwargs)

    return decorated_function
