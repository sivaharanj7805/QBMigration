"""
Anomaly Detection System
========================

Detects unusual patterns in user behavior and system operations to identify:
- Suspicious login patterns (unusual times, locations, frequency)
- Large or unusual file uploads
- Abnormal migration activity
- Potential account compromise

ISSUE #39: Transaction anomaly detection for security monitoring.

Author: ForensicBridge Security Team
Version: 1.0.0
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import hashlib

from flask import request
from models.database import db
from sqlalchemy import text, func

logger = logging.getLogger(__name__)

# Anomaly thresholds
ANOMALY_THRESHOLDS = {
    # Login patterns
    'login_hour_start': 6,  # Normal login hours: 6 AM - 11 PM
    'login_hour_end': 23,
    'max_logins_per_hour': 10,  # Max login attempts per hour
    'max_logins_per_day': 50,   # Max logins per day
    'unusual_location_distance_km': 500,  # Travel > 500km in < 1 hour is suspicious

    # File uploads
    'large_file_threshold_mb': 2000,  # Files > 2GB are flagged
    'max_uploads_per_hour': 5,  # Max file uploads per hour
    'max_upload_size_per_day_gb': 10,  # Max total upload size per day

    # Migration patterns
    'rapid_migrations_count': 3,  # Starting 3+ migrations in 10 minutes is suspicious
    'rapid_migrations_window_minutes': 10,
    'unusual_migration_count_per_day': 20,  # > 20 migrations per day is unusual
}

# Known IP ranges for common VPNs and proxies (basic list)
SUSPICIOUS_IP_RANGES = [
    '10.8.0.',    # OpenVPN default
    '192.168.',   # Private networks (could be corporate VPN)
]


def is_unusual_login_time(timestamp: datetime) -> Tuple[bool, str]:
    """
    Detect logins at unusual hours.

    Most legitimate logins occur during business hours (6 AM - 11 PM).
    Logins outside this window may indicate automated attacks or compromised accounts.

    Args:
        timestamp: Login timestamp

    Returns:
        (is_unusual: bool, reason: str)
    """
    hour = timestamp.hour

    if hour < ANOMALY_THRESHOLDS['login_hour_start'] or hour > ANOMALY_THRESHOLDS['login_hour_end']:
        return True, f"Login at unusual hour: {hour}:00 (outside 6 AM - 11 PM)"

    return False, ""


def detect_rapid_login_attempts(user_id: int, window_hours: int = 1) -> Tuple[bool, str]:
    """
    Detect rapid login attempts that may indicate brute force or account takeover.

    Args:
        user_id: User ID to check
        window_hours: Time window in hours

    Returns:
        (is_suspicious: bool, reason: str)
    """
    try:
        # Query login attempts in the time window
        window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours)

        result = db.session.execute(text("""
            SELECT COUNT(*) as login_count
            FROM users
            WHERE id = :user_id
            AND last_login_at >= :window_start
        """), {'user_id': user_id, 'window_start': window_start})

        row = result.fetchone()
        login_count = row[0] if row else 0

        if login_count > ANOMALY_THRESHOLDS['max_logins_per_hour']:
            return True, f"Rapid login attempts: {login_count} in {window_hours}h (threshold: {ANOMALY_THRESHOLDS['max_logins_per_hour']})"

        return False, ""

    except Exception as e:
        logger.error(f"Error detecting rapid logins: {e}")
        return False, ""


def detect_impossible_travel(user_id: int, current_ip: str) -> Tuple[bool, str]:
    """
    Detect impossible travel scenarios.

    If a user logs in from location A, then location B within a short time window,
    and the distance between locations would require impossibly fast travel (e.g., > 500 km/h),
    this indicates account sharing or compromise.

    Args:
        user_id: User ID
        current_ip: Current login IP address

    Returns:
        (is_suspicious: bool, reason: str)

    Note: This is a simplified implementation. Production systems should use:
    - GeoIP database for accurate IP-to-location mapping
    - Haversine formula for distance calculations
    - Consider VPN usage patterns
    """
    # Simplified check: detect if IP changed dramatically in short time
    # In production, use MaxMind GeoIP2 or similar for precise geolocation

    try:
        # Get previous login IP within last hour
        result = db.session.execute(text("""
            SELECT last_login_ip, last_login_at
            FROM users
            WHERE id = :user_id
            AND last_login_at >= :window_start
        """), {
            'user_id': user_id,
            'window_start': datetime.now(timezone.utc) - timedelta(hours=1)
        })

        row = result.fetchone()
        if not row:
            return False, ""

        prev_ip, prev_login = row

        # If IP changed significantly in < 1 hour, flag as suspicious
        # Simplified: check if first 2 octets changed (crude location proxy)
        if prev_ip and current_ip:
            prev_prefix = '.'.join(prev_ip.split('.')[:2])
            curr_prefix = '.'.join(current_ip.split('.')[:2])

            if prev_prefix != curr_prefix:
                time_diff = datetime.now(timezone.utc) - prev_login
                if time_diff < timedelta(hours=1):
                    return True, f"Impossible travel: IP changed from {prev_ip} to {current_ip} in {time_diff.seconds // 60} minutes"

        return False, ""

    except Exception as e:
        logger.error(f"Error detecting impossible travel: {e}")
        return False, ""


def is_suspicious_ip(ip_address: str) -> Tuple[bool, str]:
    """
    Check if IP address is from known suspicious ranges.

    Args:
        ip_address: IP address to check

    Returns:
        (is_suspicious: bool, reason: str)
    """
    for suspicious_range in SUSPICIOUS_IP_RANGES:
        if ip_address.startswith(suspicious_range):
            return True, f"IP from suspicious range: {suspicious_range}*"

    return False, ""


def detect_large_file_upload(file_size_bytes: int, user_id: int) -> Tuple[bool, str]:
    """
    Detect unusually large file uploads that may indicate data exfiltration or abuse.

    Args:
        file_size_bytes: Size of uploaded file in bytes
        user_id: User uploading the file

    Returns:
        (is_suspicious: bool, reason: str)
    """
    file_size_mb = file_size_bytes / (1024 * 1024)

    # Check if single file exceeds threshold
    if file_size_mb > ANOMALY_THRESHOLDS['large_file_threshold_mb']:
        return True, f"Large file upload: {file_size_mb:.1f} MB (threshold: {ANOMALY_THRESHOLDS['large_file_threshold_mb']} MB)"

    # Check total upload volume in last 24 hours
    try:
        result = db.session.execute(text("""
            SELECT COALESCE(SUM(encrypted_data_size_bytes), 0) as total_size
            FROM migrations
            WHERE user_id = :user_id
            AND created_at >= :window_start
        """), {
            'user_id': user_id,
            'window_start': datetime.now(timezone.utc) - timedelta(days=1)
        })

        row = result.fetchone()
        total_size_bytes = row[0] if row else 0
        total_size_gb = total_size_bytes / (1024 * 1024 * 1024)

        # Add current upload to total
        total_size_gb += file_size_bytes / (1024 * 1024 * 1024)

        if total_size_gb > ANOMALY_THRESHOLDS['max_upload_size_per_day_gb']:
            return True, f"Daily upload limit exceeded: {total_size_gb:.2f} GB (threshold: {ANOMALY_THRESHOLDS['max_upload_size_per_day_gb']} GB)"

        return False, ""

    except Exception as e:
        logger.error(f"Error checking daily upload volume: {e}")
        return False, ""


def detect_rapid_migrations(user_id: int) -> Tuple[bool, str]:
    """
    Detect rapid migration starts that may indicate automated abuse.

    Args:
        user_id: User ID

    Returns:
        (is_suspicious: bool, reason: str)
    """
    try:
        window_start = datetime.now(timezone.utc) - timedelta(
            minutes=ANOMALY_THRESHOLDS['rapid_migrations_window_minutes']
        )

        result = db.session.execute(text("""
            SELECT COUNT(*) as migration_count
            FROM migrations
            WHERE user_id = :user_id
            AND created_at >= :window_start
            AND status IN ('pending', 'processing', 'uploading')
        """), {'user_id': user_id, 'window_start': window_start})

        row = result.fetchone()
        migration_count = row[0] if row else 0

        if migration_count >= ANOMALY_THRESHOLDS['rapid_migrations_count']:
            return True, f"Rapid migrations: {migration_count} started in {ANOMALY_THRESHOLDS['rapid_migrations_window_minutes']} minutes"

        return False, ""

    except Exception as e:
        logger.error(f"Error detecting rapid migrations: {e}")
        return False, ""


def check_login_anomalies(user_id: int, ip_address: str) -> List[Dict]:
    """
    Comprehensive login anomaly detection.

    Args:
        user_id: User ID
        ip_address: Login IP address

    Returns:
        List of detected anomalies with severity and details
    """
    anomalies = []

    # Check login time
    is_unusual, reason = is_unusual_login_time(datetime.now(timezone.utc))
    if is_unusual:
        anomalies.append({
            'type': 'unusual_login_time',
            'severity': 'low',
            'reason': reason,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    # Check rapid login attempts
    is_suspicious, reason = detect_rapid_login_attempts(user_id)
    if is_suspicious:
        anomalies.append({
            'type': 'rapid_login_attempts',
            'severity': 'high',
            'reason': reason,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    # Check impossible travel
    is_suspicious, reason = detect_impossible_travel(user_id, ip_address)
    if is_suspicious:
        anomalies.append({
            'type': 'impossible_travel',
            'severity': 'critical',
            'reason': reason,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    # Check suspicious IP
    is_suspicious, reason = is_suspicious_ip(ip_address)
    if is_suspicious:
        anomalies.append({
            'type': 'suspicious_ip',
            'severity': 'medium',
            'reason': reason,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    return anomalies


def check_upload_anomalies(user_id: int, file_size_bytes: int) -> List[Dict]:
    """
    Comprehensive file upload anomaly detection.

    Args:
        user_id: User ID
        file_size_bytes: Size of uploaded file

    Returns:
        List of detected anomalies with severity and details
    """
    anomalies = []

    # Check large file upload
    is_suspicious, reason = detect_large_file_upload(file_size_bytes, user_id)
    if is_suspicious:
        severity = 'critical' if file_size_bytes > (5 * 1024 * 1024 * 1024) else 'high'
        anomalies.append({
            'type': 'large_file_upload',
            'severity': severity,
            'reason': reason,
            'file_size_mb': file_size_bytes / (1024 * 1024),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    return anomalies


def check_migration_anomalies(user_id: int) -> List[Dict]:
    """
    Comprehensive migration activity anomaly detection.

    Args:
        user_id: User ID

    Returns:
        List of detected anomalies with severity and details
    """
    anomalies = []

    # Check rapid migrations
    is_suspicious, reason = detect_rapid_migrations(user_id)
    if is_suspicious:
        anomalies.append({
            'type': 'rapid_migrations',
            'severity': 'high',
            'reason': reason,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    return anomalies


def log_anomaly(user_id: int, anomaly: Dict) -> None:
    """
    Log detected anomaly for security monitoring and alerting.

    Args:
        user_id: User ID
        anomaly: Anomaly details dictionary
    """
    # Log to application logs
    logger.warning(
        f"ANOMALY DETECTED - User: {user_id}, Type: {anomaly['type']}, "
        f"Severity: {anomaly['severity']}, Reason: {anomaly['reason']}"
    )

    # In production, this would also:
    # 1. Store in anomaly_events table for historical analysis
    # 2. Send alerts for critical/high severity anomalies
    # 3. Trigger automated responses (e.g., require 2FA, lock account)
    # 4. Update user risk score

    # For critical anomalies, could trigger immediate action
    if anomaly['severity'] == 'critical':
        logger.critical(f"CRITICAL ANOMALY - Immediate review required: {anomaly}")
        # In production: Send email/Slack alert to security team
