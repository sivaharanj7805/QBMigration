"""
Extended test suite for api/migrations.py endpoints.

Targets uncovered lines:
- start_migration internals (470-690): AWS integration, credential handling
- process_migration alias (727)
- cancel_migration cleanup branches (790-791, 816-821)
- retry_migration edge cases (841, 880-882, 912-917)
- delete_migration edge cases (936, 970-975)
- execute_migration_celery / ImportError (1021-1091)
- get_migration_stats edge cases (1170, 1191-1196)
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from models.migration import Migration
from models.migration_credit import MigrationCredit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_UUID = "00000000-0000-4000-a000-000000000000"
BAD_UUID = "not-a-uuid"


def _create_migration(db_session, user, **overrides):
    """Create a migration with sensible defaults, applying overrides."""
    defaults = {
        "user_id": user.id,
        "company_name": "Test Co",
        "qb_file_name": "test.qbw",
        "status": "pending",
    }
    defaults.update(overrides)
    m = Migration(**defaults)
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


def _create_credit(db_session, user, **overrides):
    """Create a paid/available MigrationCredit for the given user."""
    defaults = {
        "user_id": user.id,
        "tier_type": "starter",
        "transaction_limit": 5000,
        "price_cents": 49700,
        "status": "available",
        "payment_status": "paid",
        "stripe_checkout_session_id": f"cs_{uuid.uuid4().hex[:24]}",
        "stripe_payment_intent_id": f"pi_{uuid.uuid4().hex[:24]}",
    }
    defaults.update(overrides)
    credit = MigrationCredit(**defaults)
    db_session.add(credit)
    db_session.commit()
    db_session.refresh(credit)
    return credit


# ===================================================================
# 1. TestListMigrations
# ===================================================================


class TestListMigrations:
    """GET /api/migrations"""

    def test_list_migrations(self, authenticated_client, db_session, test_user):
        """Returns 200 with migrations array."""
        _create_migration(db_session, test_user)
        resp = authenticated_client.get("/api/migrations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert isinstance(data["migrations"], list)
        assert len(data["migrations"]) >= 1

    def test_list_with_status_filter(self, authenticated_client, db_session, test_user):
        """Filtering by status=pending returns only pending migrations."""
        _create_migration(db_session, test_user, status="pending")
        _create_migration(db_session, test_user, status="completed")
        resp = authenticated_client.get("/api/migrations?status=pending")
        assert resp.status_code == 200
        data = resp.get_json()
        for m in data["migrations"]:
            assert m["status"] == "pending"

    def test_list_invalid_status(self, authenticated_client, db_session):
        """Invalid status filter returns 400."""
        resp = authenticated_client.get("/api/migrations?status=badvalue")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_list_with_pagination(self, authenticated_client, db_session, test_user):
        """Pagination parameters are respected."""
        for i in range(12):
            _create_migration(
                db_session,
                test_user,
                company_name=f"Co {i}",
            )
        resp = authenticated_client.get("/api/migrations?page=1&per_page=10")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["migrations"]) == 10
        assert data["pagination"]["total_items"] == 12
        assert data["pagination"]["has_next"] is True


# ===================================================================
# 2. TestGetMigration
# ===================================================================


class TestGetMigration:
    """GET /api/migrations/<migration_id>"""

    def test_get_migration_success(
        self, authenticated_client, db_session, test_migration
    ):
        """Existing migration returns 200."""
        resp = authenticated_client.get(
            f"/api/migrations/{test_migration.migration_id}"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["migration"]["migration_id"] == test_migration.migration_id

    def test_get_migration_not_found(self, authenticated_client, db_session):
        """Non-existent UUID returns 404."""
        resp = authenticated_client.get(f"/api/migrations/{FAKE_UUID}")
        assert resp.status_code == 404

    def test_get_migration_invalid_uuid(self, authenticated_client, db_session):
        """Non-UUID string returns 400."""
        resp = authenticated_client.get(f"/api/migrations/{BAD_UUID}")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid migration ID" in data["error"]


# ===================================================================
# 3. TestGetMigrationStatus
# ===================================================================


class TestGetMigrationStatus:
    """GET /api/migrations/<migration_id>/status"""

    def test_get_status_success(self, authenticated_client, db_session, test_migration):
        """Returns lightweight status payload."""
        resp = authenticated_client.get(
            f"/api/migrations/{test_migration.migration_id}/status"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["status"] == "pending"

    def test_get_status_not_found(self, authenticated_client, db_session):
        """Non-existent migration returns 404."""
        resp = authenticated_client.get(f"/api/migrations/{FAKE_UUID}/status")
        assert resp.status_code == 404


# ===================================================================
# 4. TestCancelMigration
# ===================================================================


class TestCancelMigration:
    """POST /api/migrations/<migration_id>/cancel"""

    @patch("api.migrations.AWSMigrationManager")
    def test_cancel_pending_migration(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
    ):
        """Cancel succeeds from an allowed state (uploaded)."""
        mock_aws = MagicMock()
        mock_aws.cleanup_migration.return_value = {
            "instance_terminated": True,
            "s3_deleted": True,
        }
        mock_aws_cls.return_value = mock_aws

        test_migration.status = "uploaded"
        db_session.commit()

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/cancel"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_cancel_completed_migration(
        self, authenticated_client, db_session, test_migration
    ):
        """Cannot cancel a completed migration -> 400."""
        test_migration.status = "completed"
        db_session.commit()

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/cancel"
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "cannot be cancelled" in data["error"]

    def test_cancel_invalid_uuid(self, authenticated_client, db_session):
        """Invalid UUID returns 400."""
        resp = authenticated_client.post(f"/api/migrations/{BAD_UUID}/cancel")
        assert resp.status_code == 400

    @patch("api.migrations.AWSMigrationManager")
    def test_cancel_fallback_status_branch(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
    ):
        """Exercises the else branch where mark_as_failed is absent (lines 790-791)."""
        mock_aws = MagicMock()
        mock_aws.cleanup_migration.return_value = {}
        mock_aws_cls.return_value = mock_aws

        test_migration.status = "pending"
        db_session.commit()

        # Temporarily remove mark_as_failed so the else branch runs
        original = Migration.mark_as_failed
        try:
            delattr(Migration, "mark_as_failed")
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/cancel"
            )
            assert resp.status_code == 200
        finally:
            Migration.mark_as_failed = original

    @patch("api.migrations.AWSMigrationManager")
    def test_cancel_not_found(self, mock_aws_cls, authenticated_client, db_session):
        """Cancel on non-existent migration returns 404."""
        resp = authenticated_client.post(f"/api/migrations/{FAKE_UUID}/cancel")
        assert resp.status_code == 404


# ===================================================================
# 5. TestRetryMigration
# ===================================================================


class TestRetryMigration:
    """POST /api/migrations/<migration_id>/retry"""

    def test_retry_failed_migration(
        self, authenticated_client, db_session, test_migration
    ):
        """Retry succeeds on a failed migration and resets status."""
        test_migration.status = "failed"
        test_migration.retry_count = 0
        db_session.commit()

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/retry"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        db_session.refresh(test_migration)
        assert test_migration.status == "uploaded"
        assert test_migration.progress_percent == 0

    def test_retry_non_failed(self, authenticated_client, db_session, test_migration):
        """Retry on non-failed migration returns 400."""
        test_migration.status = "pending"
        db_session.commit()

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/retry"
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Only failed" in data["error"]

    def test_retry_invalid_uuid(self, authenticated_client, db_session):
        """Invalid UUID returns 400."""
        resp = authenticated_client.post(f"/api/migrations/{BAD_UUID}/retry")
        assert resp.status_code == 400

    def test_retry_not_found(self, authenticated_client, db_session):
        """Non-existent migration returns 404."""
        resp = authenticated_client.post(f"/api/migrations/{FAKE_UUID}/retry")
        assert resp.status_code == 404

    def test_retry_fallback_retry_count_branch(
        self, authenticated_client, db_session, test_migration
    ):
        """Exercises elif branch for retry_count increment (lines 880-882)."""
        test_migration.status = "failed"
        test_migration.retry_count = 0
        db_session.commit()

        # Remove increment_retry so the elif branch executes
        original = Migration.increment_retry
        try:
            delattr(Migration, "increment_retry")
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/retry"
            )
            assert resp.status_code == 200
            db_session.refresh(test_migration)
            assert test_migration.retry_count == 1
        finally:
            Migration.increment_retry = original

    def test_retry_max_retries_reached(
        self, authenticated_client, db_session, test_migration
    ):
        """Retry fails when can_retry returns False."""
        test_migration.status = "failed"
        test_migration.retry_count = 3
        test_migration.max_retries = 3
        db_session.commit()

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/retry"
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Maximum retry" in data["error"]


# ===================================================================
# 6. TestDeleteMigration
# ===================================================================


class TestDeleteMigration:
    """DELETE /api/migrations/<migration_id>"""

    @patch("api.migrations.AWSMigrationManager")
    def test_delete_migration(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
    ):
        """Successful deletion returns 200 and removes the record."""
        mock_aws = MagicMock()
        mock_aws.cleanup_migration.return_value = {}
        mock_aws_cls.return_value = mock_aws

        mid = test_migration.migration_id
        resp = authenticated_client.delete(f"/api/migrations/{mid}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        assert Migration.query.filter_by(migration_id=mid).first() is None

    def test_delete_not_found(self, authenticated_client, db_session):
        """Delete non-existent migration returns 404."""
        resp = authenticated_client.delete(f"/api/migrations/{FAKE_UUID}")
        assert resp.status_code == 404

    def test_delete_invalid_uuid(self, authenticated_client, db_session):
        """Invalid UUID returns 400."""
        resp = authenticated_client.delete(f"/api/migrations/{BAD_UUID}")
        assert resp.status_code == 400

    @patch("api.migrations.AWSMigrationManager")
    def test_delete_already_cleaned(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
    ):
        """Deletion skips AWS cleanup if cleanup_completed is True."""
        mock_aws_cls.return_value = MagicMock()
        test_migration.cleanup_completed = True
        db_session.commit()

        mid = test_migration.migration_id
        resp = authenticated_client.delete(f"/api/migrations/{mid}")
        assert resp.status_code == 200
        # AWSMigrationManager should NOT have been instantiated
        mock_aws_cls.assert_not_called()

    @patch("api.migrations.AWSMigrationManager")
    def test_delete_cleanup_failure_still_deletes(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
    ):
        """Deletion succeeds even when AWS cleanup raises (lines 958-960)."""
        mock_aws = MagicMock()
        mock_aws.cleanup_migration.side_effect = Exception("AWS down")
        mock_aws_cls.return_value = mock_aws

        mid = test_migration.migration_id
        resp = authenticated_client.delete(f"/api/migrations/{mid}")
        assert resp.status_code == 200
        assert Migration.query.filter_by(migration_id=mid).first() is None


# ===================================================================
# 7. TestStartMigration
# ===================================================================


class TestStartMigration:
    """POST /api/migrations/<migration_id>/start"""

    def test_start_invalid_uuid(self, authenticated_client, db_session):
        """Invalid UUID returns 400 (covers UUID validation)."""
        resp = authenticated_client.post(f"/api/migrations/{BAD_UUID}/start")
        assert resp.status_code == 400

    def test_start_not_found(self, authenticated_client, db_session, test_user):
        """Non-existent UUID returns 404."""
        _create_credit(db_session, test_user)
        resp = authenticated_client.post(f"/api/migrations/{FAKE_UUID}/start")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False

    def test_start_wrong_status(
        self, authenticated_client, db_session, test_migration, test_user
    ):
        """Starting a pending (not uploaded) migration returns 400."""
        _create_credit(db_session, test_user)
        test_migration.status = "pending"
        db_session.commit()

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/start"
        )
        assert resp.status_code == 400

    def test_start_no_credits(self, authenticated_client, db_session, test_migration):
        """No credits returns 402."""
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        db_session.commit()

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/start"
        )
        assert resp.status_code == 402

    def test_start_exercises_exception_handler(
        self, authenticated_client, db_session, test_migration, test_user
    ):
        """Start with uploaded status but missing credentials returns 400."""
        _create_credit(db_session, test_user)
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        db_session.commit()

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/start",
            json={},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "error" in data

    @patch("api.migrations.AWSMigrationManager")
    def test_start_ec2_creation_fails(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
        test_user,
    ):
        """EC2 creation with invalid encrypted credentials returns 400."""
        _create_credit(db_session, test_user)
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        test_user.qbo_realm_id = "realm_123"
        db_session.commit()

        mock_aws = MagicMock()
        mock_aws.create_ec2_instance.return_value = None
        mock_aws_cls.return_value = mock_aws

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/start",
            json={"encrypted_credentials": "blob"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False


# ===================================================================
# 7b. TestProcessMigration (alias, line 727)
# ===================================================================


class TestProcessMigration:
    """POST /api/migrations/<migration_id>/process (alias for start, line 727)."""

    def test_process_invalid_uuid(self, authenticated_client, db_session):
        """Invalid UUID returns 400 (covers route + UUID validation)."""
        resp = authenticated_client.post(f"/api/migrations/{BAD_UUID}/process")
        assert resp.status_code == 400

    def test_process_delegates_to_start(
        self, authenticated_client, db_session, test_migration, test_user
    ):
        """Process delegates to start_migration (exercises line 727)."""
        _create_credit(db_session, test_user)
        test_migration.status = "pending"
        db_session.commit()

        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/process"
        )
        # Delegates to start_migration; status "pending" != "uploaded" → 400
        assert resp.status_code == 400


# ===================================================================
# 8. TestExecuteMigrationCelery
# ===================================================================


class TestExecuteMigrationCelery:
    """POST /api/migrations/<migration_id>/execute"""

    def test_execute_import_error(
        self, authenticated_client, db_session, test_migration
    ):
        """When Celery tasks module is unavailable returns 503."""
        test_migration.status = "uploaded"
        db_session.commit()

        with patch.dict("sys.modules", {"tasks": None}):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/execute"
            )

        assert resp.status_code == 503
        data = resp.get_json()
        assert "not available" in data["error"].lower()

    def test_execute_invalid_uuid(self, authenticated_client, db_session):
        """Invalid UUID returns 400."""
        resp = authenticated_client.post(f"/api/migrations/{BAD_UUID}/execute")
        assert resp.status_code == 400

    def test_execute_not_found(self, authenticated_client, db_session):
        """Non-existent migration returns 404 or 503 if tasks unavailable."""
        with patch.dict("sys.modules", {"tasks": None}):
            resp = authenticated_client.post(f"/api/migrations/{FAKE_UUID}/execute")
        assert resp.status_code in (404, 503)

    def test_execute_wrong_status(
        self, authenticated_client, db_session, test_migration
    ):
        """Migration in wrong status returns 400 or 503."""
        test_migration.status = "pending"
        db_session.commit()

        # tasks module may or may not be importable; use a mock
        mock_tasks = MagicMock()
        with patch.dict("sys.modules", {"tasks": mock_tasks}):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/execute"
            )

        assert resp.status_code == 400

    def test_execute_success(self, authenticated_client, db_session, test_migration):
        """Successful execution queues Celery task and returns 202."""
        test_migration.status = "uploaded"
        db_session.commit()

        mock_task_result = MagicMock()
        mock_task_result.id = "celery-task-id-123"
        mock_tasks = MagicMock()
        mock_tasks.run_migration_task.delay.return_value = mock_task_result

        with patch.dict("sys.modules", {"tasks": mock_tasks}):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/execute"
            )

        assert resp.status_code == 202
        data = resp.get_json()
        assert data["success"] is True
        assert data["task_id"] == "celery-task-id-123"
        assert data["status"] == "queued"

    def test_execute_failed_migration(
        self, authenticated_client, db_session, test_migration
    ):
        """Failed migration can also be re-executed via Celery."""
        test_migration.status = "failed"
        db_session.commit()

        mock_task_result = MagicMock()
        mock_task_result.id = "celery-retry-id"
        mock_tasks = MagicMock()
        mock_tasks.run_migration_task.delay.return_value = mock_task_result

        with patch.dict("sys.modules", {"tasks": mock_tasks}):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/execute"
            )

        assert resp.status_code == 202


# ===================================================================
# 9. TestMigrationStats
# ===================================================================


class TestMigrationStats:
    """GET /api/migrations/stats"""

    def test_migration_stats(self, authenticated_client, db_session):
        """Empty stats returns 200 with defaults."""
        resp = authenticated_client.get("/api/migrations/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        stats = data["stats"]
        assert "migrations_this_month" in stats
        assert "total_records" in stats
        assert "avg_duration" in stats
        assert "success_rate" in stats

    def test_migration_stats_with_data(
        self, authenticated_client, db_session, test_user
    ):
        """Stats reflect actual data for the user."""
        now = datetime.now(timezone.utc)
        _create_migration(
            db_session,
            test_user,
            status="completed",
            total_records_migrated=500,
            created_at=now - timedelta(minutes=10),
            completed_at=now,
        )
        resp = authenticated_client.get("/api/migrations/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        stats = data["stats"]
        assert stats["migrations_this_month"] >= 1
        assert stats["success_rate"] == "100.0%"

    def test_migration_stats_large_records_k(
        self, authenticated_client, db_session, test_user
    ):
        """Total records >= 1000 formatted as K."""
        _create_migration(
            db_session,
            test_user,
            status="completed",
            total_records_migrated=5000,
        )
        resp = authenticated_client.get("/api/migrations/stats")
        assert resp.status_code == 200
        stats = resp.get_json()["stats"]
        assert "K" in stats["total_records"]

    def test_migration_stats_large_records_m(
        self, authenticated_client, db_session, test_user
    ):
        """Total records >= 1_000_000 formatted as M (line 1170)."""
        _create_migration(
            db_session,
            test_user,
            status="completed",
            total_records_migrated=2_500_000,
        )
        resp = authenticated_client.get("/api/migrations/stats")
        assert resp.status_code == 200
        stats = resp.get_json()["stats"]
        assert "M" in stats["total_records"]

    def test_migration_stats_avg_duration(
        self, authenticated_client, db_session, test_user
    ):
        """Average duration is calculated for completed migrations."""
        now = datetime.now(timezone.utc)
        _create_migration(
            db_session,
            test_user,
            status="completed",
            total_records_migrated=100,
            created_at=now - timedelta(minutes=5),
            completed_at=now,
        )
        resp = authenticated_client.get("/api/migrations/stats")
        assert resp.status_code == 200
        stats = resp.get_json()["stats"]
        # Should contain minutes/seconds, not "--"
        assert stats["avg_duration"] != "--"

    def test_migration_stats_mixed_success_rate(
        self, authenticated_client, db_session, test_user
    ):
        """Success rate reflects completed and failed migrations."""
        now = datetime.now(timezone.utc)
        _create_migration(db_session, test_user, status="completed", created_at=now)
        _create_migration(db_session, test_user, status="failed", created_at=now)
        resp = authenticated_client.get("/api/migrations/stats")
        assert resp.status_code == 200
        stats = resp.get_json()["stats"]
        assert stats["success_rate"] == "50.0%"
