import os
from datetime import timedelta
import secrets
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration with comprehensive security and AWS integration"""
    
    # ============================================================================
    # FLASK CORE
    # ============================================================================
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        if os.getenv('FLASK_ENV') == 'production':
            raise ValueError("SECRET_KEY must be set in production!")
        else:
            SECRET_KEY = 'dev-secret-key-CHANGE-IN-PRODUCTION-' + secrets.token_hex(16)
            print("⚠️  WARNING: Using generated SECRET_KEY for development")
    
    if len(SECRET_KEY) < 32:
        raise ValueError("SECRET_KEY must be at least 32 characters!")
    
    DEBUG = False
    TESTING = False
    
    # ============================================================================
    # DATABASE - PostgreSQL
    # ============================================================================
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        print("❌ ERROR: DATABASE_URL not found in environment!")
    
    # Fix Heroku/Railway postgres:// URLs

    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'pool_timeout': 30,
        'max_overflow': 20,
        'echo': False  # Set True for SQL debugging
    }
    
    # ============================================================================
    # AWS CONFIGURATION
    # ============================================================================
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

    # SECURITY WARNING: Check if using access keys in production
    @staticmethod
    def warn_aws_credentials():
        """Warn if using AWS access keys instead of IAM roles in production"""
        if os.getenv('FLASK_ENV') == 'production':
            if os.getenv('AWS_ACCESS_KEY_ID') or os.getenv('AWS_SECRET_ACCESS_KEY'):
                import warnings
                warnings.warn(
                    "⚠️  SECURITY WARNING: Using AWS access keys in production. "
                    "Consider using IAM roles instead for better security.",
                    UserWarning
                )

    AWS_REGION = os.getenv('AWS_REGION', 'ca-central-1')  # Canadian data residency per legal docs
    
    # S3
    AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET', 'qb-migration-temp-files')
    AWS_S3_CODE_BUCKET = os.getenv('AWS_S3_CODE_BUCKET', 'qb-migration-worker-code')  # Bucket for migration worker code
    AWS_S3_ENCRYPTION = 'AES256'
    AWS_S3_FILE_TTL_HOURS = int(os.getenv('S3_FILE_TTL_HOURS', '24'))
    
    # EC2
    AWS_EC2_AMI_ID = os.getenv('AWS_EC2_AMI_ID', 'ami-0c55b159cbfafe1f0')
    AWS_EC2_INSTANCE_TYPE = os.getenv('AWS_EC2_INSTANCE_TYPE', 't3.micro')
    AWS_EC2_KEY_NAME = os.getenv('AWS_EC2_KEY_NAME', 'qb-migration-key')
    AWS_EC2_SECURITY_GROUP = os.getenv('AWS_EC2_SECURITY_GROUP')
    AWS_EC2_SUBNET_ID = os.getenv('AWS_EC2_SUBNET_ID')
    
    # IAM
    AWS_IAM_INSTANCE_PROFILE = os.getenv('AWS_IAM_INSTANCE_PROFILE', 'QB-Migration-Instance-Role')
    
    # Secrets Manager
    AWS_SECRETS_MANAGER_ARN = os.getenv('AWS_SECRETS_MANAGER_ARN')
    
    # Lambda
    AWS_LAMBDA_CLEANUP_FUNCTION = os.getenv('AWS_LAMBDA_CLEANUP_FUNCTION', 'qb-migration-cleanup')

    # ============================================================================
    # AWS VALIDATION
    # ============================================================================
    @classmethod
    def validate_aws_region(cls):
        """
        SECURITY: Validate AWS_REGION matches AWS_EC2_AMI_ID region
        Prevents data sovereignty violations (Canadian data in US region)
        """
        import warnings

        region = cls.AWS_REGION
        ami_id = cls.AWS_EC2_AMI_ID

        # AMI IDs are region-specific - we can't validate without AWS API call
        # But we can warn about known mismatches
        known_us_east_amis = ['ami-0c55b159cbfafe1f0', 'ami-0d5eff06f840b0e53']

        if region == 'ca-central-1' and ami_id in known_us_east_amis:
            warnings.warn(
                f"⚠️  DATA SOVEREIGNTY WARNING: AWS_REGION is set to '{region}' "
                f"but AWS_EC2_AMI_ID '{ami_id}' appears to be a US region AMI. "
                f"This violates PIPEDA Canadian data residency requirements. "
                f"Update AWS_EC2_AMI_ID to a ca-central-1 AMI.",
                UserWarning
            )

        # Additional validation: Region format
        if not region.startswith(('us-', 'ca-', 'eu-', 'ap-', 'sa-', 'af-', 'me-')):
            raise ValueError(
                f"Invalid AWS_REGION format: '{region}'. "
                f"Must be a valid AWS region (e.g., 'ca-central-1')"
            )

    # ============================================================================
    # SECURITY
    # ============================================================================
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv('SESSION_TIMEOUT_HOURS', '24')))
    SESSION_COOKIE_NAME = 'qb_session'
    
    # Rate Limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'memory://')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True
    
    # File Upload
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_UPLOAD_SIZE_MB', '50')) * 1024 * 1024
    ALLOWED_ENCRYPTION_PREFIXES = ['IV:', 'AES:', 'ENC:']
    MIN_ENCRYPTED_DATA_LENGTH = 100
    MAX_ENCRYPTED_DATA_LENGTH = MAX_CONTENT_LENGTH
    
    # Account Protection
    MAX_LOGIN_ATTEMPTS = int(os.getenv('MAX_LOGIN_ATTEMPTS', '5'))
    ACCOUNT_LOCKOUT_DURATION = timedelta(minutes=int(os.getenv('ACCOUNT_LOCKOUT_MINUTES', '15')))
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_REQUIRE_UPPERCASE = True
    PASSWORD_REQUIRE_LOWERCASE = True
    PASSWORD_REQUIRE_DIGIT = True
    PASSWORD_HISTORY_COUNT = 5  # Remember last 5 passwords
    
    # CAPTCHA
    CAPTCHA_THRESHOLD = int(os.getenv('CAPTCHA_THRESHOLD', '3'))
    RECAPTCHA_SITE_KEY = os.getenv('RECAPTCHA_SITE_KEY')
    RECAPTCHA_SECRET_KEY = os.getenv('RECAPTCHA_SECRET_KEY')
    
    # Encryption
    BACKUP_ENCRYPTION_KEY = os.getenv('BACKUP_ENCRYPTION_KEY')
    ENCRYPTION_KEY_VERSION = os.getenv('ENCRYPTION_KEY_VERSION', 'v1')
    
    # ============================================================================
    # TIMEOUTS & LIMITS
    # ============================================================================
    EC2_STARTUP_TIMEOUT_MINUTES = int(os.getenv('EC2_STARTUP_TIMEOUT_MINUTES', '15'))
    MIGRATION_MAX_DURATION_HOURS = int(os.getenv('MIGRATION_MAX_DURATION_HOURS', '8'))
    WEBHOOK_RETRY_ATTEMPTS = int(os.getenv('WEBHOOK_RETRY_ATTEMPTS', '3'))
    WEBHOOK_TIMEOUT_SECONDS = int(os.getenv('WEBHOOK_TIMEOUT_SECONDS', '30'))
    WEBHOOK_REPLAY_WINDOW_MINUTES = 5  # Reject webhooks older than 5 minutes
    
    # ============================================================================
    # CLEANUP & RETENTION
    # ============================================================================
    AUTO_CLEANUP_ENABLED = os.getenv('AUTO_CLEANUP_ENABLED', 'true').lower() == 'true'
    CLEANUP_CHECK_INTERVAL_MINUTES = int(os.getenv('CLEANUP_CHECK_INTERVAL_MINUTES', '15'))
    ORPHANED_INSTANCE_TIMEOUT_HOURS = int(os.getenv('ORPHANED_INSTANCE_TIMEOUT_HOURS', '6'))
    FORCE_CLEANUP_AFTER_HOURS = int(os.getenv('FORCE_CLEANUP_AFTER_HOURS', '48'))
    
    MIGRATION_METADATA_RETENTION_DAYS = int(os.getenv('MIGRATION_METADATA_RETENTION_DAYS', '2555'))  # 7 years per legal docs
    USER_DATA_RETENTION_DAYS = int(os.getenv('USER_DATA_RETENTION_DAYS', '365'))
    
    # ============================================================================
    # BACKUPS
    # ============================================================================
    BACKUP_ENABLED = os.getenv('ENABLE_BACKUP_TO_S3', 'true').lower() == 'true'
    BACKUP_INTERVAL_HOURS = 6
    BACKUP_RETENTION_DAYS = int(os.getenv('BACKUP_RETENTION_DAYS', '7'))
    BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backups')
    BACKUP_TO_S3 = os.getenv('ENABLE_BACKUP_TO_S3', 'true').lower() == 'true'
    
    # ============================================================================
    # MONITORING & ALERTING
    # ============================================================================
    SENTRY_DSN = os.getenv('SENTRY_DSN')
    SENTRY_ENVIRONMENT = os.getenv('FLASK_ENV', 'development')
    SENTRY_TRACES_SAMPLE_RATE = 0.1
    
    CLOUDWATCH_LOG_GROUP = os.getenv('CLOUDWATCH_LOG_GROUP', '/aws/qb-migration')
    CLOUDWATCH_LOG_STREAM = os.getenv('CLOUDWATCH_LOG_STREAM', 'app-logs')
    
    ALERT_EMAIL = os.getenv('ALERT_EMAIL', 'admin@yourcompany.com')
    ALERT_ON_MIGRATION_FAILURE_COUNT = 3
    ALERT_ON_STUCK_MIGRATION_HOURS = 4
    
    LOG_LEVEL = 'INFO'
    LOG_MAX_BYTES = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 10
    
    # ============================================================================
    # COST TRACKING
    # ============================================================================
    ENABLE_COST_TRACKING = os.getenv('ENABLE_COST_TRACKING', 'true').lower() == 'true'
    S3_COST_PER_GB = float(os.getenv('S3_COST_PER_GB', '0.023'))
    EC2_COST_PER_HOUR = float(os.getenv('EC2_COST_PER_HOUR', '0.0416'))
    
    # ============================================================================
    # WEBHOOKS
    # ============================================================================
    WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', secrets.token_hex(32))
    SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:5000')
    
    # ============================================================================
    # EMAIL
    # ============================================================================
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@qbmigrate.io')
    
    # ============================================================================
    # QUICKBOOKS ONLINE
    # ============================================================================
    QBO_CLIENT_ID = os.getenv('QBO_CLIENT_ID')
    QBO_CLIENT_SECRET = os.getenv('QBO_CLIENT_SECRET')
    QBO_ENVIRONMENT = os.getenv('QBO_ENVIRONMENT', 'sandbox')
    QBO_REDIRECT_URI = os.getenv('QBO_REDIRECT_URI', 'http://localhost:5000/api/qbo/callback')
    
    # ============================================================================
    # FEATURE FLAGS
    # ============================================================================
    ENABLE_2FA = os.getenv('ENABLE_2FA', 'false').lower() == 'true'
    ENABLE_VIRUS_SCANNING = os.getenv('ENABLE_VIRUS_SCANNING', 'false').lower() == 'true'
    ENABLE_METRICS_DASHBOARD = os.getenv('ENABLE_METRICS_DASHBOARD', 'false').lower() == 'true'
    
    # ============================================================================
    # ENTERPRISE FEATURES (v2.0)
    # ============================================================================
    # SSO / SAML 2.0
    ENABLE_SSO = os.getenv('ENABLE_SSO', 'false').lower() == 'true'
    SSO_PROVIDERS = os.getenv('SSO_PROVIDERS', '').split(',') if os.getenv('SSO_PROVIDERS') else []
    SAML_SP_ENTITY_ID = os.getenv('SAML_SP_ENTITY_ID', 'https://forensicbridge.io')
    SAML_ACS_URL = os.getenv('SAML_ACS_URL', '/api/sso/acs')
    
    # S3 Object Locking (WORM - Write Once, Read Many)
    ENABLE_WORM_STORAGE = os.getenv('ENABLE_WORM_STORAGE', 'false').lower() == 'true'
    WORM_RETENTION_YEARS = int(os.getenv('WORM_RETENTION_YEARS', '7'))
    WORM_RETENTION_MODE = os.getenv('WORM_RETENTION_MODE', 'COMPLIANCE')  # GOVERNANCE or COMPLIANCE
    
    # Customer-Managed Keys (CMK)
    ENABLE_CMK = os.getenv('ENABLE_CMK', 'false').lower() == 'true'
    DEFAULT_CMK_ARN = os.getenv('DEFAULT_CMK_ARN', '')
    
    # Multi-AZ Deployment
    ENABLE_MULTI_AZ = os.getenv('ENABLE_MULTI_AZ', 'false').lower() == 'true'
    PREFERRED_AVAILABILITY_ZONES = os.getenv('PREFERRED_AZS', 'ca-central-1a,ca-central-1b,ca-central-1d').split(',')
    
    # Forensic Archival (Glacier)
    ENABLE_FORENSIC_ARCHIVAL = os.getenv('ENABLE_FORENSIC_ARCHIVAL', 'false').lower() == 'true'
    GLACIER_RETENTION_YEARS = int(os.getenv('GLACIER_RETENTION_YEARS', '7'))
    
    # Webhook Delivery Logging
    ENABLE_WEBHOOK_LOGGING = os.getenv('ENABLE_WEBHOOK_LOGGING', 'true').lower() == 'true'
    WEBHOOK_LOG_RETENTION_DAYS = int(os.getenv('WEBHOOK_LOG_RETENTION_DAYS', '90'))
    
    # ============================================================================
    # PAGINATION
    # ============================================================================
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 100
    MAX_OFFSET = 10000
    
    # ============================================================================
    # LICENSING
    # ============================================================================
    LICENSE_SECRET_KEY = os.getenv('LICENSE_SECRET_KEY', secrets.token_hex(32))
    LICENSE_TOKEN_EXPIRY_HOURS = int(os.getenv('LICENSE_TOKEN_EXPIRY_HOURS', '24'))
    
    # License/Pricing tiers - Per-file pricing model
    LICENSE_TIERS = {
        'standard': {
            'name': 'Standard',
            'price_per_file': 199,
            'max_file_size_mb': 100,
            'description': 'Files under 100MB'
        },
        'industrial': {
            'name': 'Industrial', 
            'price_per_file': 499,
            'max_file_size_mb': 1024,
            'description': 'Files 100MB - 1GB'
        },
        'forensic': {
            'name': 'Monster/Forensic',
            'price_per_file': 1499,
            'max_file_size_mb': -1,  # Unlimited
            'description': 'Files over 1GB, full SHA-256 pipeline'
        }
    }
    
    # Legacy subscription tiers (for backwards compatibility)
    SUBSCRIPTION_TIERS = {
        'starter': {'migrations': 10, 'name': 'Starter'},
        'professional': {'migrations': 50, 'name': 'Professional'},
        'enterprise': {'migrations': -1, 'name': 'Enterprise'}  # -1 = unlimited
    }
    
    # Admin emails for license management (properly parse empty values)
    @staticmethod
    def get_admin_emails():
        raw = os.getenv('ADMIN_EMAILS', '')
        return [e.strip() for e in raw.split(',') if e.strip()]
    
    @staticmethod
    def init_app(app):
        """Initialize app - override in subclasses for specific setup"""
        pass


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    RATELIMIT_ENABLED = False
    AUTO_CLEANUP_ENABLED = False
    BACKUP_ENABLED = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = False
    
    # CRITICAL: Override the database URI directly as class attribute
    # This MUST be set here, not in init_app, because the parent class
    # already sets SQLALCHEMY_DATABASE_URI from DATABASE_URL env var
    SQLALCHEMY_DATABASE_URI = 'postgresql://qbmigration:TestPass123@localhost:5432/qbmigration_test'
    
    RATELIMIT_ENABLED = False
    AUTO_CLEANUP_ENABLED = False
    BACKUP_ENABLED = False
    BACKUP_TO_S3 = False
    WTF_CSRF_ENABLED = False
    AWS_S3_BUCKET = None
    
    # Use simpler connection pool for tests
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'pool_recycle': 1800,
        'pool_pre_ping': True,
        'pool_timeout': 10,
        'max_overflow': 5,
    }
    
    @classmethod
    def init_app(cls, app):
        """Initialize app with test database"""
        # Ensure the test database URI is set (belt and suspenders)
        app.config['SQLALCHEMY_DATABASE_URI'] = cls.SQLALCHEMY_DATABASE_URI


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
            'SECRET_KEY',
            'DATABASE_URL',
            'AWS_S3_BUCKET',
            'AWS_EC2_AMI_ID',
            'SENTRY_DSN',
            'WEBHOOK_SECRET',
            'BACKUP_ENCRYPTION_KEY'
        ]

        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required production environment variables: {', '.join(missing)}")

        # Validate SECRET_KEY strength
        if len(os.getenv('SECRET_KEY', '')) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production!")


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}