# Remediation Plan: Path to 100/100

This document provides exact code changes needed to achieve a 100/100 production readiness score.

---

## Phase 1: Critical Fixes (62 → 78 points)

### 1.1 Fix CI Test Gates (CRIT-01)

**File:** `.github/workflows/python-ci.yml`

**Lines 121-122 - Remove `|| true` from server tests:**
```yaml
# BEFORE:
- name: Run tests
  run: |
    pytest tests/ -v --cov=. --cov-report=xml --cov-report=term-missing || true

# AFTER:
- name: Run tests
  run: |
    pytest tests/ -v --cov=. --cov-report=xml --cov-report=term-missing
```

**Lines 154-155 - Remove `|| true` from service tests:**
```yaml
# BEFORE:
- name: Run service tests
  run: |
    cd QBMigrationService && python -m pytest tests/ -v || true

# AFTER:
- name: Run service tests
  run: |
    cd QBMigrationService && python -m pytest tests/ -v
```

---

### 1.2 Fix Security Scan Gate (CRIT-03)

**File:** `.github/workflows/python-ci.yml`

**Line 66 - Remove `--exit-zero` from bandit:**
```yaml
# BEFORE:
run: |
  bandit -r QBMigrationServer/ -ll -ii -f json -o bandit-report.json --exit-zero

# AFTER (Option A - fail on medium+ severity):
run: |
  bandit -r QBMigrationServer/ -ll -ii -f json -o bandit-report.json

# AFTER (Option B - separate blocking step):
run: |
  bandit -r QBMigrationServer/ -ll -ii -f json -o bandit-report.json --exit-zero
  bandit -r QBMigrationServer/ -ll -ii  # This will fail if issues found
```

---

### 1.3 Move Chunked Uploads to Redis (CRIT-02)

**File:** `QBMigrationServer/api/upload.py`

**Replace lines 818-820:**
```python
# BEFORE:
_chunked_uploads = {}
_chunked_uploads_lock = threading.Lock()
CHUNKED_UPLOAD_EXPIRY = 24 * 60 * 60  # 24 hours

# AFTER:
import redis
import json
from flask import current_app

CHUNKED_UPLOAD_EXPIRY = 4 * 60 * 60  # 4 hours (reduced from 24)
MAX_CONCURRENT_UPLOADS = 100  # Limit concurrent sessions

def _get_redis():
    """Get Redis client for chunked upload storage."""
    redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
    return redis.from_url(redis_url)

def _get_upload_session(session_id: str) -> Optional[dict]:
    """Retrieve upload session from Redis."""
    r = _get_redis()
    data = r.get(f"chunked_upload:{session_id}")
    if data:
        return json.loads(data)
    return None

def _set_upload_session(session_id: str, session_data: dict):
    """Store upload session in Redis with expiry."""
    r = _get_redis()
    # Check concurrent upload limit
    if r.scard("chunked_upload_sessions") >= MAX_CONCURRENT_UPLOADS:
        raise ValueError("Too many concurrent uploads. Please try again later.")
    r.setex(
        f"chunked_upload:{session_id}",
        CHUNKED_UPLOAD_EXPIRY,
        json.dumps(session_data)
    )
    r.sadd("chunked_upload_sessions", session_id)
    r.expire("chunked_upload_sessions", CHUNKED_UPLOAD_EXPIRY)

def _delete_upload_session(session_id: str):
    """Remove upload session from Redis."""
    r = _get_redis()
    r.delete(f"chunked_upload:{session_id}")
    r.srem("chunked_upload_sessions", session_id)
```

**Update all references from `_chunked_uploads[session_id]` to use the new functions.**

---

### 1.4 Add Auth to Session Status Endpoint (HIGH-01)

**File:** `QBMigrationServer/api/session_validation.py`

**Around line 640 - Add authentication:**
```python
# BEFORE:
@session_bp.route('/api/session/<session_id>/status', methods=['GET'])
def get_session_status(session_id):

# AFTER:
from flask_login import login_required

@session_bp.route('/api/session/<session_id>/status', methods=['GET'])
@login_required
def get_session_status(session_id):
```

