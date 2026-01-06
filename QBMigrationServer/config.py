import os
from datetime import timedelta
import secrets

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
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://qbmigration:changeme@localhost:5432/qbmigration')
    
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
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    
    # S3
    AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET', 'qb-migration-temp-files')
    AWS_S3_ENCRYPTION = 'AES256'
    AWS_S3_FILE_TTL_HOURS = int(os.getenv('S3_FILE_TTL_HOURS', '24'))
    
    # EC2
    AWS_EC2_AMI_ID = os.getenv('AWS_EC2_AMI_ID', 'ami-0c55b159cbfafe1f0')
    AWS_EC2_INSTANCE_TYPE = os.getenv('AWS_EC2_INSTANCE_TYPE', 't3.medium')
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
    
    MIGRATION_METADATA_RETENTION_DAYS = int(os.getenv('MIGRATION_METADATA_RETENTION_DAYS', '90'))
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
    # PAGINATION
    # ============================================================================
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 100
    MAX_OFFSET = 10000


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    RATELIMIT_ENABLED = False
    AUTO_CLEANUP_ENABLED = False
    BACKUP_ENABLED = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'postgresql://test:test@localhost:5432/qbmigration_test'
    RATELIMIT_ENABLED = False
    AUTO_CLEANUP_ENABLED = False
    BACKUP_ENABLED = False
    WTF_CSRF_ENABLED = False


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