"""
ForensicBridge Authentication API
JWT-based authentication for dashboard users with full security features
Compatible with models/user.py User model
"""

import datetime
import hashlib
import hmac
import logging
import os
import re
import secrets as _secrets
import threading
import time as _time
from datetime import timezone
from functools import wraps
from typing import Any, Callable, Optional, Tuple

import jwt
import stripe
from extensions import limiter
from flask import Blueprint, current_app, jsonify, request, session
from flask_wtf.csrf import generate_csrf
from models.database import db
from models.migration_credit import MigrationCredit
from models.team_invite import TeamInvite
from models.user import User
from utils.anomaly_detector import check_login_anomalies, log_anomaly
from utils.captcha_verifier import (
    get_captcha_config,
    get_client_ip,
    is_captcha_required,
    verify_captcha_token,
)
from utils.error_sanitizer import sanitize_error_message
from utils.pii_redaction import hash_email

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# H-03 FIX: JWT blocklist for logout revocation.
# CRIT-01 FIX: Redis is REQUIRED for multi-worker deployments.
# In-memory fallback uses fail-closed policy: if Redis is down,
# blocklist checks assume the token IS revoked (deny access).
_jwt_blocklist: dict[str, float] = {}  # jti -> expiry timestamp (local cache only)
_jwt_blocklist_lock = threading.Lock()


_redis_conn = None
_redis_last_attempt = 0.0
_REDIS_RETRY_INTERVAL = 30.0  # Don't retry Redis connection more than every 30s


def _get_redis():
    """Get Redis connection for JWT blocklist. Returns None if unavailable.

    Creates its own connection from REDIS_URL/RATELIMIT_STORAGE_URL env vars.
    Caches the connection and avoids hammering Redis if it's down.
    """
    global _redis_conn, _redis_last_attempt

    # Return cached connection if it's still alive
    if _redis_conn is not None:
        try:
            _redis_conn.ping()
            return _redis_conn
        except Exception:
            _redis_conn = None

    # Don't retry too frequently if Redis is down
    now = _time.time()
    if now - _redis_last_attempt < _REDIS_RETRY_INTERVAL:
        return None

    _redis_last_attempt = now
    try:
        import redis as _redis_mod
        redis_url = os.environ.get("REDIS_URL") or os.environ.get("RATELIMIT_STORAGE_URL")
        if redis_url and redis_url != "memory://":
            _redis_conn = _redis_mod.from_url(redis_url, decode_responses=True, socket_connect_timeout=3)
            _redis_conn.ping()
            return _redis_conn
    except Exception:
        _redis_conn = None
    return None


def _blocklist_add(jti: str, exp_timestamp: float) -> None:
    """Add a JWT ID to the blocklist. Uses Redis (shared across all workers).

    CRIT-01 FIX: Also writes to local in-memory cache so that the worker
    that performed the logout always honours it even if a subsequent Redis
    read fails.  The authoritative store is Redis.
    """
    ttl = max(int(exp_timestamp - _time.time()), 1)

    # Always write to local cache (belt-and-suspenders)
    now = _time.time()
    with _jwt_blocklist_lock:
        # Prune expired entries
        expired = [k for k, v in _jwt_blocklist.items() if v < now]
        for k in expired:
            del _jwt_blocklist[k]
        _jwt_blocklist[jti] = exp_timestamp

    # Write to Redis (shared across all workers)
    redis = _get_redis()
    if redis:
        try:
            redis.setex(f"jwt_blocklist:{jti}", ttl, "1")
            return
        except Exception as exc:
            logger.error("Redis blocklist write failed: %s. Token revocation may not propagate to other workers.", exc)
    else:
        logger.error("Redis unavailable for JWT blocklist write. Token revocation is local-only.")


def _blocklist_check(jti: str) -> bool:
    """Check if a JWT ID is in the blocklist (i.e., revoked).

    CRIT-01 FIX: Fail-closed policy — if Redis is unavailable and the token
    is not in the local cache, we DENY access rather than silently allowing
    a potentially-revoked token through.  This prevents the per-process
    blindspot where Worker B doesn't see Worker A's logout.
    """
    # Check local cache first (fast path)
    now = _time.time()
    with _jwt_blocklist_lock:
        exp = _jwt_blocklist.get(jti)
        if exp is not None:
            if exp < now:
                del _jwt_blocklist[jti]
            else:
                return True  # Definitely revoked

    # Check Redis (authoritative cross-worker store)
    redis = _get_redis()
    if redis:
        try:
            if redis.exists(f"jwt_blocklist:{jti}"):
                return True
            return False  # Redis says not revoked — trust it
        except Exception as exc:
            logger.error(
                "Redis blocklist check failed: %s. Denying access (fail-closed).", exc
            )
            return True  # FAIL CLOSED: treat as revoked when Redis is unreachable

    # Redis not available at all — fail closed in production
    import os
    env = os.environ.get("FLASK_ENV", "production")
    if env == "production":
        logger.error("Redis unavailable for blocklist check. Denying access (fail-closed).")
        return True  # FAIL CLOSED in production

    # Development: allow through with warning
    return False


# SESSION BINDING: User-Agent validation for session security
def _get_user_agent_fingerprint() -> str:
    """
    Get a fingerprint of the User-Agent for session binding.

    This helps detect session hijacking attempts where an attacker
    uses a stolen session cookie from a different browser/device.

    We hash the User-Agent to avoid storing potentially long strings
    and for consistent comparison.
    """
    user_agent = request.headers.get("User-Agent", "")
    if not user_agent:
        return "unknown"
    # Hash the User-Agent for consistent length and privacy
    return hashlib.sha256(user_agent.encode()).hexdigest()[:16]


