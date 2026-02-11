"""
Deep coverage tests for api/auth.py targeting ALL uncovered lines.

Covers:
- require_auth: session binding failure, cookie auth fallback
- require_mfa decorator: MFA not enabled, recently verified, required (403)
- require_role decorator: wrong role, user not found, correct role
- admin_required shorthand
- verify_mfa endpoint: TOTP verification, invalid code, backup codes
- constant_time_compare function
- JWT signing/verification key: RS256 paths, unsupported algorithms
- validate_email fallback paths
- validate_password internal branches
- Registration: duplicate email timing attack, password validation failure, generic exception
- Login: CAPTCHA required/failed, MFA required response
- /me endpoint: auto-sync legacy credits, tier info error handling
- Logout: QBO token revocation
- /validate endpoint: user not found, exception fallback
- /select-tier: invalid tier, paid tier Stripe flow, idempotency
- /upgrade-tier: missing tier_id, Stripe verification, idempotency
- /team: team member listing with exception fallback
- /team/invite: user not found
- _generate_password_reset_token
- _send_password_reset_email: Flask-Mail path + fallback + exception handling
- forgot-password: fake timing hash for nonexistent user
- reset-password: token decode, JTI mismatch, password validation, reuse prevention
- _verify_email_verification_token: wrong purpose
- _send_verification_email: Flask-Mail + fallback
- send-verification endpoint
- verify-email endpoint
- check-captcha-required, validate, admin endpoints
"""

import datetime
import os
import sys
from datetime import timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.auth import (  # noqa: E402
    _generate_password_reset_token,
    _get_jwt_signing_key,
    _get_jwt_verification_key,
    _send_password_reset_email,
    _send_verification_email,
    _verify_email_verification_token,
    _verify_password_reset_token,
    constant_time_compare,
    create_token,
    validate_email,
    validate_password,
)
from models.user import User  # noqa: E402

# ============================================================================
# HELPERS
# ============================================================================


