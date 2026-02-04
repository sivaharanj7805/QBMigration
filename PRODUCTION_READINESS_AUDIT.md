# ForensicBridge (QBMigration) - Production Readiness Audit

**Audit Date:** 2026-02-04
**Auditor:** Automated Production Readiness Review (Opus 4.5)
**Branch:** `claude/production-readiness-audit-BNniw`
**Commit Base:** `a5567cd`

---

## VERDICT: CONDITIONAL GO

**Production Readiness Score: 62 / 100**

The application demonstrates significant security hardening (encryption, HMAC webhooks, Argon2id, RBAC, CSRF, CSP headers) and thoughtful architecture (ephemeral EC2, PIPEDA-aware data residency, audit logging). However, **3 critical blockers** and **8 high-severity issues** must be resolved before production deployment.

---

## Repo Summary

| Attribute | Value |
|---|---|
| **Product** | ForensicBridge - QuickBooks Desktop to QBO/Caseware migration platform |
| **Components** | Python Flask API, Python Migration Service, Next.js Dashboard, C# Desktop Extractor, C# WPF Launcher |
| **Infrastructure** | AWS (S3, EC2, Lambda, CloudFormation), PostgreSQL, Redis, Docker, Nginx |
| **CI/CD** | GitHub Actions (lint, security scan, test-server, test-service, type-check) |
| **Lines of Code** | ~25,000+ across Python, TypeScript, C# |
| **Test Coverage** | Present but not enforced (see CRIT-01) |
| **Security Model** | JWT + Session cookies, HMAC webhooks, AES-256-GCM + RSA-4096 hybrid encryption |

---

## Blockers to Production (Ranked)

### CRITICAL (Must fix before any production traffic)

| # | Issue | File:Line | Impact | Effort |
|---|---|---|---|---|
| **CRIT-01** | CI tests cannot fail builds - `\|\| true` silences all test failures | `.github/workflows/python-ci.yml:121,154` | Broken code ships to production undetected | 5 min |
| **CRIT-02** | Chunked upload sessions stored in-memory dict - lost on restart/deploy, no bound on count | `QBMigrationServer/api/upload.py:818` | Data loss during deploys; OOM via unbounded sessions | 2-4 hrs |
| **CRIT-03** | Security scan uses `--exit-zero` - security vulnerabilities don't block merges | `.github/workflows/python-ci.yml:66` | Known CVEs ship to production | 5 min |

### HIGH (Must fix before GA, can soft-launch with monitoring)

| # | Issue | File:Line | Impact | Effort |
|---|---|---|---|---|
| **HIGH-01** | Session status endpoint has no authentication | `QBMigrationServer/api/session_validation.py:640+` | Exposes project names, client info, tier data to unauthenticated users | 30 min |
| **HIGH-02** | Device fingerprint hashed without salt (SHA-256) | `QBMigrationServer/api/session_validation.py:110` | Fingerprints can be brute-forced from known device profiles | 1 hr |
| **HIGH-03** | Rate limiter uses in-memory storage by default | `QBMigrationServer/config.py:155` | Rate limits reset on restart; not shared across Gunicorn workers | 1 hr |
| **HIGH-04** | `auto_migrate_database()` uses raw DDL with string interpolation in column loop | `QBMigrationServer/app.py:376-380` | Schema migration failures silently swallowed (`except: pass`) | 2 hrs |
| **HIGH-05** | Gunicorn configured for `gevent` but chunked upload uses `threading.Lock` | `QBMigrationServer/gunicorn.conf.py:54` / `upload.py:819` | Locks may not work correctly with gevent monkey-patching | 2 hrs |
| **HIGH-06** | MFA secret (`mfa_secret`) stored as plaintext in database | `QBMigrationServer/models/user.py:84` | TOTP secret exposure on DB breach allows 2FA bypass | 4 hrs |
| **HIGH-07** | `aws_region` defaults to `us-east-1` in Migration model | `QBMigrationServer/models/migration.py:61` | Contradicts PIPEDA `ca-central-1` requirement in config | 30 min |
| **HIGH-08** | Celery worker/beat defined in docker-compose but `celery_worker` module not found | `docker-compose.yml:120` | Background task processing won't start | 2-4 hrs |

