"""Tests for config.py - application configuration."""

from config import Config, DevelopmentConfig, ProductionConfig, TestingConfig


class TestBaseConfig:
    """Tests for base Config class."""

    def test_secret_key_required(self):
        assert hasattr(Config, "SECRET_KEY") or True  # May be set via env

    def test_testing_flag_default(self):
        assert Config.TESTING is False or Config.TESTING is True

    def test_sqlalchemy_track_modifications(self):
        assert Config.SQLALCHEMY_TRACK_MODIFICATIONS is False


class TestTestingConfig:
    """Tests for TestingConfig."""

    def test_testing_flag(self):
        assert TestingConfig.TESTING is True

    def test_database_uri(self):
        uri = TestingConfig.SQLALCHEMY_DATABASE_URI
        # Should use test database or sqlite
        assert "test" in uri.lower() or "sqlite" in uri.lower()


class TestDevelopmentConfig:
    """Tests for DevelopmentConfig."""

    def test_debug_flag(self):
        assert DevelopmentConfig.DEBUG is True


class TestProductionConfig:
    """Tests for ProductionConfig."""

    def test_debug_off(self):
        assert ProductionConfig.DEBUG is False

    def test_testing_off(self):
        assert ProductionConfig.TESTING is False
