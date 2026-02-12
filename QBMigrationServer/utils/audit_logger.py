"""
Security Audit Logger for SOC2 Compliance
==========================================

Provides structured security audit logging for compliance with:
- SOC2 Type II
- GDPR Article 30 (Records of Processing)
- PIPEDA (Canadian Privacy)
- PCI-DSS (if handling payment data)

Audit Events Logged:
- Authentication (login, logout, failed attempts, MFA)
- Authorization (access granted/denied, role changes)
- Data Access (read, create, update, delete operations)
- Security Events (rate limits, suspicious activity, lockouts)
- Configuration Changes (settings, API keys, webhooks)
- Migration Operations (start, complete, fail, data access)

Log Format:
    JSON structured logs with:
    - timestamp (ISO 8601 UTC)
    - event_type (category.action)
    - actor (user_id, ip, user_agent hash)
    - resource (type, id)
    - action (what happened)
    - outcome (success/failure)
    - metadata (additional context)
    - correlation_id (request tracing)

Usage:
    from utils.audit_logger import audit_log, AuditEvent

    # Log authentication event
    audit_log.auth_login(user_id=123, success=True, ip="1.2.3.4")

    # Log data access
    audit_log.data_access(
        user_id=123,
        resource_type="migration",
        resource_id="abc-123",
        action="read"
    )

    # Custom event
    audit_log.log(AuditEvent(
        event_type="custom.operation",
        actor_id=123,
        resource_type="report",
        action="generate",
        outcome="success"
    ))

Author: ForensicBridge Security Team
Version: 1.0.0
"""

import hashlib
import hmac
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

# AUDIT FIX HIGH: HMAC key for audit log tamper protection
# In production, this should be set via environment variable
_hmac_raw = os.getenv("AUDIT_HMAC_KEY", "")
if not _hmac_raw and os.getenv("FLASK_ENV") == "production":
    raise RuntimeError(
        "AUDIT_HMAC_KEY must be set in production for tamper-proof audit logs"
    )
AUDIT_HMAC_KEY = _hmac_raw.encode("utf-8")

# Configure audit logger
# Use LOG_DIR env var (set in Dockerfile to /app/logs, the writable volume)
# to avoid writing to the read-only QBMigrationServer mount
_log_dir = os.environ.get("LOG_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "logs"
)
AUDIT_LOG_FILE = os.path.join(_log_dir, "audit.log")

# Ensure logs directory exists
os.makedirs(_log_dir, exist_ok=True)


class AuditEventType(Enum):
    """Standardized audit event types for SOC2 compliance."""

    # Authentication Events
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_MFA_ENABLED = "auth.mfa.enabled"
    AUTH_MFA_DISABLED = "auth.mfa.disabled"
    AUTH_MFA_VERIFIED = "auth.mfa.verified"
    AUTH_MFA_FAILED = "auth.mfa.failed"
    AUTH_PASSWORD_CHANGED = "auth.password.changed"
    AUTH_PASSWORD_RESET_REQUESTED = "auth.password.reset_requested"
    AUTH_PASSWORD_RESET_COMPLETED = "auth.password.reset_completed"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"
    AUTH_SESSION_INVALIDATED = "auth.session.invalidated"

    # Authorization Events
    AUTHZ_ACCESS_GRANTED = "authz.access.granted"
    AUTHZ_ACCESS_DENIED = "authz.access.denied"
    AUTHZ_ROLE_CHANGED = "authz.role.changed"
    AUTHZ_PERMISSION_CHANGED = "authz.permission.changed"

    # User Management Events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_LOCKED = "user.locked"
    USER_UNLOCKED = "user.unlocked"

    # Data Access Events
    DATA_READ = "data.read"
    DATA_CREATE = "data.create"
    DATA_UPDATE = "data.update"
    DATA_DELETE = "data.delete"
    DATA_EXPORT = "data.export"
    DATA_IMPORT = "data.import"

    # Migration Events
    MIGRATION_STARTED = "migration.started"
    MIGRATION_COMPLETED = "migration.completed"
    MIGRATION_FAILED = "migration.failed"
    MIGRATION_CANCELLED = "migration.cancelled"
    MIGRATION_RETRY = "migration.retry"
    MIGRATION_DATA_ACCESSED = "migration.data.accessed"

    # Security Events
    SECURITY_RATE_LIMIT_HIT = "security.rate_limit.hit"
    SECURITY_SUSPICIOUS_ACTIVITY = "security.suspicious_activity"
    SECURITY_ACCOUNT_LOCKOUT = "security.account.lockout"
    SECURITY_CAPTCHA_REQUIRED = "security.captcha.required"
    SECURITY_CAPTCHA_FAILED = "security.captcha.failed"
    SECURITY_IP_BLOCKED = "security.ip.blocked"
    SECURITY_WEBHOOK_INVALID = "security.webhook.invalid"

    # Configuration Events
    CONFIG_SETTING_CHANGED = "config.setting.changed"
    CONFIG_API_KEY_CREATED = "config.api_key.created"
    CONFIG_API_KEY_REVOKED = "config.api_key.revoked"
    CONFIG_WEBHOOK_CREATED = "config.webhook.created"
    CONFIG_WEBHOOK_DELETED = "config.webhook.deleted"

    # Payment Events
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"

    # System Events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_BACKUP_COMPLETED = "system.backup.completed"
    SYSTEM_CLEANUP_COMPLETED = "system.cleanup.completed"


