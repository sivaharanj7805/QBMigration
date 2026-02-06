"""
Shared utilities and configurations for QBMigration platform.

This package contains cross-component utilities:
- logging_config: Centralized logging configuration (FIX XC-02)
- api_version: API versioning utilities (FIX XC-03)
- error_codes: Centralized error code registry (FIX XC-04)
"""

from .logging_config import configure_logging, get_logger
from .api_version import (
    API_VERSION,
    check_version_compatibility,
    get_deprecation_warnings,
    VERSION_HEADER,
    CLIENT_VERSION_HEADER,
)
from .error_codes import ErrorCode, get_error_message, create_error_response

__all__ = [
    # Logging
    "configure_logging",
    "get_logger",
    # API Version
    "API_VERSION",
    "check_version_compatibility",
    "get_deprecation_warnings",
    "VERSION_HEADER",
    "CLIENT_VERSION_HEADER",
    # Error Codes
    "ErrorCode",
    "get_error_message",
    "create_error_response",
]

__version__ = API_VERSION
