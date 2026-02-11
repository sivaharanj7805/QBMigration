"""Tests for admin endpoints in api/license_api.py.

Covers POST /api/license/create, POST /api/license/deactivate,
POST /api/license/revoke, GET /api/license/list,
and GET /api/license/<int:license_id>/history.
(Lines 491-530, 546-578, 594-623, 631-667, 675-694)
"""

import pytest
from models.license import License


@pytest.fixture(autouse=True)
def set_admin_user(test_user, db_session):
    """Set test_user to admin role so admin_required decorator grants access."""
    test_user.role = "admin"
    db_session.commit()
    return test_user


def _create_license(db_session, tier="professional", user_email="customer@example.com"):
    """Create a license in the database and return the committed object."""
    license_obj = License.create_license(
        tier=tier,
        user_email=user_email,
        order_id="ORDER-TEST-001",
        expires_in_days=365,
    )
    db_session.add(license_obj)
    db_session.commit()
    db_session.refresh(license_obj)
    return license_obj


class TestCreateLicense:
    """Tests for POST /api/license/create (admin only)."""

    def test_create_license_success(self, authenticated_client, db_session):
        """Admin can create a license with valid tier, email, and order_id."""
        response = authenticated_client.post(
            "/api/license/create",
            json={
                "tier": "professional",
                "user_email": "buyer@example.com",
                "order_id": "ORD-001",
                "expires_in_days": 365,
            },
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["success"] is True
        assert "license" in data
        assert data["license"]["tier"] == "professional"
        assert data["license"]["license_key"].startswith("FB-")
        assert data["license"]["user_email"] == "buyer@example.com"
        assert data["license"]["order_id"] == "ORD-001"

    def test_create_license_default_tier(self, authenticated_client, db_session):
        """When tier is omitted the endpoint defaults to starter."""
        response = authenticated_client.post(
            "/api/license/create",
            json={"user_email": "default@example.com", "order_id": "ORD-DEF"},
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["license"]["tier"] == "starter"

    def test_create_license_no_data(self, authenticated_client, db_session):
        """POST with empty body triggers the generic exception handler."""
        response = authenticated_client.post(
            "/api/license/create",
            data="",
            content_type="application/json",
        )
        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False

    def test_create_license_invalid_tier(self, authenticated_client, db_session):
        """POST with an invalid tier returns 400 via ValueError."""
        response = authenticated_client.post(
            "/api/license/create",
            json={"tier": "nonexistent_tier"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "error" in data

    def test_create_license_unauthenticated(self, client, db_session):
        """Unauthenticated request is rejected."""
        response = client.post(
            "/api/license/create",
            json={"tier": "starter"},
        )
        assert response.status_code in (401, 302)


class TestDeactivateLicense:
    """Tests for POST /api/license/deactivate (admin only)."""

    def test_deactivate_license_success(self, authenticated_client, db_session):
        """Admin can deactivate an activated license for transfer."""
        license_obj = _create_license(db_session)
        license_obj.activate("hardware-fp-abc")
        db_session.commit()

        response = authenticated_client.post(
            "/api/license/deactivate",
            json={
                "license_key": license_obj.license_key,
                "reason": "Customer requested transfer",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "message" in data

    def test_deactivate_license_not_found(self, authenticated_client, db_session):
        """Deactivating a nonexistent license returns 404."""
        response = authenticated_client.post(
            "/api/license/deactivate",
            json={
                "license_key": "FB-FAKE-FAKE-FAKE-FAKE",
                "reason": "Test",
            },
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False

    def test_deactivate_no_key(self, authenticated_client, db_session):
        """POST without license_key returns 400."""
        response = authenticated_client.post(
            "/api/license/deactivate",
            json={"reason": "No key provided"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False


class TestRevokeLicense:
    """Tests for POST /api/license/revoke (admin only)."""

    def test_revoke_license_success(self, authenticated_client, db_session):
        """Admin can permanently revoke a license."""
        license_obj = _create_license(db_session)

        response = authenticated_client.post(
            "/api/license/revoke",
            json={
                "license_key": license_obj.license_key,
                "reason": "Chargeback",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "revoked" in data["message"].lower()

    def test_revoke_not_found(self, authenticated_client, db_session):
        """Revoking a nonexistent license returns 404."""
        response = authenticated_client.post(
            "/api/license/revoke",
            json={
                "license_key": "FB-NONE-NONE-NONE-NONE",
                "reason": "Test",
            },
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False

    def test_revoke_no_key(self, authenticated_client, db_session):
        """POST without license_key returns 400."""
        response = authenticated_client.post(
            "/api/license/revoke",
            json={"reason": "Missing key"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False


class TestListLicenses:
    """Tests for GET /api/license/list (admin only)."""

    def test_list_licenses(self, authenticated_client, db_session):
        """Admin can list all active licenses with pagination metadata."""
        _create_license(db_session, tier="professional")
        _create_license(db_session, tier="starter", user_email="other@example.com")

        response = authenticated_client.get("/api/license/list")
        assert response.status_code == 200
        data = response.get_json()
        assert "licenses" in data
        assert isinstance(data["licenses"], list)
        assert data["total"] >= 2
        assert "page" in data
        assert "pages" in data

    def test_list_licenses_with_filters(self, authenticated_client, db_session):
        """Admin can filter licenses by tier and active_only."""
        _create_license(db_session, tier="professional")
        _create_license(db_session, tier="starter", user_email="other@example.com")

        response = authenticated_client.get(
            "/api/license/list?tier=professional&active_only=true"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "licenses" in data
        for lic in data["licenses"]:
            assert lic["tier"] == "professional"


class TestLicenseHistory:
    """Tests for GET /api/license/<int:license_id>/history (admin only)."""

    def test_get_license_history(self, authenticated_client, db_session):
        """Admin can view activation history for a license."""
        license_obj = _create_license(db_session)

        response = authenticated_client.get(f"/api/license/{license_obj.id}/history")
        assert response.status_code == 200
        data = response.get_json()
        assert "license" in data
        assert "history" in data
        assert isinstance(data["history"], list)
        assert data["license"]["id"] == license_obj.id

    def test_history_not_found(self, authenticated_client, db_session):
        """Requesting history for a nonexistent license returns an error."""
        response = authenticated_client.get("/api/license/99999/history")
        assert response.status_code in (404, 500)
