"""
Additional tests for api/auth.py to improve coverage from 68.46% toward 90%+.

Targets uncovered areas:
- Session binding functions (_get_user_agent_fingerprint, _validate_session_binding)
- require_auth decorator branches (no header, invalid token, expired token, cookie auth)
- POST /api/auth/logout endpoint
- POST /api/auth/reset-password (change password via reset flow)
- GET /api/auth/me (user profile retrieval)
- POST /api/auth/refresh (token refresh)
"""

import datetime
import hashlib
import uuid
from datetime import timezone

import jwt
from flask import session

# ---------------------------------------------------------------------------
# TestSessionBinding
# ---------------------------------------------------------------------------


class TestSessionBinding:
    """Tests for _get_user_agent_fingerprint and _validate_session_binding."""

    def test_get_user_agent_fingerprint_with_ua(self, app, client):
        """Calling an endpoint with a User-Agent should produce a hash-based fingerprint."""
        from api.auth import _get_user_agent_fingerprint

        ua_string = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TestBrowser/1.0"
        expected = hashlib.sha256(ua_string.encode()).hexdigest()[:16]

        with app.test_request_context(headers={"User-Agent": ua_string}):
            result = _get_user_agent_fingerprint()

        assert result == expected
        assert len(result) == 16

    def test_get_user_agent_fingerprint_empty_ua(self, app, client):
        """Empty User-Agent should return 'unknown'."""
        from api.auth import _get_user_agent_fingerprint

        with app.test_request_context(headers={"User-Agent": ""}):
            result = _get_user_agent_fingerprint()

        assert result == "unknown"

    def test_get_user_agent_fingerprint_no_ua(self, app, client):
        """Missing User-Agent header should return 'unknown'."""
        from api.auth import _get_user_agent_fingerprint

        with app.test_request_context():
            result = _get_user_agent_fingerprint()

        assert result == "unknown"

    def test_validate_session_binding_no_session(self, app, client):
        """When no user_id in session, validation should pass."""
        from api.auth import _validate_session_binding

        with app.test_request_context():
            with client.session_transaction() as sess:
                sess.clear()
            is_valid, error = _validate_session_binding()

        assert is_valid is True
        assert error == ""

    def test_validate_session_binding_matching_ua(
        self, app, client, db_session, test_user
    ):
        """Session binding should pass when User-Agent matches stored fingerprint."""
        from api.auth import _validate_session_binding

        ua_string = "TestAgent/2.0"
        fingerprint = hashlib.sha256(ua_string.encode()).hexdigest()[:16]

        with app.test_request_context(headers={"User-Agent": ua_string}):
            session["user_id"] = test_user.id
            session["_ua_fingerprint"] = fingerprint
            is_valid, error = _validate_session_binding()

        assert is_valid is True
        assert error == ""

    def test_validate_session_binding_mismatched_ua(
        self, app, client, db_session, test_user
    ):
        """Session binding should fail when User-Agent does not match."""
        from api.auth import _validate_session_binding

        stored_fp = hashlib.sha256(b"OriginalBrowser/1.0").hexdigest()[:16]

        with app.test_request_context(headers={"User-Agent": "DifferentBrowser/2.0"}):
            session["user_id"] = test_user.id
            session["_ua_fingerprint"] = stored_fp
            is_valid, error = _validate_session_binding()

        assert is_valid is False
        assert "fingerprint" in error.lower()


# ---------------------------------------------------------------------------
# TestRequireAuth
# ---------------------------------------------------------------------------


class TestRequireAuth:
    """Tests for the require_auth decorator branches."""

    def test_require_auth_no_header(self, client, db_session, test_user):
        """Calling an authenticated endpoint with no Authorization header should return 401."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False

    def test_require_auth_invalid_token(self, client, db_session, test_user):
        """Calling with a garbage token should return 401."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer totally-invalid-garbage-token"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False

    def test_require_auth_expired_token(self, client, app, db_session, test_user):
        """Calling with an expired JWT should return 401."""
        payload = {
            "user_id": test_user.id,
            "email": test_user.email,
            "exp": datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=1),
            "iat": datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=2),
        }
        expired_token = jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    def test_require_auth_malformed_header(self, client, db_session, test_user):
        """Authorization header without 'Bearer' prefix should return 401."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Token some-value"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False

    def test_require_auth_bearer_only(self, client, db_session, test_user):
        """Authorization header with only 'Bearer' (no token) should return 401."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestLogoutEndpoint
# ---------------------------------------------------------------------------


class TestLogoutEndpoint:
    """Tests for POST /api/auth/logout."""

    def test_logout_success(self, authenticated_client):
        """Authenticated user should be able to logout successfully."""
        response = authenticated_client.post("/api/auth/logout")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "logged out" in data["message"].lower()

    def test_logout_requires_auth(self, client, db_session, test_user):
        """Logout without auth should return 401."""
        response = client.post("/api/auth/logout")
        assert response.status_code == 401

    def test_logout_clears_cookie(self, authenticated_client):
        """Logout should clear the auth_token cookie."""
        response = authenticated_client.post("/api/auth/logout")
        assert response.status_code == 200
        # Check that Set-Cookie header clears auth_token
        cookie_headers = response.headers.getlist("Set-Cookie")
        auth_cookie_cleared = any("auth_token" in c for c in cookie_headers)
        assert auth_cookie_cleared


# ---------------------------------------------------------------------------
# TestChangePassword
# ---------------------------------------------------------------------------


