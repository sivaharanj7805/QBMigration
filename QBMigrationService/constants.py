"""
QBMigrationService Constants
===========================
Centralized constants to eliminate magic numbers throughout the service.

These are service-specific constants that complement the server constants.
"""

from typing import Dict, FrozenSet

# =============================================================================
# QBO API CONSTANTS
# =============================================================================


class QBOLimits:
    """QuickBooks Online API limits and thresholds"""

    # Batch limits
    MAX_BATCH_SIZE = 30
    MAX_QUERY_RESULTS = 1000

    # Field lengths
    MAX_NAME_LENGTH = 100
    MAX_DESCRIPTION_LENGTH = 4000
    MAX_MEMO_LENGTH = 4000
    MAX_ADDRESS_LINE_LENGTH = 500

    # Rate limits by plan
    SIMPLE_START_RPM = 100
    ESSENTIALS_RPM = 100
    PLUS_RPM = 500
    ADVANCED_RPM = 500


class EntityTypes:
    """QBO entity type constants"""

    ACCOUNT = "Account"
    CUSTOMER = "Customer"
    VENDOR = "Vendor"
    ITEM = "Item"
    INVOICE = "Invoice"
    BILL = "Bill"
    PAYMENT = "Payment"
    DEPOSIT = "Deposit"
    TRANSFER = "Transfer"
    JOURNAL_ENTRY = "JournalEntry"
    PURCHASE = "Purchase"
    SALES_RECEIPT = "SalesReceipt"
    CREDIT_MEMO = "CreditMemo"
    REFUND_RECEIPT = "RefundReceipt"
    ESTIMATE = "Estimate"
    PURCHASE_ORDER = "PurchaseOrder"
    EMPLOYEE = "Employee"
    CLASS = "Class"
    DEPARTMENT = "Department"
    TAX_CODE = "TaxCode"
    TAX_RATE = "TaxRate"
    TERM = "Term"
    PAYMENT_METHOD = "PaymentMethod"

    # Entity processing order (dependencies first)
    PROCESSING_ORDER = [
        "TaxCode",
        "TaxRate",
        "PaymentMethod",
        "Term",
        "Class",
        "Department",
        "Account",
        "Customer",
        "Vendor",
        "Employee",
        "Item",
        "Invoice",
        "Bill",
        "Payment",
        "Deposit",
        "Transfer",
        "JournalEntry",
        "Purchase",
        "SalesReceipt",
        "CreditMemo",
        "RefundReceipt",
        "Estimate",
        "PurchaseOrder",
    ]


# =============================================================================
# ACCOUNT TYPE MAPPINGS
# =============================================================================


class AccountTypes:
    """QBO account type constants and mappings"""

    # Asset accounts
    BANK = "Bank"
    ACCOUNTS_RECEIVABLE = "Accounts Receivable"
    OTHER_CURRENT_ASSET = "Other Current Asset"
    FIXED_ASSET = "Fixed Asset"
    OTHER_ASSET = "Other Asset"

    # Liability accounts
    ACCOUNTS_PAYABLE = "Accounts Payable"
    CREDIT_CARD = "Credit Card"
    OTHER_CURRENT_LIABILITY = "Other Current Liability"
    LONG_TERM_LIABILITY = "Long Term Liability"

    # Equity accounts
    EQUITY = "Equity"

    # Income accounts
    INCOME = "Income"
    OTHER_INCOME = "Other Income"

    # Expense accounts
    EXPENSE = "Expense"
    OTHER_EXPENSE = "Other Expense"
    COST_OF_GOODS_SOLD = "Cost of Goods Sold"

    # Mapping from QB Desktop to QBO
    DESKTOP_TO_QBO_MAPPING: Dict[str, str] = {
        "BANK": "Bank",
        "AR": "Accounts Receivable",
        "OTHERASSET": "Other Current Asset",
        "FIXEDASSET": "Fixed Asset",
        "OTHERASSET2": "Other Asset",
        "AP": "Accounts Payable",
        "CCARD": "Credit Card",
        "OTHCURRENTLIAB": "Other Current Liability",
        "LONGTERMLIAB": "Long Term Liability",
        "EQUITY": "Equity",
        "INC": "Income",
        "OTHERINC": "Other Income",
        "EXP": "Expense",
        "OTHEREXP": "Other Expense",
        "COGS": "Cost of Goods Sold",
    }


# =============================================================================
# DATE FORMATS
# =============================================================================


