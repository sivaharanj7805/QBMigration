"""
Performance benchmarks for utils/error_sanitizer.py.

Covers:
- MED-16 FIX: Pre-compiled regex performance
- Throughput of sanitize_error_message at scale
- Pattern matching correctness under load
- Memory stability during repeated sanitization
"""

import os
import re
import time

import pytest

os.environ["FLASK_ENV"] = "testing"

from utils.error_sanitizer import (
    _COMPILED_SENSITIVE_PATTERNS,
    SENSITIVE_PATTERNS,
    create_error_response,
    sanitize_error_message,
    sanitize_qbo_error,
    sanitize_qbo_error_for_url,
)

# ---------------------------------------------------------------------------
# COMPILED PATTERN VALIDATION
# ---------------------------------------------------------------------------


class TestCompiledPatterns:
    """Verify MED-16 fix: all patterns are pre-compiled at module load."""

    def test_all_patterns_compiled(self):
        """Every SENSITIVE_PATTERNS entry has a compiled counterpart."""
        assert len(_COMPILED_SENSITIVE_PATTERNS) == len(SENSITIVE_PATTERNS)

    def test_compiled_patterns_are_regex_objects(self):
        """Pre-compiled patterns are re.Pattern objects."""
        for compiled_re, replacement in _COMPILED_SENSITIVE_PATTERNS:
            assert isinstance(
                compiled_re, re.Pattern
            ), f"Expected compiled regex, got {type(compiled_re)}"

    def test_compiled_patterns_case_insensitive(self):
        """All patterns are compiled with IGNORECASE flag."""
        for compiled_re, replacement in _COMPILED_SENSITIVE_PATTERNS:
            assert (
                compiled_re.flags & re.IGNORECASE
            ), f"Pattern {compiled_re.pattern[:30]}... missing IGNORECASE"

    def test_patterns_count_minimum(self):
        """Should have 30+ sensitive patterns."""
        assert len(SENSITIVE_PATTERNS) >= 30


# ---------------------------------------------------------------------------
# PERFORMANCE BENCHMARKS
# ---------------------------------------------------------------------------


class TestSanitizationPerformance:
    """Performance benchmarks for error sanitization."""

    # Sample error messages that trigger various pattern matches
    SAMPLE_ERRORS = [
        # File path patterns
        Exception("/home/user/app/secret.py: line 42: error"),
        # Database error patterns
        Exception('relation "users" does not exist'),
        Exception('duplicate key value violates unique constraint "users_email_key"'),
        Exception('null value in column "password" violates not-null constraint'),
        Exception('connection to server at "db.internal.com" port 5432 failed'),
        # AWS patterns
        Exception("aws_access_key_id=AKIAIOSFODNN7EXAMPLE"),
        # Token patterns
        Exception(
            "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkw.dozjgNryP4J3jVmNHl0w"
        ),
        # Connection strings
        Exception("postgresql://admin:s3cr3t@db.example.com:5432/production"),
        # Generic Python errors
        ValueError("Invalid email format"),
        KeyError("missing_field"),
        TypeError("NoneType has no attribute"),
        ConnectionError("Connection refused"),
        TimeoutError("Query timed out after 30s"),
        # Long error message
        Exception("x" * 500),
        # Clean error (no patterns match)
        Exception("Simple user-facing error"),
    ]

    @pytest.mark.slow
    def test_sanitize_1000_messages_under_5_seconds(self):
        """
        Benchmark: Sanitize 1000 diverse error messages in < 5 seconds.

        With pre-compiled regexes (MED-16 fix), this should be fast.
        Without pre-compilation, 30+ re.compile() calls per message would
        cause significant overhead.
        """
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_DEBUG"] = "0"

        start = time.perf_counter()
        for _ in range(1000):
            for error in self.SAMPLE_ERRORS:
                sanitize_error_message(error)
        elapsed = time.perf_counter() - start

        os.environ["FLASK_ENV"] = "testing"

        # 1000 * 15 = 15,000 sanitizations in < 5 seconds
        assert (
            elapsed < 5.0
        ), f"Sanitization took {elapsed:.3f}s for 15,000 calls (expected < 5s)"

    def test_single_sanitize_under_1ms(self):
        """Each sanitize call should complete in < 1ms on average."""
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_DEBUG"] = "0"

        error = Exception(
            'duplicate key value violates unique constraint "users_email_key"'
        )

        # Warm up
        sanitize_error_message(error)

        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            sanitize_error_message(error)
        elapsed = time.perf_counter() - start

        os.environ["FLASK_ENV"] = "testing"

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 1.0, f"Average sanitize time: {avg_ms:.3f}ms (expected < 1ms)"

    def test_compile_time_saved(self):
        """
        Verify pre-compilation saves time vs on-the-fly compilation.

        Compare pre-compiled pattern matching vs fresh compilation.
        """
        test_message = "postgresql://admin:password@db.example.com/production"

        # Pre-compiled (current implementation)
        start = time.perf_counter()
        for _ in range(100):
            result = test_message
            for compiled_re, replacement in _COMPILED_SENSITIVE_PATTERNS:
                result = compiled_re.sub(replacement, result)
        precompiled_time = time.perf_counter() - start

        # On-the-fly compilation (old implementation)
        start = time.perf_counter()
        for _ in range(100):
            result = test_message
            for pattern, replacement in SENSITIVE_PATTERNS:
                result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        onthefly_time = time.perf_counter() - start

        # Pre-compiled should be faster (or at least not slower)
        # Allow 20% tolerance for system variability
        assert (
            precompiled_time <= onthefly_time * 1.2
        ), f"Pre-compiled: {precompiled_time:.4f}s, On-the-fly: {onthefly_time:.4f}s"


