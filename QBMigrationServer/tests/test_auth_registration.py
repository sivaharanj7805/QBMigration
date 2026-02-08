"""Tests for auth registration, login edge cases, password change, profile, and logout."""


class TestRegistrationValidation:
    """Tests for registration endpoint validation."""

    def test_register_missing_email(self, client):
        response = client.post(
            "/api/auth/register",
            json={"password": "ValidPassword123!", "first_name": "Test"},
        )
        assert response.status_code == 400

    def test_register_missing_password(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "first_name": "Test"},
        )
        assert response.status_code == 400

    def test_register_invalid_email(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "ValidPassword123!"},
        )
        assert response.status_code == 400

    def test_register_weak_password(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "weak@example.com", "password": "short"},
        )
        assert response.status_code == 400

    def test_register_success(self, client, db_session):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "brand_new_user@example.com",
                "password": "StrongPassword123!",
                "first_name": "New",
                "last_name": "User",
            },
        )
        assert response.status_code in (200, 201)
        data = response.get_json()
        assert data["success"] is True

    def test_register_duplicate_email(self, client, db_session, test_user):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "StrongPassword123!",
            },
        )
        assert response.status_code in (400, 409)


class TestLoginEdgeCases:
    """Tests for login endpoint edge cases."""

    def test_login_missing_fields(self, client):
        response = client.post("/api/auth/login", json={})
        assert response.status_code == 400

    def test_login_empty_email(self, client):
        response = client.post(
            "/api/auth/login",
            json={"email": "", "password": "ValidPassword123!"},
        )
        assert response.status_code in (400, 401)

    def test_login_empty_password(self, client, db_session, test_user):
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": ""},
        )
        assert response.status_code in (400, 401)


class TestRefreshToken:
    """Tests for refresh token endpoint."""

    def test_refresh_requires_auth(self, client):
        response = client.post("/api/auth/refresh")
        assert response.status_code == 401

    def test_refresh_success(self, authenticated_client):
        response = authenticated_client.post("/api/auth/refresh")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "token" in data


class TestSendVerification:
    """Tests for send-verification endpoint."""

    def test_send_verification_requires_auth(self, client):
        response = client.post("/api/auth/send-verification")
        assert response.status_code == 401

    def test_send_verification_success(self, authenticated_client):
        response = authenticated_client.post("/api/auth/send-verification")
        assert response.status_code in (200, 401)

    def test_verification_status(self, authenticated_client):
        response = authenticated_client.get("/api/auth/verification-status")
        assert response.status_code == 200
        data = response.get_json()
        assert "verified" in data or "email_verified" in data


class TestLogout:
    """Tests for logout endpoint."""

    def test_logout_authenticated(self, authenticated_client):
        response = authenticated_client.post("/api/auth/logout")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_logout_unauthenticated(self, client):
        response = client.post("/api/auth/logout")
        # Logout without auth should still succeed or return 401
        assert response.status_code in (200, 401)
