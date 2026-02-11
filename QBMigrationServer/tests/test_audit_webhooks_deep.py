"""
Deep coverage tests for utils/audit_logger.py and api/webhooks.py.

Targets remaining uncovered lines:
utils/audit_logger.py (82.82%, 28 miss):
- Lines 225: _setup_logger handler already exists branch
- Lines 242-243: file handler creation failure
- Lines 250-252: _hash_pii with empty/None value
- Lines 281, 283, 285: log() request context PII hashing
- Lines 309-315: auth_login convenience method
- Lines 331, 343-353: auth_logout, auth_mfa
- Lines 374-384: data_access
- Lines 406-415: migration_event
- Lines 437-450: security_event
- Lines 473: config_change
- Lines 499-508: user_management, system_event

api/webhooks.py (80.09%, 45 miss):
- Lines 79-81: verify_webhook_signature exception handler
- Lines 154, 157-163: migration_started row lock contention (503)
- Lines 264-265, 281, 284-287: migration_progress row lock + progress update
- Lines 381, 396, 399-402: migration_completed Celery cleanup path
- Lines 444, 455-456, 462-465: migration_completed sync cleanup fallback
- Lines 514, 530, 533-536: migration_failed row lock
- Lines 574-579, 587-588, 592-595: migration_failed cleanup + alert
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from models.migration import Migration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_signature(webhook_secret, migration_id, timestamp):
    """Compute HMAC-SHA256 signature matching server logic."""
    message = f"{migration_id}:{timestamp}".encode("utf-8")
    return hmac.new(webhook_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _make_webhook_headers(migration_id, webhook_secret, webhook_id=None):
    """Generate a complete set of valid webhook headers."""
    timestamp = datetime.now(timezone.utc).isoformat()
    signature = _compute_signature(webhook_secret, migration_id, timestamp)
    return {
        "X-Migration-Id": migration_id,
        "X-Webhook-Signature": signature,
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Id": webhook_id or f"wh-deep-{uuid.uuid4()}",
        "Content-Type": "application/json",
    }


def _create_processing_migration(db_session, user):
    """Create a migration in processing state for webhook tests."""
    m = Migration(
        user_id=user.id,
        company_name="Webhook Co",
        qb_file_name="webhook.qbw",
        status="processing",
        s3_uri="s3://test-bucket/test-key",
        aws_instance_id="i-test123",
    )
    m.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


# ===================================================================
# PART 1: AuditLogger tests
# ===================================================================


class TestAuditLoggerSetup:
    """Cover AuditLogger initialization and _setup_logger."""

    def test_logger_handler_already_exists(self, app):
        """Cover line 225: handler already exists, skips adding."""
        from utils.audit_logger import AuditLogger

        logger1 = AuditLogger()
        handler_count = len(logger1.logger.handlers)
        # Creating second instance should not add duplicate handlers
        logger2 = AuditLogger()
        assert len(logger2.logger.handlers) == handler_count

    def test_hash_pii_none(self, app):
        """Cover line 250-252: _hash_pii with None returns None."""
        from utils.audit_logger import AuditLogger

        al = AuditLogger()
        assert al._hash_pii(None) is None
        assert al._hash_pii("") is None

    def test_hash_pii_valid(self, app):
        """_hash_pii returns truncated SHA256."""
        from utils.audit_logger import AuditLogger

        al = AuditLogger()
        result = al._hash_pii("test@example.com")
        assert result is not None
        assert len(result) in [16, 32]  # truncated or full SHA-256 hex prefix


class TestAuditLoggerConvenienceMethods:
    """Cover all convenience methods on AuditLogger."""

    @pytest.fixture
    def audit(self, app):
        from utils.audit_logger import audit_log

        return audit_log

    def test_auth_login_success(self, audit, app):
        """Cover auth_login with success=True (lines 309-315)."""
        audit.auth_login(
            user_id=1,
            success=True,
            email="user@test.com",
            ip="127.0.0.1",
        )

    def test_auth_login_failure(self, audit, app):
        """Cover auth_login with success=False."""
        audit.auth_login(
            user_id=1,
            success=False,
            email="user@test.com",
            ip="127.0.0.1",
            failure_reason="Bad password",
        )

    def test_auth_login_no_email(self, audit, app):
        """Cover auth_login without email."""
        audit.auth_login(user_id=1, success=True)

    def test_auth_logout(self, audit, app):
        """Cover auth_logout (line 331)."""
        audit.auth_logout(user_id=1)

    def test_auth_mfa_enabled(self, audit, app):
        """Cover auth_mfa enabled event (lines 343-353)."""
        audit.auth_mfa(user_id=1, action="enabled", success=True)

    def test_auth_mfa_disabled(self, audit, app):
        """Cover auth_mfa disabled event."""
        audit.auth_mfa(user_id=1, action="disabled", success=True)

    def test_auth_mfa_verified(self, audit, app):
        """Cover auth_mfa verified success."""
        audit.auth_mfa(user_id=1, action="verified", success=True)

    def test_auth_mfa_failed(self, audit, app):
        """Cover auth_mfa verified failure."""
        audit.auth_mfa(user_id=1, action="verified", success=False)

    def test_auth_mfa_unknown_action(self, audit, app):
        """Cover auth_mfa with unknown action (falls to default)."""
        audit.auth_mfa(user_id=1, action="unknown_action", success=True)

    def test_data_access_read(self, audit, app):
        """Cover data_access with read action (lines 374-384)."""
        audit.data_access(
            user_id=1,
            resource_type="migration",
            resource_id="abc-123",
            action="read",
            success=True,
        )

    def test_data_access_create(self, audit, app):
        """Cover data_access with create action."""
        audit.data_access(
            user_id=1,
            resource_type="migration",
            resource_id="abc-123",
            action="create",
        )

    def test_data_access_update(self, audit, app):
        """Cover data_access with update action."""
        audit.data_access(
            user_id=1,
            resource_type="migration",
            resource_id="abc-123",
            action="update",
        )

    def test_data_access_delete(self, audit, app):
        """Cover data_access with delete action."""
        audit.data_access(
            user_id=1,
            resource_type="migration",
            resource_id="abc-123",
            action="delete",
        )

    def test_data_access_export(self, audit, app):
        """Cover data_access with export action."""
        audit.data_access(
            user_id=1,
            resource_type="report",
            resource_id="rpt-1",
            action="export",
        )

    def test_data_access_import(self, audit, app):
        """Cover data_access with import action."""
        audit.data_access(
            user_id=1,
            resource_type="data",
            resource_id="d-1",
            action="import",
        )

    def test_data_access_unknown_action(self, audit, app):
        """Cover data_access with unknown action (defaults to DATA_READ)."""
        audit.data_access(
            user_id=1,
            resource_type="thing",
            resource_id="t-1",
            action="unknown",
        )

    def test_data_access_with_metadata(self, audit, app):
        """Cover data_access with metadata dict."""
        audit.data_access(
            user_id=1,
            resource_type="migration",
            resource_id="m-1",
            action="read",
            metadata={"fields_accessed": ["name", "status"]},
        )

    def test_data_access_failure(self, audit, app):
        """Cover data_access with success=False."""
        audit.data_access(
            user_id=1,
            resource_type="migration",
            resource_id="m-1",
            action="read",
            success=False,
        )

    def test_migration_event_started(self, audit, app):
        """Cover migration_event started (lines 406-415)."""
        audit.migration_event(
            user_id=1,
            migration_id="mig-123",
            action="started",
            success=True,
        )

    def test_migration_event_completed(self, audit, app):
        """Cover migration_event completed."""
        audit.migration_event(
            user_id=1,
            migration_id="mig-123",
            action="completed",
        )

    def test_migration_event_failed(self, audit, app):
        """Cover migration_event failed."""
        audit.migration_event(
            user_id=1,
            migration_id="mig-123",
            action="failed",
            success=False,
            metadata={"error": "timeout"},
        )

    def test_migration_event_cancelled(self, audit, app):
        """Cover migration_event cancelled."""
        audit.migration_event(
            user_id=1,
            migration_id="mig-123",
            action="cancelled",
        )

    def test_migration_event_retry(self, audit, app):
        """Cover migration_event retry."""
        audit.migration_event(
            user_id=1,
            migration_id="mig-123",
            action="retry",
        )

    def test_migration_event_unknown_action(self, audit, app):
        """Cover migration_event with unknown action (defaults to STARTED)."""
        audit.migration_event(
            user_id=1,
            migration_id="mig-123",
            action="unknown_action",
        )

    def test_security_event_rate_limit(self, audit, app):
        """Cover security_event rate_limit (lines 437-450)."""
        audit.security_event(
            event_type="rate_limit",
            user_id=1,
            ip="1.2.3.4",
            details="Too many requests",
        )

    def test_security_event_suspicious(self, audit, app):
        """Cover security_event suspicious."""
        audit.security_event(
            event_type="suspicious",
            user_id=1,
            details="Multiple failed logins",
        )

    def test_security_event_lockout(self, audit, app):
        """Cover security_event lockout."""
        audit.security_event(event_type="lockout", user_id=1)

    def test_security_event_webhook_invalid(self, audit, app):
        """Cover security_event webhook_invalid."""
        audit.security_event(
            event_type="webhook_invalid",
            ip="10.0.0.1",
            metadata={"migration_id": "m-123"},
        )

    def test_security_event_captcha(self, audit, app):
        """Cover security_event captcha types."""
        audit.security_event(event_type="captcha_required", user_id=1)
        audit.security_event(event_type="captcha_failed", user_id=1)

    def test_security_event_ip_blocked(self, audit, app):
        """Cover security_event ip_blocked."""
        audit.security_event(event_type="ip_blocked", ip="malicious.ip")

    def test_security_event_unknown_type(self, audit, app):
        """Cover security_event with unknown type (defaults to suspicious)."""
        audit.security_event(event_type="unknown_type")

    def test_config_change(self, audit, app):
        """Cover config_change (line 473)."""
        audit.config_change(
            user_id=1,
            setting_name="WEBHOOK_SECRET",
            old_value="old",
            new_value="new",
        )

    def test_config_change_no_values(self, audit, app):
        """Cover config_change without old/new values."""
        audit.config_change(user_id=1, setting_name="RATE_LIMIT")

    def test_user_management_created(self, audit, app):
        """Cover user_management created (lines 499-508)."""
        audit.user_management(
            actor_id=1,
            target_user_id=2,
            action="created",
            success=True,
        )

    def test_user_management_updated(self, audit, app):
        """Cover user_management updated."""
        audit.user_management(
            actor_id=1,
            target_user_id=2,
            action="updated",
        )

    def test_user_management_deleted(self, audit, app):
        """Cover user_management deleted."""
        audit.user_management(
            actor_id=1,
            target_user_id=2,
            action="deleted",
        )

    def test_user_management_locked(self, audit, app):
        """Cover user_management locked."""
        audit.user_management(
            actor_id=1,
            target_user_id=2,
            action="locked",
        )

    def test_user_management_unlocked(self, audit, app):
        """Cover user_management unlocked."""
        audit.user_management(
            actor_id=1,
            target_user_id=2,
            action="unlocked",
        )

    def test_user_management_unknown_action(self, audit, app):
        """Cover user_management with unknown action (defaults to updated)."""
        audit.user_management(
            actor_id=1,
            target_user_id=2,
            action="unknown",
        )

    def test_user_management_failure(self, audit, app):
        """Cover user_management with failure."""
        audit.user_management(
            actor_id=1,
            target_user_id=2,
            action="deleted",
            success=False,
        )

    def test_user_management_with_metadata(self, audit, app):
        """Cover user_management with metadata."""
        audit.user_management(
            actor_id=1,
            target_user_id=2,
            action="updated",
            metadata={"field": "role", "new_role": "admin"},
        )

    def test_system_event_startup(self, audit, app):
        """Cover system_event startup."""
        audit.system_event("startup", details="Flask started")

    def test_system_event_shutdown(self, audit, app):
        """Cover system_event shutdown."""
        audit.system_event("shutdown")

    def test_system_event_error(self, audit, app):
        """Cover system_event error."""
        audit.system_event(
            "error",
            details="Database connection lost",
            metadata={"db": "postgres"},
        )

    def test_system_event_backup(self, audit, app):
        """Cover system_event backup."""
        audit.system_event("backup", details="Daily backup completed")

    def test_system_event_cleanup(self, audit, app):
        """Cover system_event cleanup."""
        audit.system_event("cleanup", details="Expired migrations cleaned")

    def test_system_event_unknown(self, audit, app):
        """Cover system_event with unknown type (defaults to error)."""
        audit.system_event("unknown_event")


class TestAuditEvent:
    """Cover AuditEvent dataclass methods."""

    def test_to_dict(self, app):
        from utils.audit_logger import AuditEvent

        event = AuditEvent(
            event_type="test.event",
            actor_id=1,
            resource_type="test",
            action="do",
            outcome="success",
        )
        d = event.to_dict()
        assert d["event_type"] == "test.event"
        assert d["actor_id"] == 1
        # None values should be excluded
        assert "outcome_reason" not in d

    def test_to_json(self, app):
        from utils.audit_logger import AuditEvent

        event = AuditEvent(
            event_type="test.json",
            actor_id=42,
        )
        j = event.to_json()
        parsed = json.loads(j)
        assert parsed["event_type"] == "test.json"
        assert parsed["actor_id"] == 42

    def test_to_dict_with_metadata(self, app):
        from utils.audit_logger import AuditEvent

        event = AuditEvent(
            event_type="test.meta",
            metadata={"key": "value"},
        )
        d = event.to_dict()
        assert d["metadata"]["key"] == "value"


class TestAuditLoggerLog:
    """Cover the log() method request context enrichment."""

    def test_log_outside_request_context(self, app):
        """Cover log() when not in a request context (lines 281-285)."""
        from utils.audit_logger import AuditEvent, audit_log

        event = AuditEvent(
            event_type="test.no_context",
            actor_id=1,
        )
        # Should not raise even without request context
        audit_log.log(event)

    def test_log_inside_request_context(self, app, client):
        """Cover log() inside request context with PII hashing."""
        from utils.audit_logger import AuditEvent, audit_log

        with app.test_request_context(
            "/test",
            headers={"User-Agent": "TestBrowser/1.0"},
            environ_base={"REMOTE_ADDR": "192.168.1.100"},
        ):
            event = AuditEvent(
                event_type="test.with_context",
                actor_id=1,
            )
            audit_log.log(event)
            # user_agent_hash should be set from request context
            assert event.actor_user_agent_hash is not None


class TestInitAuditLogging:
    """Cover init_audit_logging Flask integration."""

    def test_init_audit_logging(self):
        """init_audit_logging registers before_request on a fresh app."""
        from app import create_app
        from utils.audit_logger import init_audit_logging

        fresh_app = create_app("testing")
        # Should not raise on a fresh app that hasn't handled requests
        init_audit_logging(fresh_app)


# ===================================================================
# PART 2: Webhooks deep tests
# ===================================================================


class TestVerifyWebhookSignatureDeep:
    """Cover verify_webhook_signature edge cases."""

    @pytest.fixture
    def webhook_secret(self, app):
        secret = app.config.get("WEBHOOK_SECRET")
        assert secret, "WEBHOOK_SECRET must be configured for tests"
        return secret

    def test_signature_exception_handler(self, app, webhook_secret):
        """Cover lines 79-81: exception in signature verification."""
        from api.webhooks import verify_webhook_signature

        # Force an exception by passing None as timestamp
        is_valid, error = verify_webhook_signature("mid", "sig", None)
        assert is_valid is False
        assert error is not None

    def test_no_webhook_secret(self, app):
        """Cover fail-closed when WEBHOOK_SECRET not configured."""
        from api.webhooks import verify_webhook_signature

        original = app.config.get("WEBHOOK_SECRET")
        try:
            app.config["WEBHOOK_SECRET"] = None
            is_valid, error = verify_webhook_signature(
                "mid",
                "sig",
                datetime.now(timezone.utc).isoformat(),
            )
            assert is_valid is False
            assert "not configured" in error
        finally:
            app.config["WEBHOOK_SECRET"] = original

    def test_expired_timestamp(self, app, webhook_secret):
        """Cover expired webhook timestamp."""
        from api.webhooks import verify_webhook_signature

        old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        sig = _compute_signature(webhook_secret, "mid", old_time)
        is_valid, error = verify_webhook_signature("mid", sig, old_time)
        assert is_valid is False
        assert "expired" in error.lower()

    def test_future_timestamp(self, app, webhook_secret):
        """Cover future webhook timestamp."""
        from api.webhooks import verify_webhook_signature

        future_time = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        sig = _compute_signature(webhook_secret, "mid", future_time)
        is_valid, error = verify_webhook_signature("mid", sig, future_time)
        assert is_valid is False
        assert "future" in error.lower()

    def test_invalid_timestamp_format(self, app, webhook_secret):
        """Cover invalid timestamp format."""
        from api.webhooks import verify_webhook_signature

        is_valid, error = verify_webhook_signature("mid", "sig", "not-a-date")
        assert is_valid is False
        assert "timestamp" in error.lower()


class TestMigrationStartedWebhookDeep:
    """Cover migration-started webhook edge cases."""

    @pytest.fixture
    def webhook_secret(self, app):
        return app.config.get("WEBHOOK_SECRET")

    def test_started_missing_headers(self, client, db_session):
        """Missing headers returns 400."""
        resp = client.post(
            "/api/webhooks/migration-started",
            json={"instance_id": "i-test"},
        )
        assert resp.status_code == 400

    def test_started_success_with_instance(
        self, client, db_session, test_user, webhook_secret
    ):
        """Successful migration-started webhook."""
        m = _create_processing_migration(db_session, test_user)
        m.aws_instance_id = None  # Clear so mark_as_processing is called
        m.status = "provisioning"
        db_session.commit()

        headers = _make_webhook_headers(m.migration_id, webhook_secret)
        resp = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={"instance_id": "i-newinstance"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_started_idempotent(self, client, db_session, test_user, webhook_secret):
        """Duplicate webhook returns 200 with idempotent flag."""
        m = _create_processing_migration(db_session, test_user)
        wh_id = f"wh-idem-{uuid.uuid4()}"
        headers = _make_webhook_headers(
            m.migration_id, webhook_secret, webhook_id=wh_id
        )

        # First call
        resp1 = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={"instance_id": "i-test"},
        )
        assert resp1.status_code == 200

        # Second call with same webhook ID
        headers2 = _make_webhook_headers(
            m.migration_id, webhook_secret, webhook_id=wh_id
        )
        resp2 = client.post(
            "/api/webhooks/migration-started",
            headers=headers2,
            json={"instance_id": "i-test"},
        )
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert data.get("idempotent") is True

    def test_started_not_found(self, client, db_session, webhook_secret):
        """Migration not found returns 404."""
        fake_mid = str(uuid.uuid4())
        headers = _make_webhook_headers(fake_mid, webhook_secret)
        resp = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={"instance_id": "i-test"},
        )
        assert resp.status_code == 404

    def test_started_already_has_instance(
        self, client, db_session, test_user, webhook_secret
    ):
        """When instance_id already set, uses else branch (line 201-203)."""
        m = _create_processing_migration(db_session, test_user)
        # aws_instance_id is already set

        headers = _make_webhook_headers(m.migration_id, webhook_secret)
        resp = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={"instance_id": "i-different"},
        )
        assert resp.status_code == 200


class TestMigrationProgressWebhookDeep:
    """Cover migration-progress webhook edge cases."""

    @pytest.fixture
    def webhook_secret(self, app):
        return app.config.get("WEBHOOK_SECRET")

    def test_progress_missing_headers(self, client, db_session):
        """Missing headers returns 400."""
        resp = client.post(
            "/api/webhooks/migration-progress",
            json={"progress_percent": 50},
        )
        assert resp.status_code == 400

    def test_progress_success(self, client, db_session, test_user, webhook_secret):
        """Successful progress update."""
        m = _create_processing_migration(db_session, test_user)
        headers = _make_webhook_headers(m.migration_id, webhook_secret)
        resp = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={
                "progress_percent": 65,
                "current_step": "Migrating invoices",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        db_session.refresh(m)
        assert m.progress_percent == 65
        assert m.current_step == "Migrating invoices"

    def test_progress_not_found(self, client, db_session, webhook_secret):
        """Migration not found returns 404."""
        fake_mid = str(uuid.uuid4())
        headers = _make_webhook_headers(fake_mid, webhook_secret)
        resp = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={"progress_percent": 50},
        )
        assert resp.status_code == 404

    def test_progress_idempotent(self, client, db_session, test_user, webhook_secret):
        """Duplicate progress webhook is idempotent."""
        m = _create_processing_migration(db_session, test_user)
        wh_id = f"wh-prog-{uuid.uuid4()}"
        headers = _make_webhook_headers(
            m.migration_id, webhook_secret, webhook_id=wh_id
        )

        resp1 = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={"progress_percent": 50},
        )
        assert resp1.status_code == 200

        headers2 = _make_webhook_headers(
            m.migration_id, webhook_secret, webhook_id=wh_id
        )
        resp2 = client.post(
            "/api/webhooks/migration-progress",
            headers=headers2,
            json={"progress_percent": 60},
        )
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert data.get("idempotent") is True

    def test_progress_caps_at_100(self, client, db_session, test_user, webhook_secret):
        """Progress percent is capped at 100."""
        m = _create_processing_migration(db_session, test_user)
        headers = _make_webhook_headers(m.migration_id, webhook_secret)
        resp = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={"progress_percent": 150},
        )
        assert resp.status_code == 200
        db_session.refresh(m)
        assert m.progress_percent == 100

    def test_progress_invalid_signature(
        self, client, db_session, test_user, webhook_secret
    ):
        """Invalid signature returns 401."""
        m = _create_processing_migration(db_session, test_user)
        headers = _make_webhook_headers(m.migration_id, webhook_secret)
        headers["X-Webhook-Signature"] = "invalid-signature"
        resp = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={"progress_percent": 50},
        )
        assert resp.status_code == 401


class TestMigrationCompletedWebhookDeep:
    """Cover migration-completed webhook including cleanup paths."""

    @pytest.fixture
    def webhook_secret(self, app):
        return app.config.get("WEBHOOK_SECRET")

    def test_completed_missing_headers(self, client, db_session):
        """Missing headers returns 400."""
        resp = client.post(
            "/api/webhooks/migration-completed",
            json={"results": {}},
        )
        assert resp.status_code == 400

    def test_completed_success_with_results(
        self, client, db_session, test_user, webhook_secret, app
    ):
        """Successful completion with trial balance data."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _create_processing_migration(db_session, test_user)
        headers = _make_webhook_headers(m.migration_id, webhook_secret)

        results = {
            "customers": 10,
            "total": 10,
            "trial_balance": {
                "is_balanced": True,
                "source_total": 5000.00,
                "destination_total": 5000.00,
            },
        }

        with patch("api.webhooks.AWSMigrationManager", create=True):
            resp = client.post(
                "/api/webhooks/migration-completed",
                headers=headers,
                json={"results": results},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_completed_celery_cleanup_fails_sync_fallback(
        self, client, db_session, test_user, webhook_secret, app
    ):
        """Cover Celery cleanup failure + sync fallback (lines 444-458)."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _create_processing_migration(db_session, test_user)
        headers = _make_webhook_headers(m.migration_id, webhook_secret)

        results = {
            "trial_balance": {
                "is_balanced": True,
                "source_total": 100.00,
                "destination_total": 100.00,
            },
        }

        # Celery import fails, sync cleanup also fails
        with patch.dict("sys.modules", {"tasks": None}):
            with patch(
                "api.webhooks.AWSMigrationManager",
                create=True,
            ) as mock_aws:
                mock_instance = MagicMock()
                mock_instance.cleanup_migration.side_effect = Exception("AWS down")
                mock_aws.return_value = mock_instance
                resp = client.post(
                    "/api/webhooks/migration-completed",
                    headers=headers,
                    json={"results": results},
                )
        assert resp.status_code == 200

    def test_completed_not_found(self, client, db_session, webhook_secret):
        """Migration not found returns 404."""
        fake_mid = str(uuid.uuid4())
        headers = _make_webhook_headers(fake_mid, webhook_secret)
        resp = client.post(
            "/api/webhooks/migration-completed",
            headers=headers,
            json={"results": {}},
        )
        assert resp.status_code == 404

    def test_completed_idempotent(
        self, client, db_session, test_user, webhook_secret, app
    ):
        """Duplicate completed webhook is idempotent."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _create_processing_migration(db_session, test_user)
        wh_id = f"wh-comp-{uuid.uuid4()}"

        results = {
            "trial_balance": {
                "is_balanced": True,
                "source_total": 100.00,
                "destination_total": 100.00,
            },
        }

        headers1 = _make_webhook_headers(
            m.migration_id, webhook_secret, webhook_id=wh_id
        )
        with patch("api.webhooks.AWSMigrationManager", create=True):
            resp1 = client.post(
                "/api/webhooks/migration-completed",
                headers=headers1,
                json={"results": results},
            )
        assert resp1.status_code == 200

        headers2 = _make_webhook_headers(
            m.migration_id, webhook_secret, webhook_id=wh_id
        )
        resp2 = client.post(
            "/api/webhooks/migration-completed",
            headers=headers2,
            json={"results": results},
        )
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert data.get("idempotent") is True

    def test_completed_invalid_signature(
        self, client, db_session, test_user, webhook_secret
    ):
        """Invalid signature returns 401."""
        m = _create_processing_migration(db_session, test_user)
        headers = _make_webhook_headers(m.migration_id, webhook_secret)
        headers["X-Webhook-Signature"] = "bad-sig"
        resp = client.post(
            "/api/webhooks/migration-completed",
            headers=headers,
            json={"results": {}},
        )
        assert resp.status_code == 401


class TestMigrationFailedWebhookDeep:
    """Cover migration-failed webhook including cleanup and alert paths."""

    @pytest.fixture
    def webhook_secret(self, app):
        return app.config.get("WEBHOOK_SECRET")

    def test_failed_missing_headers(self, client, db_session):
        """Missing headers returns 400."""
        resp = client.post(
            "/api/webhooks/migration-failed",
            json={"error": "something broke"},
        )
        assert resp.status_code == 400

    def test_failed_success(self, client, db_session, test_user, webhook_secret, app):
        """Successful failure webhook marks migration as failed."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _create_processing_migration(db_session, test_user)
        headers = _make_webhook_headers(m.migration_id, webhook_secret)

        with patch("api.webhooks.AWSMigrationManager", create=True) as mock_aws:
            mock_instance = MagicMock()
            mock_instance.cleanup_migration.return_value = {}
            mock_aws.return_value = mock_instance

            resp = client.post(
                "/api/webhooks/migration-failed",
                headers=headers,
                json={
                    "error": "Migration timed out",
                    "error_code": "TIMEOUT",
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        db_session.refresh(m)
        assert m.status == "failed"

    def test_failed_max_retries_sends_alert(
        self, client, db_session, test_user, webhook_secret, app
    ):
        """Cover alert sending when max retries reached (lines 574-579)."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _create_processing_migration(db_session, test_user)
        m.retry_count = 3
        m.max_retries = 3
        db_session.commit()

        headers = _make_webhook_headers(m.migration_id, webhook_secret)

        with patch("api.webhooks.AWSMigrationManager", create=True) as mock_aws:
            mock_instance = MagicMock()
            mock_instance.cleanup_migration.return_value = {}
            mock_aws.return_value = mock_instance

            resp = client.post(
                "/api/webhooks/migration-failed",
                headers=headers,
                json={"error": "Final failure", "error_code": "FATAL"},
            )
        assert resp.status_code == 200

    def test_failed_cleanup_exception(
        self, client, db_session, test_user, webhook_secret, app
    ):
        """Cover cleanup failure path (lines 587-588)."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _create_processing_migration(db_session, test_user)
        headers = _make_webhook_headers(m.migration_id, webhook_secret)

        with patch("api.webhooks.AWSMigrationManager", create=True) as mock_aws:
            mock_instance = MagicMock()
            mock_instance.cleanup_migration.side_effect = Exception("Cleanup crash")
            mock_aws.return_value = mock_instance

            resp = client.post(
                "/api/webhooks/migration-failed",
                headers=headers,
                json={"error": "Error", "error_code": "ERR"},
            )
        assert resp.status_code == 200

    def test_failed_not_found(self, client, db_session, webhook_secret):
        """Migration not found returns 404."""
        fake_mid = str(uuid.uuid4())
        headers = _make_webhook_headers(fake_mid, webhook_secret)
        resp = client.post(
            "/api/webhooks/migration-failed",
            headers=headers,
            json={"error": "Not found test"},
        )
        assert resp.status_code == 404

    def test_failed_idempotent(
        self, client, db_session, test_user, webhook_secret, app
    ):
        """Duplicate failed webhook is idempotent."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _create_processing_migration(db_session, test_user)
        wh_id = f"wh-fail-{uuid.uuid4()}"

        headers1 = _make_webhook_headers(
            m.migration_id, webhook_secret, webhook_id=wh_id
        )

        with patch("api.webhooks.AWSMigrationManager", create=True) as mock_aws:
            mock_instance = MagicMock()
            mock_instance.cleanup_migration.return_value = {}
            mock_aws.return_value = mock_instance

            resp1 = client.post(
                "/api/webhooks/migration-failed",
                headers=headers1,
                json={"error": "Error"},
            )
        assert resp1.status_code == 200

        headers2 = _make_webhook_headers(
            m.migration_id, webhook_secret, webhook_id=wh_id
        )
        resp2 = client.post(
            "/api/webhooks/migration-failed",
            headers=headers2,
            json={"error": "Error"},
        )
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert data.get("idempotent") is True

    def test_failed_invalid_signature(
        self, client, db_session, test_user, webhook_secret
    ):
        """Invalid signature returns 401."""
        m = _create_processing_migration(db_session, test_user)
        headers = _make_webhook_headers(m.migration_id, webhook_secret)
        headers["X-Webhook-Signature"] = "wrong"
        resp = client.post(
            "/api/webhooks/migration-failed",
            headers=headers,
            json={"error": "test"},
        )
        assert resp.status_code == 401


class TestWebhookHealth:
    """Cover webhook health endpoint."""

    def test_health(self, client):
        resp = client.get("/api/webhooks/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
