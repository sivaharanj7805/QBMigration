"""
Comprehensive tests for the webhook API endpoints.

Tests cover:
- Health endpoint
- Header validation (missing headers -> 400)
- HMAC signature verification (invalid -> 401)
- Timestamp freshness (expired -> 401, future -> 401)
- Valid webhooks for all four lifecycle events
- Idempotent webhook processing (duplicate webhook_id)
- Migration not found (404)
- Invalid JSON payload handling
- Edge cases (Z-suffix timestamps, naive timestamps, step truncation, etc.)

Webhook endpoints use HMAC-SHA256 signature auth (not Flask-Login),
so we use the bare ``client`` fixture rather than ``authenticated_client``.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from models.database import db
from models.migration import Migration
from models.user import User

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_signature(webhook_secret, migration_id, timestamp):
    """Generate HMAC-SHA256 signature matching the server's verification logic.

    The server computes:
        hmac.new(secret, f"{migration_id}:{timestamp}".encode(), sha256).hexdigest()
    """
    message = f"{migration_id}:{timestamp}"
    return hmac.new(
        webhook_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestWebhooks:
    """Comprehensive tests for the webhook API."""

    # ---------------------------------------------------------------
    # Fixtures
    # ---------------------------------------------------------------

    @pytest.fixture
    def webhook_secret(self, app):
        """Retrieve the WEBHOOK_SECRET that the running app is configured with."""
        secret = app.config.get("WEBHOOK_SECRET")
        assert secret, "WEBHOOK_SECRET must be configured for webhook tests"
        return secret

    @pytest.fixture
    def webhook_migration(self, db_session, test_user):
        """Create a Migration in 'pending' status with a known migration_id."""
        migration = Migration(
            user_id=test_user.id,
            company_name="Webhook Test Company",
            qb_file_name="webhook_test.qbw",
            data_size_bytes=500000,
            status="pending",
        )
        db_session.add(migration)
        db_session.commit()
        db_session.refresh(migration)
        return migration

    # ---- header-builder helper ----

    def _make_headers(
        self, webhook_secret, migration_id, timestamp=None, webhook_id=None
    ):
        """Build a complete, validly-signed set of webhook headers."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        if webhook_id is None:
            webhook_id = str(uuid.uuid4())

        signature = make_signature(webhook_secret, migration_id, timestamp)

        return {
            "X-Migration-Id": migration_id,
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Id": webhook_id,
            "Content-Type": "application/json",
        }

    # ===============================================================
    # 1. Health endpoint
    # ===============================================================

    def test_health_endpoint_returns_200(self, client):
        """GET /api/webhooks/health should return 200 with status=healthy."""
        response = client.get("/api/webhooks/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    # ===============================================================
    # 2. Missing headers -> 400
    # ===============================================================

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/webhooks/migration-started",
            "/api/webhooks/migration-progress",
            "/api/webhooks/migration-completed",
            "/api/webhooks/migration-failed",
        ],
    )
    def test_missing_all_headers_returns_400(self, client, endpoint):
        """All webhook endpoints must reject requests with no auth headers."""
        response = client.post(endpoint, json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Missing required headers" in data["error"]

    @pytest.mark.parametrize(
        "omit_header",
        [
            "X-Migration-Id",
            "X-Webhook-Signature",
            "X-Webhook-Timestamp",
            "X-Webhook-Id",
        ],
    )
    def test_missing_single_header_returns_400(
        self, client, webhook_secret, webhook_migration, omit_header
    ):
        """Omitting any single required header must return 400."""
        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )
        del headers[omit_header]

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 400

    # ===============================================================
    # 3. Invalid signature -> 401
    # ===============================================================

    def test_invalid_signature_returns_401(
        self, client, webhook_secret, webhook_migration
    ):
        """A tampered signature must be rejected with 401."""
        timestamp = datetime.now(timezone.utc).isoformat()
        headers = {
            "X-Migration-Id": webhook_migration.migration_id,
            "X-Webhook-Signature": "deadbeef" * 8,  # 64 hex chars, wrong sig
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Id": str(uuid.uuid4()),
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

    def test_signature_for_wrong_migration_id_returns_401(
        self,
        client,
        webhook_secret,
        webhook_migration,
    ):
        """A signature computed for a different migration_id must fail."""
        timestamp = datetime.now(timezone.utc).isoformat()
        wrong_id = str(uuid.uuid4())
        # Sign with the WRONG migration id
        signature = make_signature(webhook_secret, wrong_id, timestamp)

        headers = {
            "X-Migration-Id": webhook_migration.migration_id,  # real id in header
            "X-Webhook-Signature": signature,  # signed with wrong_id
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 401

    # ===============================================================
    # 4. Expired timestamp -> 401
    # ===============================================================

    def test_expired_timestamp_returns_401(
        self, client, webhook_secret, webhook_migration
    ):
        """A timestamp older than WEBHOOK_REPLAY_WINDOW_MINUTES must be rejected."""
        old_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
            timestamp=old_timestamp,
        )

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert (
            "expired" in data.get("error", "").lower()
            or "verification failed" in data.get("error", "").lower()
        )

    # ===============================================================
    # 5. Future timestamp -> 401
    # ===============================================================

    def test_future_timestamp_returns_401(
        self, client, webhook_secret, webhook_migration
    ):
        """A timestamp more than 30 seconds in the future must be rejected."""
        future_timestamp = (
            datetime.now(timezone.utc) + timedelta(minutes=5)
        ).isoformat()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
            timestamp=future_timestamp,
        )

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert (
            "future" in data.get("error", "").lower()
            or "verification failed" in data.get("error", "").lower()
        )

    # ===============================================================
    # 6. Valid signature — migration-started
    # ===============================================================

    def test_migration_started_valid_signature(
        self, client, webhook_secret, webhook_migration, db_session
    ):
        """A validly-signed migration-started webhook should return 200
        and transition the migration to 'processing' status.

        ``mark_as_processing(instance_id)`` requires the migration to be
        in 'provisioning' or 'uploaded' status, so we set it to 'uploaded'
        before calling the endpoint with an instance_id.
        """
        # mark_as_processing requires 'provisioning' or 'uploaded'
        webhook_migration.status = "uploaded"
        db_session.commit()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={"instance_id": "i-test123456"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        # Verify the migration was updated
        db_session.expire_all()
        updated = (
            db_session.query(Migration)
            .filter_by(
                migration_id=webhook_migration.migration_id,
            )
            .first()
        )
        assert updated is not None
        assert updated.status == "processing"
        assert updated.aws_instance_id == "i-test123456"

    def test_migration_started_without_instance_id(
        self,
        client,
        webhook_secret,
        webhook_migration,
        db_session,
    ):
        """migration-started without instance_id should still succeed,
        falling back to directly setting status='processing'.
        """
        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        db_session.expire_all()
        updated = (
            db_session.query(Migration)
            .filter_by(
                migration_id=webhook_migration.migration_id,
            )
            .first()
        )
        assert updated.status == "processing"

    # ===============================================================
    # 7. Valid signature — migration-progress with progress data
    # ===============================================================

    def test_migration_progress_valid_signature(
        self, client, webhook_secret, webhook_migration, db_session
    ):
        """migration-progress should update progress_percent and current_step."""
        webhook_migration.status = "processing"
        db_session.commit()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={
                "progress_percent": 42,
                "current_step": "Migrating invoices",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        db_session.expire_all()
        updated = (
            db_session.query(Migration)
            .filter_by(
                migration_id=webhook_migration.migration_id,
            )
            .first()
        )
        assert updated.progress_percent == 42
        assert updated.current_step == "Migrating invoices"

    def test_migration_progress_clamps_to_100(
        self, client, webhook_secret, webhook_migration, db_session
    ):
        """progress_percent greater than 100 should be clamped to 100."""
        webhook_migration.status = "processing"
        db_session.commit()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={"progress_percent": 150},
        )
        assert response.status_code == 200

        db_session.expire_all()
        updated = (
            db_session.query(Migration)
            .filter_by(
                migration_id=webhook_migration.migration_id,
            )
            .first()
        )
        assert updated.progress_percent == 100

    # ===============================================================
    # 8. Valid signature — migration-completed
    # ===============================================================

    def test_migration_completed_valid_signature(
        self, client, webhook_secret, webhook_migration, db_session
    ):
        """migration-completed should mark the migration as completed."""
        # mark_as_completed requires 'processing' status
        webhook_migration.status = "processing"
        db_session.commit()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-completed",
            headers=headers,
            json={
                "results": {
                    "customers": 10,
                    "vendors": 5,
                    "invoices": 100,
                    "total": 115,
                    "trial_balance": {
                        "is_balanced": True,
                        "source_total": 50000.00,
                        "destination_total": 50000.00,
                    },
                },
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        db_session.expire_all()
        updated = (
            db_session.query(Migration)
            .filter_by(
                migration_id=webhook_migration.migration_id,
            )
            .first()
        )
        assert updated.status == "completed"
        assert updated.progress_percent == 100
        assert updated.customers_migrated == 10
        assert updated.total_records_migrated == 115

    # ===============================================================
    # 9. Valid signature — migration-failed
    # ===============================================================

    def test_migration_failed_valid_signature(
        self, client, webhook_secret, webhook_migration, db_session
    ):
        """migration-failed should mark the migration as failed with error details."""
        webhook_migration.status = "processing"
        db_session.commit()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-failed",
            headers=headers,
            json={
                "error": "QuickBooks file is corrupted",
                "error_code": "QB_FILE_CORRUPT",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        db_session.expire_all()
        updated = (
            db_session.query(Migration)
            .filter_by(
                migration_id=webhook_migration.migration_id,
            )
            .first()
        )
        assert updated.status == "failed"
        assert updated.error_code == "QB_FILE_CORRUPT"

    def test_migration_failed_without_error_details(
        self,
        client,
        webhook_secret,
        webhook_migration,
        db_session,
    ):
        """migration-failed with empty body should use defaults."""
        webhook_migration.status = "processing"
        db_session.commit()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-failed",
            headers=headers,
            json={},
        )
        assert response.status_code == 200

        db_session.expire_all()
        updated = (
            db_session.query(Migration)
            .filter_by(
                migration_id=webhook_migration.migration_id,
            )
            .first()
        )
        assert updated.status == "failed"
        assert updated.error_code == "UNKNOWN_ERROR"

    # ===============================================================
    # 10. Idempotent webhook processing (duplicate webhook_id)
    # ===============================================================

    def test_duplicate_webhook_id_is_idempotent(
        self, client, webhook_secret, webhook_migration, db_session
    ):
        """Sending the same webhook_id twice should return 200 with
        ``idempotent=True`` on the second call.
        """
        webhook_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        signature = make_signature(
            webhook_secret,
            webhook_migration.migration_id,
            timestamp,
        )

        headers = {
            "X-Migration-Id": webhook_migration.migration_id,
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Id": webhook_id,
            "Content-Type": "application/json",
        }

        # First call -- should process normally
        resp1 = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={"instance_id": "i-first"},
        )
        assert resp1.status_code == 200
        assert resp1.get_json()["success"] is True

        # Second call with SAME webhook_id -- should be idempotent
        resp2 = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={"instance_id": "i-second"},
        )
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2["success"] is True
        assert data2.get("idempotent") is True
        assert data2.get("message") == "Already processed"

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/webhooks/migration-progress",
            "/api/webhooks/migration-completed",
            "/api/webhooks/migration-failed",
        ],
    )
    def test_duplicate_webhook_id_idempotent_all_endpoints(
        self,
        client,
        webhook_secret,
        webhook_migration,
        db_session,
        endpoint,
    ):
        """All webhook endpoints should handle duplicate webhook_id idempotently."""
        webhook_migration.status = "processing"
        db_session.commit()

        webhook_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        signature = make_signature(
            webhook_secret,
            webhook_migration.migration_id,
            timestamp,
        )

        headers = {
            "X-Migration-Id": webhook_migration.migration_id,
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Id": webhook_id,
            "Content-Type": "application/json",
        }

        payload = {}
        if "progress" in endpoint:
            payload = {"progress_percent": 50, "current_step": "Testing"}
        elif "completed" in endpoint:
            payload = {
                "results": {
                    "trial_balance": {
                        "is_balanced": True,
                        "source_total": 1000.0,
                        "destination_total": 1000.0,
                    },
                }
            }
        elif "failed" in endpoint:
            payload = {"error": "test error", "error_code": "TEST_ERROR"}

        # First call
        resp1 = client.post(endpoint, headers=headers, json=payload)
        assert resp1.status_code == 200

        # Duplicate call
        resp2 = client.post(endpoint, headers=headers, json=payload)
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2.get("idempotent") is True

    # ===============================================================
    # 11. Migration not found -> 404
    # ===============================================================

    def test_migration_not_found_returns_404(
        self, client, webhook_secret, db_session, test_user
    ):
        """Referencing a non-existent migration_id should return 404."""
        fake_migration_id = str(uuid.uuid4())
        headers = self._make_headers(
            webhook_secret,
            fake_migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/webhooks/migration-progress",
            "/api/webhooks/migration-completed",
            "/api/webhooks/migration-failed",
        ],
    )
    def test_migration_not_found_all_endpoints(
        self, client, webhook_secret, db_session, test_user, endpoint
    ):
        """All webhook endpoints should return 404 for unknown migration_id."""
        fake_migration_id = str(uuid.uuid4())
        headers = self._make_headers(webhook_secret, fake_migration_id)

        response = client.post(endpoint, headers=headers, json={})
        assert response.status_code == 404

    # ===============================================================
    # 12. Invalid / malformed JSON payload
    # ===============================================================

    def test_non_json_content_type_returns_500(
        self, client, webhook_secret, webhook_migration
    ):
        """Sending a non-JSON Content-Type triggers an UnsupportedMediaType
        exception inside ``request.get_json()`` (Flask default behaviour
        with ``silent=False``).  The generic exception handler catches it
        and returns 500.
        """
        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )
        # Override Content-Type to send non-JSON
        headers["Content-Type"] = "text/plain"

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            data="this is not json",
        )
        # get_json() raises UnsupportedMediaType, caught by outer handler -> 500
        assert response.status_code == 500

    def test_malformed_json_body_returns_500(
        self,
        client,
        webhook_secret,
        webhook_migration,
        db_session,
    ):
        """Malformed JSON with ``Content-Type: application/json`` causes
        ``get_json()`` to raise BadRequest.  The outer exception handler
        catches it and returns 500.
        """
        webhook_migration.status = "processing"
        db_session.commit()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            data="{invalid json!!!",
            content_type="application/json",
        )
        assert response.status_code == 500

    def test_empty_json_body_accepted(
        self, client, webhook_secret, webhook_migration, db_session
    ):
        """An empty JSON body ``{}`` should be accepted gracefully.
        The endpoint treats missing fields as defaults.
        """
        webhook_migration.status = "processing"
        db_session.commit()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )

        response = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={},
        )
        assert response.status_code == 200

        db_session.expire_all()
        updated = (
            db_session.query(Migration)
            .filter_by(
                migration_id=webhook_migration.migration_id,
            )
            .first()
        )
        # Defaults: progress_percent=0, current_step=''
        assert updated.progress_percent == 0

    # ===============================================================
    # Additional edge-case tests
    # ===============================================================

    def test_timestamp_with_z_suffix_accepted(
        self, client, webhook_secret, webhook_migration
    ):
        """Timestamps ending with 'Z' (common in JavaScript) should be
        accepted because the server replaces 'Z' with '+00:00'.
        """
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
            timestamp=ts,
        )

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 200

    def test_timestamp_without_timezone_accepted(
        self, client, webhook_secret, webhook_migration
    ):
        """Naive ISO timestamps (no tz offset) should be treated as UTC."""
        ts = datetime.utcnow().isoformat()  # e.g. 2026-02-03T05:30:00.123456
        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
            timestamp=ts,
        )

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 200

    def test_slightly_future_timestamp_within_tolerance(
        self,
        client,
        webhook_secret,
        webhook_migration,
    ):
        """A timestamp up to 30 seconds in the future should be accepted
        (the server allows a 30-second clock-skew window).
        """
        ts = (datetime.now(timezone.utc) + timedelta(seconds=20)).isoformat()
        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
            timestamp=ts,
        )

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 200

    def test_progress_step_truncated_to_255(
        self, client, webhook_secret, webhook_migration, db_session
    ):
        """current_step longer than 255 characters should be truncated."""
        webhook_migration.status = "processing"
        db_session.commit()

        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
        )
        long_step = "X" * 500

        response = client.post(
            "/api/webhooks/migration-progress",
            headers=headers,
            json={"progress_percent": 50, "current_step": long_step},
        )
        assert response.status_code == 200

        db_session.expire_all()
        updated = (
            db_session.query(Migration)
            .filter_by(
                migration_id=webhook_migration.migration_id,
            )
            .first()
        )
        assert len(updated.current_step) == 255

    def test_webhook_secret_not_configured_returns_401(
        self,
        client,
        app,
        webhook_migration,
    ):
        """When WEBHOOK_SECRET is unset, all webhooks must fail-closed (401)."""
        original_secret = app.config.get("WEBHOOK_SECRET")
        try:
            app.config["WEBHOOK_SECRET"] = None

            timestamp = datetime.now(timezone.utc).isoformat()
            headers = {
                "X-Migration-Id": webhook_migration.migration_id,
                "X-Webhook-Signature": "anything",
                "X-Webhook-Timestamp": timestamp,
                "X-Webhook-Id": str(uuid.uuid4()),
                "Content-Type": "application/json",
            }

            response = client.post(
                "/api/webhooks/migration-started",
                headers=headers,
                json={},
            )
            assert response.status_code == 401
            data = response.get_json()
            assert (
                "not configured" in data["error"].lower()
                or "verification failed" in data["error"].lower()
            )
        finally:
            # Always restore to avoid polluting other tests
            app.config["WEBHOOK_SECRET"] = original_secret

    def test_invalid_timestamp_format_returns_401(
        self, client, webhook_secret, webhook_migration
    ):
        """A non-ISO timestamp string should be rejected."""
        bad_ts = "not-a-timestamp"
        headers = self._make_headers(
            webhook_secret,
            webhook_migration.migration_id,
            timestamp=bad_ts,
        )

        response = client.post(
            "/api/webhooks/migration-started",
            headers=headers,
            json={},
        )
        assert response.status_code == 401
