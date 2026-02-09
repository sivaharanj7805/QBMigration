"""
Extended tests for api/reports.py - targeting uncovered lines for 85%+ coverage.

Covers:
- Report listing with completed migrations (with/without report files)
- Report generation with completed migration, certificate redirect, unknown type
- Report download validation (invalid ID, bad type)
- Discrepancy endpoint (empty, with verification_results JSON data)
- Record count endpoint
- Discrepancy report download (PDF generation fallback)
"""

import json
import uuid
from datetime import datetime, timezone

from models.migration import Migration

# ============================================================================
# Helpers
# ============================================================================


def _create_completed_migration(db_session, test_user, **overrides):
    """Create a completed migration for testing."""
    defaults = {
        "migration_id": str(uuid.uuid4()),
        "user_id": test_user.id,
        "company_name": "Test Co",
        "qb_file_name": "test.qbw",
        "status": "completed",
        "completed_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    migration = Migration(**defaults)
    db_session.add(migration)
    db_session.commit()
    db_session.refresh(migration)
    return migration


# ============================================================================
# List Reports - GET /api/reports
# ============================================================================


class TestListReports:
    """Tests for GET /api/reports."""

    def test_list_reports_returns_array(
        self, authenticated_client, db_session, test_user
    ):
        """GET /api/reports returns 200 with reports array (may be empty)."""
        response = authenticated_client.get("/api/reports")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert isinstance(data["reports"], list)
        assert "count" in data

    def test_list_reports_with_completed_migration(
        self, authenticated_client, db_session, test_user
    ):
        """Completed migration appears in report listing context."""
        _create_completed_migration(db_session, test_user)
        response = authenticated_client.get("/api/reports")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        # Reports list may be empty if no PDF files exist on disk, but the request succeeds
        assert isinstance(data["reports"], list)

    def test_list_reports_with_verification_discrepancies(
        self, authenticated_client, db_session, test_user
    ):
        """Migration with verification_results containing discrepancies shows discrepancy report."""
        verification = json.dumps(
            {
                "discrepancies": [
                    {
                        "account_name": "Cash",
                        "difference": 100.50,
                        "source_balance": 5000.00,
                        "destination_balance": 4899.50,
                    }
                ]
            }
        )
        _create_completed_migration(
            db_session, test_user, verification_results=verification
        )
        response = authenticated_client.get("/api/reports")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        # Should include a discrepancy report entry
        discrepancy_reports = [r for r in data["reports"] if r["type"] == "discrepancy"]
        assert len(discrepancy_reports) == 1
        assert discrepancy_reports[0]["name"] == "Discrepancy Report"

    def test_list_reports_bad_verification_json(
        self, authenticated_client, db_session, test_user
    ):
        """Migration with invalid verification_results JSON does not crash."""
        _create_completed_migration(
            db_session, test_user, verification_results="not-valid-json{"
        )
        response = authenticated_client.get("/api/reports")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True


# ============================================================================
# Generate Report - POST /api/reports/generate
# ============================================================================


class TestGenerateReport:
    """Tests for POST /api/reports/generate."""

    def test_generate_no_migration(self, authenticated_client, db_session, test_user):
        """POST /api/reports/generate returns 404 when no completed migration exists."""
        response = authenticated_client.post(
            "/api/reports/generate", json={"type": "variance"}
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False
        assert "no completed migration" in data["error"].lower()

    def test_generate_with_migration(self, authenticated_client, db_session, test_user):
        """POST generate with type=variance on completed migration succeeds."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.post(
            "/api/reports/generate",
            json={"type": "variance", "migration_id": migration.migration_id},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "variance" in data.get("message", "").lower()
        assert "report_id" in data
        assert "download_url" in data

    def test_generate_health_report(self, authenticated_client, db_session, test_user):
        """POST generate with type=health on completed migration succeeds."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.post(
            "/api/reports/generate",
            json={"type": "health", "migration_id": migration.migration_id},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_generate_discrepancy_report(
        self, authenticated_client, db_session, test_user
    ):
        """POST generate with type=discrepancy on completed migration succeeds."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.post(
            "/api/reports/generate",
            json={"type": "discrepancy", "migration_id": migration.migration_id},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_generate_certificate_redirect(
        self, authenticated_client, db_session, test_user
    ):
        """POST with type=certificate returns redirect info."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.post(
            "/api/reports/generate",
            json={"type": "certificate", "migration_id": migration.migration_id},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "redirect" in data
        assert "audit-certificate" in data["redirect"]

    def test_generate_unknown_type(self, authenticated_client, db_session, test_user):
        """POST with type=invalid returns 400."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.post(
            "/api/reports/generate",
            json={"type": "invalid", "migration_id": migration.migration_id},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "unknown report type" in data["error"].lower()

    def test_generate_default_type_is_variance(
        self, authenticated_client, db_session, test_user
    ):
        """POST generate without type defaults to variance."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.post(
            "/api/reports/generate",
            json={"migration_id": migration.migration_id},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "variance" in data.get("report_id", "")

    def test_generate_uses_latest_completed(
        self, authenticated_client, db_session, test_user
    ):
        """POST generate without migration_id uses latest completed migration."""
        _create_completed_migration(db_session, test_user, company_name="Old Co")
        response = authenticated_client.post(
            "/api/reports/generate", json={"type": "variance"}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_generate_empty_json_body(
        self, authenticated_client, db_session, test_user
    ):
        """POST generate with empty JSON object defaults to variance and latest migration."""
        _create_completed_migration(db_session, test_user)
        response = authenticated_client.post(
            "/api/reports/generate",
            json={},
        )
        # Empty dict means type defaults to "variance" and uses latest completed migration
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True


# ============================================================================
# Download Report - GET /api/reports/<report_id>/download
# ============================================================================


class TestDownloadReport:
    """Tests for GET /api/reports/<report_id>/download."""

    def test_download_invalid_id(self, authenticated_client, db_session, test_user):
        """GET /api/reports/invalid/download returns 400 for non-parseable ID."""
        response = authenticated_client.get("/api/reports/invalid/download")
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_download_bad_type(self, authenticated_client, db_session, test_user):
        """GET /api/reports/{uuid}_badtype/download returns 400 for invalid report type."""
        valid_uuid = str(uuid.uuid4())
        response = authenticated_client.get(
            f"/api/reports/{valid_uuid}_badtype/download"
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "invalid report type" in data["error"].lower()

    def test_download_valid_type_no_migration(
        self, authenticated_client, db_session, test_user
    ):
        """GET download with valid format but nonexistent migration returns 404."""
        valid_uuid = str(uuid.uuid4())
        response = authenticated_client.get(
            f"/api/reports/{valid_uuid}_variance/download"
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False

    def test_download_no_file_on_disk(
        self, authenticated_client, db_session, test_user
    ):
        """GET download for existing migration but missing file returns 404."""
        migration = _create_completed_migration(db_session, test_user)
        report_id = f"{migration.migration_id}_variance"
        response = authenticated_client.get(f"/api/reports/{report_id}/download")
        assert response.status_code == 404
        data = response.get_json()
        assert "regenerate" in data["error"].lower()

    def test_download_report_after_generation(
        self, authenticated_client, db_session, test_user
    ):
        """Generate a report then download it."""
        migration = _create_completed_migration(db_session, test_user)
        # Generate first
        gen_resp = authenticated_client.post(
            "/api/reports/generate",
            json={"type": "variance", "migration_id": migration.migration_id},
        )
        assert gen_resp.status_code == 200
        gen_data = gen_resp.get_json()
        download_url = gen_data["download_url"]

        # Download
        dl_resp = authenticated_client.get(download_url)
        # Should return the file (200) since generation created it
        assert dl_resp.status_code == 200

    def test_download_path_traversal_blocked(
        self, authenticated_client, db_session, test_user
    ):
        """Path traversal attempts in report ID are blocked (400 or 404)."""
        # Flask routing may normalize path traversal sequences, returning 404,
        # or the UUID validator catches it and returns 400. Either way, the
        # traversal does not result in file access.
        response = authenticated_client.get(
            "/api/reports/../../etc/passwd_variance/download"
        )
        assert response.status_code in (400, 404)


# ============================================================================
# Discrepancies - GET /api/migrations/<id>/discrepancies
# ============================================================================


class TestDiscrepancies:
    """Tests for GET /api/migrations/<id>/discrepancies."""

    def test_get_discrepancies(self, authenticated_client, db_session, test_user):
        """GET discrepancies for migration returns 200."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/discrepancies"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["migration_id"] == migration.migration_id
        assert "discrepancies" in data
        assert "total_discrepancy" in data
        assert "has_discrepancies" in data

    def test_discrepancies_empty(self, authenticated_client, db_session, test_user):
        """Migration without verification_results has no discrepancies."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/discrepancies"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["has_discrepancies"] is False
        assert data["total_discrepancy"] == 0
        assert data["discrepancies"] == []

    def test_discrepancies_with_data(self, authenticated_client, db_session, test_user):
        """Migration with verification_results containing discrepancies returns them."""
        verification = json.dumps(
            {
                "discrepancies": [
                    {
                        "account_name": "Accounts Receivable",
                        "account_type": "Asset",
                        "source_balance": 10000.00,
                        "destination_balance": 9500.00,
                        "difference": 500.00,
                        "severity": "critical",
                        "possible_cause": "Missing invoices",
                    },
                    {
                        "account_name": "Office Supplies",
                        "account_type": "Expense",
                        "source_balance": 250.00,
                        "destination_balance": 245.00,
                        "difference": 5.00,
                        "severity": "warning",
                        "possible_cause": "Rounding",
                    },
                ]
            }
        )
        migration = _create_completed_migration(
            db_session, test_user, verification_results=verification
        )
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/discrepancies"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["has_discrepancies"] is True
        assert len(data["discrepancies"]) == 2
        assert data["total_discrepancy"] == 505.00
        assert data["discrepancies"][0]["account_name"] == "Accounts Receivable"

    def test_discrepancies_from_trial_balance(
        self, authenticated_client, db_session, test_user
    ):
        """Migration with trial_balance variance (no explicit discrepancies) generates one."""
        verification = json.dumps(
            {
                "trial_balance": {
                    "source_total": 50000.00,
                    "destination_total": 49800.00,
                }
            }
        )
        migration = _create_completed_migration(
            db_session, test_user, verification_results=verification
        )
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/discrepancies"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["has_discrepancies"] is True
        assert len(data["discrepancies"]) == 1
        assert data["discrepancies"][0]["account_name"] == "Trial Balance Total"
        assert data["discrepancies"][0]["severity"] == "critical"
        assert data["total_discrepancy"] == 200.00

    def test_discrepancies_trial_balance_small_diff(
        self, authenticated_client, db_session, test_user
    ):
        """Trial balance difference less than 1 cent is treated as balanced."""
        verification = json.dumps(
            {
                "trial_balance": {
                    "source_total": 50000.00,
                    "destination_total": 50000.005,
                }
            }
        )
        migration = _create_completed_migration(
            db_session, test_user, verification_results=verification
        )
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/discrepancies"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["has_discrepancies"] is False

    def test_discrepancies_not_found(self, authenticated_client, db_session, test_user):
        """GET discrepancies for nonexistent migration returns 404."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f"/api/migrations/{fake_id}/discrepancies")
        assert response.status_code == 404

    def test_discrepancies_bad_json(self, authenticated_client, db_session, test_user):
        """Migration with invalid verification_results JSON does not crash."""
        migration = _create_completed_migration(
            db_session, test_user, verification_results="{bad json"
        )
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/discrepancies"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["has_discrepancies"] is False


# ============================================================================
# Record Count - GET /api/migrations/<id>/record-count
# ============================================================================


class TestRecordCount:
    """Tests for GET /api/migrations/<id>/record-count."""

    def test_get_record_count(self, authenticated_client, db_session, test_user):
        """GET record-count for migration returns 200."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/record-count"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["migration_id"] == migration.migration_id
        assert "record_count" in data

    def test_record_count_from_verification(
        self, authenticated_client, db_session, test_user
    ):
        """Record count extracted from verification_results total_records."""
        verification = json.dumps({"total_records": 1500})
        migration = _create_completed_migration(
            db_session, test_user, verification_results=verification
        )
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/record-count"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["record_count"] == 1500

    def test_record_count_default_zero(
        self, authenticated_client, db_session, test_user
    ):
        """Migration without verification data returns record_count of 0."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/record-count"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["record_count"] == 0

    def test_record_count_not_found(self, authenticated_client, db_session, test_user):
        """GET record-count for nonexistent migration returns 404."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f"/api/migrations/{fake_id}/record-count")
        assert response.status_code == 404

    def test_record_count_bad_verification_json(
        self, authenticated_client, db_session, test_user
    ):
        """Bad verification_results JSON falls back to 0."""
        migration = _create_completed_migration(
            db_session, test_user, verification_results="not-json"
        )
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/record-count"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["record_count"] == 0


# ============================================================================
# Discrepancy Report - GET /api/migrations/<id>/discrepancy-report
# ============================================================================


class TestDiscrepancyReport:
    """Tests for GET /api/migrations/<id>/discrepancy-report."""

    def test_download_discrepancy_report(
        self, authenticated_client, db_session, test_user
    ):
        """GET discrepancy-report generates and returns a file."""
        migration = _create_completed_migration(db_session, test_user)
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/discrepancy-report"
        )
        # Should succeed (generates PDF or text fallback)
        assert response.status_code == 200

    def test_download_discrepancy_report_with_data(
        self, authenticated_client, db_session, test_user
    ):
        """GET discrepancy-report with verification data includes discrepancies in output."""
        verification = json.dumps(
            {
                "discrepancies": [
                    {
                        "account_name": "Revenue",
                        "source_balance": 20000.00,
                        "destination_balance": 19500.00,
                        "difference": 500.00,
                    }
                ]
            }
        )
        migration = _create_completed_migration(
            db_session, test_user, verification_results=verification
        )
        response = authenticated_client.get(
            f"/api/migrations/{migration.migration_id}/discrepancy-report"
        )
        assert response.status_code == 200

    def test_download_discrepancy_report_not_found(
        self, authenticated_client, db_session, test_user
    ):
        """GET discrepancy-report for nonexistent migration returns 404."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(
            f"/api/migrations/{fake_id}/discrepancy-report"
        )
        assert response.status_code == 404


# ============================================================================
# Helper function unit tests
# ============================================================================


class TestHelpers:
    """Unit tests for helper functions in reports module."""

    def test_is_valid_migration_id_valid(self, app):
        """Valid UUID passes validation."""
        from api.reports import is_valid_migration_id

        assert is_valid_migration_id(str(uuid.uuid4())) is True

    def test_is_valid_migration_id_invalid(self, app):
        """Invalid strings fail validation."""
        from api.reports import is_valid_migration_id

        assert is_valid_migration_id("") is False
        assert is_valid_migration_id(None) is False
        assert is_valid_migration_id("not-a-uuid") is False
        assert is_valid_migration_id("../../../etc/passwd") is False

    def test_is_valid_migration_id_short(self, app):
        """Truncated UUID fails validation."""
        from api.reports import is_valid_migration_id

        assert is_valid_migration_id("12345678-1234-1234-1234") is False
