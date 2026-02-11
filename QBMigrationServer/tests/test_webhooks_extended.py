"""
Extended tests for api/webhooks.py to improve coverage beyond 80%.

Tests cover:
- verify_webhook_signature function directly (valid, invalid, expired, future, unconfigured)
- migration-started webhook (missing headers, invalid sig, not found, success)
- migration-progress webhook (missing headers, success with progress data)
- migration-completed webhook (missing headers, success with results)
- migration-failed webhook (missing headers, success with error details)
- Webhook health endpoint

Uses HMAC-SHA256 signature verification matching the server's implementation.
"""

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from models.database import db
from models.migration import Migration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_signature(webhook_secret, migration_id, timestamp):
    """Compute HMAC-SHA256 signature matching server logic."""
    message = f"{migration_id}:{timestamp}".encode("utf-8")
    return hmac.new(webhook_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _make_webhook_headers(migration_id, webhook_secret):
    """Generate a complete set of valid webhook headers."""
    timestamp = datetime.now(timezone.utc).isoformat()
    signature = _compute_signature(webhook_secret, migration_id, timestamp)
    return {
        "X-Migration-Id": migration_id,
        "X-Webhook-Signature": signature,
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Id": f"wh-test-{uuid.uuid4()}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# TestVerifyWebhookSignature
# ---------------------------------------------------------------------------


class TestVerifyWebhookSignature:
    """Direct tests for the verify_webhook_signature function."""

    @pytest.fixture
    def webhook_secret(self, app):
        secret = app.config.get("WEBHOOK_SECRET")
        assert secret, "WEBHOOK_SECRET must be configured for tests"
        return secret

    def test_valid_signature(self, app, webhook_secret):
        """A correctly computed HMAC signature should return (True, None)."""
        from api.webhooks import verify_webhook_signature

        migration_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        signature = _compute_signature(webhook_secret, migration_id, timestamp)

        with app.app_context():
            is_valid, error = verify_webhook_signature(
                migration_id, signature, timestamp
            )

        assert is_valid is True
        assert error is None

    def test_invalid_signature(self, app, webhook_secret):
        """A wrong signature should return (False, 'Invalid signature')."""
        from api.webhooks import verify_webhook_signature

        migration_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        bad_signature = "a" * 64

        with app.app_context():
            is_valid, error = verify_webhook_signature(
                migration_id, bad_signature, timestamp
            )

        assert is_valid is False
        assert "Invalid signature" in error

    def test_expired_timestamp(self, app, webhook_secret):
        """A timestamp older than the replay window should be rejected."""
        from api.webhooks import verify_webhook_signature

        migration_id = str(uuid.uuid4())
        old_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        signature = _compute_signature(webhook_secret, migration_id, old_timestamp)

        with app.app_context():
            is_valid, error = verify_webhook_signature(
                migration_id, signature, old_timestamp
            )

        assert is_valid is False
        assert "expired" in error.lower()

    def test_future_timestamp(self, app, webhook_secret):
        """A timestamp far in the future should be rejected."""
        from api.webhooks import verify_webhook_signature

        migration_id = str(uuid.uuid4())
        future_timestamp = (
            datetime.now(timezone.utc) + timedelta(minutes=10)
        ).isoformat()
        signature = _compute_signature(webhook_secret, migration_id, future_timestamp)

        with app.app_context():
            is_valid, error = verify_webhook_signature(
                migration_id, signature, future_timestamp
            )

        assert is_valid is False
        assert "future" in error.lower()

    def test_no_webhook_secret(self, app):
        """When WEBHOOK_SECRET is not configured, verification should fail closed."""
        from api.webhooks import verify_webhook_signature

        migration_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        original = app.config.get("WEBHOOK_SECRET")
        try:
            app.config["WEBHOOK_SECRET"] = None
            with app.app_context():
                is_valid, error = verify_webhook_signature(
                    migration_id, "anything", timestamp
                )
            assert is_valid is False
            assert "not configured" in error.lower()
        finally:
            app.config["WEBHOOK_SECRET"] = original


# ---------------------------------------------------------------------------
# TestMigrationStartedWebhook
# ---------------------------------------------------------------------------


class TestMigrationStartedWebhook:
    """Tests for POST /api/webhooks/migration-started."""

    @pytest.fixture
    def webhook_secret(self, app):
        secret = app.config.get("WEBHOOK_SECRET")
        assert secret, "WEBHOOK_SECRET must be configured"
        return secret

    @pytest.fixture
    def webhook_migration(self, db_session, test_user):
        migration = Migration(
            user_id=test_user.id,
            company_name="Webhook Extended Test",
            qb_file_name="ext_test.qbw",
            data_size_bytes=100000,
            status="uploaded",
        )
        db_session.add(migration)
        db_session.commit()
        db_session.refresh(migration)
        return migration

    def test_missing_headers(self, client, db_session, test_user):
        """POST without required headers should return 400."""
        response = client.post("/api/webhooks/migration-started", json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Missing required headers" in data["error"]

    def test_invalid_signature(self, client, webhook_secret, webhook_migration):
        """POST with wrong signature should return 401."""
        timestamp = datetime.now(timezone.utc).isoformat()
        headers = {
            "X-Migration-Id": webhook_migration.migration_id,
            "X-Webhook-Signature": "bad" * 20,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Id": f"wh-bad-{uuid.uuid4()}",
            "Content-Type": "application/json",
        }
        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False

    def test_migration_not_found(self, client, webhook_secret, db_session, test_user):
        """POST with valid signature but nonexistent migration should return 404."""
        fake_id = str(uuid.uuid4())
        headers = _make_webhook_headers(fake_id, webhook_secret)
        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_success(self, client, webhook_secret, webhook_migration, db_session):
        """Properly signed webhook should return 200 and update migration."""
        headers = _make_webhook_headers(webhook_migration.migration_id, webhook_secret)
        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={"instance_id": "i-ext-test-001"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        db_session.expire_all()
        updated = (
            db.session.query(Migration)
            .filter_by(migration_id=webhook_migration.migration_id)
            .first()
        )
        assert updated.status == "processing"
        assert updated.aws_instance_id == "i-ext-test-001"


# ---------------------------------------------------------------------------
# TestMigrationProgressWebhook
# ---------------------------------------------------------------------------


class TestMigrationProgressWebhook:
    """Tests for POST /api/webhooks/migration-progress."""

    @pytest.fixture
    def webhook_secret(self, app):
        secret = app.config.get("WEBHOOK_SECRET")
        assert secret
        return secret

    @pytest.fixture
    def webhook_migration(self, db_session, test_user):
        migration = Migration(
            user_id=test_user.id,
            company_name="Progress Test",
            qb_file_name="progress.qbw",
            data_size_bytes=200000,
            status="processing",
        )
        db_session.add(migration)
        db_session.commit()
        db_session.refresh(migration)
        return migration

    def test_missing_headers(self, client, db_session, test_user):
        """POST without required headers should return 400."""
        response = client.post("/api/webhooks/migration-progress", json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_success(self, client, webhook_secret, webhook_migration, db_session):
        """Valid progress update should return 200 and update progress."""
        headers = _make_webhook_headers(webhook_migration.migration_id, webhook_secret)
        response = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={"progress_percent": 65, "current_step": "Migrating vendors"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        db_session.expire_all()
        updated = (
            db.session.query(Migration)
            .filter_by(migration_id=webhook_migration.migration_id)
            .first()
        )
        assert updated.progress_percent == 65
        assert updated.current_step == "Migrating vendors"


# ---------------------------------------------------------------------------
# TestMigrationCompletedWebhook
# ---------------------------------------------------------------------------


class TestMigrationCompletedWebhook:
    """Tests for POST /api/webhooks/migration-completed."""

    @pytest.fixture
    def webhook_secret(self, app):
        secret = app.config.get("WEBHOOK_SECRET")
        assert secret
        return secret

    @pytest.fixture
    def webhook_migration(self, db_session, test_user):
        migration = Migration(
            user_id=test_user.id,
            company_name="Completed Test",
            qb_file_name="completed.qbw",
            data_size_bytes=300000,
            status="processing",
        )
        db_session.add(migration)
        db_session.commit()
        db_session.refresh(migration)
        return migration

    def test_missing_headers(self, client, db_session, test_user):
        """POST without required headers should return 400."""
        response = client.post("/api/webhooks/migration-completed", json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_success(self, client, webhook_secret, webhook_migration, db_session):
        """Valid completion webhook should return 200 and mark migration completed."""
        headers = _make_webhook_headers(webhook_migration.migration_id, webhook_secret)
        response = client.post(
            "/api/webhooks/migration-completed",
            headers=headers,
            json={
                "results": {
                    "customers": 25,
                    "vendors": 10,
                    "invoices": 200,
                    "total": 235,
                    "trial_balance": {
                        "is_balanced": True,
                        "source_total": 75000.00,
                        "destination_total": 75000.00,
                    },
                }
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        db_session.expire_all()
        updated = (
            db.session.query(Migration)
            .filter_by(migration_id=webhook_migration.migration_id)
            .first()
        )
        assert updated.status == "completed"
        assert updated.progress_percent == 100


# ---------------------------------------------------------------------------
# TestMigrationFailedWebhook
# ---------------------------------------------------------------------------


class TestMigrationFailedWebhook:
    """Tests for POST /api/webhooks/migration-failed."""

    @pytest.fixture
    def webhook_secret(self, app):
        secret = app.config.get("WEBHOOK_SECRET")
        assert secret
        return secret

    @pytest.fixture
    def webhook_migration(self, db_session, test_user):
        migration = Migration(
            user_id=test_user.id,
            company_name="Failed Test",
            qb_file_name="failed.qbw",
            data_size_bytes=400000,
            status="processing",
        )
        db_session.add(migration)
        db_session.commit()
        db_session.refresh(migration)
        return migration

    def test_missing_headers(self, client, db_session, test_user):
        """POST without required headers should return 400."""
        response = client.post("/api/webhooks/migration-failed", json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_success(self, client, webhook_secret, webhook_migration, db_session):
        """Valid failure webhook should return 200 and mark migration failed."""
        headers = _make_webhook_headers(webhook_migration.migration_id, webhook_secret)
        response = client.post(
            "/api/webhooks/migration-failed",
            headers=headers,
            json={
                "error": "Connection timeout to QuickBooks",
                "error_code": "QB_TIMEOUT",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        db_session.expire_all()
        updated = (
            db.session.query(Migration)
            .filter_by(migration_id=webhook_migration.migration_id)
            .first()
        )
        assert updated.status == "failed"
        assert updated.error_code == "QB_TIMEOUT"


# ---------------------------------------------------------------------------
# TestWebhookHealth
# ---------------------------------------------------------------------------


class TestWebhookHealth:
    """Tests for GET /api/webhooks/health."""

    def test_webhook_health(self, client):
        """Health endpoint should return 200 with status healthy."""
        response = client.get("/api/webhooks/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
