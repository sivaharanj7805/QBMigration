"""Tests for api/session_validation.py - session validation, activation, extraction."""

from models.project import Project


class TestValidateSession:
    """Tests for POST /api/session/validate."""

    def test_validate_no_data(self, client):
        response = client.post(
            "/api/session/validate",
            data="",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_validate_missing_session_id(self, client):
        response = client.post(
            "/api/session/validate",
            json={"device_fingerprint": "fp-123"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["valid"] is False

    def test_validate_missing_fingerprint(self, client):
        response = client.post(
            "/api/session/validate",
            json={"session_id": "FB-TEST-1234"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "fingerprint" in data["error"].lower()

    def test_validate_nonexistent_session(self, client, db_session):
        response = client.post(
            "/api/session/validate",
            json={
                "session_id": "FB-NONEXISTENT-0000",
                "device_fingerprint": "test-device-fp",
            },
        )
        # Returns 200 with valid=False or 404
        data = response.get_json()
        assert data["valid"] is False

    def test_validate_valid_session(self, client, db_session, test_user):
        # Create a project with session_id
        project = Project(
            user_id=test_user.id,
            name="Test Project",
            client_name="Test Client",
        )
        db_session.add(project)
        db_session.commit()
        # Use the auto-generated session_id
        session_id = project.session_id

        response = client.post(
            "/api/session/validate",
            json={
                "session_id": session_id,
                "device_fingerprint": "device-abc-123",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["valid"] is True


class TestActivateSession:
    """Tests for POST /api/session/activate."""

    def test_activate_no_data(self, client):
        response = client.post(
            "/api/session/activate",
            data="",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_activate_missing_session_id(self, client):
        response = client.post(
            "/api/session/activate",
            json={"device_fingerprint": "fp-123"},
        )
        assert response.status_code == 400

    def test_activate_nonexistent_session(self, client, db_session):
        response = client.post(
            "/api/session/activate",
            json={
                "session_id": "FB-NONEXISTENT-0000",
                "device_fingerprint": "test-fp",
            },
        )
        data = response.get_json()
        assert data.get("success") is False or response.status_code == 404


class TestSessionStatus:
    """Tests for GET /api/session/status/<session_id>."""

    def test_status_requires_auth(self, client, db_session):
        response = client.get("/api/session/status/FB-NONEXISTENT")
        # Status endpoint requires authentication
        assert response.status_code == 401

    def test_status_nonexistent_session(self, authenticated_client, db_session):
        response = authenticated_client.get("/api/session/status/FB-NONEXISTENT")
        data = response.get_json()
        assert data.get("found") is False or response.status_code == 404
