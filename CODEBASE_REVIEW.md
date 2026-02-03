# QBMigration Codebase Review & Assessment

**Date:** February 3, 2026
**Reviewer:** Claude Opus 4.5
**Scope:** Full codebase review - QBMigrationServer, QBMigrationService, QBDesktopReader, forensicbridge-dashboard

---

## OVERALL SCORE: 38/100

---

### Score Breakdown

| Category | Weight | Score | Weighted |
|----------|--------|-------|----------|
| QBD → QBO Migration Logic | 20% | 25/100 | 5.0 |
| QBD → Caseware Export Logic | 15% | 20/100 | 3.0 |
| Server & API Correctness | 15% | 50/100 | 7.5 |
| Authentication & Security | 15% | 55/100 | 8.25 |
| Data Integrity & Models | 10% | 40/100 | 4.0 |
| Frontend & UX | 10% | 45/100 | 4.5 |
| Error Handling & Edge Cases | 5% | 30/100 | 1.5 |
| DevOps & Configuration | 5% | 55/100 | 2.75 |
| Testing Coverage | 5% | 30/100 | 1.5 |
| **Total** | **100%** | | **38/100** |

---

## CRITICAL FINDINGS (Will Cause Failures in Production)

### 1. QBD → QBO: ID Mappings Are Never Stored (data_transformer.py)

**Severity: CRITICAL — Entire QBO migration pipeline is broken**

No `transform_*` method in `data_transformer.py` ever calls `self.store_mapping()` to record QBD-to-QBO ID mappings. The `id_mapping` dict stays empty throughout transformation. Every subsequent `map_id()` call for foreign key references (Customer on Invoice, Account on Bill lines, Vendor on Purchase Orders, etc.) returns `None`.

**Impact:** Every transaction entity (Invoices, Bills, Payments, etc.) will have `null` references for all linked entities. The QBO API will reject them with 400 errors, or worse, create orphaned records.

### 2. QBO Batch API: Missing "operation" Key (qbo_client.py:852-856)

**Severity: CRITICAL — Every batch request is malformed**

```python
batch_data["BatchItemRequest"].append({
    "bId": f"bid_{j}",
    entity_type: entity_data
    # MISSING: "operation": "create"
})
```

The QBO Batch API requires an `"operation"` field in each `BatchItemRequest` item. Without it, the QBO API will reject every batch call. This means the entire batch upload pathway — the primary method for large migrations — is non-functional.

### 3. Orchestrator: entities_migrated Dict Corrupted (orchestrator.py:235-243)

**Severity: CRITICAL — Cross-entity references break mid-migration**

The `entities_migrated` variable is used simultaneously as an ID-mapping dictionary (inside `_migrate_entity`) and then overwritten with a plain integer count:

```python
# Line 331-333: ID mappings stored
existing_maps[entity_name][source_id] = result['Id']

# Line 243: OVERWRITTEN with integer
entities_migrated[entity_name] = count
```

After migrating Customers, `entities_migrated['Customers']` becomes an integer. When Invoices try to resolve Customer references via `existing_maps['Customers']`, they find an integer, not a dict. All cross-entity reference resolution silently breaks.

### 4. Caseware: Transaction Type Matching Is 100% Dead Code (caseware_exporter.py:1016-1034)

**Severity: CRITICAL — Every GL entry uses fallback logic**

The `_determine_debit_credit` method uses singular, lowercase forms (`'invoice'`, `'bill'`) in its lookup sets, but `_iterate_transactions` passes plural forms (`'invoices'`, `'bills'`). Since `'invoices' != 'invoice'`, **every single transaction** falls through to the sign-based fallback branch, making the entire classification logic dead code.

### 5. Caseware: Single-Sided GL Entries (caseware_exporter.py:992-1003)

**Severity: CRITICAL — Violates double-entry accounting**

Each GL row contains only one side of the entry. A properly structured GL export must have two rows per transaction (debit line and credit line) that net to zero. An invoice for $1,000 should produce:
- Row 1: A/R debit $1,000
- Row 2: Revenue credit $1,000

Instead, only one row is produced. Caseware's balanced-entry validation will reject the entire import.

### 6. Caseware: CSV Sanitizer Corrupts Negative Numbers (caseware_exporter.py:911)

**Severity: HIGH — Data corruption in exported files**

The `DANGEROUS_CHARS` set includes `-` (hyphen). Any field value starting with a negative sign (e.g., `"-500.00"`) or a hyphenated name (e.g., `"A/R - Trade"`) will be prefixed with a single quote: `"'-500.00"`, `"'A/R - Trade"`. This corrupts account names and any string-formatted negative amounts.

### 7. QBO: 400/403 Errors Are Incorrectly Retried (qbo_client.py)

