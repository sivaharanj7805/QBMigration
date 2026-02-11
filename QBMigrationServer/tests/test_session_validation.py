"""
Test Suite for Session Validation API Endpoints
Tests /api/session/* endpoints from api/session_validation.py

These endpoints use project session IDs (format: FB-YYYYMMDDHHMMSS-XXXXXXXX),
NOT Flask login sessions. Authentication is done via session_id + device_fingerprint
rather than Flask-Login.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.migration_credit import MigrationCredit  # noqa: E402
from models.project import Project  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_credit(db_session, test_user):
    """Create a migration credit for project creation."""
    credit = MigrationCredit(
        user_id=test_user.id,
        tier_type="starter",
        transaction_limit=5000,
        price_cents=49700,
        status="used",
        payment_status="paid",
        stripe_checkout_session_id="test_checkout_session_001",
    )
    db_session.add(credit)
    db_session.commit()
    db_session.refresh(credit)
    return credit


@pytest.fixture
def test_project(db_session, test_user, test_credit):
    """Create a project with a known session ID for validation tests."""
    project = Project(
        user_id=test_user.id,
        name="Test Project",
        client_name="Test Client",
        session_id="FB-20260203120000-TESTABCD",
        tier_type="starter",
        transaction_limit=5000,
        status="active",
        migration_credit_id=test_credit.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


# ---------------------------------------------------------------------------
# Tests: POST /api/session/validate
# ---------------------------------------------------------------------------


class TestValidateSession:
    """Tests for POST /api/session/validate"""

    def test_validate_missing_body_returns_400(self, client, db_session):
        """Sending no JSON body should return 400."""
        response = client.post("/api/session/validate", content_type="application/json")
        assert response.status_code == 400

    def test_validate_missing_session_id_returns_400(self, client, db_session):
        """Missing session_id field should return 400."""
        response = client.post(
            "/api/session/validate",
            json={"device_fingerprint": "abc123"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["valid"] is False
        assert "session" in data["error"].lower() or "required" in data["error"].lower()

    def test_validate_empty_session_id_returns_400(self, client, db_session):
        """Empty string session_id should return 400."""
        response = client.post(
            "/api/session/validate",
            json={"session_id": "", "device_fingerprint": "abc123"},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_validate_missing_device_fingerprint_returns_400(self, client, db_session):
        """Missing device_fingerprint should return 400."""
        response = client.post(
            "/api/session/validate",
            json={"session_id": "FB-20260203120000-TESTABCD"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["valid"] is False
        assert "fingerprint" in data["error"].lower()

    def test_validate_empty_device_fingerprint_returns_400(self, client, db_session):
        """Empty device fingerprint should return 400."""
        response = client.post(
            "/api/session/validate",
            json={
                "session_id": "FB-20260203120000-TESTABCD",
                "device_fingerprint": "   ",
            },
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_validate_nonexistent_session_returns_404(self, client, db_session):
        """A session_id that does not exist in the database should return 404."""
        response = client.post(
            "/api/session/validate",
            json={
                "session_id": "FB-99990101000000-NOTEXIST",
                "device_fingerprint": "device_fp_123",
            },
            content_type="application/json",
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["valid"] is False

    def test_validate_valid_session_returns_success(
        self, client, db_session, test_project
    ):
        """A valid session_id with device fingerprint should return valid=True."""
        response = client.post(
            "/api/session/validate",
            json={
                "session_id": test_project.session_id,
                "device_fingerprint": "test_device_fp_001",
            },
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["valid"] is True
        assert data["session_id"] == test_project.session_id
        assert data["project_name"] == test_project.name
        assert data["tier"] == "starter"
        assert "transaction_limit" in data
        assert "transactions_remaining" in data


# ---------------------------------------------------------------------------
# Tests: POST /api/session/activate
# ---------------------------------------------------------------------------


class TestActivateSession:
    """Tests for POST /api/session/activate"""

    def test_activate_missing_body_returns_400(self, client, db_session):
        """Sending no JSON body should return 400."""
        response = client.post("/api/session/activate", content_type="application/json")
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_activate_missing_fields_returns_400(self, client, db_session):
        """Missing device_fingerprint should return 400."""
        response = client.post(
            "/api/session/activate",
            json={"session_id": "FB-20260203120000-TESTABCD"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_activate_nonexistent_session_returns_404(self, client, db_session):
        """Activating a non-existent session should return 404."""
        response = client.post(
            "/api/session/activate",
            json={
                "session_id": "FB-99990101000000-NOTEXIST",
                "device_fingerprint": "device_fp_123",
            },
            content_type="application/json",
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False

    def test_activate_valid_session_succeeds(self, client, db_session, test_project):
        """Activating a valid session on a new device should succeed."""
        response = client.post(
            "/api/session/activate",
            json={
                "session_id": test_project.session_id,
                "device_fingerprint": "new_device_fp_001",
                "device_name": "Test Workstation",
            },
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "activation_id" in data


# ---------------------------------------------------------------------------
# Tests: POST /api/session/start-extraction
# ---------------------------------------------------------------------------


class TestStartExtraction:
    """Tests for POST /api/session/start-extraction"""

    def test_start_extraction_missing_body_returns_400(self, client, db_session):
        """Sending no JSON body should return 400."""
        response = client.post(
            "/api/session/start-extraction", content_type="application/json"
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_start_extraction_missing_fields_returns_400(self, client, db_session):
        """Missing required fields should return 400."""
        response = client.post(
            "/api/session/start-extraction",
            json={"session_id": "FB-20260203120000-TESTABCD"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_start_extraction_invalid_session_returns_404(self, client, db_session):
        """Starting extraction with invalid session should return 404."""
        response = client.post(
            "/api/session/start-extraction",
            json={
                "session_id": "FB-99990101000000-NOTEXIST",
                "device_fingerprint": "device_fp_123",
                "company_name": "Test Company",
            },
            content_type="application/json",
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /api/session/complete-extraction
# ---------------------------------------------------------------------------


class TestCompleteExtraction:
    """Tests for POST /api/session/complete-extraction"""

    def test_complete_extraction_missing_body_returns_400(self, client, db_session):
        """Sending no JSON body should return 400."""
        response = client.post(
            "/api/session/complete-extraction", content_type="application/json"
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_complete_extraction_missing_fields_returns_400(self, client, db_session):
        """Missing device_fingerprint should return 400."""
        response = client.post(
            "/api/session/complete-extraction",
            json={"session_id": "FB-20260203120000-TESTABCD"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_complete_extraction_invalid_session_returns_404(self, client, db_session):
        """Completing extraction with invalid session should return 404."""
        response = client.post(
            "/api/session/complete-extraction",
            json={
                "session_id": "FB-99990101000000-NOTEXIST",
                "device_fingerprint": "device_fp_123",
                "extraction_token": "fake_token",
                "transaction_count": 100,
                "company_name": "Test",
                "qb_version": "Enterprise 2024",
            },
            content_type="application/json",
        )
        # CRIT-03 FIX: endpoint checks activation first (403) before project lookup (404)
        assert response.status_code == 403
        data = response.get_json()
        assert data["success"] is False
        assert (
            "extraction" in data["error"].lower() or "active" in data["error"].lower()
        )


# ---------------------------------------------------------------------------
# Tests: GET /api/session/status/<session_id>
# ---------------------------------------------------------------------------


class TestSessionStatus:
    """Tests for GET /api/session/status/<session_id>

    NOTE: The session status endpoint requires authentication via flask_login.
    Tests use authenticated_client which sets both JWT header and session cookie.
    """

    def test_status_requires_auth(self, client, db_session):
        """Requesting status without authentication should return 401."""
        response = client.get("/api/session/status/FB-99990101000000-NOTEXIST")
        assert response.status_code == 401

    def test_status_nonexistent_session_returns_404(
        self, authenticated_client, db_session
    ):
        """Requesting status for a non-existent session should return 404."""
        response = authenticated_client.get(
            "/api/session/status/FB-99990101000000-NOTEXIST"
        )
        assert response.status_code == 404
        data = response.get_json()
        assert data["found"] is False

    def test_status_valid_session_returns_project_info(
        self, authenticated_client, db_session, test_project
    ):
        """Requesting status for a valid session should return project details."""
        response = authenticated_client.get(
            f"/api/session/status/{test_project.session_id}"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["found"] is True
        assert data["session_id"] == test_project.session_id
        assert data["project_name"] == test_project.name
        assert data["status"] == "active"
        assert data["tier"] == "starter"

    def test_status_includes_transaction_info(
        self, authenticated_client, db_session, test_project
    ):
        """Status response should include transaction limit details."""
        response = authenticated_client.get(
            f"/api/session/status/{test_project.session_id}"
        )
        data = response.get_json()
        assert "transaction_limit" in data
        assert data["transaction_limit"] == 5000
        assert "transactions_used" in data
        assert "transactions_remaining" in data

    def test_status_includes_device_info(
        self, authenticated_client, db_session, test_project
    ):
        """Status response should include device activation counts."""
        response = authenticated_client.get(
            f"/api/session/status/{test_project.session_id}"
        )
        data = response.get_json()
        assert "devices_active" in data
        assert "max_devices" in data
        assert "extractions_used" in data
        assert "max_extractions" in data

    def test_status_includes_tier_name(
        self, authenticated_client, db_session, test_project
    ):
        """Status response should include the human-readable tier name."""
        response = authenticated_client.get(
            f"/api/session/status/{test_project.session_id}"
        )
        data = response.get_json()
        assert data["tier_name"] == "Starter"

    def test_status_includes_created_at(
        self, authenticated_client, db_session, test_project
    ):
        """Status response should include creation timestamp."""
        response = authenticated_client.get(
            f"/api/session/status/{test_project.session_id}"
        )
        data = response.get_json()
        assert "created_at" in data
        assert data["created_at"] is not None


# ---------------------------------------------------------------------------
# Tests: Rate Limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for rate limiting on session validation endpoints.

    The rate limiter triggers after 10+ attempts within 5 minutes
    for the same session_id + IP address combination.
    """

    def test_rate_limit_after_many_validate_attempts(
        self, client, db_session, test_project
    ):
        """After 10+ validation attempts in 5 minutes, should return 429."""
        payload = {
            "session_id": test_project.session_id,
            "device_fingerprint": "rate_limit_test_device",
        }

        last_response = None
        for i in range(12):
            last_response = client.post(
                "/api/session/validate", json=payload, content_type="application/json"
            )

        # After 10+ attempts, the rate limiter should kick in
        assert last_response.status_code == 429
        data = last_response.get_json()
        assert data["valid"] is False
        assert "too many" in data["error"].lower() or "wait" in data["error"].lower()


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------


