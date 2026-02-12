"""
Test for CRITICAL FIX A16: Session/JWT Invalidation on Password Change

This test verifies that when a user changes their password, all previously
issued JWT tokens and active sessions are automatically invalidated.

Security Impact: Prevents stolen tokens from being used after password change.
"""

import datetime
import time
from datetime import timezone

import pytest
from api.auth import create_token, decode_token
from models.user import User


class TestPasswordChangeInvalidation:
    """Test suite for password change invalidation fix"""

    def test_jwt_invalidated_after_password_change(self, app, db_session):
        """Test that JWT tokens issued before password change are rejected"""
        with app.app_context():
            # Create a user
            user = User(email="test@example.com", first_name="Test", last_name="User")
            user.set_password("OldPassword123!")
            db_session.add(user)
            db_session.commit()
            initial_password_changed_at = user.password_changed_at

            # Create a JWT token (simulating login)
            token = create_token(user.id, user.email, expires_hours=24)

            # Verify token is valid
            payload = decode_token(token)
            assert payload is not None
            assert payload["user_id"] == user.id
            assert payload["email"] == user.email

            # Small delay to ensure password_changed_at timestamp differs
            time.sleep(0.1)

            # Change password
            user.set_password("NewPassword456!")
            db_session.commit()

            # Verify password_changed_at was updated
            assert user.password_changed_at > initial_password_changed_at

            # CRITICAL: Token should now be invalid
            payload = decode_token(token)
            assert (
                payload is None
            ), "Token should be invalid after password change, but it's still valid!"

    def test_jwt_valid_after_password_change_if_issued_after(self, app, db_session):
        """Test that JWT tokens issued AFTER password change remain valid"""
        with app.app_context():
            # Create a user
            user = User(
                email="test2@example.com", first_name="Test", last_name="User"
            )
            user.set_password("OldPassword123!")
            db_session.add(user)
            db_session.commit()

            # Change password
            time.sleep(0.1)
            user.set_password("NewPassword456!")
            db_session.commit()

            # Create a JWT token AFTER password change (simulating new login)
            time.sleep(0.1)
            token = create_token(user.id, user.email, expires_hours=24)

            # Token should be valid
            payload = decode_token(token)
            assert payload is not None
            assert payload["user_id"] == user.id

    def test_session_invalidated_after_password_change(self, client, app, db_session):
        """Test that active sessions are invalidated after password change"""
        with app.app_context():
            # Register and login
            client.post(
                "/api/auth/register",
                json={
                    "email": "session_test@example.com",
                    "password": "OldPassword123!",
                    "first_name": "Session",
                    "last_name": "Test",
                },
            )

            login_response = client.post(
                "/api/auth/login",
                json={"email": "session_test@example.com", "password": "OldPassword123!"},
            )
            assert login_response.status_code == 200

            # Access protected endpoint (should work)
            response = client.get("/api/auth/me")
            assert response.status_code == 200

            # Change password (would need a change-password endpoint)
            user = User.query.filter_by(email="session_test@example.com").first()
            time.sleep(0.1)
            user.set_password("NewPassword456!")
            db_session.commit()

            # Access protected endpoint again (should fail)
            response = client.get("/api/auth/me")
            assert response.status_code == 401
            data = response.get_json()
            assert data["session_invalid"] is True
            assert "password change" in data["error"].lower()

    def test_multiple_devices_all_invalidated(self, app, db_session):
        """Test that password change invalidates tokens on ALL devices"""
        with app.app_context():
            # Create a user
            user = User(
                email="multidevice@example.com", first_name="Multi", last_name="Device"
            )
            user.set_password("OldPassword123!")
            db_session.add(user)
            db_session.commit()

            # Simulate login from 3 different devices
            token_device1 = create_token(user.id, user.email, expires_hours=24)
            token_device2 = create_token(user.id, user.email, expires_hours=24)
            token_device3 = create_token(user.id, user.email, expires_hours=24)

            # All tokens should be valid
            assert decode_token(token_device1) is not None
            assert decode_token(token_device2) is not None
            assert decode_token(token_device3) is not None

            # Change password (simulating user changing password from device 1)
            time.sleep(0.1)
            user.set_password("NewPassword456!")
            db_session.commit()

            # ALL tokens should now be invalid
            assert (
                decode_token(token_device1) is None
            ), "Device 1 token should be invalid"
            assert (
                decode_token(token_device2) is None
            ), "Device 2 token should be invalid"
            assert (
                decode_token(token_device3) is None
            ), "Device 3 token should be invalid"

    def test_token_without_iat_still_works(self, app, db_session):
        """Test backward compatibility: tokens without iat claim still work (legacy)"""
        with app.app_context():
            import jwt

            from api.auth import _get_jwt_signing_key

            user = User(
                email="legacy@example.com", first_name="Legacy", last_name="User"
            )
            user.set_password("Password123!")
            db_session.add(user)
            db_session.commit()

            # Create a legacy token without iat claim (pre-fix tokens)
            legacy_payload = {
                "user_id": user.id,
                "email": user.email,
                "exp": datetime.datetime.now(timezone.utc)
                + datetime.timedelta(hours=24),
                # No 'iat' claim
            }
            legacy_token = jwt.encode(
                legacy_payload, _get_jwt_signing_key(), algorithm="HS256"
            )

            # Should still work (gracefully handle missing iat)
            payload = decode_token(legacy_token)
            assert (
                payload is not None
            ), "Legacy token without iat should still work for backward compatibility"

    def test_password_reset_invalidates_all_tokens(self, app, db_session):
        """Test that password reset via forgot-password also invalidates tokens"""
        with app.app_context():
            # Create user and get a valid token
            user = User(email="reset@example.com", first_name="Reset", last_name="User")
            user.set_password("OldPassword123!")
            db_session.add(user)
            db_session.commit()

            old_token = create_token(user.id, user.email, expires_hours=24)
            assert decode_token(old_token) is not None

            # Simulate password reset
            time.sleep(0.1)
            user.set_password("NewResetPassword456!")
            db_session.commit()

            # Old token should be invalid
            assert decode_token(old_token) is None


# Fixtures


@pytest.fixture
def app():
    """Create Flask app for testing"""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    return app


@pytest.fixture
def db_session(app):
    """Create database session"""
    from models.database import db

    with app.app_context():
        db.create_all()
        yield db.session
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()