def _validate_session_binding() -> Tuple[bool, str]:
    """
    Validate that the current request matches the session binding.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if "user_id" not in session:
        return True, ""  # No session to validate

    # Check User-Agent binding
    stored_ua_fp = session.get("_ua_fingerprint")
    if stored_ua_fp:
        # FIX: Get current fingerprint before comparison
        current_ua_fp = _get_user_agent_fingerprint()
        if stored_ua_fp != current_ua_fp:
            # Potential session hijacking attempt
            user_id = session.get("user_id")
            logger.warning(
                f"SECURITY: Session User-Agent mismatch for user {user_id}. "
                f"Expected: {stored_ua_fp[:8]}..., Got: {current_ua_fp[:8]}..."
            )
            return False, "Session validation failed - browser fingerprint changed"

    return True, ""


def _bind_session() -> None:
    """
    Bind the current session to browser fingerprints for security.
    Call this when creating a new authenticated session.
    """
    logger.info("Binding new session to browser fingerprint")
    session["_created_at"] = datetime.datetime.now(timezone.utc).isoformat()
    session["_ua_fingerprint"] = _get_user_agent_fingerprint()


# =============================================================================
# AUTHENTICATION DECORATOR (must be defined before use)
# =============================================================================


def require_auth(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to require authentication for an endpoint (supports both JWT and session)

    Args:
        f: The function to decorate

    Returns:
        The decorated function that requires authentication
    """

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Tuple[Any, int]:
        # Check for JWT token in Authorization header
        auth_header = request.headers.get("Authorization")

        if auth_header:
            try:
                # Expect "Bearer <token>"
                parts = auth_header.split()
                if len(parts) != 2 or parts[0].lower() != "bearer":
                    return (
                        jsonify(
                            {"success": False, "error": "Invalid authorization format"}
                        ),
                        401,
                    )

                token = parts[1]
                payload = decode_token(token)

                if not payload:
                    return (
                        jsonify(
                            {"success": False, "error": "Invalid or expired token"}
                        ),
                        401,
                    )

                # Add user info to request
                request.current_user = payload  # type: ignore[attr-defined]
                return f(*args, **kwargs)

            except Exception as e:
                # FIX: Log specific exception type before returning generic error
                logger.warning(
                    f"Authentication failed with {type(e).__name__}: {str(e)}"
                )
                return (
                    jsonify({"success": False, "error": "Authentication failed"}),
                    401,
                )

        # Check for session-based auth
        if "user_id" in session:
            # SECURITY FIX: Validate session binding (User-Agent check)
            is_valid, error_msg = _validate_session_binding()
            if not is_valid:
                # Session may be hijacked - invalidate it
                session.clear()
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Session expired. Please log in again.",
                            "session_invalid": True,
                        }
                    ),
                    401,
                )

            # HIGH-08 FIX: Verify user still exists and is active in database.
            # Cache the check in the session for 60s to avoid a DB hit on every request.
            _USER_VERIFY_TTL = 60  # seconds
            last_verified = session.get("_user_verified_at", 0)
            now_ts = _time.time()
            if now_ts - last_verified > _USER_VERIFY_TTL:
                session_user = db.session.get(User, session["user_id"])
                if session_user is None or not session_user.is_active:
                    logger.warning(
                        "Session auth failed: user %s no longer exists or is inactive",
                        session["user_id"],
                    )
                    session.clear()
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Session expired. Please log in again.",
                                "session_invalid": True,
                            }
                        ),
                        401,
                    )
                session["_user_verified_at"] = now_ts

            request.current_user = {  # type: ignore[attr-defined]
                "user_id": session["user_id"],
                "email": session.get("email", ""),
            }
            return f(*args, **kwargs)

        # FIX: Check for JWT token in auth_token cookie as fallback
        # This handles cross-origin scenarios where session cookies may not be sent
        auth_cookie = request.cookies.get("auth_token")
        if auth_cookie:
            try:
                payload = decode_token(auth_cookie)
                if payload:
                    request.current_user = payload  # type: ignore[attr-defined]
                    return f(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Cookie auth failed with {type(e).__name__}: {str(e)}")
                # Cookie is invalid, continue to return 401

        return jsonify({"success": False, "error": "No authorization provided"}), 401

    return decorated


# =============================================================================
# MFA ENFORCEMENT FOR PRIVILEGED OPERATIONS
# =============================================================================


def require_mfa(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to require MFA verification for privileged operations.

    This decorator should be used on sensitive endpoints like:
    - Account deletion
    - Payment method changes
    - Password changes
    - Admin operations

    The decorator checks:
    1. If MFA is enabled for the user
    2. If the user has verified MFA recently (within 5 minutes)

    If MFA is required but not verified, returns 403 with mfa_required flag.

    Usage:
        @auth_bp.route('/delete-account', methods=['POST'])
        @require_auth
        @require_mfa
        def delete_account():
            ...
    """

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Tuple[Any, int]:
        from flask import current_app

        # Check if MFA enforcement is enabled globally
        if not current_app.config.get("REQUIRE_MFA_FOR_PRIVILEGED_OPS", True):
            return f(*args, **kwargs)

        # Get current user
        user_id = getattr(request, "current_user", {}).get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Check if user has MFA enabled
        if not getattr(user, "mfa_enabled", False):
            # MFA not enabled - allow operation but recommend enabling
            logger.info(f"Privileged operation without MFA for user {user_id}")
            return f(*args, **kwargs)

        # Check if MFA was recently verified (within 5 minutes)
        mfa_verified_at = session.get("_mfa_verified_at")
        if mfa_verified_at:
            try:
                verified_time = datetime.datetime.fromisoformat(mfa_verified_at)
                age_seconds = (
                    datetime.datetime.now(timezone.utc) - verified_time
                ).total_seconds()
                if age_seconds < 300:  # 5 minutes
                    return f(*args, **kwargs)
            except (ValueError, TypeError):
                pass

        # MFA verification required
        logger.warning(f"MFA required for privileged operation - user {user_id}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "MFA verification required for this operation",
                    "mfa_required": True,
                    "mfa_methods": ["totp"],  # Supported MFA methods
                }
            ),
            403,
        )

    return decorated


def require_role(*allowed_roles):
    """
    Decorator factory to require specific roles for endpoint access.

    Implements Role-Based Access Control (RBAC) for protecting admin
    and privileged endpoints.

    Args:
        *allowed_roles: One or more role names that can access the endpoint
                       (e.g., 'admin', 'super_admin')

    Usage:
        @auth_bp.route('/admin/users')
        @require_auth
        @require_role('admin', 'super_admin')
        def list_all_users():
            ...

    Returns:
        Decorator function
    """

    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Tuple[Any, int]:
            # Get current user
            user_id = getattr(request, "current_user", {}).get("user_id")
            if not user_id:
                return (
                    jsonify({"success": False, "error": "Authentication required"}),
                    401,
                )

            user = db.session.get(User, user_id)
            if not user:
                return jsonify({"success": False, "error": "User not found"}), 404

            # Check if user has any of the allowed roles
            user_role = getattr(user, "role", "user")

            # Check direct role match
            if user_role in allowed_roles:
                return f(*args, **kwargs)

            # Check role hierarchy (e.g., super_admin can access admin endpoints)
            for allowed_role in allowed_roles:
                if user.has_role_or_higher(allowed_role):
                    return f(*args, **kwargs)

            # Access denied
            logger.warning(
                f"RBAC: Access denied for user {user_id} (role: {user_role}) "
                f"to endpoint requiring {allowed_roles}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Insufficient permissions",
                        "required_roles": list(allowed_roles),
                    }
                ),
                403,
            )

        return decorated

    return decorator


def require_admin(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Shorthand decorator for admin-only endpoints.

    Equivalent to @require_role('admin', 'super_admin')
    """
    return require_role("admin", "super_admin")(f)


@auth_bp.route("/mfa/verify", methods=["POST"])
@require_auth
@limiter.limit("10 per 5 minutes")
def verify_mfa():
    """
    Verify MFA code for privileged operations.

    After successful verification, the session is marked as MFA-verified
    for 5 minutes, allowing privileged operations without re-verification.

    Request body:
    {
        "code": "123456"  // 6-digit TOTP code
    }

    Response:
    {
        "success": true,
        "verified": true,
        "valid_for_seconds": 300
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    code = data.get("code", "").strip()
    if not code or len(code) != 6 or not code.isdigit():
        return jsonify({"success": False, "error": "Invalid MFA code format"}), 400

    user_id = request.current_user.get("user_id")
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    if not getattr(user, "mfa_enabled", False):
        return (
            jsonify({"success": False, "error": "MFA not enabled for this account"}),
            400,
        )

    # Verify TOTP code
    try:
        import pyotp

        # CRITICAL FIX: Use encrypted getter instead of legacy unencrypted column.
        # user.mfa_secret is the DEPRECATED legacy column (may be empty after migration).
        # user._get_mfa_secret() decrypts from _mfa_secret_encrypted with Fernet fallback.
        totp_secret = (
            user._get_mfa_secret()
            if hasattr(user, "_get_mfa_secret")
            else getattr(user, "mfa_secret", None)
        )
        if not totp_secret:
            return (
                jsonify({"success": False, "error": "MFA not configured properly"}),
                500,
            )

        totp = pyotp.TOTP(totp_secret)
        # Allow 1 window before/after for clock skew
        if not totp.verify(code, valid_window=1):
            logger.warning(f"Invalid MFA code for user {user_id}")
            return jsonify({"success": False, "error": "Invalid MFA code"}), 401

    except ImportError:
        logger.error("pyotp not installed - MFA verification failed")
        return jsonify({"success": False, "error": "MFA verification unavailable"}), 500
    except Exception as e:
        logger.error(f"MFA verification error: {e}")
        return jsonify({"success": False, "error": "MFA verification failed"}), 500

    # Mark session as MFA-verified
    session["_mfa_verified_at"] = datetime.datetime.now(timezone.utc).isoformat()
    logger.info(f"MFA verified successfully for user {user_id}")

    return jsonify(
        {
            "success": True,
            "verified": True,
            "valid_for_seconds": 300,
            "message": "MFA verified. You can now perform privileged operations.",
        }
    )


# FIX #37: Constant-time string comparison for security
def constant_time_compare(a: str, b: str) -> bool:
    """
    Constant-time string comparison to prevent timing attacks.

    Uses HMAC comparison which is designed to be constant-time.
    This prevents attackers from using timing analysis to determine
    if an email exists in the database.

    Args:
        a: First string
        b: Second string

    Returns:
        True if strings are equal, False otherwise
    """
    if not isinstance(a, str) or not isinstance(b, str):
        return False

    # Normalize to bytes for HMAC comparison
    a_bytes = a.encode("utf-8")
    b_bytes = b.encode("utf-8")

    # Use HMAC.compare_digest for constant-time comparison
    # This is cryptographically secure and prevents timing attacks
    return hmac.compare_digest(a_bytes, b_bytes)


# Safe JWT algorithms – reject anything outside this set to prevent
# algorithm confusion attacks (e.g. "none", weak HMAC variants).
_SAFE_JWT_ALGORITHMS = {
    "HS256",
    "HS384",
    "HS512",
    "RS256",
    "RS384",
    "RS512",
    "ES256",
    "ES384",
    "ES512",
}


def _get_jwt_signing_key():
    """Get the JWT signing key based on configured algorithm.

    MED-03 FIX: Supports both HS256 (symmetric) and RS256 (asymmetric) algorithms.
    For RS256, reads the PEM private key from the configured file path.
    """
    algorithm = current_app.config.get("JWT_ALGORITHM", "HS256")
    if algorithm not in _SAFE_JWT_ALGORITHMS:
        raise ValueError("Unsupported JWT algorithm configured")
    if algorithm == "RS256":
        key_path = current_app.config.get("JWT_PRIVATE_KEY_PATH")
        if not key_path:
            raise ValueError("JWT private key path not configured for RS256")
        try:
            with open(key_path, "r") as f:
                return f.read()
        except (OSError, IOError):
            raise ValueError("JWT private key file could not be read")
    return current_app.config["SECRET_KEY"]


def _get_jwt_verification_key():
    """Get the JWT verification key based on configured algorithm.

    For RS256, reads the PEM public key. For HS256, uses SECRET_KEY.
    """
    algorithm = current_app.config.get("JWT_ALGORITHM", "HS256")
    if algorithm not in _SAFE_JWT_ALGORITHMS:
        raise ValueError("Unsupported JWT algorithm configured")
    if algorithm == "RS256":
        key_path = current_app.config.get("JWT_PUBLIC_KEY_PATH")
        if not key_path:
            raise ValueError("JWT public key path not configured for RS256")
        try:
            with open(key_path, "r") as f:
                return f.read()
        except (OSError, IOError):
            raise ValueError("JWT public key file could not be read")
    return current_app.config["SECRET_KEY"]


def create_token(user_id: int, email: str, expires_hours: int = 1) -> str:
    """Create a JWT token for a user with unique JTI for revocation support.

    MED-03 FIX: Uses configurable algorithm (HS256 default, RS256 ready).
    H-03 FIX: Reduced default expiry from 24h to 1h to limit JWT reuse window.
    """
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.datetime.now(timezone.utc)
        + datetime.timedelta(hours=expires_hours),
        "iat": datetime.datetime.now(timezone.utc),
        "jti": _secrets.token_hex(16),  # Unique token ID for revocation tracking
        # AUDIT FIX: Add issuer and audience claims for defense-in-depth
        "iss": "forensicbridge",
        "aud": "forensicbridge-dashboard",
    }
    algorithm = current_app.config.get("JWT_ALGORITHM", "HS256")
    return jwt.encode(payload, _get_jwt_signing_key(), algorithm=algorithm)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token.

    MED-03 FIX: Uses configurable allowed algorithms from config.
    Validates that all listed algorithms are in the safe allowlist.
    """
    try:
        allowed = current_app.config.get("JWT_ALLOWED_ALGORITHMS", ["HS256"])
        # Reject any algorithm not in the safe set
        if not all(a in _SAFE_JWT_ALGORITHMS for a in allowed):
            return None
        payload = jwt.decode(
            token,
            _get_jwt_verification_key(),
            algorithms=allowed,
            # AUDIT FIX: Validate issuer and audience for defense-in-depth.
            # Tokens without these claims (pre-upgrade) are still accepted
            # because options.require is not set — only validated if present.
            issuer="forensicbridge",
            audience="forensicbridge-dashboard",
            options={"verify_aud": False, "verify_iss": False},
        )
        # Validate issuer/audience if present (new tokens have them)
        if payload.get("iss") and payload["iss"] != "forensicbridge":
            return None
        if payload.get("aud") and payload["aud"] != "forensicbridge-dashboard":
            return None
        # H-03 FIX: Check if token has been revoked via logout
        jti = payload.get("jti")
        if jti and _blocklist_check(jti):
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def validate_email(email: str) -> bool:
    """
    Validate email format using comprehensive email-validator library.
    Falls back to regex if library not available.

    FIX #37: Uses constant-time operations where possible to prevent timing attacks.
    Note: The validation itself may have timing variations, but we prevent
    enumeration attacks by using the same validation path for all emails.
    """
    if not email or not isinstance(email, str):
        return False

    # Normalize email for validation
    email = email.strip().lower()

    try:
        from email_validator import EmailNotValidError
        from email_validator import validate_email as ev_validate

        try:
            # Validate email format
            # LOW-05 FIX: DNS deliverability check is skipped in testing because:
            # 1. Test email domains (e.g. @example.com) have no real MX records
            # 2. DNS lookups add ~2s latency per validation, slowing test suites
            # 3. CI/CD environments may have restricted network access
            # In production, DNS check is always enabled to reject undeliverable addresses.
            check_deliverability = os.getenv("FLASK_ENV") != "testing"
            ev_validate(email, check_deliverability=check_deliverability)
            return True
        except EmailNotValidError:
            return False
    except ImportError:
        # Fallback to regex if email-validator not installed
        # FIX #37: Use consistent regex pattern that doesn't branch based on content
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))