---

### 1.5 Fix Region Default (HIGH-07)

**File:** `QBMigrationServer/models/migration.py`

**Line 61:**
```python
# BEFORE:
aws_region = db.Column(db.String(50), default='us-east-1')

# AFTER:
aws_region = db.Column(db.String(50), default='ca-central-1')
```

---

## Phase 2: Security Hardening (78 → 88 points)

### 2.1 Redis-Backed Rate Limiting (HIGH-03)

**File:** `QBMigrationServer/config.py`

**Line 155:**
```python
# BEFORE:
RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'memory://')

# AFTER:
RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL')
if not RATELIMIT_STORAGE_URL:
    if os.getenv('FLASK_ENV') == 'production':
        raise ValueError("REDIS_URL must be set in production for rate limiting!")
    RATELIMIT_STORAGE_URL = 'memory://'
```

---

### 2.2 Salt Device Fingerprints (HIGH-02)

**File:** `QBMigrationServer/api/session_validation.py`

**Replace `hash_fingerprint` function around line 110:**
```python
# BEFORE:
def hash_fingerprint(fingerprint: str) -> Optional[str]:
    """Hash a device fingerprint for storage."""
    if not fingerprint:
        return None
    return hashlib.sha256(fingerprint.encode()).hexdigest()

# AFTER:
import hmac

def hash_fingerprint(fingerprint: str) -> Optional[str]:
    """Hash a device fingerprint with HMAC for secure storage."""
    if not fingerprint:
        return None
    secret = current_app.config['SECRET_KEY'].encode()
    return hmac.new(secret, fingerprint.encode(), hashlib.sha256).hexdigest()
```

**Note:** Existing fingerprints will need migration. Add a one-time migration script:
```python
# scripts/migrate_fingerprints.py
def migrate_fingerprints():
    """Re-hash existing fingerprints with HMAC."""
    # This requires storing the original fingerprint temporarily
    # or accepting that existing sessions will need re-validation
    pass
```

---

### 2.3 Encrypt MFA Secrets (HIGH-06)

**File:** `QBMigrationServer/models/user.py`

**Replace MFA fields around lines 84-85:**
```python
# BEFORE:
mfa_secret = db.Column(db.String(32), nullable=True)
backup_codes = db.Column(db.Text, nullable=True)  # JSON list

# AFTER:
_mfa_secret_encrypted = db.Column('mfa_secret_encrypted', db.Text, nullable=True)
_backup_codes_encrypted = db.Column('backup_codes_encrypted', db.Text, nullable=True)

@property
def mfa_secret(self) -> Optional[str]:
    """Decrypt and return MFA secret."""
    if not self._mfa_secret_encrypted:
        return None
    from cryptography.fernet import Fernet
    from flask import current_app
    key = current_app.config['BACKUP_ENCRYPTION_KEY']
    f = Fernet(key.encode() if isinstance(key, str) else key)
    return f.decrypt(self._mfa_secret_encrypted.encode()).decode()

@mfa_secret.setter
def mfa_secret(self, value: Optional[str]):
    """Encrypt and store MFA secret."""
    if value is None:
        self._mfa_secret_encrypted = None
        return
    from cryptography.fernet import Fernet
    from flask import current_app
    key = current_app.config['BACKUP_ENCRYPTION_KEY']
    f = Fernet(key.encode() if isinstance(key, str) else key)
    self._mfa_secret_encrypted = f.encrypt(value.encode()).decode()

@property
def backup_codes(self) -> Optional[list]:
    """Decrypt and return backup codes."""
    if not self._backup_codes_encrypted:
        return None
    from cryptography.fernet import Fernet
    from flask import current_app
    import json
    key = current_app.config['BACKUP_ENCRYPTION_KEY']
    f = Fernet(key.encode() if isinstance(key, str) else key)
    return json.loads(f.decrypt(self._backup_codes_encrypted.encode()).decode())

@backup_codes.setter
def backup_codes(self, value: Optional[list]):
    """Encrypt and store backup codes."""
    if value is None:
        self._backup_codes_encrypted = None
        return
    from cryptography.fernet import Fernet
    from flask import current_app
    import json
    key = current_app.config['BACKUP_ENCRYPTION_KEY']
    f = Fernet(key.encode() if isinstance(key, str) else key)
    self._backup_codes_encrypted = f.encrypt(json.dumps(value).encode()).decode()
```

