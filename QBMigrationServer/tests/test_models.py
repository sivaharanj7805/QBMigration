"""
Comprehensive tests for User, Migration, and MigrationCredit models.

Tests cover all public methods, edge cases, and state transitions
for the three core domain models.
"""

import pytest
from datetime import datetime, timezone, timedelta
from models.database import db
from models.user import User
from models.migration import Migration
from models.migration_credit import MigrationCredit

# ============================================================================
# USER MODEL TESTS
# ============================================================================


class TestUserModel:
    """Tests for User model methods."""

    # ------------------------------------------------------------------------
    # is_locked()
    # ------------------------------------------------------------------------

    def test_is_locked_returns_false_when_no_lock(self, app, db_session, test_user):
        """Account with no lock timestamp should not be locked."""
        test_user.account_locked_until = None
        test_user.failed_login_attempts = 0
        db_session.commit()

        assert test_user.is_locked() is False

    def test_is_locked_returns_true_when_lock_active(self, app, db_session, test_user):
        """Account locked until a future time should report as locked."""
        test_user.account_locked_until = datetime.now(timezone.utc) + timedelta(
            minutes=10
        )
        test_user.failed_login_attempts = 5
        db_session.commit()

        assert test_user.is_locked() is True

    def test_is_locked_returns_false_when_lock_expired(
        self, app, db_session, test_user
    ):
        """Account whose lock has expired should not be locked."""
        test_user.account_locked_until = datetime.now(timezone.utc) - timedelta(
            minutes=1
        )
        test_user.failed_login_attempts = 5
        db_session.commit()

        assert test_user.is_locked() is False
        # Side effect: resets fields after expired lock
        assert test_user.failed_login_attempts == 0
        assert test_user.account_locked_until is None

    def test_is_locked_handles_naive_datetime(self, app, db_session, test_user):
        """is_locked should handle naive datetime stored in account_locked_until."""
        # Store a naive datetime in the future (no tzinfo)
        test_user.account_locked_until = datetime.utcnow() + timedelta(minutes=10)
        test_user.failed_login_attempts = 5
        db_session.commit()

        assert test_user.is_locked() is True

    def test_is_locked_handles_naive_datetime_expired(self, app, db_session, test_user):
        """is_locked should handle expired naive datetime."""
        test_user.account_locked_until = datetime.utcnow() - timedelta(minutes=1)
        test_user.failed_login_attempts = 5
        db_session.commit()

        assert test_user.is_locked() is False

    # ------------------------------------------------------------------------
    # record_failed_login()
    # ------------------------------------------------------------------------

    def test_record_failed_login_increments_counter(self, app, db_session, test_user):
        """Each failed login should increment the failed attempts counter."""
        test_user.failed_login_attempts = 0
        db_session.commit()

        test_user.record_failed_login()

        assert test_user.failed_login_attempts == 1
        assert test_user.last_failed_login is not None
        assert test_user.account_locked_until is None  # Not yet at threshold

    def test_record_failed_login_locks_at_threshold(self, app, db_session, test_user):
        """Account should lock after 5 failed attempts."""
        test_user.failed_login_attempts = 4
        db_session.commit()

        test_user.record_failed_login()

        assert test_user.failed_login_attempts == 5
        assert test_user.account_locked_until is not None
        # Lock duration should be approximately 15 minutes
        expected_lock = datetime.now(timezone.utc) + timedelta(minutes=15)
        assert abs((test_user.account_locked_until - expected_lock).total_seconds()) < 5

    def test_record_failed_login_continues_past_threshold(
        self, app, db_session, test_user
    ):
        """Failed logins should continue to increment past the threshold."""
        test_user.failed_login_attempts = 5
        test_user.account_locked_until = datetime.now(timezone.utc) + timedelta(
            minutes=15
        )
        db_session.commit()

        test_user.record_failed_login()

        assert test_user.failed_login_attempts == 6

    def test_record_failed_login_sets_last_failed_login_timestamp(
        self, app, db_session, test_user
    ):
        """last_failed_login should be set to current UTC time."""
        before = datetime.now(timezone.utc)
        test_user.record_failed_login()
        after = datetime.now(timezone.utc)

        assert test_user.last_failed_login is not None
        # Allow for naive datetime comparison
        ts = test_user.last_failed_login
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        assert before <= ts <= after

    # ------------------------------------------------------------------------
    # record_successful_login()
    # ------------------------------------------------------------------------

    def test_record_successful_login_resets_failed_attempts(
        self, app, db_session, test_user
    ):
        """Successful login should reset all lockout fields."""
        test_user.failed_login_attempts = 3
        test_user.last_failed_login = datetime.now(timezone.utc)
        test_user.account_locked_until = datetime.now(timezone.utc) + timedelta(
            minutes=10
        )
        db_session.commit()

        test_user.record_successful_login()

        assert test_user.failed_login_attempts == 0
        assert test_user.last_failed_login is None
        assert test_user.account_locked_until is None

    def test_record_successful_login_updates_timestamps(
        self, app, db_session, test_user
    ):
        """Successful login should update last_login and last_login_at."""
        before = datetime.now(timezone.utc)
        test_user.record_successful_login()
        after = datetime.now(timezone.utc)

        assert test_user.last_login is not None
        assert test_user.last_login_at is not None

    def test_record_successful_login_records_ip(self, app, db_session, test_user):
        """Successful login should record IP address for anomaly detection."""
        test_user.record_successful_login(ip_address="192.168.1.100")

        assert test_user.last_login_ip == "192.168.1.100"

    def test_record_successful_login_without_ip(self, app, db_session, test_user):
        """Successful login without IP should not change last_login_ip."""
        test_user.last_login_ip = "10.0.0.1"
        db_session.commit()

        test_user.record_successful_login()

        assert test_user.last_login_ip == "10.0.0.1"

    # ------------------------------------------------------------------------
    # get_tier_info()
    # ------------------------------------------------------------------------

    def test_get_tier_info_no_tier(self, app, db_session, test_user):
        """User with no tier should return sensible defaults."""
        test_user.subscription_tier = None
        db_session.commit()

        info = test_user.get_tier_info()

        assert "migrations_purchased" in info
        assert "migrations_used" in info
        assert "migrations_remaining" in info

    def test_get_tier_info_with_credits(self, app, db_session, test_user):
        """Tier info should reflect MigrationCredit records."""
        test_user.subscription_tier = "business"
        db_session.commit()

        # Create paid available credits
        for i in range(2):
            credit = MigrationCredit(
                user_id=test_user.id,
                tier_type="business",
                transaction_limit=25000,
                price_cents=99700,
                stripe_checkout_session_id="sess_tier_info_{}".format(i),
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
            db_session.add(credit)

        # Create one used credit
        used_credit = MigrationCredit(
            user_id=test_user.id,
            tier_type="business",
            transaction_limit=25000,
            price_cents=99700,
            stripe_checkout_session_id="sess_tier_info_used",
            payment_status="paid",
            status="used",
            paid_at=datetime.now(timezone.utc),
            used_at=datetime.now(timezone.utc),
        )
        db_session.add(used_credit)
        db_session.commit()

        info = test_user.get_tier_info()

        assert info["tier"] == "business"
        assert info["migrations_purchased"] == 3  # 2 available + 1 used
        assert info["migrations_used"] == 1
        assert info["migrations_remaining"] == 2
        assert info["has_tier"] is True

    def test_get_tier_info_returns_correct_keys(self, app, db_session, test_user):
        """get_tier_info should return all expected keys."""
        test_user.subscription_tier = "starter"
        db_session.commit()

        info = test_user.get_tier_info()

        expected_keys = {
            "tier",
            "tier_name",
            "max_transactions",
            "migrations_purchased",
            "migrations_used",
            "migrations_remaining",
            "has_tier",
        }
        assert expected_keys == set(info.keys())

    # ------------------------------------------------------------------------
    # get_migrations_remaining()
    # ------------------------------------------------------------------------

    def test_get_migrations_remaining_basic(self, app, db_session, test_user):
        """Should return purchased minus used."""
        test_user.migrations_purchased = 5
        test_user.migrations_used = 2
        db_session.commit()

        assert test_user.get_migrations_remaining() == 3

    def test_get_migrations_remaining_zero(self, app, db_session, test_user):
        """Should return 0 when all used."""
        test_user.migrations_purchased = 3
        test_user.migrations_used = 3
        db_session.commit()

        assert test_user.get_migrations_remaining() == 0

    def test_get_migrations_remaining_never_negative(self, app, db_session, test_user):
        """Should never return negative even if used > purchased."""
        test_user.migrations_purchased = 1
        test_user.migrations_used = 5
        db_session.commit()

        assert test_user.get_migrations_remaining() == 0

    def test_get_migrations_remaining_handles_none(self, app, db_session, test_user):
        """Should handle None values gracefully via getattr fallback."""
        # The column has NOT NULL constraint, so we test the getattr fallback
        # by creating a user-like object. The method uses getattr with None default.
        # With default values of 0 (NOT NULL), remaining should be 0.
        test_user.migrations_purchased = 0
        test_user.migrations_used = 0
        db_session.commit()

        assert test_user.get_migrations_remaining() == 0

    # ------------------------------------------------------------------------
    # add_migrations()
    # ------------------------------------------------------------------------

    def test_add_migrations_basic(self, app, db_session, test_user):
        """Should add to migrations_purchased."""
        test_user.migrations_purchased = 0
        db_session.commit()

        test_user.add_migrations(3)

        assert test_user.migrations_purchased == 3

    def test_add_migrations_cumulative(self, app, db_session, test_user):
        """Multiple calls should accumulate."""
        test_user.migrations_purchased = 2
        db_session.commit()

        test_user.add_migrations(3)

        assert test_user.migrations_purchased == 5

    def test_add_migrations_with_tier(self, app, db_session, test_user):
        """Should set subscription_tier and tier_purchased_at when tier provided."""
        test_user.subscription_tier = None
        test_user.tier_purchased_at = None
        db_session.commit()

        test_user.add_migrations(1, tier="professional")

        assert test_user.subscription_tier == "professional"
        assert test_user.tier_purchased_at is not None

    def test_add_migrations_without_tier(self, app, db_session, test_user):
        """Should not change tier when no tier provided."""
        test_user.subscription_tier = "starter"
        db_session.commit()

        test_user.add_migrations(1)

        assert test_user.subscription_tier == "starter"

    def test_add_migrations_handles_none_purchased(self, app, db_session, test_user):
        """Should handle zero migrations_purchased and add correctly."""
        test_user.migrations_purchased = 0
        db_session.commit()

        test_user.add_migrations(2)

        assert test_user.migrations_purchased == 2

    # ------------------------------------------------------------------------
    # has_role()
    # ------------------------------------------------------------------------

    def test_has_role_matches_exact(self, app, db_session, test_user):
        """has_role should return True for exact match."""
        test_user.role = "admin"
        db_session.commit()

        assert test_user.has_role("admin") is True

    def test_has_role_no_match(self, app, db_session, test_user):
        """has_role should return False when role does not match."""
        test_user.role = "user"
        db_session.commit()

        assert test_user.has_role("admin") is False

    def test_has_role_default_user(self, app, db_session, test_user):
        """Default role should be 'user'."""
        assert test_user.has_role("user") is True

    # ------------------------------------------------------------------------
    # is_admin()
    # ------------------------------------------------------------------------

    def test_is_admin_with_admin_role(self, app, db_session, test_user):
        """Admin role should be recognized as admin."""
        test_user.role = "admin"
        db_session.commit()

        assert test_user.is_admin() is True

    def test_is_admin_with_super_admin_role(self, app, db_session, test_user):
        """Super admin should also be recognized as admin."""
        test_user.role = "super_admin"
        db_session.commit()

        assert test_user.is_admin() is True

    def test_is_admin_with_user_role(self, app, db_session, test_user):
        """Regular user should not be admin."""
        test_user.role = "user"
        db_session.commit()

        assert test_user.is_admin() is False

    def test_is_admin_with_support_role(self, app, db_session, test_user):
        """Support role should not be admin (below admin in hierarchy)."""
        test_user.role = "support"
        db_session.commit()

        assert test_user.is_admin() is False

    # ------------------------------------------------------------------------
    # is_super_admin()
    # ------------------------------------------------------------------------

    def test_is_super_admin_true(self, app, db_session, test_user):
        """super_admin role should return True."""
        test_user.role = "super_admin"
        db_session.commit()

        assert test_user.is_super_admin() is True

    def test_is_super_admin_false_for_admin(self, app, db_session, test_user):
        """Admin is not super_admin."""
        test_user.role = "admin"
        db_session.commit()

        assert test_user.is_super_admin() is False

    def test_is_super_admin_false_for_user(self, app, db_session, test_user):
        """Regular user is not super_admin."""
        test_user.role = "user"
        db_session.commit()

        assert test_user.is_super_admin() is False

    # ------------------------------------------------------------------------
    # reset failed attempts (record_successful_login acts as the reset)
    # ------------------------------------------------------------------------

    def test_reset_failed_attempts_via_successful_login(
        self, app, db_session, test_user
    ):
        """Successful login resets failed_login_attempts to 0."""
        test_user.failed_login_attempts = 4
        db_session.commit()

        test_user.record_successful_login()

        assert test_user.failed_login_attempts == 0

    # ------------------------------------------------------------------------
    # use_migration() and has_migrations_remaining()
    # ------------------------------------------------------------------------

    def test_use_migration_decrements(self, app, db_session, test_user):
        """use_migration should increment migrations_used."""
        test_user.migrations_purchased = 3
        test_user.migrations_used = 0
        db_session.commit()

        result = test_user.use_migration()

        assert result is True
        assert test_user.migrations_used == 1

    def test_use_migration_fails_when_none_remaining(self, app, db_session, test_user):
        """use_migration should return False when no migrations remaining."""
        test_user.migrations_purchased = 1
        test_user.migrations_used = 1
        db_session.commit()

        result = test_user.use_migration()

        assert result is False
        assert test_user.migrations_used == 1

    def test_has_migrations_remaining_true(self, app, db_session, test_user):
        """Should return True when there are remaining migrations."""
        test_user.migrations_purchased = 5
        test_user.migrations_used = 2
        db_session.commit()

        assert test_user.has_migrations_remaining() is True

    def test_has_migrations_remaining_false(self, app, db_session, test_user):
        """Should return False when all used up."""
        test_user.migrations_purchased = 3
        test_user.migrations_used = 3
        db_session.commit()

        assert test_user.has_migrations_remaining() is False

    # ------------------------------------------------------------------------
    # __repr__
    # ------------------------------------------------------------------------

    def test_repr(self, app, db_session, test_user):
        """User repr should include email."""
        assert "test@example.com" in repr(test_user)


# ============================================================================
# MIGRATION MODEL TESTS
# ============================================================================


class TestMigrationModel:
    """Tests for Migration model methods."""

    # ------------------------------------------------------------------------
    # __init__ defaults
    # ------------------------------------------------------------------------

    def test_migration_generates_uuid(self, app, db_session, test_user):
        """Migration should auto-generate a UUID migration_id."""
        migration = Migration(user_id=test_user.id, status="pending")
        db_session.add(migration)
        db_session.commit()

        assert migration.migration_id is not None
        assert len(migration.migration_id) == 36  # UUID format

    def test_migration_sets_default_expiry(self, app, db_session, test_user):
        """Migration should have a default expiry of 48 hours."""
        before = datetime.now(timezone.utc)
        migration = Migration(user_id=test_user.id, status="pending")
        db_session.add(migration)
        db_session.commit()
        after = datetime.now(timezone.utc)

        expected_min = before + timedelta(hours=48)
        expected_max = after + timedelta(hours=48)
        assert expected_min <= migration.expires_at <= expected_max

    # ------------------------------------------------------------------------
    # mark_as_uploading()
    # ------------------------------------------------------------------------

    def test_mark_as_uploading_from_pending(self, app, db_session, test_migration):
        """Should transition from pending to uploading."""
        assert test_migration.status == "pending"

        result = test_migration.mark_as_uploading()

        assert result is True
        assert test_migration.status == "uploading"

    def test_mark_as_uploading_idempotent(self, app, db_session, test_migration):
        """Should not change status if already uploading."""
        test_migration.status = "uploading"
        db_session.commit()

        result = test_migration.mark_as_uploading()

        assert result is False
        assert test_migration.status == "uploading"

    def test_mark_as_uploading_rejects_wrong_status(
        self, app, db_session, test_migration
    ):
        """Should reject transition from non-pending status."""
        test_migration.status = "processing"
        db_session.commit()

        result = test_migration.mark_as_uploading()

        assert result is False
        assert test_migration.status == "processing"

    # ------------------------------------------------------------------------
    # mark_as_uploaded()
    # ------------------------------------------------------------------------

    def test_mark_as_uploaded_from_uploading(self, app, db_session, test_migration):
        """Should transition from uploading to uploaded with S3 info."""
        test_migration.status = "uploading"
        db_session.commit()

        result = test_migration.mark_as_uploaded(
            s3_uri="s3://bucket/key", s3_bucket="bucket", s3_key="key"
        )

        assert result is True
        assert test_migration.status == "uploaded"
        assert test_migration.s3_uri == "s3://bucket/key"
        assert test_migration.s3_bucket == "bucket"
        assert test_migration.s3_key == "key"

    def test_mark_as_uploaded_from_pending(self, app, db_session, test_migration):
        """Should also accept transition from pending."""
        result = test_migration.mark_as_uploaded(
            s3_uri="s3://b/k", s3_bucket="b", s3_key="k"
        )

        assert result is True
        assert test_migration.status == "uploaded"

    def test_mark_as_uploaded_rejects_processing(self, app, db_session, test_migration):
        """Should reject transition from processing."""
        test_migration.status = "processing"
        db_session.commit()

        result = test_migration.mark_as_uploaded(
            s3_uri="s3://b/k", s3_bucket="b", s3_key="k"
        )

        assert result is False
        assert test_migration.status == "processing"

    # ------------------------------------------------------------------------
    # mark_as_processing()
    # ------------------------------------------------------------------------

    def test_mark_as_processing_from_uploaded(self, app, db_session, test_migration):
        """Should transition from uploaded to processing."""
        test_migration.status = "uploaded"
        db_session.commit()

        result = test_migration.mark_as_processing(instance_id="i-abc123")

        assert result is True
        assert test_migration.status == "processing"
        assert test_migration.aws_instance_id == "i-abc123"
        assert test_migration.started_at is not None

    def test_mark_as_processing_from_provisioning(
        self, app, db_session, test_migration
    ):
        """Should accept transition from provisioning."""
        test_migration.status = "provisioning"
        db_session.commit()

        result = test_migration.mark_as_processing(instance_id="i-xyz789")

        assert result is True
        assert test_migration.status == "processing"

    def test_mark_as_processing_rejects_pending(self, app, db_session, test_migration):
        """Should reject transition from pending."""
        result = test_migration.mark_as_processing(instance_id="i-nope")

        assert result is False
        assert test_migration.status == "pending"

    # ------------------------------------------------------------------------
    # mark_as_completed()
    # ------------------------------------------------------------------------

    def test_mark_as_completed_with_results(self, app, db_session, test_migration):
        """Should complete migration with results and trial balance."""
        test_migration.status = "processing"
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        results = {
            "customers": 100,
            "vendors": 50,
            "invoices": 200,
            "bills": 75,
            "items": 30,
            "total": 455,
            "trial_balance": {
                "is_balanced": True,
                "source_total": 50000.00,
                "destination_total": 50000.00,
            },
        }

        result = test_migration.mark_as_completed(results)

        assert result is True
        assert test_migration.status == "completed"
        assert test_migration.progress_percent == 100
        assert test_migration.completed_at is not None
        assert test_migration.customers_migrated == 100
        assert test_migration.vendors_migrated == 50
        assert test_migration.invoices_migrated == 200
        assert test_migration.bills_migrated == 75
        assert test_migration.items_migrated == 30
        assert test_migration.total_records_migrated == 455

    def test_mark_as_completed_rejects_non_processing(
        self, app, db_session, test_migration
    ):
        """Should not complete a migration that is not processing."""
        test_migration.status = "uploaded"
        db_session.commit()

        result = test_migration.mark_as_completed()

        assert result is False
        assert test_migration.status == "uploaded"

    def test_mark_as_completed_fails_on_unbalanced_trial(
        self, app, db_session, test_migration
    ):
        """Should fail if trial balance has discrepancy."""
        test_migration.status = "processing"
        test_migration.started_at = datetime.now(timezone.utc)
        db_session.commit()

        results = {
            "trial_balance": {
                "is_balanced": False,
                "source_total": 50000.00,
                "destination_total": 49000.00,
            }
        }

        with pytest.raises(ValueError, match="Trial balance reconciliation failed"):
            test_migration.mark_as_completed(results)

        assert test_migration.status == "failed"
        assert test_migration.error_code == "TRIAL_BALANCE_MISMATCH"

    def test_mark_as_completed_fails_without_trial_balance(
        self, app, db_session, test_migration
    ):
        """Should fail when results provided without trial_balance data."""
        test_migration.status = "processing"
        test_migration.started_at = datetime.now(timezone.utc)
        db_session.commit()

        results = {"customers": 10, "total": 10}

        with pytest.raises(ValueError, match="Trial balance verification data missing"):
            test_migration.mark_as_completed(results)

        assert test_migration.status == "failed"
        assert test_migration.error_code == "TRIAL_BALANCE_MISSING"

    def test_mark_as_completed_no_results(self, app, db_session, test_migration):
        """Should complete with None results (no trial balance check needed)."""
        test_migration.status = "processing"
        test_migration.started_at = datetime.now(timezone.utc)
        db_session.commit()

        result = test_migration.mark_as_completed(results=None)

        assert result is True
        assert test_migration.status == "completed"

    # ------------------------------------------------------------------------
    # mark_as_failed()
    # ------------------------------------------------------------------------

    def test_mark_as_failed_from_processing(self, app, db_session, test_migration):
        """Should mark a processing migration as failed."""
        test_migration.status = "processing"
        db_session.commit()

        result = test_migration.mark_as_failed(
            error_message="Connection lost", error_code="CONNECTION_TIMEOUT"
        )

        assert result is True
        assert test_migration.status == "failed"
        assert test_migration.error_code == "CONNECTION_TIMEOUT"
        assert test_migration.completed_at is not None

    def test_mark_as_failed_from_pending(self, app, db_session, test_migration):
        """Should allow failure from pending status."""
        result = test_migration.mark_as_failed(
            error_message="Invalid file", error_code="INVALID_FILE"
        )

        assert result is True
        assert test_migration.status == "failed"

    def test_mark_as_failed_rejects_completed(self, app, db_session, test_migration):
        """Should not overwrite a completed migration."""
        test_migration.status = "completed"
        db_session.commit()

        result = test_migration.mark_as_failed("Late error")

        assert result is False
        assert test_migration.status == "completed"

    def test_mark_as_failed_rejects_cleaned(self, app, db_session, test_migration):
        """Should not overwrite a cleaned migration."""
        test_migration.status = "cleaned"
        db_session.commit()

        result = test_migration.mark_as_failed("Too late")

        assert result is False
        assert test_migration.status == "cleaned"

    def test_mark_as_failed_stores_encrypted_error(
        self, app, db_session, test_migration
    ):
        """Error message should be encrypted when stored."""
        test_migration.status = "processing"
        db_session.commit()

        test_migration.mark_as_failed("Sensitive QB data error")

        # The raw encrypted field should differ from the plaintext
        assert test_migration.error_message_encrypted is not None
        assert test_migration.error_message_encrypted != "Sensitive QB data error"

    # ------------------------------------------------------------------------
    # can_retry()
    # ------------------------------------------------------------------------

    def test_can_retry_true_when_under_max(self, app, db_session, test_migration):
        """Should return True when retry_count < max_retries."""
        test_migration.retry_count = 0
        test_migration.max_retries = 3
        test_migration.status = "failed"
        db_session.commit()

        assert test_migration.can_retry() is True

    def test_can_retry_false_at_max(self, app, db_session, test_migration):
        """Should return False when retry_count >= max_retries."""
        test_migration.retry_count = 3
        test_migration.max_retries = 3
        test_migration.status = "failed"
        db_session.commit()

        assert test_migration.can_retry() is False

    def test_can_retry_false_over_max(self, app, db_session, test_migration):
        """Should return False when retry_count > max_retries."""
        test_migration.retry_count = 5
        test_migration.max_retries = 3
        db_session.commit()

        assert test_migration.can_retry() is False

    # ------------------------------------------------------------------------
    # increment_retry()
    # ------------------------------------------------------------------------

    def test_increment_retry(self, app, db_session, test_migration):
        """Should increment retry_count by 1."""
        test_migration.retry_count = 1
        db_session.commit()

        test_migration.increment_retry()

        assert test_migration.retry_count == 2

    def test_increment_retry_from_zero(self, app, db_session, test_migration):
        """Should increment from 0 to 1."""
        test_migration.retry_count = 0
        db_session.commit()

        test_migration.increment_retry()

        assert test_migration.retry_count == 1

    # ------------------------------------------------------------------------
    # is_expired()
    # ------------------------------------------------------------------------

    def test_is_expired_true(self, app, db_session, test_migration):
        """Should return True when expires_at is in the past."""
        test_migration.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        assert test_migration.is_expired() is True

    def test_is_expired_false(self, app, db_session, test_migration):
        """Should return False when expires_at is in the future."""
        test_migration.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        db_session.commit()

        assert test_migration.is_expired() is False

    # ------------------------------------------------------------------------
    # is_stuck()
    # ------------------------------------------------------------------------

    def test_is_stuck_true(self, app, db_session, test_migration):
        """Should return True when processing for longer than timeout."""
        test_migration.status = "processing"
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(hours=7)
        db_session.commit()

        assert test_migration.is_stuck() is True

    def test_is_stuck_false_within_timeout(self, app, db_session, test_migration):
        """Should return False when within timeout period."""
        test_migration.status = "processing"
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        assert test_migration.is_stuck() is False

    def test_is_stuck_false_not_processing(self, app, db_session, test_migration):
        """Should return False if not in processing status."""
        test_migration.status = "completed"
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(hours=100)
        db_session.commit()

        assert test_migration.is_stuck() is False

    def test_is_stuck_false_no_started_at(self, app, db_session, test_migration):
        """Should return False if started_at is None."""
        test_migration.status = "processing"
        test_migration.started_at = None
        db_session.commit()

        assert test_migration.is_stuck() is False

    def test_is_stuck_custom_timeout(self, app, db_session, test_migration):
        """Should respect custom timeout_hours parameter."""
        test_migration.status = "processing"
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(hours=3)
        db_session.commit()

        assert test_migration.is_stuck(timeout_hours=2) is True
        assert test_migration.is_stuck(timeout_hours=4) is False

    # ------------------------------------------------------------------------
    # needs_cleanup()
    # ------------------------------------------------------------------------

    def test_needs_cleanup_completed(self, app, db_session, test_migration):
        """Completed migration with cleanup_completed=False needs cleanup."""
        test_migration.status = "completed"
        test_migration.cleanup_completed = False
        db_session.commit()

        assert test_migration.needs_cleanup() is True

    def test_needs_cleanup_failed(self, app, db_session, test_migration):
        """Failed migration with cleanup_completed=False needs cleanup."""
        test_migration.status = "failed"
        test_migration.cleanup_completed = False
        db_session.commit()

        assert test_migration.needs_cleanup() is True

    def test_needs_cleanup_false_already_cleaned(self, app, db_session, test_migration):
        """Migration with cleanup_completed=True does not need cleanup."""
        test_migration.status = "completed"
        test_migration.cleanup_completed = True
        db_session.commit()

        assert test_migration.needs_cleanup() is False

    def test_needs_cleanup_expired(self, app, db_session, test_migration):
        """Expired migration needs cleanup."""
        test_migration.status = "pending"
        test_migration.cleanup_completed = False
        test_migration.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        assert test_migration.needs_cleanup() is True

    def test_needs_cleanup_stuck(self, app, db_session, test_migration):
        """Stuck migration needs cleanup."""
        test_migration.status = "processing"
        test_migration.cleanup_completed = False
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(hours=10)
        # Set expires_at to a future aware datetime so is_expired() does not
        # hit a naive vs aware comparison error before is_stuck() is reached
        test_migration.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        db_session.commit()

        assert test_migration.needs_cleanup() is True

    def test_needs_cleanup_pending_not_expired(self, app, db_session, test_migration):
        """Pending non-expired migration does not need cleanup."""
        test_migration.status = "pending"
        test_migration.cleanup_completed = False
        test_migration.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        db_session.commit()

        assert test_migration.needs_cleanup() is False

    # ------------------------------------------------------------------------
    # get_duration_minutes()
    # ------------------------------------------------------------------------

    def test_get_duration_minutes_completed(self, app, db_session, test_migration):
        """Should return minutes between started_at and completed_at."""
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        test_migration.completed_at = datetime.now(timezone.utc)
        db_session.commit()

        duration = test_migration.get_duration_minutes()

        assert duration == 120

    def test_get_duration_minutes_in_progress(self, app, db_session, test_migration):
        """Should use current time when not completed."""
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        test_migration.completed_at = None
        db_session.commit()

        duration = test_migration.get_duration_minutes()

        assert 29 <= duration <= 31

    def test_get_duration_minutes_not_started(self, app, db_session, test_migration):
        """Should return 0 when not started."""
        test_migration.started_at = None
        db_session.commit()

        assert test_migration.get_duration_minutes() == 0

    # ------------------------------------------------------------------------
    # calculate_file_hash()
    # ------------------------------------------------------------------------

    def test_calculate_file_hash_string(self, app, db_session, test_migration):
        """Should calculate SHA-256 hash from string data."""
        test_migration.calculate_file_hash("hello world")

        assert test_migration.file_hash is not None
        assert len(test_migration.file_hash) == 64  # SHA-256 hex digest
        # Known hash of 'hello world'
        assert (
            test_migration.file_hash
            == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        )

    def test_calculate_file_hash_bytes(self, app, db_session, test_migration):
        """Should calculate SHA-256 hash from bytes data."""
        test_migration.calculate_file_hash(b"hello world")

        assert test_migration.file_hash is not None
        assert len(test_migration.file_hash) == 64

    def test_calculate_file_hash_deterministic(self, app, db_session, test_migration):
        """Same data should produce same hash."""
        test_migration.calculate_file_hash("test data")
        hash1 = test_migration.file_hash

        test_migration.calculate_file_hash("test data")
        hash2 = test_migration.file_hash

        assert hash1 == hash2

    def test_calculate_file_hash_different_data(self, app, db_session, test_migration):
        """Different data should produce different hashes."""
        test_migration.calculate_file_hash("data1")
        hash1 = test_migration.file_hash

        test_migration.calculate_file_hash("data2")
        hash2 = test_migration.file_hash

        assert hash1 != hash2

    # ------------------------------------------------------------------------
    # estimate_cost()
    # ------------------------------------------------------------------------

    def test_estimate_cost_with_data(self, app, db_session, test_migration):
        """Should estimate cost based on data_size_bytes."""
        test_migration.data_size_bytes = 1024 * 1024 * 100  # 100 MB
        db_session.commit()

        test_migration.estimate_cost()

        assert test_migration.estimated_cost_usd is not None
        assert float(test_migration.estimated_cost_usd) > 0
        assert test_migration.cost_breakdown is not None

    def test_estimate_cost_no_data(self, app, db_session, test_migration):
        """Should not set cost when no data_size_bytes."""
        test_migration.data_size_bytes = None
        db_session.commit()

        test_migration.estimate_cost()

        assert test_migration.estimated_cost_usd is None

    def test_estimate_cost_breakdown_has_components(
        self, app, db_session, test_migration
    ):
        """Cost breakdown should include s3, ec2, and data_transfer components."""
        import json

        test_migration.data_size_bytes = 1024 * 1024 * 500  # 500 MB
        db_session.commit()

        test_migration.estimate_cost()

        breakdown = json.loads(test_migration.cost_breakdown)
        assert "s3_storage" in breakdown
        assert "ec2_compute" in breakdown
        assert "data_transfer" in breakdown

    # ------------------------------------------------------------------------
    # to_dict()
    # ------------------------------------------------------------------------

    def test_to_dict_basic_fields(self, app, db_session, test_migration):
        """to_dict should include all basic fields."""
        result = test_migration.to_dict()

        assert "migration_id" in result
        assert "status" in result
        assert "progress_percent" in result
        assert "company_name" in result
        assert "created_at" in result
        assert "destination" in result
        assert result["status"] == "pending"

    def test_to_dict_excludes_sensitive_by_default(
        self, app, db_session, test_migration
    ):
        """to_dict without include_sensitive should not include S3/AWS details."""
        result = test_migration.to_dict()

        assert "s3_uri" not in result
        assert "aws_instance_id" not in result
        assert "file_hash" not in result

    def test_to_dict_includes_sensitive(self, app, db_session, test_migration):
        """to_dict with include_sensitive=True should include all details."""
        test_migration.s3_uri = "s3://bucket/key"
        test_migration.aws_instance_id = "i-test123"
        db_session.commit()

        result = test_migration.to_dict(include_sensitive=True)

        assert result["s3_uri"] == "s3://bucket/key"
        assert result["aws_instance_id"] == "i-test123"
        assert "cleanup_completed" in result
        assert "expires_at" in result

    def test_to_dict_error_fields_only_on_failed(self, app, db_session, test_migration):
        """Error message and code should only appear when status is failed."""
        test_migration.status = "pending"
        db_session.commit()

        result = test_migration.to_dict()

        assert result["error_message"] is None
        assert result["error_code"] is None
        assert result["can_retry"] is False

    def test_to_dict_shows_error_on_failed(self, app, db_session, test_migration):
        """Failed migration should show error info in to_dict."""
        test_migration.status = "failed"
        test_migration.set_error_message("Something broke")
        test_migration.error_code = "BROKEN"
        test_migration.retry_count = 0
        test_migration.max_retries = 3
        db_session.commit()

        result = test_migration.to_dict()

        assert result["error_code"] == "BROKEN"
        assert result["can_retry"] is True

    # ------------------------------------------------------------------------
    # __repr__
    # ------------------------------------------------------------------------

    def test_repr(self, app, db_session, test_migration):
        """Migration repr should include migration_id and status."""
        repr_str = repr(test_migration)
        assert test_migration.migration_id in repr_str
        assert test_migration.status in repr_str


# ============================================================================
# MIGRATION CREDIT MODEL TESTS
# ============================================================================


class TestMigrationCreditModel:
    """Tests for MigrationCredit model methods."""

    # ------------------------------------------------------------------------
    # TIER_CONFIG validation
    # ------------------------------------------------------------------------

    def test_tier_config_starter(self, app, db_session):
        """Starter tier should have correct config."""
        config = MigrationCredit.TIER_CONFIG["starter"]
        assert config["price_cents"] == 49700
        assert config["transaction_limit"] == 5000

    def test_tier_config_business(self, app, db_session):
        """Business tier should have correct config."""
        config = MigrationCredit.TIER_CONFIG["business"]
        assert config["price_cents"] == 99700
        assert config["transaction_limit"] == 25000

    def test_tier_config_professional(self, app, db_session):
        """Professional tier should have correct config."""
        config = MigrationCredit.TIER_CONFIG["professional"]
        assert config["price_cents"] == 199700
        assert config["transaction_limit"] == 100000

    def test_tier_config_enterprise(self, app, db_session):
        """Enterprise tier should have correct config."""
        config = MigrationCredit.TIER_CONFIG["enterprise"]
        assert config["price_cents"] == 399700
        assert config["transaction_limit"] == 500000

    def test_tier_config_forensic(self, app, db_session):
        """Forensic tier should have unlimited transactions."""
        config = MigrationCredit.TIER_CONFIG["forensic"]
        assert config["price_cents"] == 799700
        assert config["transaction_limit"] == -1

    # ------------------------------------------------------------------------
    # create_pending()
    # ------------------------------------------------------------------------

    def test_create_pending_basic(self, app, db_session, test_user):
        """Should create a pending credit with correct attributes."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="business",
            stripe_checkout_session_id="sess_pending_1",
        )

        assert credit.id is not None
        assert credit.user_id == test_user.id
        assert credit.tier_type == "business"
        assert credit.transaction_limit == 25000
        assert credit.price_cents == 99700
        assert credit.payment_status == "pending"
        assert credit.status == "pending"
        assert credit.stripe_checkout_session_id == "sess_pending_1"

    def test_create_pending_invalid_tier(self, app, db_session, test_user):
        """Should raise ValueError for invalid tier."""
        with pytest.raises(ValueError, match="Invalid tier type"):
            MigrationCredit.create_pending(
                user_id=test_user.id,
                tier_type="nonexistent",
                stripe_checkout_session_id="sess_invalid",
            )

    def test_create_pending_all_tiers(self, app, db_session, test_user):
        """Should create pending credits for each valid tier."""
        for i, tier in enumerate(MigrationCredit.TIER_CONFIG.keys()):
            credit = MigrationCredit.create_pending(
                user_id=test_user.id,
                tier_type=tier,
                stripe_checkout_session_id="sess_all_{}_{}".format(tier, i),
            )
            config = MigrationCredit.TIER_CONFIG[tier]
            assert credit.tier_type == tier
            assert credit.transaction_limit == config["transaction_limit"]
            assert credit.price_cents == config["price_cents"]

    def test_create_pending_no_auto_commit(self, app, db_session, test_user):
        """Should not commit when auto_commit=False."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_no_commit",
            auto_commit=False,
        )
        # Manually commit for cleanup
        db_session.commit()

        assert credit.tier_type == "starter"

    # ------------------------------------------------------------------------
    # mark_paid()
    # ------------------------------------------------------------------------

    def test_mark_paid(self, app, db_session, test_user):
        """Should update payment_status to paid and status to available."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_mark_paid",
        )

        credit.mark_paid(payment_intent_id="pi_test_123")

        assert credit.payment_status == "paid"
        assert credit.status == "available"
        assert credit.stripe_payment_intent_id == "pi_test_123"
        assert credit.paid_at is not None

    def test_mark_paid_no_auto_commit(self, app, db_session, test_user):
        """Should not commit when auto_commit=False."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="business",
            stripe_checkout_session_id="sess_paid_no_commit",
        )

        credit.mark_paid(payment_intent_id="pi_no_commit", auto_commit=False)
        db_session.commit()

        assert credit.payment_status == "paid"
        assert credit.status == "available"

    # ------------------------------------------------------------------------
    # mark_failed()
    # ------------------------------------------------------------------------

    def test_mark_failed(self, app, db_session, test_user):
        """Should update payment_status to failed and status to expired."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_mark_failed",
        )

        credit.mark_failed()

        assert credit.payment_status == "failed"
        assert credit.status == "expired"

    def test_mark_failed_no_auto_commit(self, app, db_session, test_user):
        """Should not commit when auto_commit=False."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_failed_no_commit",
        )

        credit.mark_failed(auto_commit=False)
        db_session.commit()

        assert credit.payment_status == "failed"
        assert credit.status == "expired"

    # ------------------------------------------------------------------------
    # use_for_migration()
    # ------------------------------------------------------------------------

    def test_use_for_migration_success(self, app, db_session, test_user):
        """Should mark credit as used with migration details."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="business",
            stripe_checkout_session_id="sess_use_success",
        )
        credit.mark_paid(payment_intent_id="pi_use_success")

        result = credit.use_for_migration(
            migration_id="mig-uuid-123", transactions_count=1000
        )

        assert result is True
        assert credit.status == "used"
        assert credit.migration_id == "mig-uuid-123"
        assert credit.transactions_used == 1000
        assert credit.used_at is not None

    def test_use_for_migration_fails_if_not_available(self, app, db_session, test_user):
        """Should return False if credit is not in available status."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_use_not_avail",
        )
        # Still in pending status

        result = credit.use_for_migration(migration_id="mig-1")

        assert result is False
        assert credit.status == "pending"

    def test_use_for_migration_fails_if_already_used(self, app, db_session, test_user):
        """Should return False if credit is already used."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_use_already",
        )
        credit.mark_paid(payment_intent_id="pi_use_already")
        credit.use_for_migration(migration_id="mig-first")

        result = credit.use_for_migration(migration_id="mig-second")

        assert result is False
        assert credit.migration_id == "mig-first"

    def test_use_for_migration_rejects_over_limit(self, app, db_session, test_user):
        """Should reject if transaction count exceeds credit limit."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_use_over",
        )
        credit.mark_paid(payment_intent_id="pi_use_over")

        # Starter limit is 5000
        result = credit.use_for_migration(
            migration_id="mig-big", transactions_count=10000
        )

        assert result is False
        assert credit.status == "available"

    def test_use_for_migration_unlimited_forensic(self, app, db_session, test_user):
        """Forensic credit should accept any transaction count."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="forensic",
            stripe_checkout_session_id="sess_use_forensic",
        )
        credit.mark_paid(payment_intent_id="pi_use_forensic")

        result = credit.use_for_migration(
            migration_id="mig-huge", transactions_count=999999
        )

        assert result is True
        assert credit.status == "used"

    # ------------------------------------------------------------------------
    # can_handle_transactions()
    # ------------------------------------------------------------------------

    def test_can_handle_transactions_within_limit(self, app, db_session, test_user):
        """Should return True when count is within limit."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="business",
            stripe_checkout_session_id="sess_handle_within",
        )

        assert credit.can_handle_transactions(5000) is True
        assert credit.can_handle_transactions(25000) is True

    def test_can_handle_transactions_over_limit(self, app, db_session, test_user):
        """Should return False when count exceeds limit."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_handle_over",
        )

        assert credit.can_handle_transactions(5001) is False

    def test_can_handle_transactions_unlimited(self, app, db_session, test_user):
        """Forensic tier should handle any transaction count."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="forensic",
            stripe_checkout_session_id="sess_handle_unlimited",
        )

        assert credit.can_handle_transactions(999999999) is True

    def test_can_handle_transactions_zero(self, app, db_session, test_user):
        """Should handle zero transactions."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_handle_zero",
        )

        assert credit.can_handle_transactions(0) is True

    def test_can_handle_transactions_exact_limit(self, app, db_session, test_user):
        """Should return True at exactly the transaction limit."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_handle_exact",
        )

        assert credit.can_handle_transactions(5000) is True

    # ------------------------------------------------------------------------
    # get_available_for_user()
    # ------------------------------------------------------------------------

    def test_get_available_for_user_returns_paid_available(
        self, app, db_session, test_user
    ):
        """Should return only paid+available credits."""
        # Available + paid
        c1 = MigrationCredit(
            user_id=test_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="sess_avail_1",
            payment_status="paid",
            status="available",
            paid_at=datetime.now(timezone.utc),
        )
        # Pending (not yet paid)
        c2 = MigrationCredit(
            user_id=test_user.id,
            tier_type="business",
            transaction_limit=25000,
            price_cents=99700,
            stripe_checkout_session_id="sess_avail_2",
            payment_status="pending",
            status="pending",
        )
        # Used (paid but used)
        c3 = MigrationCredit(
            user_id=test_user.id,
            tier_type="professional",
            transaction_limit=100000,
            price_cents=199700,
            stripe_checkout_session_id="sess_avail_3",
            payment_status="paid",
            status="used",
            paid_at=datetime.now(timezone.utc),
        )
        db_session.add_all([c1, c2, c3])
        db_session.commit()

        available = MigrationCredit.get_available_for_user(test_user.id)

        assert len(available) == 1
        assert available[0].id == c1.id

    def test_get_available_for_user_empty(self, app, db_session, test_user):
        """Should return empty list when no available credits."""
        available = MigrationCredit.get_available_for_user(test_user.id)

        assert available == []

    def test_get_available_for_user_multiple(self, app, db_session, test_user):
        """Should return all available credits for user."""
        for i in range(3):
            c = MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id="sess_avail_multi_{}".format(i),
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
            db_session.add(c)
        db_session.commit()

        available = MigrationCredit.get_available_for_user(test_user.id)

        assert len(available) == 3

    def test_get_available_for_user_excludes_other_users(
        self, app, db_session, test_user
    ):
        """Should not return credits belonging to other users."""
        # Create another user
        other_user = User(
            email="other@example.com", first_name="Other", last_name="User"
        )
        other_user.set_password("TestPassword1234")
        db_session.add(other_user)
        db_session.commit()

        # Credit for other user
        c = MigrationCredit(
            user_id=other_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="sess_other_user",
            payment_status="paid",
            status="available",
            paid_at=datetime.now(timezone.utc),
        )
        db_session.add(c)
        db_session.commit()

        available = MigrationCredit.get_available_for_user(test_user.id)

        assert len(available) == 0

    # ------------------------------------------------------------------------
    # get_credits_summary()
    # ------------------------------------------------------------------------

    def test_get_credits_summary_basic(self, app, db_session, test_user):
        """Should return summary grouped by tier."""
        # 2 available starter, 1 used starter
        for i in range(2):
            db_session.add(
                MigrationCredit(
                    user_id=test_user.id,
                    tier_type="starter",
                    transaction_limit=5000,
                    price_cents=49700,
                    stripe_checkout_session_id="sess_summary_avail_{}".format(i),
                    payment_status="paid",
                    status="available",
                    paid_at=datetime.now(timezone.utc),
                )
            )
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id="sess_summary_used",
                payment_status="paid",
                status="used",
                paid_at=datetime.now(timezone.utc),
            )
        )
        # 1 available business
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="business",
                transaction_limit=25000,
                price_cents=99700,
                stripe_checkout_session_id="sess_summary_biz",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        summary = MigrationCredit.get_credits_summary(test_user.id)

        assert "starter" in summary
        assert summary["starter"]["available"] == 2
        assert summary["starter"]["used"] == 1
        assert summary["starter"]["transaction_limit"] == 5000

        assert "business" in summary
        assert summary["business"]["available"] == 1
        assert summary["business"]["used"] == 0

    def test_get_credits_summary_excludes_unpaid(self, app, db_session, test_user):
        """Should only include paid credits in summary."""
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id="sess_summary_unpaid",
                payment_status="pending",
                status="pending",
            )
        )
        db_session.commit()

        summary = MigrationCredit.get_credits_summary(test_user.id)

        assert "starter" not in summary

    def test_get_credits_summary_empty(self, app, db_session, test_user):
        """Should return empty dict when no credits."""
        summary = MigrationCredit.get_credits_summary(test_user.id)

        assert summary == {}

    def test_get_credits_summary_excludes_zero_tiers(self, app, db_session, test_user):
        """Should only include tiers that have credits."""
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="enterprise",
                transaction_limit=500000,
                price_cents=399700,
                stripe_checkout_session_id="sess_summary_ent",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        summary = MigrationCredit.get_credits_summary(test_user.id)

        assert "enterprise" in summary
        assert "starter" not in summary
        assert "business" not in summary

    # ------------------------------------------------------------------------
    # find_best_credit()
    # ------------------------------------------------------------------------

    def test_find_best_credit_selects_smallest_suitable(
        self, app, db_session, test_user
    ):
        """Should select the smallest credit that can handle the transactions."""
        # Create starter (5000 limit) and business (25000 limit)
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="business",
                transaction_limit=25000,
                price_cents=99700,
                stripe_checkout_session_id="sess_best_biz",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id="sess_best_start",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        # 3000 transactions - starter is enough
        credit = MigrationCredit.find_best_credit(test_user.id, 3000)

        assert credit is not None
        assert credit.tier_type == "starter"

    def test_find_best_credit_skips_too_small(self, app, db_session, test_user):
        """Should skip credits that cannot handle the transaction count."""
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id="sess_best_small",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="business",
                transaction_limit=25000,
                price_cents=99700,
                stripe_checkout_session_id="sess_best_bigger",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        # 10000 transactions - starter too small, business fits
        credit = MigrationCredit.find_best_credit(test_user.id, 10000)

        assert credit is not None
        assert credit.tier_type == "business"

    def test_find_best_credit_none_suitable(self, app, db_session, test_user):
        """Should return None when no credit can handle the transactions."""
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id="sess_best_none",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        credit = MigrationCredit.find_best_credit(test_user.id, 100000)

        assert credit is None

    def test_find_best_credit_no_credits(self, app, db_session, test_user):
        """Should return None when user has no credits."""
        credit = MigrationCredit.find_best_credit(test_user.id, 100)

        assert credit is None

    def test_find_best_credit_forensic_last_resort(self, app, db_session, test_user):
        """Forensic (unlimited) should be used last since it sorts highest."""
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="forensic",
                transaction_limit=-1,
                price_cents=799700,
                stripe_checkout_session_id="sess_best_forensic",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id="sess_best_starter_f",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        # Small count - starter should be preferred over forensic
        credit = MigrationCredit.find_best_credit(test_user.id, 100)

        assert credit is not None
        assert credit.tier_type == "starter"

    def test_find_best_credit_forensic_when_only_option(
        self, app, db_session, test_user
    ):
        """Should use forensic when it is the only suitable credit."""
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="forensic",
                transaction_limit=-1,
                price_cents=799700,
                stripe_checkout_session_id="sess_best_forensic_only",
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        credit = MigrationCredit.find_best_credit(test_user.id, 600000)

        assert credit is not None
        assert credit.tier_type == "forensic"

    def test_find_best_credit_ignores_used(self, app, db_session, test_user):
        """Should not return credits that are already used."""
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id="sess_best_used",
                payment_status="paid",
                status="used",
                paid_at=datetime.now(timezone.utc),
                used_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        credit = MigrationCredit.find_best_credit(test_user.id, 100)

        assert credit is None

    def test_find_best_credit_ignores_unpaid(self, app, db_session, test_user):
        """Should not return credits that are not paid."""
        db_session.add(
            MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id="sess_best_unpaid",
                payment_status="pending",
                status="pending",
            )
        )
        db_session.commit()

        credit = MigrationCredit.find_best_credit(test_user.id, 100)

        assert credit is None

    # ------------------------------------------------------------------------
    # to_dict()
    # ------------------------------------------------------------------------

    def test_to_dict_basic(self, app, db_session, test_user):
        """to_dict should include all expected fields."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="business",
            stripe_checkout_session_id="sess_todict",
        )

        result = credit.to_dict()

        assert result["tier_type"] == "business"
        assert result["tier_name"] == "Business"
        assert result["transaction_limit"] == 25000
        assert result["price_cents"] == 99700
        assert result["status"] == "pending"
        assert result["payment_status"] == "pending"
        assert result["migration_id"] is None
        assert result["transactions_used"] == 0
        assert "created_at" in result
        assert result["paid_at"] is None
        assert result["used_at"] is None

    def test_to_dict_paid_credit(self, app, db_session, test_user):
        """to_dict of paid credit should show paid_at."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="enterprise",
            stripe_checkout_session_id="sess_todict_paid",
        )
        credit.mark_paid(payment_intent_id="pi_todict_paid")

        result = credit.to_dict()

        assert result["status"] == "available"
        assert result["payment_status"] == "paid"
        assert result["paid_at"] is not None

    def test_to_dict_used_credit(self, app, db_session, test_user):
        """to_dict of used credit should show migration_id and used_at."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_todict_used",
        )
        credit.mark_paid(payment_intent_id="pi_todict_used")
        credit.use_for_migration(migration_id="mig-dict-test", transactions_count=2500)

        result = credit.to_dict()

        assert result["status"] == "used"
        assert result["migration_id"] == "mig-dict-test"
        assert result["transactions_used"] == 2500
        assert result["used_at"] is not None

    def test_to_dict_includes_id(self, app, db_session, test_user):
        """to_dict should include the credit id."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_todict_id",
        )

        result = credit.to_dict()

        assert "id" in result
        assert result["id"] == credit.id

    def test_to_dict_all_tiers_have_names(self, app, db_session, test_user):
        """to_dict tier_name should resolve for all known tiers."""
        for i, tier in enumerate(MigrationCredit.TIER_CONFIG.keys()):
            credit = MigrationCredit.create_pending(
                user_id=test_user.id,
                tier_type=tier,
                stripe_checkout_session_id="sess_todict_tier_{}_{}".format(tier, i),
            )
            result = credit.to_dict()
            assert result["tier_name"] == MigrationCredit.TIER_CONFIG[tier]["name"]

    # ------------------------------------------------------------------------
    # Full lifecycle test
    # ------------------------------------------------------------------------

    def test_full_lifecycle_pending_to_paid_to_used(self, app, db_session, test_user):
        """Test the complete lifecycle: create -> pay -> use."""
        # Step 1: Create pending
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="professional",
            stripe_checkout_session_id="sess_lifecycle",
        )
        assert credit.status == "pending"
        assert credit.payment_status == "pending"

        # Step 2: Mark paid
        credit.mark_paid(payment_intent_id="pi_lifecycle")
        assert credit.status == "available"
        assert credit.payment_status == "paid"
        assert credit.paid_at is not None

        # Step 3: Use for migration
        result = credit.use_for_migration(
            migration_id="mig-lifecycle-123", transactions_count=50000
        )
        assert result is True
        assert credit.status == "used"
        assert credit.migration_id == "mig-lifecycle-123"
        assert credit.transactions_used == 50000
        assert credit.used_at is not None

    def test_full_lifecycle_pending_to_failed(self, app, db_session, test_user):
        """Test lifecycle when payment fails: create -> fail."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="sess_lifecycle_fail",
        )
        assert credit.status == "pending"

        credit.mark_failed()
        assert credit.status == "expired"
        assert credit.payment_status == "failed"

        # Cannot use a failed credit
        result = credit.use_for_migration(migration_id="mig-nope")
        assert result is False
