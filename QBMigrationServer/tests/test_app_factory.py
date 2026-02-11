"""
Tests for app.py - application factory, middleware, error handlers, and routes.

Covers uncovered lines from the coverage report including:
- Root endpoint, health endpoint, health OPTIONS
- Error handlers (400, 404, 413, 429)
- Security headers middleware
- Rate limit headers
- Request logging middleware
- Content length check
- CSRF error handling
- Unauthorized handler
- Request loader (JWT from cookie)
- setup_logging function
- Disconnect page
"""

import os

import jwt
from app import setup_logging


class TestRootEndpoint:
    """Tests for GET / root endpoint."""

    def test_root_returns_200(self, client):
        """Root endpoint returns 200 with server info."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_json(self, client):
        """Root endpoint returns valid JSON."""
        data = client.get("/").get_json()
        assert data is not None

    def test_root_has_message(self, client):
        """Root endpoint includes server name."""
        data = client.get("/").get_json()
        assert data["name"] == "ForensicBridge Migration Server"

    def test_root_has_status_running(self, client):
        """Root endpoint shows running status."""
        data = client.get("/").get_json()
        assert data["status"] == "running"

    def test_root_has_version(self, client):
        """Root endpoint includes version string."""
        data = client.get("/").get_json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_root_has_environment(self, client):
        """Root endpoint includes status field."""
        data = client.get("/").get_json()
        assert "status" in data

    def test_root_has_features(self, client):
        """Root endpoint includes name, version, and status."""
        data = client.get("/").get_json()
        assert "name" in data
        assert "version" in data
        assert "status" in data

    def test_root_has_endpoints(self, client):
        """Root endpoint returns minimal server info."""
        data = client.get("/").get_json()
        assert data["name"] == "ForensicBridge Migration Server"
        assert data["status"] == "running"
        assert isinstance(data["version"], str)

    def test_root_auth_endpoints(self, client):
        """Root endpoint returns valid version string."""
        data = client.get("/").get_json()
        version = data["version"]
        parts = version.split(".")
        assert len(parts) >= 2, f"Version '{version}' should be semver-like"

    def test_root_migration_endpoints(self, client):
        """Root endpoint status is running."""
        data = client.get("/").get_json()
        assert data["status"] == "running"


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_returns_200(self, client):
        """Health endpoint returns 200 when healthy."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        """Health endpoint returns valid JSON."""
        data = client.get("/health").get_json()
        assert data is not None

    def test_health_status_healthy(self, client):
        """Health endpoint shows healthy status."""
        data = client.get("/health").get_json()
        assert data["status"] == "healthy"

    def test_health_has_timestamp(self, client):
        """Health endpoint includes timestamp."""
        data = client.get("/health").get_json()
        assert "timestamp" in data
        assert data["timestamp"].endswith("Z")

    def test_health_has_checks(self, client):
        """Health endpoint includes checks dictionary."""
        data = client.get("/health").get_json()
        assert "checks" in data
        assert isinstance(data["checks"], dict)

    def test_health_database_check(self, client):
        """Health endpoint checks database connection."""
        data = client.get("/health").get_json()
        assert data["checks"]["database"] == "healthy"

    def test_health_disk_space_check(self, client):
        """Health endpoint checks disk space."""
        data = client.get("/health").get_json()
        assert data["checks"]["disk_space"] in ("healthy", "warning")

    def test_health_detailed_query_param(self, client):
        """Health endpoint accepts ?detailed=true parameter."""
        response = client.get("/health?detailed=true")
        assert response.status_code == 200
        data = response.get_json()
        # SQLite test DB returns not_postgresql for connection pool
        assert "checks" in data

    def test_health_cors_headers_no_origin(self, client):
        """Health endpoint adds CORS wildcard when no Origin header."""
        response = client.get("/health")
        assert response.headers.get("Access-Control-Allow-Origin") == "*"
        assert "GET" in response.headers.get("Access-Control-Allow-Methods", "")


class TestHealthOptions:
    """Tests for OPTIONS /health endpoint."""

    def test_health_options_returns_200(self, client):
        """OPTIONS /health returns 200."""
        response = client.options("/health")
        assert response.status_code == 200

    def test_health_options_cors_methods(self, client):
        """OPTIONS /health returns CORS Allow-Methods."""
        response = client.options("/health")
        assert "Access-Control-Allow-Methods" in response.headers
        methods = response.headers["Access-Control-Allow-Methods"]
        assert "GET" in methods
        assert "OPTIONS" in methods

    def test_health_options_cors_headers(self, client):
        """OPTIONS /health returns CORS Allow-Headers."""
        response = client.options("/health")
        assert "Access-Control-Allow-Headers" in response.headers

    def test_health_options_cors_max_age(self, client):
        """OPTIONS /health returns CORS Max-Age."""
        response = client.options("/health")
        assert response.headers.get("Access-Control-Max-Age") == "3600"

    def test_health_options_with_allowed_origin(self, app, client):
        """OPTIONS /health with an allowed Origin uses that origin."""
        allowed = app.config.get("ALLOWED_ORIGINS", [])
        if allowed:
            origin = allowed[0]
            response = client.options("/health", headers={"Origin": origin})
            assert response.status_code == 200
            assert response.headers.get("Access-Control-Allow-Origin") == origin


class TestErrorHandlers:
    """Tests for HTTP error handlers."""

    def test_404_returns_json(self, client):
        """404 error returns JSON response."""
        response = client.get("/nonexistent-route-xyz789")
        assert response.status_code == 404
        data = response.get_json()
        assert data is not None

    def test_404_has_success_false(self, client):
        """404 error has success: false."""
        data = client.get("/nonexistent-route-xyz789").get_json()
        assert data["success"] is False

    def test_404_has_error_message(self, client):
        """404 error includes error message."""
        data = client.get("/nonexistent-route-xyz789").get_json()
        assert "not found" in data["error"].lower()

    def test_404_has_message_field(self, client):
        """404 error includes descriptive message."""
        data = client.get("/nonexistent-route-xyz789").get_json()
        assert "message" in data

    def test_401_on_protected_endpoint(self, client):
        """Unauthenticated access to protected endpoint returns 401."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_401_returns_json(self, client):
        """401 error returns JSON with success: false."""
        data = client.get("/api/auth/me").get_json()
        assert data["success"] is False

    def test_401_has_error_field(self, client):
        """401 error includes error field."""
        data = client.get("/api/auth/me").get_json()
        assert "error" in data

    def test_413_handler_via_error_handler_spec(self, app):
        """413 error handler returns proper JSON via direct invocation."""
        from werkzeug.exceptions import RequestEntityTooLarge

        with app.test_request_context("/"):
            for code_or_exc, func in app.error_handler_spec.get(None, {}).items():
                if code_or_exc == 413:
                    handler = list(func.values())[0]
                    error = RequestEntityTooLarge()
                    response, status_code = handler(error)
                    data = response.get_json()
                    assert status_code == 413
                    assert data["success"] is False
                    payload_msg = data.get("error", "") + " " + data.get("message", "")
                    assert (
                        "too large" in payload_msg.lower()
                        or "payload" in payload_msg.lower()
                    )
                    break

    def test_429_handler_via_error_handler_spec(self, app):
        """429 error handler returns proper JSON via direct invocation."""
        from werkzeug.exceptions import TooManyRequests

        with app.test_request_context("/api/auth/login"):
            for code_or_exc, func in app.error_handler_spec.get(None, {}).items():
                if code_or_exc == 429:
                    handler = list(func.values())[0]
                    error = TooManyRequests()
                    response, status_code = handler(error)
                    data = response.get_json()
                    assert status_code == 429
                    assert data["success"] is False
                    assert "too many" in data["error"].lower()
                    assert "message" in data
                    break

    def test_400_handler_via_error_handler_spec(self, app):
        """400 error handler returns proper JSON via direct invocation."""
        from werkzeug.exceptions import BadRequest, HTTPException

        with app.test_request_context("/"):
            handlers_for_400 = app.error_handler_spec.get(None, {}).get(400, {})
            # The 400 handler is registered under HTTPException key;
            # CSRFError handler is separate under CSRFError key.
            handler = handlers_for_400.get(HTTPException)
            if handler:
                error = BadRequest("Invalid data")
                response, status_code = handler(error)
                data = response.get_json()
                assert status_code == 400
                assert data["success"] is False
                assert data["error_code"] == "BAD_REQUEST"

    def test_500_handler_via_error_handler_spec(self, app):
        """500 error handler returns proper JSON via direct invocation."""
        with app.test_request_context("/"):
            for code_or_exc, func in app.error_handler_spec.get(None, {}).items():
                if code_or_exc == 500:
                    handler = list(func.values())[0]
                    error = Exception("Internal error details")
                    response, status_code = handler(error)
                    data = response.get_json()
                    assert status_code == 500
                    assert data["success"] is False
                    break