### MEDIUM (Should fix within first sprint post-launch)

| # | Issue | File:Line | Impact | Effort |
|---|---|---|---|---|
| **MED-01** | `clear_cache()` in secrets manager doesn't use thread lock | `QBMigrationServer/utils/secrets_manager.py:203-208` | Race condition on cache clear in multi-threaded env | 15 min |
| **MED-02** | Synchronous AWS cleanup in webhook handler blocks response | `QBMigrationServer/api/webhooks.py:354-359` | Webhook response delayed by S3/EC2 cleanup operations | 2 hrs |
| **MED-03** | No maximum concurrent chunked upload sessions limit | `QBMigrationServer/api/upload.py:818` | Memory exhaustion via many parallel uploads | 1 hr |
| **MED-04** | `_get_env_secrets()` returns empty strings for all secrets | `QBMigrationServer/utils/secrets_manager.py:174-200` | Silent misconfiguration - app runs with empty credentials | 1 hr |
| **MED-05** | Health check queries `pg_stat_activity` on every request | `QBMigrationServer/app.py:1001-1026` | Unnecessary DB load from monitoring; fails on SQLite | 30 min |
| **MED-06** | Type-check job is `continue-on-error: true` | `.github/workflows/python-ci.yml:166` | Type errors never surface in PR reviews | 5 min |
| **MED-07** | CSP allows `'unsafe-inline'` for scripts and styles | `QBMigrationServer/app.py:710-711` | Weakens XSS protection significantly | 4 hrs |
| **MED-08** | `password_history` stored as JSON text column | `QBMigrationServer/models/user.py:79` | Old password hashes accumulate without rotation/cleanup | 2 hrs |
| **MED-09** | Redis health check includes password in command | `docker-compose.yml:104` | Password visible in `docker inspect` and process list | 30 min |
| **MED-10** | `file_upload.py` `supported-exports` endpoint has no auth | `QBMigrationServer/api/file_upload.py:167` | Minor info disclosure of supported export types | 15 min |
| **MED-11** | QBO OAuth tokens encrypted with Fernet but key rotation not implemented | `QBMigrationServer/models/user.py:98-99`, `config.py:181` | Key compromise requires manual re-encryption of all tokens | 4 hrs |
| **MED-12** | `backup_codes` stored as JSON text without encryption | `QBMigrationServer/models/user.py:85` | MFA backup codes exposed on DB breach | 2 hrs |

### LOW (Fix when convenient)

| # | Issue | File:Line | Impact | Effort |
|---|---|---|---|---|
| **LOW-01** | Logging uses emojis in production log messages | `QBMigrationServer/config.py:25,254` | Log parsers may break on emoji characters | 15 min |
| **LOW-02** | `ALERT_EMAIL` defaults to `admin@yourcompany.com` | `QBMigrationServer/config.py:222` | Alert emails go nowhere if not explicitly set | 5 min |
| **LOW-03** | Docker Compose version `3.8` is deprecated | `docker-compose.yml:12` | Warning on newer Docker Compose versions | 5 min |
| **LOW-04** | `QBO_REDIRECT_URI` defaults to localhost in base Config | `QBMigrationServer/config.py:275` | Not a bug (overridden in production) but confusing | 5 min |
| **LOW-05** | Postgres health check hardcodes username `qbmigration` | `docker-compose.yml:81` | Health check fails if `POSTGRES_USER` is changed | 5 min |
| **LOW-06** | `flake8` second pass uses `--exit-zero` | `.github/workflows/python-ci.yml:43` | Style violations never block CI | 5 min |
| **LOW-07** | Black/isort checks emit warnings but don't fail CI | `.github/workflows/python-ci.yml:32-36` | Inconsistent formatting ships to production | 5 min |

---

## Line-by-Line Review

### `QBMigrationServer/app.py` (1299 lines)

**Purpose:** Flask application factory - creates and configures the Flask app with all blueprints, middleware, security headers, error handlers, and health checks.