**Database migration required:**
```sql
-- Migration: Rename columns and encrypt existing data
ALTER TABLE users RENAME COLUMN mfa_secret TO mfa_secret_old;
ALTER TABLE users RENAME COLUMN backup_codes TO backup_codes_old;
ALTER TABLE users ADD COLUMN mfa_secret_encrypted TEXT;
ALTER TABLE users ADD COLUMN backup_codes_encrypted TEXT;
-- Run Python script to encrypt existing values, then drop old columns
```

---

### 2.4 Resolve Worker Class Mismatch (HIGH-05)

**Option A: Standardize on gthread (recommended for simplicity)**

**File:** `QBMigrationServer/gunicorn.conf.py` line 54:
```python
# BEFORE:
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'gevent')

# AFTER:
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'gthread')
```

**Option B: Standardize on gevent (better for I/O-bound)**

**File:** `Dockerfile` lines 82-85:
```dockerfile
# BEFORE:
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "--worker-class", "gthread", ...]

# AFTER:
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--worker-class", "gevent", ...]
```

And add gevent monkey-patching at the top of `wsgi.py`:
```python
# At the very top of wsgi.py, before any other imports:
from gevent import monkey
monkey.patch_all()
```

---

### 2.5 Create Celery Worker Module (HIGH-08)

**File:** `QBMigrationServer/celery_worker.py` (new file)
```python
"""Celery worker configuration for background tasks."""
from celery import Celery
from flask import Flask
import os

def make_celery(app: Flask = None) -> Celery:
    """Create and configure Celery instance."""
    celery = Celery(
        'qbmigration',
        broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
        backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
        include=['QBMigrationServer.tasks']
    )

    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_time_limit=3600,  # 1 hour max
        worker_prefetch_multiplier=1,
        task_acks_late=True,
    )

    if app:
        celery.conf.update(app.config)

        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = ContextTask

    return celery

# Create default celery instance
celery = make_celery()
```

**File:** `QBMigrationServer/tasks.py` (new file)
```python
"""Background tasks for QBMigration."""
from .celery_worker import celery
from .utils.aws_manager import AWSManager
import logging

logger = logging.getLogger(__name__)

@celery.task(bind=True, max_retries=3)
def cleanup_migration_async(self, migration_id: str, instance_id: str):
    """Async cleanup of AWS resources after migration."""
    try:
        aws_manager = AWSManager()
        aws_manager.cleanup_migration(migration_id, instance_id)
        logger.info(f"Cleanup completed for migration {migration_id}")
    except Exception as e:
        logger.error(f"Cleanup failed for migration {migration_id}: {e}")
        raise self.retry(exc=e, countdown=60)
```

---

### 2.6 Async Webhook Cleanup (MED-02)

**File:** `QBMigrationServer/api/webhooks.py`

**Replace synchronous cleanup around lines 354-359:**
```python
# BEFORE:
if migration.aws_instance_id:
    try:
        aws_manager.cleanup_migration(migration_id, migration.aws_instance_id)
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

# AFTER:
if migration.aws_instance_id:
    from ..tasks import cleanup_migration_async
    cleanup_migration_async.delay(migration_id, migration.aws_instance_id)
    logger.info(f"Scheduled async cleanup for migration {migration_id}")
```

---

## Phase 3: Polish (88 → 95+ points)

### 3.1 Enforce Type Checking (MED-06)

**File:** `.github/workflows/python-ci.yml`

