"""Tests for models/whitelabel_settings.py - WhitelabelSettings model."""

from models.whitelabel_settings import WhitelabelSettings


class TestWhitelabelValidation:
    """Tests for WhitelabelSettings.validate_config class method."""

    def test_valid_config(self):
        data = {
            "company_name": "Acme Inc",
            "primary_color": "#FF5733",
            "secondary_color": "#000000",
            "accent_color": "#FFFFFF",
            "support_email": "support@acme.com",
            "website_url": "https://acme.com",
        }
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert error is None
        assert cleaned["company_name"] == "Acme Inc"
        assert cleaned["primary_color"] == "#FF5733"

    def test_empty_config_uses_defaults(self):
        cleaned, error = WhitelabelSettings.validate_config({})
        assert error is None
        assert cleaned["company_name"] == "ForensicBridge"
        assert cleaned["primary_color"] == "#3B82F6"

    def test_invalid_hex_color(self):
        data = {"primary_color": "red"}
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert cleaned is None
        assert "hex color" in error.lower()

    def test_invalid_hex_color_short(self):
        data = {"primary_color": "#FFF"}
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert cleaned is None
        assert "hex color" in error.lower()

    def test_company_name_too_long(self):
        data = {"company_name": "A" * 256}
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert cleaned is None
        assert "255 characters" in error

    def test_logo_too_large(self):
        data = {"logo_url": "x" * 600_000}
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert cleaned is None
        assert "500KB" in error

    def test_email_too_long(self):
        data = {"support_email": "a" * 256}
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert cleaned is None
        assert "255 characters" in error

    def test_url_too_long(self):
        data = {"website_url": "https://" + "a" * 500}
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert cleaned is None
        assert "500 characters" in error

    def test_multiple_errors(self):
        data = {
            "company_name": "A" * 256,
            "primary_color": "invalid",
        }
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert cleaned is None
        assert ";" in error  # Multiple errors joined by semicolons

    def test_valid_colors_all_types(self):
        data = {
            "primary_color": "#3B82F6",
            "secondary_color": "#0F172A",
            "accent_color": "#B8860B",
        }
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert error is None

    def test_support_phone_truncated(self):
        data = {"support_phone": "1" * 100}
        cleaned, error = WhitelabelSettings.validate_config(data)
        assert error is None
        assert len(cleaned["support_phone"]) == 50


class TestWhitelabelToDict:
    """Tests for WhitelabelSettings.to_dict method."""

    def test_to_dict_defaults(self):
        settings = WhitelabelSettings()
        d = settings.to_dict()
        assert d["company_name"] == ""  # None gets default to ""
        assert d["primary_color"] == "#3B82F6"
        assert d["secondary_color"] == "#0F172A"
        assert d["accent_color"] == "#B8860B"

    def test_to_dict_with_values(self):
        settings = WhitelabelSettings(
            company_name="Test Co",
            support_email="test@test.com",
        )
        d = settings.to_dict()
        assert d["company_name"] == "Test Co"
        assert d["support_email"] == "test@test.com"
