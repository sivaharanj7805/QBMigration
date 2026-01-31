# Production Readiness Audit Report

**Date:** January 31, 2026
**Auditor:** Claude Code (Opus 4.5)
**Codebase:** ForensicBridge QB Migration Platform
**Branch:** `claude/production-readiness-review-NHHaJ`

---

## Executive Summary

This audit identifies **47 issues** across 6 severity categories that could cause problems in production. The codebase demonstrates solid security fundamentals but has several race conditions, edge cases, and configuration issues that should be addressed before production deployment.

| Severity | Count | Description |
|----------|-------|-------------|
| 🔴 **CRITICAL** | 6 | Must fix before production - can cause data loss, security breach, or system failure |
| 🟠 **HIGH** | 12 | Should fix before production - significant risk of failures |
| 🟡 **MEDIUM** | 15 | Fix soon after launch - user-facing issues or edge cases |
| 🔵 **LOW** | 10 | Improvements - code quality and maintainability |
| ⚪ **INFO** | 4 | Observations - no action required |

---

## 🔴 CRITICAL Issues (Must Fix)

### CRIT-01: Race Condition in Migration Credit Consumption

**Location:** `QBMigrationServer/api/upload.py`

**Problem:** When a user uploads a file and consumes a migration credit, there's no database-level locking. If a user rapidly submits multiple uploads, they could consume the same credit twice.

```python
# Current code (vulnerable):
credit = MigrationCredit.find_best_credit(user_id, transaction_count)
if credit:
    credit.use_for_migration(migration_id)  # No SELECT FOR UPDATE
```

**Impact:** Users could perform more migrations than purchased, causing revenue loss.

**Fix:** Use `SELECT FOR UPDATE` with database transaction:
```python
credit = MigrationCredit.query.filter_by(user_id=user_id, status='available').\
    with_for_update(skip_locked=True).first()
```

---

### CRIT-02: QBO Tokens Stored Without Encryption at Rest

**Location:** `QBMigrationServer/models/user.py:87-90`

**Problem:** QBO access/refresh tokens are stored as plain TEXT columns. While transport is encrypted (HTTPS), the tokens are stored unencrypted in the database.

```python
qbo_access_token = db.Column(db.Text)    # UNENCRYPTED!
qbo_refresh_token = db.Column(db.Text)   # UNENCRYPTED!
```

**Impact:** Database breach exposes all users' QuickBooks credentials, allowing attackers to access their financial data.

**Fix:** Encrypt tokens using Fernet with `BACKUP_ENCRYPTION_KEY`:
```python
def set_qbo_tokens(self, access_token, refresh_token):
    fernet = Fernet(current_app.config['BACKUP_ENCRYPTION_KEY'])
    self.qbo_access_token = fernet.encrypt(access_token.encode()).decode()
    self.qbo_refresh_token = fernet.encrypt(refresh_token.encode()).decode()
```

---

### CRIT-03: Stripe Webhook Returns 200 on Signature Failure

**Location:** `QBMigrationServer/api/payments.py:175-181`

**Problem:** When Stripe signature verification fails, the webhook returns HTTP 200. This prevents Stripe retries but also hides attacks where attackers forge webhook payloads.

```python
except stripe.error.SignatureVerificationError as e:
    logger.error(f"Invalid signature: {str(e)}")
    return jsonify({'received': True, 'error': 'Invalid signature'}), 200  # WRONG!
```

**Impact:** Attackers can forge fake payment completions to activate credits without paying.

**Fix:** Return 400 for invalid signatures (Stripe will retry with backoff):
```python
except stripe.error.SignatureVerificationError as e:
    logger.error(f"SECURITY: Invalid Stripe signature from {request.remote_addr}")
    return jsonify({'error': 'Invalid signature'}), 400
```

---

### CRIT-04: EC2 Instance Receives QBO Credentials in User Data

**Location:** `QBMigrationServer/utils/aws_manager.py:515-686`

**Problem:** The EC2 user data script retrieves QBO credentials via AWS CLI commands. If the instance is compromised before cleanup, credentials are exposed. User data is logged to `/var/log/cloud-init-output.log`.

**Impact:** Compromised EC2 instance exposes customer QBO credentials.

**Fix:** Use AWS Secrets Manager with IAM role-based access and ensure the instance IAM role has time-limited access. Delete the secret immediately after retrieval in the worker script rather than at termination.

---

### CRIT-05: No Idempotency on Stripe Webhook Handler

**Location:** `QBMigrationServer/api/payments.py:199-249`