**Severity: HIGH — Wastes API quota and delays failures**

The error handler falls through to `response.raise_for_status()` → `RequestException` catch → retry logic. 400 errors (validation failures) and 403 errors (permission denied) are retried with exponential backoff, but these errors are not transient. This wastes time and API quota without any possibility of success.

### 8. QBO: Delete Payload Format Is Wrong (qbo_client.py:727-734)

**Severity: HIGH — All delete operations fail**

Delete sends `{"Invoice": {"Id": "123", "SyncToken": "0"}}` but the QBO delete API expects a flat payload `{"Id": "123", "SyncToken": "0"}`.

### 9. Verifier: Account Type Naming Mismatch (verifier.py:348-380)

**Severity: HIGH — Trial balance verification gives wrong results**

QBD classification uses camelCase (`"AccountsReceivable"`, `"OtherCurrentAsset"`) while QBO classification uses space-separated names (`"Accounts Receivable"`, `"Other Current Asset"`). If QBD source data uses space-separated names (common from XML exports), every multi-word account type is misclassified as credit-normal instead of debit-normal, corrupting the entire trial balance verification.

### 10. Verifier: "VERIFIED" Status Hardcoded Regardless of Accuracy (verifier.py:1050-1051)

**Severity: HIGH — False audit certification**

The PDF certificate always shows `"✓ VERIFIED"` for Balance Sheet and P&L accuracy, even when the match percentage is 0%. Combined with the default-to-100% behavior when no data exists (line 1033-1035), the system can produce a certificate claiming 100% verified accuracy when nothing was actually checked.

---

## HIGH-SEVERITY FINDINGS

### 11. No Credit/Quota Check Before Starting Migration (migrations.py:403-577)

The `start_migration` endpoint launches AWS EC2 instances (real cost) without verifying the user has available migration credits. Any authenticated user can start unlimited migrations, incurring unbounded AWS costs.

### 12. Free Tier Bypass (auth.py:1048-1166)

The `select_tier` and `upgrade_tier` endpoints create `MigrationCredit` records with `price_cents=0` and `payment_status='paid'` without any payment gateway verification. Any authenticated user can get unlimited free migration credits.

### 13. IIF Parser: Address Field Mapping Is Wrong (iif_parser.py:324-329)

`BADDR1` is mapped to `Line1` but in IIF format, BADDR1 is typically the company name, not the street address. The State field (BADDR4) is completely missing.

### 14. IIF Parser: SPL Handler Is Dead Code (iif_parser.py:129-137)

The dedicated `SPL` (transaction split) handler is unreachable because `SPL` matches the general `RECORD_TYPES` check first. Transaction splits are processed without their special handling.

### 15. Data Transformer: No Parent-Child Ordering Within Entity Types

Entities within a single type are processed in source order. If a child Account appears before its parent, `map_id()` for the ParentRef returns `None`, creating an invalid sub-account with a null parent reference.

### 16. Data Transformer: Null ParentRef Propagation (data_transformer.py:1107-1108)

When `map_id()` returns `None` for a parent that hasn't been processed yet, the code still sets `ParentRef: {value: None}` and `SubAccount: True`, creating invalid entities.

### 17. Data Transformer: Bill ItemLines Silently Dropped (data_transformer.py:1238)

Bills in QB Desktop can have both ExpenseLines and ItemLines. Only ExpenseLines are processed. All item-based bill lines are silently dropped, causing financial data loss.

### 18. Multi-Currency Is Completely Non-Functional (data_transformer.py)

`enable_multi_currency` flag is stored but never read. `default_currency` is computed but never applied. No entity ever gets a `CurrencyRef` field. No exchange rates are handled. Multi-currency companies will get incorrect results.

### 19. Trial Balance Inconsistency Between Sequential and Parallel Paths

`transform()` (sequential) omits the `difference` key in the trial balance result, while `transform_parallel()` includes it. Callers expecting `difference` will get a `KeyError` on the sequential path.

### 20. QBO Rate Limiting: 40-Batch-Per-Minute Limit Not Enforced

The docstring mentions this limit, but neither `batch_create_parallel` nor `batch_create_optimized` enforces it. With 8 parallel workers, batches fire far faster than 40/minute.

### 21. OAuth Tokens Passed in Plaintext Through Celery (migrations.py:866-875)

OAuth tokens are serialized into Celery task arguments stored in Redis in plaintext. Anyone with Redis access can read QBO tokens.

### 22. Race Condition: Duplicate EC2 Provisioning (migrations.py:439-519)

Two concurrent `start_migration` requests can both see `status == 'uploaded'` and both provision EC2 instances, resulting in duplicate AWS resources and double billing.

### 23. Upload: In-Memory Chunked Upload Storage Never Cleaned Up (upload.py:812-816)

