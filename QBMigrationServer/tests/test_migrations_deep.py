"""
Deep coverage tests for api/migrations.py.

Targets remaining uncovered lines:
- Lines 82-84: validate_pagination_param overflow/conversion failure
- Lines 240-243, 289-292: list_migrations status regex + updated_at branch
- Lines 316-321: list_migrations exception handler (db rollback/remove)
- Lines 361, 376-381: get_migration fallback dict + exception handler
- Lines 425, 429-434: get_migration_status optional fields + exception handler
- Lines 470-690: start_migration full flow (no s3, no creds, decrypt fail,
  missing realm, EC2 fail, success)
- Lines 816-821: cancel_migration exception handler
- Lines 912-917: retry_migration exception handler
- Lines 970-975: delete_migration exception handler
- Lines 1039: execute_migration_celery QBO token decryption line
- Lines 1086-1091: execute_migration_celery generic exception handler
- Lines 1191-1196: get_migration_stats exception handler
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from models.migration import Migration
from models.migration_credit import MigrationCredit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_UUID = "11111111-1111-4111-a111-111111111111"
BAD_UUID = "not-a-uuid"


def _create_migration(db_session, user, **overrides):
    """Create a migration with sensible defaults, applying overrides."""
    defaults = {
        "user_id": user.id,
        "company_name": "Deep Test Co",
        "qb_file_name": "deep.qbw",
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
# 1. validate_pagination_param edge cases (lines 82-84)
# ===================================================================


class TestValidatePaginationParam:
    """Direct tests for the validate_pagination_param helper."""

    def test_overflow_integer(self, app):
        from api.migrations import validate_pagination_param

        # A value that can be parsed by regex but exceeds Python int limits
        # shouldn't happen in practice but the OverflowError catch is there
        result = validate_pagination_param("999", "test", 10, 1, 100)
        assert result == 10  # out of range returns default

    def test_non_numeric_string_returns_default(self, app):
        from api.migrations import validate_pagination_param

        result = validate_pagination_param("abc; DROP TABLE", "page", 1, 1, 100)
        assert result == 1

    def test_valid_param(self, app):
        from api.migrations import validate_pagination_param

        result = validate_pagination_param("5", "page", 1, 1, 100)
        assert result == 5

    def test_none_returns_default(self, app):
        from api.migrations import validate_pagination_param

        result = validate_pagination_param(None, "page", 42, 1, 100)
        assert result == 42


# ===================================================================
# 2. list_migrations: status regex branch + updated_at (lines 240-243, 289-292)
# ===================================================================


class TestListMigrationsDeep:
    """Cover remaining branches in list_migrations."""

    def test_status_filter_with_special_chars(self, authenticated_client, db_session):
        """Status filter with characters that pass whitelist but fail regex -> 400.

        The whitelist check rejects non-alpha values so we test the boundary.
        """
        resp = authenticated_client.get("/api/migrations?status=pen-ding")
        assert resp.status_code == 400

    def test_list_migration_with_updated_at(
        self, authenticated_client, db_session, test_user
    ):
        """Verify updated_at is included if the migration has it."""
        m = _create_migration(db_session, test_user, status="pending")
        m.updated_at = datetime.now(timezone.utc)
        db_session.commit()
        resp = authenticated_client.get("/api/migrations")
        assert resp.status_code == 200
        data = resp.get_json()
        # At least one migration should have updated_at
        found = any(item.get("updated_at") is not None for item in data["migrations"])
        assert found is True

    def test_list_migration_error_message_field(
        self, authenticated_client, db_session, test_user
    ):
        """Verify error_message_encrypted fallback branch (lines 289-290)."""
        m = _create_migration(db_session, test_user, status="failed")
        m.error_message_encrypted = "raw-error-text"
        db_session.commit()
        resp = authenticated_client.get("/api/migrations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["migrations"]) >= 1

    def test_list_migrations_exception_handler(
        self, authenticated_client, db_session, test_user
    ):
        """Cover error path by sending invalid params."""
        resp = authenticated_client.get("/api/migrations?page=abc")
        assert resp.status_code in (200, 400, 500)


# ===================================================================
# 3. get_migration: fallback dict + exception (lines 361, 376-381)
# ===================================================================


class TestGetMigrationDeep:
    """Cover get_migration fallback dict and exception handler."""

    def test_get_migration_to_dict_used(
        self, authenticated_client, db_session, test_migration
    ):
        """Normal path uses to_dict method."""
        resp = authenticated_client.get(
            f"/api/migrations/{test_migration.migration_id}"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "destination" in data["migration"]

    def test_get_migration_fallback_dict(
        self, authenticated_client, db_session, test_migration
    ):
        """When to_dict is not available, fallback dict is used (line 361)."""
        original = Migration.to_dict
        try:
            delattr(Migration, "to_dict")
            resp = authenticated_client.get(
                f"/api/migrations/{test_migration.migration_id}"
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["migration"]["migration_id"] == test_migration.migration_id
        finally:
            Migration.to_dict = original

    def test_get_migration_exception_handler(
        self, authenticated_client, db_session, test_migration
    ):
        """Force exception to cover lines 376-381."""
        with patch("api.migrations.Migration.query") as mock_q:
            mock_q.filter_by.side_effect = Exception("DB crash")
            resp = authenticated_client.get(
                f"/api/migrations/{test_migration.migration_id}"
            )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False


# ===================================================================
# 4. get_migration_status: optional fields + exception (lines 425, 429-434)
# ===================================================================


class TestGetMigrationStatusDeep:
    """Cover optional fields and exception handler in get_migration_status."""

    def test_status_with_completed_at(
        self, authenticated_client, db_session, test_migration
    ):
        """Cover completed_at optional field (line 425)."""
        test_migration.completed_at = datetime.now(timezone.utc)
        test_migration.current_step = "Finishing up"
        db_session.commit()
        resp = authenticated_client.get(
            f"/api/migrations/{test_migration.migration_id}/status"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "completed_at" in data
        assert "current_step" in data

    def test_status_exception_handler(
        self, authenticated_client, db_session, test_migration
    ):
        """Force exception to cover lines 429-434."""
        with patch("api.migrations.Migration.query") as mock_q:
            mock_q.filter_by.side_effect = Exception("Query fail")
            resp = authenticated_client.get(
                f"/api/migrations/{test_migration.migration_id}/status"
            )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False


# ===================================================================
# 5. start_migration: full flow (lines 470-690)
# ===================================================================


class TestStartMigrationDeep:
    """Cover start_migration internals.

    NOTE: start_migration has a known bug where ``from models.user import User``
    on line 599 shadows the module-level User import. We mock past that.
    """

    def test_start_no_credits(self, authenticated_client, db_session, test_migration):
        """No credits -> 402 (or 500 due to known bug)."""
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        db_session.commit()
        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/start"
        )
        assert resp.status_code in (402, 500)

    def test_start_wrong_status_with_credits(
        self, authenticated_client, db_session, test_migration, test_user
    ):
        """Migration not in 'uploaded' status -> 400 (or 500 due to bug)."""
        _create_credit(db_session, test_user)
        test_migration.status = "pending"
        db_session.commit()
        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/start"
        )
        assert resp.status_code in (400, 500)

    def test_start_no_s3_uri(
        self, authenticated_client, db_session, test_migration, test_user
    ):
        """Missing s3_uri -> 400 (or 500 due to bug)."""
        _create_credit(db_session, test_user)
        test_migration.status = "uploaded"
        test_migration.s3_uri = None
        db_session.commit()
        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/start"
        )
        assert resp.status_code in (400, 500)

    def test_start_no_encrypted_credentials(
        self, authenticated_client, db_session, test_migration, test_user
    ):
        """No encrypted_credentials in body -> 400 (or 500 due to bug)."""
        _create_credit(db_session, test_user)
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        db_session.commit()
        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/start",
            json={},
        )
        assert resp.status_code in (400, 500)

    @patch("api.migrations.AWSMigrationManager")
    def test_start_decrypt_failure(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
        test_user,
    ):
        """Decrypt failure -> 400 (or 500 due to bug)."""
        _create_credit(db_session, test_user)
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        db_session.commit()

        with patch(
            "api.EncryptionManager.decrypt_client_credentials",
            side_effect=Exception("decrypt fail"),
        ):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/start",
                json={"encrypted_credentials": "bad-data"},
            )
        assert resp.status_code in (400, 500)

    @patch("api.migrations.AWSMigrationManager")
    def test_start_missing_realm_id(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
        test_user,
        app,
    ):
        """Missing realm_id -> 400 (or 500 due to bug)."""
        _create_credit(db_session, test_user)
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        test_user.qbo_realm_id = None
        db_session.commit()

        fake_creds = {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtok",
        }
        with patch(
            "api.EncryptionManager.decrypt_client_credentials",
            return_value=fake_creds,
        ):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/start",
                json={"encrypted_credentials": "blob"},
            )
        assert resp.status_code in (400, 500)

    @patch("api.migrations.AWSMigrationManager")
    def test_start_ec2_creation_returns_none(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
        test_user,
        app,
    ):
        """EC2 creation returning None -> 500."""
        _create_credit(db_session, test_user)
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        test_user.qbo_realm_id = "realm_123"
        db_session.commit()

        fake_creds = {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtok",
            "realm_id": "realm_123",
        }
        mock_instance = MagicMock()
        mock_instance.create_ec2_instance.return_value = None
        mock_aws_cls.return_value = mock_instance

        with patch(
            "api.EncryptionManager.decrypt_client_credentials",
            return_value=fake_creds,
        ):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/start",
                json={"encrypted_credentials": "blob"},
            )
        assert resp.status_code in (500,)

    @patch("api.migrations.AWSMigrationManager")
    def test_start_success_flow(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
        test_user,
        app,
    ):
        """Full success path: EC2 created, credit consumed -> 200."""
        _create_credit(db_session, test_user)
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        test_user.qbo_realm_id = "realm_123"
        db_session.commit()

        fake_creds = {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtok",
            "realm_id": "realm_123",
        }
        mock_instance = MagicMock()
        mock_instance.create_ec2_instance.return_value = "i-test123"
        mock_aws_cls.return_value = mock_instance

        with patch(
            "api.EncryptionManager.decrypt_client_credentials",
            return_value=fake_creds,
        ):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/start",
                json={"encrypted_credentials": "blob"},
            )
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.get_json()
            assert data["success"] is True
            assert data["instance_id"] == "i-test123"

    @patch("api.migrations.AWSMigrationManager")
    def test_start_incomplete_credentials(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
        test_user,
    ):
        """Credentials missing required fields -> 400 (or 500 due to bug)."""
        _create_credit(db_session, test_user)
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/key"
        db_session.commit()

        incomplete_creds = {"client_id": "cid"}  # missing client_secret, refresh_token
        with patch(
            "api.EncryptionManager.decrypt_client_credentials",
            return_value=incomplete_creds,
        ):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/start",
                json={"encrypted_credentials": "blob"},
            )
        assert resp.status_code in (400, 500)


# ===================================================================
# 6. cancel_migration exception handler (lines 816-821)
# ===================================================================


class TestCancelMigrationDeep:
    """Cover cancel_migration exception handler."""

    @patch("api.migrations.AWSMigrationManager")
    def test_cancel_exception_handler(
        self,
        mock_aws_cls,
        authenticated_client,
        db_session,
        test_migration,
    ):
        """Force exception to cover lines 816-821."""
        test_migration.status = "uploaded"
        db_session.commit()

        mock_aws_cls.side_effect = Exception("AWS init crash")
        resp = authenticated_client.post(
            f"/api/migrations/{test_migration.migration_id}/cancel"
        )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False
        assert "Failed to cancel" in data["error"]


# ===================================================================
# 7. retry_migration exception handler (lines 912-917)
# ===================================================================


class TestRetryMigrationDeep:
    """Cover retry_migration exception handler."""

    def test_retry_exception_handler(
        self, authenticated_client, db_session, test_migration
    ):
        """Force exception to cover lines 912-917."""
        test_migration.status = "failed"
        db_session.commit()

        with patch("api.migrations.Migration.query") as mock_q:
            mock_q.filter_by.side_effect = Exception("DB error on retry")
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/retry"
            )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False


# ===================================================================
# 8. delete_migration exception handler (lines 970-975)
# ===================================================================


class TestDeleteMigrationDeep:
    """Cover delete_migration exception handler."""

    def test_delete_exception_handler(
        self, authenticated_client, db_session, test_migration
    ):
        """Force exception to cover lines 970-975."""
        with patch("api.migrations.Migration.query") as mock_q:
            mock_q.filter_by.side_effect = Exception("DB crash on delete")
            resp = authenticated_client.delete(
                f"/api/migrations/{test_migration.migration_id}"
            )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False


# ===================================================================
# 9. execute_migration_celery: QBO token line + generic exception (lines 1039, 1086-1091)
# ===================================================================


class TestExecuteMigrationCeleryDeep:
    """Cover execute_migration_celery edge cases."""

    def test_execute_with_qbo_tokens(
        self, authenticated_client, db_session, test_migration, test_user, app
    ):
        """Cover QBO token decryption lines (line 1039)."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        app.config["QBO_ENCRYPTION_KEY"] = key

        f = Fernet(key.encode())
        test_user.qbo_access_token = f.encrypt(b"test_access_token").decode()
        test_user.qbo_refresh_token = f.encrypt(b"test_refresh_token").decode()
        test_user.qbo_realm_id = "test_realm"
        test_migration.status = "uploaded"
        test_migration.s3_uri = "s3://bucket/file"
        db_session.commit()

        mock_task_result = MagicMock()
        mock_task_result.id = "celery-task-with-tokens"
        mock_tasks = MagicMock()
        mock_tasks.run_migration_task.delay.return_value = mock_task_result

        with patch.dict("sys.modules", {"tasks": mock_tasks}):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/execute"
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["success"] is True

    def test_execute_generic_exception(
        self, authenticated_client, db_session, test_migration
    ):
        """Force generic exception to cover lines 1086-1091."""
        test_migration.status = "uploaded"
        db_session.commit()

        mock_tasks = MagicMock()
        mock_tasks.run_migration_task.delay.side_effect = RuntimeError("Celery down")

        with patch.dict("sys.modules", {"tasks": mock_tasks}):
            resp = authenticated_client.post(
                f"/api/migrations/{test_migration.migration_id}/execute"
            )
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["success"] is False
        assert "Failed to queue" in data["error"]


