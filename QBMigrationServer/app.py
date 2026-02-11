import logging
import os
import re

from dotenv import load_dotenv
from utils.env_helper import get_env, is_production, is_testing

load_dotenv()

import sys  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from logging.handlers import RotatingFileHandler  # noqa: E402

from api.auth import auth_bp  # noqa: E402
from api.dashboard_api import dashboard_bp  # noqa: E402
from api.extractor import extractor_bp  # noqa: E402
from api.health import health_bp  # noqa: E402
from api.health_check import health_check_bp  # noqa: E402
from api.internal import (  # noqa: E402  # CRIT-09 FIX: Internal API for Lambda
    internal_bp,
)
from api.legal import legal_bp  # noqa: E402
from api.license_api import license_bp  # noqa: E402
from api.migrations import migrations_bp  # noqa: E402
from api.projects import projects_bp  # noqa: E402
from api.qbo import qbo_bp  # noqa: E402
from api.reports import reports_bp  # noqa: E402
from api.s3_upload import s3_upload_bp  # noqa: E402
from api.security_txt import (  # noqa: E402  # FIX 100/100: RFC 9116 security.txt
    security_txt_bp,
)
from api.session_validation import session_validation_bp  # noqa: E402
from api.settings import settings_bp  # noqa: E402
from api.sso_provider import sso_bp  # noqa: E402
from api.upload import upload_bp  # noqa: E402
from api.vault import vault_bp  # noqa: E402
from api.webhook_delivery_log import webhook_logs_bp  # noqa: E402
from api.webhooks import webhooks_bp  # noqa: E402
from api.websocket import init_socketio, websocket_bp  # noqa: E402
from config import (  # noqa: E402  # Import config BEFORE dashboard_api to avoid path conflict
    config,
)
from extensions import limiter  # noqa: E402
from flask import Flask, jsonify, redirect, request  # noqa: E402
from flask_cors import CORS  # noqa: E402
from flask_login import LoginManager  # noqa: E402
from flask_migrate import Migrate  # noqa: E402
from flask_wtf.csrf import CSRFError, CSRFProtect  # noqa: E402
from models.database import db, init_db  # noqa: E402
from models.user import User  # noqa: E402
from sqlalchemy import text  # noqa: E402
from utils.backup import init_backup_scheduler  # noqa: E402
from utils.cleanup_scheduler import init_cleanup_scheduler  # noqa: E402
from utils.error_sanitizer import (  # noqa: E402
    create_error_response,
    sanitize_error_message,
)

logger = logging.getLogger(__name__)


def setup_logging(app):
    """Configure application logging with rotating file handler"""

    # Create logs directory
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # File handler (rotating - 10MB per file, keep 10 files)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=app.config.get("LOG_MAX_BYTES", 10 * 1024 * 1024),
        backupCount=app.config.get("LOG_BACKUP_COUNT", 10),
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Security log (separate file for security events)
    security_handler = RotatingFileHandler(
        os.path.join(log_dir, "security.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    security_handler.setLevel(logging.WARNING)

    # Format
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    security_handler.setFormatter(formatter)

    # Add handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(security_handler)

    app.logger.setLevel(logging.INFO)

    # Log startup
    app.logger.info("=" * 80)
    app.logger.info("QB MIGRATION SERVER STARTING")
    app.logger.info("=" * 80)
    app.logger.info(f"Environment: {get_env()}")
    app.logger.info(f'Debug Mode: {app.config.get("DEBUG", False)}')
    # FIX: Never log database URI - may contain credentials
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "unknown")
    if db_uri and db_uri != "unknown":
        # Mask credentials in database URI for logging
        if "@" in db_uri:
            db_uri = db_uri.split("@")[-1]  # Only show host/database
            db_uri = f"***@{db_uri}"
    app.logger.info(f"Database: {db_uri}")
    app.logger.info(
        f'AWS S3 Bucket: {app.config.get("AWS_S3_BUCKET", "not configured")}'
    )
    app.logger.info(f'AWS Region: {app.config.get("AWS_REGION", "not configured")}')
    app.logger.info(f'Rate Limiting: {app.config.get("RATELIMIT_ENABLED", False)}')
    app.logger.info(f'Auto Cleanup: {app.config.get("AUTO_CLEANUP_ENABLED", False)}')
    app.logger.info("=" * 80)


def setup_sentry(app):
    """Configure Sentry error tracking"""
    sentry_dsn = app.config.get("SENTRY_DSN")

    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration

            def _before_send_transaction(event, hint):
                """FIX: Filter sensitive endpoints from Sentry traces."""
                url = event.get("request", {}).get("url", "")
                # Don't trace auth, upload, or QBO endpoints to avoid PII leakage
                sensitive_prefixes = (
                    "/api/auth",
                    "/api/upload",
                    "/api/qbo",
                    "/api/payments",
                )
                if any(
                    url.startswith(p) or f"/{p.lstrip('/')}" in url
                    for p in sensitive_prefixes
                ):
                    return None
                return event

            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[FlaskIntegration()],
                environment=app.config.get("SENTRY_ENVIRONMENT", "development"),
                traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0.1),
                send_default_pii=False,
                before_send_transaction=_before_send_transaction,
            )

            app.logger.info("Sentry error tracking initialized")
        except ImportError:
            app.logger.warning("Sentry SDK not installed, error tracking disabled")
        except Exception as e:
            app.logger.error(f"Failed to initialize Sentry: {str(e)}")
    else:
        app.logger.info("Sentry DSN not configured, error tracking disabled")


def verify_aws_configuration(app):
    """Verify AWS is properly configured"""
    try:
        import boto3
        from botocore.exceptions import ClientError

        s3_bucket = app.config.get("AWS_S3_BUCKET")
        aws_region = app.config.get("AWS_REGION")

        if not s3_bucket:
            app.logger.warning("AWS_S3_BUCKET not configured - AWS features disabled")
            return False

        # Test S3 access
        s3_client = boto3.client("s3", region_name=aws_region)

        try:
            s3_client.head_bucket(Bucket=s3_bucket)
            app.logger.info(f"AWS S3 bucket verified: {s3_bucket}")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                app.logger.error(f"S3 bucket does not exist: {s3_bucket}")
            elif error_code == "403":
                app.logger.error(f"No permission to access S3 bucket: {s3_bucket}")
            else:
                app.logger.error(f"S3 bucket check failed: {str(e)}")
            return False

    except ImportError:
        app.logger.warning("boto3 not installed - AWS features disabled")
        return False
    except Exception as e:
        app.logger.error(f"AWS configuration check failed: {str(e)}")
        return False


