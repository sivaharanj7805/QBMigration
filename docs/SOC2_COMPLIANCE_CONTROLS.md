# ForensicBridge SOC 2 Type II Compliance Controls

**Document Version:** 2.0
**Last Updated:** 2026-02-09
**Classification:** Confidential -- Acquisition Due Diligence
**Prepared For:** $10M Acquisition Technical Review
**Platform:** ForensicBridge -- QuickBooks Desktop to QuickBooks Online Migration SaaS

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [CC1 - Control Environment](#cc1---control-environment)
3. [CC2 - Communication and Information](#cc2---communication-and-information)
4. [CC3 - Risk Assessment](#cc3---risk-assessment)
5. [CC4 - Monitoring Activities](#cc4---monitoring-activities)
6. [CC5 - Control Activities](#cc5---control-activities)
7. [CC6 - Logical and Physical Access Controls](#cc6---logical-and-physical-access-controls)
8. [CC7 - System Operations](#cc7---system-operations)
9. [CC8 - Change Management](#cc8---change-management)
10. [CC9 - Risk Mitigation](#cc9---risk-mitigation)
11. [A1 - Availability](#a1---availability)
12. [C1 - Confidentiality](#c1---confidentiality)
13. [PI1 - Processing Integrity](#pi1---processing-integrity)
14. [Appendix A - File Reference Index](#appendix-a---file-reference-index)
15. [Appendix B - Control Summary Matrix](#appendix-b---control-summary-matrix)

---

## Executive Summary

ForensicBridge is a SaaS platform that migrates financial data from QuickBooks Desktop to QuickBooks Online. The platform processes sensitive financial data including customer records, invoices, vendor information, and account reconciliation data. This document maps the platform's implemented security controls to the AICPA SOC 2 Type II Trust Service Criteria.

**Key Statistics:**
- 1,981 automated tests passing with 0 failures
- ~88% code coverage (excluding infrastructure-only modules)
- 26 API blueprints with comprehensive security middleware
- AES-256-GCM encryption at rest, TLS 1.3 in transit
- Argon2id password hashing with TOTP MFA
- Full PII redaction in all application logs
- AWS infrastructure defined as code via CloudFormation

---

## CC1 - Control Environment

### CC1.1 - COSO Principle 1: Demonstrates Commitment to Integrity and Ethical Values

| Field | Value |
|---|---|
| **Control ID** | CC1.1 |
| **Control Description** | The organization demonstrates a commitment to integrity and ethical values through published legal documents, security practices, and responsible disclosure policies. |
| **Implementation Evidence** | Legal endpoints serve EULA, Privacy Policy, DPA, Cookie Policy, and Security Practices documents. RFC 9116 security.txt provides a standardized vulnerability disclosure channel. |
| **Key Files** | `QBMigrationServer/api/legal.py` (lines 1-308) -- Serves EULA, Privacy Policy, DPA, Cookie Policy, Security Practices with versioning and effective dates. `QBMigrationServer/api/security_txt.py` (lines 1-103) -- RFC 9116 security.txt at `/.well-known/security.txt` with contact, policy, and acknowledgments URLs. |
| **Testing Procedure** | 1. Verify all legal endpoints return HTTP 200 with correct document metadata. 2. Verify `/.well-known/security.txt` returns valid RFC 9116 content with Contact, Expires, and Policy fields. 3. Confirm legal document versions and effective dates are current. |
| **Status** | **Implemented** |

### CC1.2 - COSO Principle 2: Board of Directors Demonstrates Independence

| Field | Value |
|---|---|
| **Control ID** | CC1.2 |
| **Control Description** | Security governance is embedded in the development lifecycle through automated security scanning, mandatory code review, and CI/CD pipeline enforcement. |
| **Implementation Evidence** | GitHub Actions CI/CD pipeline includes mandatory security scan (Bandit), linting (flake8, black, isort), type checking (mypy), and SBOM generation (CycloneDX). All checks must pass before merge to main. |
| **Key Files** | `.github/workflows/python-ci.yml` (lines 45-77) -- Bandit security scan with B101/B110 skip-only policy. `.github/workflows/python-ci.yml` (lines 201-254) -- SBOM generation for Python and frontend dependencies. |
| **Testing Procedure** | 1. Verify CI pipeline runs on all PRs to main. 2. Confirm Bandit scan runs with only B101/B110 skipped. 3. Verify SBOM artifacts are generated and uploaded for each build. |
| **Status** | **Implemented** |

### CC1.3 - COSO Principle 3: Management Establishes Structure, Authority, and Responsibility

| Field | Value |
|---|---|
| **Control ID** | CC1.3 |
| **Control Description** | Role-Based Access Control (RBAC) enforces separation of duties with a defined role hierarchy. |
| **Implementation Evidence** | User model implements a 4-level role hierarchy: `user` (0), `support` (1), `admin` (2), `super_admin` (3). Permission checks enforce least privilege for user management, migration visibility, and admin dashboard access. |
| **Key Files** | `QBMigrationServer/models/user.py` (lines 237-290) -- RBAC implementation with `ROLE_HIERARCHY`, `has_role()`, `has_role_or_higher()`, `is_admin()`, `can_manage_users()`, `can_view_all_migrations()`, `can_access_admin_dashboard()`. |
| **Testing Procedure** | 1. Verify users with role `user` cannot access admin endpoints. 2. Verify `support` role can access admin dashboard but cannot manage users. 3. Verify `admin` can manage users. 4. Verify `super_admin` has full access. |
| **Status** | **Implemented** |

### CC1.4 - COSO Principle 4: Demonstrates Commitment to Competence

| Field | Value |
|---|---|
| **Control ID** | CC1.4 |
| **Control Description** | Code quality is enforced through automated testing, type checking, formatting standards, and comprehensive test coverage. |
| **Implementation Evidence** | 1,981 automated tests with ~88% coverage. CI pipeline enforces Black formatting, isort import sorting, flake8 linting with max-complexity=15, and mypy type checking. Coverage configuration excludes only infrastructure-specific modules. |
| **Key Files** | `.github/workflows/python-ci.yml` (lines 85-141) -- Test execution with coverage reporting. `QBMigrationServer/.coveragerc` -- Coverage configuration excluding ~30 infrastructure files. `QBMigrationServer/pytest.ini` -- Test configuration. |
| **Testing Procedure** | 1. Run `cd QBMigrationServer && pytest tests/` and verify 1,981 tests pass. 2. Verify coverage report shows ~88% coverage. 3. Confirm CI pipeline enforces all quality gates. |
| **Status** | **Implemented** |

### CC1.5 - COSO Principle 5: Enforces Accountability

| Field | Value |
|---|---|
| **Control ID** | CC1.5 |
| **Control Description** | Comprehensive audit logging creates an immutable record of all security-relevant actions with 7-year retention. |
| **Implementation Evidence** | SOC 2-compliant audit logger records structured JSON events for authentication, authorization, data access, security events, configuration changes, and system events. Events include actor identification, resource details, timestamps, correlation IDs, and data classification levels. |
| **Key Files** | `QBMigrationServer/utils/audit_logger.py` (lines 1-574) -- Full audit logging system with `AuditEventType` enum (50+ event types), `AuditEvent` dataclass with retention_days=2555 (7 years), convenience methods for auth, data access, migration, security, config, and system events. `QBMigrationServer/app.py` (lines 1017-1024) -- Audit logging initialization at startup. |
| **Testing Procedure** | 1. Verify audit log file is created at `logs/audit.log`. 2. Confirm log entries are valid JSON with required fields (event_type, timestamp, event_id, actor_id, outcome). 3. Verify retention_days defaults to 2555. 4. Confirm correlation IDs are added per-request. |
| **Status** | **Implemented** |

---

## CC2 - Communication and Information

### CC2.1 - Information Relevant to Security Objectives

| Field | Value |
|---|---|
| **Control ID** | CC2.1 |
| **Control Description** | Security-relevant information is logged, classified, and made available to appropriate personnel through structured logging and monitoring. |
| **Implementation Evidence** | Three-tier logging architecture: application log (`logs/app.log`), security log (`logs/security.log` -- WARNING+ only), and audit log (`logs/audit.log` -- structured JSON). All logs use rotating file handlers with 10MB rotation and 10-file retention. Sentry integration provides real-time error tracking with `send_default_pii=False`. |
| **Key Files** | `QBMigrationServer/app.py` (lines 59-131) -- `setup_logging()` configures rotating handlers for app, console, and security logs. `QBMigrationServer/app.py` (lines 134-157) -- `setup_sentry()` configures Sentry with PII disabled. `QBMigrationServer/utils/audit_logger.py` (lines 218-244) -- Audit logger with 50MB rotating files and 100-file retention. |
| **Testing Procedure** | 1. Verify three log files are created on startup. 2. Confirm security log only captures WARNING+ events. 3. Verify audit log entries are structured JSON. 4. Confirm Sentry sends events with `send_default_pii=False`. |
| **Status** | **Implemented** |

### CC2.2 - Internal Communication of Security Information

| Field | Value |
|---|---|
| **Control ID** | CC2.2 |
| **Control Description** | CloudWatch alarms and SNS notifications communicate security events to operations personnel in real-time. |
| **Implementation Evidence** | CloudFormation defines 8 CloudWatch alarms covering CPU utilization, database connections, storage space, ALB 5xx errors, WAF blocked requests, response time, and unhealthy hosts. All alarms route to an SNS topic with email subscription. |
| **Key Files** | `aws/cloudformation.yaml` (lines 728-901) -- CloudWatch alarms for HighCPU, DatabaseConnections, ALB5xxError, DatabaseFreeStorage, DatabaseCPU, WAFBlockedRequests, TargetResponseTime, UnhealthyHost. `aws/cloudformation.yaml` (lines 1008-1021) -- SNS topic and email subscription for alarm notifications. |
| **Testing Procedure** | 1. Deploy CloudFormation stack and verify all 8 alarms are created. 2. Verify SNS topic receives alarm state changes. 3. Confirm email subscription delivers notifications. 4. Test WAF blocked requests alarm triggers above threshold 1000. |
| **Status** | **Implemented** |

### CC2.3 - External Communication of Security Information

| Field | Value |
|---|---|
| **Control ID** | CC2.3 |
| **Control Description** | External parties can access security information through published legal documents, security practices, and vulnerability disclosure channels. |
| **Implementation Evidence** | Public endpoints serve security practices (`/legal/security`), privacy policy (`/legal/privacy`), DPA (`/legal/data-processing`), and security.txt (`/.well-known/security.txt`). Security practices document details encryption, authentication, infrastructure, compliance status, and incident response timeline (72h notification). |
| **Key Files** | `QBMigrationServer/api/legal.py` (lines 143-179) -- Security practices API with encryption details, authentication methods, infrastructure info, compliance list, and incident response contact. `QBMigrationServer/api/legal.py` (lines 182-222) -- DPA API with processor/controller details, data categories, sub-processors, and audit rights. `QBMigrationServer/api/security_txt.py` (lines 20-66) -- RFC 9116 security.txt with 48h acknowledgment commitment. |
| **Testing Procedure** | 1. Verify `/legal/security` returns encryption, auth, and compliance details. 2. Verify `/legal/api/dpa` lists sub-processors (AWS, Stripe, Intuit). 3. Confirm `/.well-known/security.txt` contains valid Contact, Policy, and Expires fields. |
| **Status** | **Implemented** |

---

## CC3 - Risk Assessment

### CC3.1 - Risk Identification and Analysis

| Field | Value |
|---|---|
| **Control ID** | CC3.1 |
| **Control Description** | Automated anomaly detection identifies and classifies security risks in real-time across login patterns, file uploads, and migration activity. |
| **Implementation Evidence** | Anomaly detection system evaluates login time patterns, rapid login attempts, impossible travel detection, suspicious IP ranges, large file uploads, daily upload volume, and rapid migration starts. Each anomaly is classified by severity (low, medium, high, critical). |
| **Key Files** | `QBMigrationServer/utils/anomaly_detector.py` (lines 1-462) -- Full anomaly detection with configurable thresholds: `max_logins_per_hour=10`, `large_file_threshold_mb=2000`, `rapid_migrations_count=3`, `rapid_migrations_window_minutes=10`. Functions: `check_login_anomalies()`, `check_upload_anomalies()`, `check_migration_anomalies()`. |
| **Testing Procedure** | 1. Trigger login anomaly by attempting >10 logins per hour. 2. Verify impossible travel detection flags IP changes within 1 hour. 3. Confirm large file upload detection flags files >2GB. 4. Verify rapid migration detection flags 3+ starts in 10 minutes. |
| **Status** | **Implemented** |

### CC3.2 - Fraud Risk Assessment

| Field | Value |
|---|---|
| **Control ID** | CC3.2 |
| **Control Description** | Session validation with device fingerprinting and activation tracking prevents fraud through session hijacking and credential sharing. |
| **Implementation Evidence** | Session activations table tracks device fingerprints, IP addresses, and extraction counts per session. Validation logs create an audit trail of all session validation attempts. User-Agent fingerprinting (SHA-256 hash) detects session hijacking. |
| **Key Files** | `QBMigrationServer/app.py` (lines 241-270) -- `session_activations` table with device_fingerprint, ip_address, status, extraction_count. `QBMigrationServer/app.py` (lines 259-270) -- `session_validation_logs` audit table. `QBMigrationServer/api/auth.py` (lines 38-52) -- `_get_user_agent_fingerprint()` SHA-256 session binding. |
| **Testing Procedure** | 1. Verify session activation creates record with device fingerprint. 2. Confirm different User-Agent produces different fingerprint. 3. Verify session validation logs are written for all validation attempts. |
| **Status** | **Implemented** |

### CC3.3 - Changes That Could Significantly Impact Internal Controls

| Field | Value |
|---|---|
| **Control ID** | CC3.3 |
| **Control Description** | Infrastructure changes are managed through Infrastructure as Code (CloudFormation) with version-controlled templates and automated deployment. |
| **Implementation Evidence** | All AWS infrastructure is defined in a single CloudFormation template with parameterized configuration. Changes require code review and CI/CD pipeline validation before deployment. The template defines VPC, security groups, WAF, KMS, S3, RDS, ElastiCache, EC2, ALB, CloudWatch, CloudTrail, and Auto Scaling. |
| **Key Files** | `aws/cloudformation.yaml` (lines 1-1132) -- Complete infrastructure definition. `.github/workflows/python-ci.yml` -- CI/CD pipeline with mandatory checks. |
| **Testing Procedure** | 1. Verify all infrastructure is defined in CloudFormation template. 2. Confirm template passes `aws cloudformation validate-template`. 3. Verify changes to IaC require PR review. |
| **Status** | **Implemented** |

---

## CC4 - Monitoring Activities

### CC4.1 - Ongoing Monitoring of Controls

| Field | Value |
|---|---|
| **Control ID** | CC4.1 |
| **Control Description** | Prometheus metrics provide continuous monitoring of application health, performance, security events, and resource utilization. |
| **Implementation Evidence** | Prometheus metrics endpoint at `/metrics` exports HTTP request latency histograms, request counters by endpoint/status, active request gauges, database connection pool stats, migration metrics, Celery task metrics, authentication attempts, rate limit hits, and upload sizes. |
| **Key Files** | `QBMigrationServer/utils/metrics.py` (lines 1-395) -- Prometheus integration with metrics: `http_requests_total`, `http_request_duration_seconds`, `http_requests_active`, `db_connection_pool_size`, `db_connections_checked_out`, `migrations_total`, `migrations_in_progress`, `auth_attempts_total`, `rate_limit_hits_total`, `errors_total`. `QBMigrationServer/app.py` (lines 996-1005) -- Metrics initialization at startup. |
| **Testing Procedure** | 1. Verify `/metrics` endpoint returns Prometheus-format metrics. 2. Confirm request counters increment on API calls. 3. Verify database pool metrics reflect actual connection state. 4. Confirm auth attempt counters track success/failure. |
| **Status** | **Implemented** |

### CC4.2 - Evaluation and Communication of Deficiencies

| Field | Value |
|---|---|
| **Control ID** | CC4.2 |
| **Control Description** | Health check endpoints with detailed diagnostics enable automated detection and communication of system deficiencies. |
| **Implementation Evidence** | Multi-level health check at `/health` verifies database connectivity, AWS S3 access, disk space, and optionally connection pool utilization (`?detailed=true`). Responses include structured JSON with per-component status. Health checks are exempt from HTTPS redirect to support load balancer probing. |
| **Key Files** | `QBMigrationServer/app.py` (lines 1115-1223) -- Health endpoint checking database, S3, disk space, connection pool. Returns structured `health_status` with `checks` dict. `Dockerfile` (lines 73-74) -- Docker HEALTHCHECK with 30s interval. `docker-compose.yml` (lines 54-59) -- Service health check configuration. |
| **Testing Procedure** | 1. Verify `/health` returns 200 with `{"status": "healthy"}` when all components healthy. 2. Verify 503 when database is unreachable. 3. Confirm `?detailed=true` includes connection pool stats. 4. Verify disk space warning when <1GB free. |
| **Status** | **Implemented** |

### CC4.3 - AWS CloudTrail and VPC Flow Logs

| Field | Value |
|---|---|
| **Control ID** | CC4.3 |
| **Control Description** | AWS CloudTrail and VPC Flow Logs provide comprehensive audit trails for all API calls and network traffic within the infrastructure. |
| **Implementation Evidence** | Multi-region CloudTrail trail with log file validation captures all AWS API events. VPC Flow Logs capture all traffic (ACCEPT, REJECT, ALL) to CloudWatch Logs with 365-day retention. CloudTrail logs stored in encrypted S3 bucket with 365-day lifecycle. |
| **Key Files** | `aws/cloudformation.yaml` (lines 992-1003) -- CloudTrail with `IsMultiRegionTrail: true`, `EnableLogFileValidation: true`. `aws/cloudformation.yaml` (lines 907-945) -- VPC Flow Logs with `TrafficType: ALL`, `RetentionInDays: 365`. `aws/cloudformation.yaml` (lines 950-968) -- CloudTrail S3 bucket with AES256 encryption and 365-day lifecycle. |
| **Testing Procedure** | 1. Verify CloudTrail trail is logging. 2. Confirm VPC Flow Logs are delivered to CloudWatch. 3. Verify CloudTrail S3 bucket has encryption enabled. 4. Confirm log file validation is enabled. |
| **Status** | **Implemented** |

---

## CC5 - Control Activities

### CC5.1 - Selection and Development of Control Activities

| Field | Value |
|---|---|
| **Control ID** | CC5.1 |
| **Control Description** | Defense-in-depth security controls are implemented at multiple layers: network (WAF, security groups), application (rate limiting, CSRF, CSP), data (encryption, PII redaction), and infrastructure (IAM, KMS). |
| **Implementation Evidence** | The application enforces comprehensive security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy), rate limiting with fail-closed behavior, CSRF protection, CORS with explicit origin allowlists, and input validation. |
| **Key Files** | `QBMigrationServer/app.py` (lines 779-868) -- Security headers middleware with CSP (no unsafe-inline for scripts), HSTS (1 year + preload), X-Frame-Options DENY, rate limit headers. `QBMigrationServer/app.py` (lines 736-773) -- CSRF protection with Flask-WTF. `QBMigrationServer/app.py` (lines 699-716) -- CORS with explicit origin allowlist, credential support, and 1-hour preflight cache. `QBMigrationServer/extensions.py` (lines 1-189) -- Three-tier rate limiting (IP+user combined, IP-only, user-only) with fail-closed behavior. |
| **Testing Procedure** | 1. Verify all security headers present in API responses. 2. Confirm CSP does not include `unsafe-inline` for `script-src`. 3. Verify CORS rejects unlisted origins. 4. Confirm rate limiting blocks requests above threshold. 5. Verify CSRF protection on state-changing endpoints. |
| **Status** | **Implemented** |

### CC5.2 - Selection and Development of General Controls over Technology

| Field | Value |
|---|---|
| **Control ID** | CC5.2 |
| **Control Description** | Automated security scanning in CI/CD pipeline detects vulnerabilities before code reaches production. |
| **Implementation Evidence** | Bandit static analysis scans all application code (excluding tests) with only B101 (assert_used) and B110 (try_except_pass) skipped. Safety checks for known vulnerabilities in dependencies. npm audit checks frontend dependencies. SBOM generation provides supply chain transparency. |
| **Key Files** | `.github/workflows/python-ci.yml` (lines 45-84) -- Security scan job with Bandit, JSON report artifact upload. `.github/workflows/python-ci.yml` (lines 201-254) -- SBOM generation with CycloneDX for Python and frontend dependencies, npm audit with `--audit-level=high`. |
| **Testing Procedure** | 1. Verify Bandit scan runs on every PR and push to main. 2. Confirm Bandit report is uploaded as artifact. 3. Verify SBOM artifacts are generated for both Python and frontend. 4. Confirm CI fails on high-severity npm audit findings. |
| **Status** | **Implemented** |

### CC5.3 - Deployment onto Infrastructure

| Field | Value |
|---|---|
| **Control ID** | CC5.3 |
| **Control Description** | Production deployment uses containerized applications with non-root execution, multi-stage builds, and automated health checking. |
| **Implementation Evidence** | Multi-stage Dockerfile creates minimal production image with non-root `qbmigration` user. Gunicorn with worker recycling (max-requests=1000) prevents memory leaks. Docker Compose enforces service dependencies with health check conditions. |
| **Key Files** | `Dockerfile` (lines 1-129) -- Multi-stage build: builder (dependencies), production (non-root user, health check), development. Line 39: `RUN groupadd -r qbmigration && useradd -r -g qbmigration qbmigration`. Line 77: `USER qbmigration`. `docker-compose.yml` (lines 1-217) -- Service definitions with health checks, dependency ordering, localhost-only port bindings. `QBMigrationServer/gunicorn.conf.py` (lines 1-203) -- Production Gunicorn configuration with request limits, security headers, and timeouts. |
| **Testing Procedure** | 1. Verify Docker image runs as non-root user (`docker exec ... whoami`). 2. Confirm health check passes within start period. 3. Verify Gunicorn worker recycling after 1000 requests. 4. Confirm service starts only after database is healthy. |
| **Status** | **Implemented** |

---

## CC6 - Logical and Physical Access Controls

### CC6.1 - Logical Access Security

| Field | Value |
|---|---|
| **Control ID** | CC6.1 |
| **Control Description** | Authentication uses Argon2id password hashing with configurable parameters, JWT tokens for session management, and Flask-Login integration for request-level authentication. |
| **Implementation Evidence** | Argon2id hasher with `time_cost=3`, `memory_cost=65536` (64MB), `parallelism=4`, `hash_len=32`, `salt_len=16`. JWT tokens with HMAC-SHA256 signing using 64+ character secret keys. Both Authorization header (Bearer token) and auth_token cookie supported. |
| **Key Files** | `QBMigrationServer/models/user.py` (lines 21-27) -- Argon2id PasswordHasher initialization with secure parameters. `QBMigrationServer/models/user.py` (lines 298-352) -- `set_password()` with validation and history, `check_password()` with Argon2id verification. `QBMigrationServer/app.py` (lines 889-932) -- Flask-Login request_loader supporting JWT Bearer header and auth_token cookie. `QBMigrationServer/config.py` (lines 20-35) -- SECRET_KEY validation requiring 64+ characters. |
| **Testing Procedure** | 1. Verify passwords are hashed with Argon2id (hash prefix `$argon2id$`). 2. Confirm JWT tokens are properly signed and validated. 3. Verify both Bearer header and cookie auth work. 4. Confirm SECRET_KEY <64 chars causes startup failure. |
| **Status** | **Implemented** |

### CC6.2 - Multi-Factor Authentication

| Field | Value |
|---|---|
| **Control ID** | CC6.2 |
| **Control Description** | TOTP-based multi-factor authentication with encrypted secret storage, backup codes, and trusted device management. |
| **Implementation Evidence** | TOTP MFA using pyotp with 30-second window (valid_window=1). MFA secrets encrypted at rest with Fernet (AES-128-CBC with HMAC-SHA256). 10 backup codes generated per user (secrets.token_hex(4)). Legacy plaintext MFA columns blocked in production with mandatory migration to encrypted columns. |
| **Key Files** | `QBMigrationServer/models/user.py` (lines 599-639) -- `_get_mfa_secret()` with encrypted/legacy fallback (legacy blocked in production). `QBMigrationServer/models/user.py` (lines 641-668) -- `_set_mfa_secret()` with mandatory encryption. `QBMigrationServer/models/user.py` (lines 729-790) -- `enable_2fa()`, `disable_2fa()`, `verify_2fa_token()` with TOTP and backup code support. `QBMigrationServer/models/user.py` (lines 998-1057) -- `migrate_legacy_mfa_data()` and `migrate_all_legacy_mfa()` for batch encryption migration. |
| **Testing Procedure** | 1. Enable MFA and verify TOTP secret is stored encrypted. 2. Verify TOTP token validation with 30-second window. 3. Verify backup code usage and removal after use. 4. Confirm plaintext MFA access returns None in production. |
| **Status** | **Implemented** |

### CC6.3 - Account Lockout and Brute Force Protection

| Field | Value |
|---|---|
| **Control ID** | CC6.3 |
| **Control Description** | Account lockout after 5 failed login attempts with 15-minute lockout period, combined with multi-tier rate limiting at application and WAF levels. |
| **Implementation Evidence** | Account locks after 5 failed attempts for 15 minutes. Rate limiting at three tiers: per-IP (login/registration), per-user+IP (general API), per-user (quotas). WAF rate limiting at 500 requests per 5 minutes globally, 100 per 5 minutes for auth endpoints. Application rate limiting uses Redis (required in production) with fail-closed behavior. |
| **Key Files** | `QBMigrationServer/models/user.py` (lines 524-576) -- `is_locked()` (pure query), `clear_expired_lock()`, `record_failed_login()` (locks at 5 attempts, 15-minute lockout). `QBMigrationServer/extensions.py` (lines 137-168) -- Three limiter instances: `limiter` (IP+user), `ip_limiter` (IP-only), `user_limiter` (user-only). Redis required in production (line 141-146). `aws/cloudformation.yaml` (lines 297-342) -- WAF RateLimitRule (500/5min global), AuthRateLimitRule (100/5min for /api/auth). |
| **Testing Procedure** | 1. Verify account locks after 5 failed login attempts. 2. Confirm lock expires after 15 minutes. 3. Verify rate limiter returns 429 above threshold. 4. Confirm rate limiter fails-closed when Redis unavailable in production. 5. Verify WAF blocks IPs exceeding 500 requests per 5 minutes. |
| **Status** | **Implemented** |

### CC6.4 - Password Policy Enforcement

| Field | Value |
|---|---|
| **Control ID** | CC6.4 |
| **Control Description** | PCI DSS v4.0.1 compliant password policy with minimum 12 characters, complexity requirements, password history (last 5), and reuse prevention with thread-safe database locking. |
| **Implementation Evidence** | Password validation requires 12+ characters, uppercase, lowercase, digit, and special character. Password history stores last 5 hashes with Argon2id verification against each. Thread-safe password history access using PostgreSQL row-level locking (`FOR SHARE`/`FOR UPDATE`). |
| **Key Files** | `QBMigrationServer/models/user.py` (lines 354-386) -- `_validate_password_strength()` with PCI DSS v4.0.1 requirements. `QBMigrationServer/models/user.py` (lines 388-459) -- `check_password_reuse()` with row-level locking and JSON structure validation. `QBMigrationServer/models/user.py` (lines 461-518) -- `_add_to_password_history()` with `FOR UPDATE` locking, 5-password retention. `QBMigrationServer/utils/validators.py` (lines 62-93) -- `validate_password()` with consistent requirements. |
| **Testing Procedure** | 1. Verify passwords <12 characters are rejected. 2. Confirm missing uppercase/lowercase/digit/special is rejected. 3. Verify previously used password (within last 5) is rejected. 4. Confirm password history is properly maintained after changes. |
| **Status** | **Implemented** |

### CC6.5 - Network Access Controls

| Field | Value |
|---|---|
| **Control ID** | CC6.5 |
| **Control Description** | AWS VPC with public/private subnet architecture, security groups enforcing least-privilege network access, and NAT Gateway for private subnet outbound access. |
| **Implementation Evidence** | VPC (10.0.0.0/16) with 2 public subnets (ALB) and 2 private subnets (RDS, ElastiCache, ASG instances). Security groups restrict: ALB (443/80 from anywhere), EC2 (5000 from ALB only, 22 from VPN CIDR only), RDS (5432 from EC2 only), Redis (6379 from EC2 only). Auto Scaling Group places instances in private subnets. |
| **Key Files** | `aws/cloudformation.yaml` (lines 39-172) -- VPC, subnets, IGW, NAT Gateway, route tables. `aws/cloudformation.yaml` (lines 176-244) -- Security groups: ALBSecurityGroup, EC2SecurityGroup (source: ALB SG), RDSSecurityGroup (source: EC2 SG), RedisSecurityGroup (source: EC2 SG). `aws/cloudformation.yaml` (lines 1078-1083) -- ASG in private subnets. |
| **Testing Procedure** | 1. Verify RDS is not publicly accessible. 2. Confirm EC2 port 5000 only accepts traffic from ALB security group. 3. Verify SSH restricted to VPN CIDR. 4. Confirm Redis only accepts traffic from EC2 security group. 5. Verify ASG instances launch in private subnets. |
| **Status** | **Implemented** |

### CC6.6 - Authentication Credential Management

| Field | Value |
|---|---|
| **Control ID** | CC6.6 |
| **Control Description** | Secrets management using AWS Secrets Manager with TTL-based caching, thread-safe access, and environment-specific validation. |
| **Implementation Evidence** | Production secrets retrieved from AWS Secrets Manager at runtime (never embedded in code or CloudFormation parameters). 5-minute cache TTL with thread-safe locking. Database passwords use Secrets Manager dynamic references in CloudFormation. RSA key passwords required via environment variable or Secrets Manager. |
| **Key Files** | `QBMigrationServer/utils/secrets_manager.py` (lines 1-343) -- Full Secrets Manager integration with TTL caching (`SECRETS_CACHE_TTL_SECONDS=300`), thread-safe lock, validation of required secrets, environment fallback. `aws/cloudformation.yaml` (lines 462-463) -- RDS password from Secrets Manager: `{{resolve:secretsmanager:forensicbridge/${Environment}/db:SecretString:password}}`. `aws/cloudformation.yaml` (lines 608-640) -- EC2 UserData loads secrets at runtime via `load_secrets.sh`. `QBMigrationServer/utils/encryption.py` (lines 41-58) -- RSA key password from env/Secrets Manager only (file-based fallback removed). |
| **Testing Procedure** | 1. Verify database password is not in CloudFormation parameters. 2. Confirm secrets are loaded from Secrets Manager in production. 3. Verify cache invalidates after TTL. 4. Confirm startup fails without RSA_KEY_PASSWORD in non-testing environments. |
| **Status** | **Implemented** |

### CC6.7 - Restrictions on Access to System Resources

| Field | Value |
|---|---|
| **Control ID** | CC6.7 |
| **Control Description** | IAM policies enforce least-privilege access to AWS resources with service-specific permissions and condition keys. |
| **Implementation Evidence** | EC2 role has three scoped policies: S3 access limited to migration bucket ARN, Secrets Manager access limited to `forensicbridge/*` prefix, KMS access limited to migration encryption key with condition requiring S3 service context (`kms:ViaService`). |
| **Key Files** | `aws/cloudformation.yaml` (lines 533-580) -- EC2Role with three policies: `ForensicBridgeS3Access` (PutObject, GetObject, DeleteObject, ListBucket on migration bucket), `ForensicBridgeSecretsAccess` (GetSecretValue on forensicbridge/* prefix), `ForensicBridgeKMSAccess` (Encrypt, Decrypt, GenerateDataKey with ViaService condition). |
| **Testing Procedure** | 1. Verify EC2 role cannot access S3 buckets outside migration bucket. 2. Confirm KMS access requires S3 service context. 3. Verify Secrets Manager access is scoped to forensicbridge/* prefix. |
| **Status** | **Implemented** |

### CC6.8 - Controls over System Inputs

| Field | Value |
|---|---|
| **Control ID** | CC6.8 |
| **Control Description** | Input validation, sanitization, and content length enforcement protect against injection attacks and resource exhaustion. |
| **Implementation Evidence** | Request size limited to 50MB (`MAX_CONTENT_LENGTH`). Email validation with RFC 5322 compliance. Password validation with complexity rules. String sanitization removes null bytes and enforces max length. WAF rules block SQL injection (AWSManagedRulesSQLiRuleSet), common exploits (AWSManagedRulesCommonRuleSet), and known bad inputs (AWSManagedRulesKnownBadInputsRuleSet). |
| **Key Files** | `QBMigrationServer/app.py` (lines 600-620) -- `check_content_length()` before_request handler rejecting oversized requests. `QBMigrationServer/utils/validators.py` (lines 1-112) -- `validate_email()` (RFC 5322), `validate_password()` (12+ chars, complexity), `sanitize_string()` (null byte removal, truncation). `aws/cloudformation.yaml` (lines 261-296) -- WAF managed rule groups: CommonRuleSet, SQLiRuleSet, KnownBadInputsRuleSet. |
| **Testing Procedure** | 1. Verify requests >50MB return 413. 2. Confirm invalid emails (consecutive dots, missing @) are rejected. 3. Verify null bytes are stripped from string inputs. 4. Confirm WAF blocks SQL injection payloads. |
| **Status** | **Implemented** |

---

## CC7 - System Operations

### CC7.1 - Detection and Monitoring of Security Events

| Field | Value |
|---|---|
| **Control ID** | CC7.1 |
| **Control Description** | Real-time detection of security events through anomaly detection, WAF monitoring, audit logging, and CloudTrail analysis. |
| **Implementation Evidence** | Anomaly detector evaluates login patterns, impossible travel, upload volumes, and migration frequency. WAF CloudWatch metrics track blocked requests with alarm at 1000/5min. Audit logger records all authentication, authorization, and data access events. CloudTrail captures all AWS API calls. |
| **Key Files** | `QBMigrationServer/utils/anomaly_detector.py` (lines 317-378) -- `check_login_anomalies()` with unusual time, rapid attempts, impossible travel, suspicious IP checks. `QBMigrationServer/utils/audit_logger.py` (lines 300-327) -- `auth_login()` logging success/failure with hashed PII. `aws/cloudformation.yaml` (lines 834-857) -- WAFBlockedRequestsAlarm with threshold 1000. |
| **Testing Procedure** | 1. Verify anomaly detector flags rapid login attempts. 2. Confirm WAF alarm triggers above 1000 blocked requests. 3. Verify audit log captures all login events. 4. Confirm CloudTrail records API activity. |
| **Status** | **Implemented** |

### CC7.2 - Incident Response

| Field | Value |
|---|---|
| **Control ID** | CC7.2 |
| **Control Description** | Incident detection triggers automated responses including account lockout, critical anomaly logging, and operational team notification via SNS. |
| **Implementation Evidence** | Critical anomalies trigger `logger.critical()` for immediate review. Account lockout activates automatically after 5 failed logins. Rate limit storage failure causes fail-closed (503) in production. Error sanitization prevents information disclosure during incidents. SNS topic delivers alarm notifications to operations team. |
| **Key Files** | `QBMigrationServer/utils/anomaly_detector.py` (lines 458-461) -- Critical anomaly logging with `logger.critical()`. `QBMigrationServer/extensions.py` (lines 101-134) -- `storage_error_handler()` fail-closed in production, 503 response. `QBMigrationServer/utils/error_sanitizer.py` (lines 345-418) -- `sanitize_error_message()` prevents stack trace/path/credential exposure. `aws/cloudformation.yaml` (lines 1008-1021) -- SNS alarm topic with email subscription. |
| **Testing Procedure** | 1. Verify critical anomaly produces CRITICAL log entry. 2. Confirm rate limit storage failure returns 503 in production. 3. Verify error messages are sanitized (no paths, no stack traces). 4. Confirm SNS delivers alarm notifications. |
| **Status** | **Implemented** |

### CC7.3 - Recovery from Security Incidents

| Field | Value |
|---|---|
| **Control ID** | CC7.3 |
| **Control Description** | Automated backup and recovery system with encrypted backups, S3 replication, integrity verification, and data retention cleanup. |
| **Implementation Evidence** | BackupManager creates encrypted database backups (Fernet) every 6 hours, uploads to S3 with AES-256 server-side encryption, verifies integrity via SHA-256 hash comparison, and cleans up backups older than retention period. Data retention cleanup strips sensitive PII from migrations >24 hours old. |
| **Key Files** | `QBMigrationServer/utils/backup.py` (lines 1-718) -- Full backup system: `create_backup()`, `_encrypt_backup()` (Fernet), `_verify_backup()` (SHA-256 + decryption test), `_upload_to_s3()`, `cleanup_old_backups()`, `restore_backup()`. PostgreSQL backups use `.pgpass` for secure authentication. `QBMigrationServer/utils/data_retention_cleanup.py` (lines 1-327) -- `cleanup_old_migration_data()` strips PII from old migrations, `cleanup_s3_temp_files()` deletes stale uploads, `run_full_cleanup()` runs both. |
| **Testing Procedure** | 1. Verify backup creates encrypted file with `.encrypted` extension. 2. Confirm SHA-256 hash file is generated alongside backup. 3. Verify backup hash verification passes. 4. Confirm S3 upload uses AES-256 encryption. 5. Verify data retention cleanup strips sensitive fields after 24 hours. |
| **Status** | **Implemented** |

---

## CC8 - Change Management

### CC8.1 - Changes to Infrastructure and Software

| Field | Value |
|---|---|
| **Control ID** | CC8.1 |
| **Control Description** | All infrastructure and application changes are managed through version-controlled code with automated CI/CD validation including lint, type check, security scan, tests, and SBOM generation. |
| **Implementation Evidence** | GitHub Actions CI/CD pipeline runs 6 parallel jobs on every PR: lint (black, isort, flake8), security scan (bandit, safety), server tests (pytest with coverage), service tests, type check (mypy), and SBOM generation. All jobs must pass before merge. CloudFormation manages infrastructure changes. |
| **Key Files** | `.github/workflows/python-ci.yml` (lines 1-254) -- Complete CI pipeline: `lint` (formatting, imports, linting), `security` (Bandit, Safety), `test-server` (1,981 tests with PostgreSQL service), `test-service`, `type-check` (mypy), `sbom` (CycloneDX + npm audit). |
| **Testing Procedure** | 1. Submit PR and verify all 6 CI jobs run. 2. Introduce a linting error and confirm CI fails. 3. Verify security scan catches a new vulnerability. 4. Confirm SBOM artifacts are generated. |
| **Status** | **Implemented** |

### CC8.2 - Testing of Changes Before Deployment

| Field | Value |
|---|---|
| **Control ID** | CC8.2 |
| **Control Description** | Comprehensive automated test suite with 1,981 tests, ~88% coverage, and PostgreSQL service container for integration testing. |
| **Implementation Evidence** | Test suite runs against PostgreSQL 15 service container in CI. Coverage reporting with XML and terminal output. Tests validate authentication, authorization, encryption, PII redaction, input validation, error sanitization, and all API endpoints. |
| **Key Files** | `.github/workflows/python-ci.yml` (lines 85-141) -- Test job with PostgreSQL service, coverage reporting, artifact upload. `QBMigrationServer/pytest.ini` -- Test configuration. `QBMigrationServer/.coveragerc` -- Coverage exclusions for infrastructure files. |
| **Testing Procedure** | 1. Run `cd QBMigrationServer && pytest tests/ -v --cov=.`. 2. Verify 1,981 tests pass with 0 failures. 3. Confirm coverage is ~88%. 4. Verify coverage report excludes only infrastructure files. |
| **Status** | **Implemented** |

### CC8.3 - Configuration Management

| Field | Value |
|---|---|
| **Control ID** | CC8.3 |
| **Control Description** | Application configuration is environment-aware with strict validation of security-critical settings at startup. |
| **Implementation Evidence** | Configuration validates SECRET_KEY (64+ chars), BACKUP_ENCRYPTION_KEY (valid Fernet key with encrypt/decrypt test), AWS AMI/region consistency, ALLOWED_ORIGINS (no localhost in production), RATELIMIT_STORAGE_URL (Redis required in production). Production startup fails on misconfiguration. |
| **Key Files** | `QBMigrationServer/app.py` (lines 494-598) -- Startup validation: SECRET_KEY length, Fernet key validity, AMI/region consistency, data sovereignty check. `QBMigrationServer/app.py` (lines 640-696) -- CORS origin validation: production requires explicit ALLOWED_ORIGINS, localhost blocked. `QBMigrationServer/extensions.py` (lines 137-146) -- Redis required for rate limiting in production. `QBMigrationServer/config.py` (lines 14-35) -- Config class with SECRET_KEY generation for dev, 64-char minimum enforcement. |
| **Testing Procedure** | 1. Verify startup fails with SECRET_KEY <64 characters. 2. Confirm invalid Fernet key causes startup failure. 3. Verify production rejects ALLOWED_ORIGINS containing localhost. 4. Confirm production requires RATELIMIT_STORAGE_URL set to Redis. |
| **Status** | **Implemented** |

---

## CC9 - Risk Mitigation

### CC9.1 - Identification and Management of Vendor Risks

| Field | Value |
|---|---|
| **Control ID** | CC9.1 |
| **Control Description** | Sub-processor relationships are documented in the Data Processing Agreement with security measures for each vendor integration. |
| **Implementation Evidence** | DPA endpoint documents three sub-processors: AWS (cloud hosting, USA/Canada), Stripe (payment processing, USA), and Intuit (QuickBooks API access, USA). QBO OAuth tokens are encrypted with Fernet before storage. Stripe handles all payment data (PCI-DSS scope delegation). |
| **Key Files** | `QBMigrationServer/api/legal.py` (lines 182-222) -- DPA API listing sub-processors with location and purpose. `QBMigrationServer/models/user.py` (lines 126-212) -- QBO token encryption with `set_qbo_tokens()` and `get_qbo_access_token()` using Fernet. Domain-separated encryption keys: `QBO_ENCRYPTION_KEY` required in production. |
| **Testing Procedure** | 1. Verify `/legal/api/dpa` lists all sub-processors. 2. Confirm QBO tokens are encrypted before database storage. 3. Verify QBO_ENCRYPTION_KEY is required in production. 4. Confirm Stripe payment data is not stored locally. |
| **Status** | **Implemented** |

### CC9.2 - Risk Assessment of Vendor Changes

| Field | Value |
|---|---|
| **Control ID** | CC9.2 |
| **Control Description** | Software supply chain is monitored through SBOM generation, dependency scanning, and automated vulnerability checks. |
| **Implementation Evidence** | CycloneDX SBOM generated for both Python and frontend (npm) dependencies on every CI run. npm audit with `--audit-level=high` flags known vulnerabilities. Bandit identifies security issues in first-party code. Dependency artifacts are uploaded for audit trail. |
| **Key Files** | `.github/workflows/python-ci.yml` (lines 201-254) -- SBOM job: `cyclonedx-py environment` for Python, `@cyclonedx/cyclonedx-npm` for frontend, `npm audit --production --audit-level=high`, artifact upload with `if-no-files-found: error`. |
| **Testing Procedure** | 1. Verify SBOM artifacts are generated on each CI run. 2. Confirm `sbom-python.json` lists all Python dependencies. 3. Verify `sbom-frontend.json` lists all npm dependencies. 4. Confirm npm audit runs against production dependencies. |
| **Status** | **Implemented** |

---

## A1 - Availability

### A1.1 - System Availability Objectives

| Field | Value |
|---|---|
| **Control ID** | A1.1 |
| **Control Description** | High availability architecture with Multi-AZ RDS, Auto Scaling Group (2-4 instances), ALB health checks, and automated instance recovery. |
| **Implementation Evidence** | RDS PostgreSQL 15 with `MultiAZ: true` for database failover. Auto Scaling Group with `MinSize: 2`, `MaxSize: 4` across two availability zones. ALB with health check at `/api/health` (30s interval). EC2 instances in private subnets behind NAT Gateway. |
| **Key Files** | `aws/cloudformation.yaml` (lines 454-483) -- RDS with `MultiAZ: true`, `BackupRetentionPeriod: 7`, `DeletionProtection: true`. `aws/cloudformation.yaml` (lines 1068-1091) -- AutoScalingGroup with `MinSize: 2`, `MaxSize: 4`, ELB health check. `aws/cloudformation.yaml` (lines 661-723) -- ALB with HTTPS listener (TLS 1.3), HTTP-to-HTTPS redirect, health check target group. |
| **Testing Procedure** | 1. Verify RDS is Multi-AZ. 2. Confirm ASG maintains 2+ healthy instances. 3. Verify ALB health check detects unhealthy instances. 4. Confirm unhealthy host alarm triggers at threshold >0. |
| **Status** | **Implemented** |

### A1.2 - Environmental Protections

| Field | Value |
|---|---|
| **Control ID** | A1.2 |
| **Control Description** | AWS infrastructure provides physical security through SOC 2 certified data centers with environmental controls, redundant power, and multi-region capabilities. |
| **Implementation Evidence** | AWS data centers in US and Canada regions with SOC 2, ISO 27001, and PCI DSS certifications. VPC spans two availability zones for redundancy. EBS volumes encrypted with AES-256. S3 with 99.999999999% durability. |
| **Key Files** | `aws/cloudformation.yaml` (lines 56-93) -- Two public subnets and two private subnets across separate availability zones. `aws/cloudformation.yaml` (lines 602-607) -- EC2 EBS with `Encrypted: true`. `aws/cloudformation.yaml` (lines 383-419) -- S3 with versioning, KMS encryption, Glacier transition at 30 days. |
| **Testing Procedure** | 1. Verify infrastructure spans 2+ availability zones. 2. Confirm EBS volumes are encrypted. 3. Verify S3 versioning is enabled. 4. Confirm S3 lifecycle transitions to Glacier at 30 days. |
| **Status** | **Implemented** |

### A1.3 - Backup and Recovery

| Field | Value |
|---|---|
| **Control ID** | A1.3 |
| **Control Description** | Multi-layer backup strategy with automated database backups, encrypted S3 storage, integrity verification, and configurable retention. |
| **Implementation Evidence** | Database backups every 6 hours (configurable) with Fernet encryption. SHA-256 integrity verification. S3 upload with AES-256 server-side encryption and STANDARD_IA storage class. RDS automated backups with 7-day retention. S3 lifecycle: 365-day expiration, 30-day Glacier transition. |
| **Key Files** | `QBMigrationServer/utils/backup.py` (lines 38-116) -- `create_backup()` with SQLite and PostgreSQL support. `QBMigrationServer/utils/backup.py` (lines 243-284) -- `_encrypt_backup()` with Fernet. `QBMigrationServer/utils/backup.py` (lines 329-436) -- `_verify_backup()` with SHA-256 hash and Fernet MAC verification. `QBMigrationServer/utils/backup.py` (lines 680-718) -- `init_backup_scheduler()` with APScheduler. `aws/cloudformation.yaml` (lines 473-474) -- RDS `BackupRetentionPeriod: 7`, `PreferredBackupWindow: '03:00-04:00'`. |
| **Testing Procedure** | 1. Verify backup scheduler runs at configured interval. 2. Confirm backup file is encrypted. 3. Verify SHA-256 hash verification passes. 4. Confirm S3 upload succeeds with encryption. 5. Verify old backups are cleaned up after retention period. |
| **Status** | **Implemented** |

---

## C1 - Confidentiality

### C1.1 - Identification and Protection of Confidential Information

| Field | Value |
|---|---|
| **Control ID** | C1.1 |
| **Control Description** | PII is identified and protected through SHA-256 hashing in logs, redaction of sensitive patterns, and data classification labels in audit events. |
| **Implementation Evidence** | PII redaction module provides: `hash_email()` (SHA-256, 128-bit prefix), `hash_ip()` (SHA-256, 64-bit prefix), `redact_phone()` (with false-positive prevention for dates, versions, IPs), `redact_ssn()`, `redact_credit_card()`, `redact_all_pii()`. ReDoS protection via 100KB input truncation. Audit events carry `data_classification` labels (public, internal, confidential, restricted). |
| **Key Files** | `QBMigrationServer/utils/pii_redaction.py` (lines 1-281) -- Full PII redaction: `hash_email()` (128-bit SHA-256), `hash_ip()` (64-bit SHA-256), `redact_phone()`, `redact_ssn()`, `redact_credit_card()`, `redact_all_pii()`, `create_safe_log_message()`. ReDoS limit at `_MAX_PII_INPUT_LENGTH = 100_000`. `QBMigrationServer/utils/audit_logger.py` (lines 191-194) -- `data_classification` field with `retention_days=2555`. |
| **Testing Procedure** | 1. Verify `hash_email("test@example.com")` returns `usr_` prefixed 128-bit hash. 2. Verify `hash_ip("192.168.1.1")` returns `ip_` prefixed 64-bit hash. 3. Confirm phone numbers are redacted to `XXX-XXX-XXXX`. 4. Verify SSNs are redacted to `XXX-XX-NNNN`. 5. Confirm input >100KB is truncated. |
| **Status** | **Implemented** |

### C1.2 - Encryption of Confidential Data at Rest

| Field | Value |
|---|---|
| **Control ID** | C1.2 |
| **Control Description** | All data at rest is encrypted using AWS KMS Customer Managed Keys for S3, AES-256 for EBS, Fernet (AES-128-CBC+HMAC) for application-level encryption, and RSA-4096 for key exchange. |
| **Implementation Evidence** | S3 bucket uses KMS CMK with automatic key rotation (`BucketKeyEnabled: true`). EBS volumes encrypted. RDS `StorageEncrypted: true`. ElastiCache `AtRestEncryptionEnabled: true`. Application-level: QBO tokens encrypted with Fernet, MFA secrets encrypted with Fernet, database backups encrypted with Fernet, RSA-4096 keys for hybrid encryption with QBDesktopReader. |
| **Key Files** | `aws/cloudformation.yaml` (lines 346-378) -- KMS CMK with `EnableKeyRotation: true`. `aws/cloudformation.yaml` (lines 387-393) -- S3 `SSEAlgorithm: aws:kms` with CMK. `aws/cloudformation.yaml` (lines 467) -- RDS `StorageEncrypted: true`. `aws/cloudformation.yaml` (lines 522-523) -- ElastiCache `AtRestEncryptionEnabled: true`. `QBMigrationServer/models/user.py` (lines 157-178) -- `set_qbo_tokens()` with Fernet encryption. `QBMigrationServer/utils/encryption.py` (lines 22-188) -- RSA-4096 EncryptionManager with OAEP+SHA-256 padding, password-protected private keys, atomic file creation with 0o600 permissions. |
| **Testing Procedure** | 1. Verify S3 objects are encrypted with KMS CMK. 2. Confirm EBS volumes are encrypted. 3. Verify RDS storage encryption is enabled. 4. Confirm QBO tokens are Fernet-encrypted in database. 5. Verify RSA private key file has 0600 permissions. |
| **Status** | **Implemented** |

### C1.3 - Encryption of Confidential Data in Transit

| Field | Value |
|---|---|
| **Control ID** | C1.3 |
| **Control Description** | All data in transit is encrypted with TLS 1.3 via ALB, HSTS enforcement, ElastiCache transit encryption, and HTTPS redirect for production traffic. |
| **Implementation Evidence** | ALB HTTPS listener uses `ELBSecurityPolicy-TLS13-1-2-2021-06` (TLS 1.3 minimum). HSTS header: `max-age=31536000; includeSubDomains; preload`. HTTP-to-HTTPS redirect (301) in production. ElastiCache `TransitEncryptionEnabled: true` with auth token. HTTPS redirect exempts health check endpoints. |
| **Key Files** | `aws/cloudformation.yaml` (lines 711-723) -- ALB HTTPS listener with `SslPolicy: ELBSecurityPolicy-TLS13-1-2-2021-06`. `QBMigrationServer/app.py` (lines 812-815) -- HSTS header with 1-year max-age, includeSubDomains, preload. `QBMigrationServer/app.py` (lines 1259-1271) -- HTTPS redirect in production (exempt health endpoints). `aws/cloudformation.yaml` (lines 521-525) -- ElastiCache `TransitEncryptionEnabled: true`, `AuthToken` from Secrets Manager. |
| **Testing Procedure** | 1. Verify ALB uses TLS 1.3 security policy. 2. Confirm HSTS header present in production responses. 3. Verify HTTP requests redirect to HTTPS (301). 4. Confirm ElastiCache requires TLS connections. |
| **Status** | **Implemented** |

### C1.4 - Disposal of Confidential Information

| Field | Value |
|---|---|
| **Control ID** | C1.4 |
| **Control Description** | Automated data retention and disposal with configurable retention periods, zero-persistence cleanup, and secure deletion from both database and S3. |
| **Implementation Evidence** | Data retention cleanup strips sensitive data from migrations >24 hours old (configurable). S3 temporary files cleaned after retention period. S3 lifecycle expires objects at 365 days with Glacier transition at 30 days. Backup cleanup removes files older than retention period. Migration data fields (trial_balance_data, live_status_data) replaced with stripped metadata. |
| **Key Files** | `QBMigrationServer/utils/data_retention_cleanup.py` (lines 29-135) -- `cleanup_old_migration_data()` strips PII from old migrations with periodic commits (every 100 records). `QBMigrationServer/utils/data_retention_cleanup.py` (lines 138-240) -- `cleanup_s3_temp_files()` deletes stale S3 objects. `aws/cloudformation.yaml` (lines 401-411) -- S3 lifecycle: `ExpirationInDays: 365`, Glacier at 30 days. `QBMigrationServer/api/legal.py` (lines 128-130) -- Privacy policy: account data 365 days, migration data 30 days, audit logs 7 years. |
| **Testing Procedure** | 1. Verify cleanup strips sensitive data from migrations >24 hours old. 2. Confirm S3 objects in uploads/ are deleted after retention. 3. Verify S3 lifecycle transitions to Glacier at 30 days. 4. Confirm backup cleanup removes expired files. |
| **Status** | **Implemented** |

### C1.5 - Error Sanitization and Information Disclosure Prevention

| Field | Value |
|---|---|
| **Control ID** | CC6.5-C |
| **Control Description** | Error messages are sanitized before client exposure to prevent information disclosure of file paths, database schema, credentials, and stack traces. |
| **Implementation Evidence** | Error sanitizer applies 40+ regex patterns to redact file paths, database errors (PostgreSQL, MySQL, SQLite), AWS credentials, API tokens, connection strings, and Python module paths. Exception type mapping provides generic messages (e.g., `ValueError` -> "Invalid input value"). QBO errors use a whitelist approach -- unknown errors return generic messages. |
| **Key Files** | `QBMigrationServer/utils/error_sanitizer.py` (lines 1-649) -- Complete error sanitization: `SENSITIVE_PATTERNS` (40+ regex), `EXCEPTION_TYPE_MESSAGES` (20+ mappings), `sanitize_error_message()`, `create_error_response()`, `sanitize_qbo_error()` (whitelist), `sanitize_qbo_error_for_url()` (XSS prevention). `QBMigrationServer/app.py` (lines 1342-1460) -- Sanitized error handlers for 400, 401, 403, 404, 413, 429, 500, and catch-all Exception. |
| **Testing Procedure** | 1. Verify production error response does not contain file paths. 2. Confirm database errors are mapped to generic messages. 3. Verify AWS credentials in errors are redacted. 4. Confirm unknown QBO errors return generic "connection_error". |
| **Status** | **Implemented** |

---

## PI1 - Processing Integrity

### PI1.1 - System Processing Accuracy and Completeness

| Field | Value |
|---|---|
| **Control ID** | PI1.1 |
| **Control Description** | Migration processing integrity is verified through file hash validation, webhook signature verification, extraction token validation, and migration status tracking. |
| **Implementation Evidence** | Migration records track `file_hash` (SHA-256 of uploaded file), progress percentage, per-entity counts (customers, vendors, invoices, bills, items), and verification results. Webhook signatures use HMAC-SHA256 with replay attack prevention (5-minute window). Extraction flow requires `extraction_token` for completion. |
| **Key Files** | `QBMigrationServer/app.py` (lines 284-339) -- Migration table with `file_hash`, `progress_percent`, entity counts, `verification_results`. `QBMigrationServer/api/webhooks.py` (lines 14-50) -- `verify_webhook_signature()` with HMAC-SHA256 and timestamp replay prevention. |
| **Testing Procedure** | 1. Verify uploaded file hash matches migration record. 2. Confirm webhook signature verification rejects invalid signatures. 3. Verify replay attack prevention rejects timestamps >5 minutes old. 4. Confirm extraction requires valid extraction_token. |
| **Status** | **Implemented** |

### PI1.2 - System Input Validation

| Field | Value |
|---|---|
| **Control ID** | PI1.2 |
| **Control Description** | All system inputs are validated at application and infrastructure layers with comprehensive type checking, format validation, and size limits. |
| **Implementation Evidence** | Application-level validation: email (RFC 5322), password (12+ chars, complexity), string sanitization (null bytes, length), content length (50MB). Infrastructure-level: WAF SQL injection rules, known bad inputs rules, request rate limiting. Gunicorn enforces request line size (4094), header count (100), and header field size (8190). |
| **Key Files** | `QBMigrationServer/utils/validators.py` (lines 1-112) -- Input validators. `QBMigrationServer/gunicorn.conf.py` (lines 83-90) -- Request size limits. `aws/cloudformation.yaml` (lines 261-296) -- WAF input validation rules. |
| **Testing Procedure** | 1. Submit malformed email and verify rejection. 2. Submit SQL injection payload and verify WAF blocks it. 3. Verify oversized request headers are rejected by Gunicorn. 4. Confirm null bytes are stripped from inputs. |
| **Status** | **Implemented** |

### PI1.3 - System Output Integrity

| Field | Value |
|---|---|
| **Control ID** | PI1.3 |
| **Control Description** | System outputs are secured through Content Security Policy preventing XSS, error sanitization preventing information leakage, and comprehensive security headers. |
| **Implementation Evidence** | CSP blocks inline scripts (`script-src 'self'` only, no `unsafe-inline`). X-Content-Type-Options prevents MIME sniffing. X-Frame-Options DENY prevents clickjacking. Referrer-Policy prevents URL leakage. Cache-Control prevents caching of auth/QBO responses. Error responses use standardized format with sanitized messages. |
| **Key Files** | `QBMigrationServer/app.py` (lines 782-868) -- Security headers middleware with CSP (no unsafe-inline for scripts), HSTS, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy, Cache-Control for sensitive endpoints. `QBMigrationServer/utils/error_sanitizer.py` (lines 27-75) -- `APIError` standardized response format. |
| **Testing Procedure** | 1. Verify CSP header does not contain `unsafe-inline` for `script-src`. 2. Confirm X-Frame-Options is DENY. 3. Verify auth endpoint responses have `Cache-Control: no-store`. 4. Confirm error responses follow standardized format. |
| **Status** | **Implemented** |

### PI1.4 - Processing Error Handling

| Field | Value |
|---|---|
| **Control ID** | PI1.4 |
| **Control Description** | Comprehensive error handling at all levels with database session cleanup, graceful degradation, and structured error responses. |
| **Implementation Evidence** | Database session management with rollback on exception and `db.session.remove()` in teardown. Error handlers for all HTTP status codes (400, 401, 403, 404, 413, 429, 500) plus catch-all Exception handler. Migration retry logic with configurable `max_retries=3`. Gunicorn worker recycling after 1000 requests prevents memory leaks. |
| **Key Files** | `QBMigrationServer/app.py` (lines 1322-1460) -- Database session teardown, error handlers with sanitization. `QBMigrationServer/app.py` (lines 1434-1460) -- 500 and catch-all handlers with `db.session.rollback()` + `db.session.remove()`. `Dockerfile` (lines 92-96) -- Gunicorn with `--max-requests 1000 --max-requests-jitter 100`. |
| **Testing Procedure** | 1. Verify database session is cleaned up after exceptions. 2. Confirm 500 errors return sanitized message. 3. Verify catch-all handler logs full stack trace server-side. 4. Confirm Gunicorn worker recycling at max-requests. |
| **Status** | **Implemented** |

---

## Appendix A - File Reference Index

| File Path | SOC 2 Relevance |
|---|---|
| `QBMigrationServer/app.py` | Application factory, security middleware, error handlers, CORS, CSRF, HTTPS redirect, health checks |
| `QBMigrationServer/models/user.py` | Argon2id auth, RBAC, MFA, account lockout, password policy, device fingerprinting |
| `QBMigrationServer/utils/pii_redaction.py` | SHA-256 PII hashing, email/IP/phone/SSN/CC redaction |
| `QBMigrationServer/utils/audit_logger.py` | SOC 2 audit logging, 50+ event types, 7-year retention |
| `QBMigrationServer/utils/error_sanitizer.py` | Error sanitization, 40+ regex patterns, QBO error whitelist |
| `QBMigrationServer/utils/anomaly_detector.py` | Login, upload, and migration anomaly detection |
| `QBMigrationServer/utils/encryption.py` | RSA-4096 key management, OAEP+SHA-256 |
| `QBMigrationServer/utils/backup.py` | Encrypted backups, SHA-256 verification, S3 upload |
| `QBMigrationServer/utils/data_retention_cleanup.py` | Zero-persistence data cleanup, S3 temp file deletion |
| `QBMigrationServer/utils/secrets_manager.py` | AWS Secrets Manager integration, TTL cache |
| `QBMigrationServer/utils/validators.py` | Email RFC 5322, password PCI DSS v4.0.1, string sanitization |
| `QBMigrationServer/utils/metrics.py` | Prometheus metrics, request tracking, DB pool monitoring |
| `QBMigrationServer/extensions.py` | Three-tier rate limiting, fail-closed behavior |
| `QBMigrationServer/config.py` | Security configuration, key validation |
| `QBMigrationServer/gunicorn.conf.py` | Production WSGI configuration |
| `QBMigrationServer/api/auth.py` | JWT auth, session binding, login/register endpoints |
| `QBMigrationServer/api/legal.py` | EULA, Privacy Policy, DPA, Cookie Policy, Security Practices |
| `QBMigrationServer/api/security_txt.py` | RFC 9116 vulnerability disclosure |
| `QBMigrationServer/api/webhooks.py` | HMAC signature verification, replay prevention |
| `aws/cloudformation.yaml` | VPC, WAF, KMS, S3, RDS, ElastiCache, ALB, CloudTrail, Auto Scaling |
| `Dockerfile` | Multi-stage build, non-root user, health check |
| `docker-compose.yml` | Service orchestration, health checks, network isolation |
| `.github/workflows/python-ci.yml` | CI/CD: lint, security scan, tests, type check, SBOM |

---

## Appendix B - Control Summary Matrix

| Control ID | Category | Description | Status |
|---|---|---|---|
| CC1.1 | Control Environment | Legal documents and disclosure policy | Implemented |
| CC1.2 | Control Environment | CI/CD security governance | Implemented |
| CC1.3 | Control Environment | RBAC role hierarchy | Implemented |
| CC1.4 | Control Environment | Code quality enforcement | Implemented |
| CC1.5 | Control Environment | Audit logging with 7-year retention | Implemented |
| CC2.1 | Communication | Three-tier logging architecture | Implemented |
| CC2.2 | Communication | CloudWatch alarms and SNS notifications | Implemented |
| CC2.3 | Communication | External security documentation | Implemented |
| CC3.1 | Risk Assessment | Anomaly detection system | Implemented |
| CC3.2 | Risk Assessment | Session fraud prevention | Implemented |
| CC3.3 | Risk Assessment | Infrastructure as Code | Implemented |
| CC4.1 | Monitoring | Prometheus metrics | Implemented |
| CC4.2 | Monitoring | Health check diagnostics | Implemented |
| CC4.3 | Monitoring | CloudTrail and VPC Flow Logs | Implemented |
| CC5.1 | Control Activities | Defense-in-depth security layers | Implemented |
| CC5.2 | Control Activities | Automated security scanning | Implemented |
| CC5.3 | Control Activities | Containerized deployment | Implemented |
| CC6.1 | Access Controls | Argon2id + JWT authentication | Implemented |
| CC6.2 | Access Controls | TOTP MFA with encrypted storage | Implemented |
| CC6.3 | Access Controls | Account lockout + rate limiting | Implemented |
| CC6.4 | Access Controls | PCI DSS v4.0.1 password policy | Implemented |
| CC6.5 | Access Controls | VPC network segmentation | Implemented |
| CC6.6 | Access Controls | AWS Secrets Manager | Implemented |
| CC6.7 | Access Controls | IAM least-privilege policies | Implemented |
| CC6.8 | Access Controls | Input validation and WAF rules | Implemented |
| CC7.1 | System Operations | Security event detection | Implemented |
| CC7.2 | System Operations | Incident response automation | Implemented |
| CC7.3 | System Operations | Backup and recovery | Implemented |
| CC8.1 | Change Management | CI/CD pipeline validation | Implemented |
| CC8.2 | Change Management | Automated test suite (1,981 tests) | Implemented |
| CC8.3 | Change Management | Configuration validation | Implemented |
| CC9.1 | Risk Mitigation | Sub-processor documentation | Implemented |
| CC9.2 | Risk Mitigation | Supply chain monitoring (SBOM) | Implemented |
| A1.1 | Availability | Multi-AZ + Auto Scaling | Implemented |
| A1.2 | Availability | AWS certified data centers | Implemented |
| A1.3 | Availability | Encrypted backup and recovery | Implemented |
| C1.1 | Confidentiality | PII identification and hashing | Implemented |
| C1.2 | Confidentiality | Encryption at rest (KMS + Fernet) | Implemented |
| C1.3 | Confidentiality | Encryption in transit (TLS 1.3) | Implemented |
| C1.4 | Confidentiality | Automated data disposal | Implemented |
| C1.5 | Confidentiality | Error sanitization | Implemented |
| PI1.1 | Processing Integrity | File hash and webhook verification | Implemented |
| PI1.2 | Processing Integrity | Multi-layer input validation | Implemented |
| PI1.3 | Processing Integrity | Output security (CSP, headers) | Implemented |
| PI1.4 | Processing Integrity | Error handling and session cleanup | Implemented |

---

*This document is maintained by the ForensicBridge Security Team and is updated as controls are modified or new controls are implemented. All control implementations reference specific file paths and line numbers in the codebase for auditor verification.*
