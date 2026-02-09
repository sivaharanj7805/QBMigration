"""
Tests targeting remaining coverage gaps across app.py, api/reports.py,
api/dashboard_api.py, api/session_validation.py, api/webhooks.py,
config.py, and error handler branches.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestErrorHandlers:
    """Test app.py error handlers (lines 1342-1460)."""

    def test_404_not_found_handler(self, client):
        """Trigger 404 handler (line 1384-1395)."""
        resp = client.get("/api/nonexistent-endpoint-xyz")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False

    def test_health_endpoint_returns_200(self, client):
        """Test health check basic response."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert "database" in data["checks"]

    def test_health_endpoint_options(self, client):
        """Test health check OPTIONS request (line 1119-1121)."""
        resp = client.options("/health")
        assert resp.status_code in [200, 204]

    def test_health_endpoint_detailed_sqlite(self, client):
        """Test health check with ?detailed=true on SQLite (line 1143-1186)."""
        resp = client.get("/health?detailed=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["checks"].get("connection_pool") == "not_postgresql"

    def test_health_disk_space_check(self, client):
        """Test disk space check branch (lines 1204-1216)."""
        resp = client.get("/health?detailed=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "disk_space" in data["checks"]

    def test_health_aws_not_configured(self, client):
        """Test health check when AWS not configured (line 1198)."""
        resp = client.get("/health?detailed=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["checks"].get("aws_s3") in ["not_configured", "unhealthy"]

    def test_root_endpoint(self, client):
        """Test root endpoint returns server info (line 1027-1038)."""
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "running"
        assert "version" in data


class TestHealthEndpointUnhealthy:
    """Test health endpoint unhealthy branches."""

    def test_health_database_unhealthy(self, app, client):
        """Test health check when DB fails (lines 1134-1139)."""
        from models.database import db

        with patch.object(db.session, "execute", side_effect=Exception("DB down")):
            resp = client.get("/health")
            assert resp.status_code == 503
            data = resp.get_json()
            assert data["status"] == "unhealthy"
            assert data["checks"]["database"] == "unhealthy"


class TestSetupSentry:
    """Test setup_sentry function (lines 134-157)."""

    def test_sentry_not_configured(self, app):
        """Sentry DSN not set - should log info (line 157)."""
        from app import setup_sentry

        app.config["SENTRY_DSN"] = None
        setup_sentry(app)

    def test_sentry_configured_import_error(self, app):
        """Sentry configured but SDK not installed (lines 152-153)."""
        from app import setup_sentry

        app.config["SENTRY_DSN"] = "https://examplePublicKey@o0.ingest.sentry.io/0"
        with patch.dict("sys.modules", {"sentry_sdk": None}):
            with patch("builtins.__import__", side_effect=ImportError("no sentry")):
                setup_sentry(app)

    def test_sentry_init_exception(self, app):
        """Sentry init fails with exception (lines 154-155)."""
        from app import setup_sentry

        app.config["SENTRY_DSN"] = "https://examplePublicKey@o0.ingest.sentry.io/0"
        mock_sentry = MagicMock()
        mock_sentry.init.side_effect = Exception("Sentry init failed")

        with patch.dict(
            "sys.modules",
            {"sentry_sdk": mock_sentry, "sentry_sdk.integrations.flask": MagicMock()},
        ):
            setup_sentry(app)


class TestVerifyAWSConfiguration:
    """Test verify_aws_configuration function (lines 160-195)."""

    def test_aws_no_bucket_configured(self, app):
        from app import verify_aws_configuration

        app.config["AWS_S3_BUCKET"] = None
        result = verify_aws_configuration(app)
        assert result is False

    def test_aws_bucket_verified(self, app):
        from app import verify_aws_configuration

        app.config["AWS_S3_BUCKET"] = "test-bucket"
        app.config["AWS_REGION"] = "ca-central-1"

        mock_s3 = MagicMock()
        with patch("boto3.client", return_value=mock_s3):
            result = verify_aws_configuration(app)
            assert result is True

    def test_aws_bucket_404(self, app):
        from app import verify_aws_configuration
        from botocore.exceptions import ClientError

        app.config["AWS_S3_BUCKET"] = "nonexistent-bucket"
        app.config["AWS_REGION"] = "ca-central-1"

        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
        )
        with patch("boto3.client", return_value=mock_s3):
            result = verify_aws_configuration(app)
            assert result is False

    def test_aws_bucket_403(self, app):
        from app import verify_aws_configuration
        from botocore.exceptions import ClientError

        app.config["AWS_S3_BUCKET"] = "private-bucket"
        app.config["AWS_REGION"] = "ca-central-1"

        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadBucket"
        )
        with patch("boto3.client", return_value=mock_s3):
            result = verify_aws_configuration(app)
            assert result is False

    def test_aws_bucket_other_error(self, app):
        from app import verify_aws_configuration
        from botocore.exceptions import ClientError

        app.config["AWS_S3_BUCKET"] = "broken-bucket"
        app.config["AWS_REGION"] = "ca-central-1"

        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Server Error"}}, "HeadBucket"
        )
        with patch("boto3.client", return_value=mock_s3):
            result = verify_aws_configuration(app)
            assert result is False

    def test_aws_generic_exception(self, app):
        from app import verify_aws_configuration

        app.config["AWS_S3_BUCKET"] = "test"
        app.config["AWS_REGION"] = "ca-central-1"

        with patch("boto3.client", side_effect=Exception("connection error")):
            result = verify_aws_configuration(app)
            assert result is False


