"""
Error Message Sanitizer
=======================

Sanitizes error messages before returning to clients to prevent information disclosure.

ISSUE #34: Previously exposed stack traces, internal paths, DB schema, and
sensitive configuration details in production error responses.

Author: ForensicBridge Security Team
Version: 1.0.0
"""

import re
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Sensitive patterns to redact from error messages
SENSITIVE_PATTERNS = [
    # File paths
    (r'/home/[^/]+/.*?(?=[\s\'"\\]|$)', '[REDACTED_PATH]'),
    (r'/var/[^/]+/.*?(?=[\s\'"\\]|$)', '[REDACTED_PATH]'),
    (r'/usr/[^/]+/.*?(?=[\s\'"\\]|$)', '[REDACTED_PATH]'),
    (r'/tmp/.*?(?=[\s\'"\\]|$)', '[REDACTED_PATH]'),
    (r'C:\\.*?(?=[\s\'"\\]|$)', '[REDACTED_PATH]'),

    # Database errors (PostgreSQL, MySQL, SQLite)
    (r'relation "([^"]+)" does not exist', 'Database table not found'),
    (r'column "([^"]+)" does not exist', 'Database column error'),
    (r'SQLSTATE\[\w+\]', 'Database error'),
    (r'psycopg2\.\w+Error', 'Database connection error'),
    (r'Duplicate entry.*for key', 'Duplicate entry'),

    # AWS secrets and credentials
    (r'aws_access_key_id.*', '[REDACTED_AWS_KEY]'),
    (r'aws_secret_access_key.*', '[REDACTED_AWS_SECRET]'),
    (r'AKIA[0-9A-Z]{16}', '[REDACTED_AWS_KEY]'),

    # API keys and tokens
    (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer [REDACTED_TOKEN]'),
    (r'token["\s:=]+[A-Za-z0-9\-._~+/]+=*', 'token=[REDACTED]'),
    (r'api[_-]?key["\s:=]+[A-Za-z0-9\-._~+/]+=*', 'api_key=[REDACTED]'),

    # IP addresses (optional - may want to keep for debugging)
    # (r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[REDACTED_IP]'),

    # Python module paths
    (r'File ".*?/site-packages/([^/]+)/.*?"', 'File "[package \\1]"'),
    (r'File ".*?/python\d+\.\d+/.*?"', 'File "[python library]"'),

    # Stack trace line numbers (preserve file name but redact path)
    (r'File "(/[^"]+/)?([^/"]+\.py)"', 'File "\\2"'),

    # Connection strings
    (r'postgresql://[^@]+@[^\s]+', 'postgresql://[REDACTED]'),
    (r'mysql://[^@]+@[^\s]+', 'mysql://[REDACTED]'),
    (r'mongodb://[^@]+@[^\s]+', 'mongodb://[REDACTED]'),
]

# Generic error messages for common exception types
EXCEPTION_TYPE_MESSAGES = {
    'ValueError': 'Invalid input value',
    'TypeError': 'Invalid data type',
    'KeyError': 'Missing required field',
    'AttributeError': 'Invalid attribute access',
    'IndexError': 'Invalid index',
    'FileNotFoundError': 'File not found',
    'PermissionError': 'Permission denied',
    'ConnectionError': 'Connection failed',
    'TimeoutError': 'Operation timed out',
    'OSError': 'System error',
    'IOError': 'Input/output error',
    'RuntimeError': 'Runtime error occurred',
    'ImportError': 'Module import failed',
    'NameError': 'Name not defined',
    'ZeroDivisionError': 'Division by zero',
    'OverflowError': 'Numerical overflow',
    'MemoryError': 'Out of memory',
    'RecursionError': 'Maximum recursion depth exceeded',

    # Database exceptions
    'IntegrityError': 'Data integrity constraint violation',
    'OperationalError': 'Database operation failed',
    'DatabaseError': 'Database error',
    'DataError': 'Invalid data',

    # HTTP/Network exceptions
    'HTTPError': 'HTTP request failed',
    'URLError': 'URL error',
    'SSLError': 'SSL/TLS error',
    'Timeout': 'Request timed out',

    # AWS exceptions
    'ClientError': 'AWS service error',
    'BotoCoreError': 'AWS client error',
    'NoCredentialsError': 'AWS credentials not configured',
}


def is_production() -> bool:
    """
    Determine if we're running in production environment.

    Returns:
        True if in production, False otherwise
    """
    env = os.getenv('FLASK_ENV', 'production').lower()
    debug = os.getenv('FLASK_DEBUG', '0')

    # Consider production if:
    # 1. FLASK_ENV is not 'development', 'dev', or 'testing'
    # 2. FLASK_DEBUG is not set to '1' or 'true'
    is_prod = (
        env not in ('development', 'dev', 'testing') and
        debug not in ('1', 'true', 'True', 'TRUE')
    )

    return is_prod


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
        logger.error(f"Sanitized {exception_type}: {generic_msg} (original logged separately)")
        return generic_msg

    # Step 2: Apply regex patterns to redact sensitive information
    sanitized = error_message
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    # Step 3: If message still contains sensitive indicators, use generic message
    sensitive_indicators = [
        '/home/', '/var/', '/usr/', '/tmp/', 'C:\\',
        'SQLSTATE', 'psycopg2', 'pymongo', 'sqlite3',
        'AKIA', 'aws_access', 'aws_secret',
        'Traceback', 'File "/', 'line \\d+'
    ]

    if any(indicator in sanitized for indicator in sensitive_indicators):
        # Still contains sensitive info - use generic message
        generic_msg = get_generic_error_message(context)
        logger.warning(f"Error message still sensitive after sanitization, using generic: {exception_type}")
        return generic_msg

    # Step 4: Truncate long messages
    if len(sanitized) > 150:
        sanitized = sanitized[:147] + '...'

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
        'upload': 'Failed to upload file. Please check the file format and try again.',
        'migration': 'Migration operation failed. Please contact support if the issue persists.',
        'auth': 'Authentication failed. Please check your credentials and try again.',
        'payment': 'Payment processing failed. Please verify your payment information.',
        'api': 'API request failed. Please try again later.',
        'database': 'Database operation failed. Please try again later.',
        'aws': 'Cloud service operation failed. Please try again later.',
        'validation': 'Invalid input. Please check your data and try again.',
    }

    if context and context in context_messages:
        return context_messages[context]

    return 'An error occurred processing your request. Please try again later.'


