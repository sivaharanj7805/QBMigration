# Zero-Defect Production Audit Report

**Project:** QBMigration (ForensicBridge)
**Date:** 2026-02-07
**Auditor:** Automated Deep Audit (claude-opus-4-6)
**Branch:** claude/zero-defect-audit-WXiiu
**Scope:** Full-stack security, reliability, and architecture audit

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [Critical Findings (P0)](#3-critical-findings-p0)
4. [High-Severity Findings (P1)](#4-high-severity-findings-p1)
5. [Medium-Severity Findings (P2)](#5-medium-severity-findings-p2)
6. [Low-Severity Findings (P3)](#6-low-severity-findings-p3)
7. [Security Posture Summary](#7-security-posture-summary)
8. [Frontend Audit](#8-frontend-audit)
9. [Backend Audit](#9-backend-audit)
10. [Database & Data Layer Audit](#10-database--data-layer-audit)
11. [Infrastructure & Deployment Audit](#11-infrastructure--deployment-audit)
12. [Dependency & Supply Chain Audit](#12-dependency--supply-chain-audit)
13. [Compliance Checklist](#13-compliance-checklist)
14. [Strengths & Good Practices](#14-strengths--good-practices)
15. [Remediation Priority Matrix](#15-remediation-priority-matrix)

---

## 1. Executive Summary

QBMigration is an enterprise financial data migration platform for migrating QuickBooks Desktop data to QuickBooks Online. The system consists of a Flask/Python backend, Next.js/React frontend, C#/.NET desktop agent, and AWS infrastructure (EC2, S3, RDS, Lambda, Secrets Manager, WAF).

### Audit Score: 78/100

| Category | Score | Max |
|----------|-------|-----|
| Authentication & Authorization | 14 | 15 |
| Cryptography & Data Protection | 12 | 15 |
| Input Validation & Injection Prevention | 11 | 15 |
| Infrastructure & Deployment Security | 9 | 15 |
| Error Handling & Logging | 10 | 10 |
| Race Condition & Concurrency Safety | 8 | 10 |
| Dependency & Supply Chain | 6 | 10 |
| Frontend Security | 8 | 10 |

### Finding Summary

| Severity | Count | Status |
|----------|-------|--------|
| **Critical (P0)** | 3 | Open |
| **High (P1)** | 8 | Open |
| **Medium (P2)** | 14 | Open |
| **Low (P3)** | 9 | Open |
| **Total** | 34 | — |

---

## 2. System Architecture Overview

```
┌─────────────────────┐     ┌─────────────────────────────┐
│ Next.js 16 Frontend │────▶│ Flask Backend (Gunicorn)     │
│ React 19 / TS       │     │ ├── JWT + Session Auth       │
│ TanStack Query       │     │ ├── CSRF Protection (WTF)   │
│ Zod Validation       │     │ ├── Rate Limiting (Redis)    │
└─────────────────────┘     │ ├── Celery Task Queue        │
                            │ └── SocketIO (WebSocket)      │
┌─────────────────────┐     └─────────┬───────────────────┘
│ C#/.NET 4.8 Agent   │              │
│ (QBDesktopReader)   │──webhooks──▶ │
│ QODBC Extraction    │              │
└─────────────────────┘     ┌────────┴────────────────────┐
                            │ Data Layer                    │
                            │ ├── PostgreSQL (RDS)          │
                            │ ├── Redis (Rate Limit/Cache)  │
                            │ ├── S3 (Encrypted Storage)    │
                            │ └── Secrets Manager           │
                            └───────────────────────────────┘
```

**Key Technologies:**
- Backend: Flask 3.1.2, SQLAlchemy 2.0.23, Celery, Redis 5.0.1
- Frontend: Next.js 16.1.2, React 19.2.3, Zod 3.23.8
- Auth: Argon2id (time_cost=3, memory_cost=64MB), TOTP MFA, JWT (HS256)
- Encryption: Fernet (AES-256-CBC), RSA-4096 (OAEP+SHA256), AES-256-GCM (v3.1 uploads)
- Infrastructure: AWS (EC2, S3, RDS, Lambda, WAF, KMS, CloudFormation)
- CI/CD: GitHub Actions, Docker multi-stage builds

---

## 3. Critical Findings (P0)

### P0-01: Plaintext Credential Fallback in Production

**File:** `QBMigrationServer/api/migrations.py:548-570`
**OWASP:** A02 (Cryptographic Failures)
**CWE:** CWE-312 (Cleartext Storage of Sensitive Information)

The migration start endpoint allows plaintext QBO credentials when `ALLOW_PLAINTEXT_CREDENTIALS=true`. If this environment variable is set in production (accidentally or by a compromised admin), OAuth tokens would be transmitted and potentially logged without encryption.

```
Impact: Complete compromise of all QBO credentials in transit
Likelihood: Medium (requires misconfiguration)
Risk: CRITICAL
```

**Recommendation:** Remove the plaintext credential fallback entirely. Require encrypted credentials always. If a migration needs to be done with plaintext credentials for debugging, require an explicit admin-only debug mode with audit logging.

---

### P0-02: Non-Atomic Credit Consumption Race Condition

**File:** `QBMigrationServer/api/migrations.py:469-472, 684-695`
**OWASP:** A04 (Insecure Design)
**CWE:** CWE-362 (Concurrent Execution Using Shared Resource with Improper Synchronization)

Credit availability is checked at line 469 but consumed at line 684-695 without `SELECT FOR UPDATE`. Two concurrent migration-start requests from the same user can both pass the credit check and consume the same credit, allowing more migrations than purchased.

```
Impact: Financial loss - users consume more credits than paid for
Likelihood: Medium (concurrent requests from same user)
Risk: CRITICAL
```

**Recommendation:** Wrap the credit check and consumption in a single transaction with `SELECT FOR UPDATE` on the user row, matching the pattern already used for EC2 provisioning at line 485-490.

---

### P0-03: No Code Signing for Desktop Agent Executables

**Files:** `.github/workflows/build-installer.yml`, `.github/workflows/release-extractor.yml`
**OWASP:** A08 (Software and Data Integrity Failures)
**CWE:** CWE-494 (Download of Code Without Integrity Check)

The .exe binaries produced by the build and release workflows are not code-signed. Users downloading the desktop agent have no way to verify the binary hasn't been tampered with. Windows SmartScreen will also block unsigned executables.

```
Impact: Supply chain attack - tampered binary could steal QuickBooks credentials
Likelihood: Medium (requires build pipeline or distribution channel compromise)
Risk: CRITICAL
```

**Recommendation:** Integrate Authenticode code signing into the CI pipeline using a code signing certificate stored in GitHub Secrets or Azure Key Vault.

---

## 4. High-Severity Findings (P1)

### P1-01: `unsafe-inline` in Content Security Policy

**File:** `forensicbridge-dashboard/next.config.ts:46-47`
**OWASP:** A05 (Security Misconfiguration)
**CWE:** CWE-79 (Cross-site Scripting)

The CSP includes `'unsafe-inline'` for both `script-src` and `style-src`. While `unsafe-eval` has been correctly removed, `unsafe-inline` still allows inline script injection if an XSS vector is found elsewhere.

```
Impact: XSS attacks can execute arbitrary inline scripts
Recommendation: Use nonce-based CSP for scripts; Tailwind CSS requires unsafe-inline for
styles but scripts should use strict-dynamic or nonce.
```

---

### P1-02: Client-Side Session Enforcement Bypassable

**File:** `forensicbridge-dashboard/src/lib/auth.ts:39-40, 321-329`
**OWASP:** A07 (Identification and Authentication Failures)

Session max duration (8h) and inactivity timeout (30min) are enforced client-side using `sessionStartTime` and `lastActivityTime` stored in memory/localStorage. An attacker with XSS access or browser dev tools can manipulate these values to maintain sessions indefinitely.

```
Impact: Session can persist beyond intended lifetime
Recommendation: Enforce session duration server-side via JWT exp claims and session
table TTL. Client-side enforcement should be defense-in-depth only.
```

---

### P1-03: Shell Injection via Deploy Script Branch Parameter

**File:** `deploy/ec2/deploy.sh:103`
**OWASP:** A03 (Injection)
**CWE:** CWE-78 (OS Command Injection)

`git checkout "$BRANCH"` uses the CLI argument without sanitization. While double quotes prevent word splitting, `$()` substitution and backticks within the variable are still evaluated by bash.

```
Impact: Remote code execution on production server
Recommendation: Validate $BRANCH against regex ^[a-zA-Z0-9/_.-]+$ before use.
```

---

### P1-04: Server Error Messages Leaked to Frontend

**Files:** `forensicbridge-dashboard/src/app/(auth)/login/page.tsx:40,66`, `register/page.tsx:242`
**OWASP:** A04 (Insecure Design)
**CWE:** CWE-209 (Generation of Error Message Containing Sensitive Information)

Login and registration pages display server error messages verbatim. Errors like "User not found" vs "Invalid credentials" enable user enumeration. Implementation-specific errors could leak database or framework details.

```
Impact: User enumeration, information disclosure
Recommendation: Map all server errors to generic client messages. Use consistent
"Invalid email or password" for all auth failures.
```

---

### P1-05: Missing HSTS Header

**File:** `forensicbridge-dashboard/next.config.ts`
**OWASP:** A05 (Security Misconfiguration)

The security headers configuration includes X-Frame-Options, X-Content-Type-Options, Referrer-Policy, and Permissions-Policy, but is missing `Strict-Transport-Security` (HSTS). Without HSTS, the first request to the site can be intercepted via SSL stripping.

```
Impact: Man-in-the-middle attack on first visit
Recommendation: Add Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

---

### P1-06: Incomplete Path Traversal Check on S3 Keys

**File:** `QBMigrationServer/api/internal.py:151-153`
**OWASP:** A01 (Broken Access Control)
**CWE:** CWE-22 (Path Traversal)

The path traversal check only validates against `".."` and leading `/`. It does not account for URL-encoded sequences (`%2e%2e`), double-encoding (`%252e%252e`), Unicode normalization (`..%c0%af`), or null bytes.

```
Impact: Access to unauthorized S3 objects
Recommendation: Use a whitelist regex for allowed S3 key characters, then normalize
the path before validation.
```

---

### P1-07: AWS SSM Parameter Store Hard Dependency

**File:** `QBMigrationServer/utils/aws_manager.py`
**OWASP:** A05 (Security Misconfiguration)

The AWS manager has a hard dependency on SSM Parameter Store for configuration. If SSM is unavailable (regional outage, IAM permission change), the entire migration service goes down with no graceful degradation.

```
Impact: Complete service outage during AWS SSM failures
Recommendation: Cache SSM values with TTL and fall back to cached values during outages.
```

---

### P1-08: Bandit Security Rules Excluded Without Justification

**File:** `.github/workflows/python-ci.yml:68-76`
**OWASP:** A06 (Vulnerable and Outdated Components)

The CI pipeline excludes Bandit rules B101 (assert_used), B105/B107 (hardcoded_password_string), and B110 (try_except_pass) without documented justification. B105/B107 are particularly concerning as they detect hardcoded credentials.

```
Impact: Hardcoded credentials or security issues go undetected in CI
Recommendation: Review each exclusion, document justification, and re-enable where possible.
Use inline # nosec comments for known false positives instead of global exclusions.
```

---

## 5. Medium-Severity Findings (P2)

### P2-01: PII Hash Truncation Creates Collision Risk

**File:** `QBMigrationServer/utils/pii_redaction.py`

Email hashes are truncated to 12 hex characters (48 bits). With ~280 trillion possible values, birthday paradox collisions become likely around ~17 million records. For a financial platform with audit requirements, hash collisions could link different users' PII records.

**Recommendation:** Increase hash length to at least 32 characters (128 bits).

---

### P2-02: CSRF Token Race Condition on First Request

**File:** `forensicbridge-dashboard/src/lib/auth.ts:65-69`

The first login/register request may not have a CSRF token. The code uses a `csrfRefreshInProgress` flag with a 100ms sleep, which is insufficient under high latency. A concurrent request could proceed without CSRF protection.

**Recommendation:** Ensure CSRF token is fetched before any mutation request. Use a promise-based queue instead of sleep polling.

---

### P2-03: S3 Cleanup Scales Poorly

**File:** `QBMigrationServer/utils/aws_manager.py:179-200`

S3 object deletion scans the broad `migrations/` prefix to find a specific migration's objects. With date-based path structure (`migrations/YYYY/MM/DD/`), the scan iterates over all migrations. A `MAX_PAGES` limit silently abandons cleanup if exceeded.

**Recommendation:** Store S3 object keys in the migration database record for direct deletion, or use an S3 prefix based on `migration_id`.

---

### P2-04: RSA Key File Permission Race Window

**File:** `QBMigrationServer/utils/encryption.py:127`

File permissions are set to `0o600` after the key file is created. Between file creation and `chmod`, the file is world-readable.

**Recommendation:** Use `os.open()` with `O_CREAT | O_EXCL` and mode `0o600`, then `os.fdopen()` to write.

---

### P2-05: Testing Environment Variable Bypasses Key Password

**File:** `QBMigrationServer/utils/encryption.py:98-105`

RSA key password requirement is bypassed when `PYTEST_CURRENT_TEST` environment variable is set. If this variable is present in production (e.g., from a misconfigured test runner), the key password check is skipped.

**Recommendation:** Use `FLASK_ENV == "testing"` or `app.config["TESTING"]` instead of checking for pytest environment variables.

---

### P2-06: S3 Lifecycle Rule Accumulation

**File:** `QBMigrationServer/utils/aws_manager.py:148-155`

A new S3 lifecycle rule is added on every cleanup invocation without checking for duplicates. Over time, this creates hundreds of rules impacting S3 API performance.

**Recommendation:** Check existing rules before adding, or use a single parameterized rule.

---

### P2-07: OAuth Error Details Exposed via Redirect URL

**File:** `QBMigrationServer/api/qbo.py:104-113`

OAuth error codes and messages are URL-encoded in the redirect URL. Even with sanitization, the URL appears in server access logs, browser history, and HTTP Referer headers.

**Recommendation:** Use server-side session flash messages instead of URL parameters for error details.

---

### P2-08: No Input Validation on OAuth Code/Realm ID

**File:** `QBMigrationServer/api/qbo.py:121-122`

The OAuth `code` and `realm_id` parameters from Intuit are checked for existence but not validated for format or length. Extremely long or malformed values could cause issues.

**Recommendation:** Validate `code` length (max 512) and `realm_id` format (numeric string, max 20 digits).

---

### P2-09: Default SSH CIDR Too Broad in CloudFormation

**File:** `aws/cloudformation.yaml:26`

Default `AllowedSSHCidr` is `10.0.0.0/8`, granting SSH access from the entire private network. Should default to a specific VPN/office IP range.

**Recommendation:** Change default to a restrictive CIDR (e.g., `10.0.0.0/32` to force explicit configuration).

---

### P2-10: Irreversible Git Stash in Deploy Script

**File:** `deploy/ec2/deploy.sh:99`

`git stash` silently discards uncommitted production changes without a backup or confirmation. If the script is run accidentally, production hotfixes are lost.

**Recommendation:** Use `git stash save "pre-deploy-$(date +%s)"` and log the stash reference.

---

### P2-11: Postgres Port Binding in Docker Compose

**File:** `docker-compose.yml:71`

Default PostgreSQL port binding could expose the database to all interfaces (0.0.0.0:5432) if `POSTGRES_EXPOSE_PORT` is not explicitly configured.

**Recommendation:** Default to `127.0.0.1:5432:5432` to ensure localhost-only binding.

---

### P2-12: Regex Denial-of-Service in PII Redaction

**File:** `QBMigrationServer/utils/pii_redaction.py:49, 141-148`

Email and international phone regex patterns could catastrophically backtrack on crafted input strings. Since PII redaction runs on log messages, a malicious input could slow or freeze the logging pipeline.

**Recommendation:** Add input length limits before regex matching, or use atomic groups/possessive quantifiers.

---

### P2-13: No Dependency Integrity Verification in Deploy Script

**File:** `deploy/ec2/deploy.sh`

The deploy script runs `pip install` and `npm ci` without verifying dependency integrity (no lockfile hash verification, no `--require-hashes` flag for pip).

**Recommendation:** Use `pip install --require-hashes -r requirements.txt` with a hashed requirements file.

---

### P2-14: Common Password Detection Overly Broad

**File:** `forensicbridge-dashboard/src/app/(auth)/register/page.tsx:72-86`

The `isCommonPassword()` function uses `lower.includes(pattern)` which matches substrings. Legitimate passwords like "MySecurePassword123!" would be incorrectly rejected because they contain the substring "password".

**Recommendation:** Check for exact matches against a common password dictionary, or use `zxcvbn` for entropy-based strength estimation.

---

## 6. Low-Severity Findings (P3)

### P3-01: No Key Rotation Mechanism
**File:** `QBMigrationServer/utils/encryption.py`
RSA keys and Fernet keys have no rotation policy, expiration, or versioning beyond `ENCRYPTION_KEY_VERSION`.

### P3-02: Webhook ID Unbounded Growth
**File:** `QBMigrationServer/models/migration.py`
Processed webhook IDs are stored on the Migration model for replay prevention but are never pruned.

### P3-03: All Users Share Same RSA Key Pair
**File:** `QBMigrationServer/utils/encryption.py`
No per-user or per-tenant key isolation. A key compromise exposes all users' data.

### P3-04: Request ID Collision Risk
**File:** `forensicbridge-dashboard/src/lib/api.ts:122`
Uses `Date.now()` + random substring for request deduplication. Under high concurrent load, collisions are possible.

### P3-05: No SBOM Generation in CI
**File:** `.github/workflows/python-ci.yml`
No Software Bill of Materials generated for supply chain audit trail.

### P3-06: Hardcoded Gunicorn Workers in Dockerfile
**File:** `Dockerfile:82-85`
4 workers and 2 threads are hardcoded. Should be configurable via environment variable for different deployment sizes.

### P3-07: Missing .dockerignore
**File:** Project root
No `.dockerignore` file to exclude `.git`, `node_modules`, `venv`, test files from build context.

### P3-08: SNS Alarms Not Subscribed in CloudFormation
**File:** `aws/cloudformation.yaml`
SNS topics for alarms are created but no subscription endpoints are configured, making alerts silent.

### P3-09: No Rollback Automation in Deploy Script
**File:** `deploy/ec2/deploy.sh:189-191`
Rollback command is printed but not automated. Manual rollback during incidents introduces human error risk.

---

## 7. Security Posture Summary

### OWASP Top 10 Coverage

| OWASP Category | Status | Notes |
|----------------|--------|-------|
| A01: Broken Access Control | PARTIAL | RBAC implemented; path traversal incomplete |
| A02: Cryptographic Failures | GOOD | Argon2id, AES-256, RSA-4096; plaintext fallback concern |
| A03: Injection | GOOD | UUID validation pervasive; SQLAlchemy parameterized queries |
| A04: Insecure Design | PARTIAL | Race conditions in credit system; client-side session enforcement |
| A05: Security Misconfiguration | PARTIAL | CSP has unsafe-inline; missing HSTS |
| A06: Vulnerable Components | PARTIAL | Bandit in CI but rules excluded; no SCA tool |
| A07: Auth Failures | GOOD | MFA, account lockout, session binding, rate limiting |
| A08: Data Integrity Failures | NEEDS WORK | No code signing for .exe; no SBOM |
| A09: Logging Failures | GOOD | Rotating logs, security log, PII redaction, Sentry |
| A10: SSRF | GOOD | No user-controlled URLs in server-side requests |

---

## 8. Frontend Audit

### Component: `forensicbridge-dashboard` (Next.js 16 / React 19)

**Dependencies (6 production, 11 dev):** Minimal and modern. No known critical CVEs in current versions.

| Area | Assessment |
|------|-----------|
| XSS Protection | CSP present but weakened by `unsafe-inline` |
| CSRF Protection | Implemented via double-submit pattern with `X-CSRF-Token` header |
| Token Storage | httpOnly cookies (not accessible to JavaScript) |
| Input Validation | Zod schemas for API responses; manual sanitization on forms |
| Error Handling | Server errors displayed verbatim (user enumeration risk) |
| Authentication Flow | CSRF race condition on first request |
| Password Policy | 12+ chars, upper/lower/digit/special, common password check (overly broad) |
| Accessibility | aria attributes present, label associations correct |

---

## 9. Backend Audit

### Component: `QBMigrationServer` (Flask 3.1.2)

| Area | Assessment |
|------|-----------|
| Authentication | JWT + Flask-Login hybrid; Argon2id with rehashing |
| Authorization | RBAC with role hierarchy (user→support→admin→super_admin) |
| Rate Limiting | Flask-Limiter with Redis backend; Redis required in production |
| Input Validation | UUID format validation on all ID parameters; whitelist status filters |
| SQL Injection | SQLAlchemy ORM with parameterized queries throughout |
| CSRF | Flask-WTF CSRFProtect enabled |
| File Upload | SHA-256 hash verification, v3.1 hybrid encryption (AES-256-GCM + RSA-4096) |
| Webhook Security | HMAC-SHA256 signatures, 5-min replay window, constant-time comparison |
| Session Security | Session binding via User-Agent fingerprint; session table validation |
| Encryption | Fernet for DB columns, RSA-4096 for upload encryption |
| Error Handling | Sanitized error responses, PII redaction in logs |
| Account Protection | 5-attempt lockout (15min), password history (5), breach detection |
| MFA | TOTP with encrypted secret storage; legacy columns deprecated |
| Configuration | Production requires all secrets via env vars; startup validation |

### Key Backend Risks:
1. Credit consumption race condition (P0-02)
2. Plaintext credential fallback (P0-01)
3. No idempotency tokens on migration start
4. Duplicate Celery execution paths (code duplication)

---

## 10. Database & Data Layer Audit

### Schema Design
- PostgreSQL with `SELECT FOR UPDATE` for critical sections (EC2 provisioning, webhook handling)
- SQLite fallback for development/testing with `expire_on_commit=False`
- Auto-migration on startup adds missing columns (safe with `IF NOT EXISTS`)

### Data Protection
- QBO OAuth tokens encrypted with Fernet (AES-256)
- MFA secrets encrypted (legacy plaintext columns deprecated but still exist)
- Password history hashed with Argon2id
- S3 objects encrypted at rest (AES-256 server-side)

### Retention
- Migration metadata: 7 years (2555 days) per legal/compliance
- User data: 365 days
- Webhook logs: 90 days
- S3 file TTL: 24 hours

### Concerns:
- Legacy MFA columns (`mfa_secret`, `mfa_backup_codes`) still in schema alongside encrypted versions
- Connection pool settings (10 connections, 20 overflow) may need tuning under load
- No read replicas configured for reporting queries

---

## 11. Infrastructure & Deployment Audit

### Docker
- Multi-stage build (builder→production→development)
- Non-root user (`qbmigration`) in production stage
- Health checks configured
- Missing `.dockerignore`

### AWS CloudFormation
- WAF with managed rule groups (CommonRuleSet, SQLi, KnownBadInputs)
- Auth endpoint rate limiting (100 req/IP separate from general 2000 req/IP)
- VPC segmentation (public/private subnets)
- KMS encryption with auto-rotation
- Security group isolation (ALB→EC2→RDS/Redis)

### CI/CD (GitHub Actions)
- Lint (Black, isort, flake8), Security (Bandit, Safety), Test, Type-check (mypy)
- Test coverage reporting
- Isolated test database service
- Missing: Container scanning, SBOM generation, code signing, license compliance

### Deploy Script
- Shell injection risk in branch parameter
- Irreversible git stash
- No dependency integrity verification
- No automated rollback

---

## 12. Dependency & Supply Chain Audit

### Python Dependencies (QBMigrationServer)

| Package | Version | Status |
|---------|---------|--------|
| Flask | 3.1.2 | Current |
| SQLAlchemy | 2.0.23 | Current |
| cryptography | 46.0.3 | Current |
| argon2-cffi | 23.1.0 | Current |
| boto3 | 1.35.36 | Current |
| PyJWT | 2.10.1 | Current |
| requests | 2.32.5 | Current |
| urllib3 | 2.6.3 | Pinned (Snyk fix) |
| gunicorn | 23.0.0 | Current |
| sentry-sdk | 2.18.0 | Current |

### Frontend Dependencies

| Package | Version | Status |
|---------|---------|--------|
| next | 16.1.2 | Current |
| react | 19.2.3 | Current |
| zod | 3.23.8 | Current |
| @tanstack/react-query | 5.90.17 | Current |

### Supply Chain Concerns
1. No lockfile hash verification in deployment
2. No SBOM generation
3. pip `--require-hashes` not used
4. No container image vulnerability scanning
5. No code signing for .exe artifacts
6. npm `ci` failure treated as warning in deploy script

---

## 13. Compliance Checklist

### SOC 2 Type II

| Control | Status | Notes |
|---------|--------|-------|
| CC6.1 - Logical Access | PASS | RBAC, MFA, session management |
| CC6.2 - Authentication | PASS | Argon2id, account lockout, password history |
| CC6.3 - Authorization | PASS | Role hierarchy, resource-level access control |
| CC6.6 - Encryption in Transit | PARTIAL | HTTPS enforced in production; missing HSTS |
| CC6.7 - Encryption at Rest | PASS | Fernet, AES-256, KMS, S3 server-side encryption |
| CC7.2 - Monitoring | PASS | Sentry, CloudWatch, audit logging, PII redaction |
| CC8.1 - Change Management | PARTIAL | CI/CD exists; no code signing or SBOM |

### PIPEDA (Canadian Data Residency)

| Requirement | Status | Notes |
|-------------|--------|-------|
| Data stored in Canada | PASS | AWS ca-central-1 default; AMI region validation |
| Data sovereignty validation | PASS | Config warns on US AMI IDs with Canadian region |
| Consent management | NOT AUDITED | Legal pages exist but content not reviewed |
| Data retention policy | PASS | 7-year retention, configurable cleanup |

### PCI DSS v4.0.1 (Partial - credential handling)

| Requirement | Status | Notes |
|-------------|--------|-------|
| 8.3.6 - Password complexity | PASS | 12+ chars, upper/lower/digit/special |
| 8.3.7 - Password history | PASS | Last 5 passwords tracked |
| 8.6 - MFA for admin access | PASS | TOTP MFA available, configurable requirement |

---

## 14. Strengths & Good Practices

The codebase demonstrates strong security awareness. Notable positive patterns:

1. **Argon2id with strong parameters** (time_cost=3, memory_cost=64MB, parallelism=4) - industry-leading password hashing
2. **UUID validation** on all API ID parameters prevents injection
3. **HMAC webhook verification** with constant-time comparison and 5-minute replay window
4. **Hybrid encryption** (AES-256-GCM + RSA-4096) for v3.1 uploads
5. **PII redaction** in logs with domain preservation and SHA-256 anonymization
6. **Production configuration validation** with mandatory environment variables
7. **SELECT FOR UPDATE** for race condition prevention on critical operations
8. **Session binding** via User-Agent fingerprint for hijacking detection
9. **Account lockout** (5 attempts, 15min) with breach detection
10. **WAF with managed rules** and separate auth endpoint rate limiting
11. **Non-root Docker** execution with multi-stage builds
12. **Sanitized error responses** preventing information leakage (backend)
13. **Redis-backed rate limiting** required in production (not in-memory)
14. **Data sovereignty validation** warning on US AMI with Canadian region
15. **Test configuration validation** preventing test pollution of production resources

---

## 15. Remediation Priority Matrix

### Immediate (Sprint 1)

| ID | Finding | Effort | Impact |
|----|---------|--------|--------|
| P0-01 | Remove plaintext credential fallback | Low | Critical |
| P0-02 | Add SELECT FOR UPDATE to credit consumption | Low | Critical |
| P1-04 | Map server errors to generic frontend messages | Low | High |
| P1-05 | Add HSTS header to next.config.ts | Low | High |
| P1-06 | Fix path traversal validation with whitelist regex | Low | High |

### Short-term (Sprint 2-3)

| ID | Finding | Effort | Impact |
|----|---------|--------|--------|
| P0-03 | Implement code signing for .exe artifacts | Medium | Critical |
| P1-01 | Implement nonce-based CSP for scripts | Medium | High |
| P1-02 | Add server-side session TTL enforcement | Medium | High |
| P1-03 | Validate deploy script branch parameter | Low | High |
| P1-08 | Review and document Bandit exclusions | Low | High |
| P2-01 | Increase PII hash length to 128 bits | Low | Medium |
| P2-02 | Fix CSRF token race with promise queue | Medium | Medium |

### Medium-term (Sprint 4-6)

| ID | Finding | Effort | Impact |
|----|---------|--------|--------|
| P1-07 | Add SSM value caching with TTL fallback | Medium | High |
| P2-03 | Store S3 keys in DB for direct deletion | Medium | Medium |
| P2-04 | Use os.open() with mode for key files | Low | Medium |
| P2-05 | Fix test detection to use FLASK_ENV | Low | Medium |
| P2-09 | Restrict default SSH CIDR | Low | Medium |
| P2-12 | Add input length limits before PII regex | Low | Medium |
| P2-13 | Enable pip --require-hashes | Medium | Medium |
| P2-14 | Replace substring check with dictionary lookup | Low | Medium |

### Long-term (Backlog)

| ID | Finding | Effort | Impact |
|----|---------|--------|--------|
| P3-01 | Implement key rotation mechanism | High | Low |
| P3-02 | Add webhook ID pruning | Low | Low |
| P3-03 | Per-tenant key isolation | High | Low |
| P3-05 | Add SBOM generation to CI | Medium | Low |
| P3-06 | Make Gunicorn workers configurable | Low | Low |
| P3-07 | Create .dockerignore | Low | Low |
| P3-08 | Configure SNS alarm subscriptions | Low | Low |
| P3-09 | Automate deployment rollback | Medium | Low |

---

*End of Zero-Defect Audit Report*
*Generated: 2026-02-07 | Auditor: claude-opus-4-6*
