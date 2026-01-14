"""
QuickBooks Migration Service - Custom Exceptions
=================================================

Centralized exception definitions for the migration service.

USAGE:
    from exceptions import (
        MigrationError,
        ValidationError,
        SecurityError,
        TransformationError,
        QBOAPIError,
        EncryptionError,
        ConfigurationError
    )

VERSION: 3.2.0
"""


# =============================================================================
# BASE EXCEPTION
# =============================================================================

class MigrationError(Exception):
    """
    Base exception for all migration-related errors.
    
    All other exceptions should inherit from this.
    """
    
    def __init__(self, message: str, code: str = None, details: dict = None):
        """
        Initialize migration error.
        
        Args:
            message: Human-readable error message
            code: Error code for programmatic handling (e.g., 'E001')
            details: Additional error context
        """
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.message = message
    
    def to_dict(self) -> dict:
        """Convert exception to dictionary for logging/API responses."""
        return {
            'error': self.__class__.__name__,
            'message': self.message,
            'code': self.code,
            'details': self.details
        }
    
    def __str__(self):
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


# =============================================================================
# SECURITY EXCEPTIONS
# =============================================================================

class SecurityError(MigrationError):
    """
    Raised for security-related failures.
    
    CRITICAL: These errors should ALWAYS abort the operation (fail-closed).
    
    Examples:
    - OAuth scope verification failed
    - Hash verification failed (data integrity)
    - Authentication failures
    - Token expiration
    """
    
    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message, code or 'SEC001', details)


class AuthenticationError(SecurityError):
    """Raised when authentication fails."""
    
    def __init__(self, message: str = "Authentication failed", details: dict = None):
        super().__init__(message, 'AUTH001', details)


class AuthorizationError(SecurityError):
    """Raised when user lacks required permissions."""
    
    def __init__(self, message: str = "Insufficient permissions", details: dict = None):
        super().__init__(message, 'AUTH002', details)


class HashVerificationError(SecurityError):
    """
    Raised when SHA-256 hash verification fails.
    
    CRITICAL: This indicates data was corrupted or tampered with.
    Migration MUST be aborted immediately.
    """
    
    def __init__(self, expected_hash: str, actual_hash: str, details: dict = None):
        message = (
            f"Data integrity check failed.\n"
            f"Expected: {expected_hash}\n"
            f"Actual:   {actual_hash}\n"
            f"The data may have been corrupted or tampered with."
        )
        details = details or {}
        details['expected_hash'] = expected_hash
        details['actual_hash'] = actual_hash
        super().__init__(message, 'SEC002', details)


# =============================================================================
# ENCRYPTION EXCEPTIONS
# =============================================================================

class EncryptionError(MigrationError):
    """Raised for encryption/decryption failures."""
    
    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message, code or 'ENC001', details)


class DecryptionError(EncryptionError):
    """Raised when decryption fails."""
    
    def __init__(self, message: str = "Decryption failed", details: dict = None):
        # Don't leak details about why decryption failed (security)
        super().__init__(message, 'ENC002', details)


class KeyManagementError(EncryptionError):
    """Raised for KMS/key vault errors."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, 'ENC003', details)


# =============================================================================
# VALIDATION EXCEPTIONS
# =============================================================================

class ValidationError(MigrationError):
    """Raised when data validation fails."""
    
    def __init__(self, message: str, field: str = None, details: dict = None):
        details = details or {}
        if field:
            details['field'] = field
        super().__init__(message, 'VAL001', details)
        self.field = field


class SchemaValidationError(ValidationError):
    """Raised when data doesn't match expected schema."""
    
    def __init__(self, message: str, schema_path: str = None, details: dict = None):
        details = details or {}
        if schema_path:
            details['schema_path'] = schema_path
        super().__init__(message, None, details)
        self.code = 'VAL002'


class TrialBalanceError(ValidationError):
    """Raised when trial balance doesn't balance."""
    
    def __init__(self, debits: str, credits: str, difference: str, details: dict = None):
        message = (
            f"Trial balance is not balanced.\n"
            f"Debits:  ${debits}\n"
            f"Credits: ${credits}\n"
            f"Difference: ${difference}"
        )
        details = details or {}
        details.update({
            'debits': debits,
            'credits': credits,
            'difference': difference
        })
        super().__init__(message, None, details)
        self.code = 'VAL003'


# =============================================================================
# TRANSFORMATION EXCEPTIONS
# =============================================================================

