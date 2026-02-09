"""Tests for api/settings.py - Whitelabel settings endpoints."""


class TestWhitelabelEndpoints:
    """Tests for whitelabel settings API."""

    def test_get_whitelabel_default(self, authenticated_client):
        response = authenticated_client.get("/api/settings/whitelabel")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "config" in data

    def test_save_whitelabel(self, authenticated_client):
        response = authenticated_client.post(
            "/api/settings/whitelabel",
            json={
                "company_name": "Test Company",
                "primary_color": "#FF5733",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["config"]["company_name"] == "Test Company"

    def test_save_whitelabel_invalid_color(self, authenticated_client):
        response = authenticated_client.post(
            "/api/settings/whitelabel",
            json={"primary_color": "not-a-color"},
        )
        assert response.status_code == 400

    def test_save_whitelabel_no_body(self, authenticated_client):
        response = authenticated_client.post(
            "/api/settings/whitelabel",
            content_type="application/json",
        )
        # May return 400 or 401 depending on auth middleware
        assert response.status_code in (400, 401)

    def test_get_whitelabel_after_save(self, authenticated_client):
        # Save first
        authenticated_client.post(
            "/api/settings/whitelabel",
            json={"company_name": "Saved Co"},
        )
        # Then get
        response = authenticated_client.get("/api/settings/whitelabel")
        data = response.get_json()
        assert data["config"]["company_name"] == "Saved Co"

    def test_update_whitelabel(self, authenticated_client):
        # Create
        authenticated_client.post(
            "/api/settings/whitelabel",
            json={"company_name": "First"},
        )
        # Update
        response = authenticated_client.post(
            "/api/settings/whitelabel",
            json={"company_name": "Second"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["config"]["company_name"] == "Second"

    def test_get_whitelabel_unauthenticated(self, client):
        response = client.get("/api/settings/whitelabel")
        assert response.status_code == 401