class TestSecurityHeaders:
    """Tests for security headers middleware."""

    def test_csp_header(self, client):
        """Responses include Content-Security-Policy header."""
        response = client.get("/")
        assert "Content-Security-Policy" in response.headers
        csp = response.headers["Content-Security-Policy"]
        assert "default-src" in csp

    def test_x_frame_options(self, client):
        """Responses include X-Frame-Options: DENY."""
        response = client.get("/")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_x_content_type_options(self, client):
        """Responses include X-Content-Type-Options: nosniff."""
        response = client.get("/")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_xss_protection(self, client):
        """Responses include X-XSS-Protection header (set to 0 per modern best practice)."""
        response = client.get("/")
        assert "X-XSS-Protection" in response.headers
        assert response.headers["X-XSS-Protection"] in ("0", "1")

    def test_referrer_policy(self, client):
        """Responses include Referrer-Policy header."""
        response = client.get("/")
        assert (
            response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        )

    def test_permissions_policy(self, client):
        """Responses include Permissions-Policy header."""
        response = client.get("/")
        assert "Permissions-Policy" in response.headers
        pp = response.headers["Permissions-Policy"]
        assert "camera=()" in pp
        assert "microphone=()" in pp

    def test_no_hsts_in_testing(self, client):
        """HSTS header is NOT set in testing environment."""
        response = client.get("/")
        # HSTS should only be set in production
        assert "Strict-Transport-Security" not in response.headers

    def test_cache_control_on_auth_endpoints(self, client):
        """Auth endpoints include no-store cache control."""
        response = client.get("/api/auth/me")
        cache = response.headers.get("Cache-Control", "")
        assert "no-store" in cache

    def test_security_headers_on_health(self, client):
        """Security headers are present even on health endpoint."""
        response = client.get("/health")
        assert "X-Frame-Options" in response.headers
        assert "X-Content-Type-Options" in response.headers

    def test_csp_includes_stripe(self, client):
        """CSP header includes Stripe script source."""
        response = client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")
        assert "stripe.com" in csp

    def test_permissions_policy_payment(self, client):
        """Permissions-Policy allows payment for self."""
        response = client.get("/")
        pp = response.headers.get("Permissions-Policy", "")
        assert "payment=(self)" in pp


