"""
FIX XC-04: Centralized Error Code Registry

This module provides consistent error codes across all components
of the QBMigration platform.

Usage:
    from shared.error_codes import ErrorCode, get_error_message

    return {"error": ErrorCode.AUTH_INVALID_TOKEN, "message": get_error_message(ErrorCode.AUTH_INVALID_TOKEN)}

Error Code Ranges:
    1000-1999: Authentication & Authorization
    2000-2999: Upload & File Operations
    3000-3999: Migration Processing
    4000-4999: QBO API Integration
    5000-5999: Data Transformation
    6000-6999: Validation Errors
    7000-7999: Infrastructure/System Errors
    8000-8999: License & Billing
    9000-9999: Reserved for future use
"""

from enum import IntEnum
from typing import Dict


class ErrorCode(IntEnum):
    """Centralized error codes for QBMigration platform."""

    # =========================================================================
    # 1000-1999: Authentication & Authorization
    # =========================================================================
    AUTH_INVALID_CREDENTIALS = 1001
    AUTH_INVALID_TOKEN = 1002
    AUTH_TOKEN_EXPIRED = 1003
    AUTH_INSUFFICIENT_PERMISSIONS = 1004
    AUTH_ACCOUNT_LOCKED = 1005
    AUTH_MFA_REQUIRED = 1006
    AUTH_SESSION_EXPIRED = 1007

    # =========================================================================
    # 2000-2999: Upload & File Operations
    # =========================================================================
    UPLOAD_FILE_TOO_LARGE = 2001
    UPLOAD_INVALID_FORMAT = 2002
    UPLOAD_CHECKSUM_MISMATCH = 2003
    UPLOAD_INCOMPLETE = 2004
    UPLOAD_CHUNK_MISSING = 2005
    UPLOAD_S3_ERROR = 2006
    UPLOAD_ENCRYPTION_ERROR = 2007
    UPLOAD_DECRYPTION_ERROR = 2008
    UPLOAD_DUPLICATE_DETECTED = 2009

    # =========================================================================
    # 3000-3999: Migration Processing
    # =========================================================================
    MIGRATION_NOT_FOUND = 3001
    MIGRATION_ALREADY_PROCESSING = 3002
    MIGRATION_ALREADY_COMPLETED = 3003
    MIGRATION_FAILED = 3004
    MIGRATION_CANCELLED = 3005
    MIGRATION_TIMEOUT = 3006
    MIGRATION_DATA_CORRUPT = 3007
    MIGRATION_TRIAL_BALANCE_MISMATCH = 3008

    # =========================================================================
    # 4000-4999: QBO API Integration
    # =========================================================================
    QBO_AUTH_FAILED = 4001
    QBO_TOKEN_EXPIRED = 4002
    QBO_RATE_LIMITED = 4003
    QBO_API_ERROR = 4004
    QBO_ENTITY_NOT_FOUND = 4005
    QBO_VALIDATION_ERROR = 4006
    QBO_SYNC_CONFLICT = 4007
    QBO_COMPANY_MISMATCH = 4008

    # =========================================================================
    # 5000-5999: Data Transformation
    # =========================================================================
    TRANSFORM_INVALID_SCHEMA = 5001
    TRANSFORM_MAPPING_ERROR = 5002
    TRANSFORM_MISSING_REQUIRED = 5003
    TRANSFORM_TYPE_MISMATCH = 5004
    TRANSFORM_DATE_PARSE_ERROR = 5005
    TRANSFORM_AMOUNT_OVERFLOW = 5006
    TRANSFORM_REFERENCE_NOT_FOUND = 5007

    # =========================================================================
    # 6000-6999: Validation Errors
    # =========================================================================
    VALIDATION_MISSING_FIELD = 6001
    VALIDATION_INVALID_FORMAT = 6002
    VALIDATION_OUT_OF_RANGE = 6003
    VALIDATION_CONSTRAINT_VIOLATION = 6004
    VALIDATION_DUPLICATE_VALUE = 6005

    # =========================================================================
    # 7000-7999: Infrastructure/System Errors
    # =========================================================================
    SYSTEM_DATABASE_ERROR = 7001
    SYSTEM_REDIS_ERROR = 7002
    SYSTEM_S3_ERROR = 7003
    SYSTEM_WORKER_UNAVAILABLE = 7004
    SYSTEM_INTERNAL_ERROR = 7500

    # =========================================================================
    # 8000-8999: License & Billing
    # =========================================================================
    LICENSE_INVALID = 8001
    LICENSE_EXPIRED = 8002
    LICENSE_MIGRATIONS_EXHAUSTED = 8003
    LICENSE_TIER_INSUFFICIENT = 8004
    PAYMENT_FAILED = 8005
    PAYMENT_REFUNDED = 8006


