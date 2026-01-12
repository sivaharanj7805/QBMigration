import os
from pathlib import Path
from typing import Optional

# ============================================================================
# CONFIGURATION VALIDATION & SANITIZATION
# ============================================================================

def get_env_int(key: str, default: int) -> int:
    """Safely get integer from environment with validation"""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        print(f"Warning: Invalid integer for {key}, using default: {default}")
        return default

def get_env_float(key: str, default: float) -> float:
    """Safely get float from environment with validation"""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        print(f"Warning: Invalid float for {key}, using default: {default}")
        return default

def get_env_bool(key: str, default: str = "true") -> bool:
    """Safely get boolean from environment"""
    return os.getenv(key, default).lower() in ("true", "1", "yes")

def sanitize_migration_id(migration_id: str) -> str:
    """
    Sanitize migration_id to prevent path traversal attacks
    
    SECURITY: Prevents directory traversal with IDs like "../../etc/passwd"
    """
    # Remove path separators and dangerous characters
    safe_id = "".join(c for c in migration_id if c.isalnum() or c in "_-")
    
    if not safe_id or safe_id != migration_id:
        raise ValueError(
            f"Invalid migration_id: '{migration_id}'. "
            "Only alphanumeric, underscore, and hyphen allowed."
        )
    
    return safe_id

# ============================================================================
# QUICKBOOKS ONLINE API CREDENTIALS
# ============================================================================