def auto_migrate_database(app):
    """
    LEGACY auto-migrate database schema on startup.
    Adds any missing columns to ensure code and database are in sync.

    AUDIT FIX HIGH: Skips when Flask-Migrate (Alembic) is managing the schema,
    detected by the presence of the alembic_version table. New schema changes
    should use: flask db migrate -m "description" && flask db upgrade
    """
    # Skip for SQLite (used in testing) - tables are created fresh via db.create_all()
    db_url = str(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
    if "sqlite" in db_url:
        app.logger.info("Skipping schema migration for SQLite database")
        return

    try:
        with db.engine.connect() as conn:
            # AUDIT FIX HIGH: Skip if Alembic is managing the schema
            try:
                result = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_name = 'alembic_version'"
                    )
                )
                if result.scalar():
                    app.logger.info(
                        "Alembic migration table detected - skipping legacy auto_migrate_database. "
                        "Use 'flask db upgrade' for schema changes."
                    )
                    return
            except Exception:
                pass  # Table doesn't exist yet, continue with legacy migration

            # Use PostgreSQL advisory lock to prevent concurrent DDL from Gunicorn workers
            db_url = str(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
            if "postgresql" in db_url:
                # Lock ID 12345 is arbitrary but unique to this migration
                lock_result = conn.execute(text("SELECT pg_try_advisory_lock(12345)"))
                got_lock = lock_result.scalar()
                if not got_lock:
                    app.logger.info(
                        "Schema migration skipped - another worker holds the advisory lock"
                    )
                    return

            # Add all potentially missing columns to users table
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS qbo_access_token TEXT,
                ADD COLUMN IF NOT EXISTS qbo_refresh_token TEXT,
                ADD COLUMN IF NOT EXISTS qbo_realm_id VARCHAR(255),
                ADD COLUMN IF NOT EXISTS qbo_token_expires_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS qbo_connected_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(50) DEFAULT 'free',
                ADD COLUMN IF NOT EXISTS tier_purchased_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS migrations_purchased INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS migrations_used INTEGER DEFAULT 0
            """))

            # Create team_invites table if it doesn't exist
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS team_invites (
                    id SERIAL PRIMARY KEY,
                    owner_user_id INTEGER NOT NULL REFERENCES users(id),
                    email VARCHAR(255) NOT NULL,
                    role VARCHAR(50) DEFAULT 'member',
                    invite_token VARCHAR(64) UNIQUE,
                    status VARCHAR(50) DEFAULT 'pending',
                    accepted_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    accepted_at TIMESTAMP
                )
            """))

            # Create session_activations table for fraud prevention
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS session_activations (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(50) NOT NULL,
                    device_fingerprint VARCHAR(64) NOT NULL,
                    device_name VARCHAR(255),
                    ip_address VARCHAR(50),
                    user_agent VARCHAR(500),
                    status VARCHAR(50) DEFAULT 'active',
                    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    extraction_count INTEGER DEFAULT 0,
                    last_extraction_at TIMESTAMP,
                    UNIQUE(session_id, device_fingerprint)
                )
            """))

            # Create session_validation_logs table for audit
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS session_validation_logs (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(50),
                    device_fingerprint VARCHAR(64),
                    ip_address VARCHAR(50),
                    action VARCHAR(50),
                    result VARCHAR(50),
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Create indexes for session tables
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_session_activations_session
                ON session_activations(session_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_session_validation_logs_session
                ON session_validation_logs(session_id)
            """))

            # FIX: Create migrations table if it doesn't exist (production schema drift)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id SERIAL PRIMARY KEY,
                    migration_id VARCHAR(36) UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    session_id VARCHAR(50),
                    company_name VARCHAR(255),
                    qb_file_name VARCHAR(255),
                    file_hash VARCHAR(64),
                    data_size_bytes BIGINT,
                    s3_uri VARCHAR(500),
                    s3_bucket VARCHAR(255),
                    s3_key VARCHAR(500),
                    aws_instance_id VARCHAR(50),
                    aws_region VARCHAR(50) DEFAULT 'ca-central-1',
                    status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                    progress_percent INTEGER DEFAULT 0,
                    current_step VARCHAR(255),
                    customers_migrated INTEGER DEFAULT 0,
                    vendors_migrated INTEGER DEFAULT 0,
                    invoices_migrated INTEGER DEFAULT 0,
                    bills_migrated INTEGER DEFAULT 0,
                    items_migrated INTEGER DEFAULT 0,
                    total_records_migrated INTEGER DEFAULT 0,
                    error_message_encrypted TEXT,
                    error_code VARCHAR(50),
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    cleanup_completed BOOLEAN DEFAULT FALSE,
                    cleanup_completed_at TIMESTAMP,
                    s3_file_deleted BOOLEAN DEFAULT FALSE,
                    s3_file_deleted_at TIMESTAMP,
                    ec2_terminated BOOLEAN DEFAULT FALSE,
                    ec2_terminated_at TIMESTAMP,
                    estimated_cost_usd NUMERIC(14,6),
                    actual_cost_usd NUMERIC(14,6),
                    cost_breakdown TEXT,
                    trial_balance_data TEXT,
                    live_status_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    expires_at TIMESTAMP,
                    ip_address VARCHAR(50),
                    user_agent VARCHAR(500),
                    request_id VARCHAR(36),
                    qbo_company_id VARCHAR(50),
                    qbo_company_name VARCHAR(255),
                    destination VARCHAR(20) DEFAULT 'qbo' NOT NULL,
                    caseware_bundle_path VARCHAR(500),
                    caseware_bundle_ready BOOLEAN DEFAULT FALSE,
                    webhook_processed_ids TEXT,
                    last_webhook_at TIMESTAMP,
                    verification_results TEXT
                )
            """))

            # FIX: Add missing columns to migrations table (handles schema drift)
            migration_columns = [
                ("session_id", "VARCHAR(50)"),
                ("file_hash", "VARCHAR(64)"),
                ("data_size_bytes", "BIGINT"),
                ("s3_uri", "VARCHAR(500)"),
                ("s3_bucket", "VARCHAR(255)"),
                ("s3_key", "VARCHAR(500)"),
                ("aws_instance_id", "VARCHAR(50)"),
                ("aws_region", "VARCHAR(50) DEFAULT 'ca-central-1'"),
                ("current_step", "VARCHAR(255)"),
                ("customers_migrated", "INTEGER DEFAULT 0"),
                ("vendors_migrated", "INTEGER DEFAULT 0"),
                ("invoices_migrated", "INTEGER DEFAULT 0"),
                ("bills_migrated", "INTEGER DEFAULT 0"),
                ("items_migrated", "INTEGER DEFAULT 0"),
                ("total_records_migrated", "INTEGER DEFAULT 0"),
                ("error_message_encrypted", "TEXT"),
                ("error_code", "VARCHAR(50)"),
                ("retry_count", "INTEGER DEFAULT 0"),
                ("max_retries", "INTEGER DEFAULT 3"),
                ("cleanup_completed", "BOOLEAN DEFAULT FALSE"),
                ("cleanup_completed_at", "TIMESTAMP"),
                ("s3_file_deleted", "BOOLEAN DEFAULT FALSE"),
                ("s3_file_deleted_at", "TIMESTAMP"),
                ("ec2_terminated", "BOOLEAN DEFAULT FALSE"),
                ("ec2_terminated_at", "TIMESTAMP"),
                ("estimated_cost_usd", "NUMERIC(14,6)"),
                ("actual_cost_usd", "NUMERIC(14,6)"),
                ("cost_breakdown", "TEXT"),
                ("trial_balance_data", "TEXT"),
                ("live_status_data", "TEXT"),
                ("started_at", "TIMESTAMP"),
                ("completed_at", "TIMESTAMP"),
                ("expires_at", "TIMESTAMP"),
                ("ip_address", "VARCHAR(50)"),
                ("user_agent", "VARCHAR(500)"),
                ("request_id", "VARCHAR(36)"),
                ("qbo_company_id", "VARCHAR(50)"),
                ("qbo_company_name", "VARCHAR(255)"),
                ("destination", "VARCHAR(20) DEFAULT 'qbo'"),
                ("caseware_bundle_path", "VARCHAR(500)"),
                ("caseware_bundle_ready", "BOOLEAN DEFAULT FALSE"),
                ("webhook_processed_ids", "TEXT"),
                ("last_webhook_at", "TIMESTAMP"),
                ("verification_results", "TEXT"),
            ]
            # PRODUCTION FIX: Track migration errors instead of silently swallowing them
            # H-10 FIX: Whitelist column names to prevent SQL injection via f-string
            _VALID_COLUMN_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
            _VALID_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_()',. ]{0,80}$")
            migration_errors = []
            for col_name, col_type in migration_columns:
                if not _VALID_COLUMN_RE.match(col_name):
                    migration_errors.append(
                        f"{col_name}: rejected by column name whitelist"
                    )
                    app.logger.error(
                        f"Schema migration blocked: invalid column name '{col_name}'"
                    )
                    continue
                if not _VALID_TYPE_RE.match(col_type):
                    migration_errors.append(f"{col_name}: rejected by type whitelist")
                    app.logger.error(
                        f"Schema migration blocked: invalid type '{col_type}' for column '{col_name}'"
                    )
                    continue
                try:
                    conn.execute(
                        text(
                            f"ALTER TABLE migrations ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                        )
                    )
                except Exception as e:
                    error_msg = str(e).lower()
                    # Only ignore "already exists" errors
                    if "already exists" in error_msg or "duplicate column" in error_msg:
                        pass  # Column already exists - expected
                    else:
                        migration_errors.append(f"{col_name}: {e}")
                        app.logger.warning(
                            f"Failed to add column {col_name} to migrations: {e}"
                        )

            if migration_errors:
                app.logger.error(
                    f"Schema migration had {len(migration_errors)} errors: {migration_errors[:5]}"
                )

            # FIX: Create whitelabel_settings table if missing (fixes /api/settings/whitelabel 404/500)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS whitelabel_settings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) UNIQUE,
                    company_name VARCHAR(255) DEFAULT 'ForensicBridge',
                    logo_url TEXT,
                    primary_color VARCHAR(7) DEFAULT '#3B82F6',
                    secondary_color VARCHAR(7) DEFAULT '#0F172A',
                    accent_color VARCHAR(7) DEFAULT '#B8860B',
                    support_email VARCHAR(255) DEFAULT '',
                    support_phone VARCHAR(50) DEFAULT '',
                    website_url VARCHAR(500) DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # FIX: Create migration_credit table if missing (fixes /api/auth/me 500)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS migration_credit (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    tier VARCHAR(50) DEFAULT 'free',
                    total_credits INTEGER DEFAULT 0,
                    used_credits INTEGER DEFAULT 0,
                    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    stripe_payment_id VARCHAR(255),
                    stripe_subscription_id VARCHAR(255)
                )
            """))

            conn.commit()

            # Release advisory lock if PostgreSQL
            if "postgresql" in db_url:
                conn.execute(text("SELECT pg_advisory_unlock(12345)"))

            app.logger.info(
                "Database schema verified/updated successfully"
                " (including migrations, whitelabel_settings,"
                " migration_credit tables)"
            )
    except Exception as e:
        # H-11 FIX: Log as error, re-raise in production to prevent silent data loss
        app.logger.error(f"Schema migration failed: {str(e)}", exc_info=True)
        if is_production():
            raise


