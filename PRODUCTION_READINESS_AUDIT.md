# ForensicBridge Production Readiness Audit Report

**Date:** 2026-02-05
**Auditor:** Automated Deep Audit (Claude Opus 4.5)
**Scope:** Full codebase - QBMigrationServer, QBMigrationService, QBDesktopReader, forensicbridge-dashboard, AWS infrastructure, CI/CD
**Standard:** 99.99% reliability target, SOC2/PIPEDA compliance

---

## PART 1: EXECUTIVE SUMMARY

ForensicBridge is a multi-component migration platform that extracts QuickBooks Desktop data, transforms it, and migrates it to QuickBooks Online. The system spans six major components across Python, C#, TypeScript, and AWS infrastructure (~509 files).

**Verdict: CONDITIONAL GO** - The codebase demonstrates strong security fundamentals (Argon2id, AES-256-GCM, HMAC webhooks, constant-time comparisons) but has **7 critical**, **19 high**, **22 medium**, and **16 low** severity findings that must be addressed on a staged remediation timeline.

**Production Readiness Score: 72/100**

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Security | 74/100 | 25% | 18.5 |
| Data Integrity | 78/100 | 20% | 15.6 |
| Reliability | 70/100 | 20% | 14.0 |
| Infrastructure | 65/100 | 15% | 9.75 |
| Test Coverage | 72/100 | 10% | 7.2 |
| Operational Readiness | 68/100 | 10% | 6.8 |
| **Total** | | **100%** | **71.85 ~ 72** |

---

## PART 2: REPOSITORY INVENTORY

**Total files:** ~509
**Total lines of code:** ~85,000+ (estimated)

| Component | Language | Files | Purpose |
|-----------|----------|-------|---------|
| QBMigrationServer | Python/Flask | 93 | Web API, auth, payments, webhooks |
| QBMigrationService | Python | 52 | Migration orchestration, QBO API client |
| QBDesktopReader | C# | 72 | QuickBooks Desktop data extraction |
| QBMigrationLauncher | C# WPF | 22 | Windows launcher application |
| ForensicBridgeInstaller | C# | 5 | Windows installer |
| forensicbridge-dashboard | TypeScript/Next.js | 70 | Web frontend dashboard |
| AWS/Infrastructure | YAML/Shell/PS1 | 30+ | CloudFormation, Lambda, deploy scripts |
| Tests | Python/TypeScript | 37 | 1,628 test functions across 315 test classes |

---

## PART 3: TECHNOLOGY STACK

### Backend (QBMigrationServer)
- **Framework:** Flask 3.1.2 with Gunicorn 23.0.0
- **Database:** PostgreSQL via SQLAlchemy 2.0.23
- **Cache/Queue:** Redis (rate limiting, chunked uploads), Celery
- **Auth:** JWT (PyJWT 2.10.1) + Flask-Login sessions, Argon2id (argon2-cffi 23.1.0)
- **Crypto:** cryptography 46.0.3 (Fernet, RSA-4096), AES-256-GCM
- **Monitoring:** Sentry SDK 2.18.0, OpenTelemetry, Prometheus
- **AWS:** boto3 (S3, Secrets Manager, KMS)

### Migration Service (QBMigrationService)
- **Orchestration:** Custom pipeline with progress callbacks
- **QBO Client:** REST API with OAuth 2.0, batch operations
- **Verification:** Trial balance verification with Decimal precision
- **Encryption:** AES-256-GCM with RSA key exchange

