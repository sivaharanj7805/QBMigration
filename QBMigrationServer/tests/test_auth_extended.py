"""
Extended Auth API Test Suite
Tests for auth endpoints not covered by existing tests.

Endpoints tested:
- GET  /api/auth/csrf-token
- GET  /api/auth/tiers
- POST /api/auth/select-tier
- POST /api/auth/forgot-password
- POST /api/auth/reset-password
- POST /api/auth/verify-email
- POST /api/auth/mfa/verify
- GET  /api/auth/team
- POST /api/auth/team/invite
- POST /api/auth/check-captcha-required
- GET  /api/auth/validate
- POST /api/auth/sync-credits
"""

import datetime
import os
import sys
from datetime import timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.migration_credit import MigrationCredit  # noqa: E402

# ============================================================================
# CSRF Token Endpoint
# ============================================================================


class TestCSRFToken:
    """Tests for GET /api/auth/csrf-token"""

    def test_csrf_token_returns_success(self, client, app):
        """CSRF token endpoint returns success with a token."""
        response = client.get("/api/auth/csrf-token")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "csrf_token" in data
        assert len(data["csrf_token"]) > 0

    def test_csrf_token_includes_expiry(self, client, app):
        """CSRF token response includes expires_in field."""
        response = client.get("/api/auth/csrf-token")
        data = response.get_json()
        assert "expires_in" in data
        assert isinstance(data["expires_in"], (int, float))
        assert data["expires_in"] > 0

    def test_csrf_token_in_response_header(self, client, app):
        """CSRF token is also returned in X-CSRF-Token header."""
        response = client.get("/api/auth/csrf-token")
        assert "X-CSRF-Token" in response.headers
        data = response.get_json()
        assert response.headers["X-CSRF-Token"] == data["csrf_token"]

    def test_csrf_token_no_auth_required(self, client, app):
        """CSRF token endpoint does not require authentication."""
        # Using a plain client without auth headers
        response = client.get("/api/auth/csrf-token")
        assert response.status_code == 200


# ============================================================================
# Tiers Endpoint
# ============================================================================


class TestGetTiers:
    """Tests for GET /api/auth/tiers"""

    def test_tiers_returns_success(self, client, app):
        """Tiers endpoint returns success with a list of tiers."""
        response = client.get("/api/auth/tiers")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "tiers" in data
        assert isinstance(data["tiers"], list)

    def test_tiers_contains_expected_tiers(self, client, app):
        """Response includes all expected tier IDs."""
        response = client.get("/api/auth/tiers")
        data = response.get_json()
        tier_ids = [t["id"] for t in data["tiers"]]
        for expected_id in [
            "starter",
            "business",
            "professional",
            "enterprise",
            "forensic",
        ]:
            assert expected_id in tier_ids, f"Missing tier: {expected_id}"

    def test_tiers_have_required_fields(self, client, app):
        """Each tier object has required fields."""
        response = client.get("/api/auth/tiers")
        data = response.get_json()
        for tier in data["tiers"]:
            assert "id" in tier
            assert "name" in tier
            assert "price" in tier
            assert "max_transactions" in tier
            assert "description" in tier

    def test_tiers_no_auth_required(self, client, app):
        """Tiers endpoint does not require authentication."""
        response = client.get("/api/auth/tiers")
        assert response.status_code == 200

    def test_forensic_tier_has_unlimited_transactions(self, client, app):
        """Forensic tier has unlimited transactions (max_transactions == -1)."""
        response = client.get("/api/auth/tiers")
        data = response.get_json()
        forensic = next(t for t in data["tiers"] if t["id"] == "forensic")
        assert forensic["max_transactions"] == -1


# ============================================================================
# Select Tier Endpoint
# ============================================================================