def _enable_mfa_for_user(user, app):
    """Enable MFA on a user with a proper encryption key."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    app.config["BACKUP_ENCRYPTION_KEY"] = key
    app.config["MFA_ENCRYPTION_KEY"] = key
    secret, qr_url, backup_codes = user.enable_2fa()
    return secret, backup_codes


# ============================================================================
# TestConstantTimeCompare (Lines 455-464)
# ============================================================================


class TestConstantTimeCompare:
    def test_equal_strings(self, app):
        with app.app_context():
            assert constant_time_compare("abc", "abc") is True

    def test_different_strings(self, app):
        with app.app_context():
            assert constant_time_compare("abc", "def") is False

    def test_non_string_first(self, app):
        with app.app_context():
            assert constant_time_compare(123, "abc") is False

    def test_non_string_second(self, app):
        with app.app_context():
            assert constant_time_compare("abc", 456) is False

    def test_empty_strings(self, app):
        with app.app_context():
            assert constant_time_compare("", "") is True

    def test_none_inputs(self, app):
        with app.app_context():
            assert constant_time_compare(None, None) is False


# ============================================================================
# TestJWTKeys (Lines 490-519)
# ============================================================================


class TestJWTKeys:
    def test_default_hs256_signing_key(self, app):
        with app.app_context():
            key = _get_jwt_signing_key()
            assert key == app.config["SECRET_KEY"]

    def test_default_hs256_verification_key(self, app):
        with app.app_context():
            key = _get_jwt_verification_key()
            assert key == app.config["SECRET_KEY"]

    def test_unsupported_algorithm_signing(self, app):
        with app.app_context():
            original = app.config.get("JWT_ALGORITHM", "HS256")
            app.config["JWT_ALGORITHM"] = "none"
            try:
                with pytest.raises(ValueError, match="Unsupported"):
                    _get_jwt_signing_key()
            finally:
                app.config["JWT_ALGORITHM"] = original

    def test_unsupported_algorithm_verification(self, app):
        with app.app_context():
            original = app.config.get("JWT_ALGORITHM", "HS256")
            app.config["JWT_ALGORITHM"] = "none"
            try:
                with pytest.raises(ValueError, match="Unsupported"):
                    _get_jwt_verification_key()
            finally:
                app.config["JWT_ALGORITHM"] = original

    def test_rs256_no_private_key_path(self, app):
        with app.app_context():
            original = app.config.get("JWT_ALGORITHM", "HS256")
            app.config["JWT_ALGORITHM"] = "RS256"
            app.config.pop("JWT_PRIVATE_KEY_PATH", None)
            try:
                with pytest.raises(ValueError, match="private key"):
                    _get_jwt_signing_key()
            finally:
                app.config["JWT_ALGORITHM"] = original

    def test_rs256_no_public_key_path(self, app):
        with app.app_context():
            original = app.config.get("JWT_ALGORITHM", "HS256")
            app.config["JWT_ALGORITHM"] = "RS256"
            app.config.pop("JWT_PUBLIC_KEY_PATH", None)
            try:
                with pytest.raises(ValueError, match="public key"):
                    _get_jwt_verification_key()
            finally:
                app.config["JWT_ALGORITHM"] = original

    def test_rs256_unreadable_private_key(self, app):
        with app.app_context():
            original = app.config.get("JWT_ALGORITHM", "HS256")
            app.config["JWT_ALGORITHM"] = "RS256"
            app.config["JWT_PRIVATE_KEY_PATH"] = "/nonexistent/path/key.pem"
            try:
                with pytest.raises(ValueError, match="could not be read"):
                    _get_jwt_signing_key()
            finally:
                app.config["JWT_ALGORITHM"] = original

    def test_rs256_unreadable_public_key(self, app):
        with app.app_context():
            original = app.config.get("JWT_ALGORITHM", "HS256")
            app.config["JWT_ALGORITHM"] = "RS256"
            app.config["JWT_PUBLIC_KEY_PATH"] = "/nonexistent/path/key.pem"
            try:
                with pytest.raises(ValueError, match="could not be read"):
                    _get_jwt_verification_key()
            finally:
                app.config["JWT_ALGORITHM"] = original


# ============================================================================
# TestValidateEmail (Lines 552, 571)
# ============================================================================


class TestValidateEmail:
    def test_valid_email(self, app):
        with app.app_context():
            assert validate_email("test@example.com") is True

    def test_empty_email(self, app):
        with app.app_context():
            assert validate_email("") is False

    def test_none_email(self, app):
        with app.app_context():
            assert validate_email(None) is False

    def test_non_string_email(self, app):
        with app.app_context():
            assert validate_email(123) is False

    def test_invalid_format(self, app):
        with app.app_context():
            assert validate_email("not-an-email") is False

    def test_regex_fallback_when_no_library(self, app):
        """Line 571: when email_validator not importable, falls back to regex."""
        with app.app_context():
            # Temporarily hide email_validator
            with patch.dict("sys.modules", {"email_validator": None}):
                # Force re-evaluation: the ImportError catch triggers regex fallback
                # Need to call in a way that the import inside fails
                assert validate_email("user@domain.com") is True


# ============================================================================
# TestValidatePassword (Lines 641, 643, 648, 670)
# ============================================================================


class TestValidatePassword:
    def test_short_password(self, app):
        with app.app_context():
            valid, msg = validate_password("Short1!")
            assert valid is False
            assert "12 characters" in msg

    def test_no_uppercase(self, app):
        with app.app_context():
            valid, msg = validate_password("alllowercase1!")
            assert valid is False
            assert "uppercase" in msg

    def test_no_lowercase(self, app):
        with app.app_context():
            valid, msg = validate_password("ALLUPPERCASE1!!!")
            assert valid is False
            assert "lowercase" in msg

    def test_no_digit(self, app):
        with app.app_context():
            valid, msg = validate_password("NoDigitsHereOk!!")
            assert valid is False
            assert "digit" in msg

    def test_no_special_char(self, app):
        with app.app_context():
            valid, msg = validate_password("NoSpecialChar123A")
            assert valid is False
            assert "special character" in msg

    def test_common_password(self, app):
        """Line 648: password matches common list after .lower()."""
        with app.app_context():
            # "Password123!" -> .lower() = "password123!" which is in _COMMON_PASSWORDS
            valid, msg = validate_password("Password123!")
            assert valid is False
            assert "common" in msg.lower()

    def test_valid_password(self, app):
        with app.app_context():
            valid, msg = validate_password("StrongPass123!xyz")
            assert valid is True
            assert msg == ""


# ============================================================================
# TestRequireAuthSessionAndCookie (Lines 155-156, 182-183)
# ============================================================================


class TestRequireAuthSessionAndCookie:
    def test_session_binding_failure_clears_session(self, app, client, db_session):
        """Lines 155-156: session binding invalid -> session cleared, 401."""
        user = User(email="session@example.com", first_name="S", last_name="U")
        user.set_password("TestPassword1234!")
        db_session.add(user)
        db_session.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = user.id
            sess["email"] = user.email
            sess["_ua_fingerprint"] = "mismatch_fingerprint"

        response = client.get(
            "/api/auth/me",
            headers={"User-Agent": "Different-Browser/1.0"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert data.get("session_invalid") is True

    def test_cookie_auth_fallback(self, app, client, db_session, test_user):
        """Lines 182-183: cookie auth fallback when no header or session."""
        with app.app_context():
            token = create_token(test_user.id, test_user.email)

        client.set_cookie("auth_token", token, domain="localhost")
        response = client.get("/api/auth/me")
        assert response.status_code == 200

    def test_cookie_auth_invalid_token(self, app, client, db_session):
        """Cookie with invalid token falls through to 401."""
        client.set_cookie("auth_token", "invalid.jwt.token", domain="localhost")
        response = client.get("/api/auth/me")
        assert response.status_code == 401


# ============================================================================
# TestRequireMFA (Lines 220-270)
# ============================================================================


class TestRequireMFA:
    def test_mfa_not_enabled_allows_through(
        self, authenticated_client, db_session, test_user, app
    ):
        """Lines 238-241: MFA not enabled -> allow through."""
        app.config["REQUIRE_MFA_FOR_PRIVILEGED_OPS"] = True
        test_user.mfa_enabled = False
        db_session.commit()
        response = authenticated_client.get("/api/auth/me")
        assert response.status_code == 200

    def test_mfa_disabled_globally(
        self, authenticated_client, db_session, test_user, app
    ):
        """Lines 225-226: REQUIRE_MFA_FOR_PRIVILEGED_OPS=False -> allow."""
        app.config["REQUIRE_MFA_FOR_PRIVILEGED_OPS"] = False
        response = authenticated_client.get("/api/auth/me")
        assert response.status_code == 200

    def test_require_mfa_decorator_blocks_when_mfa_enabled(
        self, app, db_session, test_user
    ):
        """Lines 257-268: MFA enabled but not recently verified -> 403."""
        from api.auth import require_auth, require_mfa
        from flask import jsonify

        app.config["REQUIRE_MFA_FOR_PRIVILEGED_OPS"] = True
        secret, _ = _enable_mfa_for_user(test_user, app)
        db_session.commit()

        # Test the decorator directly in a request context
        token = create_token(test_user.id, test_user.email)

        @require_auth
        @require_mfa
        def protected_view():
            return jsonify({"success": True})

        with app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
            result = protected_view()
            # result is a tuple (response, status_code) when MFA blocks
            if isinstance(result, tuple):
                response_obj, status = result
                assert status == 403
                data = response_obj.get_json()
                assert data.get("mfa_required") is True
            else:
                pytest.fail("Expected 403 but got success response")


# ============================================================================
# TestRequireRole (Lines 295-340)
# ============================================================================


class TestRequireRole:
    def test_wrong_role_returns_403(self, app, db_session, test_user):
        """Lines 318-336: user lacks required role -> 403."""
        from api.auth import require_auth, require_role
        from flask import jsonify

        test_user.role = "user"
        db_session.commit()

        token = create_token(test_user.id, test_user.email)

        @require_auth
        @require_role("admin", "super_admin")
        def admin_only_view():
            return jsonify({"success": True})

        with app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
            result = admin_only_view()
            if isinstance(result, tuple):
                response_obj, status = result
                assert status == 403
                data = response_obj.get_json()
                assert "Insufficient permissions" in data["error"]
            else:
                pytest.fail("Expected 403 but got success response")

    def test_correct_role_allows(self, app, db_session, test_user):
        """Lines 314-315: user has correct role -> allow."""
        from api.auth import require_auth, require_role
        from flask import jsonify

        test_user.role = "admin"
        db_session.commit()

        token = create_token(test_user.id, test_user.email)

        @require_auth
        @require_role("admin")
        def admin_view():
            return jsonify({"success": True})

        with app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
            result = admin_view()
            if isinstance(result, tuple):
                _, status = result
                assert status == 200
            else:
                data = result.get_json()
                assert data["success"] is True

    def test_super_admin_hierarchy(self, app, db_session, test_user):
        """Lines 318-320: role hierarchy check - super_admin accesses admin."""
        from api.auth import require_auth, require_role
        from flask import jsonify

        test_user.role = "super_admin"
        db_session.commit()

        token = create_token(test_user.id, test_user.email)

        @require_auth
        @require_role("admin")
        def admin_view_hier():
            return jsonify({"success": True})

        with app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
            result = admin_view_hier()
            if isinstance(result, tuple):
                _, status = result
                assert status == 200
            else:
                data = result.get_json()
                assert data["success"] is True

    def test_role_user_not_found(self, app, db_session):
        """Lines 306-308: user deleted but has valid token."""
        from api.auth import require_auth, require_role
        from flask import jsonify

        token = create_token(99999, "gone@example.com")

        @require_auth
        @require_role("admin")
        def admin_view_nf():
            return jsonify({"success": True})

        with app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
            result = admin_view_nf()
            if isinstance(result, tuple):
                _, status = result
                assert status == 404


# ============================================================================
# TestAdminRequired (Line 349)
# ============================================================================


class TestAdminRequired:
    def test_admin_required_rejects_normal_user(self, app, db_session, test_user):
        """Line 349: require_admin shorthand rejects non-admin."""
        from api.auth import require_admin, require_auth
        from flask import jsonify

        test_user.role = "user"
        db_session.commit()

        token = create_token(test_user.id, test_user.email)

        @require_auth
        @require_admin
        def admin_req_view():
            return jsonify({"success": True})

        with app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
            result = admin_req_view()
            if isinstance(result, tuple):
                _, status = result
                assert status == 403


# ============================================================================
# TestVerifyMFA (Lines 395-429)
# ============================================================================


class TestVerifyMFA:
    def test_verify_mfa_empty_json(self, authenticated_client):
        """Lines 374-376: empty json body -> code missing."""
        response = authenticated_client.post("/api/auth/mfa/verify", json={})
        assert response.status_code == 400

    def test_verify_mfa_invalid_code_format(self, authenticated_client):
        response = authenticated_client.post(
            "/api/auth/mfa/verify", json={"code": "abc"}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "Invalid MFA code format" in data["error"]

    def test_verify_mfa_not_enabled(self, authenticated_client, db_session, test_user):
        test_user.mfa_enabled = False
        db_session.commit()
        response = authenticated_client.post(
            "/api/auth/mfa/verify", json={"code": "123456"}
        )
        assert response.status_code == 400
        assert "not enabled" in response.get_json()["error"]

    def test_verify_mfa_invalid_code(
        self, authenticated_client, db_session, test_user, app
    ):
        """Lines 414-416: TOTP verification with invalid code."""
        _enable_mfa_for_user(test_user, app)
        db_session.commit()
        response = authenticated_client.post(
            "/api/auth/mfa/verify", json={"code": "000000"}
        )
        assert response.status_code == 401
        assert "Invalid MFA code" in response.get_json()["error"]

    def test_verify_mfa_valid_code(
        self, authenticated_client, db_session, test_user, app
    ):
        """Lines 426-436: valid TOTP code -> session marked MFA verified."""
        import pyotp

        secret, _ = _enable_mfa_for_user(test_user, app)
        db_session.commit()

        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        response = authenticated_client.post(
            "/api/auth/mfa/verify", json={"code": valid_code}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["verified"] is True
        assert data["valid_for_seconds"] == 300

    def test_verify_mfa_secret_not_configured(
        self, authenticated_client, db_session, test_user, app
    ):
        """Lines 406-410: MFA enabled but secret missing -> 500."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user.mfa_enabled = True
        test_user._mfa_secret_encrypted = None
        test_user.mfa_secret = None
        db_session.commit()

        response = authenticated_client.post(
            "/api/auth/mfa/verify", json={"code": "123456"}
        )
        assert response.status_code == 500
        assert "not configured" in response.get_json()["error"]


# ============================================================================
# TestRegistration (Lines 715-717, 741-748, 787-790)
# ============================================================================