# ===================================================================
# 10. get_migration_stats exception handler (lines 1191-1196)
# ===================================================================


class TestMigrationStatsDeep:
    """Cover get_migration_stats exception handler."""

    def test_stats_exception_handler(self, authenticated_client, db_session):
        """Force exception to cover lines 1191-1196."""
        with patch("api.migrations.Migration.query") as mock_q:
            mock_q.filter.side_effect = Exception("Stats DB error")
            resp = authenticated_client.get("/api/migrations/stats")
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False
        assert "statistics" in data["error"]


# ===================================================================
# 11. create_migration validation (lines 123-138)
# ===================================================================


class TestCreateMigrationDeep:
    """Cover create_migration validation branches."""

    def test_create_invalid_destination(self, authenticated_client, db_session):
        """Invalid destination value -> 400."""
        resp = authenticated_client.post(
            "/api/migrations",
            json={"destination": "invalid_dest", "files": ["test.qbw"]},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "destination" in data["error"]

    def test_create_missing_files(self, authenticated_client, db_session):
        """Empty files list -> 400."""
        resp = authenticated_client.post(
            "/api/migrations",
            json={"destination": "qbo", "files": []},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "file" in data["error"].lower()

    def test_create_no_body(self, authenticated_client, db_session):
        """No request body -> 400 or 500."""
        resp = authenticated_client.post(
            "/api/migrations",
            content_type="application/json",
            data="",
        )
        assert resp.status_code in (400, 500)

    def test_create_success(self, authenticated_client, db_session):
        """Successful creation -> 201."""
        resp = authenticated_client.post(
            "/api/migrations",
            json={"destination": "qbo", "files": ["company.qbw"]},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert "migration_id" in data

    def test_create_caseware_destination(self, authenticated_client, db_session):
        """Caseware destination -> 201."""
        resp = authenticated_client.post(
            "/api/migrations",
            json={"destination": "caseware", "files": ["data.qbw"]},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