### Desktop Reader (QBDesktopReader)
- **Framework:** .NET 8.0 (C#)
- **Data Access:** QODBC + QBFC SDK (conditional compilation)
- **Encryption:** AES-256-GCM with RSA-4096 hybrid encryption
- **Upload:** HTTP multipart + S3 direct upload
- **Streaming:** NDJSON streaming pipeline with checkpointing

### Frontend (forensicbridge-dashboard)
- **Framework:** Next.js 16.1.2, React 19.2.3
- **State:** @tanstack/react-query
- **Validation:** Zod schemas
- **Styling:** Tailwind CSS v4

### Infrastructure
- **Cloud:** AWS (EC2, S3, RDS PostgreSQL, Lambda, CloudFormation)
- **Proxy:** Nginx reverse proxy
- **CI/CD:** GitHub Actions (Python CI, build-installer, release-extractor)
- **Containers:** Docker + Docker Compose

---

## PART 4: CRITICAL FINDINGS (P0 - Must Fix Before Production)

### CRIT-01: Inconsistent Query Sanitization in QBO Verifier
**File:** `QBMigrationService/verifier.py:622,649,714`
**Severity:** CRITICAL | **Category:** Injection | **CWE:** CWE-89
**Description:** Direct string interpolation in QBO SQL-like queries. `_sanitize_query_value()` exists at line 593 but is not applied to all query templates.
```python
query = f"SELECT * FROM Transfer WHERE FromAccountRef = '{account_id}'"
```
**Impact:** If account_id contains crafted input, query manipulation possible against QBO API.
**Remediation:** Apply `_sanitize_query_value()` to ALL query template parameters. Add unit tests for injection payloads.

### CRIT-02: HTTPS Not Enforced in Nginx Configuration
**File:** `QBMigrationServer/deploy/nginx.conf:40-41,148-172`
**Severity:** CRITICAL | **Category:** Transport Security | **CWE:** CWE-319
**Description:** HTTP-to-HTTPS redirect is commented out. HTTPS server block entirely commented. All traffic in plaintext by default.
**Impact:** Man-in-the-middle attacks on all user sessions, credential theft, data interception.
**Remediation:** Uncomment HTTPS block, enforce HTTP-to-HTTPS redirect, require valid TLS certificate.

### CRIT-03: CloudFormation Database Password as Stack Parameter
**File:** `aws/cloudformation.yaml:10-14`
**Severity:** CRITICAL | **Category:** Secret Management | **CWE:** CWE-798
**Description:** `DBPassword` defined as CloudFormation parameter (NoEcho=true but stored in stack history). Visible in CloudFormation API responses and CloudTrail logs.
**Impact:** Historical password exposure if stack details queried.
**Remediation:** Use AWS Secrets Manager with CloudFormation `DynamicReference` (resolve:secretsmanager).

### CRIT-04: Race Condition in Temporary File Deletion
**File:** `QBMigrationService/orchestrator.py:369`, `main.py:369`
**Severity:** CRITICAL | **Category:** Data Security | **CWE:** CWE-367 (TOCTOU)
**Description:** Temporary decrypted file scheduled for deletion but could be accessed by other processes between migration completion and secure deletion.
**Impact:** Plaintext financial data accessible in temp directory window.
**Remediation:** Implement file locking; use immediate secure deletion on completion/failure; restrict temp directory permissions.

### CRIT-05: Token Leakage Risk in OAuth Error Paths
**File:** `QBMigrationService/oauth_manager.py:369`, `qbo_client.py:668`
**Severity:** CRITICAL | **Category:** Information Disclosure | **CWE:** CWE-532
**Description:** OAuth token refresh error paths may expose `response.text` containing tokens in error messages or logs.
**Impact:** OAuth tokens exposed in application logs, enabling account takeover.
**Remediation:** Strip all response bodies from error messages. Log only status codes and sanitized error descriptions.

### CRIT-06: Insecure Key Derivation Fallback Without KMS
**File:** `QBMigrationService/oauth_manager.py:186-193`
**Severity:** CRITICAL | **Category:** Weak Cryptography | **CWE:** CWE-326
**Description:** When KMS is unavailable, encryption key derived from `client_secret` with only 100k PBKDF2 iterations. If client_secret is compromised, all tokens are derivable.
**Impact:** Complete token compromise if client_secret leaked.
**Remediation:** Require KMS in production (enforce via config validation). Increase iterations to 600k+ for fallback.

### CRIT-07: EC2 User Data Script Credential Exposure
**File:** `QBMigrationServer/aws/ec2_user_data.ps1:248-251`, `deploy/ec2/environment.template:84-90`
**Severity:** CRITICAL | **Category:** Secret Management | **CWE:** CWE-312
**Description:** Template variables like `{{QBO_REFRESH_TOKEN}}` injected at runtime become visible as environment variables. QBO_CLIENT_SECRET stored in plaintext environment file.
**Impact:** Child processes can read credentials; memory dumps expose secrets.
**Remediation:** Move all secrets to AWS Secrets Manager. Fetch at runtime, never store in environment files.

---

## PART 5: HIGH SEVERITY FINDINGS (P1 - Fix Within First Sprint)

### HIGH-01: Single EC2 Instance - No High Availability
**File:** `aws/cloudformation.yaml:537-601`
Single EC2Instance defined; no Auto Scaling Group or multi-AZ deployment. Complete downtime if instance fails.

### HIGH-02: Missing VPC Flow Logs, CloudTrail, and ALB Access Logs
**File:** `aws/cloudformation.yaml` (absent)
No audit trail for security incidents. Cannot investigate breaches.

### HIGH-03: No Retry Logic for OAuth Token Refresh
**File:** `QBMigrationService/oauth_manager.py:374-375`
Token refresh timeout raises immediately without retry. Long migrations fail on transient network issues.

### HIGH-04: CSP Allows unsafe-eval in Frontend and Nginx
**File:** `forensicbridge-dashboard/next.config.ts:46`, `QBMigrationServer/deploy/nginx.conf:142`
`script-src 'self' 'unsafe-inline' 'unsafe-eval'` reduces XSS mitigation effectiveness.

### HIGH-05: Frontend Session Validation Only on Mount
**File:** `forensicbridge-dashboard/src/app/(dashboard)/layout.tsx:220-249`
No periodic revalidation. Users with expired sessions continue using dashboard until next API call.

### HIGH-06: Unreliable CSRF Token Initialization
**File:** `forensicbridge-dashboard/src/app/(auth)/login/page.tsx:45-50`
CSRF token set only if server sends one in response. If dedicated CSRF endpoint fails, subsequent mutations are unprotected.

### HIGH-07: No Dependency Hash Verification
**File:** `QBMigrationServer/requirements.txt`
All versions pinned but no hash verification. Supply chain attacks via compromised PyPI packages undetected.

### HIGH-08: Lambda Functions Missing DLQ and Alerting
**File:** `QBMigrationServer/aws/lambda_cleanup.py:105-106,148-149`
Lambda errors caught silently. No SNS alerts on failures. No Dead Letter Queue.

### HIGH-09: Encryption Metadata Not Validated
**File:** `QBMigrationService/orchestrator.py:245-260`
AES key retrieved from encryption metadata without format/length validation. Invalid keys silently cause decryption failures.

### HIGH-10: Missing Rate Limiting on Frontend API Calls
**File:** `forensicbridge-dashboard/src/lib/api.ts`
No throttling mechanism at API client level. Users can trigger rapid simultaneous API calls.

### HIGH-11: No Maximum Session Duration Enforcement
**File:** `forensicbridge-dashboard/src/lib/auth.ts`
CSRF tokens have 15-minute expiry but user sessions have no absolute timeout. Sessions remain valid indefinitely.

### HIGH-12: Gunicorn PID File in /tmp Without Resource Limits
**File:** `QBMigrationServer/gunicorn.conf.py:123`
PID file in /tmp. No file descriptor or memory limits configured. Resource exhaustion DoS possible.

### HIGH-13: GitHub Release Artifacts Not Cryptographically Signed
**File:** `.github/workflows/build-installer.yml`, `release-extractor.yml`
Release artifacts uploaded without cryptographic signatures. Compromised release assets undetectable.

### HIGH-14: Unhandled Exceptions in Parallel Manager
**File:** `QBMigrationService/data_transformer.py:256,287-300`
multiprocessing Manager() context not guaranteed to exit cleanly on exception.

### HIGH-15: Missing Input Validation for Migration ID in All Paths
**File:** `QBMigrationService/config.py:33-48`
`sanitize_migration_id()` exists but usage is inconsistent across all code paths.

### HIGH-16: Decimal-to-Float Conversion in Financial Reports
**File:** `QBMigrationService/verifier.py:357-390`
Converting Decimal to float for report output loses penny-level precision.

### HIGH-17: Linux/macOS Temp File Security Gap
**File:** `QBDesktopReader/StreamingPipeline.cs:129-212`
ACL protection only applied on Windows. Linux temp files use standard umask (often world-readable).

### HIGH-18: Redis Password Complexity Not Enforced
**File:** `docker-compose.yml:103`
REDIS_PASSWORD required but no strength/length validation. Weak passwords accepted.

### HIGH-19: Bandit Security Scanner Insufficient Severity Level
**File:** `.github/workflows/python-ci.yml:69`
Bandit uses `-ll` flag catching only medium+ severity. Low-severity issues not blocked.

---

## PART 6: MEDIUM SEVERITY FINDINGS (P2 - Fix Within 30 Days)

| # | Finding | File | Description |
|---|---------|------|-------------|
| MED-01 | Silent verification failure | verifier.py:800 | Exceptions return empty list, hiding errors |
| MED-02 | Decimal silent zero conversion | verifier.py:1504 | Invalid values become 0, hiding data loss |
| MED-03 | No QBO Realm ID format validation | config.py:394 | REALM_ID not validated as numeric |
| MED-04 | Missing lock in record_created() | qbo_client.py:307 | DB insert and cache update not atomic |
| MED-05 | Incomplete audit logging | audit_logger.py:210 | Token ops not logged. SOC2 trail incomplete |
| MED-06 | No timeout on batch processing | qbo_client.py:1163 | batch_create_optimized() could hang indefinitely |
| MED-07 | Decimal context not applied everywhere | data_transformer.py:55 | QB_DECIMAL_CONTEXT not verified in all paths |
| MED-08 | Inconsistent search field validation | Frontend vault/migrations | Different limits (100 vs 200 chars) |
| MED-09 | Missing fetch timeouts | vault/page.tsx:65 | Some fetch() calls without AbortController |
| MED-10 | Verbose password validation messages | register/page.tsx:35 | Specific feedback aids attacker dictionaries |
| MED-11 | Docker health check HTTP not TLS | Dockerfile:72 | Health endpoint uses http://localhost |
| MED-12 | No EBS encryption default | cloudformation.yaml | No account-level encryption policy |
| MED-13 | DB health check timing | docker-compose.yml:48 | Race between service_healthy and DB ready |
| MED-14 | Lambda hardcoded timeout | s3_trigger.py:98 | No exponential backoff for webhooks |
| MED-15 | S3 lifecycle policy inconsistency | cloudformation.yaml | LogBucket 365d vs MigrationBucket 90d |
| MED-16 | Gunicorn worker count mismatch | gunicorn.conf.py/Dockerfile | Dynamic config vs hardcoded 4 |
| MED-17 | Frontend API URL empty fallback | api.ts:30-59 | Returns empty string in non-production |
| MED-18 | Incomplete useLoadingGuard errors | useSecurityHooks.ts:160 | Thrown errors may become unhandled rejections |
| MED-19 | Missing null check in transformation | data_transformer.py:537 | Entity skip loses mapping, breaks references |
| MED-20 | No heartbeat for long migrations | orchestrator.py | Cannot distinguish hung from slow |
| MED-21 | Missing resource cleanup on exception | orchestrator.py:216 | QBO client session not closed on error |
| MED-22 | Config values logged at INFO | Multiple files | Sensitive values may appear in logs |

---

## PART 7: LOW SEVERITY FINDINGS (P3 - Fix Within 90 Days)

| # | Finding | Description |
|---|---------|-------------|
| LOW-01 | Hardcoded timeout values | No documentation for magic numbers |
| LOW-02 | Magic string status comparisons | Should be enums/constants |
| LOW-03 | Inconsistent aria-labels | Accessibility gaps for screen readers |
| LOW-04 | Missing env var documentation | No .env.example for frontend |
| LOW-05 | Console logging in production | Warnings appear if env vars unset |
| LOW-06 | Browser confirm() for destructive actions | No styled confirmation modal |
| LOW-07 | Company name unsanitized in paths | Path separators possible from untrusted source |
| LOW-08 | Deploy backup verification missing | tar exit code not checked |
| LOW-09 | CloudFormation hardcoded domain | Copy-paste risk for multi-region |
| LOW-10 | Nginx missing 404 handler | Unnecessary backend requests |
| LOW-11 | EC2 user data no progress reporting | Cannot monitor setup progress |
| LOW-12 | CI test DB default credentials | testuser:testpass in CI logs |
| LOW-13 | Dockerfile dev stage extra tools | git/vim increase attack surface |
| LOW-14 | No configuration versioning | Cannot audit config used per migration |
| LOW-15 | OAuth URLs not validated | OAUTH_TOKEN_URL format not checked |
| LOW-16 | Missing test docstrings | WHY tests exist not documented |

---

## PART 8: SECURITY DEEP DIVE

### OWASP Top 10 Assessment

| # | Category | Status | Notes |
|---|----------|--------|-------|
| A01 | Broken Access Control | PASS | RBAC with role hierarchy, require_auth/require_admin/require_mfa decorators |
| A02 | Cryptographic Failures | CONDITIONAL | AES-256-GCM, RSA-4096 excellent. KMS fallback weak (CRIT-06) |
| A03 | Injection | CONDITIONAL | SQL injection prevented in most paths. QBO query interpolation needs fix (CRIT-01) |
| A04 | Insecure Design | PASS | Defense-in-depth architecture, fail-closed patterns |
| A05 | Security Misconfiguration | FAIL | HTTPS not enforced (CRIT-02), CSP unsafe-eval (HIGH-04) |
| A06 | Vulnerable Components | CONDITIONAL | Versions pinned, no hash verification (HIGH-07) |
| A07 | Auth Failures | PASS | Argon2id, MFA, progressive CAPTCHA, account lockout, session binding |
| A08 | Data Integrity Failures | CONDITIONAL | HMAC webhooks excellent. Release artifacts unsigned (HIGH-13) |
| A09 | Logging Failures | CONDITIONAL | Security logging exists but gaps in audit trail (MED-05) |
| A10 | SSRF | PASS | No user-controlled URL fetching identified |

### Threat Model Summary

| Threat | Mitigation | Residual Risk |
|--------|------------|---------------|
| Credential theft | Argon2id, MFA, session binding | LOW - Session timeout needed |
| Data interception | AES-256-GCM, RSA-4096 hybrid encryption | MEDIUM - HTTPS not enforced |
| Injection attacks | Input sanitization, parameterized queries | MEDIUM - QBO query interpolation gap |
| Insider threat | RBAC, audit logging, encryption at rest | MEDIUM - Audit logging gaps |
| Supply chain | Version pinning, CI security scanning | HIGH - No hash verification |
| DDoS | Rate limiting, Redis-backed | LOW - Client-side throttling needed |
| Data exfiltration | PII redaction, error sanitization | LOW |

### Positive Security Findings
- Argon2id password hashing (time_cost=3, memory_cost=65536, parallelism=4)
- Constant-time comparisons throughout (auth, webhooks, encryption tags)
- Timing-attack-resistant user enumeration (fake Argon2 hash on missing user)
- AES-256-GCM authenticated encryption with proper IV/nonce management
- RSA-4096 with OAEP-SHA256 padding for key exchange
- HMAC-SHA256 webhook verification with replay prevention
- SELECT FOR UPDATE with NOWAIT for database race condition prevention
- Fernet encryption for sensitive fields at rest (MFA secrets, QBO tokens, error messages)
- Progressive CAPTCHA after 3 failed login attempts
- Session binding with User-Agent fingerprinting
- Account lockout after 5 failures (15-min duration)
- Password history tracking (last 5 passwords)
- GDPR-compliant IP hashing
- PII redaction in logs and error messages
- Secure file deletion with multi-pass overwrite (C# reader)
- Path traversal protection with symlink detection (C# reader)
- Connection string injection prevention (C# reader)

---

## PART 9: DATA INTEGRITY ASSESSMENT

### Financial Precision
- **Decimal handling:** Custom `QB_DECIMAL_CONTEXT` with 28-digit precision and ROUND_HALF_UP
- **Trial balance verification:** Enforced with $0.01 tolerance
- **Risk:** Float conversion in report output (HIGH-16) loses precision
- **Risk:** `_safe_decimal()` silent zero conversion (MED-02) hides data loss

### Data Flow Integrity
```
QBDesktop -> [QODBC/QBFC] -> C# Extractor -> [AES-256-GCM + RSA] -> Server
  -> [Decrypt + Validate Hash] -> Transform -> [QBO API] -> Verify Trial Balance
```
- SHA-256 hash verification mandatory for v3.1 uploads
- Duplicate detection via file_hash
- NDJSON streaming with checkpointing for crash recovery
- Forensic hashing for data integrity audit trail

### Identified Risks
1. Float conversion in financial report output (penny-level precision loss)
2. Silent zero substitution for invalid decimal values
3. Entity skip without mapping preservation (breaks references)
4. No per-entity validation before QBO upload

---

## PART 10: RELIABILITY ASSESSMENT

### Failure Modes Analyzed

| Scenario | Handling | Status |
|----------|----------|--------|
| Database connection failure | Health check detects, Gunicorn restarts | PARTIAL |
| S3 upload failure | Retry with backoff in C# reader | PASS |
| QBO API rate limit | Client-side rate limiter (500/min) | PASS |
| QBO API timeout | 30s read timeout, no retry | FAIL |
| OAuth token expiry | Auto-refresh mechanism | CONDITIONAL |
| Webhook delivery failure | Celery async with sync fallback | PASS |
| Mid-migration crash | Checkpoint/resume in C# reader | PARTIAL |
| Redis failure | Rate limiter degrades gracefully | PASS |
| Disk space exhaustion | Health check monitors disk | PASS |

### Single Points of Failure
1. Single EC2 instance (HIGH-01)
2. Single RDS instance (no multi-AZ in CloudFormation)
3. No circuit breaker pattern for QBO API
4. No DLQ for Lambda functions (HIGH-08)

---

## PART 11: INFRASTRUCTURE ASSESSMENT

### Deployment Architecture
- EC2 + Nginx + Gunicorn + Flask
- RDS PostgreSQL (encrypted)
- S3 for migration data (encrypted, lifecycle policies)
- Lambda for S3 triggers and cleanup
- Redis for rate limiting and upload sessions

### Gaps
- **No HA:** Single EC2 instance, no ASG
- **No CDN:** Static assets served directly
- **No WAF:** No AWS WAF in front of ALB
- **Monitoring:** Sentry + Prometheus configured but no CloudWatch alarms
- **Backup:** Database backup scheduler exists but no automated restore testing
- **DR:** No documented disaster recovery procedure

### Docker Assessment
- Multi-stage build (good)
- Non-root user in container (good)
- Health check configured (good)
- Worker count hardcoded vs. dynamic (needs fix)

---

## PART 12: TEST COVERAGE ASSESSMENT

### Statistics
- **Total test files:** 37
- **Total test functions:** 1,628
- **Total test classes:** 315
- **Lines of test code:** ~26,461
- **Minimum coverage requirement:** 70% (per pytest.ini)

### Well-Covered Areas (>80%)
- Authentication (login, registration, JWT, MFA, session)
- Webhook processing (signatures, replay, idempotency)
- Payment system (Stripe, credits, tiers)
- Security (SQL injection, XSS, CSRF, headers, input validation)
- Data transformation (date formatting, entity mapping, normalization)
- API endpoints (REST, pagination, error responses)

### Critical Coverage Gaps (<50%)
- Encryption/decryption full cycle - No end-to-end encryption test
- AWS/S3 integration - Only manual test_s3.py
- Database resilience - No connection pool, deadlock, or rollback tests
- Concurrency - Limited race condition testing
- PII redaction - No comprehensive test suite
- Performance/load - Minimal benchmarks
- Frontend UI - Basic component tests only, no interaction/e2e tests
- Disaster recovery - No restore/failover tests
- Audit compliance - No audit logging tests

---

## PART 13: OPERATIONAL READINESS

### Monitoring and Alerting
| Capability | Status | Notes |
|------------|--------|-------|
| Application logging | YES | Rotating file handler + Sentry |
| Security logging | YES | Separate security.log file |
| Performance metrics | YES | Prometheus + OpenTelemetry |
| Health checks | YES | /health with DB, S3, disk checks |
| Error alerting | PARTIAL | Sentry configured, no PagerDuty/SNS |
| Uptime monitoring | NO | No external uptime monitoring |
| Capacity alerting | NO | No CloudWatch alarms |
| Cost monitoring | NO | No AWS budget alerts |

### Runbook Readiness
- **Deployment:** Deploy script exists with rollback capability
- **Rollback:** Git stash + tag-based rollback
- **Incident response:** No documented runbook
- **Scaling:** No auto-scaling configuration
- **Secret rotation:** Secrets Manager with 5-min cache TTL supports rotation

---

## PART 14: DEPENDENCY AUDIT

### Python Dependencies (Key Packages)
| Package | Version | Status |
|---------|---------|--------|
| Flask | 3.1.2 | CURRENT |
| SQLAlchemy | 2.0.23 | CURRENT |
| cryptography | 46.0.3 | CURRENT |
| gunicorn | 23.0.0 | CURRENT |
| PyJWT | 2.10.1 | CURRENT |
| urllib3 | 2.6.3 | PATCHED (Snyk fix) |
| sentry-sdk | 2.18.0 | CURRENT |
| argon2-cffi | 23.1.0 | CURRENT |

### Frontend Dependencies
| Package | Version | Status |
|---------|---------|--------|
| next | 16.1.2 | CURRENT |
| react | 19.2.3 | CURRENT |
| zod | 3.24.5 | CURRENT |
| @tanstack/react-query | 5.80.7 | CURRENT |

### Risk: No hash pinning in requirements.txt (HIGH-07)

---

## PART 15: PRIORITIZED REMEDIATION PLAN

### Stage 1: Pre-Production (Blockers)
| # | Finding | Effort | Priority |
|---|---------|--------|----------|
| 1 | CRIT-02: Enable HTTPS in nginx | 2h | P0 |
| 2 | CRIT-01: Fix QBO query sanitization | 4h | P0 |
| 3 | CRIT-05: Sanitize OAuth error messages | 2h | P0 |
| 4 | CRIT-07: Move secrets to Secrets Manager | 8h | P0 |
| 5 | HIGH-04: Remove unsafe-eval from CSP | 1h | P0 |
| 6 | HIGH-07: Add dependency hash verification | 4h | P0 |
| 7 | HIGH-16: Fix Decimal to float conversion | 2h | P0 |

### Stage 2: First Sprint (Critical Path)
| # | Finding | Effort | Priority |
|---|---------|--------|----------|
| 8 | CRIT-04: Fix temp file race condition | 4h | P1 |
| 9 | CRIT-06: Enforce KMS in production | 4h | P1 |
| 10 | HIGH-01: Implement HA with ASG | 16h | P1 |
| 11 | HIGH-02: Add CloudTrail/VPC Flow Logs | 8h | P1 |
| 12 | HIGH-03: Add OAuth retry logic | 4h | P1 |
| 13 | HIGH-05: Frontend periodic session validation | 2h | P1 |
| 14 | HIGH-06: Guarantee CSRF token initialization | 2h | P1 |
| 15 | HIGH-09: Validate encryption metadata | 2h | P1 |

### Stage 3: 30-Day Sprint (Hardening)
All MEDIUM findings (MED-01 through MED-22)

### Stage 4: 90-Day Sprint (Polish)
All LOW findings (LOW-01 through LOW-16)

---

## PART 16: VERDICT AND SCORING

### Production Readiness Score: 72/100

### Breakdown:
- **Security Architecture:** 78/100 - Strong fundamentals, configuration gaps
- **Data Integrity:** 78/100 - Good Decimal handling, float conversion risk
- **Authentication/Authorization:** 90/100 - Excellent (Argon2id, MFA, RBAC, session binding)
- **Encryption:** 88/100 - AES-256-GCM + RSA-4096, KMS fallback concern
- **API Security:** 80/100 - Rate limiting, HMAC webhooks, input validation
- **Infrastructure:** 55/100 - Single instance, no HA, HTTPS not enforced
- **Test Coverage:** 72/100 - 1,628 tests but critical gaps remain
- **Operational Readiness:** 60/100 - Monitoring exists but no alerting/runbooks
- **Deployment Pipeline:** 70/100 - CI/CD exists, no artifact signing
- **Compliance:** 65/100 - PIPEDA region enforcement, audit logging gaps

### Verdict: **CONDITIONAL GO**

The system may proceed to production **ONLY after completing Stage 1 remediation** (7 items). The core security architecture is sound - the issues are primarily configuration (HTTPS, CSP), operational (HA, monitoring), and edge-case hardening (query sanitization, error message cleanup).

### Risk Acceptance Required For:
1. Single-instance deployment until ASG implemented (Stage 2)
2. Test coverage gaps in encryption/S3 integration until filled
3. Manual incident response until runbooks documented

---

*End of Audit Report*
*Generated: 2026-02-05 | Auditor: Claude Opus 4.5 Automated Deep Audit*