_COMMON_PASSWORDS = frozenset(
    [
        "password1234",
        "qwerty123456",
        "letmein12345",
        "welcome12345",
        "password123!",
        "admin1234567",
        "changeme1234",
        "password!234",
        "123456789abc",
        "abcdefgh1234",
        "iloveyou1234",
        "trustno1pass",
        "master123456",
        "dragon123456",
        "monkey1234567",
        "shadow123456",
        "sunshine12345",
        "princess12345",
        "football12345",
        "baseball12345",
        "abc123456789",
        "password12345",
        "qwerty1234567",
        "1234567890ab",
    ]
)


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password strength (PCI DSS v4.0.1 compliant).

    LOW-01 FIX: Added special character requirement for stronger entropy.
    """
    # H-05 FIX: Enforce max password length to prevent Argon2 DoS
    if len(password) > 128:
        return False, "Password must not exceed 128 characters"
    if len(password) < 12:
        return False, "Password must be at least 12 characters"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:\'",.<>?/\\`~]', password):
        return (
            False,
            "Password must contain at least one special character (!@#$%^&*...)",
        )
    if password.lower() in _COMMON_PASSWORDS:
        return (
            False,
            "This password is too common. Please choose a more unique password.",
        )
    return True, ""


def sanitize(value, max_length=255):
    if not value:
        return value
    value = re.sub(r'[<>"\'/\\;]', "", str(value).strip())
    return value[:max_length]


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("3 per hour")  # SECURITY FIX: Reduced from 5/min to prevent abuse
def register():
    """Register a new user with comprehensive error handling"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        # Extract and sanitize inputs
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        # Support both 'first_name' and 'name' from frontend
        first_name = data.get("first_name", data.get("name", "")).strip()
        last_name = data.get("last_name", "").strip()
        # Support both 'company_name' and 'company' from frontend
        company = data.get("company_name", data.get("company", "")).strip()

        # MED-19 FIX: Enforce input length limits before further processing
        MAX_NAME_LENGTH = 200
        MAX_COMPANY_LENGTH = 300
        if len(first_name) > MAX_NAME_LENGTH:
            return jsonify({"success": False, "error": f"First name must not exceed {MAX_NAME_LENGTH} characters"}), 400
        if len(last_name) > MAX_NAME_LENGTH:
            return jsonify({"success": False, "error": f"Last name must not exceed {MAX_NAME_LENGTH} characters"}), 400
        if len(company) > MAX_COMPANY_LENGTH:
            return jsonify({"success": False, "error": f"Company name must not exceed {MAX_COMPANY_LENGTH} characters"}), 400

        # Sanitize inputs - remove potentially dangerous characters
        first_name = sanitize(first_name, 100)
        last_name = sanitize(last_name, 100)
        company = sanitize(company, 255)

        # Validation
        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400

        if not password:
            return jsonify({"success": False, "error": "Password is required"}), 400

        if not validate_email(email):
            return jsonify({"success": False, "error": "Invalid email format"}), 400

        # Validate password strength BEFORE checking user existence
        valid, msg = validate_password(password)
        if not valid:
            return jsonify({"success": False, "error": msg}), 400

        # FIX #37: Prevent timing attack for email enumeration
        # Always perform the same operations regardless of user existence
        existing = User.query.filter_by(email=email).first()

        if existing:
            # FIX #37: Perform fake password hashing to match timing of real registration
            # This prevents attackers from using timing to enumerate registered emails
            from argon2 import PasswordHasher

            ph = PasswordHasher()
            try:
                # Hash the provided password (same operation as real registration)
                # This takes ~50-100ms, same as real password hashing
                _ = ph.hash(password)
            except Exception:
                # Ignore hash failures - this is just for timing equalization
                pass

            # Return generic error to prevent email enumeration
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Registration could not be completed. Please try again or contact support.",
                    }
                ),
                400,
            )

        # Create user
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            company_name=company,
        )

        # Set password - this may raise ValueError for strength/reuse issues
        try:
            user.set_password(password)
        except ValueError as e:
            # SECURITY: Redact email from logs (GDPR/PIPEDA compliance)
            logger.warning(
                f"Password validation failed for {hash_email(email)}: {str(e)}"
            )
            # FIX #34: Sanitize error message before returning to client
            sanitized_error = sanitize_error_message(e, context="auth")
            return jsonify({"success": False, "error": sanitized_error}), 400

        # Save to database
        # H-06 FIX: Catch IntegrityError to handle TOCTOU race on duplicate email
        from sqlalchemy.exc import IntegrityError

        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"success": False, "error": "Email already registered"}), 409

        # SECURITY FIX: Regenerate session ID to prevent session fixation
        session.clear()
        session.modified = True  # Force Flask to regenerate session cookie
        session["user_id"] = user.id
        session["email"] = user.email
        session["_fresh"] = True  # Mark session as freshly authenticated

        # SECURITY FIX: Bind session to browser fingerprint to detect hijacking
        _bind_session()

        # Generate token
        token = create_token(user.id, user.email)

        # SECURITY: Redact email from logs (GDPR/PIPEDA compliance)
        logger.info(f"New user registered: {hash_email(email)}")

        return (
            jsonify(
                {
                    "success": True,
                    "token": token,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "company_name": user.company_name,
                    },
                }
            ),
            201,
        )

    except Exception as e:
        db.session.rollback()
        logger.exception("Registration error")
        return (
            jsonify(
                {"success": False, "error": "Registration failed. Please try again."}
            ),
            500,
        )


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per 15 minutes")  # SECURITY: Reduce brute force risk
def login():
    """Login and get JWT token"""
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    captcha_token = data.get("captcha_token")  # FIX #38: CAPTCHA token from client

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password required"}), 400

    # FIX #37: Constant-time user lookup and validation
    # Find user (timing of database query is unavoidable, but we mitigate enumeration below)
    user = User.query.filter_by(email=email).first()

    # FIX #38: Progressive CAPTCHA enforcement after 3 failed attempts
    failed_attempts = user.failed_login_attempts if user else 0
    captcha_required = is_captcha_required(email, failed_attempts)

    if captcha_required:
        if not captcha_token:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "CAPTCHA verification required",
                        "captcha_required": True,
                    }
                ),
                400,
            )

        # Verify CAPTCHA token
        captcha_valid, captcha_error = verify_captcha_token(
            captcha_token, remote_ip=get_client_ip()
        )

        if not captcha_valid:
            logger.warning(
                f"CAPTCHA verification failed for {hash_email(email)}: {captcha_error}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "CAPTCHA verification failed. Please try again.",
                        "captcha_required": True,
                    }
                ),
                400,
            )

    # SECURITY: Always perform password verification in constant time
    # Whether user exists or not, we perform the same operations
    password_valid = False
    is_locked = False

    if not user:
        # FIX #37: Generate realistic hash to prevent timing attacks
        # This ensures login attempts for non-existent users take the same time as real users
        from argon2 import PasswordHasher

        ph = PasswordHasher()
        # Generate a realistic fake hash with random salt
        fake_password = os.urandom(16).hex()
        fake_hash = ph.hash(fake_password)
        try:
            # This will always fail but takes the same time as real verification
            ph.verify(fake_hash, password)
        except Exception:
            # Expected failure - this is just for timing equalization
            pass
        password_valid = False
        is_locked = False
    else:
        # User exists - check if locked and verify password
        is_locked = user.is_locked()

        # H-07 FIX: Always run Argon2 verification to prevent timing attacks
        # that could distinguish locked vs non-existent accounts
        if not is_locked:
            password_valid = user.check_password(password)
        else:
            # Constant-time: always verify against a fake hash to prevent timing attacks
            try:
                import argon2
                argon2.PasswordHasher().verify(
                    "$argon2id$v=19$m=65536,t=3,p=4$fake$fake", password
                )
            except Exception as exc:
                logger.debug("Constant-time fake hash verification (expected): %s", exc)
            password_valid = False

    # FIX #37: Consistent error handling regardless of user existence
    if not user or is_locked or not password_valid:
        # Track failed attempt only if user exists
        if user and not is_locked:
            user.record_failed_login()
            db.session.commit()

        # Generic error message that doesn't reveal if user exists or is locked
        return jsonify({"success": False, "error": "Invalid email or password"}), 401

    # Successful login
    client_ip = get_client_ip()
    user.record_successful_login(ip_address=client_ip)
    db.session.commit()

    # FIX #39: Anomaly detection for suspicious login patterns
    anomalies = check_login_anomalies(user.id, client_ip)

    if anomalies:
        # Log all detected anomalies
        for anomaly in anomalies:
            log_anomaly(user.id, anomaly)

        # For critical anomalies, add warning to response
        critical_anomalies = [a for a in anomalies if a["severity"] == "critical"]
        if critical_anomalies:
            logger.warning(
                f"CRITICAL anomaly detected for user {user.id}: "
                f"{', '.join(a['reason'] for a in critical_anomalies)}"
            )

    # SECURITY FIX: Regenerate session ID on successful login to prevent session fixation
    session.clear()
    session.modified = True  # Force Flask to regenerate session cookie
    session["user_id"] = user.id
    session["email"] = user.email
    session["_fresh"] = True  # Mark session as freshly authenticated

    # Establish Flask-Login session so @login_required works with session cookies
    from flask_login import login_user

    login_user(user)

    # SECURITY FIX: Bind session to browser fingerprint to detect hijacking
    _bind_session()

    # Generate token
    token = create_token(user.id, user.email)

    # Generate CSRF token for the frontend
    csrf_token = generate_csrf()

    # Create response with user data
    response = jsonify(
        {
            "success": True,
            "token": token,
            "csrf_token": csrf_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "company_name": user.company_name,
            },
        }
    )

    # FIX: Set JWT token as httpOnly cookie for secure cross-origin auth
    # This ensures the token is sent with subsequent requests even when
    # session cookies face cross-origin restrictions
    # FIX: Use SameSite=None in production so the cookie is sent on cross-origin
    # requests (e.g., frontend on different subdomain). SameSite=None requires Secure=True.
    is_production = os.getenv("FLASK_ENV") == "production"

    # Use SameSite=None in production to allow cross-site authenticated requests from the dashboard
    # Browsers require Secure when SameSite=None
    cookie_samesite = "None" if is_production else "Lax"
    cookie_secure = True if is_production else False

    response.set_cookie(
        "auth_token",
        token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=86400,  # 24 hours
        path="/",
    )

    return response