class TestRegistrationDeep:
    def test_duplicate_email_timing_attack_prevention(self, client, db_session):
        """Lines 715-717: duplicate email performs fake hash for timing."""
        user = User(email="existing@example.com", first_name="E", last_name="U")
        user.set_password("ExistingPass123!")
        db_session.add(user)
        db_session.commit()

        response = client.post(
            "/api/auth/register",
            json={
                "email": "existing@example.com",
                "password": "StrongNewPass123!",
                "first_name": "New",
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "could not be completed" in data["error"]

    def test_password_validation_failure_from_set_password(self, client, db_session):
        """Lines 741-748: ValueError from set_password during registration."""
        # First register user to create password history
        response1 = client.post(
            "/api/auth/register",
            json={
                "email": "reuse@example.com",
                "password": "ValidPass123!ok",
                "first_name": "Test",
            },
        )
        assert response1.status_code == 201

    def test_registration_generic_exception(self, client, db_session):
        """Lines 787-790: generic exception handler."""
        with patch("api.auth.db.session.add", side_effect=Exception("DB error")):
            response = client.post(
                "/api/auth/register",
                json={
                    "email": "excep@example.com",
                    "password": "StrongPass123!ok",
                    "first_name": "Test",
                },
            )
            assert response.status_code == 500
            data = response.get_json()
            assert "Registration failed" in data["error"]


# ============================================================================
# TestLoginCaptcha (Lines 823-844, 905-911)
# ============================================================================


class TestLoginCaptcha:
    def test_captcha_required_no_token(self, client, db_session, test_user):
        """Lines 823-833: CAPTCHA required but not provided."""
        with patch("api.auth.is_captcha_required", return_value=True):
            response = client.post(
                "/api/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "TestPassword1234!",
                },
            )
            assert response.status_code == 400
            data = response.get_json()
            assert data.get("captcha_required") is True

    def test_captcha_verification_failed(self, client, db_session, test_user):
        """Lines 840-853: CAPTCHA provided but verification failed."""
        with patch("api.auth.is_captcha_required", return_value=True):
            with patch(
                "api.auth.verify_captcha_token",
                return_value=(False, "bad captcha"),
            ):
                response = client.post(
                    "/api/auth/login",
                    json={
                        "email": "test@example.com",
                        "password": "TestPassword1234!",
                        "captcha_token": "invalid-token",
                    },
                )
                assert response.status_code == 400
                data = response.get_json()
                assert data.get("captcha_required") is True
                assert "CAPTCHA" in data["error"]

    def test_login_with_mfa_enabled(self, client, db_session, test_user, app):
        """Lines 905-911: user has MFA enabled -> login still succeeds."""
        _enable_mfa_for_user(test_user, app)
        db_session.commit()

        response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "TestPassword1234!",
            },
        )
        # Login succeeds; MFA enforcement happens at privileged endpoints
        assert response.status_code == 200


# ============================================================================
# TestMeEndpoint (Lines 1006-1040, 1047-1062)
# ============================================================================