**Critical Issues:**
- **Line 376-380:** `auto_migrate_database()` iterates over columns with f-string SQL and catches all exceptions with `pass`. If a column migration fails, the error is silently swallowed, leading to schema drift that's invisible to operators.
  ```python
  # FIX: Replace pass with proper logging
  except Exception as e:
      logger.warning(f"Column {col_name} migration skipped: {e}")
  ```

**Major Issues:**
- **Line 89:** `FLASK_ENV` check - Flask deprecated `FLASK_ENV` in Flask 2.3+. Should use `app.debug` or custom config variable.
- **Line 106-112:** Database URI masking logic is fragile - `split('@')[-1]` could still leak database name and host information in logs.
- **Line 633:** Localhost check uses `in str(allowed_origins)` which could false-positive on domains containing "localhost" as substring.
- **Line 655:** Rate limiter defaults to `memory://` storage - not shared across Gunicorn workers, making rate limiting ineffective per-worker.
- **Line 710-711:** CSP `'unsafe-inline'` for scripts and styles significantly weakens XSS protection.
- **Line 1001-1026:** `pg_stat_activity` query on health check adds DB load. Will error on SQLite (non-PostgreSQL).

**Minor Issues:**
- **Line 773:** `X-RateLimit-Reset` calculated per-response instead of from actual rate limiter state.
- **Line 964:** Health CORS helper uses `*` wildcard for non-browser requests - acceptable for read-only health endpoints but worth documenting.

**Positive Notes:**
- Excellent production startup validation (lines 458-553): validates encryption keys, SECRET_KEY length, AMI/region consistency, CORS origins.
- ProxyFix middleware correctly configured for ALB (lines 437-451).
- Comprehensive security headers (lines 704-775): CSP, HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy.
- Error sanitization in production (lines 1159-1245).
- CSRF protection enabled with proper exemptions (lines 668-697).

---

### `QBMigrationServer/config.py` (604 lines)

**Purpose:** Configuration classes for development, testing, and production environments.

**Critical Issues:** None.

**Major Issues:**
- **Line 155:** `RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'memory://')` - In production with Gunicorn workers, each worker gets its own rate limit counter. Must use Redis.
- **Line 222:** `ALERT_EMAIL` defaults to `admin@yourcompany.com` - placeholder will cause alert delivery failures.

**Minor Issues:**
- **Line 25:** Log message uses emoji - may break log parsers.
- **Line 275:** `QBO_REDIRECT_URI` defaults to `http://localhost:5000` - not a security risk since overridden in production.

**Positive Notes:**
- Production config requires all critical env vars (lines 517-529).
- TestingConfig validates against production DB usage (lines 441-494).
- Fernet key validation at startup (lines 586-596).
- Data sovereignty validation (lines 110-138).
- Comprehensive feature flags (lines 280-316).

---

### `QBMigrationServer/models/user.py` (100+ lines)

**Purpose:** User model with Argon2id hashing, TOTP 2FA, password history, account lockout.

**Critical Issues:** None.

**Major Issues:**
- **Line 84:** `mfa_secret` stored as plaintext `String(32)`. If the database is compromised, attackers can generate valid TOTP codes. Should be encrypted at rest using `BACKUP_ENCRYPTION_KEY`.
  ```python
  # FIX: Encrypt before storage, decrypt on read
  mfa_secret_encrypted = db.Column(db.Text, nullable=True)
  ```
- **Line 85:** `backup_codes` stored as plaintext JSON. Same DB breach exposure risk.

**Minor Issues:**
- **Line 79:** `password_history` as JSON text without size limit could grow indefinitely.
- **Line 93-94:** Duplicate login timestamp columns (`last_login` and `last_login_at`) - technical debt.

**Positive Notes:**
- Argon2id with secure parameters (time_cost=3, memory_cost=64MB, parallelism=4).
- RBAC with role column (line 70).
- Account lockout protection fields (lines 73-75).
- Composite indexes for performance (lines 52-55).

---

### `QBMigrationServer/models/migration.py` (100+ lines)

**Purpose:** Migration tracking model with full audit trail, cost tracking, cleanup state.

**Critical Issues:** None.

