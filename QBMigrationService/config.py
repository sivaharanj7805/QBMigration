import os

# QuickBooks Online API credentials
CLIENT_ID = os.getenv("QBO_CLIENT_ID", "YOUR_CLIENT_ID_HERE")
CLIENT_SECRET = os.getenv("QBO_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
REFRESH_TOKEN = os.getenv("QBO_REFRESH_TOKEN", "YOUR_REFRESH_TOKEN_HERE")
REALM_ID = os.getenv("QBO_REALM_ID", "YOUR_REALM_ID_HERE")

# Environment
ENVIRONMENT = os.getenv("QBO_ENVIRONMENT", "sandbox")

# API URLs
if ENVIRONMENT == "sandbox":
    BASE_URL = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{REALM_ID}"
else:
    BASE_URL = f"https://quickbooks.api.intuit.com/v3/company/{REALM_ID}"

# File paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
INPUT_FILE = os.path.join(DATA_DIR, "extracted_data.json")
OUTPUT_DIR = os.path.join(DATA_DIR, "migration_results")
ENCRYPTED_DIR = os.path.join(DATA_DIR, "encrypted")
LOG_DIR = os.path.join(DATA_DIR, "logs")

# Security settings
DATA_RETENTION_HOURS = 1  # Auto-delete after 1 hour
ENABLE_2FA = True
ENABLE_AUDIT_LOGGING = True
ENABLE_AUTO_DELETION = True

# Migration settings
BATCH_SIZE = 30
RATE_LIMIT_DELAY = 0.15
MAX_RETRIES = 3

# Create directories
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ENCRYPTED_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)