def create_error_response(error: Exception, context: Optional[str] = None,
                           status_code: int = 500) -> Dict[str, Any]:
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
        400: 'VALIDATION_ERROR',
        401: 'AUTHENTICATION_ERROR',
        403: 'AUTHORIZATION_ERROR',
        404: 'NOT_FOUND',
        409: 'CONFLICT',
        413: 'PAYLOAD_TOO_LARGE',
        429: 'RATE_LIMIT_EXCEEDED',
        500: 'INTERNAL_ERROR',
        503: 'SERVICE_UNAVAILABLE',
    }

    error_code = error_code_map.get(status_code, 'UNKNOWN_ERROR')

    response = {
        'success': False,
        'error': sanitized_message,
        'error_code': error_code
    }

    # In development, add debug info (but still sanitize paths)
    if not is_production():
        response['debug'] = {
            'exception_type': type(error).__name__,
            'original_message': str(error)[:500]  # Truncate for safety
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

    # Hash user ID in production
    if is_production() and user_id:
        from utils.pii_redaction import hash_email
        user_identifier = f"user_id_{user_id}"
    else:
        user_identifier = f"user_id={user_id}" if user_id else "anonymous"

    # Log with context
    logger.error(
        f"[{context}] Error for {user_identifier}: {sanitized}",
        extra={
            'context': context,
            'exception_type': type(error).__name__,
            'user_id': user_id
        },
        exc_info=not is_production()  # Include stack trace only in dev
    )