@dataclass
class AuditEvent:
    """
    Structured audit event for SOC2-compliant logging.

    All fields are designed to meet SOC2 CC6.1, CC6.2, CC6.3 requirements
    for logical and physical access controls.
    """

    # Event identification
    event_type: str  # From AuditEventType or custom string
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Actor information (who performed the action)
    actor_id: Optional[int] = None  # User ID
    actor_email_hash: Optional[str] = None  # Hashed email for privacy
    actor_ip: Optional[str] = None  # IP address (may be hashed)
    actor_user_agent_hash: Optional[str] = None  # Hashed User-Agent

    # Resource information (what was affected)
    resource_type: Optional[str] = None  # e.g., "migration", "user", "setting"
    resource_id: Optional[str] = None  # Resource identifier

    # Action details
    action: Optional[str] = None  # Human-readable action description
    outcome: str = "success"  # "success", "failure", "error"
    outcome_reason: Optional[str] = None  # Reason for failure/error

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Request correlation
    correlation_id: Optional[str] = None  # For tracing across services
    session_id: Optional[str] = None  # Session identifier

    # Compliance fields
    data_classification: Optional[str] = (
        None  # "public", "internal", "confidential", "restricted"
    )
    retention_days: int = 2555  # 7 years default for SOC2

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


def _sanitize_log_value(value):
    """Sanitize a value for safe logging (prevent log injection)."""
    if isinstance(value, str):
        # Remove newlines and control characters that could inject fake log entries
        return value.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return value


