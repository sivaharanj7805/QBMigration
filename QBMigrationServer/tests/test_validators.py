"""Tests for utils/validators.py - email, password, and string validation."""

from utils.validators import sanitize_string, validate_email, validate_password


class TestValidateEmail:
    """Tests for validate_email function."""

    def test_valid_email(self):
        valid, msg = validate_email("user@example.com")
        assert valid is True
        assert msg == ""

    def test_valid_email_with_plus(self):
        valid, msg = validate_email("user+tag@example.com")
        assert valid is True

    def test_valid_email_with_dots(self):
        valid, msg = validate_email("first.last@example.com")
        assert valid is True

    def test_valid_email_with_subdomain(self):
        valid, msg = validate_email("user@sub.example.com")
        assert valid is True

    def test_empty_email(self):
        valid, msg = validate_email("")
        assert valid is False
        assert "required" in msg.lower()

    def test_email_too_long(self):
        long_email = "a" * 250 + "@b.com"
        valid, msg = validate_email(long_email)
        assert valid is False
        assert "too long" in msg.lower()

    def test_email_no_at_sign(self):
        valid, msg = validate_email("userexample.com")
        assert valid is False
        assert "@" in msg

    def test_email_double_at(self):
        valid, msg = validate_email("user@@example.com")
        assert valid is False

    def test_email_consecutive_dots_local(self):
        valid, msg = validate_email("user..name@example.com")
        assert valid is False
        assert "consecutive dots" in msg.lower()

    def test_email_leading_dot_local(self):
        valid, msg = validate_email(".user@example.com")
        assert valid is False

    def test_email_trailing_dot_local(self):
        valid, msg = validate_email("user.@example.com")
        assert valid is False

    def test_email_leading_dot_domain(self):
        valid, msg = validate_email("user@.example.com")
        assert valid is False

    def test_email_trailing_dot_domain(self):
        valid, msg = validate_email("user@example.com.")
        assert valid is False

    def test_email_consecutive_dots_domain(self):
        valid, msg = validate_email("user@example..com")
        assert valid is False

    def test_email_missing_local(self):
        valid, msg = validate_email("@example.com")
        assert valid is False

    def test_email_missing_domain(self):
        valid, msg = validate_email("user@")
        assert valid is False

    def test_email_single_char_tld(self):
        valid, msg = validate_email("user@example.c")
        assert valid is False

    def test_email_numeric_local(self):
        valid, msg = validate_email("123@example.com")
        assert valid is True

    def test_email_percent_in_local(self):
        valid, msg = validate_email("user%tag@example.com")
        assert valid is True


class TestValidatePassword:
    """Tests for validate_password function."""

    def test_valid_password(self):
        valid, msg = validate_password("StrongPass123!")
        assert valid is True
        assert msg == ""

    def test_empty_password(self):
        valid, msg = validate_password("")
        assert valid is False
        assert "required" in msg.lower()

    def test_too_short(self):
        valid, msg = validate_password("Short1!")
        assert valid is False
        assert "12 characters" in msg

    def test_too_long(self):
        valid, msg = validate_password("A" * 129 + "a1!")
        assert valid is False
        assert "128" in msg

    def test_no_uppercase(self):
        valid, msg = validate_password("nouppercase123!")
        assert valid is False
        assert "uppercase" in msg.lower()

    def test_no_lowercase(self):
        valid, msg = validate_password("NOLOWERCASE123!")
        assert valid is False
        assert "lowercase" in msg.lower()

    def test_no_digit(self):
        valid, msg = validate_password("NoDigitsHere!!!")
        assert valid is False
        assert "digit" in msg.lower()

    def test_no_special(self):
        valid, msg = validate_password("NoSpecialChar12")
        assert valid is False
        assert "special" in msg.lower()

    def test_exactly_12_chars(self):
        valid, msg = validate_password("Abcdefgh12!x")
        assert valid is True

    def test_exactly_128_chars(self):
        pwd = "A" + "a" * 124 + "1!x"
        valid, msg = validate_password(pwd)
        assert valid is True


class TestSanitizeString:
    """Tests for sanitize_string function."""

    def test_normal_string(self):
        assert sanitize_string("hello world") == "hello world"

    def test_empty_string(self):
        assert sanitize_string("") == ""

    def test_none_value(self):
        assert sanitize_string(None) == ""

    def test_null_bytes(self):
        assert sanitize_string("hello\x00world") == "helloworld"

    def test_whitespace_trim(self):
        assert sanitize_string("  hello  ") == "hello"

    def test_max_length_truncation(self):
        result = sanitize_string("a" * 300)
        assert len(result) == 255

    def test_custom_max_length(self):
        result = sanitize_string("a" * 100, max_length=50)
        assert len(result) == 50

    def test_combined_sanitization(self):
        result = sanitize_string("  \x00hello\x00  ")
        assert result == "hello"