class TestSessionEdgeCases:
    """Edge case and boundary tests for session validation."""

    def test_validate_with_whitespace_only_session_id(self, client, db_session):
        """Whitespace-only session_id should be treated as empty (400)."""
        response = client.post(
            "/api/session/validate",
            json={"session_id": "   ", "device_fingerprint": "abc123"},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_activate_with_whitespace_only_fingerprint(self, client, db_session):
        """Whitespace-only fingerprint should return 400."""
        response = client.post(
            "/api/session/activate",
            json={
                "session_id": "FB-20260203120000-TESTABCD",
                "device_fingerprint": "   ",
            },
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_status_with_empty_session_id(self, client, db_session):
        """GET /api/session/status/ with no session_id should return 404
        (Flask route mismatch)."""
        response = client.get("/api/session/status/")
        assert response.status_code == 404

    def test_validate_archived_project_returns_403(
        self, client, db_session, test_project
    ):
        """Validating against an archived project should return 403."""
        test_project.status = "archived"
        db_session.commit()

        response = client.post(
            "/api/session/validate",
            json={
                "session_id": test_project.session_id,
                "device_fingerprint": "device_fp_archived",
            },
            content_type="application/json",
        )
        assert response.status_code == 403
        data = response.get_json()
        assert data["valid"] is False
        assert "archived" in data["error"].lower()