class DateFormats:
    """Date format constants for parsing and formatting"""

    # ISO format (preferred)
    ISO_8601 = "%Y-%m-%d"

    # Common formats
    US_SLASH = "%m/%d/%Y"
    US_DASH = "%m-%d-%Y"
    EU_SLASH = "%d/%m/%Y"
    EU_DASH = "%d-%m-%Y"
    EU_DOT = "%d.%m.%Y"

    # All supported formats for auto-detection
    ALL_FORMATS = [
        "%Y-%m-%d",  # ISO 8601
        "%m/%d/%Y",  # US slash
        "%d/%m/%Y",  # EU slash
        "%Y/%m/%d",  # Alt ISO
        "%m-%d-%Y",  # US dash
        "%d-%m-%Y",  # EU dash
        "%d.%m.%Y",  # EU dot
        "%Y.%m.%d",  # Alt dot
    ]

    # Region defaults
    REGION_DEFAULTS: Dict[str, str] = {
        "US": "%m/%d/%Y",
        "CA": "%m/%d/%Y",
        "UK": "%d/%m/%Y",
        "AU": "%d/%m/%Y",
        "IN": "%d/%m/%Y",
    }


# =============================================================================
# CURRENCY CODES
# =============================================================================


class Currencies:
    """Currency code constants"""

    USD = "USD"
    CAD = "CAD"
    GBP = "GBP"
    AUD = "AUD"
    EUR = "EUR"
    INR = "INR"

    REGION_CURRENCIES: Dict[str, str] = {
        "US": "USD",
        "CA": "CAD",
        "UK": "GBP",
        "AU": "AUD",
        "IN": "INR",
    }


# =============================================================================
# PROCESSING LIMITS
# =============================================================================


class ProcessingLimits:
    """Processing and performance limits"""

    # Worker limits by plan
    WORKER_LIMITS: Dict[str, int] = {
        "Simple Start": 2,
        "Essentials": 3,
        "Plus": 5,
        "Advanced": 8,
    }

    # Chunk sizes for processing
    DEFAULT_CHUNK_SIZE = 100
    LARGE_FILE_CHUNK_SIZE = 1000

    # Memory limits
    MAX_MEMORY_PERCENT = 80
    STREAM_BUFFER_SIZE = 65536  # 64KB

    # Concurrent operations
    MAX_CONCURRENT_REQUESTS = 10
    MAX_QUEUE_SIZE = 1000


# =============================================================================
# ERROR MESSAGES
# =============================================================================


class ErrorMessages:
    """Standardized error messages"""

    # Validation errors
    INVALID_EMAIL = "Invalid email format"
    INVALID_DATE = "Invalid date format"
    INVALID_AMOUNT = "Invalid amount value"
    REQUIRED_FIELD = "Required field is missing: {field}"
    FIELD_TOO_LONG = "Field exceeds maximum length: {field} (max {max_length})"

    # API errors
    QBO_AUTH_FAILED = "QuickBooks authentication failed. Please reconnect."
    QBO_RATE_LIMITED = "Rate limit exceeded. Please wait and retry."
    QBO_SERVICE_ERROR = "QuickBooks service error. Please try again later."

    # Migration errors
    MIGRATION_DATA_INVALID = "Migration data validation failed"
    MIGRATION_ENTITY_FAILED = "Failed to migrate entity: {entity_type}"
    MIGRATION_ABORTED = "Migration aborted due to critical error"

    # File errors
    FILE_TOO_LARGE = "File exceeds maximum size limit"
    FILE_CORRUPT = "File appears to be corrupt or incomplete"
    FILE_DECRYPT_FAILED = "Failed to decrypt file"


# =============================================================================
# STATUS CONSTANTS
# =============================================================================


class MigrationStatus:
    """Migration status constants"""

    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"

    TERMINAL_STATES: FrozenSet[str] = frozenset(
        {"completed", "failed", "cancelled", "partial"}
    )

    ACTIVE_STATES: FrozenSet[str] = frozenset(
        {"pending", "queued", "in_progress", "validating", "uploading"}
    )


# =============================================================================
# ENCRYPTION CONSTANTS
# =============================================================================


class Encryption:
    """Encryption-related constants"""

    # AES-256-GCM
    AES_KEY_SIZE = 32  # 256 bits
    AES_IV_SIZE = 12  # 96 bits for GCM
    AES_TAG_SIZE = 16  # 128 bits

    # Key derivation
    PBKDF2_ITERATIONS = 100000
    PBKDF2_HASH = "SHA256"
    SALT_SIZE = 32

    # Secure deletion
    SECURE_DELETE_PASSES = 7

    # Versions
    CURRENT_VERSION = "2.0"
    LEGACY_VERSIONS = ["1.0", "1.1"]
