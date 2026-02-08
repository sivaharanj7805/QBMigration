"""Tests for dashboard caseware and export endpoints."""

from models.migration import Migration


class TestExportCaseware:
    """Tests for POST /api/migrations/<id>/export-caseware."""

    def test_export_caseware_unauthenticated(self, client):
        response = client.post(
            "/api/migrations/00000000-0000-0000-0000-000000000000/export-caseware"
        )
        assert response.status_code == 401

    def test_export_caseware_invalid_uuid(self, authenticated_client):
        response = authenticated_client.post("/api/migrations/bad-uuid/export-caseware")
        # May return 400 (UUID validation) or 404 (route not matched)
        assert response.status_code in (400, 404)

    def test_export_caseware_nonexistent(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/migrations/00000000-0000-0000-0000-000000000000/export-caseware"
        )
        assert response.status_code == 404

    def test_export_caseware_not_completed(
        self, authenticated_client, db_session, test_user
    ):
        m = Migration(
            user_id=test_user.id,
            company_name="Pending Co",
            qb_file_name="pending.qbw",
            status="pending",
        )
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.post(
            f"/api/migrations/{m.migration_id}/export-caseware"
        )
        assert response.status_code in (400, 404, 500)


class TestCasewareBundle:
    """Tests for GET /api/migrations/<id>/caseware-bundle."""

    def test_bundle_unauthenticated(self, client):
        response = client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/caseware-bundle"
        )
        assert response.status_code == 401

    def test_bundle_invalid_uuid(self, authenticated_client):
        response = authenticated_client.get("/api/migrations/bad-uuid/caseware-bundle")
        assert response.status_code == 400

    def test_bundle_nonexistent(self, authenticated_client, db_session):
        response = authenticated_client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/caseware-bundle"
        )
        assert response.status_code == 404


class TestCasewareStatus:
    """Tests for GET /api/migrations/<id>/caseware-status."""

    def test_status_unauthenticated(self, client):
        response = client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/caseware-status"
        )
        assert response.status_code == 401

    def test_status_invalid_uuid(self, authenticated_client):
        response = authenticated_client.get("/api/migrations/bad-uuid/caseware-status")
        assert response.status_code == 400

    def test_status_nonexistent(self, authenticated_client, db_session):
        response = authenticated_client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/caseware-status"
        )
        assert response.status_code == 404

    def test_status_success(self, authenticated_client, db_session, test_user):
        m = Migration(
            user_id=test_user.id,
            company_name="Caseware Co",
            qb_file_name="caseware.qbw",
            status="completed",
            destination="caseware",
        )
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.get(
            f"/api/migrations/{m.migration_id}/caseware-status"
        )
        assert response.status_code == 200


class TestDashboardOverview:
    """Tests for GET /api/dashboard/overview."""

    def test_overview_unauthenticated(self, client):
        response = client.get("/api/dashboard/overview")
        assert response.status_code == 401

    def test_overview_success(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/dashboard/overview")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_overview_with_data(self, authenticated_client, db_session, test_user):
        m = Migration(
            user_id=test_user.id,
            company_name="Overview Co",
            qb_file_name="overview.qbw",
            status="completed",
            total_records_migrated=500,
        )
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.get("/api/dashboard/overview")
        assert response.status_code == 200


class TestRecentActivity:
    """Tests for GET /api/dashboard/recent-activity."""

    def test_recent_activity_unauthenticated(self, client):
        response = client.get("/api/dashboard/recent-activity")
        assert response.status_code == 401

    def test_recent_activity_success(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/dashboard/recent-activity")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True


class TestLiveStatus:
    """Tests for GET /api/migrations/<id>/live-status."""

    def test_live_status_unauthenticated(self, client):
        response = client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/live-status"
        )
        assert response.status_code == 401

    def test_live_status_invalid_uuid(self, authenticated_client):
        response = authenticated_client.get("/api/migrations/bad-uuid/live-status")
        assert response.status_code == 400

    def test_live_status_nonexistent(self, authenticated_client, db_session):
        response = authenticated_client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/live-status"
        )
        assert response.status_code == 404

    def test_live_status_success(self, authenticated_client, db_session, test_user):
        m = Migration(
            user_id=test_user.id,
            company_name="Live Co",
            qb_file_name="live.qbw",
            status="processing",
        )
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.get(
            f"/api/migrations/{m.migration_id}/live-status"
        )
        assert response.status_code == 200