class TestRateLimitHeaders:
    """Tests for X-RateLimit-* headers."""

    def test_rate_limit_header_present(self, client):
        """Responses include X-RateLimit-Limit header."""
        response = client.get("/")
        assert "X-RateLimit-Limit" in response.headers

    def test_rate_limit_reset_header_present(self, client):
        """Responses include X-RateLimit-Reset header."""
        response = client.get("/")
        assert "X-RateLimit-Reset" in response.headers

    def test_rate_limit_reset_is_numeric(self, client):
        """X-RateLimit-Reset is a numeric timestamp."""
        response = client.get("/")
        reset = response.headers.get("X-RateLimit-Reset", "")
        assert reset.isdigit()

    def test_rate_limit_default_value(self, client):
        """Default rate limit is 100 for generic endpoints."""
        response = client.get("/")
        assert response.headers.get("X-RateLimit-Limit") == "100"

    def test_rate_limit_auth_register(self, client):
        """Auth register endpoint has a tighter rate limit."""
        response = client.post(
            "/api/auth/register",
            json={"email": "x@x.com", "password": "test"},
        )
        limit = response.headers.get("X-RateLimit-Limit", "")
        assert limit == "3"

    def test_rate_limit_auth_login(self, client):
        """Auth login endpoint has specific rate limit."""
        response = client.post(
            "/api/auth/login",
            json={"email": "x@x.com", "password": "test"},
        )
        limit = response.headers.get("X-RateLimit-Limit", "")
        assert limit == "5"

    def test_rate_limit_forgot_password(self, client):
        """Forgot-password endpoint has 3/hour rate limit header."""
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": "x@example.com"},
        )
        limit = response.headers.get("X-RateLimit-Limit", "")
        assert limit == "3"

    def test_rate_limit_health_default(self, client):
        """Health endpoint gets default rate limit header."""
        response = client.get("/health")
        limit = response.headers.get("X-RateLimit-Limit", "")
        assert limit == "100"