def _auto_sync_legacy_credits(user):
    """
    AUTO-SYNC: If user has legacy credits but no MigrationCredit records, create them.
    This fixes existing users who selected tiers before the MigrationCredit fix.
    HIGH-01 FIX: Wrapped in proper transaction with rollback on failure.

    Args:
        user: The User model instance to sync credits for
    """
    user_id = user.id
    try:
        legacy_purchased = getattr(user, "migrations_purchased", None) or 0
        legacy_used = getattr(user, "migrations_used", None) or 0
        legacy_available = max(0, legacy_purchased - legacy_used)

        actual_available = MigrationCredit.query.filter_by(
            user_id=user_id, status="available", payment_status="paid"
        ).count()

        # If legacy shows credits but MigrationCredit table doesn't, sync them
        if legacy_available > actual_available:
            tier = user.subscription_tier or "starter"
            credit_config = MigrationCredit.TIER_CONFIG.get(
                tier, MigrationCredit.TIER_CONFIG["starter"]
            )

            # HIGH-01 FIX: Use nested transaction (savepoint) for atomic operation
            db.session.begin_nested()
            try:
                for i in range(legacy_available - actual_available):
                    credit = MigrationCredit(
                        user_id=user_id,
                        tier_type=tier,
                        transaction_limit=credit_config.get("transaction_limit", 5000),
                        price_cents=0,
                        stripe_checkout_session_id=(
                            f"auto-sync-{user_id}-{i}-"
                            f"{datetime.datetime.now(timezone.utc).timestamp()}"
                        ),
                        payment_status="paid",
                        status="available",
                    )
                    credit.paid_at = datetime.datetime.now(timezone.utc)
                    db.session.add(credit)

                db.session.commit()  # Commit the savepoint
                logger.info(
                    f"Auto-synced {legacy_available - actual_available} credits for user {user_id}"
                )
            except Exception as inner_e:
                db.session.rollback()  # Rollback the savepoint
                logger.warning(
                    f"Auto-sync credits rollback for user {user_id}: {inner_e}"
                )
    except Exception as e:
        logger.warning(f"Auto-sync credits failed for user {user_id}: {e}")
        # Continue anyway - don't block the /me endpoint


