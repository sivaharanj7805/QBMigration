"""
Tests for User model QBO token encryption, MFA, and legacy migration methods.

Targets coverage gaps in models/user.py:
- _get_encryption_key, set_qbo_tokens, get_qbo_access_token, get_qbo_refresh_token
- clear_qbo_tokens
- _get_mfa_secret, _set_mfa_secret, _get_backup_codes, _set_backup_codes
- enable_2fa, disable_2fa, verify_2fa_token
- migrate_legacy_mfa_data, migrate_all_legacy_mfa
- get_tier_info
- get_id, is_authenticated, is_anonymous
"""

import json
import os
import sys

import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.user import User  # noqa: E402


class TestQBOTokenEncryption:
    """Tests for QBO token encrypt/decrypt."""

    def test_set_and_get_qbo_access_token(self, app, db_session, test_user):
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user.set_qbo_tokens("access123", "refresh456", "realm789", None)
        db_session.commit()
        assert test_user.qbo_access_token is not None
        assert test_user.qbo_access_token != "access123"
        decrypted = test_user.get_qbo_access_token()
        assert decrypted == "access123"

    def test_set_and_get_qbo_refresh_token(self, app, db_session, test_user):
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user.set_qbo_tokens("acc", "refresh_secret", "realm", None)
        db_session.commit()
        decrypted = test_user.get_qbo_refresh_token()
        assert decrypted == "refresh_secret"

    def test_get_qbo_access_token_none(self, app, db_session, test_user):
        assert test_user.get_qbo_access_token() is None

    def test_get_qbo_refresh_token_none(self, app, db_session, test_user):
        assert test_user.get_qbo_refresh_token() is None

    def test_clear_qbo_tokens(self, app, db_session, test_user):
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user.set_qbo_tokens("acc", "ref", "realm", None)
        db_session.commit()
        test_user.clear_qbo_tokens()
        db_session.commit()
        assert test_user.qbo_access_token is None
        assert test_user.qbo_refresh_token is None
        assert test_user.qbo_realm_id is None

    def test_get_encryption_key_prefers_qbo_key(self, app, db_session, test_user):
        qbo_key = Fernet.generate_key().decode()
        backup_key = Fernet.generate_key().decode()
        app.config["QBO_ENCRYPTION_KEY"] = qbo_key
        app.config["BACKUP_ENCRYPTION_KEY"] = backup_key
        test_user.set_qbo_tokens("acc", "ref", "realm", None)
        db_session.commit()
        # Should use QBO key to decrypt
        f = Fernet(qbo_key.encode())
        decrypted = f.decrypt(test_user.qbo_access_token.encode()).decode()
        assert decrypted == "acc"
        # Cleanup
        app.config.pop("QBO_ENCRYPTION_KEY", None)

    def test_get_encryption_key_no_key_raises(self, app, db_session, test_user):
        orig_backup = app.config.get("BACKUP_ENCRYPTION_KEY")
        orig_qbo = app.config.get("QBO_ENCRYPTION_KEY")
        app.config["BACKUP_ENCRYPTION_KEY"] = None
        app.config["QBO_ENCRYPTION_KEY"] = None
        try:
            with pytest.raises(ValueError, match="not configured"):
                test_user.set_qbo_tokens("acc", "ref", "realm", None)
        finally:
            if orig_backup:
                app.config["BACKUP_ENCRYPTION_KEY"] = orig_backup
            if orig_qbo:
                app.config["QBO_ENCRYPTION_KEY"] = orig_qbo

    def test_decrypt_with_wrong_key_returns_none(self, app, db_session, test_user):
        key1 = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key1
        test_user.set_qbo_tokens("secret_acc", "secret_ref", "realm", None)
        db_session.commit()
        # Change key
        key2 = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key2
        assert test_user.get_qbo_access_token() is None
        assert test_user.get_qbo_refresh_token() is None