The `_chunked_uploads` dictionary has no background cleanup. Abandoned uploads leak memory indefinitely.

### 24. Upload: S3 Key Traversal via NDJSON File Names (upload.py:747)

The `file_name` from NDJSON bundle entries is used directly in the S3 key without path sanitization. A crafted filename like `../../other-migration/data` could overwrite other users' files.

### 25. Migration Model: Trial Balance Bypass (migration.py:309-380)

Passing `results=None` to `mark_as_completed` bypasses all trial balance verification despite the "MANDATORY forensic requirement" comment. A migration can be marked completed without any verification.

---

## MEDIUM-SEVERITY FINDINGS

### 26. Aggressive Name Sanitization (data_transformer.py:725)

`re.sub(r'[^\w\s\-\']', '', name)` strips `&`, `.`, `,`, `/`, `(`, `)`. "Johnson & Johnson" becomes "Johnson Johnson", "AT&T" becomes "ATT", "Smith, Inc." becomes "Smith Inc".

### 27. No AccountSubType Ever Set (data_transformer.py)

All account type mappings set AccountSubType to `None`. QBO strongly recommends AccountSubType for proper classification. This causes incorrect financial reporting categorization.

### 28. format_date Uses Config Stub Instead of self.region (data_transformer.py:802)

The date parser reads from a config stub class that defaults to `US`, ignoring the transformer's `self.region` value. UK/AU/IN users get US date parsing.

### 29. Caseware: DEBIT_TYPES Missing Asset Account Types

`Undeposited Funds`, `Prepaid Expenses`, and agricultural/manufacturing asset types are missing from DEBIT_TYPES. These accounts would be recorded as credits instead of debits.

### 30. Caseware: Trailing Comment Lines May Import as Data (caseware_exporter.py:337-345)

Lines prefixed with `#` after data rows may be parsed as data by Caseware's CSV import wizard, creating phantom accounts.

### 31. Caseware: Non-Reproducible Global Hash (caseware_exporter.py:456)

The global file hash includes `datetime.now().isoformat()`, making it impossible to independently verify the hash.

### 32. Verifier: Float Arithmetic for Financial Calculations (verifier.py:519-525)

Reconciliation balance calculations use `float` instead of `Decimal`, introducing rounding errors that can cause false positive/negative reconciliation results.

### 33. Verifier: Source Hash "Verification" Never Actually Verifies (verifier.py:900-904)

The code stores `"verified": True` unconditionally without computing a hash of the actual data to compare against the source hash.

### 34. MFA Endpoint Has No Rate Limiting (auth.py:307-374)

The `/mfa/verify` endpoint has no rate limit decorator. An attacker can brute-force 6-digit TOTP codes (1M combinations) without throttling.

### 35. CSRF Exempt on Entire Auth Blueprint (app.py:675)

`csrf.exempt(auth_bp)` exempts ALL auth routes including state-changing endpoints like `select-tier`, `upgrade-tier`, and `logout`.

### 36. Health Endpoint CORS Reflects Any Origin (app.py:957-960)

The health endpoint reflects any `Origin` header back in `Access-Control-Allow-Origin`, which could be copied to other endpoints.

### 37. MFA Secret Stored as Plaintext (user.py:84)

The TOTP `mfa_secret` is stored unencrypted in the database while QBO tokens are encrypted. If the database is compromised, attackers can generate valid 2FA tokens.

### 38. JWT Has No Revocation Mechanism

Logout clears cookies but JWT tokens remain valid for 24 hours. No token blacklist exists. Intercepted tokens work after logout.

### 39. Migrations Page Stats From Current Page Only (migrations/page.tsx:374-381)

Stats (total, completed, processing, failed) are calculated from the current page, not the full dataset. On page 2 of 10, stats show only that page's 20 items.

### 40. Display Name Race Condition in Parallel Mode (data_transformer.py:340-374)

Each parallel worker copies `shared_names` into a local set (immediately stale snapshot). Two workers can independently generate the same display name.

---

## LOWER-SEVERITY FINDINGS

### 41. O(n²) Display Name Deduplication (data_transformer.py:713)
### 42. Config stub class created on every format_date() call
### 43. IIF parser does not reset state between multiple calls
### 44. IIF parser entity type detection uses order-dependent substring matching
### 45. User model: is_locked() has unexpected side effects (commits to DB)
### 46. User model: Redundant last_login and last_login_at fields
### 47. User model: migrations_purchased can diverge from MigrationCredit table
### 48. Project model: updated_at has no default value (NULL for new records)
### 49. Frontend: Three different API client patterns used across pages
### 50. Frontend: Upload progress bar hardcoded at 60% during upload
### 51. Frontend: DestinationCard component is dead code (never called)
### 52. QBO client: QBD ID extraction uses Name/DocNumber instead of actual QBD IDs
### 53. QBO client: X-Idempotency-Key header is not supported by QBO API
### 54. QBO client: list.pop(0) is O(n) in batch queue processing
### 55. QBO client: 500 handler is dead code (overshadowed by RETRYABLE_STATUS_CODES)
### 56. Date parsing ambiguity (01/02/2024 always parsed as US format)
### 57. No file size limit in IIF parser (can OOM on large files)
### 58. LeadSheetMapper singleton has thread-unsafe mutable state
### 59. Caseware: Prior Year Balance column always empty
### 60. Caseware: Decimal-to-float precision loss in hash calculation

