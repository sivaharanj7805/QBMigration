"""Tests for api/reports.py - report listing, generation, and download."""


class TestListReports:
    """Tests for GET /api/reports."""

    def test_list_reports_authenticated(self, authenticated_client):
        response = authenticated_client.get("/api/reports")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "reports" in data

    def test_list_reports_unauthenticated(self, client):
        response = client.get("/api/reports")
        assert response.status_code == 401


class TestGenerateReport:
    """Tests for POST /api/reports/generate."""

    def test_generate_report_unauthenticated(self, client):
        response = client.post(
            "/api/reports/generate",
            json={"migration_id": "any", "report_type": "variance"},
        )
        assert response.status_code == 401

    def test_generate_report_missing_migration_id(self, authenticated_client):
        response = authenticated_client.post(
            "/api/reports/generate",
            json={"report_type": "variance"},
        )
        # Returns 400 or 404 depending on validation order
        assert response.status_code in (400, 404)

    def test_generate_report_invalid_migration_id(self, authenticated_client):
        response = authenticated_client.post(
            "/api/reports/generate",
            json={"migration_id": "not-a-uuid", "report_type": "variance"},
        )
        # Returns 400 or 404 depending on validation order
        assert response.status_code in (400, 404)

    def test_generate_report_nonexistent_migration(self, authenticated_client):
        response = authenticated_client.post(
            "/api/reports/generate",
            json={
                "migration_id": "00000000-0000-0000-0000-000000000000",
                "report_type": "variance",
            },
        )
        assert response.status_code == 404


class TestDownloadReport:
    """Tests for GET /api/reports/<id>/download."""

    def test_download_report_unauthenticated(self, client):
        response = client.get("/api/reports/some-id/download")
        assert response.status_code == 401

    def test_download_report_nonexistent(self, authenticated_client):
        response = authenticated_client.get(
            "/api/reports/nonexistent-report-id/download"
        )
        # Returns 400 or 404 depending on validation
        assert response.status_code in (400, 404)
