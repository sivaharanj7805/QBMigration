"""
License API Unit Tests
Tests for license validation, activation, usage tracking endpoints
"""

import pytest
import json
from datetime import datetime, timedelta


class TestLicenseAPI:
    """Test suite for license API endpoints"""

    def test_license_creation(self, authenticated_client, db_session):
        """Test admin license creation"""
        from models.license import License

        # Create a license directly
        license = License.create_license(
            tier="professional",
            user_email="customer@example.com",
            order_id="TEST-ORDER-001",
        )
        db_session.add(license)
        db_session.commit()

        assert license.license_key is not None
        assert license.license_key.startswith("FB-")
        assert license.tier == "professional"
        assert license.migrations_allowed == 50
        assert license.migrations_used == 0

    def test_license_key_format(self, db_session):
        """Test license key format is correct"""
        from models.license import License

        license = License.create_license(tier="starter")

        # Format: FB-XXXX-XXXX-XXXX-XXXX
        assert len(license.license_key) == 22
        parts = license.license_key.split("-")
        assert len(parts) == 5
        assert parts[0] == "FB"
        for part in parts[1:]:
            assert len(part) == 4
            assert part.isalnum()

    def test_license_validate_invalid_key(self, client, db_session):
        """Test validation with invalid license key"""
        response = client.post(
            "/api/license/validate",
            json={
                "license_key": "FB-INVALID-KEY-0000-0000",
                "hardware_fingerprint": "test-fingerprint-hash",
            },
        )

        assert response.status_code == 404
        data = json.loads(response.data)
        assert data["valid"] == False
        assert "Invalid license key" in data["error"]

    def test_license_validate_missing_fingerprint(self, client, db_session):
        """Test validation without hardware fingerprint"""
        response = client.post(
            "/api/license/validate", json={"license_key": "FB-TEST-XXXX-YYYY-ZZZZ"}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["valid"] == False

    def test_license_activation_success(self, client, db_session):
        """Test successful license activation"""
        from models.license import License

        # Create a license
        license = License.create_license(tier="starter")
        db_session.add(license)
        db_session.commit()

        fingerprint = "test-hardware-fingerprint-12345"

        response = client.post(
            "/api/license/activate",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": fingerprint,
            },
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] == True
        assert "token" in data

        # Verify license is now activated
        db_session.refresh(license)
        assert license.is_activated == True
        assert license.hardware_fingerprint == fingerprint

    def test_license_activation_different_hardware(self, client, db_session):
        """Test that license cannot be activated on different hardware"""
        from models.license import License

        # Create and activate a license
        license = License.create_license(tier="starter")
        license.activate("original-fingerprint-12345")
        db_session.add(license)
        db_session.commit()

        # Try to activate on different hardware
        response = client.post(
            "/api/license/activate",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": "different-fingerprint-67890",
            },
        )

        assert response.status_code == 409
        data = json.loads(response.data)
        assert data["success"] == False
        assert "already activated" in data["error"].lower()

    def test_license_validate_activated(self, client, db_session):
        """Test validation of activated license"""
        from models.license import License

        # Create and activate a license
        fingerprint = "test-fingerprint-abc123"
        license = License.create_license(tier="professional")
        license.activate(fingerprint)
        db_session.add(license)
        db_session.commit()

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": fingerprint,
            },
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["valid"] == True
        assert data["tier"] == "professional"
        assert data["migrations_remaining"] == 50
        assert "token" in data

    def test_license_validate_wrong_hardware(self, client, db_session):
        """Test validation fails with wrong hardware fingerprint"""
        from models.license import License

        # Create and activate a license
        license = License.create_license(tier="starter")
        license.activate("original-fingerprint")
        db_session.add(license)
        db_session.commit()

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": "different-fingerprint",
            },
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data["valid"] == False
        assert "different machine" in data["error"].lower()

    def test_license_use_migration(self, client, db_session):
        """Test migration usage decrements count"""
        from models.license import License

        # Create and activate a license
        fingerprint = "test-fingerprint"
        license = License.create_license(tier="starter")
        license.activate(fingerprint)
        db_session.add(license)
        db_session.commit()

        initial_remaining = license.get_migrations_remaining()

        response = client.post(
            "/api/license/use-migration",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": fingerprint,
                "migration_id": "test-migration-uuid",
            },
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] == True
        assert data["migrations_remaining"] == initial_remaining - 1

    def test_license_exhausted(self, client, db_session):
        """Test that license with no migrations remaining fails validation"""
        from models.license import License

        # Create a license with no migrations remaining
        fingerprint = "test-fingerprint"
        license = License.create_license(tier="starter")
        license.activate(fingerprint)
        license.migrations_used = 10  # Use all migrations
        db_session.add(license)
        db_session.commit()

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": fingerprint,
            },
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data["valid"] == False
        assert "no migrations remaining" in data["error"].lower()

    def test_license_revoked(self, client, db_session):
        """Test that revoked license fails validation"""
        from models.license import License

        # Create and revoke a license
        fingerprint = "test-fingerprint"
        license = License.create_license(tier="starter")
        license.activate(fingerprint)
        license.revoke("Test revocation", "admin@example.com")
        db_session.add(license)
        db_session.commit()

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": fingerprint,
            },
        )

        assert response.status_code == 404  # find_by_key filters out revoked

    def test_license_expired(self, client, db_session):
        """Test that expired license fails validation"""
        from models.license import License

        # Create an expired license
        fingerprint = "test-fingerprint"
        license = License.create_license(
            tier="starter", expires_in_days=-1
        )  # Already expired
        license.activate(fingerprint)
        db_session.add(license)
        db_session.commit()

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": fingerprint,
            },
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data["valid"] == False
        assert "expired" in data["error"].lower()

    def test_enterprise_unlimited_migrations(self, client, db_session):
        """Test enterprise tier has unlimited migrations"""
        from models.license import License

        fingerprint = "test-fingerprint"
        license = License.create_license(tier="enterprise")
        license.activate(fingerprint)
        db_session.add(license)
        db_session.commit()

        # Use 100 migrations
        for _ in range(100):
            license.use_migration()

        db_session.commit()

        # Should still have migrations remaining
        assert license.has_migrations_remaining() == True
        assert license.get_migrations_remaining() == -1  # Unlimited indicator

        response = client.post(
            "/api/license/validate",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": fingerprint,
            },
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["valid"] == True
        assert data["is_unlimited"] == True

    def test_license_usage_endpoint(self, client, db_session):
        """Test usage endpoint returns correct counts"""
        from models.license import License

        fingerprint = "test-fingerprint"
        license = License.create_license(tier="professional")
        license.activate(fingerprint)
        license.migrations_used = 10
        db_session.add(license)
        db_session.commit()

        response = client.post(
            "/api/license/usage",
            json={
                "license_key": license.license_key,
                "hardware_fingerprint": fingerprint,
            },
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["tier"] == "professional"
        assert data["migrations_allowed"] == 50
        assert data["migrations_used"] == 10
        assert data["migrations_remaining"] == 40


class TestLicenseModel:
    """Unit tests for License model methods"""

    def test_generate_key_unique(self, db_session):
        """Test that generated keys are unique"""
        from models.license import License

        keys = set()
        for _ in range(100):
            key = License.generate_license_key()
            assert key not in keys
            keys.add(key)

    def test_hash_key_consistent(self, db_session):
        """Test that key hashing is consistent"""
        from models.license import License

        key = "FB-TEST-XXXX-YYYY-ZZZZ"
        hash1 = License.hash_license_key(key)
        hash2 = License.hash_license_key(key)
        hash3 = License.hash_license_key(key.lower())  # Should normalize

        assert hash1 == hash2
        assert hash1 == hash3  # Case insensitive

    def test_tier_migrations(self, db_session):
        """Test that tiers have correct migration counts"""
        from models.license import License

        starter = License.create_license(tier="starter")
        professional = License.create_license(tier="professional")
        enterprise = License.create_license(tier="enterprise")

        assert starter.migrations_allowed == 10
        assert professional.migrations_allowed == 50
        assert enterprise.migrations_allowed == -1  # Unlimited

    def test_add_migrations(self, db_session):
        """Test adding migrations to a license"""
        from models.license import License

        license = License.create_license(tier="starter")
        assert license.migrations_allowed == 10

        license.add_migrations(5)
        assert license.migrations_allowed == 15

    def test_to_dict(self, db_session):
        """Test license serialization"""
        from models.license import License

        license = License.create_license(
            tier="professional", user_email="test@example.com"
        )

        data = license.to_dict()
        assert "id" in data
        assert data["tier"] == "professional"
        assert "license_key" not in data  # Should not include sensitive data

        data_sensitive = license.to_dict(include_sensitive=True)
        assert "license_key" in data_sensitive
        assert "user_email" in data_sensitive


class TestLicenseActivation:
    """Tests for LicenseActivation audit logging"""

    def test_activation_logged(self, db_session):
        """Test that activation creates audit log"""
        from models.license import License, LicenseActivation

        license = License.create_license(tier="starter")
        db_session.add(license)
        db_session.commit()

        license.activate("test-fingerprint")
        db_session.commit()

        activations = LicenseActivation.query.filter_by(license_id=license.id).all()
        assert len(activations) == 1
        assert activations[0].action == "activate"
        assert activations[0].success == True

    def test_deactivation_logged(self, db_session):
        """Test that deactivation creates audit log"""
        from models.license import License, LicenseActivation

        license = License.create_license(tier="starter")
        license.activate("test-fingerprint")
        db_session.add(license)
        db_session.commit()

        license.deactivate(reason="Test", admin_email="admin@example.com")
        db_session.commit()

        activations = LicenseActivation.query.filter_by(
            license_id=license.id, action="deactivate"
        ).all()
        assert len(activations) == 1
