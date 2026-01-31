"""
CAPTCHA Verification System
===========================

Provides CAPTCHA verification for progressive rate limiting after failed login attempts.

ISSUE #38: Implement progressive rate limiting with CAPTCHA protection.

Supports multiple CAPTCHA providers:
- Google reCAPTCHA v2 and v3
- hCaptcha
- Cloudflare Turnstile

Author: ForensicBridge Security Team
Version: 1.0.0
"""

import os
import logging
import requests
from typing import Tuple, Optional, Dict, Any
from flask import request

logger = logging.getLogger(__name__)

# CAPTCHA provider configurations
CAPTCHA_PROVIDERS = {
    'recaptcha_v2': {
        'verify_url': 'https://www.google.com/recaptcha/api/siteverify',
        'secret_env': 'RECAPTCHA_V2_SECRET_KEY',
        'score_threshold': None,  # v2 doesn't use scores
    },
    'recaptcha_v3': {
        'verify_url': 'https://www.google.com/recaptcha/api/siteverify',
        'secret_env': 'RECAPTCHA_V3_SECRET_KEY',
        'score_threshold': 0.5,  # Minimum acceptable score (0.0 - 1.0)
    },
    'hcaptcha': {
        'verify_url': 'https://hcaptcha.com/siteverify',
        'secret_env': 'HCAPTCHA_SECRET_KEY',
        'score_threshold': None,
    },
    'turnstile': {
        'verify_url': 'https://challenges.cloudflare.com/turnstile/v0/siteverify',
        'secret_env': 'TURNSTILE_SECRET_KEY',
        'score_threshold': None,
    },
}


def get_captcha_provider() -> str:
    """
    Determine which CAPTCHA provider is configured.

    Returns:
        Provider name ('recaptcha_v2', 'recaptcha_v3', 'hcaptcha', 'turnstile', or 'none')
    """
    # Check environment variables for configured provider
    for provider_name, config in CAPTCHA_PROVIDERS.items():
        if os.getenv(config['secret_env']):
            logger.info(f"CAPTCHA provider configured: {provider_name}")
            return provider_name

    logger.warning("No CAPTCHA provider configured - CAPTCHA verification disabled")
    return 'none'


def verify_captcha_token(token: str, remote_ip: Optional[str] = None,
                          provider: Optional[str] = None) -> Tuple[bool, str]:
    """
    Verify CAPTCHA token with the configured provider.

    Args:
        token: CAPTCHA token from client
        remote_ip: Client IP address (optional but recommended)
        provider: Override provider (defaults to auto-detect)

    Returns:
        Tuple of (is_valid: bool, error_message: str)

    Examples:
        >>> verify_captcha_token("token123", "192.168.1.1")
        (True, "")

        >>> verify_captcha_token("invalid")
        (False, "CAPTCHA verification failed")
    """
    if not token:
        return False, "CAPTCHA token required"

    # Determine provider
    if not provider:
        provider = get_captcha_provider()

    # CRITICAL FIX: Fail-closed when CAPTCHA not configured in production
    # In production, if CAPTCHA is required but not configured, we MUST fail
    # This prevents attackers from bypassing CAPTCHA by removing the config
    if provider == 'none':
        is_production = os.getenv('FLASK_ENV', 'development') == 'production'

        if is_production:
            # FAIL-CLOSED: In production, missing CAPTCHA config is a security failure
            logger.error(
                "SECURITY CRITICAL: CAPTCHA verification required but no provider configured. "
                "Blocking request for security. Configure a CAPTCHA provider immediately."
            )
            return False, "Security verification unavailable. Please contact support."
        else:
            # Development mode: Allow bypass with explicit warning
            logger.warning(
                "CAPTCHA verification skipped - no provider configured (development mode only). "
                "This would FAIL in production!"
            )
            return True, ""

    # Get provider configuration
    config = CAPTCHA_PROVIDERS.get(provider)
    if not config:
        logger.error(f"Unknown CAPTCHA provider: {provider}")
        return False, "Invalid CAPTCHA provider"

    secret_key = os.getenv(config['secret_env'])
    if not secret_key:
        logger.error(f"CAPTCHA secret key not configured: {config['secret_env']}")
        return False, "CAPTCHA configuration error"

    # Prepare verification request
    verify_data = {
        'secret': secret_key,
        'response': token,
    }

    # Add remote IP if provided (recommended for security)
    if remote_ip:
        if provider == 'turnstile':
            verify_data['remoteip'] = remote_ip
        else:
            verify_data['remoteip'] = remote_ip

    try:
        # Make verification request
        response = requests.post(
            config['verify_url'],
            data=verify_data,
            timeout=5
        )
        response.raise_for_status()
        result = response.json()

        # Check verification result
        if not result.get('success'):
            error_codes = result.get('error-codes', [])
            logger.warning(f"CAPTCHA verification failed: {error_codes}")
            return False, "CAPTCHA verification failed"

        # For reCAPTCHA v3, check score
        if provider == 'recaptcha_v3':
            score = result.get('score', 0.0)
            threshold = config['score_threshold']
            if score < threshold:
                logger.warning(f"CAPTCHA score too low: {score} < {threshold}")
                return False, f"CAPTCHA score too low: {score}"

        # Verification successful
        logger.info(f"CAPTCHA verified successfully: provider={provider}")
        return True, ""

    except requests.exceptions.Timeout:
        logger.error("CAPTCHA verification timeout")
        return False, "CAPTCHA verification timeout"
    except requests.exceptions.RequestException as e:
        logger.error(f"CAPTCHA verification request failed: {e}")
        return False, "CAPTCHA verification failed"
    except Exception as e:
        logger.exception(f"Unexpected error during CAPTCHA verification: {e}")
        return False, "CAPTCHA verification error"


