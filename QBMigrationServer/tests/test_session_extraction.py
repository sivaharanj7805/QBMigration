"""Tests for session extraction and completion endpoints."""

from api.session_validation import SessionActivation, hash_fingerprint
from models.project import Project


class TestStartExtraction:
    """Tests for POST /api/session/start-extraction."""

    def test_start_extraction_no_data(self, client, db_session):
        response = client.post(
            "/api/session/start-extraction",
            data="",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_start_extraction_missing_fields(self, client, db_session):
        response = client.post(
            "/api/session/start-extraction",
            json={"session_id": "FB-TEST-1234"},
        )
        assert response.status_code == 400

    def test_start_extraction_nonexistent_session(self, client, db_session):
        response = client.post(
            "/api/session/start-extraction",
            json={
                "session_id": "FB-NONEXISTENT-0000",
                "device_fingerprint": "test-fp",
            },
        )
        assert response.status_code == 404

    def test_start_extraction_device_not_activated(self, client, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Extract Project",
            client_name="Extract Client",
        )
        db_session.add(project)
        db_session.commit()

        response = client.post(
            "/api/session/start-extraction",
            json={
                "session_id": project.session_id,
                "device_fingerprint": "unactivated-device",
            },
        )
        assert response.status_code == 403

    def test_start_extraction_success(self, client, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Extract Project",
            client_name="Extract Client",
        )
        db_session.add(project)
        db_session.commit()
        session_id = project.session_id

        # Create an activation record
        fp_hash = hash_fingerprint("test-device-fp")
        activation = SessionActivation(
            session_id=session_id,
            device_fingerprint=fp_hash,
            device_name="Test Device",
            status="active",
        )
        db_session.add(activation)
        db_session.commit()

        response = client.post(
            "/api/session/start-extraction",
            json={
                "session_id": session_id,
                "device_fingerprint": "test-device-fp",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "extraction_token" in data


class TestCompleteExtraction:
    """Tests for POST /api/session/complete-extraction."""

    def test_complete_extraction_no_data(self, client, db_session):
        response = client.post(
            "/api/session/complete-extraction",
            data="",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_complete_extraction_missing_fields(self, client, db_session):
        response = client.post(
            "/api/session/complete-extraction",
            json={"session_id": "FB-TEST-1234"},
        )
        assert response.status_code == 400

    def test_complete_extraction_missing_token(self, client, db_session):
        """CRIT-03: extraction_token is now required - missing token returns 400."""
        response = client.post(
            "/api/session/complete-extraction",
            json={
                "session_id": "FB-NONEXISTENT-0000",
                "device_fingerprint": "test-fp",
                "transaction_count": 100,
            },
        )
        # CRIT-03 FIX: extraction_token is required, so missing it returns 400
        assert response.status_code == 400

    def test_complete_extraction_no_activation(self, client, db_session, test_user):
        """CRIT-03: providing a token but no matching activation returns 403."""
        project = Project(
            user_id=test_user.id,
            name="Complete Project",
            client_name="Complete Client",
            transaction_limit=5000,
        )
        db_session.add(project)
        db_session.commit()

        response = client.post(
            "/api/session/complete-extraction",
            json={
                "session_id": project.session_id,
                "device_fingerprint": "test-fp",
                "extraction_token": "fake-token",
                "transaction_count": 100,
            },
        )
        # No activation exists for this device, so returns 403
        assert response.status_code == 403

    def test_complete_extraction_exceeds_limit_no_token(
        self, client, db_session, test_user
    ):
        """Without extraction_token, complete-extraction returns 400 before checking limits."""
        project = Project(
            user_id=test_user.id,
            name="Limit Project",
            client_name="Limit Client",
            transaction_limit=100,
            transactions_used=90,
        )
        db_session.add(project)
        db_session.commit()

        response = client.post(
            "/api/session/complete-extraction",
            json={
                "session_id": project.session_id,
                "device_fingerprint": "test-fp",
                "transaction_count": 50,
            },
        )
        # CRIT-03 FIX: extraction_token is required
        assert response.status_code == 400


class TestHashFingerprint:
    """Tests for hash_fingerprint utility."""

    def test_hash_returns_string(self, app):
        result = hash_fingerprint("test-device")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest

    def test_hash_none_returns_none(self, app):
        result = hash_fingerprint(None)
        assert result is None

    def test_hash_empty_returns_none(self, app):
        result = hash_fingerprint("")
        assert result is None

    def test_hash_consistent(self, app):
        h1 = hash_fingerprint("same-device")
        h2 = hash_fingerprint("same-device")
        assert h1 == h2

    def test_hash_different_inputs(self, app):
        h1 = hash_fingerprint("device-a")
        h2 = hash_fingerprint("device-b")
        assert h1 != h2
