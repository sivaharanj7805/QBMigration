"""Extended tests for utils/anomaly_detector.py - pure detection functions."""

from datetime import datetime, timezone

from utils.anomaly_detector import (
    detect_large_file_upload,
    detect_rapid_migrations,
    is_suspicious_ip,
    is_unusual_login_time,
)


class TestIsUnusualLoginTime:
    """Tests for login time anomaly detection."""

    def test_normal_business_hours(self):
        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(ts)
        assert is_unusual is False

    def test_early_morning(self):
        ts = datetime(2024, 1, 15, 3, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(ts)
        assert is_unusual is True
        assert reason != ""

    def test_late_night(self):
        ts = datetime(2024, 1, 15, 2, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(ts)
        assert is_unusual is True

    def test_boundary_morning(self):
        ts = datetime(2024, 1, 15, 6, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(ts)
        assert isinstance(is_unusual, bool)

    def test_midday(self):
        ts = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(ts)
        assert is_unusual is False

    def test_afternoon(self):
        ts = datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc)
        is_unusual, reason = is_unusual_login_time(ts)
        assert is_unusual is False


class TestIsSuspiciousIP:
    """Tests for suspicious IP detection."""

    def test_private_192_is_flagged(self):
        # 192.168.* is in SUSPICIOUS_IP_RANGES (corporate VPN indicator)
        is_suspicious, reason = is_suspicious_ip("192.168.1.1")
        assert is_suspicious is True
        assert "suspicious" in reason.lower()

    def test_public_ip_not_flagged(self):
        is_suspicious, reason = is_suspicious_ip("8.8.8.8")
        assert is_suspicious is False

    def test_localhost_not_flagged(self):
        is_suspicious, reason = is_suspicious_ip("127.0.0.1")
        assert is_suspicious is False

    def test_openvpn_range_flagged(self):
        # 10.8.0.* is OpenVPN default
        is_suspicious, reason = is_suspicious_ip("10.8.0.5")
        assert is_suspicious is True


class TestDetectLargeFileUpload:
    """Tests for large file upload detection."""

    def test_normal_file_size(self, db_session, test_user):
        is_suspicious, reason = detect_large_file_upload(
            10 * 1024 * 1024, test_user.id  # 10 MB
        )
        assert is_suspicious is False

    def test_large_file_over_2gb(self, db_session, test_user):
        # Threshold is 2000 MB, so we need > 2GB
        is_suspicious, reason = detect_large_file_upload(
            3 * 1024 * 1024 * 1024, test_user.id  # 3 GB
        )
        assert is_suspicious is True
        assert "large" in reason.lower() or "mb" in reason.lower()

    def test_tiny_file(self, db_session, test_user):
        is_suspicious, reason = detect_large_file_upload(1024, test_user.id)  # 1 KB
        assert is_suspicious is False


class TestDetectLargeFileUploadDaily:
    """Tests for daily upload volume check."""

    def test_normal_daily_volume(self, db_session, test_user):
        is_suspicious, reason = detect_large_file_upload(
            100 * 1024 * 1024, test_user.id
        )
        assert is_suspicious is False

    def test_just_over_threshold(self, db_session, test_user):
        is_suspicious, reason = detect_large_file_upload(
            2001 * 1024 * 1024, test_user.id
        )
        assert is_suspicious is True


class TestDetectRapidMigrations:
    """Tests for rapid migration detection."""

    def test_no_recent_migrations(self, db_session, test_user):
        is_suspicious, reason = detect_rapid_migrations(test_user.id)
        assert is_suspicious is False

    def test_few_recent_migrations(self, db_session, test_user):
        from models.migration import Migration

        for i in range(2):
            m = Migration(
                user_id=test_user.id,
                company_name=f"Rapid {i}",
                qb_file_name=f"r{i}.qbw",
                status="pending",
            )
            db_session.add(m)
        db_session.commit()
        is_suspicious, reason = detect_rapid_migrations(test_user.id)
        assert is_suspicious is False