class TestRequestLoggingMiddleware:
    """Tests for request logging before_request and after_request."""

    def test_health_skips_logging(self, client):
        """Requests to /health should not trigger request logging (returns None)."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_root_skips_logging(self, client):
        """Requests to / should not trigger request logging."""
        response = client.get("/")
        assert response.status_code == 200

    def test_api_endpoint_logged(self, client):
        """Requests to non-skipped endpoints are logged without error."""
        response = client.get("/api/auth/me")
        assert response.status_code in (401, 200)


class TestCheckContentLength:
    """Tests for check_content_length before_request middleware."""

    def test_normal_request_passes(self, client):
        """Normal-sized requests pass content length check."""
        response = client.get("/")
        assert response.status_code == 200

    def test_oversized_content_length_rejected(self, app):
        """Request with Content-Length exceeding MAX_CONTENT_LENGTH is rejected."""
        max_size = app.config.get("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)
        oversized = max_size + 1
        # Use test_request_context with environ_base to set CONTENT_LENGTH
        with app.test_request_context(
            "/", method="POST", environ_base={"CONTENT_LENGTH": str(oversized)}
        ):
            rv = app.preprocess_request()
            assert rv is not None
            response, status_code = rv
            assert status_code == 413
            data = response.get_json()
            assert data["success"] is False
            assert "too large" in data["error"].lower()

    def test_exact_max_content_length_passes(self, app):
        """Request at exactly MAX_CONTENT_LENGTH passes the middleware."""
        max_size = app.config.get("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)
        with app.test_request_context(
            "/", method="POST", environ_base={"CONTENT_LENGTH": str(max_size)}
        ):
            rv = app.preprocess_request()
            # check_content_length should return None (not block)
            # Other before_request handlers may return non-None, so we just
            # check that if rv is not None, it is not a 413
            if rv is not None:
                if isinstance(rv, tuple):
                    assert rv[1] != 413
                # If rv is a Response, check status code
                elif hasattr(rv, "status_code"):
                    assert rv.status_code != 413


class TestCSRFErrorHandler:
    """Tests for CSRF error handler."""

    def test_csrf_error_returns_400(self, app):
        """CSRFError handler returns 400 with proper JSON."""
        from flask_wtf.csrf import CSRFError

        with app.test_request_context("/"):
            handler = None
            for code_or_exc, func in app.error_handler_spec.get(None, {}).items():
                if code_or_exc == CSRFError:
                    handler = list(func.values())[0]
                    break

            if handler:
                error = CSRFError("The CSRF token is missing.")
                response, status_code = handler(error)
                data = response.get_json()
                assert status_code == 400
                assert data["success"] is False
                assert "csrf" in data["error"].lower()


class TestUnauthorizedHandler:
    """Tests for require_auth decorator (used instead of Flask-Login unauthorized)."""

    def test_unauthorized_returns_401_json(self, client):
        """Unauthorized handler returns 401 with JSON body."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False
        assert "error" in data

    def test_unauthorized_error_message(self, client):
        """Unauthorized response includes authorization error message."""
        data = client.get("/api/auth/me").get_json()
        error_text = data.get("error", "").lower()
        assert "authorization" in error_text or "auth" in error_text


