"""
DateTime Utilities
==================
Future-proof datetime utilities that avoid deprecated functions.

Python 3.12+ deprecates datetime.now(timezone.utc) in favor of datetime.now(timezone.utc).
This module provides drop-in replacements that work across Python versions.

Usage:
    from utils.datetime_utils import utcnow, utcnow_iso, make_aware

    # Instead of datetime.now(timezone.utc)
    now = utcnow()

    # ISO format string
    iso_str = utcnow_iso()

    # Make a naive datetime timezone-aware
    aware_dt = make_aware(naive_dt)
"""

import warnings
from datetime import datetime, timezone, timedelta
from typing import Optional

# Try to import zoneinfo for timezone support (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


def utcnow() -> datetime:
    """
    Get current UTC time as a timezone-aware datetime.

    This is the replacement for the deprecated datetime.now(timezone.utc).

    Returns:
        Timezone-aware datetime in UTC
    """
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    """
    Get current UTC time as a naive datetime (no timezone info).

    Use this when you need compatibility with systems that don't handle
    timezone-aware datetimes well (some databases, legacy code).

    Returns:
        Naive datetime representing current UTC time
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcnow_iso() -> str:
    """
    Get current UTC time as an ISO 8601 string.

    Returns:
        ISO format string (e.g., "2024-01-15T10:30:00+00:00")
    """
    return utcnow().isoformat()


def utcnow_timestamp() -> float:
    """
    Get current UTC time as a Unix timestamp.

    Returns:
        Unix timestamp (seconds since epoch)
    """
    return utcnow().timestamp()


def utcnow_timestamp_ms() -> int:
    """
    Get current UTC time as a Unix timestamp in milliseconds.

    Returns:
        Unix timestamp in milliseconds
    """
    return int(utcnow().timestamp() * 1000)


def make_aware(dt: datetime, tz: Optional[timezone] = None) -> datetime:
    """
    Make a naive datetime timezone-aware.

    Args:
        dt: Naive datetime to make aware
        tz: Timezone to use (default: UTC)

    Returns:
        Timezone-aware datetime
    """
    if dt.tzinfo is not None:
        return dt  # Already aware

    return dt.replace(tzinfo=tz or timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """
    Ensure a datetime is in UTC.

    Args:
        dt: Datetime to convert (can be naive or aware)

    Returns:
        Timezone-aware datetime in UTC
    """
    if dt.tzinfo is None:
        # Assume naive datetimes are UTC
        return dt.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC
        return dt.astimezone(timezone.utc)


def from_timestamp(ts: float, tz: Optional[timezone] = None) -> datetime:
    """
    Create datetime from Unix timestamp.

    Args:
        ts: Unix timestamp (seconds since epoch)
        tz: Timezone for result (default: UTC)

    Returns:
        Timezone-aware datetime
    """
    return datetime.fromtimestamp(ts, tz=tz or timezone.utc)


def from_iso(iso_str: str) -> datetime:
    """
    Parse ISO 8601 datetime string.

    Args:
        iso_str: ISO format datetime string

    Returns:
        Datetime (timezone-aware if the string included timezone info)
    """
    return datetime.fromisoformat(iso_str)


def time_ago(dt: datetime) -> str:
    """
    Get human-readable time difference from now.

    Args:
        dt: Datetime to compare

    Returns:
        Human-readable string (e.g., "5 minutes ago", "2 days ago")
    """
    dt = ensure_utc(dt)
    now = utcnow()
    diff = now - dt

    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif seconds < 2592000:  # 30 days
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        months = int(seconds / 2592000)
        return f"{months} month{'s' if months != 1 else ''} ago"


def add_hours(dt: Optional[datetime] = None, hours: int = 0) -> datetime:
    """
    Add hours to a datetime.

    Args:
        dt: Starting datetime (default: now in UTC)
        hours: Hours to add (can be negative)

    Returns:
        New datetime with hours added
    """
    if dt is None:
        dt = utcnow()
    return dt + timedelta(hours=hours)


def add_days(dt: Optional[datetime] = None, days: int = 0) -> datetime:
    """
    Add days to a datetime.

    Args:
        dt: Starting datetime (default: now in UTC)
        days: Days to add (can be negative)

    Returns:
        New datetime with days added
    """
    if dt is None:
        dt = utcnow()
    return dt + timedelta(days=days)


def is_expired(dt: datetime, max_age_seconds: int) -> bool:
    """
    Check if a datetime is older than max_age_seconds from now.

    Args:
        dt: Datetime to check
        max_age_seconds: Maximum age in seconds

    Returns:
        True if expired, False otherwise
    """
    dt = ensure_utc(dt)
    age = (utcnow() - dt).total_seconds()
    return age > max_age_seconds


def is_in_future(dt: datetime) -> bool:
    """
    Check if a datetime is in the future.

    Args:
        dt: Datetime to check

    Returns:
        True if in the future, False otherwise
    """
    dt = ensure_utc(dt)
    return dt > utcnow()


# Compatibility aliases for gradual migration
def get_utc_now() -> datetime:
    """Alias for utcnow() - for compatibility."""
    return utcnow()


# Deprecation warning for old usage patterns
def _warn_deprecated_utcnow():
    """Issue deprecation warning for datetime.now(timezone.utc) usage."""
    warnings.warn(
        "datetime.now(timezone.utc) is deprecated in Python 3.12+. "
        "Use utils.datetime_utils.now(timezone.utc) instead.",
        DeprecationWarning,
        stacklevel=3
    )