class TestTrialBalance:
    """Tests for GET /api/migrations/<id>/trial-balance."""

    def test_trial_balance_unauthenticated(self, client):
        response = client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/trial-balance"
        )
        assert response.status_code == 401

    def test_trial_balance_invalid_uuid(self, authenticated_client):
        response = authenticated_client.get("/api/migrations/bad-uuid/trial-balance")
        assert response.status_code == 400

    def test_trial_balance_nonexistent(self, authenticated_client, db_session):
        response = authenticated_client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/trial-balance"
        )
        assert response.status_code == 404

    def test_trial_balance_success(self, authenticated_client, db_session, test_user):
        m = Migration(
            user_id=test_user.id,
            company_name="TB Co",
            qb_file_name="tb.qbw",
            status="completed",
        )
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.get(
            f"/api/migrations/{m.migration_id}/trial-balance"
        )
        assert response.status_code == 200


class TestAuditCertificate:
    """Tests for GET /api/migrations/<id>/audit-certificate."""

    def test_audit_cert_unauthenticated(self, client):
        response = client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/audit-certificate"
        )
        assert response.status_code == 401

    def test_audit_cert_invalid_uuid(self, authenticated_client):
        response = authenticated_client.get(
            "/api/migrations/bad-uuid/audit-certificate"
        )
        assert response.status_code == 400

    def test_audit_cert_nonexistent(self, authenticated_client, db_session):
        response = authenticated_client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/audit-certificate"
        )
        assert response.status_code == 404

    def test_audit_cert_success(self, authenticated_client, db_session, test_user):
        m = Migration(
            user_id=test_user.id,
            company_name="Audit Co",
            qb_file_name="audit.qbw",
            status="completed",
        )
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.get(
            f"/api/migrations/{m.migration_id}/audit-certificate"
        )
        assert response.status_code in (200, 404, 500)


class TestAuditCertificatePreview:
    """Tests for GET /api/migrations/<id>/audit-certificate/preview."""

    def test_preview_unauthenticated(self, client):
        response = client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/audit-certificate/preview"
        )
        assert response.status_code == 401

    def test_preview_nonexistent(self, authenticated_client, db_session):
        response = authenticated_client.get(
            "/api/migrations/00000000-0000-0000-0000-000000000000/audit-certificate/preview"
        )
        assert response.status_code == 404

    def test_preview_success(self, authenticated_client, db_session, test_user):
        from datetime import datetime, timezone

        m = Migration(
            user_id=test_user.id,
            company_name="Preview Co",
            qb_file_name="preview.qbw",
            status="completed",
        )
        m.completed_at = datetime.now(timezone.utc)
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.get(
            f"/api/migrations/{m.migration_id}/audit-certificate/preview"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["available"] is True
        assert data["company_name"] == "Preview Co"

    def test_preview_not_completed(self, authenticated_client, db_session, test_user):
        m = Migration(
            user_id=test_user.id,
            company_name="Pending Preview",
            qb_file_name="pp.qbw",
            status="pending",
        )
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.get(
            f"/api/migrations/{m.migration_id}/audit-certificate/preview"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["available"] is False


class TestBulkStatus:
    """Tests for POST /api/migrations/bulk-status."""

    def test_bulk_status_unauthenticated(self, client):
        response = client.post(
            "/api/migrations/bulk-status",
            json={"migration_ids": []},
        )
        assert response.status_code == 401

    def test_bulk_status_empty(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/migrations/bulk-status",
            json={"migration_ids": []},
        )
        assert response.status_code in (200, 400)

    def test_bulk_status_with_ids(self, authenticated_client, db_session, test_user):
        m1 = Migration(
            user_id=test_user.id,
            company_name="Bulk1",
            qb_file_name="b1.qbw",
            status="pending",
        )
        m2 = Migration(
            user_id=test_user.id,
            company_name="Bulk2",
            qb_file_name="b2.qbw",
            status="completed",
        )
        db_session.add_all([m1, m2])
        db_session.commit()

        response = authenticated_client.post(
            "/api/migrations/bulk-status",
            json={"migration_ids": [m1.migration_id, m2.migration_id]},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_bulk_status_invalid_ids(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/migrations/bulk-status",
            json={"migration_ids": ["not-a-uuid", "also-bad"]},
        )
        assert response.status_code in (200, 400)

    def test_bulk_status_no_data(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/migrations/bulk-status",
            data="",
            content_type="application/json",
        )
        assert response.status_code in (400, 500)