class TestSelectTier:
    """Tests for POST /api/auth/select-tier"""

    @patch("stripe.PaymentIntent.retrieve")
    def test_select_tier_success(
        self, mock_retrieve, authenticated_client, db_session, test_user
    ):
        """Selecting a valid tier with verified payment returns success."""
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_intent.amount = 49700  # starter price
        mock_retrieve.return_value = mock_intent

        response = authenticated_client.post(
            "/api/auth/select-tier",
            json={"tier_id": "starter", "payment_intent_id": "pi_test_123"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "tier" in data
        assert data["tier"] == "starter"

    @patch("stripe.PaymentIntent.retrieve")
    def test_select_tier_creates_migration_credit(
        self, mock_retrieve, authenticated_client, db_session, test_user
    ):
        """Selecting a tier with verified payment creates a MigrationCredit record."""
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_intent.amount = 49700
        mock_retrieve.return_value = mock_intent

        authenticated_client.post(
            "/api/auth/select-tier",
            json={"tier_id": "starter", "payment_intent_id": "pi_test_credit"},
        )
        credits = MigrationCredit.query.filter_by(
            user_id=test_user.id,
            tier_type="starter",
            status="available",
            payment_status="paid",
        ).all()
        assert len(credits) >= 1

    def test_select_tier_invalid_tier(
        self, authenticated_client, db_session, test_user
    ):
        """Selecting an invalid tier returns 400."""
        response = authenticated_client.post(
            "/api/auth/select-tier", json={"tier_id": "nonexistent_tier"}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_select_tier_missing_body(
        self, authenticated_client, db_session, test_user
    ):
        """Sending no JSON body returns error (auth layer intercepts bad request)."""
        response = authenticated_client.post(
            "/api/auth/select-tier", data="", content_type="application/json"
        )
        # Empty body causes BadRequest during auth token parsing, resulting in 401
        assert response.status_code in (400, 401)

    def test_select_tier_requires_auth(self, client, app):
        """Select tier endpoint requires authentication."""
        response = client.post("/api/auth/select-tier", json={"tier_id": "starter"})
        assert response.status_code == 401


# ============================================================================
# Forgot Password Endpoint
# ============================================================================


class TestForgotPassword:
    """Tests for POST /api/auth/forgot-password"""

    def test_forgot_password_existing_email(self, client, db_session, test_user):
        """Forgot password with existing email returns success (no enumeration)."""
        response = client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "message" in data

    def test_forgot_password_nonexistent_email(self, client, db_session):
        """Forgot password with nonexistent email returns same success response."""
        response = client.post(
            "/api/auth/forgot-password", json={"email": "doesnotexist@example.com"}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_forgot_password_prevents_enumeration(self, client, db_session, test_user):
        """Same response shape for existing and nonexistent emails."""
        resp_existing = client.post(
            "/api/auth/forgot-password", json={"email": "test@example.com"}
        )
        resp_missing = client.post(
            "/api/auth/forgot-password", json={"email": "nobody@example.com"}
        )
        data_existing = resp_existing.get_json()
        data_missing = resp_missing.get_json()
        # Both return identical message
        assert data_existing["message"] == data_missing["message"]

    def test_forgot_password_missing_email(self, client, db_session):
        """Forgot password with no email still returns success (anti-enumeration)."""
        response = client.post("/api/auth/forgot-password", json={"email": ""})
        # Even empty/invalid email returns 200 to prevent enumeration
        assert response.status_code == 200

    def test_forgot_password_no_body(self, client, db_session):
        """Forgot password with no JSON body returns 400."""
        response = client.post(
            "/api/auth/forgot-password", data="", content_type="application/json"
        )
        assert response.status_code == 400


# ============================================================================
# Reset Password Endpoint
# ============================================================================


class TestResetPassword:
    """Tests for POST /api/auth/reset-password"""

    def test_reset_password_invalid_token(self, client, db_session):
        """Reset with invalid token returns 400."""
        response = client.post(
            "/api/auth/reset-password",
            json={"token": "invalid-token-value", "password": "NewPassword1234!"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_reset_password_missing_token(self, client, db_session):
        """Reset with missing token returns 400."""
        response = client.post(
            "/api/auth/reset-password", json={"password": "NewPassword1234!"}
        )
        assert response.status_code == 400

    def test_reset_password_missing_password(self, client, db_session):
        """Reset with missing password returns 400."""
        response = client.post("/api/auth/reset-password", json={"token": "some-token"})
        assert response.status_code == 400

    def test_reset_password_weak_password(self, client, db_session, test_user, app):
        """Reset with a weak password returns 400."""
        # Generate a real token for this user
        from api.auth import _generate_password_reset_token

        token = _generate_password_reset_token(test_user.id, test_user.email)

        response = client.post(
            "/api/auth/reset-password", json={"token": token, "password": "weak"}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_reset_password_no_body(self, client, db_session):
        """Reset with no JSON body returns 400."""
        response = client.post(
            "/api/auth/reset-password", data="", content_type="application/json"
        )
        assert response.status_code == 400

    def test_reset_password_valid_token(self, client, db_session, test_user, app):
        """Reset with valid token and strong password succeeds."""
        from api.auth import _generate_password_reset_token

        token = _generate_password_reset_token(test_user.id, test_user.email)

        # HIGH-02 FIX: Store the JTI in the user record (mimics forgot-password flow)
        token_payload = jwt.decode(
            token, app.config["SECRET_KEY"], algorithms=["HS256"]
        )
        test_user.password_reset_jti = token_payload.get("jti")
        db_session.commit()

        response = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "NewSecurePass1234!"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_reset_password_expired_token(self, client, db_session, test_user, app):
        """Reset with expired token returns 400."""
        # Build an expired JWT manually
        payload = {
            "user_id": test_user.id,
            "email": test_user.email,
            "purpose": "password_reset",
            "exp": datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=1),
            "iat": datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=2),
        }
        expired_token = jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

        response = client.post(
            "/api/auth/reset-password",
            json={"token": expired_token, "password": "NewSecurePass1234!"},
        )
        assert response.status_code == 400


# ============================================================================
# Verify Email Endpoint
# ============================================================================


class TestVerifyEmail:
    """Tests for POST /api/auth/verify-email"""

    def test_verify_email_invalid_token(self, client, db_session):
        """Verify with invalid token returns 400."""
        response = client.post(
            "/api/auth/verify-email", json={"token": "totally-invalid-token"}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_verify_email_missing_token(self, client, db_session):
        """Verify with missing token returns 400."""
        response = client.post("/api/auth/verify-email", json={})
        assert response.status_code == 400

    def test_verify_email_no_body(self, client, db_session):
        """Verify with no JSON body returns 400."""
        response = client.post(
            "/api/auth/verify-email", data="", content_type="application/json"
        )
        assert response.status_code == 400

    def test_verify_email_valid_token(self, client, db_session, test_user, app):
        """Verify with a valid token marks the user email as verified."""
        from api.auth import _generate_email_verification_token

        token = _generate_email_verification_token(test_user.id, test_user.email)

        response = client.post("/api/auth/verify-email", json={"token": token})
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        # Check database
        db_session.refresh(test_user)
        assert test_user.email_verified is True

    def test_verify_email_expired_token(self, client, db_session, test_user, app):
        """Verify with expired token returns 400."""
        payload = {
            "user_id": test_user.id,
            "email": test_user.email,
            "purpose": "email_verification",
            "exp": datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=1),
            "iat": datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=25),
        }
        expired_token = jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

        response = client.post("/api/auth/verify-email", json={"token": expired_token})
        assert response.status_code == 400


# ============================================================================
# MFA Verify Endpoint
# ============================================================================


class TestMFAVerify:
    """Tests for POST /api/auth/mfa/verify"""

    def test_mfa_verify_requires_auth(self, client, app):
        """MFA verify requires authentication."""
        response = client.post("/api/auth/mfa/verify", json={"code": "123456"})
        assert response.status_code == 401

    def test_mfa_verify_no_body(self, authenticated_client, db_session, test_user):
        """MFA verify with no body returns error."""
        response = authenticated_client.post(
            "/api/auth/mfa/verify", data="", content_type="application/json"
        )
        # Empty body causes BadRequest during auth token parsing, resulting in 401
        assert response.status_code in (400, 401)

    def test_mfa_verify_invalid_code_format(
        self, authenticated_client, db_session, test_user
    ):
        """MFA verify with non-6-digit code returns 400."""
        response = authenticated_client.post(
            "/api/auth/mfa/verify", json={"code": "abc"}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_mfa_verify_mfa_not_enabled(
        self, authenticated_client, db_session, test_user
    ):
        """MFA verify when MFA is not enabled returns 400."""
        # test_user has mfa_enabled=False by default
        response = authenticated_client.post(
            "/api/auth/mfa/verify", json={"code": "123456"}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "not enabled" in data["error"].lower()

    def test_mfa_verify_empty_code(self, authenticated_client, db_session, test_user):
        """MFA verify with empty code returns 400."""
        response = authenticated_client.post("/api/auth/mfa/verify", json={"code": ""})
        assert response.status_code == 400


# ============================================================================
# Team Endpoint
# ============================================================================


class TestTeam:
    """Tests for GET /api/auth/team"""

    def test_team_requires_auth(self, client, app):
        """Team endpoint requires authentication."""
        response = client.get("/api/auth/team")
        assert response.status_code == 401

    def test_team_returns_owner(self, authenticated_client, db_session, test_user):
        """Team list includes the current user as Owner."""
        response = authenticated_client.get("/api/auth/team")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "team_members" in data
        assert len(data["team_members"]) >= 1
        # First member should be the owner
        owner = data["team_members"][0]
        assert owner["role"] == "Owner"
        assert owner["email"] == test_user.email

    def test_team_returns_pending_invites(
        self, authenticated_client, db_session, test_user
    ):
        """Team response includes pending_invites list."""
        response = authenticated_client.get("/api/auth/team")
        data = response.get_json()
        assert "pending_invites" in data
        assert isinstance(data["pending_invites"], list)


# ============================================================================
# Team Invite Endpoint
# ============================================================================


class TestTeamInvite:
    """Tests for POST /api/auth/team/invite"""

    def test_invite_requires_auth(self, client, app):
        """Team invite requires authentication."""
        response = client.post(
            "/api/auth/team/invite",
            json={"email": "invitee@example.com", "role": "member"},
        )
        assert response.status_code == 401

    def test_invite_success(self, authenticated_client, db_session, test_user):
        """Team invite creates a pending invitation."""
        response = authenticated_client.post(
            "/api/auth/team/invite",
            json={"email": "teammate@example.com", "role": "member"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["invite"]["email"] == "teammate@example.com"
        assert data["invite"]["role"] == "member"

    def test_invite_missing_email(self, authenticated_client, db_session, test_user):
        """Invite with missing email returns 400."""
        response = authenticated_client.post(
            "/api/auth/team/invite", json={"role": "member"}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_invite_no_body(self, authenticated_client, db_session, test_user):
        """Invite with no body returns error."""
        response = authenticated_client.post(
            "/api/auth/team/invite", data="", content_type="application/json"
        )
        # Empty body causes BadRequest during auth token parsing, resulting in 401
        assert response.status_code in (400, 401)

    def test_invite_default_role(self, authenticated_client, db_session, test_user):
        """Team invite feature now works and defaults to role='member' when not specified."""
        response = authenticated_client.post(
            "/api/auth/team/invite", json={"email": "default_role@example.com"}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        # Check that default role is 'member'
        assert data.get("invite", {}).get("role") == "member"


# ============================================================================
# Check CAPTCHA Required Endpoint
# ============================================================================


class TestCheckCaptchaRequired:
    """Tests for POST /api/auth/check-captcha-required"""

    def test_check_captcha_returns_result(self, client, db_session, test_user):
        """Check captcha returns captcha_required boolean."""
        response = client.post(
            "/api/auth/check-captcha-required", json={"email": "test@example.com"}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "captcha_required" in data
        assert isinstance(data["captcha_required"], bool)

    def test_check_captcha_includes_threshold(self, client, db_session, test_user):
        """Response includes a threshold value."""
        response = client.post(
            "/api/auth/check-captcha-required", json={"email": "test@example.com"}
        )
        data = response.get_json()
        assert "threshold" in data

    def test_check_captcha_nonexistent_email(self, client, db_session):
        """Nonexistent email returns same shape (no enumeration leak)."""
        response = client.post(
            "/api/auth/check-captcha-required", json={"email": "unknown@example.com"}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "captcha_required" in data

    def test_check_captcha_missing_email(self, client, db_session):
        """Missing email returns 400."""
        response = client.post("/api/auth/check-captcha-required", json={"email": ""})
        assert response.status_code == 400

    def test_check_captcha_no_body(self, client, db_session):
        """No JSON body returns 400."""
        response = client.post(
            "/api/auth/check-captcha-required", data="", content_type="application/json"
        )
        assert response.status_code == 400

    def test_check_captcha_no_auth_required(self, client, db_session, test_user):
        """Endpoint does not require authentication."""
        response = client.post(
            "/api/auth/check-captcha-required", json={"email": "test@example.com"}
        )
        assert response.status_code == 200


# ============================================================================
# Validate Session Endpoint
# ============================================================================


class TestValidateSession:
    """Tests for GET /api/auth/validate"""

    def test_validate_requires_auth(self, client, app):
        """Validate endpoint requires authentication."""
        response = client.get("/api/auth/validate")
        assert response.status_code == 401

    def test_validate_returns_user_info(
        self, authenticated_client, db_session, test_user
    ):
        """Validate returns user info for authenticated user."""
        response = authenticated_client.get("/api/auth/validate")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "user" in data
        assert data["user"]["email"] == test_user.email
        assert data["user"]["id"] == test_user.id

    def test_validate_includes_profile_fields(
        self, authenticated_client, db_session, test_user
    ):
        """Validate response includes first_name, last_name, company_name."""
        response = authenticated_client.get("/api/auth/validate")
        data = response.get_json()
        user_data = data["user"]
        assert "first_name" in user_data
        assert "last_name" in user_data
        assert "company_name" in user_data


# ============================================================================
# Sync Credits Endpoint
# ============================================================================


class TestSyncCredits:
    """Tests for POST /api/auth/sync-credits"""

    def test_sync_credits_requires_auth(self, client, app):
        """Sync credits requires authentication."""
        response = client.post("/api/auth/sync-credits")
        assert response.status_code == 401

    def test_sync_credits_no_legacy(self, authenticated_client, db_session, test_user):
        """Sync credits for user with no legacy credits returns success."""
        response = authenticated_client.post("/api/auth/sync-credits")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_sync_credits_creates_missing_records(
        self, authenticated_client, db_session, test_user
    ):
        """Sync creates MigrationCredit records matching legacy counts."""
        # Set legacy counts on user
        test_user.migrations_purchased = 3
        test_user.migrations_used = 1
        db_session.commit()

        response = authenticated_client.post("/api/auth/sync-credits")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        # Verify credits were created
        available = MigrationCredit.query.filter_by(
            user_id=test_user.id, status="available", payment_status="paid"
        ).count()
        used = MigrationCredit.query.filter_by(
            user_id=test_user.id, status="used", payment_status="paid"
        ).count()
        # Should have at least the legacy amounts
        assert available >= 2  # 3 purchased - 1 used = 2 available
        assert used >= 1

    def test_sync_credits_idempotent(self, authenticated_client, db_session, test_user):
        """Calling sync-credits twice does not duplicate records."""
        test_user.migrations_purchased = 1
        test_user.migrations_used = 0
        db_session.commit()

        authenticated_client.post("/api/auth/sync-credits")
        first_count = MigrationCredit.query.filter_by(
            user_id=test_user.id, payment_status="paid"
        ).count()

        authenticated_client.post("/api/auth/sync-credits")
        second_count = MigrationCredit.query.filter_by(
            user_id=test_user.id, payment_status="paid"
        ).count()

        assert first_count == second_count


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