**Line 166:**
```yaml
# BEFORE:
type-check:
  runs-on: ubuntu-latest
  continue-on-error: true

# AFTER:
type-check:
  runs-on: ubuntu-latest
  # Removed continue-on-error
```

---

### 3.2 Enforce Formatting (LOW-06, LOW-07)

**File:** `.github/workflows/python-ci.yml`

**Lines 32-43:**
```yaml
# BEFORE:
- name: Check formatting with Black
  run: |
    black --check . || echo "Formatting issues found"

- name: Check import sorting
  run: |
    isort --check-only . || echo "Import sorting issues found"

- name: Lint with flake8
  run: |
    flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
    flake8 . --count --exit-zero --max-complexity=10 --statistics

# AFTER:
- name: Check formatting with Black
  run: black --check .

- name: Check import sorting
  run: isort --check-only .

- name: Lint with flake8
  run: |
    flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
    flake8 . --count --max-complexity=10 --statistics
```

---

### 3.3 Implement Key Rotation (MED-11)

**File:** `QBMigrationServer/config.py`

**Add after line 181:**
```python
# Encryption key rotation support
ENCRYPTION_KEY_VERSIONS = {
    'v1': os.getenv('ENCRYPTION_KEY_V1'),
    'v2': os.getenv('ENCRYPTION_KEY_V2'),
}
CURRENT_ENCRYPTION_KEY_VERSION = os.getenv('ENCRYPTION_KEY_VERSION', 'v1')

@classmethod
def get_encryption_key(cls, version: str = None) -> str:
    """Get encryption key by version for rotation support."""
    version = version or cls.CURRENT_ENCRYPTION_KEY_VERSION
    key = cls.ENCRYPTION_KEY_VERSIONS.get(version)
    if not key:
        raise ValueError(f"Encryption key version {version} not configured")
    return key
```

**File:** `QBMigrationServer/models/user.py`

**Update encrypted fields to include version:**
```python
# Store version with encrypted data
_qbo_tokens_encrypted = db.Column(db.Text, nullable=True)  # Format: "v1:encrypted_data"

@property
def qbo_tokens(self) -> Optional[dict]:
    if not self._qbo_tokens_encrypted:
        return None
    version, data = self._qbo_tokens_encrypted.split(':', 1)
    key = current_app.config.get_encryption_key(version)
    f = Fernet(key.encode())
    return json.loads(f.decrypt(data.encode()).decode())

@qbo_tokens.setter
def qbo_tokens(self, value: Optional[dict]):
    if value is None:
        self._qbo_tokens_encrypted = None
        return
    version = current_app.config['CURRENT_ENCRYPTION_KEY_VERSION']
    key = current_app.config.get_encryption_key(version)
    f = Fernet(key.encode())
    encrypted = f.encrypt(json.dumps(value).encode()).decode()
    self._qbo_tokens_encrypted = f"{version}:{encrypted}"
```

---

### 3.4 Remove CSP unsafe-inline (MED-07)

**File:** `QBMigrationServer/app.py`

**Replace CSP configuration around lines 710-711:**
```python
# BEFORE:
"Content-Security-Policy": (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://js.stripe.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    ...
)

# AFTER - Use nonces:
import secrets

@app.before_request
def generate_csp_nonce():
    """Generate a unique nonce for each request."""
    g.csp_nonce = secrets.token_urlsafe(32)

@app.after_request
def add_security_headers(response):
    nonce = getattr(g, 'csp_nonce', '')
    response.headers['Content-Security-Policy'] = (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://js.stripe.com; "
        f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; "
        ...
    )
    return response
```

**Update templates to use nonce:**
```html
<script nonce="{{ g.csp_nonce }}">
  // inline script
</script>
<style nonce="{{ g.csp_nonce }}">
  /* inline styles */
</style>
```

---

### 3.5 Fix Schema Migration Error Handling (HIGH-04)

**File:** `QBMigrationServer/app.py`

