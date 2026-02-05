"""
QBMigration Constants
====================
Centralized constants to eliminate magic numbers throughout the codebase.
All numeric values used in multiple places should be defined here.

Categories:
- API Rate Limiting
- Timeouts and Delays
- Size Limits
- Retry Configuration
- Security Parameters
- Database Configuration
- AWS Configuration
- QBO API Limits
"""

from typing import Any, Dict

# =============================================================================
# API RATE LIMITING
# =============================================================================


# Rate limits per endpoint (requests per time window)
class RateLimits:
    """Rate limiting constants for API endpoints"""

    # Auth endpoints
    REGISTER_PER_HOUR = 3
    LOGIN_PER_15_MIN = 5
    PASSWORD_RESET_PER_HOUR = 3

    # General API
    DEFAULT_PER_MINUTE = 100
    UPLOAD_PER_MINUTE = 10
    HEALTH_PER_MINUTE = 60
    DETAILED_HEALTH_PER_MINUTE = 10

    # Webhook endpoints (high volume)
    WEBHOOK_PER_MINUTE = 500

    # Migration endpoints
    MIGRATION_START_PER_HOUR = 10
    MIGRATION_STATUS_PER_MINUTE = 30


# =============================================================================
# TIMEOUTS AND DELAYS
# =============================================================================


class Timeouts:
    """Timeout constants in seconds"""

    # HTTP/Network
    HTTP_CONNECT = 10
    HTTP_READ = 30
    HTTP_TOTAL = 60

    # Database
    DB_QUERY_DEFAULT = 30
    DB_QUERY_LONG_RUNNING = 300
    SQLITE_BUSY_TIMEOUT_MS = 30000

    # AWS Operations
    S3_UPLOAD = 300
    S3_DOWNLOAD = 300
    EC2_STARTUP_MINUTES = 15

    # External APIs
    QBO_API_REQUEST = 60
    WEBHOOK_DELIVERY = 30
    CAPTCHA_VERIFY = 5

    # Background Jobs
    MIGRATION_MAX_HOURS = 24
    BACKUP_OPERATION = 600

    # Session
    SESSION_EXPIRY_HOURS = 24
    JWT_EXPIRY_HOURS = 24
    REFRESH_TOKEN_DAYS = 30


class Delays:
    """Delay/sleep constants in seconds"""

    RATE_LIMIT_BACKOFF = 0.15
    RETRY_BASE_DELAY = 2.0
    RETRY_MAX_DELAY = 60
    WEBHOOK_RETRY_DELAY = 5


# =============================================================================
# SIZE LIMITS
# =============================================================================


class SizeLimits:
    """Size limit constants"""

    # File uploads (in bytes)
    MAX_UPLOAD_SIZE_MB = 100
    MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # Data fields
    MAX_EMAIL_LENGTH = 254
    MAX_NAME_LENGTH = 100
    MAX_COMPANY_LENGTH = 255
    MAX_DESCRIPTION_LENGTH = 4000  # QBO limit for notes/descriptions
    MAX_MEMO_LENGTH = 4000

    # Arrays and collections
    MAX_WEBHOOK_IDS = 50
    MAX_BATCH_SIZE = 30  # QBO batch limit
    MAX_QUERY_RESULTS = 1000  # QBO query limit

    # Logs
    MAX_LOG_MESSAGE_LENGTH = 10000
    MAX_ERROR_MESSAGE_LENGTH = 500


# =============================================================================
# RETRY CONFIGURATION
# =============================================================================


class RetryConfig:
    """Retry configuration constants"""

    MAX_ATTEMPTS = 3
    BACKOFF_BASE = 2.0
    BACKOFF_MAX = 60
    JITTER_ENABLED = True

    # Retryable HTTP status codes
    RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

    # Retryable exception types (as strings for matching)
    RETRYABLE_EXCEPTIONS = frozenset(
        {
            "ConnectionError",
            "Timeout",
            "ChunkedEncodingError",
            "ConnectionResetError",
            "BrokenPipeError",
        }
    )


# =============================================================================
# SECURITY PARAMETERS
# =============================================================================


class Security:
    """Security-related constants"""

    # Password requirements
    MIN_PASSWORD_LENGTH = 8
    MAX_PASSWORD_LENGTH = 128
    BCRYPT_MIN_ROUNDS = 10
    BCRYPT_DEFAULT_ROUNDS = 12

    # Account lockout
    MAX_FAILED_LOGINS = 5
    LOCKOUT_DURATION_MINUTES = 30

    # CAPTCHA
    CAPTCHA_THRESHOLD_ATTEMPTS = 3

    # Token sizes
    CSRF_TOKEN_BYTES = 32
    API_KEY_BYTES = 32
    SESSION_TOKEN_BYTES = 32

    # Encryption
    AES_KEY_BITS = 256
    AES_IV_BYTES = 12  # GCM mode
    AES_TAG_BYTES = 16  # GCM tag

    # Key derivation
    PBKDF2_MIN_ITERATIONS = 10000
    PBKDF2_DEFAULT_ITERATIONS = 100000

    # Secure deletion
    SECURE_DELETE_PASSES = 7


# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================


class Database:
    """Database configuration constants"""

    # Connection pool
    POOL_SIZE_DEFAULT = 10
    POOL_SIZE_MAX = 20
    POOL_OVERFLOW = 10
    POOL_RECYCLE_SECONDS = 1800
    POOL_TIMEOUT_SECONDS = 30

    # Query limits
    MAX_RESULTS_PER_PAGE = 100
    DEFAULT_PAGE_SIZE = 20

    # Cleanup
    DATA_RETENTION_HOURS = 1
    ARCHIVE_RETENTION_YEARS = 7


# =============================================================================
# AWS CONFIGURATION
# =============================================================================


class AWS:
    """AWS-related constants"""

    # Default region
    DEFAULT_REGION = "ca-central-1"  # Montreal - Canadian data residency

    # S3
    S3_ENCRYPTION_ALGORITHM = "AES256"
    S3_FILE_TTL_HOURS = 24
    S3_PRESIGNED_URL_EXPIRY = 3600  # 1 hour
    S3_MULTIPART_THRESHOLD = 8 * 1024 * 1024  # 8MB

    # Secrets Manager
    SECRETS_CACHE_TTL_SECONDS = 300  # 5 minutes


# =============================================================================
# QUICKBOOKS ONLINE API
# =============================================================================


class QBO:
    """QuickBooks Online API constants"""

    # Rate limits
    RATE_LIMIT_PER_MINUTE = 500
    BATCH_SIZE_LIMIT = 30
    QUERY_MAX_RESULTS = 1000
    MAX_FIELD_LENGTH = 4000

    # Plan-specific worker limits
    PLAN_WORKER_LIMITS: Dict[str, int] = {
        "Simple Start": 2,
        "Essentials": 3,
        "Plus": 5,
        "Advanced": 8,
    }

    # Valid plans
    VALID_PLANS = frozenset({"Simple Start", "Essentials", "Plus", "Advanced"})

    # Environments
    VALID_ENVIRONMENTS = frozenset({"sandbox", "production"})

    # Regions
    VALID_REGIONS = frozenset({"US", "CA", "UK", "AU", "IN"})


# =============================================================================
# HTTP STATUS CODES (for clarity)
# =============================================================================


class HTTPStatus:
    """Common HTTP status codes"""

    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504


# =============================================================================
# ERROR CODES
# =============================================================================


class ErrorCodes:
    """Application-specific error codes"""

    # Authentication
    AUTH_INVALID_CREDENTIALS = "AUTH001"
    AUTH_TOKEN_EXPIRED = "AUTH002"
    AUTH_ACCOUNT_LOCKED = "AUTH003"
    AUTH_CAPTCHA_REQUIRED = "AUTH004"

    # Migration
    MIGRATION_INVALID_DATA = "MIG001"
    MIGRATION_QUOTA_EXCEEDED = "MIG002"
    MIGRATION_IN_PROGRESS = "MIG003"
    MIGRATION_FAILED = "MIG004"

    # Upload
    UPLOAD_TOO_LARGE = "UPL001"
    UPLOAD_INVALID_FORMAT = "UPL002"
    UPLOAD_ENCRYPTION_FAILED = "UPL003"

    # QBO
    QBO_AUTH_FAILED = "QBO001"
    QBO_RATE_LIMITED = "QBO002"
    QBO_INVALID_DATA = "QBO003"

    # System
    SYSTEM_MAINTENANCE = "SYS001"
    SYSTEM_OVERLOADED = "SYS002"
    DATABASE_ERROR = "SYS003"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_all_constants() -> Dict[str, Any]:
    """
    Get all constants as a dictionary for debugging/logging.
    Useful for configuration validation.
    """
    return {
        "rate_limits": {
            "register_per_hour": RateLimits.REGISTER_PER_HOUR,
            "login_per_15_min": RateLimits.LOGIN_PER_15_MIN,
            "default_per_minute": RateLimits.DEFAULT_PER_MINUTE,
        },
        "timeouts": {
            "http_connect": Timeouts.HTTP_CONNECT,
            "http_read": Timeouts.HTTP_READ,
            "db_query": Timeouts.DB_QUERY_DEFAULT,
        },
        "size_limits": {
            "max_upload_mb": SizeLimits.MAX_UPLOAD_SIZE_MB,
            "max_batch_size": SizeLimits.MAX_BATCH_SIZE,
        },
        "security": {
            "min_password_length": Security.MIN_PASSWORD_LENGTH,
            "bcrypt_rounds": Security.BCRYPT_DEFAULT_ROUNDS,
            "max_failed_logins": Security.MAX_FAILED_LOGINS,
        },
        "qbo": {
            "batch_size_limit": QBO.BATCH_SIZE_LIMIT,
            "rate_limit_per_minute": QBO.RATE_LIMIT_PER_MINUTE,
        },
    }
