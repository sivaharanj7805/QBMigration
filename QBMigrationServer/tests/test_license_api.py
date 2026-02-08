"""Tests for api/license_api.py - license validation, activation, usage endpoints."""

from models.license import License


class TestValidateLicense:
    """Tests for POST /api/license/validate."""

    def test_validate_no_data(self, client, db_session):
        response = client.post(
            "/api/license/validate",
            data="",
            content_type="application/json",
        )
        assert response.status_code in (400, 500)

    def test_validate_missing_license_key(self, client, db_session):
        response = client.post(
            "/api/license/validate",
            json={"hardware_fingerprint": "test-fp"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["valid"] is False

    def test_validate_missing_fingerprint(self, client, db_session):
        response = client.post(
            "/api/license/validate",
            json={"license_key": "FB-TEST-KEY1-KEY2-KEY3"},
        )
        assert response.status_code == 400

    def test_validate_nonexistent_key(self, client, db_session):
        response = client.post(
            "/api/license/validate",
            json={
                "license_key": "FB-FAKE-FAKE-FAKE-FAKE",
                "hardware_fingerprint": "test-fp-123",
            },
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["valid"] is False

    def test_validate_valid_license(self, client, db_session, test_user):
        # Create a license
        license_obj = License.create_license(
            tier="professional", user_email=test_user.email
        )
        db_session.add(license_obj)
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": key,
                "hardware_fingerprint": "test-hardware-fp-abc",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["valid"] is True
        assert data["tier"] == "professional"
        assert "token" in data

    def test_validate_revoked_license(self, client, db_session, test_user):
        license_obj = License.create_license(tier="starter", user_email=test_user.email)
        db_session.add(license_obj)
        db_session.commit()
        key = license_obj.license_key

        # Revoke it
        license_obj.revoke(reason="Test revocation", revoked_by="admin@test.com")
        db_session.commit()

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": key,
                "hardware_fingerprint": "test-fp",
            },
        )
        # find_by_key filters out revoked, so 404
        assert response.status_code == 404

    def test_validate_expired_license(self, client, db_session, test_user):
        from datetime import datetime, timedelta, timezone

        license_obj = License.create_license(tier="starter", user_email=test_user.email)
        license_obj.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db_session.add(license_obj)
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": key,
                "hardware_fingerprint": "test-fp",
            },
        )
        assert response.status_code == 403

    def test_validate_wrong_hardware(self, client, db_session, test_user):
        license_obj = License.create_license(
            tier="professional", user_email=test_user.email
        )
        db_session.add(license_obj)
        db_session.commit()

        # Activate on specific hardware
        license_obj.activate("original-hardware-fp")
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": key,
                "hardware_fingerprint": "different-hardware-fp",
            },
        )
        assert response.status_code == 403

    def test_validate_exhausted_migrations(self, client, db_session, test_user):
        license_obj = License.create_license(tier="starter", user_email=test_user.email)
        db_session.add(license_obj)
        db_session.commit()

        # Use all migrations
        license_obj.migrations_used = license_obj.migrations_allowed
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": key,
                "hardware_fingerprint": "test-fp",
            },
        )
        assert response.status_code == 403


class TestActivateLicense:
    """Tests for POST /api/license/activate."""

    def test_activate_no_data(self, client, db_session):
        response = client.post(
            "/api/license/activate",
            data="",
            content_type="application/json",
        )
        assert response.status_code in (400, 500)

    def test_activate_missing_key(self, client, db_session):
        response = client.post(
            "/api/license/activate",
            json={"hardware_fingerprint": "test-fp"},
        )
        assert response.status_code == 400

    def test_activate_missing_fingerprint(self, client, db_session):
        response = client.post(
            "/api/license/activate",
            json={"license_key": "FB-TEST-TEST-TEST-TEST"},
        )
        assert response.status_code == 400

    def test_activate_nonexistent(self, client, db_session):
        response = client.post(
            "/api/license/activate",
            json={
                "license_key": "FB-FAKE-FAKE-FAKE-FAKE",
                "hardware_fingerprint": "test-fp",
            },
        )
        assert response.status_code == 404

    def test_activate_success(self, client, db_session, test_user):
        license_obj = License.create_license(
            tier="professional", user_email=test_user.email
        )
        db_session.add(license_obj)
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/activate",
            json={
                "license_key": key,
                "hardware_fingerprint": "new-hardware-fp",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "token" in data

    def test_activate_revoked(self, client, db_session, test_user):
        license_obj = License.create_license(tier="starter", user_email=test_user.email)
        db_session.add(license_obj)
        db_session.commit()
        key = license_obj.license_key
        license_obj.revoke(reason="Test", revoked_by="admin@test.com")
        db_session.commit()

        response = client.post(
            "/api/license/activate",
            json={
                "license_key": key,
                "hardware_fingerprint": "test-fp",
            },
        )
        # find_by_key filters revoked - 404
        assert response.status_code == 404

    def test_activate_expired(self, client, db_session, test_user):
        from datetime import datetime, timedelta, timezone

        license_obj = License.create_license(tier="starter", user_email=test_user.email)
        license_obj.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db_session.add(license_obj)
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/activate",
            json={
                "license_key": key,
                "hardware_fingerprint": "test-fp",
            },
        )
        assert response.status_code == 403

    def test_activate_different_hardware(self, client, db_session, test_user):
        license_obj = License.create_license(
            tier="professional", user_email=test_user.email
        )
        db_session.add(license_obj)
        db_session.commit()

        # First activation
        license_obj.activate("first-hardware")
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/activate",
            json={
                "license_key": key,
                "hardware_fingerprint": "second-hardware",
            },
        )
        assert response.status_code == 409