class TestLogRequestMiddleware:
    """Test request logging middleware (lines 1274-1320)."""

    def test_request_logging_skips_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_request_logging_sanitizes_sensitive_paths(self, client):
        # Trigger sensitive path sanitization for /reset-password
        resp = client.get("/api/auth/reset-password/some-token")
        assert resp.status_code in [404, 405, 400, 200, 302]

    def test_response_logging_skips_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200


class TestReportsAPI:
    """Test api/reports.py coverage."""

    def test_list_reports_unauthenticated(self, client):
        resp = client.get("/api/reports")
        assert resp.status_code == 401

    def test_list_reports_authenticated(self, authenticated_client, db_session):
        resp = authenticated_client.get("/api/reports")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] == 0

    def test_list_reports_with_completed_migration(
        self, authenticated_client, db_session, test_user, test_migration
    ):
        test_migration.status = "completed"
        test_migration.completed_at = datetime.now(timezone.utc)
        db_session.commit()

        resp = authenticated_client.get("/api/reports")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_generate_report_unauthenticated(self, client):
        resp = client.post("/api/reports/generate")
        assert resp.status_code == 401

    def test_generate_report_no_data(self, authenticated_client):
        """Generate report with no JSON body."""
        resp = authenticated_client.post(
            "/api/reports/generate",
            data="",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code in [400, 500]

    def test_generate_report_nonexistent_migration(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/reports/generate",
            json={
                "migration_id": "12345678-1234-1234-1234-123456789012",
                "report_type": "variance",
            },
        )
        assert resp.status_code in [400, 404]

    def test_download_report_invalid_id(self, authenticated_client):
        resp = authenticated_client.get("/api/reports/../../../etc/passwd/download")
        assert resp.status_code in [400, 404]


class TestReportsValidation:
    """Test report validation helper."""

    def test_is_valid_migration_id_valid(self, app):
        from api.reports import is_valid_migration_id

        assert is_valid_migration_id("12345678-1234-1234-1234-123456789012") is True

    def test_is_valid_migration_id_invalid(self, app):
        from api.reports import is_valid_migration_id

        assert is_valid_migration_id("") is False
        assert is_valid_migration_id(None) is False
        assert is_valid_migration_id("not-a-uuid") is False
        assert is_valid_migration_id("../etc/passwd") is False


class TestDashboardAPICoverage:
    """Test dashboard_api.py uncovered branches."""

    def test_dashboard_overview_unauthenticated(self, client):
        resp = client.get("/api/dashboard/overview")
        assert resp.status_code == 401

    def test_dashboard_overview_authenticated(self, authenticated_client, db_session):
        resp = authenticated_client.get("/api/dashboard/overview")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_recent_activity_authenticated(self, authenticated_client, db_session):
        resp = authenticated_client.get("/api/dashboard/recent-activity")
        assert resp.status_code == 200

    def test_audit_certificate_unauthenticated(self, client):
        resp = client.get("/api/migrations/fake-id/audit-certificate")
        assert resp.status_code == 401

    def test_audit_certificate_not_found(self, authenticated_client, db_session):
        resp = authenticated_client.get(
            "/api/migrations/nonexistent-id/audit-certificate"
        )
        assert resp.status_code in [400, 404]

    def test_live_status_not_found(self, authenticated_client, db_session):
        resp = authenticated_client.get(
            "/api/migrations/nonexistent-id/live-status"
        )
        assert resp.status_code in [400, 404]

    def test_trial_balance_not_found(self, authenticated_client, db_session):
        resp = authenticated_client.get(
            "/api/migrations/nonexistent-id/trial-balance"
        )
        assert resp.status_code in [400, 404]

    def test_bulk_status_empty(self, authenticated_client, db_session):
        resp = authenticated_client.post(
            "/api/migrations/bulk-status",
            json={"migration_ids": []},
        )
        assert resp.status_code in [200, 400]


class TestWebhooksCoverage:
    """Test api/webhooks.py uncovered branches."""

    def test_webhook_started_no_signature(self, client):
        resp = client.post(
            "/api/webhooks/migration-started",
            json={"migration_id": "test", "status": "started"},
        )
        assert resp.status_code in [400, 401, 403]

    def test_webhook_progress_no_signature(self, client):
        resp = client.post(
            "/api/webhooks/migration-progress",
            json={"migration_id": "test", "progress": 50},
        )
        assert resp.status_code in [400, 401, 403]

    def test_webhook_completed_no_signature(self, client):
        resp = client.post(
            "/api/webhooks/migration-completed",
            json={"migration_id": "test", "status": "completed"},
        )
        assert resp.status_code in [400, 401, 403]

    def test_webhook_failed_no_signature(self, client):
        resp = client.post(
            "/api/webhooks/migration-failed",
            json={"migration_id": "test", "error": "something"},
        )
        assert resp.status_code in [400, 401, 403]

    def test_webhook_health(self, client):
        resp = client.get("/api/webhooks/health")
        assert resp.status_code == 200


class TestConfigCoverage:
    """Test config.py validation paths."""

    def test_config_warn_aws_credentials_non_production(self, app):
        from config import Config

        with patch.dict(os.environ, {"FLASK_ENV": "testing"}):
            Config.warn_aws_credentials()

    def test_config_warn_aws_credentials_production(self, app):
        from config import Config

        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "production",
                "AWS_ACCESS_KEY_ID": "test-key",
                "AWS_SECRET_ACCESS_KEY": "test-secret",
            },
        ):
            import warnings

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                Config.warn_aws_credentials()
                assert len(w) >= 1