**Major Issues:**
- **Line 61:** `aws_region` defaults to `'us-east-1'` but config.py defaults to `'ca-central-1'`. A migration created without explicitly setting region gets the wrong default, violating PIPEDA data residency.
  ```python
  # FIX: Use config default
  aws_region = db.Column(db.String(50), default='ca-central-1')
  ```

**Minor Issues:**
- **Line 97:** `cost_breakdown` stored as JSON text rather than PostgreSQL JSONB.

**Positive Notes:**
- Comprehensive indexes (lines 24-35).
- CASCADE delete for GDPR compliance (line 41).
- Webhook idempotency tracking via `webhook_processed_ids`.
- Encrypted error messages (line 80).

---

### `QBMigrationServer/models/database.py` (57 lines)

**Purpose:** SQLAlchemy initialization, PostgreSQL detection, row-level locking utility.

**Critical Issues:** None.
**Major Issues:** None.

**Minor Issues:**
- **Line 35:** `db.session.bind.dialect.name` - accessing `bind` directly is deprecated in SQLAlchemy 2.0+.

**Positive Notes:**
- `is_postgresql()` properly handles SQLite fallback.
- `expire_on_commit = False` correctly limited to testing only.

---

### `QBMigrationServer/api/webhooks.py` (475 lines)

**Purpose:** Webhook endpoints for migration lifecycle with HMAC signature verification, replay prevention, idempotency.

**Critical Issues:** None.

**Major Issues:**
- **Line 354-359:** Synchronous AWS cleanup call blocks webhook response path.
  ```python
  # FIX: Move to background thread or Celery task
  from concurrent.futures import ThreadPoolExecutor
  executor = ThreadPoolExecutor(max_workers=1)
  executor.submit(aws_manager.cleanup_migration, migration_id, migration.aws_instance_id)
  ```

**Minor Issues:**
- Lines 131-146, 239-252, 322-335, 414-427: Repetitive `SELECT FOR UPDATE` pattern should be extracted to a helper.

**Positive Notes:**
- HMAC-SHA256 with `hmac.compare_digest` for timing-safe comparison (line 66).
- Replay attack prevention with timestamp window (lines 43-55).
- Idempotency via webhook ID tracking (lines 157-164).
- `nowait=True` on FOR UPDATE to prevent indefinite blocking.

---

### `QBMigrationServer/api/session_validation.py` (681+ lines)

**Purpose:** Session validation with device fingerprinting for fraud prevention.

**Critical Issues:** None.

**Major Issues:**
- **Line 110:** `hash_fingerprint()` uses SHA-256 without salt. Device fingerprints are low-entropy, making rainbow table attacks feasible.
  ```python
  # FIX: Use HMAC with app secret
  import hmac
  def hash_fingerprint(fingerprint):
      if not fingerprint:
          return None
      secret = current_app.config['SECRET_KEY'].encode()
      return hmac.new(secret, fingerprint.encode(), hashlib.sha256).hexdigest()
  ```
- **Line 640+:** Session status endpoint has NO authentication decorator. Exposes project names, client names, tier information.

**Minor Issues:**
- Lines 36-73: Models defined inline rather than in `models/` directory.

**Positive Notes:**
- Rate limiting per session+IP (lines 93-103).
- Audit logging for all validation attempts (lines 76-90).
- Device count limits per session.

---

### `QBMigrationServer/api/internal.py` (235 lines)

**Purpose:** Internal API for Lambda and service-to-service communication.

**Critical Issues:** None.
**Major Issues:** None.

**Positive Notes:**
- Constant-time comparison with `hmac.compare_digest` (line 60).
- UUID validation for session_id (lines 117-123).
- Path traversal check for s3_key (lines 126-131).
- State machine validation before processing (lines 150-155).

---

### `QBMigrationServer/api/upload.py` (1362 lines)

**Purpose:** Encrypted file upload with v3.1 hybrid encryption, NDJSON bundles, chunked upload.

**Critical Issues:**
- **Line 818:** `_chunked_uploads = {}` - In-memory dict for upload sessions. Lost on any restart/deploy/worker recycle. With Gunicorn's `max_requests=1000`, workers restart periodically, losing all in-progress uploads.
  ```python
  # FIX: Use Redis for session storage
  # _chunked_uploads = redis_client.hgetall('chunked_uploads')
  ```

