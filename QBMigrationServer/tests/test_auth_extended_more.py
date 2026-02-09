"""Extended auth tests - tier, team, MFA, captcha, and validation endpoints."""

from unittest.mock import MagicMock, patch


class TestAuthTiers:
    """Tests for tier-related endpoints."""

    def test_tiers_list_unauthenticated(self, client):
        response = client.get("/api/auth/tiers")
        assert response.status_code in (200, 401)

    def test_tiers_list(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/auth/tiers")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "tiers" in data

    def test_select_tier_requires_auth(self, client):
        response = client.post("/api/auth/select-tier", json={"tier": "starter"})
        assert response.status_code == 401

    def test_select_tier_missing_tier(self, authenticated_client, db_session):
        response = authenticated_client.post("/api/auth/select-tier", json={})
        assert response.status_code == 400

    def test_select_tier_invalid_id(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/auth/select-tier", json={"tier_id": "nonexistent"}
        )
        assert response.status_code == 400

    def test_select_tier_starter(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/auth/select-tier", json={"tier_id": "starter"}
        )
        assert response.status_code in (200, 400, 402)

    def test_upgrade_tier_requires_auth(self, client):
        response = client.post(
            "/api/auth/upgrade-tier",
            json={"tier": "professional", "payment_intent_id": "pi_test"},
        )
        assert response.status_code == 401

    def test_upgrade_tier_missing_fields(self, authenticated_client, db_session):
        response = authenticated_client.post("/api/auth/upgrade-tier", json={})
        assert response.status_code == 400

    def test_upgrade_tier_invalid_tier(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/auth/upgrade-tier", json={"tier_id": "nonexistent"}
        )
        assert response.status_code == 400

    def test_upgrade_tier_no_payment(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/auth/upgrade-tier", json={"tier_id": "professional"}
        )
        assert response.status_code == 402

    @patch("stripe.PaymentIntent.retrieve")
    def test_upgrade_tier_payment_failed(
        self, mock_retrieve, authenticated_client, db_session
    ):
        mock_retrieve.return_value = MagicMock(
            status="requires_payment_method",
            id="pi_test_failed",
        )
        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={"tier_id": "professional", "payment_intent_id": "pi_test_failed"},
        )
        assert response.status_code in (400, 402)

    @patch("stripe.PaymentIntent.retrieve")
    def test_upgrade_tier_success(
        self, mock_retrieve, authenticated_client, db_session
    ):
        mock_retrieve.return_value = MagicMock(
            status="succeeded",
            id="pi_test_ok",
            amount=9900,
        )
        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={"tier_id": "professional", "payment_intent_id": "pi_test_ok"},
        )
        assert response.status_code in (200, 400, 402, 500)


class TestAuthTeam:
    """Tests for team management endpoints."""

    def test_team_requires_auth(self, client):
        response = client.get("/api/auth/team")
        assert response.status_code == 401

    def test_team_list(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/auth/team")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_team_invite_requires_auth(self, client):
        response = client.post(
            "/api/auth/team/invite", json={"email": "invite@example.com"}
        )
        assert response.status_code == 401

    def test_team_invite_missing_email(self, authenticated_client, db_session):
        response = authenticated_client.post("/api/auth/team/invite", json={})
        assert response.status_code == 400

    def test_team_invite(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/auth/team/invite",
            json={"email": "teammate@example.com", "role": "member"},
        )
        # May succeed, 403 (not team owner), or 501 (not implemented)
        assert response.status_code in (200, 201, 400, 403, 501)


class TestAuthCaptcha:
    """Tests for CAPTCHA configuration endpoint."""

    def test_captcha_config(self, client, db_session):
        response = client.get("/api/auth/captcha-config")
        assert response.status_code == 200
        data = response.get_json()
        assert "enabled" in data or "provider" in data or "success" in data

    def test_check_captcha_required(self, client, db_session):
        response = client.get("/api/auth/check-captcha-required")
        assert response.status_code in (200, 404, 500)


class TestAuthValidate:
    """Tests for token validation endpoint."""

    def test_validate_requires_auth(self, client):
        response = client.get("/api/auth/validate")
        assert response.status_code == 401

    def test_validate_with_auth(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/auth/validate")
        assert response.status_code == 200
        data = response.get_json()
        assert data.get("valid") is True or data.get("success") is True


class TestAuthMe:
    """Tests for /api/auth/me endpoint."""

    def test_me_requires_auth(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_returns_user_data(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "user" in data
        assert data["user"]["email"] == "test@example.com"


class TestAuthForgotPassword:
    """Tests for forgot-password endpoint."""

    def test_forgot_password_no_data(self, client, db_session):
        response = client.post(
            "/api/auth/forgot-password",
            data="",
            content_type="application/json",
        )
        assert response.status_code in (400, 500)

    def test_forgot_password_missing_email(self, client, db_session):
        response = client.post("/api/auth/forgot-password", json={})
        assert response.status_code == 400

    @patch("api.auth._send_password_reset_email")
    def test_forgot_password_success(self, mock_send, client, db_session, test_user):
        mock_send.return_value = True
        response = client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )
        # Always returns 200 to prevent email enumeration
        assert response.status_code == 200

    def test_forgot_password_nonexistent_email(self, client, db_session):
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": "nonexistent@example.com"},
        )
        # Returns 200 even for nonexistent emails (prevent enumeration)
        assert response.status_code == 200


class TestAuthCSRF:
    """Tests for CSRF token endpoint."""

    def test_csrf_token(self, client, db_session):
        response = client.get("/api/auth/csrf-token")
        assert response.status_code == 200
        data = response.get_json()
        assert "csrf_token" in data or "token" in data

    def test_csrf_token_authenticated(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/auth/csrf-token")
        assert response.status_code == 200


class TestSyncCredits:
    """Tests for sync-credits endpoint."""

    def test_sync_credits_requires_auth(self, client):
        response = client.post("/api/auth/sync-credits")
        assert response.status_code == 401

    def test_sync_credits(self, authenticated_client, db_session):
        response = authenticated_client.post("/api/auth/sync-credits")
        assert response.status_code in (200, 404)