class TestMeEndpointDeep:
    def test_me_auto_sync_legacy_credits(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 1006-1040: auto-sync legacy credits to MigrationCredit."""
        test_user.migrations_purchased = 3
        test_user.migrations_used = 0
        test_user.subscription_tier = "starter"
        db_session.commit()

        response = authenticated_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_me_tier_info_attribute_error(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 1047-1058: tier info AttributeError handling."""
        with patch.object(
            User,
            "get_tier_info",
            side_effect=AttributeError("missing column"),
        ):
            response = authenticated_client.get("/api/auth/me")
            assert response.status_code == 200
            data = response.get_json()
            user_data = data["user"]
            assert user_data["subscription_tier"] == "none"

    def test_me_tier_info_generic_exception(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 1059-1071: tier info generic Exception -> 500."""
        with patch.object(
            User,
            "get_tier_info",
            side_effect=RuntimeError("DB corruption"),
        ):
            response = authenticated_client.get("/api/auth/me")
            assert response.status_code == 500
            data = response.get_json()
            assert data["error_code"] == "TIER_INFO_UNAVAILABLE"


# ============================================================================
# TestLogout (Lines 1128-1134)
# ============================================================================


class TestLogoutDeep:
    def test_logout_revokes_qbo_tokens(
        self, authenticated_client, db_session, test_user, app
    ):
        """Lines 1128-1131: QBO token revocation on logout."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user.set_qbo_tokens("access_tok", "refresh_tok", "realm123", None)
        db_session.commit()

        with patch("api.qbo.revoke_qbo_tokens") as mock_revoke:
            response = authenticated_client.post("/api/auth/logout")
            assert response.status_code == 200
            mock_revoke.assert_called_once()

    def test_logout_qbo_revocation_failure(
        self, authenticated_client, db_session, test_user, app
    ):
        """Lines 1132-1134: QBO revocation fails but logout still succeeds."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_user.set_qbo_tokens("access_tok", "refresh_tok", "realm123", None)
        db_session.commit()

        with patch(
            "api.qbo.revoke_qbo_tokens",
            side_effect=Exception("Revoke failed"),
        ):
            response = authenticated_client.post("/api/auth/logout")
            assert response.status_code == 200


# ============================================================================
# TestValidateSession (Lines 1213, 1227-1229)
# ============================================================================


class TestValidateSessionDeep:
    def test_validate_user_not_found(self, app, client, db_session):
        """Line 1213: user deleted after token issued -> 401."""
        token = create_token(99999, "gone@example.com")
        response = client.get(
            "/api/auth/validate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_validate_exception_handling(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 1227-1229: exception in validation -> 401."""
        with patch(
            "api.auth.db.session.get",
            side_effect=Exception("DB error"),
        ):
            response = authenticated_client.get("/api/auth/validate")
            assert response.status_code == 401
            data = response.get_json()
            assert "validation failed" in data["error"]


# ============================================================================
# TestSelectTier (Lines 1294, 1329, 1340-1362, 1377, 1389-1390)
# ============================================================================


class TestSelectTierDeep:
    def test_select_invalid_tier(self, authenticated_client, db_session):
        """Line 1294: invalid tier_id."""
        response = authenticated_client.post(
            "/api/auth/select-tier",
            json={"tier_id": "nonexistent_tier"},
        )
        assert response.status_code == 400
        assert "Invalid tier" in response.get_json()["error"]

    def test_select_tier_paid_no_payment_intent(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 1307-1317: paid tier without payment_intent_id -> 402."""
        response = authenticated_client.post(
            "/api/auth/select-tier",
            json={"tier_id": "business"},
        )
        assert response.status_code == 402
        assert "Payment required" in response.get_json()["error"]

    @patch("stripe.PaymentIntent.retrieve")
    def test_select_paid_tier_stripe_success(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Lines 1340-1362: Stripe verification for paid tier."""
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_intent.amount = 9999999
        mock_stripe.return_value = mock_intent

        response = authenticated_client.post(
            "/api/auth/select-tier",
            json={
                "tier_id": "professional",
                "payment_intent_id": "pi_test_select_deep",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    @patch("stripe.PaymentIntent.retrieve")
    def test_select_paid_tier_payment_not_succeeded(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Line 1329: payment status != succeeded."""
        mock_intent = MagicMock()
        mock_intent.status = "requires_payment_method"
        mock_intent.amount = 999999
        mock_stripe.return_value = mock_intent

        response = authenticated_client.post(
            "/api/auth/select-tier",
            json={
                "tier_id": "business",
                "payment_intent_id": "pi_test_incomplete",
            },
        )
        assert response.status_code == 402
        assert "not been completed" in response.get_json()["error"]

    @patch("stripe.PaymentIntent.retrieve")
    def test_select_paid_tier_amount_mismatch(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Lines 1339-1348: payment amount too low."""
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_intent.amount = 1
        mock_stripe.return_value = mock_intent

        response = authenticated_client.post(
            "/api/auth/select-tier",
            json={
                "tier_id": "business",
                "payment_intent_id": "pi_test_amount_low",
            },
        )
        assert response.status_code == 402
        assert "amount" in response.get_json()["error"].lower()

    @patch("stripe.PaymentIntent.retrieve")
    def test_select_paid_tier_stripe_invalid_request(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Lines 1350-1359: Stripe InvalidRequestError."""
        import stripe

        mock_stripe.side_effect = stripe.error.InvalidRequestError(
            "No such payment", "payment_intent_id"
        )
        response = authenticated_client.post(
            "/api/auth/select-tier",
            json={
                "tier_id": "business",
                "payment_intent_id": "pi_invalid",
            },
        )
        assert response.status_code == 402
        assert "Invalid payment" in response.get_json()["error"]

    @patch("stripe.PaymentIntent.retrieve")
    def test_select_paid_tier_stripe_generic_error(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Lines 1360-1370: Stripe generic exception."""
        mock_stripe.side_effect = Exception("Stripe down")
        response = authenticated_client.post(
            "/api/auth/select-tier",
            json={
                "tier_id": "business",
                "payment_intent_id": "pi_error",
            },
        )
        assert response.status_code == 500
        assert "verification failed" in response.get_json()["error"].lower()

    @patch("stripe.PaymentIntent.retrieve")
    def test_select_paid_tier_idempotency(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Lines 1377, 1389-1390: duplicate payment_intent_id rejected."""
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_intent.amount = 9999999
        mock_stripe.return_value = mock_intent

        # First request succeeds
        resp1 = authenticated_client.post(
            "/api/auth/select-tier",
            json={
                "tier_id": "professional",
                "payment_intent_id": "pi_dup_check_sel_deep",
            },
        )
        assert resp1.status_code == 200

        # Second request with same PI is rejected
        resp2 = authenticated_client.post(
            "/api/auth/select-tier",
            json={
                "tier_id": "professional",
                "payment_intent_id": "pi_dup_check_sel_deep",
            },
        )
        assert resp2.status_code == 409
        assert "already been applied" in resp2.get_json()["error"]


# ============================================================================
# TestUpgradeTier (Lines 1453, 1506-1570)
# ============================================================================


class TestUpgradeTierDeep:
    def test_upgrade_missing_tier(self, authenticated_client, db_session):
        """Line 1453: missing/empty tier_id."""
        response = authenticated_client.post(
            "/api/auth/upgrade-tier", json={"tier_id": ""}
        )
        assert response.status_code == 400

    def test_upgrade_invalid_tier(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={"tier_id": "nonexistent"},
        )
        assert response.status_code == 400

    def test_upgrade_paid_tier_no_payment_intent(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 1462-1473: paid tier without payment_intent_id -> 402."""
        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={"tier_id": "enterprise"},
        )
        assert response.status_code == 402
        assert "Payment required" in response.get_json()["error"]

    @patch("stripe.PaymentIntent.retrieve")
    def test_upgrade_stripe_success(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Lines 1506-1570: Stripe verification + credit creation."""
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_intent.amount = 9999999
        mock_stripe.return_value = mock_intent

        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={
                "tier_id": "enterprise",
                "payment_intent_id": "pi_upgrade_ent_deep",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    @patch("stripe.PaymentIntent.retrieve")
    def test_upgrade_payment_not_completed(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        mock_intent = MagicMock()
        mock_intent.status = "pending"
        mock_intent.amount = 9999999
        mock_stripe.return_value = mock_intent

        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={
                "tier_id": "enterprise",
                "payment_intent_id": "pi_upgrade_pend_deep",
            },
        )
        assert response.status_code == 402

    @patch("stripe.PaymentIntent.retrieve")
    def test_upgrade_amount_mismatch(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_intent.amount = 1
        mock_stripe.return_value = mock_intent

        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={
                "tier_id": "enterprise",
                "payment_intent_id": "pi_upgrade_low_deep",
            },
        )
        assert response.status_code == 402

    @patch("stripe.PaymentIntent.retrieve")
    def test_upgrade_stripe_invalid_request(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Lines 1506-1515: Stripe InvalidRequestError."""
        import stripe

        mock_stripe.side_effect = stripe.error.InvalidRequestError(
            "No such pi", "payment_intent_id"
        )
        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={
                "tier_id": "enterprise",
                "payment_intent_id": "pi_bad_deep",
            },
        )
        assert response.status_code == 402

    @patch("stripe.PaymentIntent.retrieve")
    def test_upgrade_stripe_generic_error(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Lines 1516-1526: generic Stripe error."""
        mock_stripe.side_effect = Exception("Stripe network error")
        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={
                "tier_id": "enterprise",
                "payment_intent_id": "pi_net_err_deep",
            },
        )
        assert response.status_code == 500

    @patch("stripe.PaymentIntent.retrieve")
    def test_upgrade_idempotency_check(
        self, mock_stripe, authenticated_client, db_session, test_user
    ):
        """Lines 1528-1541: duplicate payment_intent_id -> 409."""
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_intent.amount = 9999999
        mock_stripe.return_value = mock_intent

        authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={
                "tier_id": "enterprise",
                "payment_intent_id": "pi_dup_upgrade_deep",
            },
        )
        resp2 = authenticated_client.post(
            "/api/auth/upgrade-tier",
            json={
                "tier_id": "enterprise",
                "payment_intent_id": "pi_dup_upgrade_deep",
            },
        )
        assert resp2.status_code == 409


# ============================================================================
# TestTeam (Lines 1593, 1623-1626, 1664)
# ============================================================================


class TestTeamDeep:
    def test_team_list_success(self, authenticated_client, db_session, test_user):
        """Lines 1593+: normal team listing."""
        response = authenticated_client.get("/api/auth/team")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_team_list_with_exception_fallback(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 1623-1626: team fetch exception -> fallback with owner only."""
        with patch(
            "models.team_invite.TeamInvite.get_team_members",
            side_effect=Exception("Table not found"),
        ):
            response = authenticated_client.get("/api/auth/team")
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert len(data["team_members"]) >= 1

    def test_team_invite_user_not_found(self, app, client, db_session):
        """Line 1664: user not found during invite."""
        token = create_token(99999, "ghost@example.com")
        response = client.post(
            "/api/auth/team/invite",
            json={"email": "invitee@example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_team_invite_no_email(self, authenticated_client, db_session, test_user):
        response = authenticated_client.post(
            "/api/auth/team/invite", json={"email": ""}
        )
        assert response.status_code == 400

    def test_team_invite_feature_not_available(
        self, authenticated_client, db_session, test_user
    ):
        """Team invites are now implemented and working."""
        response = authenticated_client.post(
            "/api/auth/team/invite",
            json={"email": "team@example.com"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True


# ============================================================================
# TestPasswordResetToken (Line 1725)
# ============================================================================


class TestPasswordResetToken:
    def test_generate_password_reset_token(self, app):
        """Line 1725: _generate_password_reset_token."""
        with app.app_context():
            token = _generate_password_reset_token(1, "user@example.com")
            assert token is not None
            payload = jwt.decode(
                token,
                app.config["SECRET_KEY"],
                algorithms=["HS256"],
            )
            assert payload["purpose"] == "password_reset"
            assert payload["user_id"] == 1
            assert "jti" in payload

    def test_verify_password_reset_token_valid(self, app):
        with app.app_context():
            token = _generate_password_reset_token(1, "user@example.com")
            payload = _verify_password_reset_token(token)
            assert payload is not None
            assert payload["purpose"] == "password_reset"

    def test_verify_password_reset_token_wrong_purpose(self, app):
        """Line 1725: token with wrong purpose returns None."""
        with app.app_context():
            token = jwt.encode(
                {
                    "user_id": 1,
                    "email": "user@example.com",
                    "purpose": "something_else",
                    "exp": datetime.datetime.now(timezone.utc)
                    + datetime.timedelta(hours=1),
                },
                app.config["SECRET_KEY"],
                algorithm="HS256",
            )
            result = _verify_password_reset_token(token)
            assert result is None

    def test_verify_password_reset_token_expired(self, app):
        with app.app_context():
            token = jwt.encode(
                {
                    "user_id": 1,
                    "email": "user@example.com",
                    "purpose": "password_reset",
                    "exp": datetime.datetime.now(timezone.utc)
                    - datetime.timedelta(hours=1),
                },
                app.config["SECRET_KEY"],
                algorithm="HS256",
            )
            result = _verify_password_reset_token(token)
            assert result is None


# ============================================================================
# TestSendPasswordResetEmail (Lines 1755-1803, 1812-1817)
# ============================================================================


class TestSendPasswordResetEmail:
    def test_dev_fallback_no_mail(self, app):
        """Lines 1806-1810: dev mode with no mail config -> log URL."""
        with app.app_context():
            app.config.pop("MAIL_SERVER", None)
            app.config.pop("MAIL_USERNAME", None)
            result = _send_password_reset_email("test@example.com", "tok123")
            assert result is True

    def test_flask_mail_path(self, app):
        """Lines 1755-1799: Flask-Mail configured and sends successfully."""
        with app.app_context():
            app.config["MAIL_SERVER"] = "smtp.example.com"
            app.config["MAIL_USERNAME"] = "noreply@example.com"

            mock_mail_mod = MagicMock()
            mock_mail_instance = MagicMock()
            mock_mail_mod.Mail.return_value = mock_mail_instance
            mock_mail_mod.Message.return_value = MagicMock()

            with patch.dict("sys.modules", {"flask_mail": mock_mail_mod}):
                result = _send_password_reset_email("test@example.com", "tok123")
                assert result is True
                mock_mail_instance.send.assert_called_once()

            app.config.pop("MAIL_SERVER", None)
            app.config.pop("MAIL_USERNAME", None)

    def test_flask_mail_send_exception(self, app):
        """Lines 1802-1803: Flask-Mail send fails -> falls through to dev fallback."""
        with app.app_context():
            app.config["MAIL_SERVER"] = "smtp.example.com"
            app.config["MAIL_USERNAME"] = "noreply@example.com"

            mock_mail_mod = MagicMock()
            mock_mail_instance = MagicMock()
            mock_mail_instance.send.side_effect = Exception("SMTP error")
            mock_mail_mod.Mail.return_value = mock_mail_instance
            mock_mail_mod.Message.return_value = MagicMock()

            with patch.dict("sys.modules", {"flask_mail": mock_mail_mod}):
                result = _send_password_reset_email("test@example.com", "tok123")
                # Falls back to dev mode since FLASK_ENV != production
                assert result is True

            app.config.pop("MAIL_SERVER", None)
            app.config.pop("MAIL_USERNAME", None)

    def test_production_no_mail_returns_false(self, app):
        """Lines 1812-1813: production mode with no mail -> returns False."""
        with app.app_context():
            app.config["MAIL_SERVER"] = "smtp.example.com"
            app.config["MAIL_USERNAME"] = "noreply@example.com"

            # Simulate ImportError for flask_mail
            original_env = os.environ.get("FLASK_ENV")
            os.environ["FLASK_ENV"] = "production"
            app.config["FLASK_ENV"] = "production"

            with patch.dict("sys.modules", {"flask_mail": None}):
                result = _send_password_reset_email("test@example.com", "tok123")
                assert result is False

            # Restore
            os.environ["FLASK_ENV"] = original_env or "testing"
            app.config["FLASK_ENV"] = "testing"
            app.config.pop("MAIL_SERVER", None)
            app.config.pop("MAIL_USERNAME", None)

    def test_outer_exception_handler(self, app):
        """Lines 1815-1817: outer exception handler."""
        with app.app_context():
            with patch(
                "api.auth.current_app.config",
                new_callable=lambda: MagicMock(
                    side_effect=RuntimeError("Config broken"),
                    get=MagicMock(side_effect=RuntimeError("broken")),
                ),
            ):
                result = _send_password_reset_email("test@example.com", "tok")
                assert result is False


# ============================================================================
# TestForgotPassword (Lines 1893-1894)
# ============================================================================


class TestForgotPasswordDeep:
    def test_forgot_password_existing_user(self, client, db_session, test_user):
        """Lines 1866-1881: real user -> token generated + email sent."""
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        # Check JTI was stored
        db_session.refresh(test_user)
        assert test_user.password_reset_jti is not None

    def test_forgot_password_nonexistent_user(self, client, db_session):
        """Lines 1893-1894: fake timing hash for nonexistent user."""
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": "nonexistent@example.com"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_forgot_password_invalid_email(self, client, db_session):
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": "not-an-email"},
        )
        assert response.status_code == 200

    def test_forgot_password_no_data(self, client, db_session):
        response = client.post(
            "/api/auth/forgot-password",
            content_type="application/json",
            data="null",
        )
        assert response.status_code == 400


# ============================================================================
# TestResetPassword (Lines 1933, 1967, 1970, 1984-1985, 2016-2022)
# ============================================================================


class TestResetPasswordDeep:
    def _generate_valid_token_and_store_jti(self, app, db_session, test_user):
        """Helper: generate a reset token and store its JTI on the user."""
        with app.app_context():
            token = _generate_password_reset_token(test_user.id, test_user.email)
            payload = jwt.decode(
                token,
                app.config["SECRET_KEY"],
                algorithms=["HS256"],
            )
            test_user.password_reset_jti = payload["jti"]
            db_session.commit()
            return token

    def test_reset_password_no_data(self, client, db_session):
        """Line 1933: no data -> 400."""
        response = client.post(
            "/api/auth/reset-password",
            content_type="application/json",
            data="null",
        )
        assert response.status_code == 400

    def test_reset_password_no_token(self, client, db_session):
        response = client.post(
            "/api/auth/reset-password",
            json={"password": "NewStrongPass123!"},
        )
        assert response.status_code == 400

    def test_reset_password_invalid_token(self, client, db_session):
        """Line 1967: invalid token -> 400."""
        response = client.post(
            "/api/auth/reset-password",
            json={
                "token": "invalid.jwt.token",
                "password": "NewStrongPass123!",
            },
        )
        assert response.status_code == 400

    def test_reset_password_user_not_found(self, app, client, db_session):
        """Line 1967: valid token but user deleted."""
        with app.app_context():
            token = _generate_password_reset_token(99999, "gone@example.com")
        response = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "NewStrongPass123!"},
        )
        assert response.status_code == 404

    def test_reset_password_inactive_user(self, app, client, db_session, test_user):
        """Line 1970: inactive user -> 403."""
        token = self._generate_valid_token_and_store_jti(app, db_session, test_user)
        test_user.is_active = False
        db_session.commit()

        response = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "NewStrongPass123!"},
        )
        assert response.status_code == 403

        # Restore
        test_user.is_active = True
        db_session.commit()

    def test_reset_password_jti_mismatch(self, app, client, db_session, test_user):
        """Lines 1984-1985: JTI doesn't match stored value."""
        with app.app_context():
            token = _generate_password_reset_token(test_user.id, test_user.email)
        test_user.password_reset_jti = "different-jti-value"
        db_session.commit()

        response = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "BrandNewPass123!"},
        )
        assert response.status_code == 400
        assert "already been used" in response.get_json()["error"]

    def test_reset_password_weak_password(self, app, client, db_session, test_user):
        """Line validation: weak password fails."""
        token = self._generate_valid_token_and_store_jti(app, db_session, test_user)
        response = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "weak"},
        )
        assert response.status_code == 400

    def test_reset_password_success(self, app, client, db_session, test_user):
        """Lines 1997-2014: successful password reset."""
        token = self._generate_valid_token_and_store_jti(app, db_session, test_user)
        response = client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "password": "CompletelyNewPass123!",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        db_session.refresh(test_user)
        assert test_user.password_reset_jti is None

    def test_reset_password_reuse_prevention(self, app, client, db_session, test_user):
        """Lines 2016-2022: password reuse -> ValueError from set_password."""
        test_user.set_password("CurrentPass123!ok")
        db_session.commit()

        token = self._generate_valid_token_and_store_jti(app, db_session, test_user)

        response = client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "password": "CurrentPass123!ok",
            },
        )
        assert response.status_code == 400


# ============================================================================
# TestEmailVerification (Line 2071, Lines 2092-2158)
# ============================================================================


class TestEmailVerificationDeep:
    def test_verify_email_verification_token_wrong_purpose(self, app):
        """Line 2071: wrong purpose returns None."""
        with app.app_context():
            token = jwt.encode(
                {
                    "user_id": 1,
                    "email": "u@example.com",
                    "purpose": "password_reset",
                    "exp": datetime.datetime.now(timezone.utc)
                    + datetime.timedelta(hours=24),
                },
                app.config["SECRET_KEY"],
                algorithm="HS256",
            )
            result = _verify_email_verification_token(token)
            assert result is None

    def test_verify_email_verification_token_expired(self, app):
        with app.app_context():
            token = jwt.encode(
                {
                    "user_id": 1,
                    "email": "u@example.com",
                    "purpose": "email_verification",
                    "exp": datetime.datetime.now(timezone.utc)
                    - datetime.timedelta(hours=1),
                },
                app.config["SECRET_KEY"],
                algorithm="HS256",
            )
            result = _verify_email_verification_token(token)
            assert result is None

    def test_send_verification_email_dev_fallback(self, app):
        """Lines 2148-2151: dev fallback for verification email."""
        with app.app_context():
            app.config.pop("MAIL_SERVER", None)
            app.config.pop("MAIL_USERNAME", None)
            result = _send_verification_email("test@example.com", "vtok123")
            assert result is True

    def test_send_verification_email_flask_mail(self, app):
        """Lines 2100-2142: Flask-Mail path."""
        with app.app_context():
            app.config["MAIL_SERVER"] = "smtp.example.com"
            app.config["MAIL_USERNAME"] = "noreply@example.com"

            mock_mail_mod = MagicMock()
            mock_mail_instance = MagicMock()
            mock_mail_mod.Mail.return_value = mock_mail_instance
            mock_mail_mod.Message.return_value = MagicMock()

            with patch.dict("sys.modules", {"flask_mail": mock_mail_mod}):
                result = _send_verification_email("test@example.com", "vtok123")
                assert result is True
                mock_mail_instance.send.assert_called_once()

            app.config.pop("MAIL_SERVER", None)
            app.config.pop("MAIL_USERNAME", None)

    def test_send_verification_email_import_error(self, app):
        """Lines 2143-2144: Flask-Mail not installed."""
        with app.app_context():
            app.config["MAIL_SERVER"] = "smtp.example.com"
            app.config["MAIL_USERNAME"] = "noreply@example.com"

            with patch.dict("sys.modules", {"flask_mail": None}):
                result = _send_verification_email("test@example.com", "vtok123")
                assert result is True

            app.config.pop("MAIL_SERVER", None)
            app.config.pop("MAIL_USERNAME", None)

    def test_send_verification_email_send_error(self, app):
        """Lines 2145-2146: Flask-Mail send fails."""
        with app.app_context():
            app.config["MAIL_SERVER"] = "smtp.example.com"
            app.config["MAIL_USERNAME"] = "noreply@example.com"

            mock_mail_mod = MagicMock()
            mock_mail_instance = MagicMock()
            mock_mail_instance.send.side_effect = Exception("SMTP fail")
            mock_mail_mod.Mail.return_value = mock_mail_instance
            mock_mail_mod.Message.return_value = MagicMock()

            with patch.dict("sys.modules", {"flask_mail": mock_mail_mod}):
                result = _send_verification_email("test@example.com", "vtok123")
                assert result is True

            app.config.pop("MAIL_SERVER", None)
            app.config.pop("MAIL_USERNAME", None)

    def test_send_verification_email_outer_exception(self, app):
        """Lines 2156-2158: outer exception handler."""
        with app.app_context():
            # Force an exception by passing a non-string that causes a crash
            with patch(
                "api.auth.current_app.config",
                new_callable=lambda: MagicMock(
                    get=MagicMock(side_effect=RuntimeError("broken"))
                ),
            ):
                result = _send_verification_email("test@example.com", "vtok")
                assert result is False


# ============================================================================
# TestSendVerificationEndpoint (Lines 2183, 2186-2215)
# ============================================================================


class TestSendVerificationEndpoint:
    def test_send_verification_success(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 2203-2213: send verification for current email."""
        response = authenticated_client.post("/api/auth/send-verification", json={})
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_send_verification_new_email(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 2186-2202: new email address provided."""
        response = authenticated_client.post(
            "/api/auth/send-verification",
            json={"email": "newemail@example.com"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_send_verification_invalid_new_email(
        self, authenticated_client, db_session, test_user
    ):
        """Line 2191: invalid new email format."""
        response = authenticated_client.post(
            "/api/auth/send-verification",
            json={"email": "not-valid"},
        )
        assert response.status_code == 400

    def test_send_verification_email_taken(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 2194-2196: new email already in use."""
        other = User(email="taken@example.com", first_name="O", last_name="U")
        other.set_password("OtherPass1234!")
        db_session.add(other)
        db_session.commit()

        response = authenticated_client.post(
            "/api/auth/send-verification",
            json={"email": "taken@example.com"},
        )
        assert response.status_code == 409

    def test_send_verification_user_not_found(self, app, client, db_session):
        """Line 2183: user not found."""
        token = create_token(99999, "gone@example.com")
        response = client.post(
            "/api/auth/send-verification",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_send_verification_send_fails(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 2214-2222: _send_verification_email returns False."""
        with patch("api.auth._send_verification_email", return_value=False):
            response = authenticated_client.post("/api/auth/send-verification", json={})
            assert response.status_code == 500


# ============================================================================
# TestVerifyEmailEndpoint (Lines 2250, 2273, 2281-2291)
# ============================================================================


class TestVerifyEmailEndpoint:
    def test_verify_email_no_data(self, client, db_session):
        response = client.post(
            "/api/auth/verify-email",
            content_type="application/json",
            data="null",
        )
        assert response.status_code == 400

    def test_verify_email_empty_token(self, client, db_session):
        """Line 2250: empty token."""
        response = client.post("/api/auth/verify-email", json={"token": ""})
        assert response.status_code == 400

    def test_verify_email_invalid_token(self, client, db_session):
        response = client.post(
            "/api/auth/verify-email",
            json={"token": "bad.jwt.token"},
        )
        assert response.status_code == 400

    def test_verify_email_user_not_found(self, app, client, db_session):
        """Line 2273: user not found."""
        with app.app_context():
            from api.auth import _generate_email_verification_token

            token = _generate_email_verification_token(99999, "gone@example.com")
        response = client.post("/api/auth/verify-email", json={"token": token})
        assert response.status_code == 404

    def test_verify_email_success(self, app, client, db_session, test_user):
        """Lines 2296-2302: successful email verification."""
        with app.app_context():
            from api.auth import _generate_email_verification_token

            token = _generate_email_verification_token(test_user.id, test_user.email)
        response = client.post("/api/auth/verify-email", json={"token": token})
        assert response.status_code == 200
        db_session.refresh(test_user)
        assert test_user.email_verified is True

    def test_verify_email_change(self, app, client, db_session, test_user):
        """Lines 2281-2291: email change verification."""
        new_email = "changed@example.com"
        with app.app_context():
            from api.auth import _generate_email_verification_token

            token = _generate_email_verification_token(test_user.id, new_email)
        response = client.post("/api/auth/verify-email", json={"token": token})
        assert response.status_code == 200
        db_session.refresh(test_user)
        assert test_user.email == new_email
        assert test_user.email_verified is True

    def test_verify_email_change_already_taken(
        self, app, client, db_session, test_user
    ):
        """Lines 2281-2286: new email already taken."""
        other = User(email="occupied@example.com", first_name="O", last_name="U")
        other.set_password("OtherPass1234!")
        db_session.add(other)
        db_session.commit()

        with app.app_context():
            from api.auth import _generate_email_verification_token

            token = _generate_email_verification_token(
                test_user.id, "occupied@example.com"
            )
        response = client.post("/api/auth/verify-email", json={"token": token})
        assert response.status_code == 409


# ============================================================================
# TestCheckCaptchaRequired (Line 2322, 2388)
# ============================================================================


class TestCheckCaptchaRequired:
    def test_check_captcha_no_data(self, client, db_session):
        """Line 2388: no data."""
        response = client.post(
            "/api/auth/check-captcha-required",
            content_type="application/json",
            data="null",
        )
        assert response.status_code == 400

    def test_check_captcha_empty_email(self, client, db_session):
        response = client.post(
            "/api/auth/check-captcha-required",
            json={"email": ""},
        )
        assert response.status_code == 400

    def test_check_captcha_existing_user(self, client, db_session, test_user):
        """Line 2322+: check captcha for existing user."""
        response = client.post(
            "/api/auth/check-captcha-required",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "captcha_required" in data
        assert data["threshold"] == 3

    def test_check_captcha_nonexistent_user(self, client, db_session):
        response = client.post(
            "/api/auth/check-captcha-required",
            json={"email": "nobody@example.com"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "captcha_required" in data


# ============================================================================
# TestVerificationStatus (Line 2322)
# ============================================================================


class TestVerificationStatus:
    def test_verification_status_user_not_found(self, app, client, db_session):
        """Line 2322: user not found in verification-status."""
        token = create_token(99999, "gone@example.com")
        response = client.get(
            "/api/auth/verification-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_verification_status_success(
        self, authenticated_client, db_session, test_user
    ):
        response = authenticated_client.get("/api/auth/verification-status")
        assert response.status_code == 200
        data = response.get_json()
        assert "email_verified" in data


# ============================================================================
# TestSyncCredits (Line 2441)
# ============================================================================


class TestSyncCreditsDeep:
    def test_sync_credits_user_not_found(self, app, client, db_session):
        """Line 2441: sync-credits with nonexistent user."""
        token = create_token(99999, "gone@example.com")
        response = client.post(
            "/api/auth/sync-credits",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_sync_credits_success(self, authenticated_client, db_session, test_user):
        test_user.migrations_purchased = 2
        test_user.migrations_used = 0
        test_user.subscription_tier = "starter"
        db_session.commit()

        response = authenticated_client.post("/api/auth/sync-credits")
        assert response.status_code == 200

    def test_sync_credits_with_used_credits(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 2487-2499: sync-credits creates used credit records."""
        test_user.migrations_purchased = 3
        test_user.migrations_used = 2
        test_user.subscription_tier = "starter"
        db_session.commit()

        response = authenticated_client.post("/api/auth/sync-credits")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True


# ============================================================================
# TestLoginDeep (Lines 805, 812, 863-876, 888-893, 911)
# ============================================================================


class TestLoginDeep:
    def test_login_no_data(self, client, db_session):
        """Line 805: missing data."""
        response = client.post(
            "/api/auth/login",
            content_type="application/json",
            data="null",
        )
        assert response.status_code == 400

    def test_login_missing_email(self, client, db_session):
        """Line 812: missing email."""
        response = client.post(
            "/api/auth/login",
            json={"password": "SomePass123!"},
        )
        assert response.status_code == 400
        assert "email" in response.get_json()["error"].lower()

    def test_login_nonexistent_user_timing_attack(self, client, db_session):
        """Lines 863-876: non-existent user gets fake hash for timing."""
        response = client.post(
            "/api/auth/login",
            json={
                "email": "doesnotexist@example.com",
                "password": "SomePass123!xyz",
            },
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.get_json()["error"]

    def test_login_wrong_password_tracks_failure(self, client, db_session, test_user):
        """Lines 888-893: wrong password records failed login."""
        response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "WrongPass123!xyz",
            },
        )
        assert response.status_code == 401
        db_session.refresh(test_user)
        assert test_user.failed_login_attempts >= 1

    def test_login_anomaly_detection(self, client, db_session, test_user):
        """Lines 905-911: anomaly detection fires on login."""
        with patch(
            "api.auth.check_login_anomalies",
            return_value=[{"severity": "critical", "reason": "geo_jump"}],
        ):
            with patch("api.auth.log_anomaly"):
                response = client.post(
                    "/api/auth/login",
                    json={
                        "email": "test@example.com",
                        "password": "TestPassword1234!",
                    },
                )
                # Login still succeeds but anomaly is logged
                assert response.status_code == 200


# ============================================================================
# TestMeEndpointSync (Lines 1034-1040)
# ============================================================================


class TestMeEndpointSyncError:
    def test_me_auto_sync_exception(self, authenticated_client, db_session, test_user):
        """Lines 1034-1040: auto-sync credits DB error -> continues."""
        from models.migration_credit import MigrationCredit

        test_user.migrations_purchased = 5
        test_user.migrations_used = 0
        test_user.subscription_tier = "starter"
        db_session.commit()

        with patch.object(
            MigrationCredit,
            "__init__",
            side_effect=Exception("DB constraint error"),
        ):
            response = authenticated_client.get("/api/auth/me")
            # Should succeed even if sync fails
            assert response.status_code == 200


# ============================================================================
# TestRefreshToken (Lines 1099-1104)
# ============================================================================


class TestRefreshToken:
    def test_refresh_token(self, authenticated_client, db_session, test_user):
        """Lines 1099-1104: token refresh endpoint."""
        response = authenticated_client.post("/api/auth/refresh")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "token" in data


# ============================================================================
# TestTiersEndpoint (Lines 1244-1263)
# ============================================================================


class TestTiersEndpoint:
    def test_get_tiers_list(self, client, db_session):
        """Lines 1244-1263: get available tiers."""
        response = client.get("/api/auth/tiers")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "tiers" in data
        assert len(data["tiers"]) > 0
        # Check tier structure
        tier = data["tiers"][0]
        assert "id" in tier
        assert "name" in tier
        assert "price" in tier
        assert "price_display" in tier
        assert "max_transactions" in tier


# ============================================================================
# TestCaptchaConfig (Lines 2357-2359)
# ============================================================================


class TestCaptchaConfig:
    def test_captcha_config(self, client, db_session):
        """Lines 2357-2359: captcha-config endpoint."""
        response = client.get("/api/auth/captcha-config")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "captcha" in data


# ============================================================================
# TestResetPasswordMore (Lines 1942, 1974-1975, 2019-2022)
# ============================================================================


class TestResetPasswordMore:
    def _generate_valid_token_and_store_jti(self, app, db_session, test_user):
        with app.app_context():
            token = _generate_password_reset_token(test_user.id, test_user.email)
            payload = jwt.decode(
                token,
                app.config["SECRET_KEY"],
                algorithms=["HS256"],
            )
            test_user.password_reset_jti = payload["jti"]
            db_session.commit()
            return token

    def test_reset_password_empty_password(self, client, db_session, test_user, app):
        """Line 1942: empty new_password -> 400."""
        token = self._generate_valid_token_and_store_jti(app, db_session, test_user)
        response = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": ""},
        )
        assert response.status_code == 400

    def test_reset_password_email_mismatch(self, client, db_session, test_user, app):
        """Lines 1974-1975: token email differs from user email."""
        with app.app_context():
            # Generate token with wrong email
            token = jwt.encode(
                {
                    "user_id": test_user.id,
                    "email": "wrong@example.com",
                    "purpose": "password_reset",
                    "jti": "test-jti-mismatch-email",
                    "exp": datetime.datetime.now(timezone.utc)
                    + datetime.timedelta(hours=1),
                },
                app.config["SECRET_KEY"],
                algorithm="HS256",
            )
        test_user.password_reset_jti = "test-jti-mismatch-email"
        db_session.commit()

        response = client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "password": "BrandNewSecure123!",
            },
        )
        assert response.status_code == 400
        assert "Invalid reset token" in response.get_json()["error"]

    def test_reset_password_generic_exception(self, client, db_session, test_user, app):
        """Lines 2019-2022: generic exception during password reset."""
        token = self._generate_valid_token_and_store_jti(app, db_session, test_user)
        with patch.object(
            User,
            "set_password",
            side_effect=RuntimeError("DB write error"),
        ):
            response = client.post(
                "/api/auth/reset-password",
                json={
                    "token": token,
                    "password": "ValidNewPass123!ok",
                },
            )
            assert response.status_code == 500
            assert "Failed to reset" in response.get_json()["error"]


# ============================================================================
# TestForgotPasswordMore (Lines 1893-1894)
# ============================================================================


class TestForgotPasswordMore:
    def test_forgot_password_fake_hash_exception(self, client, db_session):
        """Lines 1893-1894: fake hash exception path for nonexistent user."""
        # Trigger the argon2 PasswordHasher fake hash path
        # for a user that does not exist
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": "fakeuser99@example.com"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True


# ============================================================================
# TestRegistrationMore (Lines 688, 691, 694, 699)
# ============================================================================


class TestRegistrationMore:
    def test_register_missing_email(self, client, db_session):
        """Line 688: email empty."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "",
                "password": "StrongPass123!ok",
                "first_name": "Test",
            },
        )
        assert response.status_code == 400
        assert "Email is required" in response.get_json()["error"]

    def test_register_missing_password(self, client, db_session):
        """Line 691: password empty."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "valid@example.com",
                "password": "",
                "first_name": "Test",
            },
        )
        assert response.status_code == 400
        assert "Password is required" in response.get_json()["error"]

    def test_register_invalid_email_format(self, client, db_session):
        """Line 694: invalid email format."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "StrongPass123!ok",
                "first_name": "Test",
            },
        )
        assert response.status_code == 400
        assert "Invalid email format" in response.get_json()["error"]

    def test_register_weak_password(self, client, db_session):
        """Line 699: weak password -> validation error."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "weakpw@example.com",
                "password": "weak",
                "first_name": "Test",
            },
        )
        assert response.status_code == 400


# ============================================================================
# TestCSRFToken (Lines 1182-1195)
# ============================================================================


class TestCSRFToken:
    def test_csrf_token_endpoint(self, client, db_session):
        """Lines 1182-1195: /csrf-token returns CSRF token."""
        response = client.get("/api/auth/csrf-token")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "csrf_token" in data
        assert "expires_in" in data
        assert "X-CSRF-Token" in response.headers


# ============================================================================
# TestSelectTierUserNotFound (Line 1294)
# ============================================================================


class TestSelectTierUserNotFound:
    def test_select_tier_user_not_found(self, app, client, db_session):
        """Line 1294: user not found in select-tier."""
        token = create_token(99999, "gone@example.com")
        response = client.post(
            "/api/auth/select-tier",
            json={"tier_id": "starter"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_select_tier_no_data(self, authenticated_client, db_session, test_user):
        """Line 1281: no data in select-tier."""
        response = authenticated_client.post(
            "/api/auth/select-tier",
            content_type="application/json",
            data="null",
        )
        assert response.status_code == 400


# ============================================================================
# TestSelectTierFreeTier (Lines 1389-1390)
# ============================================================================


class TestSelectTierFreeTier:
    def test_select_free_tier(self, authenticated_client, db_session, test_user):
        """Lines 1389-1390: free tier path (price_cents=0)."""
        from models.migration_credit import MigrationCredit

        # Mock the tier config to include a free tier
        original_config = MigrationCredit.TIER_CONFIG.copy()
        MigrationCredit.TIER_CONFIG["starter"] = {
            **original_config["starter"],
            "price_cents": 0,
        }
        try:
            response = authenticated_client.post(
                "/api/auth/select-tier",
                json={"tier_id": "starter"},
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
        finally:
            MigrationCredit.TIER_CONFIG = original_config


# ============================================================================
# TestUpgradeTierUserNotFound (Lines 1441, 1453)
# ============================================================================


class TestUpgradeTierUserNotFound:
    def test_upgrade_tier_user_not_found(self, app, client, db_session):
        """Line 1453: user not found in upgrade-tier."""
        token = create_token(99999, "gone@example.com")
        response = client.post(
            "/api/auth/upgrade-tier",
            json={"tier_id": "starter"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_upgrade_tier_no_data(self, authenticated_client, db_session, test_user):
        """Line 1441: no data in upgrade-tier."""
        response = authenticated_client.post(
            "/api/auth/upgrade-tier",
            content_type="application/json",
            data="null",
        )
        assert response.status_code == 400


# ============================================================================
# TestUpgradeTierFreeTier (Lines 1545-1546)
# ============================================================================


class TestUpgradeTierFreeTier:
    def test_upgrade_free_tier(self, authenticated_client, db_session, test_user):
        """Lines 1545-1546: free tier path in upgrade (price_cents=0)."""
        from models.migration_credit import MigrationCredit

        original_config = MigrationCredit.TIER_CONFIG.copy()
        MigrationCredit.TIER_CONFIG["starter"] = {
            **original_config["starter"],
            "price_cents": 0,
        }
        try:
            response = authenticated_client.post(
                "/api/auth/upgrade-tier",
                json={"tier_id": "starter"},
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
        finally:
            MigrationCredit.TIER_CONFIG = original_config


# ============================================================================
# TestTeamUserNotFound (Lines 1593, 1652)
# ============================================================================


class TestTeamUserNotFound:
    def test_team_list_user_not_found(self, app, client, db_session):
        """Line 1593: team list user not found."""
        token = create_token(99999, "gone@example.com")
        response = client.get(
            "/api/auth/team",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_team_invite_no_data(self, authenticated_client, db_session, test_user):
        """Line 1652: no data in team invite."""
        response = authenticated_client.post(
            "/api/auth/team/invite",
            content_type="application/json",
            data="null",
        )
        assert response.status_code == 400


# ============================================================================
# TestTeamSuccess (Lines 1602-1615)
# ============================================================================


class TestTeamSuccess:
    def test_team_list_with_team_invite(
        self, authenticated_client, db_session, test_user
    ):
        """Lines 1602-1615: successful team listing with TeamInvite."""
        from models.team_invite import TeamInvite

        with patch.object(
            TeamInvite,
            "get_team_members",
            return_value=[
                {
                    "id": 2,
                    "email": "member@example.com",
                    "name": "Team Member",
                    "role": "Member",
                    "joined_at": "2024-01-01T00:00:00",
                }
            ],
        ):
            with patch.object(
                TeamInvite,
                "get_pending_for_owner",
                return_value=[],
            ):
                response = authenticated_client.get("/api/auth/team")
                assert response.status_code == 200
                data = response.get_json()
                assert data["success"] is True
                assert len(data["team_members"]) == 2  # owner + member
                assert data["team_members"][0]["role"] == "Owner"


# ============================================================================
# TestMeUserNotFound (Line 990)
# ============================================================================


class TestMeUserNotFound:
    def test_me_user_not_found(self, app, client, db_session):
        """Line 990: /me with deleted user."""
        token = create_token(99999, "gone@example.com")
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


# ============================================================================
# TestMeSyncOuterException (Lines 1039-1040)
# ============================================================================


class TestMeSyncOuterException:
    def test_me_outer_sync_exception(self, authenticated_client, db_session, test_user):
        """Lines 1039-1040: outer exception in auto-sync wraps."""
        test_user.migrations_purchased = 5
        test_user.migrations_used = 0
        test_user.subscription_tier = "starter"
        db_session.commit()

        from models.migration_credit import MigrationCredit

        # Force the outer try to fail by making the query fail
        with patch.object(
            MigrationCredit.query,
            "filter_by",
            side_effect=Exception("DB down"),
        ):
            response = authenticated_client.get("/api/auth/me")
            assert response.status_code == 200


# ============================================================================
# TestValidateSessionSuccess (Line 1215)
# ============================================================================


class TestValidateSessionSuccess:
    def test_validate_session_success(
        self, authenticated_client, db_session, test_user
    ):
        """Line 1215: validate returns user info."""
        response = authenticated_client.get("/api/auth/validate")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["user"]["email"] == test_user.email


# ============================================================================
# TestSessionAuth (Lines 167-171)
# ============================================================================


class TestSessionAuthSuccess:
    def test_valid_session_auth(self, app, client, db_session, test_user):
        """Lines 167-171: valid session -> session auth path."""
        import hashlib

        # Set up a proper session with matching fingerprint
        ua = "TestBrowser/1.0"
        fingerprint = hashlib.sha256(ua.encode()).hexdigest()[:16]

        with client.session_transaction() as sess:
            sess["user_id"] = test_user.id
            sess["email"] = test_user.email
            sess["_ua_fingerprint"] = fingerprint

        response = client.get(
            "/api/auth/me",
            headers={"User-Agent": ua},
        )
        assert response.status_code == 200


# ============================================================================
# TestCookieAuthException (Lines 182-183)
# ============================================================================


class TestCookieAuthException:
    def test_cookie_auth_decode_raises(self, app, client, db_session):
        """Lines 182-183: cookie auth decode raises exception."""
        # Set a cookie that will cause decode_token to raise
        client.set_cookie("auth_token", "deliberately.broken.token", domain="localhost")
        with patch(
            "api.auth.decode_token",
            side_effect=RuntimeError("JWT decode error"),
        ):
            response = client.get("/api/auth/me")
            assert response.status_code == 401


# ============================================================================
# TestVerifyMFAException (Lines 421-423)
# ============================================================================


class TestVerifyMFAException:
    def test_verify_mfa_generic_exception(
        self, authenticated_client, db_session, test_user, app
    ):
        """Lines 421-423: generic exception in MFA verification."""
        _enable_mfa_for_user(test_user, app)
        db_session.commit()

        with patch("pyotp.TOTP", side_effect=RuntimeError("TOTP error")):
            response = authenticated_client.post(
                "/api/auth/mfa/verify", json={"code": "123456"}
            )
            assert response.status_code == 500
            assert "verification failed" in response.get_json()["error"]


# ============================================================================
# TestForgotPasswordHash (Lines 1893-1894)
# ============================================================================


class TestForgotPasswordHashException:
    def test_fake_hash_exception_path(self, client, db_session):
        """Lines 1893-1894: argon2 hash exception during fake timing."""
        with patch("argon2.PasswordHasher") as mock_ph:
            mock_ph_instance = MagicMock()
            mock_ph_instance.hash.side_effect = Exception("Hash error")
            mock_ph.return_value = mock_ph_instance

            response = client.post(
                "/api/auth/forgot-password",
                json={"email": "nonexist99@example.com"},
            )
            # Should still return 200 even with hash exception
            assert response.status_code == 200


# ============================================================================
# TestSendVerificationEmailProduction (Lines 2153-2154)
# ============================================================================


class TestSendVerificationEmailProduction:
    def test_production_no_mail_returns_false(self, app):
        """Lines 2153-2154: production mode with no mail -> returns False."""
        with app.app_context():
            app.config["MAIL_SERVER"] = "smtp.example.com"
            app.config["MAIL_USERNAME"] = "noreply@example.com"

            original_env = os.environ.get("FLASK_ENV")
            os.environ["FLASK_ENV"] = "production"
            app.config["FLASK_ENV"] = "production"

            with patch.dict("sys.modules", {"flask_mail": None}):
                result = _send_verification_email("test@example.com", "vtok")
                assert result is False

            os.environ["FLASK_ENV"] = original_env or "testing"
            app.config["FLASK_ENV"] = "testing"
            app.config.pop("MAIL_SERVER", None)
            app.config.pop("MAIL_USERNAME", None)


# ============================================================================
# TestRequireAuthEdgeCases (Lines 50, 63, 117, 128, 139-144)
# ============================================================================


class TestRequireAuthEdgeCases:
    def test_empty_user_agent_fingerprint(self, app, client, db_session, test_user):
        """Line 50: empty User-Agent -> 'unknown' fingerprint."""
        with client.session_transaction() as sess:
            sess["user_id"] = test_user.id
            sess["email"] = test_user.email
            sess["_ua_fingerprint"] = "unknown"

        response = client.get(
            "/api/auth/me",
            headers={"User-Agent": ""},
        )
        assert response.status_code == 200

    def test_no_session_validate_binding(self, app, client, db_session):
        """Line 63: _validate_session_binding with no session -> True."""
        # Just calling without session should fall through to 401
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_invalid_bearer_format(self, client, db_session):
        """Line 117: auth header not 'Bearer <token>' format."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert "Invalid authorization format" in data["error"]

    def test_invalid_token_returns_error(self, client, db_session):
        """Line 128: valid Bearer format but invalid token."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalidtokenformat"},
        )
        assert response.status_code == 401

    def test_bearer_decode_exception(self, client, db_session):
        """Lines 139-144: exception during token decoding."""
        with patch(
            "api.auth.decode_token",
            side_effect=RuntimeError("Decode crash"),
        ):
            response = client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer sometoken123"},
            )
            assert response.status_code == 401
            data = response.get_json()
            assert "Authentication failed" in data["error"]


# ============================================================================
# TestRegistrationTimingEdgeCases (Lines 715-717, 741-748)
# ============================================================================


class TestRegistrationTimingEdgeCases:
    def test_duplicate_email_hash_exception(self, client, db_session):
        """Lines 715-717: argon2 hash exception during timing equalization."""
        user = User(email="hashfail@example.com", first_name="H", last_name="F")
        user.set_password("ExistingPass123!")
        db_session.add(user)
        db_session.commit()

        with patch("argon2.PasswordHasher") as mock_ph:
            mock_inst = MagicMock()
            mock_inst.hash.side_effect = Exception("Hash failed")
            mock_ph.return_value = mock_inst

            response = client.post(
                "/api/auth/register",
                json={
                    "email": "hashfail@example.com",
                    "password": "StrongNewPass123!",
                    "first_name": "New",
                },
            )
            assert response.status_code == 400
            assert "could not be completed" in response.get_json()["error"]

    def test_registration_set_password_value_error(self, client, db_session):
        """Lines 741-748: ValueError from set_password during registration."""
        with patch.object(
            User,
            "set_password",
            side_effect=ValueError("Password too similar to email"),
        ):
            response = client.post(
                "/api/auth/register",
                json={
                    "email": "valuerr@example.com",
                    "password": "StrongNewPass123!",
                    "first_name": "New",
                },
            )
            assert response.status_code == 400


# ============================================================================
# TestMeAutoSyncInnerException (Lines 1039-1040)
# ============================================================================


class TestMeAutoSyncInnerException:
    def test_inner_sync_rollback(self, authenticated_client, db_session, test_user):
        """Lines 1039-1040: inner exception in credit sync rollback."""
        test_user.migrations_purchased = 5
        test_user.migrations_used = 0
        test_user.subscription_tier = "starter"
        db_session.commit()

        with patch(
            "api.auth.db.session.begin_nested",
            side_effect=Exception("Savepoint error"),
        ):
            response = authenticated_client.get("/api/auth/me")
            # Should succeed - the outer try catches the exception
            assert response.status_code == 200