def is_captcha_required(email: str, failed_attempts: int = 0) -> bool:
    """
    Determine if CAPTCHA is required for login based on failed attempts.

    Progressive enforcement:
    - 0-2 failed attempts: No CAPTCHA required
    - 3+ failed attempts: CAPTCHA required
    - Account locked (5+ attempts): CAPTCHA required

    Args:
        email: User email address
        failed_attempts: Number of consecutive failed login attempts

    Returns:
        True if CAPTCHA should be required, False otherwise
    """
    # FIX #38: Require CAPTCHA after 3 failed attempts
    if failed_attempts >= 3:
        logger.info(f"CAPTCHA required for {email}: {failed_attempts} failed attempts")
        return True

    return False


def get_client_ip() -> str:
    """
    Get client IP address from request, accounting for proxies.

    Checks headers in order:
    1. X-Forwarded-For (first IP if multiple)
    2. X-Real-IP
    3. request.remote_addr

    Returns:
        Client IP address
    """
    # Check X-Forwarded-For header (used by proxies/load balancers)
    x_forwarded_for = request.headers.get('X-Forwarded-For')
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
        # First IP is the original client
        return x_forwarded_for.split(',')[0].strip()

    # Check X-Real-IP header (used by some proxies)
    x_real_ip = request.headers.get('X-Real-IP')
    if x_real_ip:
        return x_real_ip.strip()

    # Fallback to direct connection IP
    return request.remote_addr or 'unknown'


def get_captcha_config() -> Dict[str, Any]:
    """
    Get CAPTCHA configuration for frontend integration.

    Returns:
        Dictionary with CAPTCHA configuration:
        - enabled: bool
        - provider: str
        - site_key: str (if configured)
        - threshold: int (failed attempts before CAPTCHA required)
    """
    provider = get_captcha_provider()

    config = {
        'enabled': provider != 'none',
        'provider': provider,
        'threshold': 3,  # CAPTCHA required after 3 failed attempts
    }

    # Add site key if available (public key for frontend)
    site_key_env_map = {
        'recaptcha_v2': 'RECAPTCHA_V2_SITE_KEY',
        'recaptcha_v3': 'RECAPTCHA_V3_SITE_KEY',
        'hcaptcha': 'HCAPTCHA_SITE_KEY',
        'turnstile': 'TURNSTILE_SITE_KEY',
    }

    if provider in site_key_env_map:
        site_key = os.getenv(site_key_env_map[provider])
        if site_key:
            config['site_key'] = site_key

    return config