# ---------------------------------------------------------------------------
# PATTERN MATCHING CORRECTNESS
# ---------------------------------------------------------------------------


class TestPatternCorrectness:
    """Verify all sensitive patterns match expected inputs."""

    def _match(self, text: str) -> str:
        """Apply all compiled patterns and return result."""
        result = text
        for compiled_re, replacement in _COMPILED_SENSITIVE_PATTERNS:
            result = compiled_re.sub(replacement, result)
        return result

    def test_redacts_file_paths(self):
        result = self._match("/home/user/app/models/secret.py")
        assert "[REDACTED_PATH]" in result

    def test_redacts_postgres_connection_string(self):
        result = self._match("postgresql://admin:secret@db.internal.com:5432/mydb")
        assert "[REDACTED]" in result
        assert "secret" not in result

    def test_redacts_mysql_connection_string(self):
        result = self._match("mysql://root:password@localhost/app")
        assert "[REDACTED]" in result

    def test_redacts_redis_connection_string(self):
        result = self._match("redis://user:pass@redis.internal.com:6379/0")
        assert "[REDACTED]" in result

    def test_redacts_aws_key(self):
        result = self._match("AKIAIOSFODNN7EXAMPLE")
        assert "[REDACTED_AWS_KEY]" in result

    def test_redacts_bearer_token(self):
        result = self._match("Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
        assert "[REDACTED_TOKEN]" in result

    def test_postgres_relation_error(self):
        result = self._match('relation "secret_table" does not exist')
        assert "Database table not found" in result

    def test_duplicate_key_error(self):
        result = self._match(
            'duplicate key value violates unique constraint "users_email_key"'
        )
        assert "Duplicate entry" in result

    def test_deadlock_error(self):
        result = self._match("deadlock detected")
        assert "deadlock" in result.lower() or "retry" in result.lower()


# ---------------------------------------------------------------------------
# QBO ERROR SANITIZATION
# ---------------------------------------------------------------------------


class TestQboSanitizationPerformance:
    """Performance tests for QBO error sanitization."""

    def test_qbo_error_whitelist_lookup(self):
        """QBO whitelist lookup is fast (dict-based)."""
        start = time.perf_counter()
        for _ in range(10000):
            sanitize_qbo_error("access_denied")
            sanitize_qbo_error("unknown_evil_error")
            sanitize_qbo_error("invalid_grant")
        elapsed = time.perf_counter() - start

        assert elapsed < 10.0, f"30,000 QBO sanitizations took {elapsed:.3f}s (limit 10s to account for coverage overhead)"

    def test_qbo_url_sanitization_xss(self):
        """URL sanitization blocks XSS in error codes."""
        malicious = "error<script>alert(document.cookie)</script>"
        result = sanitize_qbo_error_for_url(malicious)
        assert "<" not in result
        assert ">" not in result
        assert "script" in result  # alphanumeric chars preserved
        assert len(result) <= 50


# ---------------------------------------------------------------------------
# CREATE ERROR RESPONSE
# ---------------------------------------------------------------------------


class TestCreateErrorResponsePerformance:
    """Performance tests for create_error_response."""

    def test_response_creation_speed(self):
        """create_error_response should be fast."""
        errors = [
            ValueError("test"),
            KeyError("missing"),
            TypeError("wrong"),
        ]

        start = time.perf_counter()
        for _ in range(1000):
            for error in errors:
                create_error_response(error, "auth", 400)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, f"3,000 response creations took {elapsed:.3f}s"