**Problem:** The `handle_successful_payment` function checks `if credit.payment_status == 'paid': return` but this check is not atomic with the update. Concurrent webhook deliveries can cause double-processing.

**Impact:** Duplicate credit activation, revenue accounting errors.

**Fix:** Use database-level idempotency key:
```python
# Add unique constraint on stripe_payment_intent_id
# Use INSERT ... ON CONFLICT DO NOTHING pattern
```

---

### CRIT-06: Hardcoded Development Path in Dashboard API

**Location:** `QBMigrationServer/api/dashboard_api.py:26-27`

**Problem:** Hardcoded path `/home/user/QBMigration/QBMigrationService` that won't exist in production.

```python
if '/home/user/QBMigration/QBMigrationService' not in sys.path:
    sys.path.insert(0, '/home/user/QBMigration/QBMigrationService')
```

**Impact:** Application will fail to import `LeadSheetMapper` in production, causing Caseware exports to fail.

**Fix:** Use relative path from app root or environment variable:
```python
import os
service_path = os.getenv('QBM_SERVICE_PATH', os.path.join(os.path.dirname(__file__), '..', '..', 'QBMigrationService'))
```

---

## 🟠 HIGH Severity Issues

### HIGH-01: Missing Transaction Rollback in Credit Sync

**Location:** `QBMigrationServer/api/auth.py:427-458`

**Problem:** Auto-sync of legacy credits in `/me` endpoint doesn't wrap operations in try-except with rollback. If partial credits are created before an error, database becomes inconsistent.

---

### HIGH-02: Cleanup Scheduler Can Leave Orphaned Resources

**Location:** `QBMigrationServer/utils/cleanup_scheduler.py:98-132`

**Problem:** If `cleanup_migration()` partially succeeds (e.g., S3 deleted but EC2 termination fails), the migration is not marked for re-cleanup. Resources remain orphaned.

**Fix:** Track individual cleanup steps and retry failed operations.

---

### HIGH-03: JWT Token Has No Revocation Mechanism

**Location:** `QBMigrationServer/api/auth.py:60-68`

**Problem:** JWT tokens are valid until expiration (24 hours). If a user's account is compromised, there's no way to invalidate existing tokens.

**Fix:** Add token version to user model and include in JWT. Increment on password change/logout.

---

### HIGH-04: S3 Upload Uses STANDARD_IA Without Lifecycle for Failed Migrations

**Location:** `QBMigrationServer/utils/aws_manager.py:106`

**Problem:** Uploads use `StorageClass: 'STANDARD_IA'` but lifecycle only applies to successful migrations. Failed uploads remain indefinitely.

**Fix:** Apply lifecycle policy at bucket level, not object level.

---

### HIGH-05: Database Connection Pool Not Monitored for Exhaustion

**Location:** `QBMigrationServer/config.py:115-122`

**Problem:** Pool size is 10 with max overflow of 20. Under load, pool exhaustion causes request timeouts. Health check shows pool status but no alerting.

**Fix:** Add CloudWatch alarm for pool usage > 80%.

---

### HIGH-06: QBO Token Refresh Race Condition

**Location:** `QBMigrationServer/api/qbo.py:236-296`

**Problem:** If multiple requests hit token refresh simultaneously, they all call Intuit API and overwrite each other's tokens. Last write wins, but intermediate tokens may be invalidated.

**Fix:** Use distributed lock (Redis) for token refresh operations.

---

### HIGH-07: Missing Input Validation on Migration ID Format

**Location:** `QBMigrationServer/api/migrations.py:176-230`

**Problem:** Migration IDs from URL parameters are not validated. While SQLAlchemy parameterizes queries, malformed IDs cause unnecessary database queries.

**Fix:** Add UUID format validation before database lookup.

---

### HIGH-08: Caseware Bundle Encryption Key Derivation Uses Migration ID as Salt

**Location:** `QBMigrationServer/api/dashboard_api.py:738-752`

**Problem:** Using predictable migration ID as PBKDF2 salt reduces security. Attacker knowing migration ID can precompute.

**Fix:** Use random salt and store with the encrypted file.

---

### HIGH-09: Frontend API Client Lacks Retry Logic

**Location:** `forensicbridge-dashboard/src/lib/api.ts`

**Problem:** No automatic retry for transient network failures. Users see errors for temporary issues.

**Fix:** Add exponential backoff retry for 5xx errors and network failures.

---

### HIGH-10: Webhook Signature Window Too Wide

**Location:** `QBMigrationServer/api/webhooks.py` (referenced in exploration)

