import os

# QuickBooks Online API credentials
CLIENT_ID = os.getenv("QBO_CLIENT_ID", "YOUR_CLIENT_ID_HERE")
CLIENT_SECRET = os.getenv("QBO_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
REFRESH_TOKEN = os.getenv("QBO_REFRESH_TOKEN", "YOUR_REFRESH_TOKEN_HERE")
REALM_ID = os.getenv("QBO_REALM_ID", "YOUR_REALM_ID_HERE")
ACCESS_TOKEN = os.getenv("QBO_ACCESS_TOKEN", "")  # Optional for initial setup

# Environment (sandbox or production)
ENVIRONMENT = os.getenv("QBO_ENVIRONMENT", "sandbox")

# Region support (US, CA, UK, AU, IN)
REGION = os.getenv("QBO_REGION", "US")

# Production guard - requires explicit flag to run against production
PRODUCTION_GUARD_ENABLED = os.getenv("QBO_PRODUCTION_GUARD", "true").lower() == "true"
PRODUCTION_CONFIRMATION_FLAG = os.getenv("QBO_CONFIRM_PRODUCTION", "false").lower() == "true"

# Multi-region API URLs
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
region_config = REGION_URLS.get(REGION.upper(), REGION_URLS["US"])
base_url_template = region_config.get(ENVIRONMENT, region_config["sandbox"])
BASE_URL = f"{base_url_template}/{REALM_ID}"

# OAuth URLs
OAUTH_BASE_URL = "https://oauth.platform.intuit.com/oauth2/v1"
OAUTH_TOKEN_URL = f"{OAUTH_BASE_URL}/tokens/bearer"
OAUTH_REVOKE_URL = f"{OAUTH_BASE_URL}/tokens/revoke"

# File paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
INPUT_FILE = os.path.join(DATA_DIR, "extracted_data.json")
OUTPUT_DIR = os.path.join(DATA_DIR, "migration_results")
ENCRYPTED_DIR = os.path.join(DATA_DIR, "encrypted")
LOG_DIR = os.path.join(DATA_DIR, "logs")

# Security settings
DATA_RETENTION_HOURS = int(os.getenv("DATA_RETENTION_HOURS", "1"))
ENABLE_2FA = os.getenv("ENABLE_2FA", "true").lower() == "true"
ENABLE_AUDIT_LOGGING = os.getenv("ENABLE_AUDIT_LOGGING", "true").lower() == "true"
ENABLE_AUTO_DELETION = os.getenv("ENABLE_AUTO_DELETION", "true").lower() == "true"
ENCRYPT_LOGS = os.getenv("ENCRYPT_LOGS", "true").lower() == "true"

# Migration settings
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "30"))  # QBO limit is 30
RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY", "0.15"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# QBO API Limits
QBO_RATE_LIMIT_PER_MINUTE = 500  # Requests per minute
QBO_BATCH_SIZE_LIMIT = 30  # Items per batch request
QBO_QUERY_MAX_RESULTS = 1000  # Max results per query

# QuickBooks Desktop limits
QBD_MAX_TARGETS_WARNING = 1_200_000  # Warn if file exceeds 1.2M targets
QBD_SUPPORTED_VERSIONS = ['2018', '2019', '2020', '2021', '2022', '2023', '2024']

# Migration audit trail
ADD_MIGRATION_MEMO = os.getenv("ADD_MIGRATION_MEMO", "true").lower() == "true"
MIGRATION_MEMO_TEMPLATE = "Migrated from QuickBooks Desktop on {date} by {app_name}"
APP_NAME = os.getenv("APP_NAME", "QB Migration Tool")

# Required OAuth scopes
REQUIRED_SCOPES = [
    "com.intuit.quickbooks.accounting"
]

# Create directories
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ENCRYPTED_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


def validate_production_access():
    """
    Production guard: Ensure user explicitly confirms production access
    
    Prevents accidental production migrations
    """
    if ENVIRONMENT == "production":
        if PRODUCTION_GUARD_ENABLED and not PRODUCTION_CONFIRMATION_FLAG:
            raise Exception(
                "❌ PRODUCTION GUARD: Cannot run against production without explicit confirmation.\n"
                "Set environment variable: QBO_CONFIRM_PRODUCTION=true\n"
                "Or disable guard with: QBO_PRODUCTION_GUARD=false"
            )
        
        print("⚠️  WARNING: Running against PRODUCTION environment")
        print(f"   Region: {REGION}")
        print(f"   Realm ID: {REALM_ID}")
        print(f"   Confirm this is correct before proceeding.\n")
    else:
        print(f"✓ Running in {ENVIRONMENT.upper()} mode (Region: {REGION})")


def get_qbo_plan_recommendation(class_count, item_count, user_count):
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


# Currency codes by region
REGION_CURRENCIES = {
    "US": "USD",
    "CA": "CAD",
    "UK": "GBP",
    "AU": "AUD",
    "IN": "INR"
}

DEFAULT_CURRENCY = REGION_CURRENCIES.get(REGION.upper(), "USD")