**Replace around lines 376-380:**
```python
# BEFORE:
for col_name, col_type in columns_to_add:
    try:
        db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type}'))
        db.session.commit()
    except:
        pass

# AFTER:
migration_errors = []
for col_name, col_type in columns_to_add:
    try:
        db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type}'))
        db.session.commit()
        logger.info(f"Added column {col_name} to {table}")
    except Exception as e:
        db.session.rollback()
        error_msg = str(e).lower()
        # Ignore "column already exists" errors
        if 'duplicate column' in error_msg or 'already exists' in error_msg:
            logger.debug(f"Column {col_name} already exists in {table}")
        else:
            migration_errors.append(f"{table}.{col_name}: {e}")
            logger.error(f"Failed to add column {col_name} to {table}: {e}")

if migration_errors:
    logger.critical(f"Schema migration had {len(migration_errors)} errors: {migration_errors}")
    # Optionally raise to prevent app startup with broken schema
    # raise RuntimeError(f"Schema migration failed: {migration_errors}")
```

---

### 3.6 Validate Secrets on Startup (MED-04)

**File:** `QBMigrationServer/utils/secrets_manager.py`

**Replace `_get_env_secrets` around lines 174-200:**
```python
# BEFORE:
def _get_env_secrets() -> Dict[str, str]:
    """Get secrets from environment variables (fallback/development)."""
    return {
        'database_url': os.getenv('DATABASE_URL', ''),
        'secret_key': os.getenv('SECRET_KEY', ''),
        ...
    }

# AFTER:
REQUIRED_SECRETS = ['database_url', 'secret_key']
PRODUCTION_REQUIRED_SECRETS = ['database_url', 'secret_key', 'aws_access_key_id', 'aws_secret_access_key']

def _get_env_secrets() -> Dict[str, str]:
    """Get secrets from environment variables with validation."""
    secrets = {
        'database_url': os.getenv('DATABASE_URL', ''),
        'secret_key': os.getenv('SECRET_KEY', ''),
        'aws_access_key_id': os.getenv('AWS_ACCESS_KEY_ID', ''),
        'aws_secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY', ''),
        'backup_encryption_key': os.getenv('BACKUP_ENCRYPTION_KEY', ''),
        'webhook_secret': os.getenv('WEBHOOK_SECRET', ''),
        'internal_api_key': os.getenv('INTERNAL_API_KEY', ''),
    }

    # Validate required secrets
    is_production = os.getenv('FLASK_ENV') == 'production'
    required = PRODUCTION_REQUIRED_SECRETS if is_production else REQUIRED_SECRETS

    missing = [k for k in required if not secrets.get(k)]
    if missing:
        error_msg = f"Missing required secrets: {', '.join(missing)}"
        if is_production:
            raise RuntimeError(error_msg)
        else:
            logger.warning(f"DEV MODE: {error_msg}")

    # Warn about empty non-critical secrets
    empty = [k for k, v in secrets.items() if not v and k not in missing]
    if empty:
        logger.warning(f"Empty secrets (may cause issues): {', '.join(empty)}")

    return secrets
```

---

### 3.7 Fix Thread Lock in Secrets Cache (MED-01)

**File:** `QBMigrationServer/utils/secrets_manager.py`

**Replace `clear_cache` around lines 203-208:**
```python
# BEFORE:
def clear_cache():
    """Clear the secrets cache."""
    global _secrets_cache
    _secrets_cache = {}

# AFTER:
def clear_cache():
    """Clear the secrets cache (thread-safe)."""
    global _secrets_cache
    with _secrets_cache_lock:
        _secrets_cache = {}
        logger.info("Secrets cache cleared")
```

---

### 3.8 Fix Health Check (MED-05)

**File:** `QBMigrationServer/app.py`