**Major Issues:**
- **Line 818-820:** No limit on concurrent upload sessions. OOM risk from many parallel uploads.
- **Line 819:** `threading.Lock` may not work correctly with gevent worker class.

**Positive Notes:**
- SHA-256 hash verification for data integrity.
- Input sanitization via whitelist regex.
- Rate limiting on upload endpoints.
- Proper temp directory cleanup.

---

### `QBMigrationServer/utils/secrets_manager.py` (297 lines)

**Purpose:** AWS Secrets Manager integration with TTL-based caching and thread-safe locks.

**Critical Issues:** None.
**Major Issues:** None.

**Minor Issues:**
- **Line 203-208:** `clear_cache()` doesn't acquire `_secrets_cache_lock`.
- **Line 174-200:** `_get_env_secrets()` returns empty strings for missing env vars.

**Positive Notes:**
- Thread-safe cache access (lines 94-100).
- Returns copies to prevent external modification (lines 100, 126).
- Configurable TTL (line 29).

---

### `QBMigrationServer/utils/auth.py` (33 lines)

**Purpose:** Auth decorators for admin and verified email requirements.

**Critical Issues:** None.
**Major Issues:** None.
**Minor Issues:** None.

**Positive Notes:** Clean, correct decorators using Flask-Login.

---

### `.github/workflows/python-ci.yml` (186 lines)

**Purpose:** CI pipeline for linting, security scanning, testing, type checking.

**Critical Issues:**
- **Line 121:** `pytest tests/ ... || true` - Test failures silenced.
  ```yaml
  # FIX: Remove || true
  pytest tests/ -v --cov=. --cov-report=xml --cov-report=term-missing
  ```
- **Line 154:** Same `|| true` pattern on service tests.
- **Line 66:** `bandit ... --exit-zero` - Security scan never fails CI.

**Major Issues:**
- **Line 166:** `continue-on-error: true` on type-check job.
- **Lines 32-36:** Black/isort only emit warnings.

**Positive Notes:**
- PostgreSQL service container for integration tests.
- Secrets properly injected via GitHub secrets.

---

### `Dockerfile` (118 lines)

**Purpose:** Multi-stage Docker build for production and development.

**Critical Issues:** None.
**Major Issues:** None.

**Minor Issues:**
- **Line 73:** Health check hits `/api/health` but app defines health at `/health`.
- **Line 82-85:** CMD uses `gthread` but `gunicorn.conf.py` defaults to `gevent`.

**Positive Notes:**
- Multi-stage build.
- Non-root user.
- `PYTHONUNBUFFERED=1` for proper log flushing.

---

### `docker-compose.yml` (205 lines)

**Purpose:** Docker Compose orchestration.

**Critical Issues:** None.

**Major Issues:**
- **Line 120:** `celery -A QBMigrationServer.celery_worker` - module appears missing.
- **Line 104:** Redis health check includes password in command.

**Minor Issues:**
- **Line 12:** `version: '3.8'` deprecated.
- **Line 81:** Hardcoded username in pg_isready.
- **Lines 69-70:** PostgreSQL port exposed to host.

**Positive Notes:**
- Secrets required via `${VAR:?message}` syntax.
- Service health checks with dependencies.
- Named volumes for persistence.

---

### `QBMigrationServer/gunicorn.conf.py` (197 lines)

**Purpose:** Gunicorn WSGI server configuration.

**Critical Issues:** None.

**Major Issues:**
- **Line 54:** Default `gevent` conflicts with Dockerfile's `gthread`.

**Positive Notes:**
- `max_requests` with jitter for graceful worker recycling.
- `/dev/shm` for worker heartbeat.
- Request size limits configured.

---

### `QBMigrationService/orchestrator.py` (100+ lines reviewed)

**Purpose:** Unified migration orchestrator for QB Desktop to QBO.

**Critical Issues:** None visible.
**Major Issues:** None visible.

**Positive Notes:**
- Input validation on constructor.
- Lazy initialization of dependencies.
- Type checking imports.

---

### `QBMigrationService/qbo_client.py` (100+ lines reviewed)

**Purpose:** QuickBooks Online API client with rate limiting, retry logic.

