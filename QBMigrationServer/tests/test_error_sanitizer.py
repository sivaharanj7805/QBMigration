"""Tests for utils/error_sanitizer.py - error message sanitization."""

import os

from utils.error_sanitizer import (
    APIError,
    create_error_response,
    get_generic_error_message,
    get_qbo_user_message,
    is_production,
    log_error_safely,
    sanitize_error_message,
    sanitize_qbo_error,
    sanitize_qbo_error_for_url,
)


class TestAPIError:
    """Tests for APIError class."""

    def test_bad_request(self):
        response, status = APIError.bad_request("Invalid input")
        assert status == 400
        assert response["success"] is False
        assert response["error"] == "Invalid input"
        assert response["error_code"] == "BAD_REQUEST"

    def test_bad_request_with_field(self):
        response, status = APIError.bad_request("Required", field="email")
        assert response["field"] == "email"

    def test_bad_request_with_details(self):
        response, status = APIError.bad_request("Invalid", details={"min": 1})
        assert response["details"] == {"min": 1}

    def test_unauthorized(self):
        response, status = APIError.unauthorized()
        assert status == 401
        assert "Authentication required" in response["error"]

    def test_unauthorized_custom_message(self):
        response, status = APIError.unauthorized("Token expired")
        assert response["error"] == "Token expired"

    def test_forbidden(self):
        response, status = APIError.forbidden()
        assert status == 403
        assert "denied" in response["error"].lower()

    def test_not_found(self):
        response, status = APIError.not_found()
        assert status == 404
        assert response["error_code"] == "NOT_FOUND"

    def test_not_found_custom(self):
        response, status = APIError.not_found("User not found")
        assert response["error"] == "User not found"

    def test_conflict(self):
        response, status = APIError.conflict("Already exists")
        assert status == 409
        assert response["error_code"] == "CONFLICT"

    def test_validation_error(self):
        response, status = APIError.validation_error("Invalid format", field="date")
        assert status == 422
        assert response["error_code"] == "VALIDATION_ERROR"
        assert response["field"] == "date"

    def test_rate_limited(self):
        response, status = APIError.rate_limited()
        assert status == 429
        assert "rate limit" in response["error"].lower()

    def test_rate_limited_with_retry(self):
        response, status = APIError.rate_limited(retry_after=60)
        assert response["details"]["retry_after_seconds"] == 60

    def test_internal_error(self):
        response, status = APIError.internal_error()
        assert status == 500
        assert response["error_code"] == "INTERNAL_ERROR"

    def test_internal_error_with_exception(self):
        exc = ValueError("test error")
        response, status = APIError.internal_error(exception=exc)
        assert status == 500

    def test_service_unavailable(self):
        response, status = APIError.service_unavailable()
        assert status == 503
        assert response["error_code"] == "SERVICE_UNAVAILABLE"

    def test_response_base(self):
        response, status = APIError.response("Test", 418, "TEAPOT")
        assert status == 418
        assert response["error_code"] == "TEAPOT"

    def test_response_no_optional_fields(self):
        response, status = APIError.response("Error", 400)
        assert "error_code" not in response
        assert "field" not in response
        assert "details" not in response


class TestIsProduction:
    """Tests for is_production function."""

    def test_testing_env(self):
        os.environ["FLASK_ENV"] = "testing"
        os.environ["FLASK_DEBUG"] = "0"
        assert is_production() is False

    def test_development_env(self):
        os.environ["FLASK_ENV"] = "development"
        assert is_production() is False

    def test_debug_mode(self):
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_DEBUG"] = "1"
        assert is_production() is False

    def test_production_env(self):
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_DEBUG"] = "0"
        assert is_production() is True

    def teardown_method(self):
        os.environ["FLASK_ENV"] = "testing"
        os.environ["FLASK_DEBUG"] = "0"