class TestMFAMethods:
    """Tests for MFA enable/disable/verify."""

    def test_enable_2fa(self, app, db_session, test_user):
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        secret, qr_url, backup_codes = test_user.enable_2fa()
        db_session.commit()
        assert secret is not None
        assert len(secret) > 0
        assert "otpauth://" in qr_url
        assert len(backup_codes) == 10
        assert test_user.mfa_enabled is True

    def test_disable_2fa(self, app, db_session, test_user):
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user.enable_2fa()
        db_session.commit()
        test_user.disable_2fa()
        db_session.commit()
        assert test_user.mfa_enabled is False

    def test_verify_2fa_with_backup_code(self, app, db_session, test_user):
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        _, _, backup_codes = test_user.enable_2fa()
        db_session.commit()
        # Verify with a backup code
        result = test_user.verify_2fa_token(backup_codes[0])
        assert result is True

    def test_verify_2fa_invalid_token(self, app, db_session, test_user):
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user.enable_2fa()
        db_session.commit()
        result = test_user.verify_2fa_token("000000")
        assert result is False

    def test_set_mfa_secret_none(self, app, db_session, test_user):
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user._set_mfa_secret(None)
        assert test_user._mfa_secret_encrypted is None

    def test_set_backup_codes_none(self, app, db_session, test_user):
        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user._set_backup_codes(None)
        assert test_user._backup_codes_encrypted is None

    def test_get_mfa_secret_legacy_fallback(self, app, db_session, test_user):
        """Test legacy fallback when encrypted column is empty - now write-blocked."""
        # Legacy columns are now write-blocked, so we can't test the fallback anymore
        # Instead, test that encrypted MFA works correctly
        test_user._set_mfa_secret("new_secret")
        db_session.commit()
        result = test_user._get_mfa_secret()
        assert result == "new_secret"

    def test_get_backup_codes_legacy_fallback(self, app, db_session, test_user):
        """Test legacy fallback when encrypted column is empty - now write-blocked."""
        # Legacy columns are now write-blocked, so we can't test the fallback anymore
        # Instead, test that encrypted backup codes work correctly
        test_user._set_backup_codes(["CODE1", "CODE2"])
        db_session.commit()
        result = test_user._get_backup_codes()
        assert result == ["CODE1", "CODE2"]

    def test_get_backup_codes_bad_json_fallback(self, app, db_session, test_user):
        """Test bad encrypted data returns None."""
        # Set invalid encrypted data directly
        test_user._backup_codes_encrypted = "not valid encrypted data"
        db_session.commit()
        result = test_user._get_backup_codes()
        assert result is None

    def test_set_mfa_secret_no_key_raises(self, app, db_session, test_user):
        orig_backup = app.config.get("BACKUP_ENCRYPTION_KEY")
        orig_qbo = app.config.get("QBO_ENCRYPTION_KEY")
        orig_mfa = app.config.get("MFA_ENCRYPTION_KEY")
        app.config["BACKUP_ENCRYPTION_KEY"] = None
        app.config["QBO_ENCRYPTION_KEY"] = None
        app.config["MFA_ENCRYPTION_KEY"] = None
        try:
            # The error message changed slightly - match the actual message
            with pytest.raises(ValueError, match="MFA_ENCRYPTION_KEY not configured"):
                test_user._set_mfa_secret("test_secret")
        finally:
            if orig_backup:
                app.config["BACKUP_ENCRYPTION_KEY"] = orig_backup
            if orig_qbo:
                app.config["QBO_ENCRYPTION_KEY"] = orig_qbo
            if orig_mfa:
                app.config["MFA_ENCRYPTION_KEY"] = orig_mfa

    def test_set_backup_codes_no_key_raises(self, app, db_session, test_user):
        orig_backup = app.config.get("BACKUP_ENCRYPTION_KEY")
        orig_qbo = app.config.get("QBO_ENCRYPTION_KEY")
        orig_mfa = app.config.get("MFA_ENCRYPTION_KEY")
        app.config["BACKUP_ENCRYPTION_KEY"] = None
        app.config["QBO_ENCRYPTION_KEY"] = None
        app.config["MFA_ENCRYPTION_KEY"] = None
        try:
            with pytest.raises(ValueError, match="Encryption key not configured"):
                test_user._set_backup_codes(["CODE1"])
        finally:
            if orig_backup:
                app.config["BACKUP_ENCRYPTION_KEY"] = orig_backup
            if orig_qbo:
                app.config["QBO_ENCRYPTION_KEY"] = orig_qbo
            if orig_mfa:
                app.config["MFA_ENCRYPTION_KEY"] = orig_mfa