**Critical Issues:** None visible.
**Major Issues:** None visible.

**Positive Notes:**
- Thread-safe rate limit tracking.
- Per-request header copies.
- SQLite state database for crash recovery.
- Plan-aware rate limiting.

---

## Top 20 Risks (Ranked by Severity x Likelihood)

| Rank | Risk | Severity | Likelihood | Score | Category |
|------|------|----------|------------|-------|----------|
| 1 | CI tests silenced with `\|\| true` - broken code ships | Critical | Certain | 10 | Reliability |
| 2 | Security scan `--exit-zero` - known CVEs ship | Critical | High | 9 | Security |
| 3 | Chunked uploads lost on restart/deploy | Critical | High | 9 | Reliability |
| 4 | Unauthenticated session status endpoint | High | High | 8 | Security |
| 5 | Rate limiter per-worker with in-memory storage | High | High | 8 | Security |
| 6 | Gevent + threading.Lock mismatch | High | Medium | 7 | Reliability |
| 7 | MFA secrets stored plaintext in DB | High | Medium | 7 | Security |
| 8 | Migration region default inconsistency | High | Medium | 7 | Compliance |
| 9 | Celery worker module missing | High | Certain | 7 | Reliability |
| 10 | Device fingerprint unsalted hash | Medium | Medium | 6 | Security |
| 11 | Synchronous AWS cleanup in webhook | Medium | High | 6 | Performance |
| 12 | No upload session count limit (OOM risk) | Medium | Medium | 5 | Security |
| 13 | CSP unsafe-inline weakens XSS protection | Medium | Low | 5 | Security |
| 14 | Schema migration errors silently swallowed | Medium | Medium | 5 | Reliability |
| 15 | MFA backup codes unencrypted | Medium | Low | 4 | Security |
| 16 | QBO token key rotation not implemented | Medium | Low | 4 | Security |
| 17 | Secrets manager returns empty strings on fallback | Medium | Medium | 4 | Reliability |
| 18 | Health check queries pg_stat_activity | Low | High | 3 | Performance |
| 19 | Docker Compose PostgreSQL port exposed | Low | Medium | 3 | Security |
| 20 | Gunicorn worker class inconsistency | Medium | Medium | 5 | Reliability |

---

## Scoring Breakdown

| Category | Weight | Score | Notes |
|----------|--------|-------|-------|
| **Authentication & Authorization** | 15% | 12/15 | Argon2id, JWT, Flask-Login, RBAC. Deductions: MFA secrets plaintext, unauthenticated session endpoint |
| **Data Encryption** | 15% | 13/15 | AES-256-GCM + RSA-4096 hybrid, Fernet for tokens, encrypted error messages. Deduction: no key rotation |
| **Input Validation** | 10% | 8/10 | UUID validation, path traversal checks, whitelist regex. Deduction: unsalted fingerprint hash |
| **CI/CD & Testing** | 15% | 4/15 | Tests exist but `\|\| true` means they can't fail. Security scan `--exit-zero`. Type check optional |
| **Infrastructure Security** | 10% | 7/10 | Non-root Docker, ProxyFix, VPC-aware design. Deductions: port exposure, worker class mismatch |
| **Error Handling** | 5% | 4/5 | Error sanitization in production, Sentry integration. Minor: swallowed schema migration errors |
| **Logging & Monitoring** | 5% | 4/5 | Rotating file handlers, security log, PII redaction. Minor: emoji in logs |
| **Data Integrity** | 10% | 6/10 | SHA-256 verification, idempotent webhooks, FOR UPDATE locking. Deductions: in-memory uploads, region default |
| **Configuration Management** | 5% | 4/5 | Production validation thorough. Minor: placeholder email, env var inconsistencies |
| **Compliance (PIPEDA)** | 10% | 5/10 | Data residency checks exist but region default mismatch undermines them |

**Total: 62/100**

---

## Staged Remediation Plan

### Phase 1: "Stop the Bleeding" (Before any production traffic)

**Milestone:** CI pipeline catches failures; upload data persists across deploys.
**Target Score:** 78/100