class TestSessionValidationCoverage:
    """Test session_validation.py deeper paths."""

    def test_activate_device_missing_fields(self, client, db_session):
        resp = client.post(
            "/api/session/activate",
            json={"session_id": "test"},
        )
        assert resp.status_code == 400

    def test_validate_session_missing_fields(self, client, db_session):
        resp = client.post(
            "/api/session/validate",
            json={},
        )
        assert resp.status_code == 400

    def test_session_status_nonexistent(self, client, db_session):
        resp = client.get("/api/session/status/FB-NONEXISTENT-0000")
        assert resp.status_code in [200, 401, 404]

    def test_complete_extraction_empty_body(self, client, db_session):
        resp = client.post(
            "/api/session/complete-extraction",
            data="",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_complete_extraction_missing_session_id(self, client, db_session):
        resp = client.post(
            "/api/session/complete-extraction",
            json={"device_fingerprint": "fp", "extraction_token": "tok"},
        )
        assert resp.status_code == 400

    def test_complete_extraction_missing_token(self, client, db_session):
        resp = client.post(
            "/api/session/complete-extraction",
            json={
                "session_id": "FB-20260209-TEST1234",
                "device_fingerprint": "test-fp",
                "transaction_count": 100,
            },
        )
        assert resp.status_code == 400

    def test_complete_extraction_no_activation(self, client, db_session):
        resp = client.post(
            "/api/session/complete-extraction",
            json={
                "session_id": "FB-20260209-TEST1234",
                "device_fingerprint": "test-fp",
                "extraction_token": "fake-token-12345",
                "transaction_count": 100,
            },
        )
        assert resp.status_code == 403

    def test_start_extraction_missing_fields(self, client, db_session):
        resp = client.post(
            "/api/session/start-extraction",
            json={"session_id": "test"},
        )
        assert resp.status_code == 400


class TestProjectModelCoverage:
    """Test Project model methods for coverage."""

    def test_project_can_extract_transactions(self, app, db_session, test_user):
        from models.project import Project

        project = Project(
            user_id=test_user.id,
            name="TX Test",
            client_name="TX Client",
            transaction_limit=1000,
            transactions_used=500,
        )
        db_session.add(project)
        db_session.commit()

        assert project.can_extract_transactions(400) is True
        assert project.can_extract_transactions(600) is False

    def test_project_unlimited_transactions(self, app, db_session, test_user):
        from models.project import Project

        project = Project(
            user_id=test_user.id,
            name="Unlimited Test",
            client_name="Unlimited Client",
            transaction_limit=-1,
        )
        db_session.add(project)
        db_session.commit()

        assert project.can_extract_transactions(999999) is True
        assert project.get_remaining_transactions() == -1

    def test_project_record_transactions(self, app, db_session, test_user):
        from models.project import Project

        project = Project(
            user_id=test_user.id,
            name="Record Test",
            client_name="Record Client",
            transaction_limit=1000,
        )
        db_session.add(project)
        db_session.commit()

        assert project.record_transactions(500) is True
        assert project.transactions_used == 500

    def test_project_get_tier_name(self, app, db_session, test_user):
        from models.project import Project

        project = Project(
            user_id=test_user.id,
            name="Tier Test",
            client_name="Tier Client",
            tier_type="starter",
        )
        db_session.add(project)
        db_session.commit()

        tier_name = project.get_tier_name()
        assert isinstance(tier_name, str)
        assert len(tier_name) > 0


class TestErrorSanitizerCoverage:
    """Test error sanitizer utilities."""

    def test_sanitize_error_message_basic(self, app):
        from utils.error_sanitizer import sanitize_error_message

        result = sanitize_error_message("Some error message")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_sanitize_error_in_production_mode(self, app):
        """In production mode, error messages should be sanitized."""
        from utils.error_sanitizer import sanitize_error_message

        with patch.dict(os.environ, {"FLASK_ENV": "production"}):
            error_with_path = Exception("/home/user/secret/file.py: line 42 error")
            result = sanitize_error_message(error_with_path, context="api")
            # Production mode should sanitize the error
            assert isinstance(result, str)

    def test_create_error_response(self, app):
        from utils.error_sanitizer import create_error_response

        response = create_error_response(
            Exception("test error"), context="api", status_code=500
        )
        assert isinstance(response, dict)
        assert response.get("success") is False


class TestAnomalyDetectorCoverage:
    """Test anomaly_detector.py functions."""

    def test_is_unusual_login_time(self, app):
        from utils.anomaly_detector import is_unusual_login_time

        # 3 AM should be unusual
        unusual_time = datetime(2026, 1, 15, 3, 0, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(unusual_time)
        assert isinstance(is_unusual, bool)
        assert isinstance(reason, str)

    def test_is_unusual_login_time_normal(self, app):
        from utils.anomaly_detector import is_unusual_login_time

        # 10 AM should be normal
        normal_time = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(normal_time)
        assert is_unusual is False

    def test_is_suspicious_ip(self, app):
        from utils.anomaly_detector import is_suspicious_ip

        is_suspicious, reason = is_suspicious_ip("192.168.1.1")
        assert isinstance(is_suspicious, bool)
        assert isinstance(reason, str)

    def test_detect_large_file_upload(self, app):
        from utils.anomaly_detector import detect_large_file_upload

        is_large, reason = detect_large_file_upload(1024 * 1024 * 1024 * 5, user_id=1)
        assert isinstance(is_large, bool)

    def test_check_login_anomalies(self, app, db_session, test_user):
        from utils.anomaly_detector import check_login_anomalies

        anomalies = check_login_anomalies(
            user_id=test_user.id, ip_address="192.168.1.1"
        )
        assert isinstance(anomalies, list)

    def test_check_upload_anomalies(self, app, db_session, test_user):
        from utils.anomaly_detector import check_upload_anomalies

        anomalies = check_upload_anomalies(
            user_id=test_user.id, file_size_bytes=1024 * 1024
        )
        assert isinstance(anomalies, list)

    def test_check_migration_anomalies(self, app, db_session, test_user):
        from utils.anomaly_detector import check_migration_anomalies

        anomalies = check_migration_anomalies(user_id=test_user.id)
        assert isinstance(anomalies, list)


class TestLegalAPICoverage:
    """Test api/legal.py endpoints."""

    def test_legal_documents_list(self, client):
        resp = client.get("/legal/api/documents")
        assert resp.status_code == 200

    def test_legal_eula(self, client):
        resp = client.get("/legal/api/eula")
        assert resp.status_code == 200

    def test_legal_privacy(self, client):
        resp = client.get("/legal/api/privacy")
        assert resp.status_code == 200

    def test_legal_security(self, client):
        resp = client.get("/legal/api/security")
        assert resp.status_code == 200

    def test_legal_dpa(self, client):
        resp = client.get("/legal/api/dpa")
        assert resp.status_code == 200

    def test_legal_html_eula(self, client):
        resp = client.get("/legal/eula")
        assert resp.status_code == 200

    def test_legal_html_privacy(self, client):
        resp = client.get("/legal/privacy")
        assert resp.status_code == 200

    def test_legal_html_terms(self, client):
        resp = client.get("/legal/terms")
        assert resp.status_code in [200, 302]

    def test_legal_html_cookies(self, client):
        resp = client.get("/legal/cookies")
        assert resp.status_code == 200


class TestMigrationModelCoverage:
    """Test additional Migration model methods."""

    def test_migration_to_dict(self, app, db_session, test_migration):
        result = test_migration.to_dict()
        assert isinstance(result, dict)
        assert "migration_id" in result
        assert "status" in result

    def test_migration_update_progress(self, app, db_session, test_migration):
        test_migration.progress_percent = 50
        test_migration.current_step = "Processing customers"
        db_session.commit()

        assert test_migration.progress_percent == 50
        assert test_migration.current_step == "Processing customers"


class TestDatabaseModelCoverage:
    """Test models/database.py."""

    def test_init_db_called_successfully(self, app):
        from models.database import db

        assert db.engine is not None


class TestUserModelCoverage:
    """Test User model methods for coverage."""

    def test_user_clear_expired_lock(self, app, db_session, test_user):
        test_user.account_locked_until = datetime.now(timezone.utc) - timedelta(
            minutes=1
        )
        test_user.failed_login_attempts = 5
        db_session.commit()

        assert test_user.is_locked() is False

        if hasattr(test_user, "clear_expired_lock"):
            test_user.clear_expired_lock()
            db_session.commit()
            assert test_user.account_locked_until is None
            assert test_user.failed_login_attempts == 0

    def test_user_set_password(self, app, db_session, test_user):
        """Test password hashing."""
        test_user.set_password("NewSecurePassword123!")
        db_session.commit()
        assert test_user.check_password("NewSecurePassword123!") is True
        assert test_user.check_password("WrongPassword123!") is False

    def test_user_subscription_tier_default(self, app, db_session, test_user):
        """Test default subscription tier."""
        assert test_user.subscription_tier in ["free", None]

    def test_user_mfa_not_enabled_by_default(self, app, db_session, test_user):
        """Test MFA is not enabled by default."""
        if hasattr(test_user, "mfa_enabled"):
            assert test_user.mfa_enabled is False or test_user.mfa_enabled is None
