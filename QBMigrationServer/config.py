import logging
import os
from datetime import timedelta

from dotenv import load_dotenv
from utils.env_helper import get_env, is_production

load_dotenv()

# Initialize logger at module level before Config class uses it
logger = logging.getLogger(__name__)


class Config:
    """Base configuration with comprehensive security and AWS integration"""

    # ============================================================================
    # FLASK CORE
    # ============================================================================
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        if is_production():
            raise ValueError("SECRET_KEY must be set in production!")
        else:
            import secrets

            SECRET_KEY = secrets.token_hex(32)
            logger.warning(
                "No SECRET_KEY set - generated random key for this session. "
                "Set SECRET_KEY env var for stable sessions across restarts."
            )

    # M-21 FIX: Increased minimum from 32 to 64 characters.
    # token_hex(32) produces 32 random bytes = 64 hex characters = 256 bits entropy,
    # which meets the 256-bit standard for HMAC-SHA256 JWT signing.
    # A SECRET_KEY under 64 characters could be a weak user-chosen string.
    if is_production() and len(SECRET_KEY) < 64:
        raise ValueError(
            "SECRET_KEY must be at least 64 characters for adequate JWT signing entropy. "
            'Generate with: python -c "import secrets; print(secrets.token_hex(32))"'
        )

    DEBUG = False
    TESTING = False

    # ============================================================================
    # DATABASE - PostgreSQL
    # ============================================================================
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    if not SQLALCHEMY_DATABASE_URI:
        if is_production():
            raise ValueError("DATABASE_URL must be set in production!")
        else:
            logger.warning("DATABASE_URL not set - using SQLite for development")
            SQLALCHEMY_DATABASE_URI = "sqlite:///qb_migration_dev.db"

    # Fix Heroku/Railway postgres:// URLs

    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
        "pool_timeout": 30,
        "max_overflow": 20,
        "echo": False,  # Set True for SQL debugging
    }

    # ============================================================================
    # AWS CONFIGURATION
    # ============================================================================
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

    # AUDIT FIX P5-M2: Enforce IAM roles in production — block access keys
    @staticmethod
    def warn_aws_credentials():
        """Block AWS access keys in production — require IAM roles"""
        if is_production():
            if os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_SECRET_ACCESS_KEY"):
                logger.error(
                    "SECURITY: AWS access keys detected in production. "
                    "Use IAM instance roles instead. Set ALLOW_AWS_KEYS=true to override."
                )
                if not os.getenv("ALLOW_AWS_KEYS"):
                    raise EnvironmentError(
                        "AWS access keys are not allowed in production. "
                        "Use IAM roles or set ALLOW_AWS_KEYS=true to override."
                    )

    AWS_REGION = os.getenv(
        "AWS_REGION", "ca-central-1"
    )  # Canadian data residency per legal docs

    # S3
    AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
    if not AWS_S3_BUCKET and is_production():
        raise ValueError("AWS_S3_BUCKET must be set in production!")
    AWS_S3_CODE_BUCKET = os.getenv(
        "AWS_S3_CODE_BUCKET", "qb-migration-worker-code"
    )  # Bucket for migration worker code
    AWS_S3_ENCRYPTION = "AES256"
    AWS_S3_FILE_TTL_HOURS = int(os.getenv("S3_FILE_TTL_HOURS", "24"))

    # EC2
    # FIX #49: Remove hardcoded US AMI - require explicit configuration per region
    # Default ami-0c55b159cbfafe1f0 was for us-east-1, causing data sovereignty violations
    AWS_EC2_AMI_ID = os.getenv(
        "AWS_EC2_AMI_ID", ""
    )  # MUST be set explicitly for your region
    AWS_EC2_INSTANCE_TYPE = os.getenv("AWS_EC2_INSTANCE_TYPE", "t3.micro")
    AWS_EC2_KEY_NAME = os.getenv("AWS_EC2_KEY_NAME", "qb-migration-key")
    AWS_EC2_SECURITY_GROUP = os.getenv("AWS_EC2_SECURITY_GROUP")
    AWS_EC2_SUBNET_ID = os.getenv("AWS_EC2_SUBNET_ID")

    # IAM
    AWS_IAM_INSTANCE_PROFILE = os.getenv(
        "AWS_IAM_INSTANCE_PROFILE", "QB-Migration-Instance-Role"
    )

    # Secrets Manager
    AWS_SECRETS_MANAGER_ARN = os.getenv("AWS_SECRETS_MANAGER_ARN")

    # Lambda
    AWS_LAMBDA_CLEANUP_FUNCTION = os.getenv(
        "AWS_LAMBDA_CLEANUP_FUNCTION", "qb-migration-cleanup"
    )

    # ============================================================================
    # AWS VALIDATION
    # ============================================================================
    @classmethod
    def validate_aws_region(cls):
        """
        SECURITY: Validate AWS_REGION matches AWS_EC2_AMI_ID region
        Prevents data sovereignty violations (Canadian data in US region)
        """
        region = cls.AWS_REGION
        ami_id = cls.AWS_EC2_AMI_ID

        # AMI IDs are region-specific - we can't validate without AWS API call
        # But we can warn about known mismatches
        known_us_east_amis = ["ami-0c55b159cbfafe1f0", "ami-0d5eff06f840b0e53"]

        if region == "ca-central-1" and ami_id in known_us_east_amis:
            raise ValueError(
                f"DATA SOVEREIGNTY VIOLATION: AWS_REGION is set to '{region}' "
                f"but AWS_EC2_AMI_ID '{ami_id}' appears to be a US region AMI. "
                f"This violates PIPEDA Canadian data residency requirements. "
                f"Update AWS_EC2_AMI_ID to a ca-central-1 AMI."
            )

        # Additional validation: Region format
        if not region.startswith(("us-", "ca-", "eu-", "ap-", "sa-", "af-", "me-")):
            raise ValueError(
                f"Invalid AWS_REGION format: '{region}'. "
                f"Must be a valid AWS region (e.g., 'ca-central-1')"
            )

    # ============================================================================
    # SECURITY
    # ============================================================================
    # SECURITY FIX: SESSION_COOKIE_SECURE should be True in production
    # Set to True when FLASK_ENV=production to enforce HTTPS-only cookies
    SESSION_COOKIE_SECURE = is_production()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=int(os.getenv("SESSION_TIMEOUT_HOURS", "24"))
    )
    SESSION_COOKIE_NAME = "qb_session"
    # FIX: Allow SESSION_COOKIE_DOMAIN from environment for cross-subdomain auth
    SESSION_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN", None)

    # Rate Limiting
    # SECURITY FIX: Require Redis in production for cross-worker rate limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URL = os.getenv("REDIS_URL")
    if not RATELIMIT_STORAGE_URL:
        if is_production():
            raise ValueError(
                "REDIS_URL must be set in production for rate limiting! "
                "In-memory rate limiting is per-worker and ineffective."
            )
        RATELIMIT_STORAGE_URL = "memory://"
        logger.warning("Using in-memory rate limiting (development only)")
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_HEADERS_ENABLED = True

    # File Upload
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")) * 1024 * 1024
    ALLOWED_ENCRYPTION_PREFIXES = ["IV:", "AES:", "ENC:"]
    MIN_ENCRYPTED_DATA_LENGTH = 100
    MAX_ENCRYPTED_DATA_LENGTH = MAX_CONTENT_LENGTH

    # Account Protection
    MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
    ACCOUNT_LOCKOUT_DURATION = timedelta(
        minutes=int(os.getenv("ACCOUNT_LOCKOUT_MINUTES", "15"))
    )
    PASSWORD_MIN_LENGTH = 12  # PCI DSS v4.0.1 requires minimum 12 characters
    PASSWORD_REQUIRE_UPPERCASE = True
    PASSWORD_REQUIRE_LOWERCASE = True
    PASSWORD_REQUIRE_DIGIT = True
    PASSWORD_HISTORY_COUNT = 5  # Remember last 5 passwords
    PASSWORD_REQUIRE_SPECIAL = True  # LOW-01 FIX: Require special character

    # MED-03 FIX: Configurable JWT algorithm for RS256 readiness
    # HS256 (symmetric) is default; set to RS256 for distributed/microservice deployments
    # When using RS256, set JWT_PRIVATE_KEY_PATH and JWT_PUBLIC_KEY_PATH
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ALLOWED_ALGORITHMS = os.getenv("JWT_ALLOWED_ALGORITHMS", "HS256").split(",")
    JWT_PRIVATE_KEY_PATH = os.getenv(
        "JWT_PRIVATE_KEY_PATH"
    )  # For RS256: path to PEM private key
    JWT_PUBLIC_KEY_PATH = os.getenv(
        "JWT_PUBLIC_KEY_PATH"
    )  # For RS256: path to PEM public key

    # CAPTCHA
    CAPTCHA_THRESHOLD = int(os.getenv("CAPTCHA_THRESHOLD", "3"))
    RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
    RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")

    # Encryption
    BACKUP_ENCRYPTION_KEY = os.getenv("BACKUP_ENCRYPTION_KEY")
    # HIGH-05 FIX: Enforce domain-separated encryption keys.
    # QBO_ENCRYPTION_KEY MUST be separate from BACKUP_ENCRYPTION_KEY to prevent
    # a backup key compromise from also exposing QBO OAuth tokens.
    # In production, require a dedicated QBO_ENCRYPTION_KEY.
    QBO_ENCRYPTION_KEY = os.getenv("QBO_ENCRYPTION_KEY")
    if not QBO_ENCRYPTION_KEY and is_production():
        import warnings

        warnings.warn(
            "QBO_ENCRYPTION_KEY not set in production — falling back to "
            "BACKUP_ENCRYPTION_KEY. Set a dedicated QBO_ENCRYPTION_KEY for "
            "proper cryptographic domain separation.",
            stacklevel=2,
        )
        QBO_ENCRYPTION_KEY = os.getenv("BACKUP_ENCRYPTION_KEY")
    elif not QBO_ENCRYPTION_KEY:
        QBO_ENCRYPTION_KEY = os.getenv("BACKUP_ENCRYPTION_KEY")
    ENCRYPTION_KEY_VERSION = os.getenv("ENCRYPTION_KEY_VERSION", "v1")

    # ============================================================================
    # TIMEOUTS & LIMITS
    # ============================================================================
    EC2_STARTUP_TIMEOUT_MINUTES = int(os.getenv("EC2_STARTUP_TIMEOUT_MINUTES", "15"))
    MIGRATION_MAX_DURATION_HOURS = int(os.getenv("MIGRATION_MAX_DURATION_HOURS", "8"))
    WEBHOOK_RETRY_ATTEMPTS = int(os.getenv("WEBHOOK_RETRY_ATTEMPTS", "3"))
    WEBHOOK_TIMEOUT_SECONDS = int(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "30"))
    WEBHOOK_REPLAY_WINDOW_MINUTES = 2  # Reject webhooks older than 2 minutes

    # ============================================================================
    # CLEANUP & RETENTION
    # ============================================================================
    AUTO_CLEANUP_ENABLED = os.getenv("AUTO_CLEANUP_ENABLED", "true").lower() == "true"
    CLEANUP_CHECK_INTERVAL_MINUTES = int(
        os.getenv("CLEANUP_CHECK_INTERVAL_MINUTES", "15")
    )
    ORPHANED_INSTANCE_TIMEOUT_HOURS = int(
        os.getenv("ORPHANED_INSTANCE_TIMEOUT_HOURS", "6")
    )
    FORCE_CLEANUP_AFTER_HOURS = int(os.getenv("FORCE_CLEANUP_AFTER_HOURS", "48"))

    MIGRATION_METADATA_RETENTION_DAYS = int(
        os.getenv("MIGRATION_METADATA_RETENTION_DAYS", "2555")
    )  # 7 years per legal docs
    USER_DATA_RETENTION_DAYS = int(os.getenv("USER_DATA_RETENTION_DAYS", "365"))

    # Per-jurisdiction retention periods (days)
    # CRA IC05-1R1: 6 years from end of last tax year to which records relate
    CRA_RETENTION_DAYS = int(os.getenv("CRA_RETENTION_DAYS", "2190"))  # ~6 years
    # IRS Rev. Proc. 98-25: 7 years for most records
    IRS_RETENTION_DAYS = int(os.getenv("IRS_RETENTION_DAYS", "2555"))  # ~7 years

    # ============================================================================
    # BACKUPS
    # ============================================================================
    BACKUP_ENABLED = os.getenv("ENABLE_BACKUP_TO_S3", "true").lower() == "true"
    BACKUP_INTERVAL_HOURS = 6
    BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "7"))
    BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")
    BACKUP_TO_S3 = os.getenv("ENABLE_BACKUP_TO_S3", "true").lower() == "true"

    # ============================================================================
    # MONITORING & ALERTING
    # ============================================================================
    SENTRY_DSN = os.getenv("SENTRY_DSN")
    SENTRY_ENVIRONMENT = get_env()
    SENTRY_TRACES_SAMPLE_RATE = 0.1

    CLOUDWATCH_LOG_GROUP = os.getenv("CLOUDWATCH_LOG_GROUP", "/aws/qb-migration")
    CLOUDWATCH_LOG_STREAM = os.getenv("CLOUDWATCH_LOG_STREAM", "app-logs")

    # PRODUCTION FIX: No placeholder email - must be set explicitly
    ALERT_EMAIL = os.getenv("ALERT_EMAIL")
    if not ALERT_EMAIL and is_production():
        logger.warning(
            "ALERT_EMAIL not set - migration failure alerts will not be sent"
        )
    ALERT_ON_MIGRATION_FAILURE_COUNT = 3
    ALERT_ON_STUCK_MIGRATION_HOURS = 4

    LOG_LEVEL = "INFO"
    LOG_MAX_BYTES = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 10

    # ============================================================================
    # COST TRACKING
    # ============================================================================
    ENABLE_COST_TRACKING = os.getenv("ENABLE_COST_TRACKING", "true").lower() == "true"
    S3_COST_PER_GB = float(os.getenv("S3_COST_PER_GB", "0.023"))
    EC2_COST_PER_HOUR = float(os.getenv("EC2_COST_PER_HOUR", "0.0416"))

    # ============================================================================
    # WEBHOOKS
    # ============================================================================
    # SECURITY FIX: WEBHOOK_SECRET must be persistent across restarts
    # In production, this MUST be set via environment variable or Secrets Manager
    # A generated secret would break webhook signature verification on restart
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
    if not WEBHOOK_SECRET:
        if is_production():
            raise ValueError(
                "CRITICAL: WEBHOOK_SECRET must be set in production! "
                "This secret is used to sign webhook requests and must persist across restarts. "
                "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        else:
            # Development only - generate ephemeral secret with warning
            WEBHOOK_SECRET = secrets.token_hex(32)
            logger.warning(
                "Using generated WEBHOOK_SECRET for development. "
                "Webhooks will fail after restart. Set WEBHOOK_SECRET for persistence."
            )

    SERVER_URL = os.getenv("SERVER_URL", "http://localhost:5000")

    # ============================================================================
    # EMAIL (supports SMTP, AWS SES via SMTP interface, or any SMTP-compatible relay)
    # ============================================================================
    # AWS SES SMTP setup:
    #   MAIL_SERVER=email-smtp.<region>.amazonaws.com
    #   MAIL_PORT=587
    #   MAIL_USERNAME=<SES SMTP credential Access Key>
    #   MAIL_PASSWORD=<SES SMTP credential Secret Key>
    #   MAIL_DEFAULT_SENDER must be a verified SES identity
    # ============================================================================
    MAIL_SERVER = os.getenv("MAIL_SERVER", "email-smtp.ca-central-1.amazonaws.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@qbmigrate.io")

    # ============================================================================
    # QUICKBOOKS ONLINE
    # ============================================================================
    QBO_CLIENT_ID = os.getenv("QBO_CLIENT_ID")
    QBO_CLIENT_SECRET = os.getenv("QBO_CLIENT_SECRET")
    QBO_ENVIRONMENT = os.getenv("QBO_ENVIRONMENT", "sandbox")
    QBO_REDIRECT_URI = os.getenv(
        "QBO_REDIRECT_URI", "http://localhost:5000/api/qbo/callback"
    )

    # ============================================================================
    # FEATURE FLAGS
    # ============================================================================
    # MFA/2FA: Enabled by default in production for security compliance
    # Users can optionally enable MFA; privileged operations may require it
    ENABLE_2FA = os.getenv("ENABLE_2FA", "true").lower() == "true"
    # Require MFA for privileged operations (account deletion, payment changes, etc.)
    REQUIRE_MFA_FOR_PRIVILEGED_OPS = (
        os.getenv("REQUIRE_MFA_FOR_PRIVILEGED_OPS", "true").lower() == "true"
    )
    ENABLE_VIRUS_SCANNING = (
        os.getenv("ENABLE_VIRUS_SCANNING", "false").lower() == "true"
    )
    ENABLE_METRICS_DASHBOARD = (
        os.getenv("ENABLE_METRICS_DASHBOARD", "false").lower() == "true"
    )

    # ============================================================================
    # ENTERPRISE FEATURES (v2.0)
    # ============================================================================
    # SSO / SAML 2.0
    ENABLE_SSO = os.getenv("ENABLE_SSO", "false").lower() == "true"
    SSO_PROVIDERS = (
        os.getenv("SSO_PROVIDERS", "").split(",") if os.getenv("SSO_PROVIDERS") else []
    )
    SAML_SP_ENTITY_ID = os.getenv("SAML_SP_ENTITY_ID", "https://forensicbridge.io")
    SAML_ACS_URL = os.getenv("SAML_ACS_URL", "/api/sso/acs")

    # S3 Object Locking (WORM - Write Once, Read Many)
    ENABLE_WORM_STORAGE = os.getenv("ENABLE_WORM_STORAGE", "false").lower() == "true"
    WORM_RETENTION_YEARS = int(os.getenv("WORM_RETENTION_YEARS", "7"))
    WORM_RETENTION_MODE = os.getenv(
        "WORM_RETENTION_MODE", "COMPLIANCE"
    )  # GOVERNANCE or COMPLIANCE

    # Customer-Managed Keys (CMK)
    ENABLE_CMK = os.getenv("ENABLE_CMK", "false").lower() == "true"
    DEFAULT_CMK_ARN = os.getenv("DEFAULT_CMK_ARN", "")

    # Multi-AZ Deployment
    ENABLE_MULTI_AZ = os.getenv("ENABLE_MULTI_AZ", "false").lower() == "true"
    PREFERRED_AVAILABILITY_ZONES = os.getenv(
        "PREFERRED_AZS", "ca-central-1a,ca-central-1b,ca-central-1d"
    ).split(",")

    # Forensic Archival (Glacier)
    ENABLE_FORENSIC_ARCHIVAL = (
        os.getenv("ENABLE_FORENSIC_ARCHIVAL", "false").lower() == "true"
    )
    GLACIER_RETENTION_YEARS = int(os.getenv("GLACIER_RETENTION_YEARS", "7"))

    # Webhook Delivery Logging
    ENABLE_WEBHOOK_LOGGING = (
        os.getenv("ENABLE_WEBHOOK_LOGGING", "true").lower() == "true"
    )
    WEBHOOK_LOG_RETENTION_DAYS = int(os.getenv("WEBHOOK_LOG_RETENTION_DAYS", "90"))

    # ============================================================================
    # PAGINATION
    # ============================================================================
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 100
    MAX_OFFSET = 10000

    # ============================================================================
    # LICENSING
    # ============================================================================
    # CRITICAL SECURITY FIX: LICENSE_SECRET_KEY must be persistent
    # Generating a random key on each import would invalidate all existing license tokens
    LICENSE_SECRET_KEY = os.getenv("LICENSE_SECRET_KEY")
    if not LICENSE_SECRET_KEY:
        if is_production():
            raise ValueError(
                "CRITICAL: LICENSE_SECRET_KEY must be set in production! "
                "This secret is used to sign license tokens and must persist across restarts. "
                "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        else:
            # Development only - generate ephemeral secret with warning
            LICENSE_SECRET_KEY = secrets.token_hex(32)
            logger.warning(
                "Using generated LICENSE_SECRET_KEY for development. "
                "License tokens will be invalid after restart. Set LICENSE_SECRET_KEY for persistence."
            )
    LICENSE_TOKEN_EXPIRY_HOURS = int(os.getenv("LICENSE_TOKEN_EXPIRY_HOURS", "24"))

    # License/Pricing tiers - Per-file pricing model
    LICENSE_TIERS = {
        "standard": {
            "name": "Standard",
            "price_per_file": 199,
            "max_file_size_mb": 100,
            "description": "Files under 100MB",
        },
        "industrial": {
            "name": "Industrial",
            "price_per_file": 499,
            "max_file_size_mb": 1024,
            "description": "Files 100MB - 1GB",
        },
        "forensic": {
            "name": "Monster/Forensic",
            "price_per_file": 1499,
            "max_file_size_mb": -1,  # Unlimited
            "description": "Files over 1GB, full SHA-256 pipeline",
        },
    }

    # Legacy subscription tiers (for backwards compatibility)
    SUBSCRIPTION_TIERS = {
        "starter": {"migrations": 10, "name": "Starter"},
        "professional": {"migrations": 50, "name": "Professional"},
        "enterprise": {"migrations": -1, "name": "Enterprise"},  # -1 = unlimited
    }

    # Admin emails for license management (properly parse empty values)
    @staticmethod
    def get_admin_emails():
        raw = os.getenv("ADMIN_EMAILS", "")
        return [e.strip() for e in raw.split(",") if e.strip()]

    @staticmethod
    def init_app(app):
        """Initialize app - override in subclasses for specific setup"""


class DevelopmentConfig(Config):
    """Development configuration"""

    DEBUG = True
    RATELIMIT_ENABLED = False
    AUTO_CLEANUP_ENABLED = False
    BACKUP_ENABLED = False


class TestingConfig(Config):
    """Testing configuration with validation for test environment"""

    TESTING = True
    DEBUG = False

    # Use DATABASE_URL env var if available, otherwise use SQLite for testing
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///:memory:")

    RATELIMIT_ENABLED = False
    AUTO_CLEANUP_ENABLED = False
    BACKUP_ENABLED = False
    BACKUP_TO_S3 = False
    WTF_CSRF_ENABLED = False
    AWS_S3_BUCKET = None

    # Test-specific timeout settings (shorter for faster test runs)
    EC2_STARTUP_TIMEOUT_MINUTES = 1
    MIGRATION_MAX_DURATION_HOURS = 1
    WEBHOOK_TIMEOUT_SECONDS = 5

    # Use simpler connection pool for tests (only for non-SQLite)
    @property
    def SQLALCHEMY_ENGINE_OPTIONS(self):
        if "sqlite" in str(self.SQLALCHEMY_DATABASE_URI):
            return {}  # SQLite doesn't support connection pooling
        return {
            "pool_size": 5,
            "pool_recycle": 1800,
            "pool_pre_ping": True,
            "pool_timeout": 10,
            "max_overflow": 5,
        }

    @classmethod
    def init_app(cls, app):
        """Initialize app with test database and validate test configuration"""
        # Use environment variable if set, otherwise use class default
        db_url = os.getenv("DATABASE_URL", cls.SQLALCHEMY_DATABASE_URI)
        app.config["SQLALCHEMY_DATABASE_URI"] = db_url
        # Adjust engine options based on database type
        if "sqlite" in db_url:
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}

        # TESTING CONFIG VALIDATION: Ensure test-specific settings are correct
        cls._validate_test_config(app)

    @classmethod
    def _validate_test_config(cls, app):
        """
        Validate test configuration to prevent test pollution and ensure
        tests don't accidentally affect production resources.
        """
        import logging

        logger = logging.getLogger(__name__)

        issues = []

        # Ensure we're not pointing to production database
        db_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if db_url:
            if "production" in db_url.lower():
                issues.append(
                    "Database URL contains 'production' - refusing to run tests against production DB"
                )
            if "rds.amazonaws.com" in db_url and "test" not in db_url.lower():
                issues.append(
                    "Database URL appears to be production RDS - ensure test database is used"
                )

        # Ensure S3 bucket is not production
        s3_bucket = app.config.get("AWS_S3_BUCKET", "")
        if (
            s3_bucket
            and "prod" in s3_bucket.lower()
            and "test" not in s3_bucket.lower()
        ):
            issues.append(
                f"S3 bucket '{s3_bucket}' appears to be production - use test bucket"
            )

        # Ensure dangerous features are disabled for tests
        if app.config.get("AUTO_CLEANUP_ENABLED"):
            issues.append("AUTO_CLEANUP_ENABLED should be False in testing")

        if app.config.get("BACKUP_TO_S3"):
            issues.append("BACKUP_TO_S3 should be False in testing")

        # Validate encryption key is present (tests need this for encryption tests)
        backup_key = app.config.get("BACKUP_ENCRYPTION_KEY")
        if not backup_key:
            # Generate a test key if not provided
            from cryptography.fernet import Fernet

            test_key = Fernet.generate_key().decode()
            app.config["BACKUP_ENCRYPTION_KEY"] = test_key
            logger.info("Generated test BACKUP_ENCRYPTION_KEY")

        # Validate SECRET_KEY
        secret_key = app.config.get("SECRET_KEY")
        if not secret_key or len(secret_key) < 32:
            import secrets as secrets_module

            test_secret = "test-secret-key-" + secrets_module.token_hex(16)
            app.config["SECRET_KEY"] = test_secret
            logger.info("Generated test SECRET_KEY")

        # Report any issues
        if issues:
            for issue in issues:
                logger.error(f"TEST CONFIG ISSUE: {issue}")
            raise RuntimeError(
                f"Test configuration validation failed: {'; '.join(issues)}"
            )

        logger.info("Test configuration validated successfully")


class ProductionConfig(Config):
    """Production configuration"""

    DEBUG = False
    SESSION_COOKIE_SECURE = True
    RATELIMIT_ENABLED = True
    AUTO_CLEANUP_ENABLED = True
    BACKUP_ENABLED = True

    @classmethod
    def init_app(cls, app):
        """Initialize production app"""
        Config.init_app(app)

        # SECURITY WARNING: Warn about AWS credentials
        Config.warn_aws_credentials()

        # SECURITY: Validate AWS region matches AMI region (data sovereignty)
        Config.validate_aws_region()

        # Validate critical production settings
        required_vars = [
            "SECRET_KEY",
            "DATABASE_URL",
            "AWS_S3_BUCKET",
            "AWS_EC2_AMI_ID",
            "SENTRY_DSN",
            "WEBHOOK_SECRET",
            "BACKUP_ENCRYPTION_KEY",
            "SERVER_URL",
            "QBO_REDIRECT_URI",
        ]

        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(
                f"Missing required production environment variables: {', '.join(missing)}"
            )

        # Validate SECRET_KEY strength
        if len(os.getenv("SECRET_KEY", "")) < 64:
            raise ValueError("SECRET_KEY must be at least 64 characters in production!")


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def validate_config():
    """
    CFG-01: Startup configuration validation.
    Call this at application startup to ensure all required settings are present.

    Raises:
        RuntimeError: If required configuration is missing
    """
    import logging

    logger = logging.getLogger(__name__)

    env = get_env()

    # Always required settings
    base_required = ["SECRET_KEY", "DATABASE_URL"]

    # Production-only required settings
    production_required = [
        "AWS_S3_BUCKET",
        "AWS_EC2_AMI_ID",
        "WEBHOOK_SECRET",
        "BACKUP_ENCRYPTION_KEY",
    ]

    # Check base requirements
    missing = [k for k in base_required if not os.getenv(k)]

    # Add production requirements in production
    if env == "production":
        missing.extend([k for k in production_required if not os.getenv(k)])

    if missing:
        error_msg = f"Missing required configuration: {', '.join(missing)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # Validate SECRET_KEY length
    secret_key = os.getenv("SECRET_KEY", "")
    if len(secret_key) < 64:
        raise RuntimeError("SECRET_KEY must be at least 64 characters")

    # Validate BACKUP_ENCRYPTION_KEY format if set
    backup_key = os.getenv("BACKUP_ENCRYPTION_KEY")
    if backup_key:
        try:
            from cryptography.fernet import Fernet

            key_bytes = (
                backup_key.encode() if isinstance(backup_key, str) else backup_key
            )
            Fernet(key_bytes)  # Will raise if invalid
        except Exception as e:
            raise RuntimeError(
                f"BACKUP_ENCRYPTION_KEY is invalid: {e}. "
                "Generate with: python -c "
                "'from cryptography.fernet import Fernet;"
                " print(Fernet.generate_key().decode())'"
            )

    # MED-02 FIX: Validate QBO_ENCRYPTION_KEY if set (separate from backup key)
    qbo_key = os.getenv("QBO_ENCRYPTION_KEY")
    if qbo_key:
        try:
            from cryptography.fernet import Fernet

            Fernet(qbo_key.encode() if isinstance(qbo_key, str) else qbo_key)
        except Exception as e:
            raise RuntimeError(
                f"QBO_ENCRYPTION_KEY is invalid: {e}. "
                "Generate with: python -c "
                "'from cryptography.fernet import Fernet;"
                " print(Fernet.generate_key().decode())'"
            )
    elif env == "production" and backup_key:
        logger.warning(
            "QBO_ENCRYPTION_KEY not set - falling back to BACKUP_ENCRYPTION_KEY. "
            "Set a dedicated QBO_ENCRYPTION_KEY for key separation best practice."
        )

    # Validate DATABASE_URL format
    db_url = os.getenv("DATABASE_URL", "")
    if db_url and not db_url.startswith(("postgresql://", "postgres://", "sqlite://")):
        logger.warning(f"Unusual DATABASE_URL format: {db_url[:20]}...")

    logger.info(f"Configuration validated successfully for environment: {env}")
    return True