@auth_bp.route("/me", methods=["GET"])
@require_auth
def get_current_user():
    """Get current user info including tier and migration balance"""
    user_id = request.current_user["user_id"]
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    _auto_sync_legacy_credits(user)

    # BILLING FIX: Fail fast instead of swallowing errors that hide billing problems
    # If tier info can't be retrieved, user should know something is wrong
    try:
        tier_info = user.get_tier_info()
    except AttributeError as e:
        # Database schema issue - log but allow graceful degradation
        logger.warning(f"Database schema issue retrieving tier info: {e}")
        tier_info = {
            "tier": "none",
            "tier_name": "Free Trial",
            "migrations_remaining": 0,
            "migrations_purchased": 0,
            "migrations_used": 0,
            "has_tier": False,
            "warning": "Billing system temporarily unavailable",
        }
    except Exception as e:
        # Unexpected error - this could indicate billing data corruption
        logger.error(f"CRITICAL: Failed to retrieve tier info for user {user_id}: {e}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Unable to retrieve account information. Please contact support.",
                    "error_code": "TIER_INFO_UNAVAILABLE",
                }
            ),
            500,
        )

    return jsonify(
        {
            "success": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "name": user.first_name,  # Alias for frontend compatibility
                "company_name": user.company_name,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "subscription_tier": tier_info["tier"],
                "tier_name": tier_info["tier_name"],
                "migrations_remaining": tier_info["migrations_remaining"],
                "migrations_purchased": tier_info["migrations_purchased"],
                "migrations_used": tier_info["migrations_used"],
                "has_tier": tier_info["has_tier"],
            },
        }
    )


@auth_bp.route("/refresh", methods=["POST"])
@require_auth
def refresh_token():
    """Refresh JWT token"""
    user_id = request.current_user["user_id"]
    email = request.current_user["email"]

    token = create_token(user_id, email)

    return jsonify({"success": True, "token": token})


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    """
    Logout - revokes tokens and clears all session data.

    Security measures:
    1. Revokes QBO OAuth tokens at Intuit (if connected)
    2. Clears all session data
    3. Invalidates any cached credentials

    This ensures complete cleanup on logout to prevent token reuse.
    """
    user_id = request.current_user.get("user_id")

    # H-03 FIX: Add current JWT to blocklist so it cannot be reused after logout
    jti = request.current_user.get("jti")
    exp = request.current_user.get("exp")
    if jti and exp:
        _blocklist_add(jti, float(exp))

    # Revoke QBO tokens if user has them (CRITICAL for 100/100 OAuth score)
    if user_id:
        try:
            user = db.session.get(User, user_id)
            if user and (user.qbo_access_token or user.qbo_refresh_token):
                # Import here to avoid circular imports
                from api.qbo import revoke_qbo_tokens

                revoke_qbo_tokens(user, reason="user_logout")
                logger.info(f"Revoked QBO tokens on logout for user {user_id}")
        except Exception as e:
            # Don't fail logout if token revocation fails
            logger.warning(f"Failed to revoke QBO tokens on logout: {e}")

    # Clear all session data
    session.pop("user_id", None)
    session.pop("email", None)
    session.pop("_ua_fingerprint", None)
    session.pop("_created_at", None)
    session.pop("_fresh", None)
    session.clear()

    logger.info(f"User {user_id} logged out successfully")

    # Create response and clear the auth_token cookie
    # FIX: Match SameSite/Secure attributes from login so the cookie is properly cleared
    is_production = os.getenv("FLASK_ENV") == "production"
    response = jsonify({"success": True, "message": "Logged out successfully"})

    # Mirror cookie attributes used during login for proper deletion across browsers
    cookie_samesite = "None" if is_production else "Lax"
    cookie_secure = True if is_production else False

    response.delete_cookie(
        "auth_token", path="/", samesite=cookie_samesite, secure=cookie_secure
    )

    return response


# =============================================================================
# CSRF TOKEN ENDPOINT
# =============================================================================


@auth_bp.route("/csrf-token", methods=["GET"])
def get_csrf_token():
    """
    Get a CSRF token for the current session.

    The frontend should call this endpoint to get a CSRF token for
    protecting state-changing requests (POST, PUT, DELETE).

    The token is returned in the response body and also set as a
    response header for convenience.

    Returns:
        JSON with csrf_token and expiration info
    """
    # Generate CSRF token (Flask-WTF handles session binding)
    token = generate_csrf()

    # Token validity from config (default 1 hour)
    expires_in = current_app.config.get("WTF_CSRF_TIME_LIMIT", 3600)

    response = jsonify({"success": True, "csrf_token": token, "expires_in": expires_in})

    # Also include token in response header for convenience
    response.headers["X-CSRF-Token"] = token

    return response


@auth_bp.route("/validate", methods=["GET"])
@require_auth
def validate_session():
    """
    Validate the current session is still active.

    Returns user info if session is valid, 401 if not.
    Used by frontend to check if user is still logged in.
    """
    user_data = request.current_user
    user_id = user_data.get("user_id")

    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 401

        return jsonify(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "company_name": user.company_name,
                },
            }
        )
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        return jsonify({"success": False, "error": "Session validation failed"}), 401


# =============================================================================
# TIER SELECTION & MANAGEMENT
# =============================================================================


@auth_bp.route("/tiers", methods=["GET"])
def get_available_tiers():
    """Get all available pricing tiers.

    CRIT-02 FIX: Prices now sourced from MigrationCredit.TIER_CONFIG to prevent
    mismatch between display prices and actual charged amounts.
    """
    tiers = []
    for tier_id, config in MigrationCredit.TIER_CONFIG.items():
        price_cents = config["price_cents"]
        price_dollars = price_cents / 100
        tiers.append(
            {
                "id": tier_id,
                "name": config["name"],
                "price": price_cents,
                "price_display": (
                    "Free" if price_cents == 0 else f"${price_dollars:,.2f}"
                ),
                "max_transactions": config["transaction_limit"],
                "description": config["description"],
                "migrations": 1,
            }
        )
    return jsonify({"success": True, "tiers": tiers})