class TestSanitizeErrorMessage:
    """Tests for sanitize_error_message function."""

    def test_development_shows_full_error(self):
        os.environ["FLASK_ENV"] = "testing"
        error = ValueError("detailed error info")
        result = sanitize_error_message(error)
        assert "detailed error info" in result

    def test_production_sanitizes_value_error(self):
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_DEBUG"] = "0"
        error = ValueError("Invalid email format")
        result = sanitize_error_message(error)
        assert result == "Invalid input value"
        os.environ["FLASK_ENV"] = "testing"

    def test_production_sanitizes_key_error(self):
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_DEBUG"] = "0"
        error = KeyError("secret_field")
        result = sanitize_error_message(error)
        assert result == "Missing required field"
        os.environ["FLASK_ENV"] = "testing"

    def teardown_method(self):
        os.environ["FLASK_ENV"] = "testing"
        os.environ["FLASK_DEBUG"] = "0"


class TestGetGenericErrorMessage:
    """Tests for get_generic_error_message function."""

    def test_upload_context(self):
        msg = get_generic_error_message("upload")
        assert "upload" in msg.lower() or "file" in msg.lower()

    def test_auth_context(self):
        msg = get_generic_error_message("auth")
        assert "authentication" in msg.lower() or "credentials" in msg.lower()

    def test_migration_context(self):
        msg = get_generic_error_message("migration")
        assert "migration" in msg.lower()

    def test_payment_context(self):
        msg = get_generic_error_message("payment")
        assert "payment" in msg.lower()

    def test_unknown_context(self):
        msg = get_generic_error_message("unknown_thing")
        assert "error occurred" in msg.lower()

    def test_none_context(self):
        msg = get_generic_error_message(None)
        assert "error occurred" in msg.lower()


class TestCreateErrorResponse:
    """Tests for create_error_response function."""

    def test_basic_response(self):
        error = ValueError("test")
        response = create_error_response(error, "auth", 400)
        assert response["success"] is False
        assert response["error_code"] == "VALIDATION_ERROR"

    def test_500_response(self):
        error = Exception("test")
        response = create_error_response(error, status_code=500)
        assert response["error_code"] == "INTERNAL_ERROR"

    def test_dev_includes_debug(self):
        os.environ["FLASK_ENV"] = "testing"
        error = ValueError("test debug")
        response = create_error_response(error, status_code=400)
        assert "debug" in response
        assert response["debug"]["exception_type"] == "ValueError"


class TestLogErrorSafely:
    """Tests for log_error_safely function."""

    def test_logs_without_error(self):
        # Should not raise
        error = ValueError("test error")
        log_error_safely(error, "auth", user_id=123)

    def test_logs_without_user(self):
        error = ValueError("test error")
        log_error_safely(error, "migration")


class TestSanitizeQboError:
    """Tests for QBO error sanitization functions."""

    def test_known_error(self):
        result = sanitize_qbo_error("access_denied")
        assert result["code"] == "access_denied"
        assert "denied" in result["message"].lower()

    def test_unknown_error(self):
        result = sanitize_qbo_error("secret_internal_error")
        assert result["code"] == "connection_error"
        assert "try again" in result["message"].lower()

    def test_empty_error(self):
        result = sanitize_qbo_error("")
        assert result["code"] == "unknown_error"

    def test_none_error(self):
        result = sanitize_qbo_error(None)
        assert result["code"] == "unknown_error"

    def test_xss_in_error_code(self):
        result = sanitize_qbo_error("<script>alert(1)</script>")
        assert "<script>" not in result["code"]

    def test_sanitize_for_url(self):
        result = sanitize_qbo_error_for_url("access_denied")
        assert result == "access_denied"

    def test_sanitize_for_url_xss(self):
        result = sanitize_qbo_error_for_url("error<script>")
        assert "<" not in result

    def test_sanitize_for_url_empty(self):
        assert sanitize_qbo_error_for_url("") == "unknown"
        assert sanitize_qbo_error_for_url(None) == "unknown"

    def test_get_qbo_user_message_known(self):
        msg = get_qbo_user_message("invalid_grant")
        assert "expired" in msg.lower() or "reconnect" in msg.lower()

    def test_get_qbo_user_message_unknown(self):
        msg = get_qbo_user_message("xyz_internal")
        assert "try again" in msg.lower()