class TestLicenseUsage:
    """Tests for POST /api/license/usage."""

    def test_usage_no_data(self, client, db_session):
        response = client.post(
            "/api/license/usage",
            data="",
            content_type="application/json",
        )
        assert response.status_code in (400, 500)

    def test_usage_missing_fields(self, client, db_session):
        response = client.post(
            "/api/license/usage",
            json={"license_key": "FB-TEST-TEST-TEST-TEST"},
        )
        assert response.status_code == 400

    def test_usage_nonexistent(self, client, db_session):
        response = client.post(
            "/api/license/usage",
            json={
                "license_key": "FB-FAKE-FAKE-FAKE-FAKE",
                "hardware_fingerprint": "test-fp",
            },
        )
        assert response.status_code == 404

    def test_usage_success(self, client, db_session, test_user):
        license_obj = License.create_license(
            tier="professional", user_email=test_user.email
        )
        db_session.add(license_obj)
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/usage",
            json={
                "license_key": key,
                "hardware_fingerprint": "test-fp",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["tier"] == "professional"
        assert "migrations_remaining" in data


class TestUseMigration:
    """Tests for POST /api/license/use-migration."""

    def test_use_migration_no_data(self, client, db_session):
        response = client.post(
            "/api/license/use-migration",
            data="",
            content_type="application/json",
        )
        assert response.status_code in (400, 500)

    def test_use_migration_missing_fields(self, client, db_session):
        response = client.post(
            "/api/license/use-migration",
            json={"license_key": "FB-TEST-TEST-TEST-TEST"},
        )
        assert response.status_code == 400

    def test_use_migration_nonexistent(self, client, db_session):
        response = client.post(
            "/api/license/use-migration",
            json={
                "license_key": "FB-FAKE-FAKE-FAKE-FAKE",
                "hardware_fingerprint": "test-fp",
            },
        )
        assert response.status_code == 404

    def test_use_migration_success(self, client, db_session, test_user):
        license_obj = License.create_license(
            tier="professional", user_email=test_user.email
        )
        db_session.add(license_obj)
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/use-migration",
            json={
                "license_key": key,
                "hardware_fingerprint": "test-fp",
                "migration_id": "test-migration-123",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "migrations_remaining" in data

    def test_use_migration_exhausted(self, client, db_session, test_user):
        license_obj = License.create_license(tier="starter", user_email=test_user.email)
        db_session.add(license_obj)
        db_session.commit()

        # Exhaust all migrations
        license_obj.migrations_used = license_obj.migrations_allowed
        db_session.commit()
        key = license_obj.license_key

        response = client.post(
            "/api/license/use-migration",
            json={
                "license_key": key,
                "hardware_fingerprint": "test-fp",
                "migration_id": "test-migration-456",
            },
        )
        assert response.status_code == 403


class TestLicenseAdminEndpoints:
    """Tests for admin-only license endpoints."""

    def test_create_license_requires_auth(self, client, db_session):
        response = client.post(
            "/api/license/create",
            json={"tier": "starter"},
        )
        assert response.status_code in (401, 302)

    def test_deactivate_requires_auth(self, client, db_session):
        response = client.post(
            "/api/license/deactivate",
            json={"license_key": "FB-TEST-TEST-TEST-TEST"},
        )
        assert response.status_code in (401, 302)

    def test_revoke_requires_auth(self, client, db_session):
        response = client.post(
            "/api/license/revoke",
            json={"license_key": "FB-TEST-TEST-TEST-TEST"},
        )
        assert response.status_code in (401, 302)

    def test_list_requires_auth(self, client, db_session):
        response = client.get("/api/license/list")
        assert response.status_code in (401, 302)

    def test_history_requires_auth(self, client, db_session):
        response = client.get("/api/license/1/history")
        assert response.status_code in (401, 302)

    def test_create_non_admin(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/license/create",
            json={"tier": "starter"},
        )
        assert response.status_code == 403

    def test_list_non_admin(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/license/list")
        assert response.status_code == 403

    def test_deactivate_non_admin(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/license/deactivate",
            json={"license_key": "FB-TEST-TEST-TEST-TEST"},
        )
        assert response.status_code == 403

    def test_revoke_non_admin(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/license/revoke",
            json={"license_key": "FB-TEST-TEST-TEST-TEST"},
        )
        assert response.status_code == 403