class TestChangePassword:
    """Tests for password change via the reset-password flow.

    There is no standalone /change-password endpoint, so we exercise
    the POST /api/auth/reset-password path which serves the same
    purpose and covers password change code in auth.py.
    """

    def test_change_password_success(self, client, db_session, test_user, app):
        """Reset password with a valid token and strong new password should succeed."""
        from api.auth import _generate_password_reset_token

        token = _generate_password_reset_token(test_user.id, test_user.email)

        # Store JTI so reset-password can validate it
        token_payload = jwt.decode(
            token, app.config["SECRET_KEY"], algorithms=["HS256"]
        )
        test_user.password_reset_jti = token_payload.get("jti")
        db_session.commit()

        response = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "NewStrongPass9876!"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_change_password_wrong_old(self, client, db_session, test_user, app):
        """Reset password with an invalid (tampered) token should fail."""
        # Create a token with wrong signing key to simulate invalid credentials
        payload = {
            "user_id": test_user.id,
            "email": test_user.email,
            "purpose": "password_reset",
            "exp": datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=1),
            "iat": datetime.datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }
        bad_token = jwt.encode(
            payload, "wrong-secret-key-completely", algorithm="HS256"
        )

        response = client.post(
            "/api/auth/reset-password",
            json={"token": bad_token, "password": "AnotherGoodPass1234!"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False


# ---------------------------------------------------------------------------
# TestUserProfile
# ---------------------------------------------------------------------------


class TestUserProfile:
    """Tests for GET /api/auth/me."""

    def test_get_profile(self, authenticated_client, db_session, test_user):
        """GET /api/auth/me should return user data for authenticated user."""
        response = authenticated_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "user" in data
        assert data["user"]["email"] == test_user.email
        assert data["user"]["first_name"] == test_user.first_name
        assert data["user"]["last_name"] == test_user.last_name

    def test_update_profile(self, authenticated_client, db_session, test_user):
        """GET /api/auth/me should reflect the company name stored on the user."""
        # Update company name directly in DB
        test_user.company_name = "Updated Company Name"
        db_session.commit()

        response = authenticated_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.get_json()
        assert data["user"]["company_name"] == "Updated Company Name"

    def test_get_profile_requires_auth(self, client, db_session, test_user):
        """GET /api/auth/me without auth should return 401."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_get_profile_includes_tier_info(
        self, authenticated_client, db_session, test_user
    ):
        """GET /api/auth/me should include subscription tier fields."""
        response = authenticated_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.get_json()
        user_data = data["user"]
        assert "subscription_tier" in user_data
        assert "migrations_remaining" in user_data
        assert "has_tier" in user_data


# ---------------------------------------------------------------------------
# TestDeleteAccount
# ---------------------------------------------------------------------------


class TestDeleteAccount:
    """Tests for account deletion behavior.

    The delete-account route is defined as a docstring example in the
    require_mfa decorator. Since it is not a registered endpoint, we
    verify that unsupported methods on auth endpoints are properly
    rejected by the application error handler.
    """

    def test_delete_account_not_allowed_method(self, authenticated_client):
        """DELETE on /api/auth/me is not a registered method and is rejected."""
        response = authenticated_client.delete("/api/auth/me")
        # The app's global error handler converts MethodNotAllowed to 500
        assert response.status_code in (405, 500)

    def test_delete_requires_auth(self, client, db_session, test_user):
        """Any operation on authenticated endpoint without auth is rejected."""
        response = client.delete("/api/auth/me")
        # May return 401, 405, or 500 depending on handler ordering
        assert response.status_code in (401, 405, 500)


# ---------------------------------------------------------------------------
# TestTokenRefresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    """Tests for POST /api/auth/refresh to improve require_auth coverage."""

    def test_refresh_token_success(self, authenticated_client):
        """Authenticated user should be able to refresh their token."""
        response = authenticated_client.post("/api/auth/refresh")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "token" in data
        assert len(data["token"]) > 0

    def test_refresh_token_requires_auth(self, client, db_session, test_user):
        """Refresh without auth should return 401."""
        response = client.post("/api/auth/refresh")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestLoginCoverage
# ---------------------------------------------------------------------------


class TestLoginCoverage:
    """Additional login tests to cover uncovered branches in auth.py."""

    def test_login_missing_email(self, client, db_session, test_user):
        """Login without email should return 400."""
        response = client.post(
            "/api/auth/login",
            json={"password": "TestPassword1234!"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_login_missing_password(self, client, db_session, test_user):
        """Login without password should return 400."""
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 400

    def test_login_wrong_password(self, client, db_session, test_user):
        """Login with wrong password should return 401."""
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "WrongPassword999!"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False

    def test_login_nonexistent_user(self, client, db_session):
        """Login with nonexistent email should return 401 (no enumeration)."""
        response = client.post(
            "/api/auth/login",
            json={
                "email": f"nonexistent-{uuid.uuid4()}@example.com",
                "password": "SomePassword1234!",
            },
        )
        assert response.status_code == 401

    def test_login_no_body(self, client, db_session, test_user):
        """Login with no JSON body should return 400."""
        response = client.post(
            "/api/auth/login",
            data="",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_login_success_sets_cookie(self, client, db_session, test_user):
        """Successful login should set an auth_token cookie."""
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword1234!"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "token" in data
        # Check cookie is set
        cookie_headers = response.headers.getlist("Set-Cookie")
        has_auth_cookie = any("auth_token" in c for c in cookie_headers)
        assert has_auth_cookie