class TransformationError(MigrationError):
    """Raised when data transformation fails."""
    
    def __init__(self, message: str, entity_type: str = None, 
                 entity_name: str = None, details: dict = None):
        details = details or {}
        if entity_type:
            details['entity_type'] = entity_type
        if entity_name:
            details['entity_name'] = entity_name
        super().__init__(message, 'TRN001', details)
        self.entity_type = entity_type
        self.entity_name = entity_name


class EntityNotSupportedError(TransformationError):
    """Raised when an entity type is not supported for migration."""
    
    def __init__(self, entity_type: str, details: dict = None):
        message = f"Entity type '{entity_type}' is not supported for migration"
        super().__init__(message, entity_type, None, details)
        self.code = 'TRN002'


class MappingError(TransformationError):
    """Raised when ID mapping fails."""
    
    def __init__(self, entity_type: str, qbd_id: str, details: dict = None):
        message = f"Cannot find QBO ID for {entity_type} with QBD ID '{qbd_id}'"
        details = details or {}
        details['qbd_id'] = qbd_id
        super().__init__(message, entity_type, None, details)
        self.code = 'TRN003'


# =============================================================================
# API EXCEPTIONS
# =============================================================================

class QBOAPIError(MigrationError):
    """Raised for QuickBooks Online API errors."""
    
    def __init__(self, message: str, status_code: int = None, 
                 intuit_tid: str = None, details: dict = None):
        details = details or {}
        if status_code:
            details['status_code'] = status_code
        if intuit_tid:
            details['intuit_tid'] = intuit_tid
        super().__init__(message, 'API001', details)
        self.status_code = status_code
        self.intuit_tid = intuit_tid


class RateLimitError(QBOAPIError):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, retry_after: int = None, details: dict = None):
        message = "Rate limit exceeded"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        details = details or {}
        details['retry_after'] = retry_after
        super().__init__(message, 429, None, details)
        self.code = 'API002'
        self.retry_after = retry_after


class BatchError(QBOAPIError):
    """Raised when batch operation partially fails."""
    
    def __init__(self, succeeded: int, failed: int, errors: list = None, details: dict = None):
        message = f"Batch operation partially failed: {succeeded} succeeded, {failed} failed"
        details = details or {}
        details.update({
            'succeeded': succeeded,
            'failed': failed,
            'errors': errors or []
        })
        super().__init__(message, None, None, details)
        self.code = 'API003'
        self.succeeded = succeeded
        self.failed = failed
        self.errors = errors or []


# =============================================================================
# CONFIGURATION EXCEPTIONS
# =============================================================================

class ConfigurationError(MigrationError):
    """Raised for configuration-related errors."""
    
    def __init__(self, message: str, config_key: str = None, details: dict = None):
        details = details or {}
        if config_key:
            details['config_key'] = config_key
        super().__init__(message, 'CFG001', details)
        self.config_key = config_key


class MissingConfigError(ConfigurationError):
    """Raised when required configuration is missing."""
    
    def __init__(self, config_key: str, details: dict = None):
        message = f"Missing required configuration: {config_key}"
        super().__init__(message, config_key, details)
        self.code = 'CFG002'


# =============================================================================
# FILE/IO EXCEPTIONS
# =============================================================================

class FileOperationError(MigrationError):
    """Raised for file operation failures."""
    
    def __init__(self, message: str, filepath: str = None, details: dict = None):
        details = details or {}
        if filepath:
            details['filepath'] = filepath
        super().__init__(message, 'FILE001', details)
        self.filepath = filepath


class SecureDeletionError(FileOperationError):
    """Raised when secure file deletion fails."""
    
    def __init__(self, filepath: str, details: dict = None):
        message = f"Failed to securely delete file: {filepath}"
        super().__init__(message, filepath, details)
        self.code = 'FILE002'


# =============================================================================
# DATABASE EXCEPTIONS
# =============================================================================

class DatabaseError(MigrationError):
    """Raised for database operation failures."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, 'DB001', details)


class IdMappingError(DatabaseError):
    """Raised when ID mapping lookup/store fails."""
    
    def __init__(self, entity_type: str, qbd_id: str, details: dict = None):
        message = f"ID mapping failed for {entity_type}:{qbd_id}"
        details = details or {}
        details['entity_type'] = entity_type
        details['qbd_id'] = qbd_id
        super().__init__(message, details)
        self.code = 'DB002'