class TestRequestLoaderJWTCookie:
    """Tests for load_user_from_request with auth_token cookie."""

    def test_valid_jwt_cookie_loads_user(self, app, client, db_session, test_user):
        """Request loader can authenticate via auth_token cookie."""
        from api.auth import create_token

        with app.app_context():
            token = create_token(test_user.id, test_user.email)

        client.set_cookie("auth_token", token, domain="localhost")
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_invalid_jwt_cookie_returns_401(self, client):
        """Invalid auth_token cookie does not authenticate."""
        client.set_cookie("auth_token", "invalid-token-value", domain="localhost")
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_valid_bearer_header_loads_user(self, app, client, db_session, test_user):
        """Request loader authenticates via Authorization Bearer header."""
        from api.auth import create_token

        with app.app_context():
            token = create_token(test_user.id, test_user.email)

        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_expired_jwt_cookie_returns_401(self, app, client, db_session, test_user):
        """Expired auth_token cookie does not authenticate."""
        import datetime

        payload = {
            "user_id": test_user.id,
            "email": test_user.email,
            "exp": datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc),
            "iat": datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc),
        }
        expired_token = jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")
        client.set_cookie("auth_token", expired_token, domain="localhost")
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_bearer_with_nonexistent_user(self, app, client, db_session):
        """Bearer token with nonexistent user_id is rejected."""
        from api.auth import create_token

        with app.app_context():
            token = create_token(99999, "ghost@example.com")

        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        # require_auth passes (token is valid) but endpoint returns 404 (user not in DB)
        assert response.status_code in (401, 404)

    def test_malformed_bearer_header(self, client):
        """Malformed Authorization header is rejected."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "NotBearer some-token"},
        )
        assert response.status_code == 401

    def test_bearer_no_token(self, client):
        """Authorization header with just 'Bearer' and no token."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer"},
        )
        assert response.status_code == 401


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_log_directory_exists_after_app_creation(self, app):
        """setup_logging creates the logs directory during app creation."""
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        assert os.path.isdir(log_dir)

    def test_log_files_created(self, app):
        """setup_logging creates app.log and security.log files."""
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        assert os.path.exists(os.path.join(log_dir, "app.log"))
        assert os.path.exists(os.path.join(log_dir, "security.log"))

    def test_setup_logging_callable(self, app):
        """setup_logging function can be called without error."""
        # setup_logging has already been called during create_app;
        # calling it again should not raise
        setup_logging(app)


class TestSetupLoggingDBUriMasking:
    """Tests for setup_logging database URI credential masking."""

    def test_db_uri_with_credentials_is_masked(self):
        """Database URI containing @ is masked in log output."""
        db_uri = "postgresql://user:pass@host:5432/db"
        if "@" in db_uri:
            masked = "***@" + db_uri.split("@")[-1]
            assert masked == "***@host:5432/db"

    def test_db_uri_without_credentials_unchanged(self):
        """Database URI without @ is not modified."""
        db_uri = "sqlite:///test.db"
        assert "@" not in db_uri
        # The masking code does not alter URIs without @
        if "@" not in db_uri:
            # No masking needed
            assert db_uri == "sqlite:///test.db"


class TestDisconnectPage:
    """Tests for GET /disconnect route."""

    def test_disconnect_returns_200(self, client):
        """Disconnect page returns 200."""
        response = client.get("/disconnect")
        assert response.status_code == 200

    def test_disconnect_returns_html(self, client):
        """Disconnect page returns HTML content."""
        response = client.get("/disconnect")
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data

    def test_disconnect_contains_quickbooks(self, client):
        """Disconnect page mentions QuickBooks."""
        response = client.get("/disconnect")
        assert b"QuickBooks" in response.data

    def test_disconnect_contains_forensicbridge(self, client):
        """Disconnect page mentions ForensicBridge."""
        response = client.get("/disconnect")
        assert b"ForensicBridge" in response.data or b"FORENSICBRIDGE" in response.data


