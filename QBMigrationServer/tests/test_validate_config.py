"""Tests for config.py validate_config function."""

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


class TestValidateConfig:
    """Tests for the validate_config() function."""

    def test_validate_config_success(self):
        from config import validate_config

        key = Fernet.generate_key().decode()
        env = {
            "SECRET_KEY": "a" * 64,
            "DATABASE_URL": "postgresql://localhost/test",
            "FLASK_ENV": "development",
            "BACKUP_ENCRYPTION_KEY": key,
        }
        with patch.dict("os.environ", env, clear=False):
            result = validate_config()
            assert result is True

    def test_validate_config_missing_secret_key(self):
        from config import validate_config

        env = {
            "DATABASE_URL": "postgresql://localhost/test",
            "FLASK_ENV": "development",
        }
        with patch.dict("os.environ", env, clear=False):
            # Remove SECRET_KEY if it exists
            with patch.dict("os.environ", {"SECRET_KEY": ""}, clear=False):
                with pytest.raises(RuntimeError, match="Missing required"):
                    validate_config()

    def test_validate_config_missing_database_url(self):
        from config import validate_config

        with patch.dict(
            "os.environ",
            {"SECRET_KEY": "a" * 32, "DATABASE_URL": "", "FLASK_ENV": "development"},
            clear=False,
        ):
            with pytest.raises(RuntimeError, match="Missing required"):
                validate_config()

    def test_validate_config_short_secret_key(self):
        from config import validate_config

        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "short",
                "DATABASE_URL": "postgresql://localhost/test",
                "FLASK_ENV": "development",
            },
            clear=False,
        ):
            with pytest.raises(RuntimeError, match="at least 64 characters"):
                validate_config()

    def test_validate_config_production_missing_vars(self):
        from config import validate_config

        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://localhost/test",
                "FLASK_ENV": "production",
            },
            clear=False,
        ):
            with pytest.raises(RuntimeError, match="Missing required"):
                validate_config()

    def test_validate_config_invalid_backup_key(self):
        from config import validate_config

        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://localhost/test",
                "FLASK_ENV": "development",
                "BACKUP_ENCRYPTION_KEY": "not-a-valid-fernet-key",
            },
            clear=False,
        ):
            with pytest.raises(RuntimeError, match="BACKUP_ENCRYPTION_KEY is invalid"):
                validate_config()

    def test_validate_config_valid_backup_key(self):
        from config import validate_config

        key = Fernet.generate_key().decode()
        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://localhost/test",
                "FLASK_ENV": "development",
                "BACKUP_ENCRYPTION_KEY": key,
            },
            clear=False,
        ):
            result = validate_config()
            assert result is True

    def test_validate_config_invalid_qbo_key(self):
        from config import validate_config

        backup_key = Fernet.generate_key().decode()
        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://localhost/test",
                "FLASK_ENV": "development",
                "BACKUP_ENCRYPTION_KEY": backup_key,
                "QBO_ENCRYPTION_KEY": "not-valid",
            },
            clear=False,
        ):
            with pytest.raises(RuntimeError, match="QBO_ENCRYPTION_KEY is invalid"):
                validate_config()
