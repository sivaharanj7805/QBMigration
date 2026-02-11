import logging
from functools import wraps

from flask import jsonify
from flask_login import current_user

_logger = logging.getLogger(__name__)


def admin_required(f):
    """Decorator to require admin privileges.

    AUDIT FIX HIGH-4: Uses ONLY role-based access control via user.is_admin().
    The ADMIN_EMAILS environment variable bypass has been removed to prevent
    privilege escalation outside the RBAC system. Admin access must be granted
    by setting the user's role column in the database.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401

        # Check role-based admin only — no email-based bypass
        if current_user.is_admin():
            return f(*args, **kwargs)

        _logger.warning(
            "Admin access denied for user %s (role=%s)",
            current_user.id,
            getattr(current_user, "role", "unknown"),
        )
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
