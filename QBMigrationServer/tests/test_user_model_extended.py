"""Extended tests for models/user.py - password validation, lockout, devices, migration usage."""

import json
from datetime import datetime, timedelta, timezone

import pytest


class TestPasswordValidation:
    """Tests for _validate_password_strength."""

    def test_password_too_short(self, db_session, test_user):
        with pytest.raises(ValueError, match="at least 12 characters"):
            test_user.set_password("Short1!aa")

    def test_password_no_uppercase(self, db_session, test_user):
        with pytest.raises(ValueError, match="uppercase letter"):
            test_user.set_password("alllowercase1234!")

    def test_password_no_lowercase(self, db_session, test_user):
        with pytest.raises(ValueError, match="lowercase letter"):
            test_user.set_password("ALLUPPERCASE1234!")

    def test_password_no_digit(self, db_session, test_user):
        with pytest.raises(ValueError, match="digit"):
            test_user.set_password("NoDigitsHereee!")

    def test_password_no_special(self, db_session, test_user):
        with pytest.raises(ValueError, match="special character"):
            test_user.set_password("NoSpecialChar123")

    def test_valid_password_accepted(self, db_session, test_user):
        # Should not raise
        test_user.set_password("ValidPassword123!")
        assert test_user.password_hash is not None


class TestAccountLockout:
    """Tests for account lockout functionality."""

    def test_is_locked_default(self, db_session, test_user):
        assert test_user.is_locked() is False

    def test_is_locked_active_lock(self, db_session, test_user):
        test_user.account_locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        db_session.commit()
        assert test_user.is_locked() is True

    def test_is_locked_expired_lock(self, db_session, test_user):
        test_user.account_locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()
        assert test_user.is_locked() is False
        # M-01 FIX: is_locked() is a pure query - no side effects
        # Lock fields are NOT automatically cleared; use clear_expired_lock() for that
        assert test_user.account_locked_until is not None

    def test_is_locked_naive_datetime(self, db_session, test_user):
        # Test with naive datetime (no tzinfo)
        test_user.account_locked_until = datetime.utcnow() + timedelta(minutes=15)
        db_session.commit()
        assert test_user.is_locked() is True

    def test_record_failed_login_increments(self, db_session, test_user):
        test_user.record_failed_login()
        assert test_user.failed_login_attempts == 1
        assert test_user.last_failed_login is not None

    def test_record_failed_login_locks_at_5(self, db_session, test_user):
        for _ in range(5):
            test_user.record_failed_login()
        assert test_user.failed_login_attempts == 5
        assert test_user.account_locked_until is not None

    def test_record_successful_login_resets(self, db_session, test_user):
        test_user.failed_login_attempts = 3
        test_user.last_failed_login = datetime.now(timezone.utc)
        db_session.commit()
        test_user.record_successful_login(ip_address="192.168.1.1")
        assert test_user.failed_login_attempts == 0
        assert test_user.last_failed_login is None
        assert test_user.account_locked_until is None
        assert test_user.last_login_at is not None
        assert test_user.last_login_ip == "192.168.1.1"

    def test_record_successful_login_no_ip(self, db_session, test_user):
        test_user.record_successful_login()
        assert test_user.failed_login_attempts == 0
        assert test_user.last_login_at is not None


class TestTrustedDevices:
    """Tests for device fingerprinting."""

    def test_is_trusted_device_empty(self, db_session, test_user):
        assert test_user.is_trusted_device("fp-123") is False

    def test_add_and_check_trusted_device(self, db_session, test_user):
        test_user.add_trusted_device("fingerprint-abc")
        assert test_user.is_trusted_device("fingerprint-abc") is True

    def test_is_trusted_device_not_found(self, db_session, test_user):
        test_user.add_trusted_device("fp-other")
        assert test_user.is_trusted_device("fp-missing") is False

    def test_add_trusted_device_max_5(self, db_session, test_user):
        for i in range(7):
            test_user.add_trusted_device(f"fp-{i}")
        devices = json.loads(test_user.trusted_devices)
        assert len(devices) == 5
        # Should keep the last 5
        assert "fp-2" in devices
        assert "fp-6" in devices

    def test_add_trusted_device_no_duplicate(self, db_session, test_user):
        test_user.add_trusted_device("fp-same")
        test_user.add_trusted_device("fp-same")
        devices = json.loads(test_user.trusted_devices)
        assert devices.count("fp-same") == 1

    def test_is_trusted_device_invalid_json(self, db_session, test_user):
        test_user.trusted_devices = "not-json"
        db_session.commit()
        assert test_user.is_trusted_device("fp-123") is False


class TestMigrationUsage:
    """Tests for subscription migration tracking."""

    def test_get_migrations_remaining_zero(self, db_session, test_user):
        assert test_user.get_migrations_remaining() == 0

    def test_get_migrations_remaining_with_purchases(self, db_session, test_user):
        test_user.migrations_purchased = 10
        test_user.migrations_used = 3
        db_session.commit()
        assert test_user.get_migrations_remaining() == 7

    def test_has_migrations_remaining_false(self, db_session, test_user):
        assert test_user.has_migrations_remaining() is False

    def test_has_migrations_remaining_true(self, db_session, test_user):
        test_user.migrations_purchased = 5
        test_user.migrations_used = 0
        db_session.commit()
        assert test_user.has_migrations_remaining() is True

    def test_use_migration_success(self, db_session, test_user):
        test_user.migrations_purchased = 5
        test_user.migrations_used = 0
        db_session.commit()
        result = test_user.use_migration()
        assert result is True
        assert test_user.migrations_used == 1

    def test_use_migration_none_remaining(self, db_session, test_user):
        result = test_user.use_migration()
        assert result is False

    def test_add_migrations(self, db_session, test_user):
        test_user.add_migrations(10)
        assert test_user.migrations_purchased == 10

    def test_add_migrations_with_tier(self, db_session, test_user):
        test_user.add_migrations(5, tier="professional")
        assert test_user.migrations_purchased == 5
        assert test_user.subscription_tier == "professional"
        assert test_user.tier_purchased_at is not None

    def test_add_migrations_cumulative(self, db_session, test_user):
        test_user.add_migrations(5)
        test_user.add_migrations(3)
        assert test_user.migrations_purchased == 8


class TestPasswordReuse:
    """Tests for password reuse detection."""

    def test_check_password_reuse_no_history(self, db_session, test_user):
        result = test_user.check_password_reuse("SomeNewPassword123!")
        assert result is False

    def test_check_password_reuse_found(self, db_session, test_user):
        # Set a password, which adds to history
        test_user.set_password("OldPassword123!!")
        db_session.commit()
        # Now check if the old password is in history
        result = test_user.check_password_reuse("OldPassword123!!")
        assert result is True

    def test_check_password_reuse_invalid_json(self, db_session, test_user):
        test_user.password_history = "not-valid-json"
        db_session.commit()
        result = test_user.check_password_reuse("Anything123!")
        assert result is False

    def test_check_password_reuse_non_list(self, db_session, test_user):
        test_user.password_history = json.dumps({"not": "a list"})
        db_session.commit()
        result = test_user.check_password_reuse("Anything123!")
        assert result is False

    def test_check_password_no_hash(self, db_session, test_user):
        test_user.password_hash = None
        assert test_user.check_password("anything") is False