**Problem:** Replay attack window is 5 minutes. Captured webhooks can be replayed within this window.

**Fix:** Reduce to 30-60 seconds and add nonce tracking.

---

### HIGH-11: No Rate Limiting on Webhook Endpoints

**Location:** `QBMigrationServer/api/webhooks.py`

**Problem:** Webhook endpoints have no rate limiting. An attacker could flood with requests to consume resources.

**Fix:** Add rate limiting by source IP, even though webhooks are signed.

---

### HIGH-12: Password Reset Not Implemented

**Location:** `QBMigrationServer/api/auth.py`

**Problem:** No password reset functionality. Users who forget passwords cannot recover their accounts.

**Fix:** Implement email-based password reset with time-limited tokens.

---

## 🟡 MEDIUM Severity Issues

### MED-01: Stripe API Key Loaded at Module Import

**Location:** `QBMigrationServer/api/payments.py:23`

```python
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')  # At import time
```

**Problem:** If environment variable isn't set at import time, Stripe calls will fail silently.

**Fix:** Set API key in request context or validate at startup.

---

### MED-02: No Pagination on Bulk Status Endpoint

**Location:** `QBMigrationServer/api/dashboard_api.py:207-267`

**Problem:** `get_bulk_status()` returns up to 100 migrations without pagination. Large result sets cause memory issues.

---

### MED-03: Certificate Generation Creates Unbounded Files

**Location:** `QBMigrationServer/api/dashboard_api.py:541-601`

**Problem:** Audit certificates are stored on disk forever. No cleanup mechanism for old certificates.

**Fix:** Add file age-based cleanup or store in S3 with lifecycle.

---

### MED-04: Logging May Expose Sensitive Data

**Location:** Multiple locations

**Problem:** While email is hashed in logs, other PII like `company_name`, migration data, and error details may be logged.

---

### MED-05: Missing Health Check for Redis

**Location:** `QBMigrationServer/app.py:632-722`

**Problem:** Rate limiting uses Redis in production, but health check doesn't verify Redis connectivity.

---

### MED-06: Frontend Throws on Missing API URL in Production

**Location:** `forensicbridge-dashboard/src/lib/api.ts:22-37`

**Problem:** Error is thrown at module load time, crashing the entire app instead of showing user-friendly error.

---

### MED-07: Team Invite Token Not Cryptographically Random

**Location:** `QBMigrationServer/models/team_invite.py`

**Problem:** Invite tokens should use `secrets.token_urlsafe()` rather than potentially predictable methods.

---

### MED-08: No Timeout on External HTTP Calls

**Location:** `QBMigrationServer/api/qbo.py:108-117`

**Problem:** Requests to Intuit OAuth endpoints have no timeout. Hanging connections block workers.

**Fix:** Add `timeout=(10, 30)` to all `requests.post/get` calls.

---

### MED-09: Database Migration Uses Raw SQL

**Location:** `QBMigrationServer/app.py:173-262`

**Problem:** Auto-migration uses raw SQL instead of Alembic. Version tracking is manual and error-prone.

---

### MED-10: Missing Index on MigrationCredit Queries

**Location:** `QBMigrationServer/models/migration_credit.py`

**Problem:** Queries filter by `user_id`, `status`, `payment_status` but no composite index exists.

**Fix:** Add index on `(user_id, status, payment_status)`.

---

### MED-11: APScheduler May Miss Jobs on App Restart

**Location:** `QBMigrationServer/utils/cleanup_scheduler.py:135-182`

**Problem:** Background scheduler jobs are in-memory. If app restarts during a scheduled run, cleanup is skipped.

**Fix:** Use persistent job store (database or Redis).

---

### MED-12: No Graceful Shutdown Handler

**Location:** `QBMigrationServer/app.py`

**Problem:** No signal handlers for SIGTERM/SIGINT. In-flight requests may be interrupted.

---

### MED-13: Caseware Temp Files Written to App Directory

**Location:** `QBMigrationServer/api/dashboard_api.py:690`

**Problem:** Caseware bundles are written relative to `current_app.root_path`. In containerized deployments, this may not be writable.

---

### MED-14: Missing CSRF Protection on State-Changing GETs

**Location:** `QBMigrationServer/api/qbo.py:152-201`

**Problem:** `/api/qbo/disconnect` accepts GET requests for a state-changing operation.

---

### MED-15: Error Sanitizer Has Regex Performance Issues

**Location:** `QBMigrationServer/utils/error_sanitizer.py:22-61`