---

## ARCHITECTURE ASSESSMENT

### Strengths

1. **Security foundation is solid**: Argon2id password hashing, Fernet encryption, HMAC webhook verification, PII redaction, rate limiting infrastructure, and comprehensive security headers
2. **Well-structured Flask blueprint architecture**: Clean separation of concerns across 21+ blueprints
3. **Comprehensive database model design**: Proper indexing, relationship management, and auto-migration
4. **Modern frontend stack**: Next.js 16, React 19, TypeScript, React Query, Zod validation
5. **Infrastructure**: Docker multi-stage builds, docker-compose orchestration, health checks, CloudWatch monitoring
6. **Compliance awareness**: Canadian data residency (ca-central-1), GDPR data retention, PIPEDA, 7-year forensic archival
7. **Anomaly detection**: Login anomaly detection, impossible travel detection, VPN detection

### Weaknesses

1. **Core migration pipeline is fundamentally broken**: The 3 critical bugs in data_transformer + orchestrator + qbo_client mean no migration can complete successfully with correct data
2. **Caseware export produces invalid accounting output**: Single-sided entries, broken debit/credit classification, and data corruption from CSV sanitization
3. **Verification system gives false confidence**: Hardcoded "VERIFIED" status, no actual hash verification, float arithmetic for financial data
4. **Payment bypass allows unlimited free usage**: No payment verification on tier selection, no credit check before migration start
5. **No JWT revocation**: 24-hour token validity with no revocation mechanism
6. **Testing coverage is insufficient**: Tests exist but core migration logic has no unit tests

---

## RECOMMENDATIONS (Priority Order)

### P0 — Must Fix Before Any Production Use

1. Fix ID mapping storage in data_transformer.py — store mappings after each entity transform
2. Add `"operation": "create"` to batch requests in qbo_client.py
3. Fix entities_migrated corruption in orchestrator.py — use separate dicts for mappings and counts
4. Fix transaction type matching in caseware_exporter.py — use consistent singular/plural forms
5. Implement double-entry GL rows in caseware_exporter.py
6. Remove `-` from CSV DANGEROUS_CHARS
7. Add credit/quota verification before migration start
8. Fix delete payload format in qbo_client.py

### P1 — Must Fix Before Beta

9. Implement parent-child ordering within entity types
10. Fix account type naming mismatch in verifier
11. Remove hardcoded "VERIFIED" status — calculate from actual match %
12. Add rate limiting to MFA verify endpoint
13. Fix payment bypass in select_tier/upgrade_tier
14. Implement JWT token revocation (blacklist on logout)
15. Fix IIF address field mapping
16. Handle Bill ItemLines (not just ExpenseLines)
17. Fix race condition in migration start (use database row locking)

### P2 — Should Fix Before GA

18. Implement multi-currency support
19. Set AccountSubType in account mapping
20. Fix format_date to use self.region
21. Add background cleanup for chunked uploads
22. Fix S3 key traversal in NDJSON upload
23. Encrypt MFA secrets in database
24. Add trial balance verification enforcement (prevent bypass via None results)
25. Fix DEBIT_TYPES in caseware_exporter to include all asset account types

---

## CONCLUSION

The QBMigration codebase demonstrates strong architectural foundations — the security infrastructure, database design, and deployment tooling are enterprise-grade. However, **the core business logic — the actual migration and export functionality — has critical bugs that prevent it from functioning correctly**.

The three critical bugs in the QBD→QBO pipeline (no ID mappings stored, corrupted entities_migrated dict, malformed batch requests) collectively mean that **no QBO migration can complete with correct data**. The Caseware export has equally severe issues: broken debit/credit classification, single-sided entries, and data corruption from the CSV sanitizer mean the export would be **rejected by Caseware's import validation**.

The verification and audit certification system — arguably the product's key differentiator — produces **false results**: hardcoded "VERIFIED" regardless of actual accuracy, no real hash verification, and default-to-100% when data is missing.

The score of **38/100** reflects that while the shell of a production system exists (security, infrastructure, API design), the core migration logic needs substantial rework before it can reliably process real accounting data.
