"""Extended tests for api/dashboard_api.py - overview, activity, error paths."""


class TestDashboardOverview:
    """Tests for dashboard overview endpoint."""

    def test_get_dashboard_overview(self, authenticated_client):
        response = authenticated_client.get("/api/dashboard/overview")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_get_dashboard_overview_unauthenticated(self, client):
        response = client.get("/api/dashboard/overview")
        assert response.status_code == 401


class TestRecentActivity:
    """Tests for recent activity endpoint."""

    def test_get_recent_activity(self, authenticated_client):
        response = authenticated_client.get("/api/dashboard/recent-activity")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_get_recent_activity_unauthenticated(self, client):
        response = client.get("/api/dashboard/recent-activity")
        assert response.status_code == 401


class TestLiveStatus:
    """Tests for live migration status."""

    def test_get_live_status_invalid_uuid(self, authenticated_client):
        response = authenticated_client.get("/api/migrations/not-a-uuid/live-status")
        assert response.status_code == 400

    def test_get_live_status_nonexistent(self, authenticated_client):
        response = authenticated_client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/live-status"
        )
        assert response.status_code == 404


class TestBulkStatus:
    """Tests for bulk migration status."""

    def test_get_bulk_status_empty(self, authenticated_client):
        response = authenticated_client.post(
            "/api/migrations/bulk-status",
            json={"migration_ids": []},
        )
        # May return all or empty depending on implementation
        assert response.status_code in (200, 400)


class TestTrialBalance:
    """Tests for trial balance endpoint."""

    def test_get_trial_balance_invalid_uuid(self, authenticated_client):
        response = authenticated_client.get("/api/migrations/not-valid/trial-balance")
        assert response.status_code == 400

    def test_get_trial_balance_nonexistent(self, authenticated_client):
        response = authenticated_client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/trial-balance"
        )
        assert response.status_code == 404


class TestAuditCertificate:
    """Tests for audit certificate endpoints."""

    def test_audit_cert_invalid_uuid(self, authenticated_client):
        response = authenticated_client.get(
            "/api/migrations/bad-uuid/audit-certificate"
        )
        assert response.status_code == 400

    def test_audit_cert_nonexistent(self, authenticated_client):
        response = authenticated_client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/audit-certificate"
        )
        assert response.status_code == 404


class TestIsValidUUID:
    """Tests for dashboard is_valid_uuid helper."""

    def test_valid_uuid(self):
        from api.dashboard_api import is_valid_uuid

        assert is_valid_uuid("12345678-1234-1234-1234-123456789abc") is True

    def test_invalid_uuid(self):
        from api.dashboard_api import is_valid_uuid

        assert is_valid_uuid("not-a-uuid") is False

    def test_empty_string(self):
        from api.dashboard_api import is_valid_uuid

        assert is_valid_uuid("") is False

    def test_none(self):
        from api.dashboard_api import is_valid_uuid

        assert is_valid_uuid(None) is False

    def test_uppercase_uuid(self):
        from api.dashboard_api import is_valid_uuid

        assert is_valid_uuid("12345678-1234-1234-1234-123456789ABC") is True

    def test_sql_injection(self):
        from api.dashboard_api import is_valid_uuid

        assert is_valid_uuid("'; DROP TABLE migrations; --") is False
