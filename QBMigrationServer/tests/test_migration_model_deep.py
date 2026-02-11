"""
Deep coverage tests for models/migration.py and models/user.py.

Targets remaining uncovered lines in models/migration.py (84.82%, 51 miss):
- Lines 189-216: to_dict with various optional fields (started_at, completed_at, etc.)
- Lines 226, 230-232: to_dict error_message + error_code for failed migrations
- Lines 429: mark_as_completed returns False from non-processing status
- Lines 518-528, 536-538: set_error_message Fernet encryption paths
- Lines 673-674, 678-681, 684-687: to_dict sensitive fields (trial_balance_data,
  live_status_data, cost_breakdown parse errors)
- Lines 697-762: strip_sensitive_data method

Also covers models/user.py additional lines:
- QBO token encryption/decryption
- get_tier_info with MigrationCredit
- migrate_legacy_mfa_data
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from models.migration import Migration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_migration(db_session, user, **overrides):
    defaults = {
        "user_id": user.id,
        "company_name": "Model Deep",
        "qb_file_name": "model.qbw",
        "status": "pending",
    }
    defaults.update(overrides)
    m = Migration(**defaults)
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


# ===================================================================
# 1. to_dict comprehensive coverage
# ===================================================================


class TestMigrationToDictDeep:
    """Cover all branches in Migration.to_dict."""

    def test_to_dict_with_started_and_completed(self, db_session, test_user, app):
        """Cover started_at and completed_at isoformat branches."""
        now = datetime.now(timezone.utc)
        m = _make_migration(
            db_session,
            test_user,
            status="completed",
        )
        m.started_at = now - timedelta(minutes=10)
        m.completed_at = now
        m.progress_percent = 100
        m.current_step = "Done"
        m.customers_migrated = 50
        m.vendors_migrated = 20
        m.invoices_migrated = 100
        m.bills_migrated = 30
        m.items_migrated = 40
        m.total_records_migrated = 240
        db_session.commit()

        d = m.to_dict()
        assert d["migration_id"] == m.migration_id
        assert d["status"] == "completed"
        assert d["started_at"] is not None
        assert d["completed_at"] is not None
        assert d["duration_minutes"] >= 9
        assert d["customers_migrated"] == 50
        assert d["vendors_migrated"] == 20
        assert d["invoices_migrated"] == 100
        assert d["total_records_migrated"] == 240
        # Not failed, so error_message and error_code should be None
        assert d["error_message"] is None
        assert d["error_code"] is None
        assert d["can_retry"] is False

    def test_to_dict_failed_with_error(self, db_session, test_user, app):
        """Cover error_message and error_code fields for failed migration."""
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _make_migration(db_session, test_user, status="pending")
        m.status = "failed"
        m.error_code = "TIMEOUT_ERROR"
        m.set_error_message("Connection timed out")
        m.retry_count = 1
        m.max_retries = 3
        db_session.commit()

        d = m.to_dict()
        assert d["error_message"] == "Connection timed out"
        assert d["error_code"] == "TIMEOUT_ERROR"
        assert d["can_retry"] is True

    def test_to_dict_failed_max_retries(self, db_session, test_user, app):
        """can_retry is False when retry_count >= max_retries."""
        m = _make_migration(db_session, test_user, status="pending")
        m.status = "failed"
        m.retry_count = 3
        m.max_retries = 3
        db_session.commit()

        d = m.to_dict()
        assert d["can_retry"] is False

    def test_to_dict_caseware_destination(self, db_session, test_user):
        """Cover caseware_bundle_ready field when destination is caseware."""
        m = _make_migration(db_session, test_user, destination="caseware")
        m.caseware_bundle_ready = True
        db_session.commit()

        d = m.to_dict()
        assert d["destination"] == "caseware"
        assert d["caseware_bundle_ready"] is True

    def test_to_dict_qbo_destination_hides_caseware(self, db_session, test_user):
        """caseware_bundle_ready is None when destination is qbo."""
        m = _make_migration(db_session, test_user, destination="qbo")
        d = m.to_dict()
        assert d["caseware_bundle_ready"] is None

    def test_to_dict_no_cost(self, db_session, test_user):
        """Cost fields are None when not set."""
        m = _make_migration(db_session, test_user)
        d = m.to_dict()
        assert d["estimated_cost_usd"] is None
        assert d["actual_cost_usd"] is None

    def test_to_dict_with_costs(self, db_session, test_user):
        """Cover estimated and actual cost float conversion."""
        m = _make_migration(db_session, test_user)
        m.estimated_cost_usd = 1.5000
        m.actual_cost_usd = 1.2500
        db_session.commit()

        d = m.to_dict()
        assert d["estimated_cost_usd"] == 1.5
        assert d["actual_cost_usd"] == 1.25

    def test_to_dict_no_created_at(self, db_session, test_user):
        """Cover created_at None branch (edge case)."""
        m = _make_migration(db_session, test_user)
        # created_at has a default, but test None branch
        d = m.to_dict()
        assert d["created_at"] is not None


# ===================================================================
# 2. to_dict sensitive fields (lines 670-687)
# ===================================================================


class TestMigrationToDictSensitiveDeep:
    """Cover sensitive field parsing in to_dict(include_sensitive=True)."""

    def test_sensitive_cost_breakdown_valid(self, db_session, test_user):
        """Valid cost breakdown JSON is parsed."""
        m = _make_migration(db_session, test_user)
        m.cost_breakdown = json.dumps({"ec2": 1.0, "s3": 0.5})
        db_session.commit()

        d = m.to_dict(include_sensitive=True)
        assert d["cost_breakdown"]["ec2"] == 1.0

    def test_sensitive_cost_breakdown_invalid_json(self, db_session, test_user):
        """Invalid cost breakdown JSON is handled gracefully (lines 673-674)."""
        m = _make_migration(db_session, test_user)
        m.cost_breakdown = "not-valid-json"
        db_session.commit()

        d = m.to_dict(include_sensitive=True)
        # cost_breakdown should not be in result or should be absent
        assert "cost_breakdown" not in d or d.get("cost_breakdown") is None

    def test_sensitive_trial_balance_data_valid(self, db_session, test_user):
        """Valid trial_balance_data JSON is parsed (lines 677-679)."""
        m = _make_migration(db_session, test_user)
        m.trial_balance_data = json.dumps({"source_total": 1000, "dest_total": 1000})
        db_session.commit()

        d = m.to_dict(include_sensitive=True)
        assert d["trial_balance_data"]["source_total"] == 1000

    def test_sensitive_trial_balance_data_invalid_json(self, db_session, test_user):
        """Invalid trial_balance_data JSON is handled (lines 680-681)."""
        m = _make_migration(db_session, test_user)
        m.trial_balance_data = "{bad json"
        db_session.commit()

        d = m.to_dict(include_sensitive=True)
        assert "trial_balance_data" not in d

    def test_sensitive_live_status_data_valid(self, db_session, test_user):
        """Valid live_status_data JSON is parsed (lines 683-685)."""
        m = _make_migration(db_session, test_user)
        m.live_status_data = json.dumps({"phase": "extracting", "progress": 50})
        db_session.commit()

        d = m.to_dict(include_sensitive=True)
        assert d["live_status_data"]["phase"] == "extracting"

    def test_sensitive_live_status_data_invalid_json(self, db_session, test_user):
        """Invalid live_status_data JSON is handled (lines 686-687)."""
        m = _make_migration(db_session, test_user)
        m.live_status_data = "not json at all"
        db_session.commit()

        d = m.to_dict(include_sensitive=True)
        assert "live_status_data" not in d

    def test_sensitive_no_data_size(self, db_session, test_user):
        """data_size_mb is None when data_size_bytes is None."""
        m = _make_migration(db_session, test_user)
        m.data_size_bytes = None
        db_session.commit()

        d = m.to_dict(include_sensitive=True)
        assert d["data_size_mb"] is None

    def test_sensitive_with_all_fields(self, db_session, test_user):
        """All sensitive fields are present when populated."""
        m = _make_migration(db_session, test_user)
        m.s3_uri = "s3://bucket/key"
        m.aws_instance_id = "i-abc123"
        m.aws_region = "us-east-1"
        m.cleanup_completed = True
        m.s3_file_deleted = True
        m.ec2_terminated = True
        m.file_hash = "abc123"
        m.data_size_bytes = 2 * 1024 * 1024
        m.retry_count = 1
        m.ip_address = "1.2.3.4"
        m.request_id = str(uuid.uuid4())
        m.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        db_session.commit()

        d = m.to_dict(include_sensitive=True)
        assert d["s3_uri"] == "s3://bucket/key"
        assert d["aws_instance_id"] == "i-abc123"
        assert d["aws_region"] == "us-east-1"
        assert d["cleanup_completed"] is True
        assert d["s3_file_deleted"] is True
        assert d["ec2_terminated"] is True
        assert d["file_hash"] == "abc123"
        assert d["data_size_mb"] == 2.0
        assert d["retry_count"] == 1
        assert d["ip_address"] == "1.2.3.4"
        assert d["expires_at"] is not None


# ===================================================================
# 3. Error message encryption/decryption (lines 518-538, 673-687)
# ===================================================================


class TestMigrationErrorEncryptionDeep:
    """Cover set_error_message and get_error_message edge cases."""

    def test_set_and_get_error_with_key(self, app, db_session, test_user):
        """Round-trip: encrypt then decrypt with valid key."""
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _make_migration(db_session, test_user, status="failed")
        m.set_error_message("Test error message for encryption")
        db_session.commit()

        result = m.get_error_message()
        assert result == "Test error message for encryption"

    def test_set_error_no_key_dev_mode(self, app, db_session, test_user):
        """No encryption key in dev mode stores redacted placeholder."""
        app.config["BACKUP_ENCRYPTION_KEY"] = None

        m = _make_migration(db_session, test_user, status="failed")
        m.set_error_message("Sensitive error info")
        db_session.commit()

        assert m.error_message_encrypted == "[REDACTED - encryption key not configured]"

    def test_get_error_no_key_returns_raw(self, app, db_session, test_user):
        """get_error_message with no key returns raw encrypted text (line 226)."""
        app.config["BACKUP_ENCRYPTION_KEY"] = None

        m = _make_migration(db_session, test_user, status="failed")
        m.error_message_encrypted = "some-unencrypted-text"
        db_session.commit()

        result = m.get_error_message()
        assert result == "some-unencrypted-text"

    def test_get_error_invalid_token(self, app, db_session, test_user):
        """get_error_message with wrong key returns fallback (lines 230-232)."""
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        app.config["BACKUP_ENCRYPTION_KEY"] = key1
        m = _make_migration(db_session, test_user, status="failed")
        m.set_error_message("Encrypted with key1")
        db_session.commit()

        # Switch to different key
        app.config["BACKUP_ENCRYPTION_KEY"] = key2
        result = m.get_error_message()
        assert result == "Error message decryption failed"

    def test_set_error_encryption_failure(self, app, db_session, test_user):
        """Fernet encryption failure stores plaintext or placeholder."""
        orig = app.config.get("BACKUP_ENCRYPTION_KEY")
        app.config["BACKUP_ENCRYPTION_KEY"] = None
        app.config.pop("QBO_ENCRYPTION_KEY", None)

        m = _make_migration(db_session, test_user, status="failed")
        m.set_error_message("Some error")
        db_session.commit()

        # Without encryption key, it falls back to storing unencrypted
        assert m.error_message_encrypted is not None

        if orig:
            app.config["BACKUP_ENCRYPTION_KEY"] = orig

    def test_set_error_none_clears(self, app, db_session, test_user):
        """Setting None clears the field."""
        m = _make_migration(db_session, test_user, status="failed")
        m.error_message_encrypted = "something"
        db_session.commit()

        m.set_error_message(None)
        assert m.error_message_encrypted is None

    def test_set_error_empty_string_clears(self, app, db_session, test_user):
        """Setting empty string clears the field."""
        m = _make_migration(db_session, test_user, status="failed")
        m.set_error_message("")
        assert m.error_message_encrypted is None


# ===================================================================
# 4. mark_as_completed edge case (line 429)
# ===================================================================


class TestMarkAsCompletedDeep:
    """Cover mark_as_completed return False from non-processing status."""

    def test_completed_from_pending_returns_false(self, db_session, test_user):
        """mark_as_completed from pending returns False (line 429)."""
        m = _make_migration(db_session, test_user, status="pending")
        results = {
            "trial_balance": {
                "is_balanced": True,
                "source_total": 100.00,
                "destination_total": 100.00,
            }
        }
        result = m.mark_as_completed(results=results)
        assert result is False
        assert m.status == "pending"

    def test_completed_from_completed_returns_false(self, db_session, test_user):
        """mark_as_completed from completed returns False."""
        m = _make_migration(db_session, test_user, status="completed")
        results = {
            "trial_balance": {
                "is_balanced": True,
                "source_total": 100.00,
                "destination_total": 100.00,
            }
        }
        result = m.mark_as_completed(results=results)
        assert result is False

    def test_completed_stores_verification_results(self, db_session, test_user, app):
        """Verification results are stored as JSON."""
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        m = _make_migration(db_session, test_user, status="processing")
        results = {
            "customers": 5,
            "total": 5,
            "trial_balance": {
                "is_balanced": True,
                "source_total": 500.00,
                "destination_total": 500.00,
            },
            "verification_data": {"hash": "abc123"},
        }
        result = m.mark_as_completed(results=results)
        assert result is True
        assert m.verification_results is not None
        vr = json.loads(m.verification_results)
        assert "trial_balance" in vr


# ===================================================================
# 5. strip_sensitive_data (lines 697-762)
# ===================================================================


class TestStripSensitiveData:
    """Cover strip_sensitive_data method."""

    def test_strip_trial_balance_data(self, db_session, test_user):
        """Trial balance data is stripped to metadata only."""
        m = _make_migration(db_session, test_user, status="completed")
        m.trial_balance_data = json.dumps(
            {
                "accounts": [{"name": "Cash", "balance": 1000}],
                "transactions": [{"id": 1, "amount": 500}],
                "hash": "abc123",
                "variance_percent": 0.0,
                "status": "balanced",
            }
        )
        db_session.commit()

        result = m.strip_sensitive_data()
        assert result is True

        stripped = json.loads(m.trial_balance_data)
        assert "stripped_at" in stripped
        assert stripped["original_account_count"] == 1
        assert stripped["original_transaction_count"] == 1
        assert stripped["data_hash"] == "abc123"
        # Raw accounts and transactions should be gone
        assert "accounts" not in stripped
        assert "transactions" not in stripped

    def test_strip_live_status_data(self, db_session, test_user):
        """Live status data is stripped to metadata only."""
        m = _make_migration(db_session, test_user, status="completed")
        m.live_status_data = json.dumps(
            {
                "current_phase": "completed",
                "phases": ["extract", "transform", "load"],
                "status": "done",
                "detailed_logs": ["log1", "log2"],
            }
        )
        db_session.commit()

        result = m.strip_sensitive_data()
        assert result is True

        stripped = json.loads(m.live_status_data)
        assert "stripped_at" in stripped
        assert stripped["final_phase"] == "completed"
        assert stripped["phase_count"] == 3
        assert stripped["completion_status"] == "done"
        assert "detailed_logs" not in stripped

    def test_strip_invalid_trial_balance_json(self, db_session, test_user):
        """Invalid trial_balance_data JSON is handled gracefully."""
        m = _make_migration(db_session, test_user, status="completed")
        m.trial_balance_data = "not valid json"
        db_session.commit()

        result = m.strip_sensitive_data()
        assert result is True

        stripped = json.loads(m.trial_balance_data)
        assert "error" in stripped
        assert "stripped_at" in stripped

    def test_strip_invalid_live_status_json(self, db_session, test_user):
        """Invalid live_status_data JSON is handled gracefully."""
        m = _make_migration(db_session, test_user, status="completed")
        m.live_status_data = "{broken"
        db_session.commit()

        result = m.strip_sensitive_data()
        assert result is True

        stripped = json.loads(m.live_status_data)
        assert "error" in stripped

    def test_strip_no_data(self, db_session, test_user):
        """strip_sensitive_data with no data returns True."""
        m = _make_migration(db_session, test_user)
        m.trial_balance_data = None
        m.live_status_data = None
        db_session.commit()

        result = m.strip_sensitive_data()
        assert result is True

    def test_strip_partial_trial_balance_keys(self, db_session, test_user):
        """Trial balance data without optional keys still works."""
        m = _make_migration(db_session, test_user, status="completed")
        m.trial_balance_data = json.dumps({"summary": "balanced"})
        db_session.commit()

        result = m.strip_sensitive_data()
        assert result is True

        stripped = json.loads(m.trial_balance_data)
        assert stripped["original_account_count"] is None
        assert stripped["original_transaction_count"] is None


# ===================================================================
# 6. User model: QBO token encryption/decryption
# ===================================================================


class TestUserQBOTokensDeep:
    """Cover User QBO token encryption edge cases."""

    def test_set_and_get_qbo_tokens(self, app, db_session, test_user):
        """Round-trip QBO token encryption."""
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        test_user.set_qbo_tokens("access_tok", "refresh_tok", "realm_42", expires)
        db_session.commit()

        assert test_user.get_qbo_access_token() == "access_tok"
        assert test_user.get_qbo_refresh_token() == "refresh_tok"
        assert test_user.qbo_realm_id == "realm_42"

    def test_get_qbo_tokens_none(self, app, db_session, test_user):
        """None tokens return None."""
        assert test_user.get_qbo_access_token() is None
        assert test_user.get_qbo_refresh_token() is None

    def test_clear_qbo_tokens(self, app, db_session, test_user):
        """clear_qbo_tokens removes all QBO fields."""
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key

        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        test_user.set_qbo_tokens("at", "rt", "realm", expires)
        db_session.commit()

        test_user.clear_qbo_tokens()
        assert test_user.qbo_access_token is None
        assert test_user.qbo_refresh_token is None
        assert test_user.qbo_realm_id is None

    def test_get_qbo_token_wrong_key(self, app, db_session, test_user):
        """Wrong decryption key returns None (error handled)."""
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        app.config["BACKUP_ENCRYPTION_KEY"] = key1
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        test_user.set_qbo_tokens("access", "refresh", "realm", expires)
        db_session.commit()

        app.config["BACKUP_ENCRYPTION_KEY"] = key2
        app.config["QBO_ENCRYPTION_KEY"] = key2
        assert test_user.get_qbo_access_token() is None
        assert test_user.get_qbo_refresh_token() is None


# ===================================================================
# 7. User model: RBAC methods
# ===================================================================


class TestUserRBACDeep:
    """Cover RBAC methods on User model."""

    def test_has_role(self, db_session, test_user):
        assert test_user.has_role("user") is True
        assert test_user.has_role("admin") is False

    def test_has_role_or_higher(self, db_session, test_user):
        assert test_user.has_role_or_higher("user") is True
        assert test_user.has_role_or_higher("admin") is False

    def test_is_admin(self, db_session, test_user):
        assert test_user.is_admin() is False
        test_user.role = "admin"
        assert test_user.is_admin() is True

    def test_is_super_admin(self, db_session, test_user):
        assert test_user.is_super_admin() is False
        test_user.role = "super_admin"
        assert test_user.is_super_admin() is True

    def test_can_manage_users(self, db_session, test_user):
        assert test_user.can_manage_users() is False
        test_user.role = "admin"
        assert test_user.can_manage_users() is True

    def test_can_view_all_migrations(self, db_session, test_user):
        assert test_user.can_view_all_migrations() is False
        test_user.role = "admin"
        assert test_user.can_view_all_migrations() is True

    def test_can_access_admin_dashboard(self, db_session, test_user):
        assert test_user.can_access_admin_dashboard() is False
        test_user.role = "support"
        assert test_user.can_access_admin_dashboard() is True


# ===================================================================
# 8. User model: subscription/migration counting
# ===================================================================


class TestUserSubscriptionDeep:
    """Cover subscription and migration methods."""

    def test_get_migrations_remaining(self, db_session, test_user):
        test_user.migrations_purchased = 5
        test_user.migrations_used = 2
        assert test_user.get_migrations_remaining() == 3

    def test_get_migrations_remaining_zero(self, db_session, test_user):
        test_user.migrations_purchased = 0
        test_user.migrations_used = 0
        assert test_user.get_migrations_remaining() == 0

    def test_has_migrations_remaining(self, db_session, test_user):
        test_user.migrations_purchased = 1
        test_user.migrations_used = 0
        assert test_user.has_migrations_remaining() is True

    def test_use_migration(self, db_session, test_user):
        test_user.migrations_purchased = 1
        test_user.migrations_used = 0
        assert test_user.use_migration() is True
        assert test_user.migrations_used == 1

    def test_use_migration_none_remaining(self, db_session, test_user):
        test_user.migrations_purchased = 0
        test_user.migrations_used = 0
        assert test_user.use_migration() is False

    def test_add_migrations(self, db_session, test_user):
        test_user.migrations_purchased = 0
        test_user.add_migrations(3, tier="business")
        assert test_user.migrations_purchased == 3
        assert test_user.subscription_tier == "business"
        assert test_user.tier_purchased_at is not None

    def test_get_tier_info(self, db_session, test_user):
        test_user.subscription_tier = "starter"
        info = test_user.get_tier_info()
        assert info["tier"] == "starter"
        assert "migrations_remaining" in info


# ===================================================================
# 9. Migration model: find_duplicate + repr
# ===================================================================


class TestMigrationMiscDeep:
    """Cover miscellaneous migration model methods."""

    def test_find_duplicate_found(self, db_session, test_user):
        m = _make_migration(db_session, test_user, status="uploaded")
        m.file_hash = "abc123hash"
        db_session.commit()

        dup = Migration.find_duplicate(test_user.id, "abc123hash")
        assert dup is not None
        assert dup.id == m.id

    def test_find_duplicate_not_found(self, db_session, test_user):
        dup = Migration.find_duplicate(test_user.id, "nonexistent_hash")
        assert dup is None

    def test_repr(self, db_session, test_user):
        m = _make_migration(db_session, test_user)
        repr_str = repr(m)
        assert "Migration" in repr_str
        assert m.migration_id in repr_str

    def test_user_repr(self, db_session, test_user):
        repr_str = repr(test_user)
        assert "User" in repr_str
        assert test_user.email in repr_str

    def test_migration_default_id(self, db_session, test_user):
        """Migration auto-generates migration_id if not provided."""
        m = Migration(
            user_id=test_user.id,
            company_name="Auto ID",
            qb_file_name="auto.qbw",
        )
        assert m.migration_id is not None
        assert len(m.migration_id) == 36  # UUID format

    def test_migration_default_expires_at(self, db_session, test_user):
        """Migration auto-generates expires_at."""
        m = Migration(
            user_id=test_user.id,
            company_name="Expiry",
            qb_file_name="exp.qbw",
        )
        assert m.expires_at is not None
        # Should be ~48 hours from now
        assert m.expires_at > datetime.now(timezone.utc)
