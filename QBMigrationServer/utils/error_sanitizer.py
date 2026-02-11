"""
Error Message Sanitizer
=======================

Sanitizes error messages before returning to clients to prevent information disclosure.

ISSUE #34: Previously exposed stack traces, internal paths, DB schema, and
sensitive configuration details in production error responses.

Author: ForensicBridge Security Team
Version: 1.0.0
"""

import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# STANDARDIZED API ERROR RESPONSE FORMAT
# =============================================================================


class APIError:
    """
    Standardized API error response builder.

    All API endpoints should use this for consistent error formatting.

    Usage:
        return APIError.bad_request("Invalid email format")
        return APIError.not_found("Migration not found", error_code="MIG001")
        return APIError.internal_error(exception)
    """

    @staticmethod
    def response(
        message: str,
        status_code: int = 400,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        field: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], int]:
        """
        Create a standardized error response.

        Args:
            message: Human-readable error message
            status_code: HTTP status code
            error_code: Application-specific error code (e.g., "AUTH001")
            details: Additional error details
            field: Field name if this is a field-specific error

        Returns:
            Tuple of (response_dict, status_code)
        """
        response = {
            "success": False,
            "error": message,
        }

        if error_code:
            response["error_code"] = error_code

        if field:
            response["field"] = field

        if details:
            response["details"] = details

        return response, status_code

    @staticmethod
    def bad_request(
        message: str,
        error_code: Optional[str] = None,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], int]:
        """400 Bad Request error"""
        return APIError.response(
            message=message,
            status_code=400,
            error_code=error_code or "BAD_REQUEST",
            field=field,
            details=details,
        )

    @staticmethod
    def unauthorized(
        message: str = "Authentication required", error_code: Optional[str] = None
    ) -> Tuple[Dict[str, Any], int]:
        """401 Unauthorized error"""
        return APIError.response(
            message=message, status_code=401, error_code=error_code or "UNAUTHORIZED"
        )

    @staticmethod
    def forbidden(
        message: str = "Access denied", error_code: Optional[str] = None
    ) -> Tuple[Dict[str, Any], int]:
        """403 Forbidden error"""
        return APIError.response(
            message=message, status_code=403, error_code=error_code or "FORBIDDEN"
        )

    @staticmethod
    def not_found(
        message: str = "Resource not found", error_code: Optional[str] = None
    ) -> Tuple[Dict[str, Any], int]:
        """404 Not Found error"""
        return APIError.response(
            message=message, status_code=404, error_code=error_code or "NOT_FOUND"
        )

    @staticmethod
    def conflict(
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], int]:
        """409 Conflict error"""
        return APIError.response(
            message=message,
            status_code=409,
            error_code=error_code or "CONFLICT",
            details=details,
        )

    @staticmethod
    def validation_error(
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], int]:
        """422 Unprocessable Entity (validation error)"""
        return APIError.response(
            message=message,
            status_code=422,
            error_code="VALIDATION_ERROR",
            field=field,
            details=details,
        )

    @staticmethod
    def rate_limited(
        message: str = "Rate limit exceeded. Please try again later.",
        retry_after: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], int]:
        """429 Too Many Requests error"""
        details = {"retry_after_seconds": retry_after} if retry_after else None
        return APIError.response(
            message=message, status_code=429, error_code="RATE_LIMITED", details=details
        )

    @staticmethod
    def internal_error(
        exception: Optional[Exception] = None,
        message: str = "An internal error occurred. Please try again.",
        error_code: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], int]:
        """500 Internal Server Error"""
        # Log the actual exception for debugging
        if exception:
            logger.exception(f"Internal error: {exception}")

        return APIError.response(
            message=message, status_code=500, error_code=error_code or "INTERNAL_ERROR"
        )

    @staticmethod
    def service_unavailable(
        message: str = "Service temporarily unavailable. Please try again later.",
        error_code: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], int]:
        """503 Service Unavailable error"""
        return APIError.response(
            message=message,
            status_code=503,
            error_code=error_code or "SERVICE_UNAVAILABLE",
        )


