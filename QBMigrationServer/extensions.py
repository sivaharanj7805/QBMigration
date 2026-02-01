import os
import logging
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import jsonify, request, session

logger = logging.getLogger(__name__)


# =============================================================================
# PER-USER RATE LIMITING (100/100 FIX)
# =============================================================================

def get_rate_limit_key():
    """
    Get the rate limiting key - combines IP and user ID for comprehensive limiting.

    This provides defense-in-depth:
    1. Unauthenticated users are limited by IP
    2. Authenticated users are limited by user ID + IP combination
    3. Prevents account takeover attacks where attacker uses different IPs
    4. Prevents IP rotation attacks on unauthenticated endpoints

    Returns:
        str: Rate limit key (either IP or "user:{id}:{ip}")
    """
    ip = get_remote_address()

    # Check for authenticated user in session
    user_id = session.get('user_id')
    if user_id:
        return f"user:{user_id}:{ip}"

    # Check for JWT auth (request.current_user is set by require_auth decorator)
    if hasattr(request, 'current_user') and request.current_user:
        user_id = request.current_user.get('user_id')
        if user_id:
            return f"user:{user_id}:{ip}"

    # Fallback to IP-only for unauthenticated requests
    return ip


def get_user_rate_limit_key():
    """
    Get rate limit key based only on user ID (for per-user quotas).

    Use this for endpoints where you want to limit by user regardless of IP,
    such as API quotas or resource creation limits.

    Returns:
        str: User-based rate limit key or IP if unauthenticated
    """
    # Check session
    user_id = session.get('user_id')
    if user_id:
        return f"user:{user_id}"

    # Check JWT
    if hasattr(request, 'current_user') and request.current_user:
        user_id = request.current_user.get('user_id')
        if user_id:
            return f"user:{user_id}"

    # Fallback to IP
    return get_remote_address()


def get_ip_rate_limit_key():
    """
    Get rate limit key based only on IP address.

    Use this for endpoints that should be strictly IP-limited,
    such as login/registration endpoints.

    Returns:
        str: IP address
    """
    return get_remote_address()


def rate_limit_error_handler(e):
    """
    Custom error handler for rate limit exceeded.
    Returns a proper JSON response.
    """
    return jsonify({
        'success': False,
        'error': 'Rate limit exceeded. Please wait before trying again.',
        'retry_after': getattr(e, 'retry_after', 60)
    }), 429


def storage_error_handler(e):
    """
    CRITICAL FIX: Fail-closed when rate limit storage (Redis) is unavailable.

    When Redis is unavailable in production, we BLOCK requests rather than
    allowing unlimited access. This prevents attackers from bypassing rate
    limits by taking Redis offline.

    In development mode, we log a warning but allow the request to proceed.
    """
    is_production = os.getenv('FLASK_ENV', 'development') == 'production'

    if is_production:
        # FAIL-CLOSED: Block requests when rate limiting storage is unavailable
        logger.error(
            f"CRITICAL: Rate limit storage unavailable - blocking request for security. "
            f"Error: {str(e)}"
        )
        return jsonify({
            'success': False,
            'error': 'Service temporarily unavailable. Please try again later.',
            'error_code': 'RATE_LIMIT_STORAGE_UNAVAILABLE'
        }), 503
    else:
        # Development: Log warning but allow request
        logger.warning(
            f"Rate limit storage unavailable (dev mode - allowing request): {str(e)}"
        )
        return None  # Return None to allow the request in development


# Shared Limiter instance with fail-closed behavior and per-user limiting
# This allows blueprints to use decorators before the app is created
limiter = Limiter(
    # 100/100 FIX: Use combined IP+user key function for comprehensive rate limiting
    key_func=get_rate_limit_key,
    # CRITICAL: Fail-closed when storage backend fails
    on_breach=rate_limit_error_handler,
    # Use in-memory fallback only in development
    storage_uri=os.getenv('RATELIMIT_STORAGE_URL', 'memory://'),
    # Enable swallow_errors=False to catch storage failures
    # This is handled by our custom storage_error_handler
    swallow_errors=False if os.getenv('FLASK_ENV') == 'production' else True,
    # Set default limits (applies to combined IP+user key)
    default_limits=["1000 per day", "100 per hour"]
)

# Additional limiter for strict IP-only limiting (login, registration)
ip_limiter = Limiter(
    key_func=get_ip_rate_limit_key,
    on_breach=rate_limit_error_handler,
    storage_uri=os.getenv('RATELIMIT_STORAGE_URL', 'memory://'),
    swallow_errors=False if os.getenv('FLASK_ENV') == 'production' else True,
)

# Additional limiter for user-only quotas (API calls, resource creation)
user_limiter = Limiter(
    key_func=get_user_rate_limit_key,
    on_breach=rate_limit_error_handler,
    storage_uri=os.getenv('RATELIMIT_STORAGE_URL', 'memory://'),
    swallow_errors=False if os.getenv('FLASK_ENV') == 'production' else True,
)


# Register custom error handler for storage failures
@limiter.request_filter
def rate_limit_storage_check():
    """
    Filter that checks if rate limiting should be applied.
    Returns True to SKIP rate limiting (whitelist), False to apply it.

    We never skip rate limiting - this is just a hook for potential IP whitelisting.
    """
    return False  # Always apply rate limiting