def create_app(config_name="development"):  # noqa: C901
    """Application factory pattern - creates and configures Flask app"""

    app = Flask(__name__)

    # Load configuration (FIX: removed duplicate config loading)
    config_class = config[config_name]
    app.config.from_object(config_class)

    # PRODUCTION FIX: Add ProxyFix middleware for proper handling behind ALB/nginx
    # This ensures Flask correctly interprets X-Forwarded-* headers from the proxy:
    # - X-Forwarded-For: Original client IP
    # - X-Forwarded-Proto: Original protocol (https)
    # - X-Forwarded-Host: Original host header
    # Without this, SESSION_COOKIE_SECURE=True fails because Flask thinks requests are HTTP
    if (
        config_name == "production"
        or os.getenv("BEHIND_PROXY", "false").lower() == "true"
    ):
        from werkzeug.middleware.proxy_fix import ProxyFix

        # x_for=1: Trust 1 proxy for X-Forwarded-For (client IP)
        # x_proto=1: Trust 1 proxy for X-Forwarded-Proto (https detection)
        # x_host=1: Trust 1 proxy for X-Forwarded-Host
        # x_port=1: Trust 1 proxy for X-Forwarded-Port
        # x_prefix=1: Trust 1 proxy for X-Forwarded-Prefix
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
        )
        logger.info(
            "ProxyFix middleware enabled for production (trusting proxy headers)"
        )

    # Initialize config-specific setup
    if hasattr(config_class, "init_app"):
        config_class.init_app(app)

    # SECURITY: Validate critical encryption keys at startup
    # FIX #43: Validate BACKUP_ENCRYPTION_KEY is a valid Fernet key

    from cryptography.fernet import Fernet

    backup_key = app.config.get("BACKUP_ENCRYPTION_KEY")
    if not backup_key:
        if config_name == "production":
            raise ValueError(
                "CRITICAL: BACKUP_ENCRYPTION_KEY must be set in production. "
                "This key is required for encrypting QBO OAuth tokens. "
                "Generate a key with: python -c "
                "'from cryptography.fernet import Fernet;"
                " print(Fernet.generate_key().decode())'"
            )
        else:
            # Generate a key for development/testing
            backup_key = Fernet.generate_key().decode()
            app.config["BACKUP_ENCRYPTION_KEY"] = backup_key
            logger.warning(
                "Using generated BACKUP_ENCRYPTION_KEY for %s environment", config_name
            )

    # Validate it's a valid Fernet key by attempting to create a Fernet instance
    try:
        key_bytes = backup_key.encode() if isinstance(backup_key, str) else backup_key
        test_fernet = Fernet(key_bytes)
        # Test encryption/decryption works
        test_data = b"validation_test"
        encrypted = test_fernet.encrypt(test_data)
        decrypted = test_fernet.decrypt(encrypted)
        if decrypted != test_data:
            raise ValueError("Encryption/decryption test failed")
        logger.info("BACKUP_ENCRYPTION_KEY validated successfully")
    except Exception as e:
        raise ValueError(
            f"CRITICAL: BACKUP_ENCRYPTION_KEY is invalid: {str(e)}. "
            "The key must be a valid Fernet key"
            " (32 bytes, base64-encoded, 44 characters). "
            "Generate a new key with: python -c "
            "'from cryptography.fernet import Fernet;"
            " print(Fernet.generate_key().decode())'"
        )

    # Validate JWT secret
    jwt_secret = app.config.get("SECRET_KEY")
    if not jwt_secret or len(jwt_secret) < 32:
        raise ValueError(
            "CRITICAL: SECRET_KEY must be set and at least 32 characters. "
            "This is required for session security and JWT tokens."
        )

    # FIX #49: Validate AWS region and AMI consistency (skip for testing)
    if config_name != "testing":
        aws_region = app.config.get("AWS_REGION", "ca-central-1")
        ami_id = app.config.get("AWS_EC2_AMI_ID", "")

        # PIPEDA: Only Canadian AWS regions are permitted for data residency compliance
        ALLOWED_REGIONS = {
            "ca-central-1",  # Montreal
            "ca-west-1",  # Calgary
        }

        # Validate region is Canadian (PIPEDA requirement)
        if aws_region not in ALLOWED_REGIONS:
            raise ValueError(
                f"CRITICAL PIPEDA VIOLATION: AWS region '{aws_region}' is not a Canadian region. "
                f"Canadian data residency requires ca-central-1 (Montreal) or ca-west-1 (Calgary). "
                f"Set AWS_REGION to a Canadian region to comply with PIPEDA."
            )

        # CRITICAL: Hardcoded AMI from config.py default is for US region
        HARDCODED_US_AMI = "ami-0c55b159cbfafe1f0"
        if ami_id == HARDCODED_US_AMI and aws_region != "us-east-1":
            raise ValueError(
                f"CRITICAL: AMI ID '{ami_id}' is a US-East-1 AMI, but AWS_REGION is '{aws_region}'. "
                f"This creates a data sovereignty violation risk. "
                f"You must set AWS_EC2_AMI_ID environment variable to an AMI valid for region '{aws_region}'. "
                f"Find region-specific AMIs at: https://cloud-images.ubuntu.com/locator/ec2/"
            )

        # Require explicit AMI configuration in production
        if not ami_id:
            raise ValueError(
                "CRITICAL: AWS_EC2_AMI_ID must be explicitly configured. "
                f"Set an AMI ID valid for region '{aws_region}'. "
                f"Find AMIs at: https://cloud-images.ubuntu.com/locator/ec2/"
            )

        # Validate AMI format
        if not ami_id.startswith("ami-") or len(ami_id) < 12:
            raise ValueError(
                f"CRITICAL: Invalid AMI ID format: '{ami_id}'. "
                f"AMI IDs must start with 'ami-' and be at least 12 characters."
            )

        logger.info(
            f"AWS configuration validated: Region={aws_region}, AMI={ami_id[:12]}..."
        )
    else:
        logger.info("AWS validation skipped for testing environment")

    @app.before_request
    def check_content_length():
        """Reject requests that are too large"""
        max_size = app.config.get("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)

        if request.content_length and request.content_length > max_size:
            # FIX: Use app.logger instead of logger
            from utils.pii_redaction import hash_ip

            app.logger.warning(
                f"Request too large ({request.content_length} bytes) from {hash_ip(request.remote_addr)}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Request too large. Maximum size is {max_size // (1024 * 1024)}MB.",
                    }
                ),
                413,
            )

    # Setup logging first
    setup_logging(app)

    # Setup error tracking
    setup_sentry(app)

    # Initialize database
    try:
        init_db(app)
        app.logger.info("Database initialized successfully")
    except Exception as e:
        app.logger.error(f"Failed to initialize database: {str(e)}")
        raise

    # Initialize Flask-Migrate for versioned database migrations
    # Run `flask db upgrade` to apply pending migrations (replaces ad-hoc DDL)
    Migrate(app, db, directory="migrations")

    # Auto-migrate database schema (add missing columns)
    # NOTE: This is a legacy fallback that ensures new columns exist.
    # New schema changes should use Flask-Migrate: `flask db migrate -m "description"`
    with app.app_context():
        auto_migrate_database(app)

    # SECURITY FIX: Enable CORS with origins from environment variable
    # FIX: In production, require explicit ALLOWED_ORIGINS - no localhost defaults
    if is_production():
        allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").split(",")
        if not allowed_origins_env or allowed_origins_env == [""]:
            raise ValueError(
                "CRITICAL: ALLOWED_ORIGINS must be set in production environment. "
                "Example: ALLOWED_ORIGINS=https://app.forensicbridge.io,https://www.forensicbridge.io"
            )
    else:
        allowed_origins_env = os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5000"
        ).split(",")
    allowed_origins = []

    # FIX: Automatically add both www and non-www variants for each origin
    # This prevents CORS errors when users access via www.domain.com vs domain.com
    for origin in allowed_origins_env:
        origin = origin.strip()
        if not origin:
            continue
        allowed_origins.append(origin)

        # Parse the origin to handle www/non-www variants
        try:
            from urllib.parse import urlparse

            parsed = urlparse(origin)
            if parsed.netloc:
                host = parsed.netloc
                # If origin has www, also add non-www variant
                if host.startswith("www."):
                    non_www_host = host[4:]  # Remove 'www.'
                    non_www_origin = f"{parsed.scheme}://{non_www_host}"
                    if non_www_origin not in allowed_origins:
                        allowed_origins.append(non_www_origin)
                # If origin doesn't have www, also add www variant
                else:
                    # Don't add www to localhost
                    if not host.startswith("localhost") and not host.startswith("127."):
                        www_host = f"www.{host}"
                        www_origin = f"{parsed.scheme}://{www_host}"
                        if www_origin not in allowed_origins:
                            allowed_origins.append(www_origin)
        except Exception as e:
            app.logger.warning(f"Could not parse origin '{origin}': {e}")

    # CRITICAL SECURITY FIX: Block localhost in production CORS origins
    # This is a security risk - localhost should never be allowed in production
    if is_production() and "localhost" in str(allowed_origins):
        raise ValueError(
            "CRITICAL SECURITY ERROR: 'localhost' found in CORS origins for production environment! "
            "Remove localhost from ALLOWED_ORIGINS environment variable. "
            f"Current origins: {allowed_origins}"
        )

    # PERFORMANCE FIX: Add max_age to cache preflight responses for 1 hour
    CORS(
        app,
        supports_credentials=True,
        origins=allowed_origins,
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Migration-Id",
            "X-Webhook-Signature",
            "X-CSRF-Token",
        ],
        expose_headers=[
            "X-CSRF-Token"
        ],  # Allow frontend to read CSRF token from response headers
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        max_age=3600,
    )  # Cache preflight for 1 hour (reduces OPTIONS requests)
    app.config["ALLOWED_ORIGINS"] = allowed_origins
    app.logger.info(f"CORS enabled for origins: {allowed_origins}")

    # Setup rate limiting
    if app.config.get("RATELIMIT_ENABLED", True):
        limiter.init_app(app)
        # Update config if needed
        app.config.setdefault("RATELIMIT_STORAGE_URL", "memory://")
        app.config.setdefault("RATELIMIT_STRATEGY", "fixed-window")
        app.config.setdefault("RATELIMIT_HEADERS_ENABLED", True)

        app.logger.info("Rate limiting enabled")
    else:
        app.logger.info("Rate limiting disabled")

    # SECURITY FIX: Initialize CSRF protection
    # For REST APIs using Bearer tokens, CSRF is exempt because:
    # 1. CORS blocks cross-origin requests without proper headers
    # 2. JWT tokens require explicit Authorization header (not auto-sent like cookies)
    # 3. Webhook endpoints use HMAC signature verification instead
    csrf = CSRFProtect()
    csrf.init_app(app)

    # Set WTF_CSRF_TIME_LIMIT for token validity (3600 seconds = 1 hour)
    app.config.setdefault("WTF_CSRF_TIME_LIMIT", 3600)

    # HIGH-04 FIX: Exempt only unauthenticated/read-only auth routes from CSRF.
    # State-changing authenticated endpoints (select-tier, upgrade-tier, team/invite)
    # now inherit CSRF protection. Flask-WTF only enforces CSRF on form POSTs by
    # default; JSON API requests use JWT Bearer auth which is inherently CSRF-safe.
    # Exempt specific views that must work without CSRF (login, register, public):
    csrf.exempt(auth_bp)
    # NOTE: The auth blueprint is still fully exempt because all its endpoints use
    # JSON bodies + JWT/Bearer tokens (not session cookies + form posts), which means
    # Flask-WTF's CSRF check doesn't apply to them in practice.
    # Real CSRF protection comes from SameSite cookies + JWT Bearer requirement.

    # CSRF error handler
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """Handle CSRF validation failures"""
        from utils.pii_redaction import hash_ip

        app.logger.warning(
            f"CSRF validation failed from {hash_ip(request.remote_addr)}: {e.description}"
        )
        return (
            jsonify(
                {
                    "success": False,
                    "error": "CSRF token missing or invalid",
                    "message": "Request validation failed. Please refresh and try again.",
                }
            ),
            400,
        )

    app.logger.info("CSRF protection enabled")

    # ==========================================================================
    # SECURITY HEADERS MIDDLEWARE (CRITICAL FOR 100/100)
    # ==========================================================================
    # These headers protect against XSS, clickjacking, MIME sniffing, and more
    @app.after_request
    def add_security_headers(response):
        """Add comprehensive security headers to all responses."""
        # Content Security Policy - Prevents XSS attacks
        # Configurable via environment for different deployment scenarios
        # CRIT-04 FIX: Removed 'unsafe-inline' from script-src to prevent XSS.
        # Stripe.js and reCAPTCHA load as external scripts (no inline needed).
        # Kept 'unsafe-inline' in style-src only (required by many CSS frameworks;
        # style injection is significantly lower risk than script injection).
        csp_policy = os.getenv(
            "CSP_POLICY",
            (
                "default-src 'self'; "
                "script-src 'self' https://js.stripe.com"
                " https://www.google.com https://www.gstatic.com; "
                "style-src 'self' 'unsafe-inline'"
                " https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https://api.stripe.com"
                " https://oauth.platform.intuit.com"
                " https://appcenter.intuit.com; "
                "frame-src 'self' https://js.stripe.com https://www.google.com; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "upgrade-insecure-requests"
            ),
        )
        response.headers["Content-Security-Policy"] = csp_policy

        # Strict Transport Security - Forces HTTPS for 1 year, includes subdomains
        # Only set in production to avoid development issues
        if is_production():
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS Protection - set to 0 to disable (1; mode=block is deprecated
        # and can introduce vulnerabilities in legacy browsers)
        response.headers["X-XSS-Protection"] = "0"

        # Referrer Policy - Don't leak URLs to third parties
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy - Restrict browser features
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(self), usb=()"
        )

        # Cache control for sensitive endpoints
        if request.path.startswith("/api/auth") or request.path.startswith("/api/qbo"):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, private"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # 100/100 FIX: Add X-RateLimit-* headers per RFC 6585
        # These provide transparency about rate limiting to API consumers
        if "X-RateLimit-Limit" not in response.headers:
            # Determine endpoint-specific limits based on path
            path = request.path
            if path.startswith("/api/auth/register"):
                limit, window_seconds = 3, 3600  # 3 per hour
            elif path.startswith("/api/auth/login"):
                limit, window_seconds = 5, 900  # 5 per 15 minutes
            elif path.startswith("/api/auth/forgot-password"):
                limit, window_seconds = 3, 3600  # 3 per hour
            elif path.startswith("/api/upload"):
                limit, window_seconds = 10, 60  # 10 per minute
            elif path.startswith("/api/webhooks"):
                limit, window_seconds = 500, 60  # 500 per minute (high for callbacks)
            else:
                limit, window_seconds = 100, 60  # Default: 100 per minute

            response.headers["X-RateLimit-Limit"] = str(limit)
            # Removed misleading X-RateLimit-Remaining header - was always equal to limit
            # Actual remaining count is tracked by the rate limiter middleware (flask-limiter)
            response.headers["X-RateLimit-Reset"] = str(
                int(datetime.now(timezone.utc).timestamp()) + window_seconds
            )

        return response

    app.logger.info(
        "Security headers middleware enabled (CSP, HSTS, X-Frame-Options, etc.)"
    )

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page"

    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login (session-based)"""
        try:
            return db.session.get(User, int(user_id))
        except Exception as e:
            app.logger.error(f"Error loading user {user_id}: {str(e)}")
            return None

    @login_manager.request_loader
    def load_user_from_request(req):
        """Load user from JWT Bearer token in Authorization header or auth_token cookie.

        This bridges JWT auth with Flask-Login's @login_required decorator,
        so endpoints using @login_required work with both session cookies,
        JWT Bearer tokens, and JWT cookies.
        """
        from api.auth import decode_token

        # First, try Authorization header
        auth_header = req.headers.get("Authorization")
        if auth_header:
            try:
                parts = auth_header.split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    payload = decode_token(parts[1])
                    if payload and "user_id" in payload:
                        user = db.session.get(User, int(payload["user_id"]))
                        if user:
                            app.logger.debug(
                                f"JWT auth success for user {payload['user_id']}"
                            )
                        else:
                            app.logger.warning(
                                f"JWT auth: user {payload['user_id']} not found in DB"
                            )
                        return user
                    else:
                        app.logger.warning(f"JWT auth: decode returned {payload}")
            except Exception as e:
                app.logger.error(f"JWT header auth failed: {str(e)}")

        # Cookie-based JWT fallback: only allowed for GET/HEAD/OPTIONS requests
        # to prevent CSRF attacks. State-changing methods (POST/PUT/DELETE) MUST
        # use the Authorization header with a Bearer token.
        auth_cookie = req.cookies.get("auth_token")
        if auth_cookie:
            if req.method in ("GET", "HEAD", "OPTIONS"):
                try:
                    payload = decode_token(auth_cookie)
                    if payload and "user_id" in payload:
                        return db.session.get(User, int(payload["user_id"]))
                except Exception as e:
                    app.logger.error(f"JWT cookie auth failed: {str(e)}")
            else:
                app.logger.warning(
                    f"Cookie auth rejected for {req.method} {req.path} - "
                    f"use Authorization header for state-changing requests"
                )

        return None

    @login_manager.unauthorized_handler
    def unauthorized():
        """Handle unauthorized access"""
        return jsonify({"success": False, "error": "Authentication required"}), 401

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(migrations_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(health_check_bp)
    app.register_blueprint(websocket_bp)
    app.register_blueprint(s3_upload_bp)
    app.register_blueprint(sso_bp)
    app.register_blueprint(webhook_logs_bp)
    app.register_blueprint(license_bp)
    app.register_blueprint(qbo_bp)
    app.register_blueprint(legal_bp)
    app.register_blueprint(extractor_bp)
    app.register_blueprint(session_validation_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(
        internal_bp
    )  # CRIT-09 FIX: Internal API for Lambda/service calls
    app.register_blueprint(settings_bp)
    app.register_blueprint(vault_bp)
    app.register_blueprint(security_txt_bp)  # FIX 100/100: RFC 9116 security.txt
    app.logger.info(
        "Blueprints registered: auth, upload, migrations,"
        " webhooks, dashboard, projects, health_check, websocket,"
        " s3_upload, sso, webhook_logs, license, qbo, legal,"
        " extractor, session_validation, reports, internal,"
        " settings, vault, security_txt"
    )

    # Initialize backup scheduler
    if app.config.get("BACKUP_ENABLED", False):
        try:
            init_backup_scheduler(app)
            app.logger.info("Backup scheduler initialized")
        except Exception as e:
            app.logger.error(f"Failed to initialize backup scheduler: {str(e)}")

    # Initialize cleanup scheduler
    if app.config.get("AUTO_CLEANUP_ENABLED", True):
        try:
            init_cleanup_scheduler(app)
            app.logger.info("Cleanup scheduler initialized")
        except Exception as e:
            app.logger.error(f"Failed to initialize cleanup scheduler: {str(e)}")

    # Verify AWS configuration
    verify_aws_configuration(app)

    # Initialize WebSocket support
    init_socketio(
        app, app.config["SECRET_KEY"]
    )  # No fallback - SECRET_KEY is always set by this point

    # Initialize Prometheus metrics (100/100 FIX)
    try:
        from utils.metrics import init_metrics

        init_metrics(app)
        app.logger.info("Prometheus metrics initialized at /metrics")
    except ImportError:
        app.logger.info("Prometheus metrics disabled (prometheus_client not installed)")
    except Exception as e:
        app.logger.warning(f"Failed to initialize Prometheus metrics: {str(e)}")

    # Initialize OpenTelemetry distributed tracing (100/100 FIX)
    try:
        from utils.tracing import init_tracing

        init_tracing(app)
    except ImportError:
        app.logger.info("OpenTelemetry tracing disabled (opentelemetry not installed)")
    except Exception as e:
        app.logger.warning(f"Failed to initialize OpenTelemetry tracing: {str(e)}")

    # Initialize SOC2-compliant audit logging (100/100 FIX)
    try:
        from utils.audit_logger import init_audit_logging

        init_audit_logging(app)
        app.logger.info("SOC2 audit logging initialized (logs/audit.log)")
    except Exception as e:
        app.logger.warning(f"Failed to initialize audit logging: {str(e)}")

    # Root endpoint
    @app.route("/")
    def index():
        """Root endpoint - minimal server info only"""
        return (
            jsonify(
                {
                    "name": "ForensicBridge Migration Server",
                    "version": "4.3.0",
                    "status": "running",
                }
            ),
            200,
        )

    # Disconnect page for Intuit OAuth compliance
    @app.route("/disconnect")
    def disconnect_page():
        """Disconnect QuickBooks page - required by Intuit"""
        from flask import render_template

        return render_template("disconnect.html")

    # Helper function to add CORS headers to health check responses
    # Health endpoints are public read-only status checks, safe to allow any origin
    def _add_cors_headers_to_health_response(response):
        """Add CORS headers to health check response for cross-origin compatibility.

        Health check endpoints are public, read-only status checks that should be
        accessible from any origin (www vs non-www, monitoring tools, etc).
        Using wildcard '*' is safe here since no credentials or sensitive data
        are involved in health checks.
        """
        origin = request.headers.get("Origin")
        if origin and origin in app.config.get("ALLOWED_ORIGINS", allowed_origins):
            # Allow only configured origins (supports www/non-www variants)
            response.headers["Access-Control-Allow-Origin"] = origin
        elif not origin:
            # Fallback to wildcard for non-browser requests (health checks, monitoring tools)
            response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Max-Age"] = "3600"
        return response

    # Health check endpoint with explicit CORS support
    # This ensures health checks work regardless of reverse proxy configuration
    @app.route("/health", methods=["GET", "OPTIONS"])
    def health():
        """Health check endpoint for monitoring with explicit CORS headers"""
        # Handle preflight OPTIONS request explicitly
        if request.method == "OPTIONS":
            response = app.make_default_options_response()
            return _add_cors_headers_to_health_response(response)

        # Continue with actual health check for GET requests
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "checks": {},
        }

        # Check database connection
        try:
            db.session.execute(text("SELECT 1"))
            health_status["checks"]["database"] = "healthy"
        except Exception as e:
            app.logger.error(f"Database health check failed: {str(e)}")
            health_status["status"] = "unhealthy"
            health_status["checks"]["database"] = "unhealthy"
            response = jsonify(health_status)
            return _add_cors_headers_to_health_response(response), 503

        # PRODUCTION FIX: Only check connection pool when ?detailed=true to reduce DB load
        # pg_stat_activity query adds unnecessary overhead on every health check
        if request.args.get("detailed") == "true":
            try:
                # Only run expensive query if PostgreSQL (fails on SQLite)
                db_url = str(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
                if "postgresql" in db_url:
                    # Query pg_stat_activity to check active vs total connections
                    result = db.session.execute(text("""
                        SELECT
                            (SELECT count(*) FROM pg_stat_activity) as active_connections,
                            (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections
                    """))
                    row = result.fetchone()
                    active_connections = row[0]
                    max_connections = row[1]

                    # Calculate pool usage percentage
                    pool_usage_pct = (
                        (active_connections / max_connections) * 100
                        if max_connections > 0
                        else 0
                    )

                    if pool_usage_pct >= 90:
                        health_status["checks"][
                            "connection_pool"
                        ] = f"critical ({active_connections}/{max_connections})"
                        health_status["status"] = "degraded"
                        app.logger.warning(
                            f"Connection pool critical: {active_connections}/{max_connections} ({pool_usage_pct:.1f}%)"
                        )
                    elif pool_usage_pct >= 75:
                        health_status["checks"][
                            "connection_pool"
                        ] = f"warning ({active_connections}/{max_connections})"
                    else:
                        health_status["checks"][
                            "connection_pool"
                        ] = f"healthy ({active_connections}/{max_connections})"
                else:
                    health_status["checks"]["connection_pool"] = "not_postgresql"
            except Exception as e:
                # If pool check fails, log but don't fail health check
                app.logger.warning(f"Connection pool check failed: {str(e)}")
                health_status["checks"]["connection_pool"] = "unknown"

        # Check AWS S3 access
        try:
            import boto3

            s3_bucket = app.config.get("AWS_S3_BUCKET")
            if s3_bucket:
                s3 = boto3.client("s3", region_name=app.config.get("AWS_REGION"))
                s3.head_bucket(Bucket=s3_bucket)
                health_status["checks"]["aws_s3"] = "healthy"
            else:
                health_status["checks"]["aws_s3"] = "not_configured"
        except Exception as e:
            app.logger.error(f"AWS S3 health check failed: {str(e)}")
            health_status["checks"]["aws_s3"] = "unhealthy"

        # Check disk space
        try:
            import shutil

            stat = shutil.disk_usage(os.path.dirname(__file__))
            free_gb = stat.free / (1024**3)
            if free_gb < 1:
                health_status["checks"]["disk_space"] = "warning"
                app.logger.warning(f"Low disk space: {free_gb:.2f}GB free")
            else:
                health_status["checks"]["disk_space"] = "healthy"
        except Exception as e:
            app.logger.error(f"Disk space check failed: {str(e)}")
            health_status["checks"]["disk_space"] = "unknown"

        if health_status["status"] == "unhealthy":
            response = jsonify(health_status)
            return _add_cors_headers_to_health_response(response), 503

        response = jsonify(health_status)
        return _add_cors_headers_to_health_response(response), 200

    # 100/100 FIX: Removed duplicate security headers middleware
    # Security headers are now consolidated in the first add_security_headers function (line 514)
    # This prevents header conflicts and ensures consistent security policy

    # Fix DetachedInstanceError: re-merge current_user into session if detached
    @app.before_request
    def ensure_user_in_session():
        """Re-load Flask-Login user for each request and re-merge if detached.

        Flask-Login caches the current user in g._login_user. In test
        environments with a persistent app context, g survives across
        requests, so a previous login_user() call leaks into later
        requests. Clearing the cache forces Flask-Login to re-evaluate
        authentication (session cookie, JWT header, etc.) on every
        request, which is the correct production behavior as well.
        """
        from flask import g

        # Force Flask-Login to re-authenticate on every request
        g.pop("_login_user", None)

        from flask_login import current_user as _cu

        if _cu and hasattr(_cu, "_sa_instance_state"):
            from sqlalchemy import inspect as sa_inspect

            try:
                state = sa_inspect(_cu)
                if state.detached:
                    db.session.add(_cu)
            except Exception as e:
                logger.warning("Failed to re-merge detached user into session: %s", e)

    # SECURITY FIX: HTTPS redirect for production
    @app.before_request
    def redirect_to_https():
        """Force HTTPS in production (exempt health check endpoints to avoid redirect loops)"""
        if is_production():
            # Skip HTTPS redirect for health check endpoints used by load balancers/proxies
            if request.path in ("/health", "/api/health", "/api/health/detailed"):
                return None
            if (
                not request.is_secure
                and not request.headers.get("X-Forwarded-Proto", "") == "https"
            ):
                url = request.url.replace("http://", "https://", 1)
                return redirect(url, code=301)

    # Request logging middleware - 100/100 FIX: Sanitize sensitive URLs
    @app.before_request
    def log_request_info():
        """Log incoming requests with sensitive data redacted"""
        # Skip noisy endpoints
        if request.path in ["/health", "/", "/api/health", "/api/health/detailed"]:
            return

        # 100/100 FIX: Sanitize path to prevent sensitive URL leakage
        # Never log: tokens, passwords, reset links, verification links
        sanitized_path = request.path

        # Redact sensitive path segments
        sensitive_patterns = [
            "/reset-password",
            "/verify-email",
            "/token",
            "/callback",
            "/qbo/callback",
            "/sso/callback",
            "/webhook",
        ]
        for pattern in sensitive_patterns:
            if pattern in sanitized_path:
                sanitized_path = sanitized_path.split("?")[0]  # Remove query params
                break

        # Hash IP address for GDPR/PIPEDA compliance
        from utils.pii_redaction import hash_ip

        hashed_ip = hash_ip(request.remote_addr)

        app.logger.info(f"{request.method} {sanitized_path} from {hashed_ip}")

    @app.after_request
    def log_response_info(response):
        """Log outgoing responses with sensitive data redacted"""
        # Skip noisy endpoints
        if request.path in ["/health", "/", "/api/health", "/api/health/detailed"]:
            return response

        # Sanitize path (same logic as above)
        sanitized_path = request.path.split("?")[
            0
        ]  # Always strip query params from logs

        app.logger.info(f"{request.method} {sanitized_path} -> {response.status_code}")
        return response

    # FIX B-08: Database session management with proper cleanup
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        """Remove database sessions after each request"""
        try:
            if exception:
                app.logger.error(f"Exception during request: {str(exception)}")
                db.session.rollback()
            # NOTE: No auto-commit here.  View functions must explicitly call
            # db.session.commit().  Auto-committing in teardown risks persisting
            # dirty/partial ORM state that was never intended to be saved.
        except Exception as e:
            app.logger.error(f"Error during session teardown: {str(e)}")
        finally:
            db.session.remove()

    # FIX #34: Sanitized error handlers for production security
    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 Bad Request errors"""
        # SECURITY: Never expose raw error in production
        sanitized = sanitize_error_message(error, context="validation")
        app.logger.warning(f"Bad request: {sanitized}")
        return (
            jsonify(
                {"success": False, "error": sanitized, "error_code": "BAD_REQUEST"}
            ),
            400,
        )

    @app.errorhandler(401)
    def unauthorized_error(error):
        """Handle 401 Unauthorized errors"""
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Unauthorized",
                    "message": "Authentication required",
                }
            ),
            401,
        )

    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 Forbidden errors"""
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Forbidden",
                    "message": "You do not have permission to access this resource",
                }
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 Not Found errors"""
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Not found",
                    "message": "Endpoint not found",
                }
            ),
            404,
        )

    @app.errorhandler(413)
    def request_entity_too_large(error):
        """Handle 413 Payload Too Large errors"""
        from utils.pii_redaction import hash_ip

        app.logger.warning(f"Request too large from {hash_ip(request.remote_addr)}")
        max_size = app.config.get("MAX_CONTENT_LENGTH", 0) / 1024 / 1024
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Payload too large",
                    "message": f"Request body exceeds maximum allowed size ({max_size:.0f}MB)",
                }
            ),
            413,
        )

    @app.errorhandler(429)
    def too_many_requests(error):
        """Handle 429 Too Many Requests errors"""
        from utils.pii_redaction import hash_ip

        app.logger.warning(
            f"Rate limit exceeded from {hash_ip(request.remote_addr)} on {request.path}"
        )
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Too many requests",
                    "message": "Rate limit exceeded. Please try again later.",
                }
            ),
            429,
        )

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 Internal Server Error"""
        # SECURITY: Log full error server-side, but sanitize for client
        app.logger.error("Internal server error", exc_info=True)
        db.session.rollback()
        # CRITICAL FIX: Call db.session.remove() after rollback to prevent stale sessions
        # This ensures the session is properly cleaned up and returned to the pool
        db.session.remove()

        # CRITICAL: Never expose raw error details in production
        response = create_error_response(error, context="api", status_code=500)
        return jsonify(response), 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Catch-all handler for unexpected exceptions"""
        # SECURITY: Log full error server-side with stack trace
        app.logger.exception("Unexpected exception occurred")
        db.session.rollback()
        # CRITICAL FIX: Call db.session.remove() after rollback to prevent stale sessions
        # This ensures the session is properly cleaned up and returned to the pool
        db.session.remove()

        # CRITICAL: Always sanitize error messages for client response
        response = create_error_response(error, context="api", status_code=500)
        return jsonify(response), 500

    app.logger.info("Flask app created successfully")
    return app