class TestLegacyMFAMigration:
    """Tests for migrate_legacy_mfa_data and migrate_all_legacy_mfa."""

    def test_migrate_legacy_mfa_data_with_secret(self, app, db_session, test_user):
        """Legacy MFA migration is no longer needed - columns are write-blocked."""
        # Since legacy columns are write-blocked, migration is not needed
        # Test that encrypted MFA works correctly instead
        key = Fernet.generate_key().decode()
        app.config["MFA_ENCRYPTION_KEY"] = key
        test_user._set_mfa_secret("new_totp_secret")
        test_user._set_backup_codes(["A1", "B2", "C3"])
        db_session.commit()
        # Migration returns False when no legacy data exists
        result = test_user.migrate_legacy_mfa_data()
        assert result is False
        # But the encrypted data works
        assert test_user._get_mfa_secret() == "new_totp_secret"
        assert test_user._get_backup_codes() == ["A1", "B2", "C3"]

    def test_migrate_legacy_mfa_data_no_legacy(self, app, db_session, test_user):
        test_user.mfa_secret = None
        test_user._mfa_secret_encrypted = None
        test_user.backup_codes = None
        test_user._backup_codes_encrypted = None
        db_session.commit()
        result = test_user.migrate_legacy_mfa_data()
        assert result is False

    def test_migrate_all_legacy_mfa(self, app, db_session, test_user):
        """Legacy MFA migration is no longer needed - columns are write-blocked."""
        # Since legacy columns are write-blocked, there's no legacy data to migrate
        # Migration returns 0 when no legacy data exists
        key = Fernet.generate_key().decode()
        app.config["MFA_ENCRYPTION_KEY"] = key
        count = User.migrate_all_legacy_mfa()
        assert count == 0

    def test_migrate_legacy_bad_backup_codes(self, app, db_session, test_user):
        """Legacy MFA migration is no longer needed - columns are write-blocked."""
        # Since legacy columns are write-blocked, there's no legacy data to migrate
        key = Fernet.generate_key().decode()
        app.config["MFA_ENCRYPTION_KEY"] = key
        result = test_user.migrate_legacy_mfa_data()
        # Returns False when no legacy data exists
        assert result is False


class TestSubscriptionInfo:
    """Tests for get_tier_info."""

    def test_get_tier_info_no_tier(self, app, db_session, test_user):
        info = test_user.get_tier_info()
        assert "tier" in info
        assert "migrations_purchased" in info
        assert "migrations_used" in info
        assert "migrations_remaining" in info

    def test_get_tier_info_with_tier(self, app, db_session, test_user):
        test_user.subscription_tier = "professional"
        db_session.commit()
        info = test_user.get_tier_info()
        assert info["tier"] == "professional"

    def test_get_tier_info_with_credits(self, app, db_session, test_user):
        from models.migration_credit import MigrationCredit

        credit = MigrationCredit(
            user_id=test_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            status="available",
            payment_status="paid",
            stripe_checkout_session_id="test_sub_sess",
        )
        db_session.add(credit)
        db_session.commit()
        info = test_user.get_tier_info()
        assert info["migrations_remaining"] >= 1


class TestFlaskLoginMethods:
    """Tests for Flask-Login interface."""

    def test_get_id(self, app, db_session, test_user):
        assert test_user.get_id() == str(test_user.id)

    def test_is_authenticated(self, app, db_session, test_user):
        assert test_user.is_authenticated is True

    def test_is_anonymous(self, app, db_session, test_user):
        assert test_user.is_anonymous is False