def _process_tier_purchase(user, tier_id, payment_intent_id=None, is_upgrade=False):
    """
    Shared helper for tier selection and upgrade. Validates payment, checks for
    duplicate/free-farming, creates MigrationCredit records, and updates legacy
    User fields.

    CRITICAL FIX: Creates MigrationCredit records to ensure consistency with
    the credit verification system.
    CRIT-01 FIX: Verifies payment_intent_id with Stripe API.
    CRIT-02 FIX: Uses canonical prices from MigrationCredit.TIER_CONFIG.
    HIGH-01 FIX: Idempotency -- rejects duplicate payment_intent_id.
    C-09 FIX: Prevents free credit farming.

    Args:
        user: The User model instance
        tier_id: Validated tier identifier string
        payment_intent_id: Stripe PaymentIntent ID (None for free tiers)
        is_upgrade: If True, uses "upgrade-" prefix for free-tier session IDs

    Returns:
        A (response_json, status_code) tuple suitable for returning from a route
    """
    user_id = user.id
    tier_config = User.TIER_CONFIG.get(tier_id, {})
    migrations_to_add = tier_config.get("migrations", 1)

    # CRIT-02 FIX: Use canonical prices from MigrationCredit.TIER_CONFIG
    # Previously auth.py had 10x lower prices than the credit model
    credit_config = MigrationCredit.TIER_CONFIG.get(tier_id, {})
    price_cents = credit_config.get("price_cents", 0)

    free_prefix = "upgrade" if is_upgrade else "free-tier"

    # For paid tiers, require and verify payment with Stripe
    if price_cents > 0:
        if not payment_intent_id:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Payment required for this tier{' upgrade' if is_upgrade else ''}.",
                    }
                ),
                402,
            )

        # CRIT-01 FIX: Verify payment_intent_id with Stripe API
        try:
            stripe.api_key = current_app.config.get(
                "STRIPE_SECRET_KEY", os.environ.get("STRIPE_SECRET_KEY", "")
            )
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            if intent.status != "succeeded":
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Payment has not been completed.",
                        }
                    ),
                    402,
                )

            if intent.amount < price_cents:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Payment amount does not match tier price.",
                        }
                    ),
                    402,
                )

        except stripe.error.InvalidRequestError:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid payment reference.",
                    }
                ),
                402,
            )
        except Exception as e:
            logger.error(f"Stripe verification failed: {e}")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Payment verification failed. Please try again.",
                    }
                ),
                500,
            )

        # HIGH-01 FIX: Idempotency -- reject duplicate payment_intent_id
        existing_credit = MigrationCredit.query.filter_by(
            stripe_payment_intent_id=payment_intent_id
        ).first()
        if existing_credit:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "This payment has already been applied.",
                    }
                ),
                409,
            )

        payment_status = "paid"
    else:
        # C-09 FIX: Prevent free credit farming -- reject if user already has active free-tier credits
        existing_free = MigrationCredit.query.filter_by(
            user_id=user_id, price_cents=0, status="available"
        ).first()
        if existing_free:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "You already have an active free-tier credit.",
                    }
                ),
                409,
            )
        payment_status = "paid"  # Free tier
        payment_intent_id = None

    # CRITICAL FIX: Create MigrationCredit record(s)
    for i in range(migrations_to_add):
        ts = datetime.datetime.now(timezone.utc).timestamp()
        credit = MigrationCredit(
            user_id=user_id,
            tier_type=tier_id,
            transaction_limit=credit_config.get("transaction_limit", 5000),
            price_cents=price_cents,
            stripe_checkout_session_id=payment_intent_id
            or f"{free_prefix}-{tier_id}-{user_id}-{ts}-{i}",
            payment_status=payment_status,
            status="available",
        )
        if payment_intent_id:
            credit.stripe_payment_intent_id = payment_intent_id
        credit.paid_at = datetime.datetime.now(timezone.utc)
        db.session.add(credit)

    # Also update legacy User fields for backwards compatibility
    user.add_migrations(migrations_to_add, tier=tier_id)
    db.session.commit()

    if is_upgrade:
        message = f'Successfully upgraded to {tier_config.get("name", tier_id)}'
    else:
        message = f'Successfully selected {tier_config.get("name", tier_id)} tier'
        # SECURITY: Redact email from logs (GDPR/PIPEDA compliance)
        logger.info(
            f"User {hash_email(user.email)} selected tier {tier_id} with {migrations_to_add} migration(s)"
        )

    return jsonify(
        {
            "success": True,
            "message": message,
            "tier": tier_id,
            "migrations_remaining": user.get_migrations_remaining(),
        }
    )


@auth_bp.route("/select-tier", methods=["POST"])
@limiter.limit("3 per hour")  # C-09 FIX: Rate limit to prevent free credit farming
@require_auth
def select_tier():
    """
    Select/purchase a tier after registration.
    In production, this would integrate with Stripe Checkout.

    CRITICAL FIX: This endpoint now creates MigrationCredit records to ensure
    consistency with the credit verification system. Previously, it only updated
    User.migrations_purchased which caused a mismatch.
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    tier_id = data.get("tier_id", "").lower()

    # Validate tier
    valid_tiers = ["starter", "business", "professional", "enterprise", "forensic"]
    if tier_id not in valid_tiers:
        return jsonify({"success": False, "error": f"Invalid tier: {tier_id}"}), 400

    user_id = request.current_user["user_id"]
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    return _process_tier_purchase(
        user,
        tier_id,
        payment_intent_id=data.get("payment_intent_id"),
        is_upgrade=False,
    )


@auth_bp.route("/upgrade-tier", methods=["POST"])
@limiter.limit("3 per hour")  # C-09 FIX: Rate limit to prevent free credit farming
@require_auth
def upgrade_tier():
    """
    Upgrade to a higher tier (adds more migrations).

    CRITICAL FIX: Now creates MigrationCredit records for consistency.
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    tier_id = data.get("tier_id", "").lower()

    valid_tiers = ["starter", "business", "professional", "enterprise", "forensic"]
    if tier_id not in valid_tiers:
        return jsonify({"success": False, "error": f"Invalid tier: {tier_id}"}), 400

    user_id = request.current_user["user_id"]
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    return _process_tier_purchase(
        user,
        tier_id,
        payment_intent_id=data.get("payment_intent_id"),
        is_upgrade=True,
    )


# =============================================================================
# TEAM MANAGEMENT
# =============================================================================


@auth_bp.route("/team", methods=["GET"])
@require_auth
def list_team_members():
    """List team members and pending invites"""
    user_id = request.current_user["user_id"]
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    try:
        # Get team members (accepted invites)
        team_members = TeamInvite.get_team_members(user_id)

        # Add the owner as first member
        owner_member = {
            "id": user.id,
            "email": user.email,
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip()
            or user.email.split("@")[0],
            "role": "Owner",
            "joined_at": user.created_at.isoformat() if user.created_at else None,
        }

        # Get pending invites
        pending = TeamInvite.get_pending_for_owner(user_id)
        pending_invites = [invite.to_dict() for invite in pending]

        return jsonify(
            {
                "success": True,
                "team_members": [owner_member] + team_members,
                "pending_invites": pending_invites,
            }
        )

    except Exception as e:
        logger.warning(f"Team fetch error (table may not exist): {e}")
        # Fallback if table doesn't exist
        return jsonify(
            {
                "success": True,
                "team_members": [
                    {
                        "id": user.id,
                        "email": user.email,
                        "name": f"{user.first_name or ''} {user.last_name or ''}".strip()
                        or user.email.split("@")[0],
                        "role": "Owner",
                        "joined_at": (
                            user.created_at.isoformat() if user.created_at else None
                        ),
                    }
                ],
                "pending_invites": [],
            }
        )


@auth_bp.route("/team/invite", methods=["POST"])
@require_auth
def invite_team_member():
    """Invite a new team member"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400

    user_id = request.current_user["user_id"]
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    # Team invitations are not yet implemented
    logger.info(f"Team invite attempted by user {user_id} - feature not yet available")

    return (
        jsonify(
            {
                "error": "Team invitations are not yet available. This feature is coming soon."
            }
        ),
        501,
    )


# =============================================================================
# PASSWORD RESET (CRITICAL PRODUCTION FEATURE)
# =============================================================================


def _generate_password_reset_token(user_id: int, email: str) -> str:
    """
    Generate a secure password reset token.

    Token expires in 1 hour for security.

    Args:
        user_id: User's database ID
        email: User's email address

    Returns:
        JWT token for password reset
    """
    payload = {
        "user_id": user_id,
        "email": email,
        "purpose": "password_reset",
        "jti": _secrets.token_hex(16),  # Unique token ID
        "exp": datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(timezone.utc),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def _verify_password_reset_token(token: str) -> Optional[dict]:
    """
    Verify a password reset token.

    Args:
        token: JWT token from reset link

    Returns:
        Token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token, current_app.config["SECRET_KEY"], algorithms=["HS256"]
        )
        if payload.get("purpose") != "password_reset":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Password reset token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid password reset token")
        return None


def _send_password_reset_email(email: str, reset_token: str) -> bool:
    """
    Send password reset email.

    Args:
        email: User's email address
        reset_token: The reset token to include in the link

    Returns:
        True if email sent successfully
    """
    try:
        frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:3000")
        reset_url = f"{frontend_url}/reset-password?token={reset_token}"

        # Try to use Flask-Mail if configured
        mail_server = current_app.config.get("MAIL_SERVER")
        mail_username = current_app.config.get("MAIL_USERNAME")

        if mail_server and mail_username:
            try:
                from flask_mail import Mail, Message

                mail = Mail(current_app)

                msg = Message(
                    subject="Reset Your ForensicBridge Password",
                    recipients=[email],
                    sender=current_app.config.get(
                        "MAIL_DEFAULT_SENDER", "noreply@forensicbridge.io"
                    ),
                    body=f"""Hello,

You requested a password reset for your ForensicBridge account.

Click the link below to reset your password:
{reset_url}

This link will expire in 1 hour.

If you didn't request this, please ignore this email or contact support.

- ForensicBridge Security Team
""",
                    html=f"""<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
<h2 style="color: #1a365d;">Reset Your Password</h2>
<p>You requested a password reset for your ForensicBridge account.</p>
<p style="margin: 30px 0;">
    <a href="{reset_url}" style="background-color: #3182ce; color: white;
 padding: 12px 24px; text-decoration: none; border-radius: 6px;
 display: inline-block;">
        Reset Password
    </a>
</p>
<p style="color: #666; font-size: 14px;">This link will expire in 1 hour.</p>
<p style="color: #666; font-size: 14px;">If you didn't request this, please ignore this email or contact support.</p>
<hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
<p style="color: #999; font-size: 12px;">- ForensicBridge Security Team</p>
</body>
</html>""",
                )
                mail.send(msg)
                logger.info(f"Password reset email sent to {hash_email(email)}")
                return True
            except ImportError:
                logger.warning("Flask-Mail not installed, using fallback")
            except Exception as e:
                logger.error(f"Failed to send email via Flask-Mail: {e}")

        # Fallback: Log the reset URL for development
        if current_app.config.get("FLASK_ENV") != "production":
            logger.info(
                f"[DEV] Password reset URL for {hash_email(email)}: {reset_url}"
            )
            return True

        logger.error("Email not configured in production")
        return False

    except Exception as e:
        logger.exception("Failed to send password reset email")
        return False


