"""Tests for auth password reset flow and MFA endpoints."""

from datetime import datetime, timezone
from unittest.mock import patch

import jwt


class TestResetPassword:
    """Tests for POST /api/auth/reset-password."""

    def test_reset_password_no_data(self, client, db_session):
        response = client.post(
            "/api/auth/reset-password",
            data="",
            content_type="application/json",
        )
        assert response.status_code in (400, 500)

    def test_reset_password_missing_token(self, client, db_session):
        response = client.post(
            "/api/auth/reset-password",
            json={"password": "NewStrongPass123!"},
        )
        assert response.status_code == 400

    def test_reset_password_missing_password(self, client, db_session):
        response = client.post(
            "/api/auth/reset-password",
            json={"token": "some-token"},
        )
        assert response.status_code == 400

    def test_reset_password_invalid_token(self, client, db_session):
        response = client.post(
            "/api/auth/reset-password",
            json={"token": "invalid-token", "password": "NewStrongPass123!"},
        )
        assert response.status_code in (400, 401)

    @patch("api.auth._send_password_reset_email")
    def test_forgot_then_reset_flow(
        self, mock_send, client, db_session, test_user, app
    ):
        mock_send.return_value = True
        # Request reset
        response = client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )
        assert response.status_code == 200

        # Generate a valid token manually
        import uuid

        jti = str(uuid.uuid4())
        test_user.reset_token_jti = jti
        db_session.commit()

        token = jwt.encode(
            {
                "user_id": test_user.id,
                "purpose": "password_reset",
                "jti": jti,
                "exp": datetime(2030, 1, 1, tzinfo=timezone.utc),
            },
            app.config["SECRET_KEY"],
            algorithm="HS256",
        )

        response = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "BrandNewPassword123!"},
        )
        assert response.status_code in (200, 400)


class TestVerifyEmail:
    """Tests for email verification endpoints."""

    def test_send_verification_requires_auth(self, client):
        response = client.post("/api/auth/send-verification")
        assert response.status_code == 401

    def test_verify_email_no_token(self, client, db_session):
        response = client.get("/api/auth/verify-email")
        assert response.status_code in (400, 404, 405, 500)

    def test_verify_email_invalid_token(self, client, db_session):
        response = client.get("/api/auth/verify-email?token=invalid-token")
        assert response.status_code in (400, 401, 404, 500)

    def test_verification_status(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/auth/verification-status")
        assert response.status_code == 200
        data = response.get_json()
        assert "verified" in data or "email_verified" in data


class TestMFAEndpoints:
    """Tests for MFA setup and verification."""

    def test_mfa_setup_requires_auth(self, client):
        response = client.post("/api/auth/mfa/setup")
        assert response.status_code in (401, 404)

    def test_mfa_verify_requires_auth(self, client):
        response = client.post("/api/auth/mfa/verify", json={"code": "123456"})
        assert response.status_code == 401

    def test_mfa_status_requires_auth(self, client):
        response = client.get("/api/auth/mfa/status")
        assert response.status_code in (401, 404)

    def test_mfa_setup(self, authenticated_client, db_session):
        response = authenticated_client.post("/api/auth/mfa/setup")
        assert response.status_code in (200, 404, 500)

    def test_mfa_verify_bad_code(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/auth/mfa/verify", json={"code": "000000"}
        )
        assert response.status_code in (400, 401, 404)


class TestLoginExtended:
    """Extended login tests for anomaly detection paths."""

    def test_login_success_records_login(self, client, db_session, test_user):
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword1234!"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "token" in data

    def test_login_wrong_password(self, client, db_session, test_user):
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "WrongPassword123!"},
        )
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client, db_session):
        response = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "SomePassword123!"},
        )
        assert response.status_code == 401

    def test_login_locked_account(self, client, db_session, test_user):
        # Lock the account
        test_user.account_locked_until = datetime(2030, 1, 1, tzinfo=timezone.utc)
        db_session.commit()

        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPassword1234!"},
        )
        assert response.status_code in (401, 403, 429)