CLIENT_ID = os.getenv("QBO_CLIENT_ID", "YOUR_CLIENT_ID_HERE")
CLIENT_SECRET = os.getenv("QBO_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
REFRESH_TOKEN = os.getenv("QBO_REFRESH_TOKEN", "YOUR_REFRESH_TOKEN_HERE")
REALM_ID = os.getenv("QBO_REALM_ID", "YOUR_REALM_ID_HERE")
ACCESS_TOKEN = os.getenv("QBO_ACCESS_TOKEN", "")  # Optional for initial setup

# Validate critical credentials
if "YOUR_" in CLIENT_ID or "YOUR_" in CLIENT_SECRET:
    print("⚠️  WARNING: QBO credentials not configured. Set environment variables.")

# ============================================================================
# ENVIRONMENT & REGION CONFIGURATION
# ============================================================================

# Environment (sandbox or production)
ENVIRONMENT = os.getenv("QBO_ENVIRONMENT", "sandbox").lower()
if ENVIRONMENT not in ("sandbox", "production"):
    print(f"Warning: Invalid environment '{ENVIRONMENT}', defaulting to 'sandbox'")
    ENVIRONMENT = "sandbox"

# Region support (US, CA, UK, AU, IN)
REGION = os.getenv("QBO_REGION", "US").upper()
VALID_REGIONS = ("US", "CA", "UK", "AU", "IN")
if REGION not in VALID_REGIONS:
    print(f"Warning: Invalid region '{REGION}', defaulting to 'US'")
    REGION = "US"

# Production guard - requires explicit flag to run against production
PRODUCTION_GUARD_ENABLED = get_env_bool("QBO_PRODUCTION_GUARD", "true")
PRODUCTION_CONFIRMATION_FLAG = get_env_bool("QBO_CONFIRM_PRODUCTION", "false")

# ============================================================================
# MULTI-REGION API URLS
# ============================================================================

REGION_URLS = {
    "US": {
        "sandbox": "https://sandbox-quickbooks.api.intuit.com/v3/company",
        "production": "https://quickbooks.api.intuit.com/v3/company"
    },
    "CA": {
        "sandbox": "https://sandbox-quickbooks.api.intuit.com/v3/company",
        "production": "https://quickbooks.api.intuit.com/v3/company"
    },
    "UK": {
        "sandbox": "https://sandbox-quickbooks.api.intuit.com/v3/company",
        "production": "https://quickbooks.api.intuit.com/v3/company"
    },
    "AU": {
        "sandbox": "https://sandbox-quickbooks.api.intuit.com/v3/company",
        "production": "https://quickbooks.api.intuit.com/v3/company"
    },
    "IN": {
        "sandbox": "https://sandbox-quickbooks.api.intuit.com/v3/company",
        "production": "https://quickbooks.api.intuit.com/v3/company"
    }
}

# Build BASE_URL based on region and environment
region_config = REGION_URLS.get(REGION, REGION_URLS["US"])
base_url_template = region_config.get(ENVIRONMENT, region_config["sandbox"])
BASE_URL = f"{base_url_template}/{REALM_ID}"

# OAuth URLs
OAUTH_BASE_URL = "https://oauth.platform.intuit.com/oauth2/v1"
OAUTH_TOKEN_URL = f"{OAUTH_BASE_URL}/tokens/bearer"
OAUTH_REVOKE_URL = f"{OAUTH_BASE_URL}/tokens/revoke"
OAUTH_INTROSPECT_URL = f"{OAUTH_BASE_URL}/tokens/introspect"

# ============================================================================
# FILE PATHS (Using pathlib for cross-platform compatibility)
# ============================================================================

# Use absolute paths to avoid working directory issues
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_FILE = DATA_DIR / "extracted_data.json"
OUTPUT_DIR = DATA_DIR / "migration_results"
ENCRYPTED_DIR = DATA_DIR / "encrypted"
LOG_DIR = DATA_DIR / "logs"

# ============================================================================
# SECURITY SETTINGS
# ============================================================================

DATA_RETENTION_HOURS = get_env_int("DATA_RETENTION_HOURS", 1)
ENABLE_2FA = get_env_bool("ENABLE_2FA", "true")
ENABLE_AUDIT_LOGGING = get_env_bool("ENABLE_AUDIT_LOGGING", "true")
ENABLE_AUTO_DELETION = get_env_bool("ENABLE_AUTO_DELETION", "true")
ENCRYPT_LOGS = get_env_bool("ENCRYPT_LOGS", "true")

# Minimum bcrypt rounds (should be configurable for future-proofing)
BCRYPT_ROUNDS = get_env_int("BCRYPT_ROUNDS", 12)
if BCRYPT_ROUNDS < 10:
    print("Warning: BCRYPT_ROUNDS too low, using minimum of 10")
    BCRYPT_ROUNDS = 10

# Token refresh buffer (in seconds) - configurable for different batch sizes
TOKEN_REFRESH_BUFFER_SECONDS = get_env_int("TOKEN_REFRESH_BUFFER_SECONDS", 300)  # 5 minutes

# ============================================================================
# MIGRATION SETTINGS
# ============================================================================

BATCH_SIZE = get_env_int("BATCH_SIZE", 30)  # QBO limit is 30
if BATCH_SIZE > 30:
    print(f"Warning: BATCH_SIZE {BATCH_SIZE} exceeds QBO limit of 30, using 30")
    BATCH_SIZE = 30

RATE_LIMIT_DELAY = get_env_float("RATE_LIMIT_DELAY", 0.15)
MAX_RETRIES = get_env_int("MAX_RETRIES", 3)

# Parallel processing settings
MAX_PARALLEL_WORKERS = get_env_int("MAX_PARALLEL_WORKERS", 5)
if MAX_PARALLEL_WORKERS > 10:
    print(f"Warning: MAX_PARALLEL_WORKERS {MAX_PARALLEL_WORKERS} may cause rate limiting")

# Redis configuration (for rate limiting and job queue)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ENABLE_REDIS = get_env_bool("ENABLE_REDIS", "false")

# QBO Plan-specific worker limits
# These are conservative limits to avoid rate limiting
QBO_PLAN_WORKER_LIMITS = {
    "Simple Start": 2,
    "Essentials": 3,
    "Plus": 5,
    "Advanced": 8
}

def get_qbo_plan_worker_limit(plan_name: str = None) -> int:
    """
    $25M FIX: Get worker limit based on QBO plan tier.
    
    Prevents rate limiting by adjusting concurrency to plan capabilities.
    """
    if plan_name is None:
        plan_name = os.getenv("QBO_PLAN", "Plus")  # Default to Plus
    
    return QBO_PLAN_WORKER_LIMITS.get(plan_name, 5)

# ============================================================================
# QBO API LIMITS
# ============================================================================

QBO_RATE_LIMIT_PER_MINUTE = 500  # Requests per minute
QBO_BATCH_SIZE_LIMIT = 30  # Items per batch request
QBO_QUERY_MAX_RESULTS = 1000  # Max results per query
QBO_MAX_FIELD_LENGTH = 4000  # Max characters for notes/descriptions

# ============================================================================
# MIGRATION AUDIT TRAIL
# ============================================================================

ADD_MIGRATION_MEMO = get_env_bool("ADD_MIGRATION_MEMO", "true")
MIGRATION_MEMO_TEMPLATE = "Migrated from QuickBooks Desktop on {date} by {app_name}"
APP_NAME = os.getenv("APP_NAME", "QB Migration Tool")

# ============================================================================
# REQUIRED OAUTH SCOPES
# ============================================================================

REQUIRED_SCOPES = [
    "com.intuit.quickbooks.accounting"
]

# ============================================================================
# CURRENCY CODES BY REGION
# ============================================================================

REGION_CURRENCIES = {
    "US": "USD",
    "CA": "CAD",
    "UK": "GBP",
    "AU": "AUD",
    "IN": "INR"
}

DEFAULT_CURRENCY = REGION_CURRENCIES.get(REGION, "USD")

# ============================================================================
# DIRECTORY CREATION (Only if not in read-only mode)
# ============================================================================

def initialize_directories():
    """
    Initialize required directories
    
    SECURITY FIX: Only create directories when needed, not on import
    """
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ENCRYPTED_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        # Set restrictive permissions on data directory
        os.chmod(DATA_DIR, 0o700)  # Owner read/write/execute only
        
    except PermissionError as e:
        print(f"⚠️  Warning: Cannot create directories: {e}")
        print(f"   Ensure write permissions for: {DATA_DIR}")

# ============================================================================
# PRODUCTION GUARD
# ============================================================================

def validate_production_access():
    """
    Production guard: Ensure user explicitly confirms production access
    
    Prevents accidental production migrations
    """
    if ENVIRONMENT == "production":
        if PRODUCTION_GUARD_ENABLED and not PRODUCTION_CONFIRMATION_FLAG:
            raise Exception(
                "⛔ PRODUCTION GUARD: Cannot run against production without explicit confirmation.\n"
                "Set environment variable: QBO_CONFIRM_PRODUCTION=true\n"
                "Or disable guard with: QBO_PRODUCTION_GUARD=false"
            )
        
        print("⚠️  WARNING: Running against PRODUCTION environment")
        print(f"   Region: {REGION}")
        print(f"   Realm ID: {REALM_ID}")
        print(f"   Confirm this is correct before proceeding.\n")
    else:
        print(f"✓ Running in {ENVIRONMENT.upper()} mode (Region: {REGION})")

# ============================================================================
# QBO PLAN RECOMMENDATION
# ============================================================================

def get_qbo_plan_recommendation(class_count: int, item_count: int, user_count: int) -> str:
    """
    Recommend QBO plan based on data volume
    
    Plans:
    - Simple Start: 1 user, no classes
    - Essentials: 3 users, no classes
    - Plus: 5 users, unlimited classes
    - Advanced: 25 users, advanced features
    """
    if class_count > 0:
        if user_count > 5:
            return "Advanced"
        else:
            return "Plus"
    else:
        if user_count <= 1:
            return "Simple Start"
        elif user_count <= 3:
            return "Essentials"
        else:
            return "Plus"

# ============================================================================
# REALM_ID VALIDATION
# ============================================================================

def validate_realm_id(token_realm_id: Optional[str] = None) -> bool:
    """
    Validate that REALM_ID matches the OAuth token's realm
    
    SECURITY: Prevents posting data to wrong company
    """
    if token_realm_id and token_realm_id != REALM_ID:
        raise ValueError(
            f"REALM_ID mismatch! Config: {REALM_ID}, Token: {token_realm_id}\n"
            "Refusing to migrate data to wrong company."
        )
    return True