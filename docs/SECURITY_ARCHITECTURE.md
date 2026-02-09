# ForensicBridge Security Architecture

**Document Version:** 2.0
**Last Updated:** 2026-02-09
**Classification:** Confidential -- Acquisition Due Diligence
**Prepared For:** $10M Acquisition Technical Review
**Platform:** ForensicBridge -- QuickBooks Desktop to QuickBooks Online Migration SaaS

---

## Table of Contents

1. [Security Architecture Overview](#1-security-architecture-overview)
2. [Data Flow and Encryption at Each Stage](#2-data-flow-and-encryption-at-each-stage)
3. [Authentication and Authorization Model](#3-authentication-and-authorization-model)
4. [Encryption Key Hierarchy](#4-encryption-key-hierarchy)
5. [Network Security](#5-network-security)
6. [Logging and Monitoring Architecture](#6-logging-and-monitoring-architecture)
7. [Incident Response Workflow](#7-incident-response-workflow)

---

## 1. Security Architecture Overview

### 1.1 System Architecture with Security Boundaries

```
                            INTERNET
                               |
                     +---------+---------+
                     |   AWS WAF (Edge)  |
                     | - Rate Limiting   |
                     | - SQLi Protection |
                     | - Bad Input Block |
                     +---------+---------+
                               |
                +--------------+--------------+
                |     AWS CloudFront / ALB     |
                |  TLS 1.3 Termination         |
                |  (ELBSecurityPolicy-TLS13)   |
                |  ACM Certificate             |
                +--------------+--------------+
                               |
        =======================|========================
        |              VPC 10.0.0.0/16                 |
        |                                              |
        |   +--- Public Subnets (10.0.1.0/24, .2.0) --|
        |   |                                          |
        |   |   +----------------------------------+   |
        |   |   |  Application Load Balancer (ALB) |   |
        |   |   |  - HTTPS :443 (from Internet)    |   |
        |   |   |  - HTTP :80 -> 301 HTTPS         |   |
        |   |   |  - Health: /api/health :30s       |   |
        |   |   +----------------+-----------------+   |
        |   |                    |                     |
        |   |   +--- NAT Gateway (outbound only) --+   |
        |   |                    |                     |
        |   +--- Private Subnets (10.0.3.0/24, .4.0) -|
        |       |                |                     |
        |   +---+----+  +-------+------+               |
        |   |  ASG   |  |   ASG        |               |
        |   | EC2 #1 |  |  EC2 #2      |               |
        |   |--------|  |--------------|               |
        |   | Docker |  | Docker       |               |
        |   | +----+ |  | +----+       |               |
        |   | |Guni| |  | |Guni|       |               |
        |   | |corn| |  | |corn|       |               |
        |   | |Flask| |  | |Flask|     |               |
        |   | +----+ |  | +----+       |               |
        |   +---+----+  +------+-------+               |
        |       |              |                        |
        |       +---------+----+                        |
        |                 |                             |
        |   +-------------+----+    +---------------+  |
        |   | RDS PostgreSQL   |    | ElastiCache   |  |
        |   | (Multi-AZ)       |    | Redis         |  |
        |   |------------------|    |---------------|  |
        |   | Port: 5432       |    | Port: 6379    |  |
        |   | Encrypted: AES256|    | TLS: Enabled  |  |
        |   | Backup: 7 days   |    | Auth: Token   |  |
        |   +------------------+    +---------------+  |
        |                                              |
        ================================================
                               |
                    +----------+-----------+
                    |     S3 Bucket        |
                    | - KMS SSE (CMK)      |
                    | - Versioning: On     |
                    | - Public: Blocked    |
                    | - Glacier: 30 days   |
                    +----------+-----------+
                               |
                    +----------+-----------+
                    | AWS KMS              |
                    | - CMK Auto-Rotate    |
                    | - Key Policy: EC2    |
                    +----------------------+
```

**File References:**
- `aws/cloudformation.yaml` (lines 39-172) -- VPC, subnets, IGW, NAT Gateway
- `aws/cloudformation.yaml` (lines 176-244) -- Security groups
- `aws/cloudformation.yaml` (lines 246-342) -- WAF configuration
- `aws/cloudformation.yaml` (lines 454-483) -- RDS PostgreSQL
- `aws/cloudformation.yaml` (lines 508-525) -- ElastiCache Redis
- `aws/cloudformation.yaml` (lines 383-419) -- S3 with KMS encryption
- `aws/cloudformation.yaml` (lines 661-723) -- ALB with TLS 1.3

### 1.2 Security Boundary Summary

| Boundary | Protection | Implementation |
|---|---|---|
| Internet -> WAF | DDoS, SQLi, bad inputs, rate limiting | AWS WAF Managed Rules + Custom Rate Rules |
| WAF -> ALB | TLS 1.3 termination | ACM Certificate, ELBSecurityPolicy-TLS13-1-2-2021-06 |
| ALB -> EC2 | Security group ingress (port 5000 from ALB SG only) | VPC Security Groups |
| EC2 -> RDS | Security group ingress (port 5432 from EC2 SG only) | VPC Security Groups, SSL |
| EC2 -> Redis | Security group ingress (port 6379 from EC2 SG only) | VPC Security Groups, TLS + Auth Token |
| EC2 -> S3 | IAM role, bucket policy | Scoped IAM policies, KMS ViaService condition |
| EC2 -> KMS | IAM role with ViaService condition | KMS key policy + IAM policy |
| Public -> Private subnet | NAT Gateway (outbound only) | No inbound routes to private subnets |

---

## 2. Data Flow and Encryption at Each Stage

### 2.1 Migration Data Flow

```
+------------------+     +---------------------+     +------------------+
| QuickBooks       |     | ForensicBridge      |     | QuickBooks       |
| Desktop          |     | Server              |     | Online           |
| (On-Premise)     |     | (AWS)               |     | (Intuit Cloud)   |
+--------+---------+     +---------+-----------+     +--------+---------+
         |                         |                           |
   [1] Extract Data          [4] Process &              [7] API Upload
         |                    Validate                        |
   [2] RSA-4096              [5] Store                  [8] OAuth 2.0
    Encrypt Payload           Encrypted                  + TLS 1.3
         |                         |                           |
   [3] HTTPS POST            [6] S3 Upload              [9] Verify
    (TLS 1.3)                 (KMS SSE)                  Migration
         |                         |                           |
         v                         v                           v

ENCRYPTION AT EACH STAGE:

[1] Client-Side:    QBDesktopReader extracts data
[2] Hybrid Encrypt: RSA-4096 (OAEP+SHA-256) wraps AES session key
                    AES-256-GCM encrypts payload
[3] In Transit:     TLS 1.3 via ALB (ELBSecurityPolicy-TLS13)
[4] Server-Side:    RSA-4096 private key decrypts session key
                    AES-256-GCM decrypts payload
[5] At Rest (DB):   RDS StorageEncrypted: true (AES-256)
                    QBO tokens: Fernet (AES-128-CBC + HMAC-SHA256)
                    MFA secrets: Fernet encrypted
[6] At Rest (S3):   KMS CMK with automatic rotation
                    BucketKeyEnabled: true
                    SSEAlgorithm: aws:kms
[7] In Transit:     TLS 1.3 to Intuit API
[8] Auth:           OAuth 2.0 with encrypted refresh tokens
[9] Verification:   SHA-256 file hash comparison
```

**File References:**
- `QBMigrationServer/utils/encryption.py` (lines 22-188) -- RSA-4096 EncryptionManager
- `QBMigrationServer/models/user.py` (lines 126-212) -- QBO token Fernet encryption
- `aws/cloudformation.yaml` (lines 346-378) -- KMS CMK configuration
- `aws/cloudformation.yaml` (lines 387-393) -- S3 KMS encryption

### 2.2 Data Classification and Handling

```
+------------------------+---------------------------+---------------------------+
| Classification         | Data Types                | Handling Rules            |
+========================+===========================+===========================+
| RESTRICTED             | - QBO OAuth tokens        | - Fernet encrypted at     |
| (Highest Sensitivity)  | - MFA secrets             |   rest                    |
|                        | - RSA private keys        | - Never in logs           |
|                        | - Database credentials    | - Secrets Manager only    |
|                        |                           | - 0600 file permissions   |
+------------------------+---------------------------+---------------------------+
| CONFIDENTIAL           | - Financial data          | - AES-256 / KMS at rest   |
|                        | - Customer PII            | - TLS 1.3 in transit      |
|                        | - Vendor information      | - 24h zero-persistence    |
|                        | - Trial balance data      | - SHA-256 hash in logs    |
+------------------------+---------------------------+---------------------------+
| INTERNAL               | - Migration metadata      | - Database encryption     |
|                        | - User account info       | - Access logging          |
|                        | - Audit event details     | - RBAC access control     |
|                        | - System configuration    |                           |
+------------------------+---------------------------+---------------------------+
| PUBLIC                 | - Legal documents         | - Standard caching        |
|                        | - Security.txt            | - No access restrictions  |
|                        | - Health check status     |                           |
+------------------------+---------------------------+---------------------------+
```

**File References:**
- `QBMigrationServer/utils/audit_logger.py` (lines 191-194) -- `data_classification` field
- `QBMigrationServer/utils/data_retention_cleanup.py` (lines 29-135) -- Zero-persistence cleanup
- `QBMigrationServer/utils/pii_redaction.py` (lines 1-281) -- PII hashing for logs

---

## 3. Authentication and Authorization Model

### 3.1 Authentication Flow

```
                     +------------------+
                     |  User / Client   |
                     +--------+---------+
                              |
                  +-----------+-----------+
                  |                       |
           [Browser Session]      [API Client]
                  |                       |
           +------v------+        +------v------+
           | POST /login |        | POST /login |
           | email + pwd |        | email + pwd |
           +------+------+        +------+------+
                  |                       |
         +--------v---------+    +--------v---------+
         | 1. Rate Limit    |    | 1. Rate Limit    |
         |    Check         |    |    Check         |
         | (IP: 5/min)      |    | (IP: 5/min)      |
         +--------+---------+    +--------+---------+
                  |                       |
         +--------v---------+    +--------v---------+
         | 2. Account Lock  |    | 2. Account Lock  |
         |    Check         |    |    Check         |
         | (5 fails=15min)  |    | (5 fails=15min)  |
         +--------+---------+    +--------+---------+
                  |                       |
         +--------v---------+    +--------v---------+
         | 3. Argon2id      |    | 3. Argon2id      |
         |    Verify        |    |    Verify        |
         | (64MB, t=3, p=4) |    | (64MB, t=3, p=4) |
         +--------+---------+    +--------+---------+
                  |                       |
         +--------v---------+    +--------v---------+
         | 4. Anomaly       |    | 4. Anomaly       |
         |    Detection     |    |    Detection     |
         | (time, travel,   |    | (time, travel,   |
         |  IP, frequency)  |    |  IP, frequency)  |
         +--------+---------+    +--------+---------+
                  |                       |
             +----v----+             +----v----+
             | MFA     |             | MFA     |
             |Enabled? |             |Enabled? |
             +----+----+             +----+----+
              Y   |   N               Y   |   N
              |   |   |               |   |   |
         +----v-+ | +-v---+      +---v--+ | +-v---+
         |TOTP  | | |Skip | --> |TOTP  | | |Skip |
         |Verify| | |     |     |Verify| | |     |
         +--+---+ | +--+--+     +--+---+ | +--+--+
            |     |    |            |     |    |
            +--+--+----+            +--+--+----+
               |                       |
         +-----v------+        +------v-------+
         | 5. Create  |        | 5. Create    |
         | Flask       |        |    JWT       |
         | Session     |        |    Token     |
         | + UA Bind   |        | (HS256)      |
         +-----+------+        +------+-------+
               |                       |
         +-----v------+        +------v-------+
         | Set Cookie: |        | Return:      |
         | session_id  |        | auth_token   |
         | (HttpOnly,  |        | (Bearer hdr) |
         |  Secure,    |        |              |
         |  SameSite)  |        |              |
         +-------------+        +--------------+
```

**File References:**
- `QBMigrationServer/api/auth.py` (lines 1-50) -- Auth blueprint, session binding
- `QBMigrationServer/models/user.py` (lines 298-352) -- Argon2id password verification
- `QBMigrationServer/models/user.py` (lines 524-576) -- Account lockout (5 fails, 15 min)
- `QBMigrationServer/models/user.py` (lines 729-790) -- TOTP MFA verification
- `QBMigrationServer/utils/anomaly_detector.py` (lines 317-378) -- Login anomaly checks
- `QBMigrationServer/app.py` (lines 889-932) -- Flask-Login request_loader (JWT + cookie)

### 3.2 Authorization Model (RBAC)

```
+-------------------------------------------------------------------+
|                    Role Hierarchy (Ascending)                      |
+===================================================================+
|                                                                   |
|  Level 0: user          Level 1: support                          |
|  +----------------+     +--------------------+                    |
|  | - Own migrations|     | - All of 'user'    |                   |
|  | - Own profile   |     | - Admin dashboard  |                   |
|  | - Upload files  |     |   (read-only)      |                   |
|  | - View status   |     | - View all         |                   |
|  +----------------+     |   migrations       |                    |
|                         +--------------------+                    |
|                                                                   |
|  Level 2: admin         Level 3: super_admin                      |
|  +----------------+     +--------------------+                    |
|  | - All of        |     | - All of 'admin'   |                   |
|  |   'support'    |     | - System config    |                    |
|  | - Manage users  |     | - Role assignment  |                   |
|  | - View audit    |     | - Data export      |                   |
|  |   logs         |     | - Backup/restore   |                    |
|  +----------------+     +--------------------+                    |
|                                                                   |
+-------------------------------------------------------------------+

Permission Check Methods:
  has_role(role)            -> Exact role match
  has_role_or_higher(role)  -> Role level >= target level
  is_admin()               -> Role is 'admin' or 'super_admin'
  can_manage_users()       -> is_admin()
  can_view_all_migrations()-> Role is 'support' or higher
  can_access_admin_dashboard() -> Role is 'support' or higher
```

**File References:**
- `QBMigrationServer/models/user.py` (lines 237-290) -- RBAC implementation with ROLE_HIERARCHY

### 3.3 Session Security Controls

| Control | Implementation | File Reference |
|---|---|---|
| Session binding | SHA-256 User-Agent fingerprint | `api/auth.py` lines 38-52 |
| CSRF protection | Flask-WTF with token validation | `app.py` lines 736-773 |
| Cookie security | HttpOnly, Secure, SameSite=Lax | `app.py` lines 870-887 |
| Session timeout | Configurable expiry (default: 24h) | `config.py` |
| JWT validation | HS256 with 64+ char secret | `app.py` lines 889-932 |
| Credential hashing | Argon2id (64MB, t=3, p=4, 32B hash, 16B salt) | `models/user.py` lines 21-27 |

---

## 4. Encryption Key Hierarchy

### 4.1 Key Hierarchy Diagram

```
+=====================================================+
|                 AWS KMS (Root of Trust)              |
|   CMK: ForensicBridgeMigrationKey                   |
|   - Auto-rotation: Enabled (annual)                 |
|   - Key Policy: EC2 role only                       |
|   - Condition: kms:ViaService = s3.*.amazonaws.com  |
+==========================+=========================+
                           |
              +------------+------------+
              |                         |
    +---------v----------+   +----------v---------+
    | S3 Bucket Keys     |   | EBS Volume Keys    |
    | (BucketKeyEnabled) |   | (AWS Managed)      |
    | - Derived from CMK |   | - AES-256          |
    | - Per-object DEK   |   | - Per-volume       |
    +--------------------+   +--------------------+

+=====================================================+
|          Application Encryption Keys                 |
+=====================================================+
|                                                     |
|  +---------------------------------------------+   |
|  | RSA-4096 Key Pair                            |   |
|  | (QBDesktopReader <-> Server)                 |   |
|  |--------------------------------------------- |   |
|  | Public Key:  Distributed to desktop clients  |   |
|  | Private Key: Encrypted with passphrase       |   |
|  |   - Password from: RSA_KEY_PASSWORD env var  |   |
|  |   - or: AWS Secrets Manager                  |   |
|  |   - File permissions: 0600 (owner only)      |   |
|  |   - Atomic file creation (O_CREAT|O_EXCL)    |   |
|  |   - OAEP padding with SHA-256                |   |
|  +---------------------------------------------+   |
|                                                     |
|  +---------------------------------------------+   |
|  | Fernet Keys (AES-128-CBC + HMAC-SHA256)      |   |
|  |--------------------------------------------- |   |
|  | 1. QBO Token Encryption Key                  |   |
|  |    - Source: QBO_ENCRYPTION_KEY env var       |   |
|  |    - Required in production                  |   |
|  |    - Encrypts: OAuth access/refresh tokens   |   |
|  |                                              |   |
|  | 2. MFA Secret Encryption Key                 |   |
|  |    - Source: MFA_ENCRYPTION_KEY env var       |   |
|  |    - Encrypts: TOTP shared secrets           |   |
|  |    - Legacy plaintext blocked in production  |   |
|  |                                              |   |
|  | 3. Backup Encryption Key                     |   |
|  |    - Source: BACKUP_ENCRYPTION_KEY env var    |   |
|  |    - Validated at startup (encrypt+decrypt)  |   |
|  |    - Encrypts: Database backup files         |   |
|  +---------------------------------------------+   |
|                                                     |
|  +---------------------------------------------+   |
|  | AWS Secrets Manager                          |   |
|  | (forensicbridge/production)                  |   |
|  |--------------------------------------------- |   |
|  | Stores all application secrets:              |   |
|  |   flask_secret_key     (JWT signing)         |   |
|  |   database_url         (PostgreSQL conn)     |   |
|  |   aws_access_key_id    (S3/KMS access)       |   |
|  |   qbo_client_secret    (OAuth 2.0)           |   |
|  |   webhook_secret       (HMAC signing)        |   |
|  |   backup_encryption_key (Fernet)             |   |
|  |   encryption_password  (RSA key passphrase)  |   |
|  | Cache TTL: 300 seconds (thread-safe)         |   |
|  +---------------------------------------------+   |
|                                                     |
+=====================================================+

Key Rotation:
  KMS CMK:        Automatic annual rotation
  Fernet Keys:    Manual rotation via Secrets Manager
  RSA Key Pair:   Manual rotation (re-encrypt at rest)
  JWT Secret:     Manual rotation (invalidates sessions)
  Webhook Secret: Manual rotation (coordinate with clients)
```

**File References:**
- `aws/cloudformation.yaml` (lines 346-378) -- KMS CMK with EnableKeyRotation
- `QBMigrationServer/utils/encryption.py` (lines 22-188) -- RSA-4096 EncryptionManager
- `QBMigrationServer/models/user.py` (lines 126-212) -- Fernet QBO token encryption
- `QBMigrationServer/models/user.py` (lines 599-668) -- Fernet MFA secret encryption
- `QBMigrationServer/utils/backup.py` (lines 243-284) -- Fernet backup encryption
- `QBMigrationServer/utils/secrets_manager.py` (lines 1-343) -- Secrets Manager with TTL cache

### 4.2 Encryption Algorithm Summary

| Use Case | Algorithm | Key Size | Mode | File |
|---|---|---|---|---|
| S3 objects at rest | AES-256 | 256-bit | KMS envelope | `aws/cloudformation.yaml` |
| EBS volumes | AES-256 | 256-bit | AWS managed | `aws/cloudformation.yaml` |
| RDS storage | AES-256 | 256-bit | AWS managed | `aws/cloudformation.yaml` |
| Client -> Server payload | RSA-4096 | 4096-bit | OAEP+SHA-256 | `utils/encryption.py` |
| QBO tokens in DB | Fernet | 128-bit | AES-CBC+HMAC | `models/user.py` |
| MFA secrets in DB | Fernet | 128-bit | AES-CBC+HMAC | `models/user.py` |
| Backup files | Fernet | 128-bit | AES-CBC+HMAC | `utils/backup.py` |
| JWT signing | HMAC | 256-bit+ | SHA-256 | `api/auth.py` |
| Webhook verification | HMAC | 256-bit | SHA-256 | `api/webhooks.py` |
| Password hashing | Argon2id | N/A | 64MB/t=3/p=4 | `models/user.py` |
| PII log hashing | SHA-256 | 256-bit | Truncated output | `utils/pii_redaction.py` |
| Data in transit | TLS 1.3 | 256-bit | AEAD | ALB configuration |
| Redis in transit | TLS | varies | Redis AUTH | `aws/cloudformation.yaml` |

---

## 5. Network Security

### 5.1 VPC Architecture

```
+================================================================+
|                    VPC: 10.0.0.0/16                            |
|                                                                |
|  +--- AZ-1 ----------------------------+                      |
|  |                                      |                      |
|  |  Public Subnet: 10.0.1.0/24         |                      |
|  |  +------+  +-----------+            |                      |
|  |  | IGW  |  | NAT GW    |            |                      |
|  |  +------+  +-----------+            |                      |
|  |                                      |                      |
|  |  Private Subnet: 10.0.3.0/24        |                      |
|  |  +--------+  +-------+  +--------+  |                      |
|  |  | EC2 #1 |  | RDS   |  | Redis  |  |                      |
|  |  | (ASG)  |  |(Prim) |  |(Node)  |  |                      |
|  |  +--------+  +-------+  +--------+  |                      |
|  +--------------------------------------+                      |
|                                                                |
|  +--- AZ-2 ----------------------------+                      |
|  |                                      |                      |
|  |  Public Subnet: 10.0.2.0/24         |                      |
|  |  +------+                            |                      |
|  |  | ALB  |                            |                      |
|  |  +------+                            |                      |
|  |                                      |                      |
|  |  Private Subnet: 10.0.4.0/24        |                      |
|  |  +--------+  +-------+              |                      |
|  |  | EC2 #2 |  | RDS   |              |                      |
|  |  | (ASG)  |  |(Stdby)|              |                      |
|  |  +--------+  +-------+              |                      |
|  +--------------------------------------+                      |
|                                                                |
+================================================================+
```

### 5.2 Security Group Rules

```
+---------------------------+-------+--------+------------------+
| Security Group            | Port  | Proto  | Source           |
+===========================+=======+========+==================+
| ALBSecurityGroup          | 443   | TCP    | 0.0.0.0/0       |
|                           | 80    | TCP    | 0.0.0.0/0       |
+---------------------------+-------+--------+------------------+
| EC2SecurityGroup          | 5000  | TCP    | ALBSecurityGroup |
|                           | 22    | TCP    | VPN CIDR (param) |
+---------------------------+-------+--------+------------------+
| RDSSecurityGroup          | 5432  | TCP    | EC2SecurityGroup |
+---------------------------+-------+--------+------------------+
| RedisSecurityGroup        | 6379  | TCP    | EC2SecurityGroup |
+---------------------------+-------+--------+------------------+

OUTBOUND: All security groups allow all outbound traffic (0.0.0.0/0)
           Private subnets route outbound through NAT Gateway
```

**File References:**
- `aws/cloudformation.yaml` (lines 176-244) -- All security group definitions

### 5.3 WAF Rules Configuration

```
+==========================================+============+===========+
| WAF Rule                                 | Action     | Priority  |
+==========================================+============+===========+
| AWSManagedRulesCommonRuleSet             | Block      | 1         |
|   - XSS, path traversal, etc.           |            |           |
+------------------------------------------+------------+-----------+
| AWSManagedRulesSQLiRuleSet               | Block      | 2         |
|   - SQL injection patterns               |            |           |
+------------------------------------------+------------+-----------+
| AWSManagedRulesKnownBadInputsRuleSet     | Block      | 3         |
|   - Log4j, SSRF, etc.                   |            |           |
+------------------------------------------+------------+-----------+
| RateLimitRule (Global)                   | Block      | 4         |
|   - 500 requests per 5 minutes          |            |           |
+------------------------------------------+------------+-----------+
| AuthRateLimitRule                        | Block      | 5         |
|   - /api/auth/* endpoints               |            |           |
|   - 100 requests per 5 minutes          |            |           |
+------------------------------------------+------------+-----------+

+ Application-Level Rate Limiting:
  - Default: 1000/day, 100/hour (per IP+user)
  - Auth endpoints: 5/minute per IP (ip_limiter)
  - Fail-closed when Redis unavailable (production)
```

**File References:**
- `aws/cloudformation.yaml` (lines 246-342) -- WAF WebACL with all rules
- `QBMigrationServer/extensions.py` (lines 148-176) -- Application rate limiters

### 5.4 Network Data Flow Restrictions

| Flow | Allowed | Blocked | Enforcement |
|---|---|---|---|
| Internet -> ALB | HTTPS (443), HTTP (80 -> 301 redirect) | All other ports | ALB Security Group |
| ALB -> EC2 | Port 5000 (HTTP) | All other ports | EC2 Security Group source: ALB SG |
| EC2 -> RDS | Port 5432 (PostgreSQL) | All other ports | RDS Security Group source: EC2 SG |
| EC2 -> Redis | Port 6379 (Redis + TLS) | All other ports | Redis Security Group source: EC2 SG |
| EC2 -> S3 | HTTPS (VPC endpoint or NAT GW) | Unencrypted | IAM policy + bucket policy |
| EC2 -> Internet | Via NAT Gateway only | Direct | Private subnet route table |
| SSH -> EC2 | Port 22 from VPN CIDR only | All other sources | EC2 Security Group |

---

## 6. Logging and Monitoring Architecture

### 6.1 Logging Architecture

```
+=================================================================+
|                    Application Layer                            |
+=================================================================+
|                                                                 |
|  +------------------+  +------------------+  +---------------+  |
|  | Application Log  |  | Security Log     |  | Audit Log     |  |
|  | logs/app.log     |  | logs/security.log|  | logs/audit.log|  |
|  |------------------|  |------------------|  |---------------|  |
|  | Level: INFO+     |  | Level: WARNING+  |  | Format: JSON  |  |
|  | Rotate: 10MB     |  | Rotate: 10MB     |  | Rotate: 50MB  |  |
|  | Keep: 10 files   |  | Keep: 10 files   |  | Keep: 100     |  |
|  | PII: Redacted    |  | PII: Redacted    |  | PII: Hashed   |  |
|  +--------+---------+  +--------+---------+  +-------+-------+  |
|           |                      |                    |          |
+=================================================================+
|                                                                 |
|  +------------------+  +------------------+                     |
|  | Prometheus       |  | Sentry           |                     |
|  | /metrics         |  | (Error Tracking) |                     |
|  |------------------|  |------------------|                     |
|  | Request latency  |  | send_default_pii |                     |
|  | Error counts     |  |   = False        |                     |
|  | Auth attempts    |  | traces_sample    |                     |
|  | Rate limit hits  |  |   _rate = 0.1    |                     |
|  | DB pool stats    |  | profiles_sample  |                     |
|  | Migration counts |  |   _rate = 0.1    |                     |
|  +--------+---------+  +--------+---------+                     |
|           |                      |                              |
+=================================================================+
|                    Infrastructure Layer                         |
+=================================================================+
|                                                                 |
|  +------------------+  +------------------+  +---------------+  |
|  | CloudWatch Logs  |  | CloudTrail       |  | VPC Flow Logs |  |
|  |------------------|  |------------------|  |---------------|  |
|  | Gunicorn stdout  |  | Multi-region     |  | All traffic   |  |
|  | VPC Flow Logs    |  | Log validation   |  | Retention:    |  |
|  | ALB access logs  |  | S3 encrypted     |  |   365 days    |  |
|  +------------------+  | Lifecycle: 365d  |  +---------------+  |
|                        +------------------+                     |
|                                                                 |
|  +------------------------------------------------------------+ |
|  | CloudWatch Alarms (8 alarms -> SNS -> Email)               | |
|  |------------------------------------------------------------| |
|  | 1. HighCPU         (>80% for 5 min)                        | |
|  | 2. DatabaseConn    (>80 connections for 5 min)             | |
|  | 3. ALB5xxError     (>10 errors in 5 min)                   | |
|  | 4. DBFreeStorage   (<5GB for 5 min)                        | |
|  | 5. DatabaseCPU     (>80% for 10 min)                       | |
|  | 6. WAFBlocked      (>1000 blocked in 5 min)                | |
|  | 7. ResponseTime    (>2 seconds for 5 min)                  | |
|  | 8. UnhealthyHost   (>0 unhealthy for 1 min)                | |
|  +------------------------------------------------------------+ |
|                                                                 |
+=================================================================+
```

**File References:**
- `QBMigrationServer/app.py` (lines 59-131) -- `setup_logging()` with rotating handlers
- `QBMigrationServer/app.py` (lines 134-157) -- `setup_sentry()` with PII disabled
- `QBMigrationServer/utils/audit_logger.py` (lines 218-244) -- Audit logger configuration
- `QBMigrationServer/utils/metrics.py` (lines 1-395) -- Prometheus metrics
- `aws/cloudformation.yaml` (lines 728-901) -- CloudWatch alarms
- `aws/cloudformation.yaml` (lines 907-968) -- VPC Flow Logs and CloudTrail

### 6.2 Audit Event Types

The audit logger tracks 50+ event types organized into categories:

| Category | Event Types | Severity |
|---|---|---|
| Authentication | `LOGIN_SUCCESS`, `LOGIN_FAILURE`, `LOGOUT`, `MFA_ENABLED`, `MFA_DISABLED`, `MFA_VERIFIED`, `PASSWORD_CHANGED`, `PASSWORD_RESET` | INFO - WARNING |
| Authorization | `ACCESS_GRANTED`, `ACCESS_DENIED`, `ROLE_CHANGED`, `PERMISSION_CHECK` | INFO - WARNING |
| Data Access | `DATA_READ`, `DATA_WRITE`, `DATA_DELETE`, `DATA_EXPORT`, `DATA_IMPORT` | INFO |
| Migration | `MIGRATION_STARTED`, `MIGRATION_COMPLETED`, `MIGRATION_FAILED`, `FILE_UPLOADED`, `FILE_DOWNLOADED` | INFO - ERROR |
| Security | `ANOMALY_DETECTED`, `RATE_LIMIT_HIT`, `ACCOUNT_LOCKED`, `SUSPICIOUS_ACTIVITY`, `BRUTE_FORCE_DETECTED` | WARNING - CRITICAL |
| Configuration | `CONFIG_CHANGED`, `USER_CREATED`, `USER_DELETED`, `BACKUP_CREATED`, `BACKUP_RESTORED` | INFO - WARNING |
| System | `SYSTEM_STARTUP`, `SYSTEM_SHUTDOWN`, `HEALTH_CHECK_FAILED`, `ERROR_OCCURRED` | INFO - CRITICAL |

**File Reference:** `QBMigrationServer/utils/audit_logger.py` (lines 30-130) -- AuditEventType enum

### 6.3 PII Handling in Logs

```
BEFORE REDACTION:                    AFTER REDACTION:
+---------------------------------+  +-----------------------------------------+
| "User john@example.com logged   |  | "User usr_a8f5f167f4... logged          |
|  in from 192.168.1.100 with     |  |  in from ip_c0a8_0164... with           |
|  phone 555-123-4567"            |  |  phone XXX-XXX-4567"                    |
+---------------------------------+  +-----------------------------------------+

Functions:
  hash_email("john@example.com")  -> "usr_a8f5f167f44f..."  (SHA-256, 128-bit)
  hash_ip("192.168.1.100")       -> "ip_c0a8_0164..."      (SHA-256, 64-bit)
  redact_phone("555-123-4567")    -> "XXX-XXX-4567"         (last 4 preserved)
  redact_ssn("123-45-6789")       -> "XXX-XX-6789"          (last 4 preserved)
  redact_credit_card("4111...")    -> "XXXX-XXXX-XXXX-1234" (last 4 preserved)
```

**File Reference:** `QBMigrationServer/utils/pii_redaction.py` (lines 1-281)

---

## 7. Incident Response Workflow

### 7.1 Detection and Response Flow

```
+==================================================================+
|                 INCIDENT DETECTION SOURCES                       |
+==================================================================+
|                                                                  |
|  +---------------+  +--------------+  +---------------------+   |
|  | WAF Blocked   |  | Anomaly      |  | CloudWatch Alarms   |   |
|  | Requests      |  | Detector     |  | (8 alarm types)     |   |
|  | (>1000/5min)  |  | (4 checks)   |  |                     |   |
|  +-------+-------+  +------+-------+  +----------+----------+   |
|          |                 |                      |              |
|  +-------v-----------------v----------------------v----------+   |
|  |                   SNS Notification                        |   |
|  |               (Email to Operations)                       |   |
|  +-----------------------------+-----------------------------+   |
|                                |                                 |
+================================|=================================+
                                 |
+================================v=================================+
|                    AUTOMATED RESPONSE                            |
+==================================================================+
|                                                                  |
|  [SEVERITY: CRITICAL]                                            |
|  +------------------------------------------------------------+ |
|  | Impossible Travel Detected                                  | |
|  |   -> logger.critical() with full anomaly details            | |
|  |   -> Account flagged for immediate review                   | |
|  |   -> Audit event: ANOMALY_DETECTED (critical)               | |
|  +------------------------------------------------------------+ |
|                                                                  |
|  [SEVERITY: HIGH]                                                |
|  +------------------------------------------------------------+ |
|  | Rapid Login Attempts (>10/hour)                             | |
|  |   -> Account locked (5 failures -> 15 min lockout)          | |
|  |   -> Audit event: ACCOUNT_LOCKED                            | |
|  |   -> Rate limit escalation                                  | |
|  +------------------------------------------------------------+ |
|  | Large File Upload (>2GB)                                    | |
|  |   -> Anomaly logged (high severity)                         | |
|  |   -> Daily volume check triggered                           | |
|  +------------------------------------------------------------+ |
|                                                                  |
|  [SEVERITY: MEDIUM]                                              |
|  +------------------------------------------------------------+ |
|  | Suspicious IP Range                                         | |
|  |   -> Anomaly logged (medium severity)                       | |
|  |   -> Enhanced monitoring activated                          | |
|  +------------------------------------------------------------+ |
|  | Rate Limit Storage Failure (Production)                     | |
|  |   -> FAIL-CLOSED: All requests return 503                   | |
|  |   -> logger.error() with CRITICAL prefix                    | |
|  +------------------------------------------------------------+ |
|                                                                  |
|  [SEVERITY: LOW]                                                 |
|  +------------------------------------------------------------+ |
|  | Unusual Login Time (outside 6 AM - 11 PM)                  | |
|  |   -> Anomaly logged (low severity)                          | |
|  |   -> Included in daily security report                      | |
|  +------------------------------------------------------------+ |
|                                                                  |
+==================================================================+
```

### 7.2 Incident Response Timeline

```
+============+==========================================+=================+
| Timeframe  | Action                                   | Responsible     |
+============+==========================================+=================+
| T+0        | Automated detection (anomaly/alarm)       | System          |
|            | Automated response (lockout/block/503)    |                 |
+------------+------------------------------------------+-----------------+
| T+0-5min   | SNS notification delivered                | System          |
|            | Audit log event written                   |                 |
|            | Sentry alert (if error)                   |                 |
+------------+------------------------------------------+-----------------+
| T+5-15min  | Operations team acknowledges alert        | On-Call          |
|            | Initial triage via CloudWatch dashboard   |                 |
|            | Review audit logs for context             |                 |
+------------+------------------------------------------+-----------------+
| T+15-60min | Impact assessment                         | Security Lead   |
|            | Determine scope and affected resources    |                 |
|            | Activate incident response if needed      |                 |
+------------+------------------------------------------+-----------------+
| T+1-4hr    | Containment actions                       | Engineering     |
|            | - WAF rule updates                        |                 |
|            | - Security group changes                  |                 |
|            | - Credential rotation (Secrets Manager)   |                 |
+------------+------------------------------------------+-----------------+
| T+4-24hr   | Root cause analysis                       | Engineering     |
|            | Review CloudTrail for unauthorized access |                 |
|            | Review VPC Flow Logs for data exfil       |                 |
+------------+------------------------------------------+-----------------+
| T+24-72hr  | Customer notification (if required)       | Legal + Comms   |
|            | Per Privacy Policy: 72-hour notification  |                 |
|            | Regulatory reporting if applicable        |                 |
+------------+------------------------------------------+-----------------+
| T+72hr+    | Post-incident review                      | Full Team       |
|            | Control improvements                      |                 |
|            | Documentation updates                     |                 |
+------------+------------------------------------------+-----------------+
```

### 7.3 Evidence Preservation

During any security incident, the following evidence sources are preserved:

| Evidence Source | Retention | Format | Location |
|---|---|---|---|
| Audit logs | 7 years (2,555 days) | Structured JSON | `logs/audit.log` (rotating, 100 files) |
| Application logs | 100MB (10x10MB) | Text | `logs/app.log` (rotating) |
| Security logs | 100MB (10x10MB) | Text (WARNING+) | `logs/security.log` (rotating) |
| CloudTrail | 365 days | JSON | S3 bucket (encrypted, validated) |
| VPC Flow Logs | 365 days | CloudWatch Logs | CloudWatch Log Group |
| WAF logs | Via CloudWatch | Metrics | CloudWatch |
| Database backups | 7 days (RDS auto) + custom retention | Encrypted dump | S3 + local |
| Sentry events | Per Sentry plan | Structured | Sentry cloud |
| Prometheus metrics | Per Prometheus retention | Time-series | Prometheus server |

**File References:**
- `QBMigrationServer/utils/audit_logger.py` (lines 191-194) -- `retention_days=2555`
- `QBMigrationServer/utils/audit_logger.py` (lines 218-244) -- 50MB rotation, 100 files
- `aws/cloudformation.yaml` (lines 907-945) -- VPC Flow Logs 365-day retention
- `aws/cloudformation.yaml` (lines 950-1003) -- CloudTrail 365-day lifecycle

### 7.4 Recovery Procedures

```
+==========================================+
| DATABASE RECOVERY                        |
+==========================================+
|                                          |
| Priority 1: RDS Multi-AZ Failover       |
|   - Automatic (< 2 minutes)             |
|   - No data loss                         |
|                                          |
| Priority 2: RDS Point-in-Time Restore   |
|   - 7-day window                         |
|   - 5-minute granularity                 |
|                                          |
| Priority 3: Application Backup Restore  |
|   - BackupManager.restore_backup()       |
|   - S3 encrypted backups                 |
|   - SHA-256 integrity verification       |
|                                          |
+==========================================+
| APPLICATION RECOVERY                     |
+==========================================+
|                                          |
| Auto Scaling Group Recovery:             |
|   - Minimum 2 instances (always on)      |
|   - Health check: /api/health (30s)      |
|   - Unhealthy -> terminate -> replace    |
|   - Max 4 instances for scaling          |
|                                          |
| Container Recovery:                      |
|   - Docker HEALTHCHECK (30s interval)    |
|   - Gunicorn worker recycling (1000 req) |
|   - Graceful worker restart (30s timeout)|
|                                          |
+==========================================+
| SECRET ROTATION                          |
+==========================================+
|                                          |
| 1. Update secret in Secrets Manager      |
| 2. Clear application cache:              |
|    secrets_manager.clear_cache()         |
| 3. Rolling restart of ASG instances      |
| 4. Verify new secret is active           |
|                                          |
+==========================================+
```

**File References:**
- `QBMigrationServer/utils/backup.py` (lines 612-677) -- `restore_backup()` with integrity checks
- `QBMigrationServer/utils/secrets_manager.py` (lines 245-252) -- `clear_cache()` for rotation
- `aws/cloudformation.yaml` (lines 1068-1091) -- ASG with health check recovery
- `Dockerfile` (lines 73-74) -- Docker HEALTHCHECK

---

## Document Control

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2025-01-01 | ForensicBridge Security Team | Initial document |
| 2.0 | 2026-02-09 | ForensicBridge Security Team | Comprehensive update for acquisition due diligence |

---

*This document is classified as Confidential and is intended for acquisition due diligence purposes. Distribution is restricted to authorized parties under NDA. All file references point to the ForensicBridge codebase and can be independently verified by auditors with repository access.*
