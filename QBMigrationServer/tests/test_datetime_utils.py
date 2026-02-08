"""Tests for utils/datetime_utils.py - UTC datetime utilities."""

from datetime import datetime, timedelta, timezone

from utils.datetime_utils import (
    add_days,
    add_hours,
    ensure_utc,
    from_iso,
    from_iso_safe,
    from_timestamp,
    get_utc_now,
    is_expired,
    is_in_future,
    make_aware,
    time_ago,
    utcnow,
    utcnow_iso,
    utcnow_naive,
    utcnow_timestamp,
    utcnow_timestamp_ms,
)


class TestUtcnow:
    """Tests for utcnow and variants."""

    def test_utcnow_returns_aware(self):
        now = utcnow()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc

    def test_utcnow_naive_returns_naive(self):
        now = utcnow_naive()
        assert now.tzinfo is None

    def test_utcnow_iso_returns_string(self):
        iso = utcnow_iso()
        assert isinstance(iso, str)
        assert "+" in iso or "Z" in iso

    def test_utcnow_timestamp_returns_float(self):
        ts = utcnow_timestamp()
        assert isinstance(ts, float)
        assert ts > 0

    def test_utcnow_timestamp_ms_returns_int(self):
        ts_ms = utcnow_timestamp_ms()
        assert isinstance(ts_ms, int)
        assert ts_ms > 0
        # ms should be ~1000x the seconds timestamp
        ts_s = utcnow_timestamp()
        assert abs(ts_ms - int(ts_s * 1000)) < 2000

    def test_get_utc_now_alias(self):
        now = get_utc_now()
        assert now.tzinfo == timezone.utc


class TestMakeAware:
    """Tests for make_aware function."""

    def test_naive_to_utc(self):
        naive = datetime(2024, 1, 15, 10, 30, 0)
        aware = make_aware(naive)
        assert aware.tzinfo == timezone.utc
        assert aware.year == 2024

    def test_already_aware(self):
        aware_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = make_aware(aware_dt)
        assert result is aware_dt  # Should return same object

    def test_custom_timezone(self):
        naive = datetime(2024, 1, 15, 10, 30, 0)
        eastern = timezone(timedelta(hours=-5))
        aware = make_aware(naive, eastern)
        assert aware.tzinfo == eastern


class TestEnsureUtc:
    """Tests for ensure_utc function."""

    def test_naive_assumed_utc(self):
        naive = datetime(2024, 1, 15, 10, 30, 0)
        result = ensure_utc(naive)
        assert result.tzinfo == timezone.utc
        assert result.hour == 10

    def test_utc_passthrough(self):
        utc_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = ensure_utc(utc_dt)
        assert result.tzinfo == timezone.utc

    def test_other_timezone_converts(self):
        eastern = timezone(timedelta(hours=-5))
        eastern_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=eastern)
        result = ensure_utc(eastern_dt)
        assert result.tzinfo == timezone.utc
        assert result.hour == 15  # 10 AM EST = 3 PM UTC


class TestFromTimestamp:
    """Tests for from_timestamp function."""

    def test_basic_timestamp(self):
        dt = from_timestamp(0)
        assert dt.year == 1970
        assert dt.tzinfo == timezone.utc

    def test_custom_timezone(self):
        eastern = timezone(timedelta(hours=-5))
        dt = from_timestamp(0, tz=eastern)
        assert dt.tzinfo == eastern


class TestFromIso:
    """Tests for from_iso and from_iso_safe."""

    def test_basic_iso(self):
        dt = from_iso("2024-01-15T10:30:00+00:00")
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_naive_iso_made_aware(self):
        dt = from_iso("2024-01-15T10:30:00")
        assert dt.tzinfo == timezone.utc

    def test_naive_iso_keep_naive(self):
        dt = from_iso("2024-01-15T10:30:00", ensure_aware=False)
        assert dt.tzinfo is None

    def test_empty_raises(self):
        try:
            from_iso("")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_from_iso_safe_valid(self):
        dt = from_iso_safe("2024-01-15T10:30:00")
        assert dt is not None
        assert dt.year == 2024

    def test_from_iso_safe_invalid(self):
        result = from_iso_safe("not-a-date")
        assert result is None

    def test_from_iso_safe_empty(self):
        result = from_iso_safe("")
        assert result is None

    def test_from_iso_safe_with_default(self):
        default = datetime(2020, 1, 1, tzinfo=timezone.utc)
        result = from_iso_safe("invalid", default=default)
        assert result == default


class TestTimeAgo:
    """Tests for time_ago function."""

    def test_just_now(self):
        result = time_ago(utcnow())
        assert result == "just now"

    def test_minutes_ago(self):
        dt = utcnow() - timedelta(minutes=5)
        result = time_ago(dt)
        assert "5 minutes ago" in result

    def test_one_minute_ago(self):
        dt = utcnow() - timedelta(minutes=1, seconds=10)
        result = time_ago(dt)
        assert "1 minute ago" in result

    def test_hours_ago(self):
        dt = utcnow() - timedelta(hours=3)
        result = time_ago(dt)
        assert "3 hours ago" in result

    def test_one_hour_ago(self):
        dt = utcnow() - timedelta(hours=1, minutes=5)
        result = time_ago(dt)
        assert "1 hour ago" in result

    def test_days_ago(self):
        dt = utcnow() - timedelta(days=5)
        result = time_ago(dt)
        assert "5 days ago" in result

    def test_months_ago(self):
        dt = utcnow() - timedelta(days=60)
        result = time_ago(dt)
        assert "month" in result


class TestAddHoursAndDays:
    """Tests for add_hours and add_days."""

    def test_add_hours_positive(self):
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        result = add_hours(base, 5)
        assert result.hour == 15

    def test_add_hours_negative(self):
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        result = add_hours(base, -5)
        assert result.hour == 5

    def test_add_hours_default_now(self):
        result = add_hours(hours=1)
        assert result > utcnow() - timedelta(minutes=1)

    def test_add_days_positive(self):
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        result = add_days(base, 10)
        assert result.day == 25

    def test_add_days_default_now(self):
        result = add_days(days=1)
        assert result > utcnow()


class TestIsExpiredAndFuture:
    """Tests for is_expired and is_in_future."""

    def test_expired(self):
        old = utcnow() - timedelta(seconds=100)
        assert is_expired(old, 50) is True

    def test_not_expired(self):
        recent = utcnow() - timedelta(seconds=10)
        assert is_expired(recent, 100) is False

    def test_in_future(self):
        future = utcnow() + timedelta(hours=1)
        assert is_in_future(future) is True

    def test_not_in_future(self):
        past = utcnow() - timedelta(hours=1)
        assert is_in_future(past) is False