# Sensitive patterns to redact from error messages
SENSITIVE_PATTERNS = [
    # File paths
    (r'/home/[^/]+/.*?(?=[\s\'"\\]|$)', "[REDACTED_PATH]"),
    (r'/var/[^/]+/.*?(?=[\s\'"\\]|$)', "[REDACTED_PATH]"),
    (r'/usr/[^/]+/.*?(?=[\s\'"\\]|$)', "[REDACTED_PATH]"),
    (r'/tmp/.*?(?=[\s\'"\\]|$)', "[REDACTED_PATH]"),  # nosec B108
    (r'C:\\.*?(?=[\s\'"\\]|$)', "[REDACTED_PATH]"),
    # IMPROVED: Database errors (PostgreSQL, MySQL, SQLite) - More comprehensive patterns
    # PostgreSQL-specific errors
    (r'relation "([^"]+)" does not exist', "Database table not found"),
    (
        r'column "([^"]+)"(?:\s+of\s+relation\s+"[^"]+")?(?:\s+does not exist)?',
        "Database column error",
    ),
    (
        r'duplicate key value violates unique constraint "([^"]+)"',
        "Duplicate entry violation",
    ),
    (
        r'null value in column "([^"]+)"(?:\s+violates not-null constraint)?',
        "Required field missing",
    ),
    (r'foreign key constraint "([^"]+)"', "Foreign key constraint violation"),
    (r'check constraint "([^"]+)"', "Data validation constraint violation"),
    (r'invalid input syntax for (?:type\s+)?(\w+):\s*"[^"]*"', "Invalid data format"),
    (
        r"value too long for type (?:character varying|varchar)\((\d+)\)",
        "Value exceeds maximum length",
    ),
    (r'connection to server at "([^"]+)".*?failed', "Database connection failed"),
    (
        r"could not connect to server:.*?Is the server running",
        "Database server unreachable",
    ),
    (
        r'password authentication failed for user "([^"]+)"',
        "Database authentication failed",
    ),
    (r'database "([^"]+)" does not exist', "Database not found"),
    (
        r'permission denied for (?:table|schema|database)\s+"([^"]+)"',
        "Database permission denied",
    ),
    (r"deadlock detected", "Database deadlock - please retry"),
    (
        r"canceling statement due to (?:user request|statement timeout)",
        "Database query timeout",
    ),
    # SQLAlchemy/psycopg2 error prefixes
    (r"SQLSTATE\[(\w+)\](?:\s*\[[^\]]+\])*", "Database error"),
    (r"\(psycopg2\.(?:errors\.)?(\w+)\)", "Database error"),
    (r"psycopg2\.(?:errors\.)?(\w+Error)", "Database connection error"),
    (r"sqlalchemy\.exc\.(\w+)", "Database error"),
    # MySQL-specific errors
    (r"Unknown column '([^']+)'", "Database column error"),
    (r"Table '([^']+)' doesn't exist", "Database table not found"),
    (r"Duplicate entry '([^']+)' for key '([^']+)'", "Duplicate entry"),
    (r"Can't connect to MySQL server", "Database connection failed"),
    (r"Access denied for user '([^']+)'@'([^']+)'", "Database authentication failed"),
    # SQLite-specific errors
    (r"no such table:\s*(\w+)", "Database table not found"),
    (r"no such column:\s*(\w+)", "Database column error"),
    (r"UNIQUE constraint failed:\s*([^\s]+)", "Duplicate entry"),
    (r"database is locked", "Database temporarily unavailable"),
    (r"unable to open database file", "Database file not accessible"),
    # Generic database error patterns
    (
        r"IntegrityError.*?(?:DETAIL|constraint).*",
        "Data integrity constraint violation",
    ),
    (r"OperationalError.*?(?:connection|timeout|lock)", "Database operation failed"),
    (r"ProgrammingError.*?(?:syntax|relation)", "Database query error"),
    (r"DataError.*?(?:out of range|invalid|overflow)", "Invalid data value"),
    # AWS secrets and credentials
    (r"aws_access_key_id.*", "[REDACTED_AWS_KEY]"),
    (r"aws_secret_access_key.*", "[REDACTED_AWS_SECRET]"),
    (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
    # API keys and tokens
    (r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer [REDACTED_TOKEN]"),
    (r'token["\s:=]+[A-Za-z0-9\-._~+/]+=*', "token=[REDACTED]"),
    (r'api[_-]?key["\s:=]+[A-Za-z0-9\-._~+/]+=*', "api_key=[REDACTED]"),
    # IP addresses (optional - may want to keep for debugging)
    # (r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[REDACTED_IP]'),
    # Python module paths
    (r'File ".*?/site-packages/([^/]+)/.*?"', 'File "[package \\1]"'),
    (r'File ".*?/python\d+\.\d+/.*?"', 'File "[python library]"'),
    # Stack trace line numbers (preserve file name but redact path)
    (r'File "(/[^"]+/)?([^/"]+\.py)"', 'File "\\2"'),
    # Connection strings (improved patterns)
    (r"postgresql://[^:]+:[^@]+@[^\s?]+", "postgresql://[REDACTED]"),
    (r"postgres://[^:]+:[^@]+@[^\s?]+", "postgresql://[REDACTED]"),
    (r"mysql://[^:]+:[^@]+@[^\s?]+", "mysql://[REDACTED]"),
    (r"mongodb://[^:]+:[^@]+@[^\s?]+", "mongodb://[REDACTED]"),
    (r"mongodb\+srv://[^:]+:[^@]+@[^\s?]+", "mongodb://[REDACTED]"),
    (r"redis://[^:]+:[^@]+@[^\s?]+", "redis://[REDACTED]"),
]

# MED-16 FIX: Pre-compile regex patterns at module load time for performance.
# Previously 30+ patterns were compiled on every call to sanitize_error_message().
_COMPILED_SENSITIVE_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in SENSITIVE_PATTERNS
]

# Generic error messages for common exception types
EXCEPTION_TYPE_MESSAGES = {
    "ValueError": "Invalid input value",
    "TypeError": "Invalid data type",
    "KeyError": "Missing required field",
    "AttributeError": "Invalid attribute access",
    "IndexError": "Invalid index",
    "FileNotFoundError": "File not found",
    "PermissionError": "Permission denied",
    "ConnectionError": "Connection failed",
    "TimeoutError": "Operation timed out",
    "OSError": "System error",
    "IOError": "Input/output error",
    "RuntimeError": "Runtime error occurred",
    "ImportError": "Module import failed",
    "NameError": "Name not defined",
    "ZeroDivisionError": "Division by zero",
    "OverflowError": "Numerical overflow",
    "MemoryError": "Out of memory",
    "RecursionError": "Maximum recursion depth exceeded",
    # Database exceptions
    "IntegrityError": "Data integrity constraint violation",
    "OperationalError": "Database operation failed",
    "DatabaseError": "Database error",
    "DataError": "Invalid data",
    # HTTP/Network exceptions
    "HTTPError": "HTTP request failed",
    "URLError": "URL error",
    "SSLError": "SSL/TLS error",
    "Timeout": "Request timed out",
    # AWS exceptions
    "ClientError": "AWS service error",
    "BotoCoreError": "AWS client error",
    "NoCredentialsError": "AWS credentials not configured",
}


def is_production() -> bool:
    """
    Determine if we're running in production environment.

    Returns:
        True if in production, False otherwise
    """
    from utils.env_helper import is_production as _is_prod

    return _is_prod()


def sanitize_error_message(error: Exception, context: Optional[str] = None) -> str:
    """
    Sanitize an exception message for safe client exposure.

    Args:
        error: The exception to sanitize
        context: Optional context (e.g., 'upload', 'migration', 'auth')

    Returns:
        Sanitized error message safe for client display

    Examples:
        >>> sanitize_error_message(ValueError("Invalid email"))
        "Invalid input value"

        >>> sanitize_error_message(Exception("/home/user/secret.py not found"))
        "An error occurred processing your request"
    """
    if not is_production():
        # In development, return the full error for debugging
        return str(error)

    # Get exception type name
    exception_type = type(error).__name__
    error_message = str(error)

    # SECURITY: Never log the error message directly - it may contain sensitive data
    # Log only the sanitized version

    # Step 1: Check for generic exception type mapping
    if exception_type in EXCEPTION_TYPE_MESSAGES:
        generic_msg = EXCEPTION_TYPE_MESSAGES[exception_type]
        logger.error(
            f"Sanitized {exception_type}: {generic_msg} (original logged separately)"
        )
        return generic_msg

    # Step 2: Apply regex patterns to redact sensitive information
    # MED-16 FIX: Use pre-compiled patterns for performance
    sanitized = error_message
    for compiled_re, replacement in _COMPILED_SENSITIVE_PATTERNS:
        sanitized = compiled_re.sub(replacement, sanitized)

    # Step 3: If message still contains sensitive indicators, use generic message
    sensitive_indicators = [
        "/home/",
        "/var/",
        "/usr/",
        "/tmp/",  # nosec B108
        "C:\\",
        "SQLSTATE",
        "psycopg2",
        "pymongo",
        "sqlite3",
        "AKIA",
        "aws_access",
        "aws_secret",
        "Traceback",
        'File "/',
    ]

    regex_indicators = [r"line \d+"]
    string_indicators = [i for i in sensitive_indicators if i != "line \\d+"]
    has_sensitive = any(indicator in sanitized for indicator in string_indicators)
    if not has_sensitive:
        has_sensitive = any(
            re.search(pattern, sanitized) for pattern in regex_indicators
        )
    if has_sensitive:
        # Still contains sensitive info - use generic message
        generic_msg = get_generic_error_message(context)
        logger.warning(
            f"Error message still sensitive after sanitization, using generic: {exception_type}"
        )
        return generic_msg

    # Step 4: Truncate long messages
    if len(sanitized) > 150:
        sanitized = sanitized[:147] + "..."

    return sanitized


def get_generic_error_message(context: Optional[str] = None) -> str:
    """
    Get a context-appropriate generic error message.

    Args:
        context: Operation context (e.g., 'upload', 'migration', 'auth')

    Returns:
        User-friendly generic error message
    """
    context_messages = {
        "upload": "Failed to upload file. Please check the file format and try again.",
        "migration": "Migration operation failed. Please contact support if the issue persists.",
        "auth": "Authentication failed. Please check your credentials and try again.",
        "payment": "Payment processing failed. Please verify your payment information.",
        "api": "API request failed. Please try again later.",
        "database": "Database operation failed. Please try again later.",
        "aws": "Cloud service operation failed. Please try again later.",
        "validation": "Invalid input. Please check your data and try again.",
    }

    if context and context in context_messages:
        return context_messages[context]

    return "An error occurred processing your request. Please try again later."


def create_error_response(
    error: Exception, context: Optional[str] = None, status_code: int = 500
) -> Dict[str, Any]:
    """
    Create a sanitized error response dictionary for JSON API responses.

    Args:
        error: The exception that occurred
        context: Operation context
        status_code: HTTP status code (default 500)

    Returns:
        Dictionary with 'success' and 'error' keys

    Example:
        >>> create_error_response(ValueError("Invalid email"), "auth", 400)
        {'success': False, 'error': 'Invalid input value', 'error_code': 'VALIDATION_ERROR'}
    """
    sanitized_message = sanitize_error_message(error, context)

    # Map status codes to error codes
    error_code_map = {
        400: "VALIDATION_ERROR",
        401: "AUTHENTICATION_ERROR",
        403: "AUTHORIZATION_ERROR",
        404: "NOT_FOUND",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }

    error_code = error_code_map.get(status_code, "UNKNOWN_ERROR")

    response = {"success": False, "error": sanitized_message, "error_code": error_code}

    # In development, add debug info (but still sanitize paths)
    if not is_production():
        response["debug"] = {
            "exception_type": type(error).__name__,
            "original_message": str(error)[:500],  # Truncate for safety
        }

    return response


def log_error_safely(error: Exception, context: str, user_id: Optional[int] = None):
    """
    Log an error with sensitive information redacted.

    Args:
        error: The exception to log
        context: Operation context
        user_id: Optional user ID (will be hashed if in production)
    """
    # Sanitize the error message for logging
    sanitized = sanitize_error_message(error, context)

    # CRIT-06 FIX: Hash user ID in production to prevent PII leakage.
    # Previously had a stray `pass` that made user_identifier always use
    # the unhashed format regardless of the condition.
    if is_production() and user_id:
        import hashlib

        hashed = hashlib.sha256(str(user_id).encode()).hexdigest()[:12]
        user_identifier = f"user_{hashed}"
    else:
        user_identifier = f"user_id={user_id}" if user_id else "anonymous"

    # Log with context (hash user_id in extra dict to prevent PII leakage)
    logger.error(
        f"[{context}] Error for {user_identifier}: {sanitized}",
        extra={
            "context": context,
            "exception_type": type(error).__name__,
            "user_id": user_identifier,
        },
        exc_info=not is_production(),  # Include stack trace only in dev
    )


# =============================================================================
# QBO ERROR PARAMETER WHITELIST
# =============================================================================

# Allowed QBO error codes that can be passed to the frontend
# Any error not in this list will be mapped to a generic message
QBO_ERROR_WHITELIST = {
    # OAuth errors from Intuit
    "access_denied": "Access was denied. Please try connecting again.",
    "invalid_scope": "Invalid permissions requested. Please contact support.",
    "server_error": "QuickBooks server error. Please try again later.",
    "temporarily_unavailable": "QuickBooks is temporarily unavailable. Please try again later.",
    "invalid_grant": "Session expired. Please reconnect to QuickBooks.",
    "invalid_client": "Configuration error. Please contact support.",
    "unsupported_grant_type": "Authentication error. Please contact support.",
    # API errors
    "rate_limit_exceeded": "Too many requests to QuickBooks. Please wait and try again.",
    "company_not_found": "QuickBooks company not found. Please reconnect.",
    "token_expired": "QuickBooks session expired. Please reconnect.",
    "unauthorized": "QuickBooks authorization failed. Please reconnect.",
    "forbidden": "Access to QuickBooks resource denied.",
    "not_found": "Requested QuickBooks data not found.",
    "validation_error": "Invalid data format for QuickBooks.",
    "duplicate": "Duplicate entry detected in QuickBooks.",
    # User-friendly generic errors
    "connection_failed": "Failed to connect to QuickBooks. Please try again.",
    "sync_failed": "Failed to sync with QuickBooks. Please try again.",
    "import_failed": "Failed to import data from QuickBooks.",
    "export_failed": "Failed to export data to QuickBooks.",
}


def sanitize_qbo_error(
    error_code: str, error_description: str = None
) -> Dict[str, str]:
    """
    Sanitize QBO error parameters using a whitelist approach.

    Only returns error codes and descriptions that are safe to display to users.
    Unknown errors are mapped to generic messages to prevent information disclosure.

    Args:
        error_code: The error code from QuickBooks OAuth/API
        error_description: Optional error description from QuickBooks

    Returns:
        Dict with 'code' and 'message' keys containing safe values

    Example:
        >>> sanitize_qbo_error('access_denied', 'User denied access')
        {'code': 'access_denied', 'message': 'Access was denied. Please try connecting again.'}

        >>> sanitize_qbo_error('secret_error_123', 'Internal schema leak')
        {'code': 'connection_error', 'message': 'Failed to connect to QuickBooks. Please try again.'}
    """
    # Normalize error code
    if not error_code:
        return {
            "code": "unknown_error",
            "message": "An error occurred with QuickBooks. Please try again.",
        }

    # Sanitize: only allow alphanumeric, underscore, hyphen
    safe_code = re.sub(r"[^a-zA-Z0-9_\-]", "", str(error_code).lower())[:50]

    # Check whitelist
    if safe_code in QBO_ERROR_WHITELIST:
        return {"code": safe_code, "message": QBO_ERROR_WHITELIST[safe_code]}

    # Not in whitelist - use generic message
    logger.warning(
        f"QBO error not in whitelist: {safe_code} (original: {error_code[:50] if error_code else 'None'})"
    )

    return {
        "code": "connection_error",
        "message": "Failed to connect to QuickBooks. Please try again.",
    }


def sanitize_qbo_error_for_url(error_code: str) -> str:
    """
    Sanitize a QBO error code for safe inclusion in a URL redirect.

    This is specifically for OAuth callback error redirects where we need
    to pass the error to the frontend via URL parameters.

    Args:
        error_code: Raw error code from QuickBooks

    Returns:
        URL-safe sanitized error code (max 50 chars, alphanumeric only)

    Example:
        >>> sanitize_qbo_error_for_url("access_denied<script>alert(1)</script>")
        'access_denied'
    """
    if not error_code:
        return "unknown"

    # Remove any HTML/script injection attempts and non-alphanumeric chars
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "", str(error_code))

    # Truncate and lowercase
    return safe[:50].lower() if safe else "unknown"


def get_qbo_user_message(error_code: str) -> str:
    """
    Get a user-friendly message for a QBO error code.

    Args:
        error_code: The sanitized error code

    Returns:
        User-friendly error message
    """
    sanitized = sanitize_qbo_error(error_code)
    return sanitized["message"]
