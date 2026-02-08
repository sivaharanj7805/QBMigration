"""Tests for utils/pii_redaction.py - PII redaction utilities."""

from utils.pii_redaction import (
    _MAX_PII_INPUT_LENGTH,
    create_safe_log_message,
    hash_email,
    hash_ip,
    redact_all_pii,
    redact_credit_card,
    redact_email,
    redact_phone,
    redact_ssn,
)


class TestHashEmail:
    """Tests for hash_email function."""

    def test_basic_hash(self):
        result = hash_email("user@example.com")
        assert result.startswith("usr_")
        assert len(result) == 36  # "usr_" + 32 hex chars

    def test_case_insensitive(self):
        h1 = hash_email("User@Example.com")
        h2 = hash_email("user@example.com")
        assert h1 == h2

    def test_consistent(self):
        h1 = hash_email("test@test.com")
        h2 = hash_email("test@test.com")
        assert h1 == h2

    def test_empty_email(self):
        assert hash_email("") == "unknown"

    def test_none_email(self):
        assert hash_email(None) == "unknown"

    def test_different_emails_different_hashes(self):
        h1 = hash_email("user1@example.com")
        h2 = hash_email("user2@example.com")
        assert h1 != h2


class TestRedactEmail:
    """Tests for redact_email function."""

    def test_basic_redaction(self):
        result = redact_email("Contact user@example.com please")
        assert "user@example.com" not in result
        assert "@example.com" in result
        assert "use***" in result

    def test_short_username(self):
        result = redact_email("Contact ab@example.com")
        assert "***@example.com" in result

    def test_no_email(self):
        text = "No email here"
        assert redact_email(text) == text

    def test_multiple_emails(self):
        text = "From alice@test.com to bob@test.com"
        result = redact_email(text)
        assert "alice@test.com" not in result
        assert "bob@test.com" not in result


class TestHashIp:
    """Tests for hash_ip function."""

    def test_basic_hash(self):
        result = hash_ip("192.168.1.1")
        assert result.startswith("ip_")
        assert len(result) == 19  # "ip_" + 16 hex chars

    def test_empty_ip(self):
        assert hash_ip("") == "unknown"

    def test_none_ip(self):
        assert hash_ip(None) == "unknown"

    def test_consistent(self):
        h1 = hash_ip("10.0.0.1")
        h2 = hash_ip("10.0.0.1")
        assert h1 == h2


class TestRedactPhone:
    """Tests for redact_phone function."""

    def test_us_format_with_dashes(self):
        result = redact_phone("Call 555-123-4567")
        assert "555-123-4567" not in result
        assert "XXX-XXX-XXXX" in result

    def test_us_format_with_parens(self):
        result = redact_phone("Call (555) 123-4567")
        assert "(555) 123-4567" not in result

    def test_international_format(self):
        result = redact_phone("Call +1-555-123-4567")
        assert "+1-555-123-4567" not in result

    def test_preserves_dates(self):
        text = "Date: 2024-01-15"
        result = redact_phone(text)
        assert "2024-01-15" in result

    def test_preserves_ip(self):
        text = "IP: 192.168.1.1"
        result = redact_phone(text)
        assert "192.168.1.1" in result

    def test_preserves_version(self):
        text = "Version 1.2.3.4"
        result = redact_phone(text)
        assert "1.2.3.4" in result


class TestRedactSsn:
    """Tests for redact_ssn function."""

    def test_basic_ssn(self):
        result = redact_ssn("SSN: 123-45-6789")
        assert "123-45" not in result
        assert "6789" in result
        assert "XXX-XX-" in result

    def test_ssn_no_dashes(self):
        result = redact_ssn("SSN: 123456789")
        assert "XXX-XX-6789" in result

    def test_no_ssn(self):
        text = "No SSN here"
        assert redact_ssn(text) == text


class TestRedactCreditCard:
    """Tests for redact_credit_card function."""

    def test_basic_card(self):
        result = redact_credit_card("Card: 4532-1234-5678-9010")
        assert "4532-1234-5678" not in result
        assert "9010" in result
        assert "XXXX-XXXX-XXXX-" in result

    def test_card_no_dashes(self):
        result = redact_credit_card("Card: 4532123456789010")
        assert "XXXX-XXXX-XXXX-9010" in result

    def test_card_with_spaces(self):
        result = redact_credit_card("Card: 4532 1234 5678 9010")
        assert "4532 1234 5678" not in result


class TestRedactAllPii:
    """Tests for redact_all_pii function."""

    def test_combined_pii(self):
        text = "User user@example.com SSN 123-45-6789"
        result = redact_all_pii(text)
        assert "user@example.com" not in result
        assert "123-45" not in result

    def test_empty_text(self):
        assert redact_all_pii("") == ""
        assert redact_all_pii(None) is None

    def test_preserve_email_hash(self):
        text = "User user@example.com logged in"
        result = redact_all_pii(text, preserve_email_hash=True)
        assert "usr_" in result
        assert "user@example.com" not in result

    def test_redos_protection(self):
        long_text = "a" * (_MAX_PII_INPUT_LENGTH + 100)
        result = redact_all_pii(long_text)
        assert "[TRUNCATED]" in result

    def test_normal_text_unchanged(self):
        text = "Normal log message with no PII"
        result = redact_all_pii(text)
        assert result == text


class TestCreateSafeLogMessage:
    """Tests for create_safe_log_message function."""

    def test_with_user_email(self):
        result = create_safe_log_message("Login failed", "user@example.com")
        assert result.startswith("[usr_")
        assert "Login failed" in result
        assert "user@example.com" not in result

    def test_without_user_email(self):
        result = create_safe_log_message("Error occurred")
        assert "[usr_" not in result
        assert "Error occurred" in result

    def test_pii_in_message_redacted(self):
        result = create_safe_log_message("Error for admin@company.com")
        assert "admin@company.com" not in result