**Replace health check around lines 1001-1026:**
```python
# BEFORE:
def detailed_health():
    # Queries pg_stat_activity on every request
    db.session.execute(text("SELECT count(*) FROM pg_stat_activity"))

# AFTER:
def detailed_health():
    """Detailed health check with conditional DB stats."""
    health = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': app.config.get('VERSION', 'unknown'),
    }

    # Basic DB connectivity check (works with SQLite too)
    try:
        db.session.execute(text("SELECT 1"))
        health['database'] = 'connected'
    except Exception as e:
        health['database'] = f'error: {str(e)}'
        health['status'] = 'degraded'

    # Only query pg_stat_activity if explicitly requested and PostgreSQL
    if request.args.get('detailed') == 'true':
        if 'postgresql' in str(db.engine.url):
            try:
                result = db.session.execute(text(
                    "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
                ))
                health['db_active_connections'] = result.scalar()
            except Exception as e:
                health['db_stats_error'] = str(e)

    return jsonify(health)
```

---

### 3.9 Fix Docker Compose Issues (LOW-03, LOW-05, MED-09)

**File:** `docker-compose.yml`

```yaml
# Line 12 - Remove deprecated version
# BEFORE:
version: '3.8'

# AFTER:
# Remove the version line entirely (Docker Compose v2+ doesn't need it)

# Line 81 - Use variable in pg_isready
# BEFORE:
test: ["CMD-SHELL", "pg_isready -U qbmigration -d qbmigration"]

# AFTER:
test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-qbmigration} -d ${POSTGRES_DB:-qbmigration}"]

# Line 104 - Fix Redis health check (don't expose password)
# BEFORE:
test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-}", "ping"]

# AFTER:
test: ["CMD-SHELL", "redis-cli -a $REDIS_PASSWORD ping | grep -q PONG"]

# Lines 69-70 - Don't expose PostgreSQL port in production
# BEFORE:
ports:
  - "5432:5432"

# AFTER:
ports:
  - "${POSTGRES_EXPOSE_PORT:-127.0.0.1:5432}:5432"  # Only localhost by default
```

---

### 3.10 Fix Remaining Minor Issues

**File:** `QBMigrationServer/config.py`

**Line 222 - Remove placeholder email:**
```python
# BEFORE:
ALERT_EMAIL = os.getenv('ALERT_EMAIL', 'admin@yourcompany.com')

# AFTER:
ALERT_EMAIL = os.getenv('ALERT_EMAIL')
if not ALERT_EMAIL and os.getenv('FLASK_ENV') == 'production':
    raise ValueError("ALERT_EMAIL must be set in production!")
```

**Lines 25, 254 - Remove emojis from log messages:**
```python
# BEFORE:
logger.info("⚠️  WARNING: Using generated SECRET_KEY for development")

# AFTER:
logger.info("WARNING: Using generated SECRET_KEY for development")
```

---

## Summary: Changes by Score Impact

| Phase | Changes | Points Gained | New Score |
|-------|---------|---------------|-----------|
| **Phase 1** | 5 fixes (CI gates, uploads, auth, region) | +16 | 78/100 |
| **Phase 2** | 6 fixes (rate limit, fingerprint, MFA, worker, celery, async) | +10 | 88/100 |
| **Phase 3** | 10 fixes (type check, format, keys, CSP, errors, secrets, health, docker) | +12 | 100/100 |

---

## Verification Checklist

After implementing all fixes:

- [ ] CI fails when tests fail
- [ ] CI fails on security vulnerabilities
- [ ] Chunked uploads persist across deploys
- [ ] Session status endpoint requires authentication
- [ ] New migrations use ca-central-1 region
- [ ] Rate limits work across all Gunicorn workers
- [ ] Device fingerprints use HMAC
- [ ] MFA secrets encrypted in database
- [ ] Worker class consistent (gevent or gthread)
- [ ] Celery workers start successfully
- [ ] Webhook cleanup is async
- [ ] Type errors block CI
- [ ] Formatting errors block CI
- [ ] Key rotation supported
- [ ] CSP uses nonces (no unsafe-inline)
- [ ] Schema migration errors logged
- [ ] Missing secrets detected at startup
- [ ] Health check works with SQLite
- [ ] Docker Compose uses variables correctly
