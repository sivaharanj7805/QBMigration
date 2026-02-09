"""Tests for api/legal.py - Legal documents API endpoints."""


class TestLegalDocuments:
    """Tests for legal document API endpoints."""

    def test_list_documents(self, client):
        response = client.get("/legal/api/documents")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "documents" in data
        assert "eula" in data["documents"]
        assert "privacy" in data["documents"]
        assert "security" in data["documents"]
        assert "dpa" in data["documents"]

    def test_eula_api(self, client):
        response = client.get("/legal/api/eula")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["document"] == "eula"
        assert "metadata" in data
        assert "summary" in data

    def test_privacy_api(self, client):
        response = client.get("/legal/api/privacy")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["document"] == "privacy"
        assert "data_collected" in data["summary"]
        assert "user_rights" in data["summary"]

    def test_security_api(self, client):
        response = client.get("/legal/api/security")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "practices" in data
        assert "encryption" in data["practices"]

    def test_dpa_api(self, client):
        response = client.get("/legal/api/dpa")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "sub_processors" in data["summary"]

    def test_eula_html_fallback(self, client):
        """EULA HTML route should fallback to JSON when template is missing."""
        response = client.get("/legal/eula")
        assert response.status_code == 200

    def test_privacy_html_fallback(self, client):
        response = client.get("/legal/privacy")
        assert response.status_code == 200

    def test_terms_redirect(self, client):
        response = client.get("/legal/terms")
        assert response.status_code in (301, 302, 308)

    def test_cookies_html_fallback(self, client):
        response = client.get("/legal/cookies")
        assert response.status_code == 200

    def test_security_html_fallback(self, client):
        response = client.get("/legal/security")
        assert response.status_code == 200

    def test_data_processing_html_fallback(self, client):
        response = client.get("/legal/data-processing")
        assert response.status_code == 200

    def test_compliance_info(self, client):
        response = client.get("/legal/api/documents")
        data = response.get_json()
        assert data["compliance"]["gdpr"] is True
        assert data["compliance"]["pipeda"] is True
