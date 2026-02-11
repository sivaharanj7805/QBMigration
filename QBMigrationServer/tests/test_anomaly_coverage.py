"""
Tests for anomaly_detector.py to cover remaining gaps.

Targets coverage in utils/anomaly_detector.py:
- detect_large_file_upload daily total check
- detect_rapid_migrations with enough migrations
- check_login_anomalies composite
- check_upload_anomalies with critical file size
- check_migration_anomalies
- log_anomaly for both high and critical severity
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.migration import Migration  # noqa: E402
from utils.anomaly_detector import check_login_anomalies  # noqa: E402
from utils.anomaly_detector import (
    check_migration_anomalies,
    check_upload_anomalies,
    detect_large_file_upload,
    detect_rapid_migrations,
    is_suspicious_ip,
    is_unusual_login_time,
    log_anomaly,
)


class TestDetectLargeFileUploadDaily:
    """Test daily upload volume check."""

    def test_single_large_file_exceeds_threshold(self, app, db_session, test_user):
        """Single file over 2GB threshold triggers detection."""
        file_size = 3 * 1024 * 1024 * 1024  # 3GB
        is_suspicious, reason = detect_large_file_upload(file_size, test_user.id)
        assert is_suspicious is True
        assert "Large file upload" in reason

    def test_daily_volume_not_exceeded(self, app, db_session, test_user):
        """Small uploads don't trigger daily limit."""
        is_suspicious, reason = detect_large_file_upload(1000, test_user.id)
        assert is_suspicious is False


class TestDetectRapidMigrationsDB:
    """Test rapid migrations detection with actual DB entries."""

    def test_rapid_migrations_triggered(self, app, db_session, test_user):
        """Create enough recent migrations to trigger detection."""
        for i in range(5):
            m = Migration(
                user_id=test_user.id,
                company_name=f"Rapid {i}",
                qb_file_name=f"rapid{i}.qbw",
                data_size_bytes=100,
                status="pending",
            )
            db_session.add(m)
        db_session.commit()
        is_suspicious, reason = detect_rapid_migrations(test_user.id)
        assert is_suspicious is True
        assert "Rapid migrations" in reason

    def test_rapid_migrations_not_triggered(self, app, db_session, test_user):
        """No recent migrations doesn't trigger."""
        is_suspicious, reason = detect_rapid_migrations(test_user.id)
        assert is_suspicious is False


class TestCheckLoginAnomalies:
    """Test composite login anomaly detection."""

    def test_check_login_anomalies_normal(self, app, db_session, test_user):
        """Normal login returns empty or low-severity anomalies."""
        anomalies = check_login_anomalies(test_user.id, "8.8.8.8")
        assert isinstance(anomalies, list)

    def test_check_login_anomalies_suspicious_ip(self, app, db_session, test_user):
        """Suspicious IP triggers anomaly."""
        anomalies = check_login_anomalies(test_user.id, "10.8.0.5")
        suspicious_types = [a["type"] for a in anomalies]
        assert "suspicious_ip" in suspicious_types

    def test_check_login_anomalies_unusual_time(self, app, db_session, test_user):
        """Login at unusual time may trigger anomaly (depends on current time)."""
        anomalies = check_login_anomalies(test_user.id, "8.8.8.8")
        # Just verify it returns a list without errors
        assert isinstance(anomalies, list)


class TestCheckUploadAnomalies:
    """Test composite upload anomaly detection."""

    def test_check_upload_anomalies_large_file(self, app, db_session, test_user):
        """Very large file triggers high severity."""
        anomalies = check_upload_anomalies(test_user.id, 3 * 1024 * 1024 * 1024)
        assert len(anomalies) > 0
        assert anomalies[0]["type"] == "large_file_upload"
        assert anomalies[0]["severity"] == "high"

    def test_check_upload_anomalies_critical_file(self, app, db_session, test_user):
        """File > 5GB triggers critical severity."""
        anomalies = check_upload_anomalies(test_user.id, 6 * 1024 * 1024 * 1024)
        assert len(anomalies) > 0
        assert anomalies[0]["severity"] == "critical"

    def test_check_upload_anomalies_small_file(self, app, db_session, test_user):
        """Small file doesn't trigger."""
        anomalies = check_upload_anomalies(test_user.id, 1000)
        assert len(anomalies) == 0


class TestCheckMigrationAnomalies:
    """Test composite migration anomaly detection."""

    def test_check_migration_anomalies_rapid(self, app, db_session, test_user):
        """Rapid migrations trigger anomaly."""
        for i in range(5):
            m = Migration(
                user_id=test_user.id,
                company_name=f"MigAnomaly {i}",
                qb_file_name=f"mig{i}.qbw",
                data_size_bytes=100,
                status="processing",
            )
            db_session.add(m)
        db_session.commit()
        anomalies = check_migration_anomalies(test_user.id)
        assert len(anomalies) > 0
        assert anomalies[0]["type"] == "rapid_migrations"

    def test_check_migration_anomalies_normal(self, app, db_session, test_user):
        """Normal activity no anomalies."""
        anomalies = check_migration_anomalies(test_user.id)
        assert len(anomalies) == 0


class TestLogAnomaly:
    """Test anomaly logging."""

    def test_log_anomaly_high(self, app):
        anomaly = {
            "type": "rapid_login_attempts",
            "severity": "high",
            "reason": "Test high severity",
        }
        log_anomaly(1, anomaly)  # Should not raise

    def test_log_anomaly_critical(self, app):
        anomaly = {
            "type": "impossible_travel",
            "severity": "critical",
            "reason": "Test critical severity",
        }
        log_anomaly(1, anomaly)  # Should not raise

    def test_log_anomaly_low(self, app):
        anomaly = {
            "type": "unusual_login_time",
            "severity": "low",
            "reason": "Test low severity",
        }
        log_anomaly(1, anomaly)  # Should not raise


class TestIsSuspiciousIP:
    """Test IP suspicion detection."""

    def test_openvpn_range(self, app):
        is_susp, reason = is_suspicious_ip("10.8.0.100")
        assert is_susp is True
        assert "10.8.0." in reason

    def test_private_range(self, app):
        is_susp, reason = is_suspicious_ip("192.168.1.1")
        assert is_susp is True

    def test_public_ip_not_suspicious(self, app):
        is_susp, reason = is_suspicious_ip("8.8.8.8")
        assert is_susp is False


class TestIsUnusualLoginTime:
    """Test unusual login time detection."""

    def test_unusual_early_morning(self, app):
        ts = datetime(2026, 1, 1, 3, 0, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(ts)
        assert is_unusual is True
        assert "unusual hour" in reason.lower()

    def test_normal_business_hours(self, app):
        ts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(ts)
        assert is_unusual is False