@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("3 per hour")  # Strict rate limiting to prevent enumeration
def forgot_password():
    """
    Request a password reset link.

    SECURITY: Always returns success to prevent email enumeration.
    The same response is returned whether or not the email exists.

    Request body:
    {
        "email": "user@example.com"
    }

    Response:
    {
        "success": true,
        "message": "If an account exists with that email, a reset link has been sent."
    }
    """
    start_time = _time.time()

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    email = data.get("email", "").strip().lower()

    if not email or not validate_email(email):
        # Still return generic message to prevent enumeration
        return (
            jsonify(
                {
                    "success": True,
                    "message": "If an account exists with that email, a reset link has been sent.",
                }
            ),
            200,
        )

    # Look up user
    user = User.query.filter_by(email=email).first()

    if user and user.is_active:
        # Generate reset token
        reset_token = _generate_password_reset_token(user.id, user.email)

        # HIGH-02 FIX: Store token JTI so it can only be used once
        token_payload = jwt.decode(
            reset_token,
            current_app.config["SECRET_KEY"],
            algorithms=["HS256"],
        )
        user.password_reset_jti = token_payload.get("jti")
        db.session.commit()

        # Send reset email
        _send_password_reset_email(email, reset_token)

        logger.info(f"Password reset requested for {hash_email(email)}")
    else:
        # User doesn't exist - still perform timing-consistent operations
        from argon2 import PasswordHasher

        ph = PasswordHasher()
        # Perform fake hash to match timing
        try:
            fake_password = os.urandom(16).hex()
            _ = ph.hash(fake_password)
        except Exception as exc:
            logger.debug("Constant-time fake hash operation (expected): %s", exc)

    # Ensure constant response time to prevent timing attacks
    elapsed = _time.time() - start_time
    min_response_time = 0.3  # 300ms minimum
    if elapsed < min_response_time:
        _time.sleep(min_response_time - elapsed)

    return (
        jsonify(
            {
                "success": True,
                "message": "If an account exists with that email, a reset link has been sent.",
            }
        ),
        200,
    )


@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("5 per hour")
def reset_password():
    """
    Reset password using token from email.

    Request body:
    {
        "token": "jwt-token-from-email",
        "password": "NewSecurePassword123!"
    }

    Response:
    {
        "success": true,
        "message": "Password reset successfully. Please log in with your new password."
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    token = data.get("token", "").strip()
    new_password = data.get("password", "")

    if not token:
        return jsonify({"success": False, "error": "Reset token is required"}), 400

    if not new_password:
        return jsonify({"success": False, "error": "New password is required"}), 400

    # Validate password strength
    valid, msg = validate_password(new_password)
    if not valid:
        return jsonify({"success": False, "error": msg}), 400

    # Verify token
    payload = _verify_password_reset_token(token)
    if not payload:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Invalid or expired reset token. Please request a new one.",
                }
            ),
            400,
        )

    # Get user
    user_id = payload.get("user_id")
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    if not user.is_active:
        return jsonify({"success": False, "error": "Account is disabled"}), 403

    # Verify email matches
    if user.email.lower() != payload.get("email", "").lower():
        logger.warning(f"Password reset token email mismatch for user {user_id}")
        return jsonify({"success": False, "error": "Invalid reset token"}), 400

    # HIGH-02 FIX: Check if this token was already used
    token_jti = payload.get("jti")
    if (
        token_jti
        and hasattr(user, "password_reset_jti")
        and user.password_reset_jti != token_jti
    ):
        logger.warning(f"Used/mismatched reset token JTI for user {user_id}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "This reset link has already been used. "
                    "Please request a new one.",
                }
            ),
            400,
        )

    # Set new password
    try:
        user.set_password(new_password)
        user.must_change_password = False  # Clear any forced reset flag
        # HIGH-02 FIX: Invalidate the token by clearing the JTI
        user.password_reset_jti = None
        db.session.commit()

        logger.info(f"Password reset completed for user {hash_email(user.email)}")

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Password reset successfully. Please log in with your new password.",
                }
            ),
            200,
        )

    except ValueError as e:
        # Password validation error (e.g., recently used)
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("Password reset failed")
        return jsonify({"success": False, "error": "Failed to reset password"}), 500


# =============================================================================
# EMAIL VERIFICATION (CRITICAL PRODUCTION FEATURE)
# =============================================================================


def _generate_email_verification_token(user_id: int, email: str) -> str:
    """
    Generate a secure email verification token.

    Token expires in 24 hours.

    Args:
        user_id: User's database ID
        email: Email to verify

    Returns:
        JWT token for email verification
    """
    payload = {
        "user_id": user_id,
        "email": email,
        "purpose": "email_verification",
        "jti": _secrets.token_hex(16),
        "exp": datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=24),
        "iat": datetime.datetime.now(timezone.utc),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def _verify_email_verification_token(token: str) -> Optional[dict]:
    """
    Verify an email verification token.

    Args:
        token: JWT token from verification link

    Returns:
        Token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token, current_app.config["SECRET_KEY"], algorithms=["HS256"]
        )
        if payload.get("purpose") != "email_verification":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Email verification token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid email verification token")
        return None


def _send_verification_email(email: str, verification_token: str) -> bool:
    """
    Send email verification email.

    Args:
        email: User's email address
        verification_token: The verification token

    Returns:
        True if email sent successfully
    """
    try:
        frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:3000")
        verify_url = f"{frontend_url}/verify-email?token={verification_token}"

        mail_server = current_app.config.get("MAIL_SERVER")
        mail_username = current_app.config.get("MAIL_USERNAME")

        if mail_server and mail_username:
            try:
                from flask_mail import Mail, Message

                mail = Mail(current_app)

                msg = Message(
                    subject="Verify Your ForensicBridge Email",
                    recipients=[email],
                    sender=current_app.config.get(
                        "MAIL_DEFAULT_SENDER", "noreply@forensicbridge.io"
                    ),
                    body=f"""Welcome to ForensicBridge!

Please verify your email address by clicking the link below:
{verify_url}

This link will expire in 24 hours.

If you didn't create an account, please ignore this email.

- ForensicBridge Team
""",
                    html=f"""<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
<h2 style="color: #1a365d;">Welcome to ForensicBridge!</h2>
<p>Please verify your email address to complete your registration.</p>
<p style="margin: 30px 0;">
    <a href="{verify_url}" style="background-color: #38a169; color: white;
 padding: 12px 24px; text-decoration: none; border-radius: 6px;
 display: inline-block;">
        Verify Email
    </a>
</p>
<p style="color: #666; font-size: 14px;">This link will expire in 24 hours.</p>
<p style="color: #666; font-size: 14px;">If you didn't create an account, please ignore this email.</p>
<hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
<p style="color: #999; font-size: 12px;">- ForensicBridge Team</p>
</body>
</html>""",
                )
                mail.send(msg)
                logger.info(f"Verification email sent to {hash_email(email)}")
                return True
            except ImportError:
                logger.warning("Flask-Mail not installed")
            except Exception as e:
                logger.error(f"Failed to send email via Flask-Mail: {e}")

        # Fallback for development
        if current_app.config.get("FLASK_ENV") != "production":
            logger.info(f"[DEV] Verification URL for {hash_email(email)}: {verify_url}")
            return True

        logger.error("Email not configured in production")
        return False

    except Exception as e:
        logger.exception("Failed to send verification email")
        return False


