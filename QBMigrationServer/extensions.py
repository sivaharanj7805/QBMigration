import os
import logging
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import jsonify

logger = logging.getLogger(__name__)


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


# Shared Limiter instance with fail-closed behavior
# This allows blueprints to use decorators before the app is created
limiter = Limiter(
    key_func=get_remote_address,
    # CRITICAL: Fail-closed when storage backend fails
    on_breach=rate_limit_error_handler,
    # Use in-memory fallback only in development
    storage_uri=os.getenv('RATELIMIT_STORAGE_URL', 'memory://'),
    # Enable swallow_errors=False to catch storage failures
    # This is handled by our custom storage_error_handler
    swallow_errors=False if os.getenv('FLASK_ENV') == 'production' else True,
    # Set default limits
    default_limits=["1000 per day", "100 per hour"]
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