# Error message registry
ERROR_MESSAGES: Dict[ErrorCode, str] = {
    # Auth errors
    ErrorCode.AUTH_INVALID_CREDENTIALS: "Invalid username or password",
    ErrorCode.AUTH_INVALID_TOKEN: "Invalid or malformed authentication token",
    ErrorCode.AUTH_TOKEN_EXPIRED: "Authentication token has expired",
    ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS: "You do not have permission to perform this action",
    ErrorCode.AUTH_ACCOUNT_LOCKED: "Account is locked due to too many failed attempts",
    ErrorCode.AUTH_MFA_REQUIRED: "Multi-factor authentication is required",
    ErrorCode.AUTH_SESSION_EXPIRED: "Session has expired, please log in again",

    # Upload errors
    ErrorCode.UPLOAD_FILE_TOO_LARGE: "File exceeds maximum allowed size",
    ErrorCode.UPLOAD_INVALID_FORMAT: "File format is not supported",
    ErrorCode.UPLOAD_CHECKSUM_MISMATCH: "File checksum does not match - data may be corrupted",
    ErrorCode.UPLOAD_INCOMPLETE: "Upload was not completed successfully",
    ErrorCode.UPLOAD_CHUNK_MISSING: "One or more upload chunks are missing",
    ErrorCode.UPLOAD_S3_ERROR: "Failed to store file in cloud storage",
    ErrorCode.UPLOAD_ENCRYPTION_ERROR: "Failed to encrypt file data",
    ErrorCode.UPLOAD_DECRYPTION_ERROR: "Failed to decrypt file data",
    ErrorCode.UPLOAD_DUPLICATE_DETECTED: "This file has already been uploaded",

    # Migration errors
    ErrorCode.MIGRATION_NOT_FOUND: "Migration not found",
    ErrorCode.MIGRATION_ALREADY_PROCESSING: "Migration is already being processed",
    ErrorCode.MIGRATION_ALREADY_COMPLETED: "Migration has already been completed",
    ErrorCode.MIGRATION_FAILED: "Migration processing failed",
    ErrorCode.MIGRATION_CANCELLED: "Migration was cancelled",
    ErrorCode.MIGRATION_TIMEOUT: "Migration processing timed out",
    ErrorCode.MIGRATION_DATA_CORRUPT: "Migration data appears to be corrupted",
    ErrorCode.MIGRATION_TRIAL_BALANCE_MISMATCH: "Trial balance does not match between source and destination",

    # QBO errors
    ErrorCode.QBO_AUTH_FAILED: "Failed to authenticate with QuickBooks Online",
    ErrorCode.QBO_TOKEN_EXPIRED: "QuickBooks Online access token has expired",
    ErrorCode.QBO_RATE_LIMITED: "QuickBooks Online API rate limit exceeded",
    ErrorCode.QBO_API_ERROR: "QuickBooks Online API returned an error",
    ErrorCode.QBO_ENTITY_NOT_FOUND: "Entity not found in QuickBooks Online",
    ErrorCode.QBO_VALIDATION_ERROR: "QuickBooks Online validation error",
    ErrorCode.QBO_SYNC_CONFLICT: "Sync conflict detected with QuickBooks Online",
    ErrorCode.QBO_COMPANY_MISMATCH: "QuickBooks company does not match expected company",

    # Transform errors
    ErrorCode.TRANSFORM_INVALID_SCHEMA: "Data schema is invalid or unsupported",
    ErrorCode.TRANSFORM_MAPPING_ERROR: "Failed to map data between formats",
    ErrorCode.TRANSFORM_MISSING_REQUIRED: "Required field is missing",
    ErrorCode.TRANSFORM_TYPE_MISMATCH: "Data type does not match expected type",
    ErrorCode.TRANSFORM_DATE_PARSE_ERROR: "Failed to parse date value",
    ErrorCode.TRANSFORM_AMOUNT_OVERFLOW: "Amount exceeds maximum supported value",
    ErrorCode.TRANSFORM_REFERENCE_NOT_FOUND: "Referenced entity was not found",

    # Validation errors
    ErrorCode.VALIDATION_MISSING_FIELD: "Required field is missing",
    ErrorCode.VALIDATION_INVALID_FORMAT: "Field format is invalid",
    ErrorCode.VALIDATION_OUT_OF_RANGE: "Value is outside allowed range",
    ErrorCode.VALIDATION_CONSTRAINT_VIOLATION: "Value violates constraint",
    ErrorCode.VALIDATION_DUPLICATE_VALUE: "Value already exists",

    # System errors
    ErrorCode.SYSTEM_DATABASE_ERROR: "Database operation failed",
    ErrorCode.SYSTEM_REDIS_ERROR: "Cache operation failed",
    ErrorCode.SYSTEM_S3_ERROR: "Cloud storage operation failed",
    ErrorCode.SYSTEM_WORKER_UNAVAILABLE: "Background worker is unavailable",
    ErrorCode.SYSTEM_INTERNAL_ERROR: "An internal error occurred",

    # License errors
    ErrorCode.LICENSE_INVALID: "License is invalid",
    ErrorCode.LICENSE_EXPIRED: "License has expired",
    ErrorCode.LICENSE_MIGRATIONS_EXHAUSTED: "No migrations remaining on license",
    ErrorCode.LICENSE_TIER_INSUFFICIENT: "License tier does not support this feature",
    ErrorCode.PAYMENT_FAILED: "Payment processing failed",
    ErrorCode.PAYMENT_REFUNDED: "Payment was refunded",
}


def get_error_message(code: ErrorCode) -> str:
    """Get the human-readable message for an error code."""
    return ERROR_MESSAGES.get(code, "An unknown error occurred")


def create_error_response(code: ErrorCode, details: str = None) -> dict:
    """
    Create a standardized error response.

    Args:
        code: Error code
        details: Additional error details

    Returns:
        Dict with error code, message, and optional details
    """
    response = {
        "error_code": int(code),
        "error": code.name,
        "message": get_error_message(code)
    }
    if details:
        response["details"] = details
    return response