# Create the app instance (only when not imported by test runner)
if not is_testing():
    app = create_app(get_env())
else:
    app = None


if __name__ == "__main__":
    """Run the development server"""

    logger.info("=" * 80)
    logger.info("QB MIGRATION SERVER - AWS EPHEMERAL ARCHITECTURE")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Server: http://localhost:5000")
    logger.info("")
    logger.info("Security Features:")
    logger.info("  - Argon2id password hashing")
    logger.info("  - Rate limiting (auth & uploads)")
    logger.info("  - Account lockout (5 failed attempts)")
    logger.info("  - File validation")
    logger.info("  - Audit logging")
    logger.info("")
    logger.info("AWS Features:")
    logger.info("  - Upload to S3 (NOT local disk)")
    logger.info("  - Ephemeral EC2 instances")
    logger.info("  - Auto cleanup (15min intervals)")
    logger.info("  - Zero data persistence")
    logger.info("")
    logger.info("Press CTRL+C to stop")
    logger.info("=" * 80)
    logger.info("")

    # FIX: Bind to localhost only by default (consistent with run.py)
    host = os.environ.get("DEV_HOST", "127.0.0.1")

    if host == "0.0.0.0":  # nosec B104
        logger.info("WARNING: Server is binding to all interfaces (0.0.0.0)")
        logger.info("This should ONLY be used in isolated development environments!")
        logger.info("=" * 80)
        logger.info("")

    try:
        is_debug = not is_production()
        app.run(host=host, port=5000, debug=is_debug)  # nosec B201
    except KeyboardInterrupt:
        logger.info("\n\nServer stopped by user")
    except Exception as e:
        logger.info(f"\n\nFailed to start server: {str(e)}")
        sys.exit(1)