| Task | Fix | Acceptance Criteria |
|------|-----|---------------------|
| Fix CI test gates | Remove `\|\| true` from pytest commands in `python-ci.yml:121,154` | CI fails when any test fails |
| Fix security scan gate | Remove `--exit-zero` from bandit in `python-ci.yml:66`, or add a separate blocking step | CI fails on medium+ severity findings |
| Move chunked uploads to Redis/DB | Replace `_chunked_uploads` dict with Redis hash or database table | Uploads survive worker restarts |
| Add auth to session status endpoint | Add `@require_auth` or `@login_required` to `/api/session/<session_id>/status` | Endpoint returns 401 without valid token |
| Fix region default | Change `models/migration.py:61` default from `'us-east-1'` to `'ca-central-1'` | New migrations get correct region |

### Phase 2: "Harden" (First week of soft launch)

**Milestone:** Security hardening complete; rate limiting effective.
**Target Score:** 88/100

| Task | Fix | Acceptance Criteria |
|------|-----|---------------------|
| Redis-backed rate limiting | Set `RATELIMIT_STORAGE_URL` to Redis URL in production config | Rate limits shared across all workers |
| Salt device fingerprints | Add HMAC-SHA256 with app secret in `hash_fingerprint()` | Brute-force infeasible |
| Encrypt MFA secrets | Encrypt `mfa_secret` and `backup_codes` with Fernet before DB storage | DB dump doesn't expose TOTP secrets |
| Resolve worker class | Standardize on `gevent` or `gthread` across Dockerfile and gunicorn.conf.py | No threading/gevent mismatch |
| Fix Celery module | Create `celery_worker.py` or update docker-compose command | Celery containers start successfully |
| Async webhook cleanup | Move AWS cleanup to background task | Webhook responses return in < 1 second |

### Phase 3: "Polish" (First month)

**Milestone:** Full CI enforcement; operational excellence.
**Target Score:** 95/100

| Task | Fix | Acceptance Criteria |
|------|-----|---------------------|
| Enforce type checking | Remove `continue-on-error` from type-check job | Type errors block PR merge |
| Enforce formatting | Remove `\|\| echo` fallbacks from Black/isort checks | Formatting issues block CI |
| Add upload session limits | Add `MAX_CONCURRENT_UPLOADS` config, reject when exceeded | OOM risk eliminated |
| Implement key rotation | Add `ENCRYPTION_KEY_VERSION` support with re-encryption migration | Can rotate keys without downtime |
| Remove CSP unsafe-inline | Implement nonce-based CSP | Security headers fully hardened |
| Fix schema migration error handling | Replace `except: pass` with proper error logging | Schema drift is detectable |
| Validate secrets on startup | Make `_get_env_secrets()` warn/fail on empty critical secrets | Misconfiguration detected at startup |

---

## Architecture Strengths

1. **Ephemeral compute model** - EC2 instances spun up per migration and terminated after, minimizing attack surface
2. **Encryption at every stage** - AES-256-GCM + RSA-4096 hybrid encryption for data in transit and at rest
3. **PIPEDA-aware design** - Canadian data residency configuration, ca-central-1 defaults (with noted inconsistency)
4. **Comprehensive security headers** - CSP, HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy
5. **Webhook security** - HMAC-SHA256 signatures, replay prevention, idempotency
6. **Argon2id password hashing** - Industry best practice with proper parameters
7. **Audit trail** - Session validation logs, webhook processing logs, security event logging
8. **Error sanitization** - Production error responses never leak stack traces or internal details
9. **Multi-stage Docker build** - Optimized image with non-root user
10. **Database locking** - SELECT FOR UPDATE with nowait for concurrency-safe webhook processing

---

## Final Notes

The codebase shows evidence of multiple rounds of security hardening (comments like "CRIT-01 FIX", "100/100 FIX", etc.), indicating active security investment. The architecture is sound - ephemeral compute, hybrid encryption, HMAC webhooks. The primary risk is **CI/CD enforcement**: the safety net exists (tests, security scans, type checks) but is disabled via `|| true` and `--exit-zero`. Fixing Phase 1 items transforms this from a 62 to approximately 78/100, and completing Phase 2 brings it to ~88/100.