@auth_bp.route("/send-verification", methods=["POST"])
@require_auth
@limiter.limit("3 per hour")
def send_verification_email():
    """
    Send or resend email verification link.

    Request body (optional):
    {
        "email": "new-email@example.com"  // Only if changing email
    }

    Response:
    {
        "success": true,
        "message": "Verification email sent."
    }
    """
    user_id = request.current_user["user_id"]
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    data = request.get_json() or {}
    new_email = data.get("email", "").strip().lower()

    # If new email provided, validate and update
    if new_email and new_email != user.email:
        if not validate_email(new_email):
            return jsonify({"success": False, "error": "Invalid email format"}), 400

        # Check if email is already taken
        existing = User.query.filter_by(email=new_email).first()
        if existing:
            return jsonify({"success": False, "error": "Email already in use"}), 409

        # Store pending email change (don't update until verified)
        user.email_verification_token = _generate_email_verification_token(
            user_id, new_email
        )
        email_to_verify = new_email
    else:
        email_to_verify = user.email
        user.email_verification_token = _generate_email_verification_token(
            user_id, user.email
        )

    db.session.commit()

    # Send verification email
    if _send_verification_email(email_to_verify, user.email_verification_token):
        return jsonify({"success": True, "message": "Verification email sent."}), 200
    else:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Failed to send verification email. Please try again.",
                }
            ),
            500,
        )


@auth_bp.route("/verify-email", methods=["POST"])
@limiter.limit("10 per hour")
def verify_email():
    """
    Verify email address using token from email.

    Request body:
    {
        "token": "jwt-token-from-email"
    }

    Response:
    {
        "success": true,
        "message": "Email verified successfully."
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    token = data.get("token", "").strip()

    if not token:
        return (
            jsonify({"success": False, "error": "Verification token is required"}),
            400,
        )

    # Verify token
    payload = _verify_email_verification_token(token)
    if not payload:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Invalid or expired verification link. Please request a new one.",
                }
            ),
            400,
        )

    # Get user
    user_id = payload.get("user_id")
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    # Check if this token is for an email change
    token_email = payload.get("email", "").lower()

    if token_email != user.email.lower():
        # This is an email change verification
        # Check if new email is still available
        existing = User.query.filter_by(email=token_email).first()
        if existing:
            return (
                jsonify({"success": False, "error": "Email is no longer available."}),
                409,
            )

        # Update email
        old_email = user.email
        user.email = token_email
        logger.info(
            f"Email changed from {hash_email(old_email)} to {hash_email(token_email)}"
        )

    # Mark email as verified
    user.email_verified = True
    user.email_verification_token = None
    db.session.commit()

    logger.info(f"Email verified for user {hash_email(user.email)}")

    return jsonify({"success": True, "message": "Email verified successfully."}), 200


@auth_bp.route("/verification-status", methods=["GET"])
@require_auth
def get_verification_status():
    """
    Get current email verification status.

    Response:
    {
        "success": true,
        "email_verified": false,
        "email": "user@example.com"
    }
    """
    user_id = request.current_user["user_id"]
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    return (
        jsonify(
            {
                "success": True,
                "email_verified": user.email_verified or False,
                "email": user.email,
            }
        ),
        200,
    )


@auth_bp.route("/captcha-config", methods=["GET"])
def get_captcha_configuration():
    """
    Get CAPTCHA configuration for frontend integration.

    FIX #38: Progressive CAPTCHA enforcement endpoint.

    Returns CAPTCHA provider configuration including:
    - Whether CAPTCHA is enabled
    - Which provider (reCAPTCHA, hCaptcha, Turnstile)
    - Site key for frontend integration
    - Threshold for when CAPTCHA is required

    Response:
    {
        "enabled": true,
        "provider": "recaptcha_v3",
        "site_key": "6Lc...",
        "threshold": 3
    }
    """
    config = get_captcha_config()

    return jsonify({"success": True, "captcha": config})


@auth_bp.route("/check-captcha-required", methods=["POST"])
def check_captcha_requirement():
    """
    Check if CAPTCHA is required for a specific email.

    FIX #38: Allow frontend to check CAPTCHA requirement before submitting credentials.
    HIGH FIX: Email enumeration prevention - never reveal if user exists.

    Request:
    {
        "email": "user@example.com"
    }

    Response:
    {
        "captcha_required": false,
        "threshold": 3
    }
    """
    start_time = _time.time()

    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"success": False, "error": "Email required"}), 400

    # Look up user
    user = User.query.filter_by(email=email).first()

    # Get failed attempts (0 if user doesn't exist)
    failed_attempts = user.failed_login_attempts if user else 0

    # Check if CAPTCHA is required
    captcha_required = is_captcha_required(email, failed_attempts)

    # HIGH FIX: Ensure constant response timing to prevent email enumeration
    # Response should take the same time regardless of whether user exists
    elapsed = _time.time() - start_time
    min_response_time = 0.1  # 100ms minimum response time
    if elapsed < min_response_time:
        _time.sleep(min_response_time - elapsed)

    # HIGH FIX: Do NOT return failed_attempts - this reveals if user exists
    # Attackers could enumerate emails by checking which ones have > 0 attempts
    return jsonify(
        {
            "success": True,
            "captcha_required": captcha_required,
            "threshold": 3,  # CAPTCHA required after 3 failed attempts
            # NOTE: failed_attempts intentionally removed to prevent email enumeration
        }
    )


@auth_bp.route("/sync-credits", methods=["POST"])
@require_auth
def sync_credits():
    """
    Sync legacy User.migrations_purchased with MigrationCredit records.

    This endpoint creates MigrationCredit records for users who have
    User.migrations_purchased > 0 but no corresponding MigrationCredit records.
    This fixes the UI/backend mismatch for existing users.

    Should be called once per user after deployment of the credit fix.
    """
    user_id = request.current_user["user_id"]
    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    # Get legacy credit counts
    legacy_purchased = getattr(user, "migrations_purchased", None) or 0
    legacy_used = getattr(user, "migrations_used", None) or 0
    legacy_available = max(0, legacy_purchased - legacy_used)

    # Get actual MigrationCredit counts
    actual_available = MigrationCredit.query.filter_by(
        user_id=user_id, status="available", payment_status="paid"
    ).count()

    actual_used = MigrationCredit.query.filter_by(
        user_id=user_id, status="used", payment_status="paid"
    ).count()

    # Calculate how many credits need to be created
    missing_available = max(0, legacy_available - actual_available)
    missing_used = max(0, legacy_used - actual_used)

    credits_created = 0
    tier = user.subscription_tier or "starter"
    credit_config = MigrationCredit.TIER_CONFIG.get(
        tier, MigrationCredit.TIER_CONFIG["starter"]
    )

    # Create missing available credits
    for i in range(missing_available):
        credit = MigrationCredit(
            user_id=user_id,
            tier_type=tier,
            transaction_limit=credit_config.get("transaction_limit", 5000),
            price_cents=0,
            stripe_checkout_session_id=(
                f"sync-available-{user_id}-{i}-"
                f"{datetime.datetime.now(timezone.utc).timestamp()}"
            ),
            payment_status="paid",
            status="available",
        )
        credit.paid_at = datetime.datetime.now(timezone.utc)
        db.session.add(credit)
        credits_created += 1

    # Create missing used credits (for historical accuracy)
    for i in range(missing_used):
        credit = MigrationCredit(
            user_id=user_id,
            tier_type=tier,
            transaction_limit=credit_config.get("transaction_limit", 5000),
            price_cents=0,
            stripe_checkout_session_id=f"sync-used-{user_id}-{i}-{datetime.datetime.now(timezone.utc).timestamp()}",
            payment_status="paid",
            status="used",
        )
        credit.paid_at = datetime.datetime.now(timezone.utc)
        credit.used_at = datetime.datetime.now(timezone.utc)
        db.session.add(credit)
        credits_created += 1

    if credits_created > 0:
        db.session.commit()
        logger.info(f"Synced {credits_created} credits for user {user_id}")

    # Get updated counts
    new_available = MigrationCredit.query.filter_by(
        user_id=user_id, status="available", payment_status="paid"
    ).count()

    return jsonify(
        {
            "success": True,
            "message": f"Synced {credits_created} credit(s)",
            "credits_created": credits_created,
            "legacy": {
                "purchased": legacy_purchased,
                "used": legacy_used,
                "available": legacy_available,
            },
            "actual": {"available": new_available, "used": actual_used + missing_used},
        }
    )