class AuditLogger:
    """
    SOC2-compliant audit logger with structured JSON output.

    Logs are written to both:
    1. Separate audit log file (logs/audit.log)
    2. Standard application log (for aggregation)
    """

    def __init__(self):
        """Initialize the audit logger."""
        self._setup_logger()

    def _setup_logger(self):
        """Configure the audit logger with file handler."""
        self.logger = logging.getLogger("audit")
        self.logger.setLevel(logging.INFO)

        # Prevent duplicate handlers
        if self.logger.handlers:
            return

        # File handler for audit log
        try:
            from logging.handlers import RotatingFileHandler

            file_handler = RotatingFileHandler(
                AUDIT_LOG_FILE,
                maxBytes=50 * 1024 * 1024,  # 50MB per file
                backupCount=100,  # Keep 100 files (covers retention period)
                encoding="utf-8",
            )
            file_handler.setLevel(logging.INFO)

            # JSON format for structured logging
            file_handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(file_handler)
        except Exception as e:
            logging.warning(f"Failed to setup audit file handler: {e}")

        # Also log to standard logger for aggregation
        self.app_logger = logging.getLogger(__name__)

    def _hash_pii(self, value: str) -> Optional[str]:
        """Hash PII for privacy compliance."""
        if not value:
            return None
        return hashlib.sha256(value.encode()).hexdigest()[:32]

    def _get_request_context(self) -> Dict[str, Any]:
        """Extract context from current Flask request."""
        try:
            from flask import g, request

            return {
                "ip": self._hash_pii(request.remote_addr or ""),
                "user_agent": request.headers.get("User-Agent", ""),
                "correlation_id": getattr(g, "correlation_id", None)
                or request.headers.get("X-Correlation-ID"),
                "endpoint": request.endpoint,
                "method": request.method,
            }
        except RuntimeError:
            # Not in request context
            return {}

    def log(self, event: AuditEvent):
        """
        Log an audit event.

        Args:
            event: AuditEvent instance to log
        """
        # Add request context if available
        ctx = self._get_request_context()
        if ctx.get("ip") and not event.actor_ip:
            event.actor_ip = self._hash_pii(ctx["ip"])
        if ctx.get("user_agent") and not event.actor_user_agent_hash:
            event.actor_user_agent_hash = self._hash_pii(ctx["user_agent"])
        if ctx.get("correlation_id") and not event.correlation_id:
            event.correlation_id = ctx["correlation_id"]

        # AUDIT FIX HIGH: Add HMAC signature for tamper detection
        event_json = event.to_json()
        if AUDIT_HMAC_KEY:
            sig = hmac.new(
                AUDIT_HMAC_KEY, event_json.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            log_line = json.dumps(
                {"payload": json.loads(event_json), "hmac_sha256": sig}
            )
        else:
            log_line = event_json

        # Log to audit file (JSON format with HMAC if configured)
        self.logger.info(log_line)

        # Also log summary to app logger (sanitize user-controlled fields to prevent log injection)
        self.app_logger.info(
            f"AUDIT: {_sanitize_log_value(event.event_type)} | actor={event.actor_id} | "
            f"resource={_sanitize_log_value(event.resource_type)}:{_sanitize_log_value(event.resource_id)} | "
            f"outcome={_sanitize_log_value(event.outcome)}"
        )

    # =========================================================================
    # Convenience Methods for Common Events
    # =========================================================================

    def auth_login(
        self,
        user_id: int,
        success: bool,
        email: str = None,
        ip: str = None,
        failure_reason: str = None,
    ):
        """Log authentication attempt."""
        event_type = (
            AuditEventType.AUTH_LOGIN_SUCCESS
            if success
            else AuditEventType.AUTH_LOGIN_FAILURE
        )

        self.log(
            AuditEvent(
                event_type=event_type.value,
                actor_id=user_id,
                actor_email_hash=self._hash_pii(email) if email else None,
                actor_ip=self._hash_pii(ip) if ip else None,
                resource_type="session",
                action="login",
                outcome="success" if success else "failure",
                outcome_reason=failure_reason,
                data_classification="confidential",
            )
        )

    def auth_logout(self, user_id: int):
        """Log logout event."""
        self.log(
            AuditEvent(
                event_type=AuditEventType.AUTH_LOGOUT.value,
                actor_id=user_id,
                resource_type="session",
                action="logout",
                outcome="success",
            )
        )

    def auth_mfa(self, user_id: int, action: str, success: bool):
        """Log MFA event."""
        event_types = {
            ("enabled", True): AuditEventType.AUTH_MFA_ENABLED,
            ("disabled", True): AuditEventType.AUTH_MFA_DISABLED,
            ("verified", True): AuditEventType.AUTH_MFA_VERIFIED,
            ("verified", False): AuditEventType.AUTH_MFA_FAILED,
        }
        event_type = event_types.get(
            (action, success), AuditEventType.AUTH_MFA_VERIFIED
        )

        self.log(
            AuditEvent(
                event_type=event_type.value,
                actor_id=user_id,
                resource_type="mfa",
                action=action,
                outcome="success" if success else "failure",
                data_classification="confidential",
            )
        )

    def data_access(
        self,
        user_id: int,
        resource_type: str,
        resource_id: str,
        action: str,
        success: bool = True,
        metadata: Dict = None,
    ):
        """Log data access event."""
        action_types = {
            "read": AuditEventType.DATA_READ,
            "create": AuditEventType.DATA_CREATE,
            "update": AuditEventType.DATA_UPDATE,
            "delete": AuditEventType.DATA_DELETE,
            "export": AuditEventType.DATA_EXPORT,
            "import": AuditEventType.DATA_IMPORT,
        }
        event_type = action_types.get(action, AuditEventType.DATA_READ)

        self.log(
            AuditEvent(
                event_type=event_type.value,
                actor_id=user_id,
                resource_type=resource_type,
                resource_id=str(resource_id),
                action=action,
                outcome="success" if success else "failure",
                metadata=metadata or {},
                data_classification="confidential",
            )
        )

    def migration_event(
        self,
        user_id: int,
        migration_id: str,
        action: str,
        success: bool = True,
        metadata: Dict = None,
    ):
        """Log migration event."""
        action_types = {
            "started": AuditEventType.MIGRATION_STARTED,
            "completed": AuditEventType.MIGRATION_COMPLETED,
            "failed": AuditEventType.MIGRATION_FAILED,
            "cancelled": AuditEventType.MIGRATION_CANCELLED,
            "retry": AuditEventType.MIGRATION_RETRY,
        }
        event_type = action_types.get(action, AuditEventType.MIGRATION_STARTED)

        self.log(
            AuditEvent(
                event_type=event_type.value,
                actor_id=user_id,
                resource_type="migration",
                resource_id=migration_id,
                action=action,
                outcome="success" if success else "failure",
                metadata=metadata or {},
                data_classification="confidential",
            )
        )

    def security_event(
        self,
        event_type: str,
        user_id: int = None,
        ip: str = None,
        details: str = None,
        metadata: Dict = None,
    ):
        """Log security event."""
        security_types = {
            "rate_limit": AuditEventType.SECURITY_RATE_LIMIT_HIT,
            "suspicious": AuditEventType.SECURITY_SUSPICIOUS_ACTIVITY,
            "lockout": AuditEventType.SECURITY_ACCOUNT_LOCKOUT,
            "captcha_required": AuditEventType.SECURITY_CAPTCHA_REQUIRED,
            "captcha_failed": AuditEventType.SECURITY_CAPTCHA_FAILED,
            "ip_blocked": AuditEventType.SECURITY_IP_BLOCKED,
            "webhook_invalid": AuditEventType.SECURITY_WEBHOOK_INVALID,
        }
        audit_event_type = security_types.get(
            event_type, AuditEventType.SECURITY_SUSPICIOUS_ACTIVITY
        )

        self.log(
            AuditEvent(
                event_type=audit_event_type.value,
                actor_id=user_id,
                actor_ip=self._hash_pii(ip) if ip else None,
                resource_type="security",
                action=event_type,
                outcome="triggered",
                outcome_reason=details,
                metadata=metadata or {},
                data_classification="restricted",
            )
        )

    def config_change(
        self,
        user_id: int,
        setting_name: str,
        old_value: str = None,
        new_value: str = None,
        resource_type: str = "setting",
    ):
        """Log configuration change."""
        self.log(
            AuditEvent(
                event_type=AuditEventType.CONFIG_SETTING_CHANGED.value,
                actor_id=user_id,
                resource_type=resource_type,
                resource_id=setting_name,
                action="changed",
                outcome="success",
                metadata={
                    "old_value": "[REDACTED]" if old_value else None,
                    "new_value": "[REDACTED]" if new_value else None,
                    "setting_name": setting_name,
                },
                data_classification="restricted",
            )
        )

    def user_management(
        self,
        actor_id: int,
        target_user_id: int,
        action: str,
        success: bool = True,
        metadata: Dict = None,
    ):
        """Log user management event."""
        action_types = {
            "created": AuditEventType.USER_CREATED,
            "updated": AuditEventType.USER_UPDATED,
            "deleted": AuditEventType.USER_DELETED,
            "locked": AuditEventType.USER_LOCKED,
            "unlocked": AuditEventType.USER_UNLOCKED,
        }
        event_type = action_types.get(action, AuditEventType.USER_UPDATED)

        self.log(
            AuditEvent(
                event_type=event_type.value,
                actor_id=actor_id,
                resource_type="user",
                resource_id=str(target_user_id),
                action=action,
                outcome="success" if success else "failure",
                metadata=metadata or {},
                data_classification="confidential",
            )
        )

    def system_event(self, event_type: str, details: str = None, metadata: Dict = None):
        """Log system event."""
        system_types = {
            "startup": AuditEventType.SYSTEM_STARTUP,
            "shutdown": AuditEventType.SYSTEM_SHUTDOWN,
            "error": AuditEventType.SYSTEM_ERROR,
            "backup": AuditEventType.SYSTEM_BACKUP_COMPLETED,
            "cleanup": AuditEventType.SYSTEM_CLEANUP_COMPLETED,
        }
        audit_event_type = system_types.get(event_type, AuditEventType.SYSTEM_ERROR)

        self.log(
            AuditEvent(
                event_type=audit_event_type.value,
                resource_type="system",
                action=event_type,
                outcome="completed",
                outcome_reason=details,
                metadata=metadata or {},
                data_classification="internal",
            )
        )


# Global audit logger instance
audit_log = AuditLogger()


# =============================================================================
# Flask Integration
# =============================================================================


def init_audit_logging(app):
    """
    Initialize audit logging for Flask application.

    Args:
        app: Flask application instance
    """
    # Log application startup
    audit_log.system_event(
        "startup", details=f"Flask environment: {app.config.get('ENV', 'unknown')}"
    )

    # Add correlation ID to each request
    @app.before_request
    def add_correlation_id():
        from flask import g, request

        g.correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

    app.logger.info("SOC2 audit logging initialized")