**Problem:** Multiple regex patterns are applied sequentially on every error. Complex patterns can cause ReDoS.

---

## 🔵 LOW Severity Issues

### LOW-01: Inconsistent Date Handling

**Location:** Multiple files

**Problem:** Some code uses `datetime.utcnow()`, some uses `datetime.now()`. Timestamps may be inconsistent.

---

### LOW-02: No API Versioning

**Location:** All API endpoints

**Problem:** All endpoints are at `/api/*` with no version prefix. Breaking changes require client updates.

---

### LOW-03: Hardcoded Tier Definitions in Multiple Places

**Location:** `QBMigrationServer/api/auth.py:539-581`, `QBMigrationServer/models/migration_credit.py:45-76`

**Problem:** Tier configurations are duplicated in User model and MigrationCredit model.

---

### LOW-04: Missing Type Hints

**Location:** Most Python files

**Problem:** Many functions lack type hints, making refactoring risky.

---

### LOW-05: Test Files Have Hardcoded Passwords

**Location:** `QBMigrationServer/tests/test_production_ready.py:26`

**Problem:** Test passwords like `TestPass123!` are committed to source control.

---

### LOW-06: Console Logging in Production

**Location:** `QBMigrationServer/app.py:67-68`

**Problem:** Console handler is added to root logger even in production.

---

### LOW-07: Magic Numbers in Code

**Location:** Multiple files

**Problem:** Numbers like `24` (hours), `30` (batch size), `5` (retries) appear without named constants.

---

### LOW-08: Unused Imports

**Location:** Various files

**Problem:** Several files import modules that aren't used, increasing load time.

---

### LOW-09: No Request ID for Tracing

**Location:** All API endpoints

**Problem:** No correlation ID is generated for requests, making debugging across services difficult.

---

### LOW-10: Documentation Comments Outdated

**Location:** Various files

**Problem:** Some docstrings reference old behavior or removed parameters.

---

## ⚪ INFORMATIONAL

### INFO-01: Good Security Practices Observed

- Argon2id password hashing with proper parameters
- Constant-time comparisons for sensitive operations
- CSRF protection via state parameter in OAuth
- Rate limiting on authentication endpoints
- Account lockout after failed attempts
- Security headers added to all responses
- PII redaction in logs (hashed emails)
- Input sanitization to prevent XSS

### INFO-02: Well-Structured Error Handling

- Centralized error sanitizer
- Production-safe error messages
- Proper exception logging with context

### INFO-03: AWS Architecture Is Sound

- Ephemeral EC2 instances reduce attack surface
- S3 server-side encryption enabled
- Secrets Manager for credential storage
- Auto-cleanup of orphaned resources

### INFO-04: Test Coverage Present

- Unit tests for core functionality
- Integration tests for API endpoints
- Security-focused test cases

---

## Recommended Action Plan

### Before Production Launch (Week 1)

1. **CRIT-01**: Add `SELECT FOR UPDATE` to credit consumption
2. **CRIT-02**: Encrypt QBO tokens at rest
3. **CRIT-03**: Return 400 for invalid Stripe signatures
4. **CRIT-05**: Add idempotency to webhook handler
5. **CRIT-06**: Fix hardcoded development path
6. **HIGH-03**: Add JWT token revocation
7. **HIGH-07**: Validate migration ID format
8. **MED-08**: Add timeouts to external HTTP calls

### First Week After Launch (Week 2)

1. **HIGH-01**: Add transaction rollback to credit sync
2. **HIGH-02**: Fix cleanup scheduler partial success
3. **HIGH-04**: Apply S3 lifecycle at bucket level
4. **HIGH-06**: Add distributed lock for token refresh
5. **HIGH-12**: Implement password reset

### First Month (Weeks 3-4)

1. **HIGH-05**: Add CloudWatch alarm for connection pool
2. **HIGH-09**: Add retry logic to frontend API client
3. **MED-01** through **MED-15**: Address all medium issues
4. **LOW-01** through **LOW-10**: Address code quality issues

---

## Conclusion

The ForensicBridge codebase demonstrates professional-grade security practices and well-thought-out architecture. However, several race conditions and edge cases need to be addressed before production deployment. The most critical issues involve payment processing and credential storage, which should be resolved immediately.

**Overall Production Readiness Score: 7.5/10**

With the critical and high-priority fixes applied, this score would rise to **9/10**.

---

*Generated by Claude Code Production Readiness Audit*
*Session: https://claude.ai/code/session_01ARBukdqkaH4GsfG4QdCmfM*