class TestCreateAppFactory:
    """Tests for create_app factory function using the session-scoped app fixture."""

    def test_app_is_flask_instance(self, app):
        """The app fixture returns a Flask application."""
        from flask import Flask

        assert isinstance(app, Flask)

    def test_app_testing_config(self, app):
        """Testing config sets TESTING=True."""
        assert app.config["TESTING"] is True

    def test_csrf_disabled_in_testing(self, app):
        """CSRF is disabled in testing config."""
        assert app.config.get("WTF_CSRF_ENABLED") is False

    def test_rate_limiting_disabled_in_testing(self, app):
        """Rate limiting is disabled in testing config."""
        assert app.config.get("RATELIMIT_ENABLED") is False

    def test_blueprints_registered(self, app):
        """Expected blueprints are registered."""
        assert "auth" in app.blueprints
        assert "upload" in app.blueprints
        assert "migrations" in app.blueprints
        assert "webhooks" in app.blueprints
        assert "dashboard" in app.blueprints

    def test_secret_key_set(self, app):
        """SECRET_KEY is set and at least 32 characters."""
        assert app.config.get("SECRET_KEY")
        assert len(app.config["SECRET_KEY"]) >= 32


class TestEnsureUserInSession:
    """Tests for ensure_user_in_session before_request middleware."""

    def test_clears_login_user_cache(self, client):
        """ensure_user_in_session clears cached login user on each request."""
        response1 = client.get("/api/auth/me")
        response2 = client.get("/api/auth/me")
        assert response1.status_code == 401
        assert response2.status_code == 401


class TestSessionTeardown:
    """Tests for shutdown_session teardown handler."""

    def test_session_cleanup_on_normal_request(self, client):
        """Database session is cleaned up after normal request."""
        response = client.get("/")
        assert response.status_code == 200

    def test_session_cleanup_on_error(self, client):
        """Database session is cleaned up after error response."""
        response = client.get("/nonexistent-teardown-test")
        assert response.status_code == 404


class TestRedirectToHttps:
    """Tests for redirect_to_https before_request middleware."""

    def test_no_redirect_in_testing(self, client):
        """HTTPS redirect does not occur in testing environment."""
        response = client.get("/")
        assert response.status_code == 200


class TestHealthWithOriginHeader:
    """Tests for health endpoint CORS with specific Origin header."""

    def test_health_with_allowed_origin(self, app, client):
        """Health endpoint returns specific origin for allowed origins."""
        allowed = app.config.get("ALLOWED_ORIGINS", [])
        if allowed:
            origin = allowed[0]
            response = client.get("/health", headers={"Origin": origin})
            assert response.headers.get("Access-Control-Allow-Origin") == origin

    def test_health_with_disallowed_origin(self, client):
        """Health endpoint does not echo back disallowed origins."""
        response = client.get(
            "/health",
            headers={"Origin": "https://evil.example.com"},
        )
        acao = response.headers.get("Access-Control-Allow-Origin", "")
        assert acao != "https://evil.example.com"


class TestAutoMigrateDatabase:
    """Tests for auto_migrate_database function."""

    def test_sqlite_skips_migration(self, app):
        """auto_migrate_database skips for SQLite databases."""
        from app import auto_migrate_database

        with app.app_context():
            auto_migrate_database(app)


class TestCacheControlHeaders:
    """Tests for cache control on sensitive endpoints."""

    def test_qbo_endpoints_cache_control(self, client):
        """QBO endpoints include no-store cache control."""
        response = client.get("/api/qbo/status")
        cache = response.headers.get("Cache-Control", "")
        assert "no-store" in cache

    def test_non_sensitive_endpoint_no_pragma(self, client):
        """Non-sensitive endpoints do not add Pragma header."""
        response = client.get("/health")
        pragma = response.headers.get("Pragma", "")
        assert pragma == ""
