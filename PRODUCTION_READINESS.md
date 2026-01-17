# ForensicBridge Complete Production Setup Guide

**Everything you need to go live - Code, Cloud, APIs, and Configuration**

---

## 🎯 WHAT THE SERVICE LOOKS LIKE

### The Accountant Experience: Dead Simple

ForensicBridge is designed for **zero technical knowledge**. An accountant sees this:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   ╔═══════════════════════════════════════════════════════╗   │
│   ║                                                       ║   │
│   ║     🗂️  DRAG YOUR QUICKBOOKS FILE HERE              ║   │
│   ║                                                       ║   │
│   ║         Drop .QBW, .QBB, or .QBM file                ║   │
│   ║                                                       ║   │
│   ╚═══════════════════════════════════════════════════════╝   │
│                                                                 │
│   Or click to browse...                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**That's it.** One drag-and-drop. No command lines, no configuration, no technical steps.

---

### Step-by-Step User Flow

| Step | What Accountant Does | What Happens Behind the Scenes |
|------|---------------------|--------------------------------|
| **1** | Drags `.QBW` file onto window | File uploaded to secure S3 bucket in Montreal |
| **2** | Waits 2-5 minutes | QBDesktopReader extracts all entities with SHA-256 hashes |
| **3** | Sees progress bar: "Extracting Invoices... 847/1,234" | Real-time webhook updates to dashboard |
| **4** | Clicks "Download Audit Bundle" | Gets Caseware-ready CSVs with forensic hashes |
| **5** | Imports into Caseware | Direct import, no manual mapping needed |

---

### What They See on Screen

```
┌─────────────────────────────────────────────────────────────────┐
│  ForensicBridge                              [John Smith ▼]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📁 Recent Migrations                                          │
│  ────────────────────────────────────────────────────────────  │
│                                                                 │
│  ✅ ABC Corp (2024)           1,847 records    Completed       │
│     Extracted: Jan 15, 2026   Trial Balance: ✓ Balanced        │
│     [View Report] [Download Caseware Bundle] [Migrate to QBO]  │
│                                                                 │
│  ⏳ XYZ Ltd (2023)            Processing...    67% complete    │
│     ████████████████░░░░░░  Extracting Bills (423/631)         │
│                                                                 │
│  ❌ DEF Inc (2022)            Failed          Retry Available  │
│     Error: QuickBooks file is password protected               │
│     [Retry] [Contact Support]                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### Output Options (One Click Each)

| Button | What It Does |
|--------|--------------|
| **Download Caseware Bundle** | Generates `Audit_TB.csv`, `Audit_GL.csv`, `Audit_Mapping.cvw` with SHA-256 hashes |
| **Migrate to QBO** | Pushes all data to QuickBooks Online (requires OAuth) |
| **View Variance Report** | Shows any discrepancies during migration |
| **Download Raw JSON** | Full NDJSON export for developers |

---

### The Installer Experience

Accountants install via a single `.exe`:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   ForensicBridge Setup                                    [X]  │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                                                         │  │
│   │   Welcome to ForensicBridge                            │  │
│   │                                                         │  │
│   │   This will install:                                   │  │
│   │   • ForensicBridge Dashboard                           │  │
│   │   • QuickBooks Desktop Extractor                       │  │
│   │   • Caseware Export Tools                              │  │
│   │                                                         │  │
│   │   No QuickBooks SDK required - we handle everything.   │  │
│   │                                                         │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│   Install Location: C:\Program Files\ForensicBridge            │
│                                                                 │
│                                      [ Install ] [ Cancel ]    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

After install, they just double-click the desktop icon and drag files.

---

### Technical Flow (Hidden from User)

```
USER ACTION                    SYSTEM ACTION
───────────                    ─────────────
Drag .QBW file          →      Upload to S3 (encrypted, ca-central-1)
                        →      Spin up ephemeral EC2 instance
                        →      Open .QBW with QBFC16 SDK
                        →      Extract 31 entity types
                        →      Compute SHA-256 per record
                        →      Write NDJSON + run_manifest.json
                        →      Generate Caseware bundle
                        →      Terminate EC2, S3 TTL starts (24hr)
                        →      Webhook: "Completed"
Click "Download"        →      Fetch pre-signed S3 URL
                        →      Download Audit_TB.csv, Audit_GL.csv
```

**All complexity is invisible.** The accountant sees: drag, wait, download.

---

## 👁️ PREVIEW THE DASHBOARD UI

To view and test the dashboard locally:

### Quick Start (Development Mode)
```powershell
cd forensicbridge-dashboard
npm install      # First time only
npm run dev      # Starts dev server
```

Then open: **http://localhost:3000**

### What You'll See

| Route | Description |
|-------|-------------|
| `/` | **Main Dashboard** - Drag & drop upload, stats, recent migrations |
| `/settings` | **Settings** - Branding, notifications, security, billing, team tabs |
| `/migrations/[id]` | **Migration Detail** - Pizza Tracker, Reconciliation Shield, Discrepancy Doctor |
| `/login` | Login page |
| `/register` | Registration page |

### Build for Production
```powershell
cd forensicbridge-dashboard
npm run build    # Creates optimized build
npm run start    # Serves production build on port 3000
```

---

## 🏆 COMPLETE FEATURE INVENTORY

All 60+ features discovered in the codebase:

### Core Migration Features

| Feature | File | Description |
|---------|------|-------------|
| **31 Entity Extraction** | `QBDataExtractor.cs` | Invoices, Bills, JournalEntries, Customers, Vendors, Items, etc. |
| **Stream-Based NDJSON** | `NDJSONWriter.cs` | Handles 4GB+ files with minimal RAM |
| **Checkpoint Resumability** | `ExtractionCheckpoint.cs` | Checkpoints every 1000 records, survives crashes |
| **Incremental Sync** | `QBDataExtractor.cs` | Only extract records modified since last sync |
| **Streaming Pipeline** | `StreamingPipeline.cs` | Memory-efficient data flow |
| **Iterator Helper** | `QBIteratorHelper.cs` | Handles QB SDK pagination |
| **Field Limits** | `FieldLimits.cs` | Enforces QBO character limits |
| **Progress Reporter** | `ProgressReporter.cs` | Real-time extraction status |

---

### QBO API Features

| Feature | File | Description |
|---------|------|-------------|
| **Parallel Processing** | `data_transformer.py` | 5 threads for maximum QBO API throughput |
| **Smart Batching** | `qbo_client.py` | Auto-optimizes batch sizes (1-30) |
| **Rate Limit Governor** | `qbo_client.py` | Exponential backoff with jitter |
| **OAuth Token Manager** | `oauth_manager.py` | Auto-refresh tokens |
| **Thread-Safe SQLite** | `qbo_client.py` | State management across threads |
| **Migration Orchestrator** | `orchestrator.py` | Single entry point for end-to-end migration |

---

### Premium Verification Features

| Feature | File | Description |
|---------|------|-------------|
| **#1: Trial Balance Verification** | `verifier.py` | Compares Desktop vs Online to the penny |
| **#2: Reconciliation State** | `verifier.py` | Verifies bank reconciliation status transferred |
| **#4: PDF Audit Certificate** | `verifier.py` | Generates `ForensicAuditCertificate.pdf` |
| **#5: Discrepancy Drill-Down** | `verifier.py` | Account-by-account variance analysis |

---

### Report Generation

| Feature | File | Description |
|---------|------|-------------|
| **📊 Variance Report Generator** | `variance_report.py` | Side-by-side P&L and Balance Sheet comparison (3 years) |
| **📋 Health Check PDF** | `health_check_pdf.py` | Pre-migration readiness report (Red/Yellow/Green) |
| **📜 Discrepancy Report** | `main.py` | Auto-generated when trial balance doesn't match |
| **📄 HTML Reports** | `variance_report.py` | Professional HTML suitable for PDF conversion |

---

### Dashboard UI Components

| Component | File | Description |
|-----------|------|-------------|
| **🍕 Pizza Tracker** | `PizzaTracker.tsx` | Real-time migration progress (5 phases) |
| **🩺 Discrepancy Doctor** | `DiscrepancyDoctor.tsx` | Interactive variance analysis drill-down |
| **📜 Audit Cert Card** | `AuditCertCard.tsx` | Displays forensic verification status |
| **🛡️ Reconciliation Shield** | `ReconciliationShield.tsx` | Bank reconciliation status display |
| **🎨 White-Label Preview** | `WhitelabelPreview.tsx` | Custom branding preview for enterprise |

---

### Active Archival Portal (Data Museum)

| Feature | File | Description |
|---------|------|-------------|
| **Archive Web API** | `archive_portal.py` | Flask-based read-only access portal |
| **Transaction Search** | `archive_portal.py` | Full-text search across archived transactions |
| **Audit Log Access** | `archive_portal.py` | Browse access history |
| **API Key Authentication** | `archive_portal.py` | Secure portal access |
| **REST Endpoints** | `archive_portal.py` | `/api/archives`, `/api/search`, `/api/audit-log` |

---

### White-Label & Licensing

| Feature | File | Description |
|---------|------|-------------|
| **WhitelabelConfig** | `whitelabel.py` | Custom company name, colors, logo |
| **LicenseManager** | `whitelabel.py` | Generate/validate license keys |
| **WhitelabelPortal** | `whitelabel.py` | Reseller management for sub-clients |
| **CSS Variable Generation** | `whitelabel.py` | Auto-theming for UI |
| **STARTER/PROFESSIONAL/ENTERPRISE Tiers** | `whitelabel.py` | 10/100/Unlimited migrations/year |

---

### File Format Support

| Feature | File | Description |
|---------|------|-------------|
| **IIF Parser** | `iif_parser.py` | Parse QuickBooks IIF export files |
| **CSV Parser** | `iif_parser.py` | Parse QB CSV exports |
| **Excel Parser** | `iif_parser.py` | Parse QB Excel exports |
| **Auto-Detect Format** | `iif_parser.py` | Automatically detect file type |
| **Entity Type Detection** | `iif_parser.py` | Identify customers, vendors, items from content |

---

### Enterprise Tier Features

| Feature | File | Description |
|---------|------|-------------|
| **SSO/SAML** | `sso_provider.py` | Microsoft Entra, Google, Okta |
| **WORM Storage** | `enterprise_aws.py` | 7-year compliance retention |
| **Customer-Managed Keys** | `enterprise_aws.py` | Bring-your-own KMS encryption |
| **Multi-AZ Deployment** | `enterprise_aws.py` | Availability zone redundancy |
| **Regional Enforcement** | `enterprise_aws.py` | Canada-only data residency |

---

### Forensic Archival (Glacier)

| Feature | File | Description |
|---------|------|-------------|
| **ForensicArchivalService** | `forensic_archival.py` | 7-year metadata archival to Glacier |
| **Migration Metadata Archive** | `forensic_archival.py` | Who/what/when audit trail |
| **Verification Report Archive** | `forensic_archival.py` | Mathematical proof of integrity |
| **Lifecycle Rules** | `forensic_archival.py` | Auto-transition to Glacier after 90 days |
| **Glacier Restore** | `forensic_archival.py` | On-demand restoration for audits |

---

### Caseware Integration

| Feature | File | Description |
|---------|------|-------------|
| **Audit_TB.csv** | `caseware_exporter.py` | Trial Balance with Lead Sheet codes |
| **Audit_GL.csv** | `caseware_exporter.py` | General Ledger with SHA-256 hashes |
| **Audit_Mapping.cvw** | `caseware_exporter.py` | Caseware column configuration |
| **Global File Hash** | `caseware_exporter.py` | File-level integrity verification |
| **58 Lead Sheet Codes** | `caseware_exporter.py` | Agricultural + Manufacturing sectors |

---

### Forensic Integrity (C#)

| Feature | File | Description |
|---------|------|-------------|
| **Per-Row SHA-256 Hash** | `ForensicHashingService.cs` | Cryptographic hash per transaction |
| **Recursive Transaction Linker** | `RecursiveTransactionLinker.cs` | Payment → Invoice relationship tracking |
| **Hash Verifier** | `HashVerifier.cs` | Validate hash integrity |
| **Data Sanitizer** | `DataSanitizer.cs` | Remove PII before logging |
| **Log Redactor** | `LogRedactor.cs` | Secure logging |

---

### Security & Encryption

| Feature | File | Description |
|---------|------|-------------|
| **AES-256-GCM Encryption** | `EncryptionManager.cs` | At-rest encryption |
| **KMS Manager** | `kms_manager.py` | AWS KMS integration |
| **S3 Direct Upload** | `S3DirectUploader.cs` | Secure file transfer |
| **Argon2id Password Hashing** | `auth.py` | OWASP recommended |
| **Rate Limiting** | `auth.py` | Auth + uploads protected |
| **Account Lockout** | `auth.py` | 5 failed attempts |
| **Canadian Data Residency** | `enterprise_aws.py` | ca-central-1 only |

---

### Infrastructure

| Feature | File | Description |
|---------|------|-------------|
| **Webhook Logging** | `webhook_delivery_log.py` | Complete webhook audit trail |
| **Cleanup Scheduler** | `cleanup_scheduler.py` | Auto-cleanup expired data |
| **Backup Manager** | `backup.py` | Database backup automation |
| **AWS Manager** | `aws_manager.py` | S3/EC2 operations |
| **Notifications** | `notifications.py` | Email/SMS alerts |
| **Validators** | `validators.py` | Input validation |

---



## 📋 MASTER CHECKLIST

### Phase 1: External Services Registration
- [ ] AWS Account setup
- [ ] Intuit Developer Account + QuickBooks API
- [ ] SSO Provider setup (if enterprise)
- [ ] Domain + SSL Certificate
- [ ] Email service (SendGrid/SES)

### Phase 2: Infrastructure Setup
- [ ] S3 Bucket creation (ca-central-1)
- [ ] KMS Key creation (for CMK customers)
- [ ] IAM User/Role with permissions
- [ ] PostgreSQL Database (RDS or local)
- [ ] Redis (for rate limiting - optional)

### Phase 3: Configuration
- [ ] .env file complete
- [ ] Database migrations
- [ ] requirements.txt installed

### Phase 4: Build & Test
- [ ] C# project builds
- [ ] Python server starts
- [ ] Endpoints respond
- [ ] Hash generation works

---

## 🔐 AWS SETUP

### Step 1: Create AWS Account
1. Go to https://aws.amazon.com/
2. Create account (requires credit card)
3. Enable MFA on root account

### Step 2: Create IAM User for ForensicBridge

In AWS Console → IAM → Users → Create User:

**User name:** `forensicbridge-prod`  
**Access type:** Programmatic access

Attach these policies:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:ListBucket",
                "s3:GetBucketLocation",
                "s3:PutObjectRetention",
                "s3:GetObjectRetention",
                "s3:PutObjectLegalHold"
            ],
            "Resource": [
                "arn:aws:s3:::forensicbridge-prod-*",
                "arn:aws:s3:::forensicbridge-prod-*/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:GenerateDataKey"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:RunInstances",
                "ec2:TerminateInstances",
                "ec2:DescribeInstances",
                "ec2:DescribeAvailabilityZones"
            ],
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    "aws:RequestedRegion": "ca-central-1"
                }
            }
        }
    ]
}
```

Save the **Access Key ID** and **Secret Access Key**.

### Step 3: Create S3 Bucket

```bash
aws s3 mb s3://forensicbridge-prod-migrations --region ca-central-1
```

Enable Object Lock (for WORM):
```bash
aws s3api put-object-lock-configuration \
    --bucket forensicbridge-prod-migrations \
    --object-lock-configuration '{"ObjectLockEnabled":"Enabled","Rule":{"DefaultRetention":{"Mode":"COMPLIANCE","Years":7}}}'
```

### Step 4: Create KMS Key (for CMK customers)

```bash
aws kms create-key --region ca-central-1 --description "ForensicBridge CMK"
```

Save the **Key ID** returned.

---

## 📱 QUICKBOOKS API SETUP

### Step 1: Create Intuit Developer Account
1. Go to https://developer.intuit.com/
2. Sign up for developer account
3. Verify email

### Step 2: Create App

In Developer Portal → Dashboard → Create an App:

**App Name:** ForensicBridge  
**Scopes:** `com.intuit.quickbooks.accounting`  
**Redirect URIs:** 
- `http://localhost:5000/api/auth/callback` (development)
- `https://yourdomain.com/api/auth/callback` (production)

### Step 3: Get Credentials

After app creation, note:
- **Client ID** (OAuth 2.0)
- **Client Secret** (OAuth 2.0)
- **Redirect URI**

### Step 4: For Desktop (QBFC SDK)

Download QuickBooks SDK from Intuit:
https://developer.intuit.com/app/developer/qbdesktop/docs/get-started

Install QBFC16 on Windows machine with QuickBooks Desktop.

---

## 🔑 SSO PROVIDER SETUP (Enterprise Only)

### Microsoft Entra ID (Azure AD)

1. Go to https://portal.azure.com/
2. Azure Active Directory → App Registrations → New Registration
3. **Name:** ForensicBridge SSO
4. **Redirect URI:** `https://yourdomain.com/api/sso/callback`
5. Note the **Application (client) ID** and **Directory (tenant) ID**
6. Create Client Secret → Note the **Value**

### Google Workspace

1. Go to https://console.cloud.google.com/
2. APIs & Services → Credentials → Create Credentials → OAuth Client ID
3. **Application type:** Web application
4. **Authorized redirect URIs:** `https://yourdomain.com/api/sso/callback`
5. Note **Client ID** and **Client Secret**

### Okta

1. Go to your Okta Admin Console
2. Applications → Create App Integration
3. **Sign-in method:** OIDC - OpenID Connect
4. **Application type:** Web Application
5. **Sign-in redirect URIs:** `https://yourdomain.com/api/sso/callback`
6. Note **Client ID**, **Client Secret**, and **Okta Domain**

---

## 📧 EMAIL SERVICE SETUP

### Option A: AWS SES (Recommended for Canada)

1. AWS Console → SES → Verified Identities
2. Add your domain or email address
3. Verify DNS records
4. Note the SES SMTP credentials

### Option B: SendGrid

1. Go to https://sendgrid.com/
2. Create account
3. Settings → API Keys → Create API Key (Full Access)
4. Note the **API Key**

---

## 🌐 DOMAIN & SSL

### Domain Registration
1. Register domain (Namecheap, GoDaddy, etc.)
2. Point DNS to your server IP

### SSL Certificate (Free with Let's Encrypt)
```bash
sudo apt install certbot
sudo certbot certonly --standalone -d yourdomain.com
```

---

## 🗄️ DATABASE SETUP

### Option A: AWS RDS (Production)

1. AWS Console → RDS → Create Database
2. **Engine:** PostgreSQL 15
3. **Instance:** db.t3.micro (free tier) or db.t3.small
4. **Region:** ca-central-1
5. Note the **Endpoint**, **Username**, **Password**

### Option B: Local PostgreSQL

```bash
# Install
sudo apt install postgresql postgresql-contrib

# Create database
sudo -u postgres psql
CREATE DATABASE forensicbridge;
CREATE USER fbuser WITH PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE forensicbridge TO fbuser;
```

---

## 📄 COMPLETE .ENV FILE

Create `QBMigrationServer/.env`:

```bash
# =============================================================================
# FORENSICBRIDGE PRODUCTION CONFIGURATION
# =============================================================================

# -----------------------------------------------------------------------------
# FLASK SETTINGS
# -----------------------------------------------------------------------------
FLASK_ENV=production
FLASK_DEBUG=false
SECRET_KEY=your-256-bit-secret-key-here-generate-with-openssl

# -----------------------------------------------------------------------------
# DATABASE
# -----------------------------------------------------------------------------
DATABASE_URL=postgresql://fbuser:your-password@localhost:5432/forensicbridge
# Or for RDS:
# DATABASE_URL=postgresql://fbuser:password@your-rds-endpoint.ca-central-1.rds.amazonaws.com:5432/forensicbridge

# -----------------------------------------------------------------------------
# AWS CONFIGURATION
# -----------------------------------------------------------------------------
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION=ca-central-1
AWS_S3_BUCKET=forensicbridge-prod-migrations
AWS_S3_ENCRYPTION=AES256
AWS_S3_FILE_TTL_HOURS=24

# -----------------------------------------------------------------------------
# QUICKBOOKS ONLINE API (OAuth 2.0)
# -----------------------------------------------------------------------------
QBO_CLIENT_ID=your-intuit-client-id
QBO_CLIENT_SECRET=your-intuit-client-secret
QBO_REDIRECT_URI=https://yourdomain.com/api/auth/callback
QBO_ENVIRONMENT=production
# For sandbox testing:
# QBO_ENVIRONMENT=sandbox

# -----------------------------------------------------------------------------
# ENTERPRISE FEATURES
# -----------------------------------------------------------------------------
# SSO
ENABLE_SSO=false
SSO_PROVIDERS=microsoft,google,okta
SAML_SP_ENTITY_ID=https://yourdomain.com
SAML_ACS_URL=https://yourdomain.com/api/sso/acs

# Microsoft Entra (if using SSO)
MS_ENTRA_TENANT_ID=your-azure-tenant-id
MS_ENTRA_CLIENT_ID=your-azure-client-id
MS_ENTRA_CLIENT_SECRET=your-azure-client-secret

# Google Workspace (if using SSO)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Okta (if using SSO)
OKTA_DOMAIN=your-org.okta.com
OKTA_CLIENT_ID=your-okta-client-id
OKTA_CLIENT_SECRET=your-okta-client-secret

# WORM Storage
ENABLE_WORM_STORAGE=false
WORM_RETENTION_YEARS=7
WORM_RETENTION_MODE=COMPLIANCE

# Customer-Managed Keys
ENABLE_CMK=false
DEFAULT_CMK_ARN=

# Multi-AZ
ENABLE_MULTI_AZ=false
PREFERRED_AZS=ca-central-1a,ca-central-1b,ca-central-1d

# Forensic Archival (Glacier)
ENABLE_FORENSIC_ARCHIVAL=false
GLACIER_RETENTION_YEARS=7

# Webhook Logging
ENABLE_WEBHOOK_LOGGING=true
WEBHOOK_LOG_RETENTION_DAYS=90

# -----------------------------------------------------------------------------
# SECURITY
# -----------------------------------------------------------------------------
ENABLE_2FA=false
RATELIMIT_ENABLED=true
RATELIMIT_DEFAULT=100 per minute
RATELIMIT_STORAGE_URL=memory://
# For production with Redis:
# RATELIMIT_STORAGE_URL=redis://localhost:6379/0

# -----------------------------------------------------------------------------
# EMAIL (Choose one)
# -----------------------------------------------------------------------------
# AWS SES
EMAIL_BACKEND=ses
SES_REGION=ca-central-1
SES_FROM_EMAIL=noreply@yourdomain.com

# SendGrid
# EMAIL_BACKEND=sendgrid
# SENDGRID_API_KEY=SG.xxxxxx

# -----------------------------------------------------------------------------
# MONITORING (Optional)
# -----------------------------------------------------------------------------
SENTRY_DSN=
SENTRY_ENVIRONMENT=production

# -----------------------------------------------------------------------------
# CLEANUP
# -----------------------------------------------------------------------------
AUTO_CLEANUP_ENABLED=true
CLEANUP_INTERVAL_MINUTES=15
```

---

## 🔧 FINAL SETUP COMMANDS

Run these in order:

```bash
# 1. Install Python dependencies
cd C:\Users\Sivaharan\QBMigration\QBMigrationServer
pip install -r requirements.txt
pip install python-saml3

# 2. Run database migrations
flask db upgrade

# 3. Build C# project
cd C:\Users\Sivaharan\QBMigration\QBDesktopReader
dotnet build -c Release

# 4. Test server starts
cd C:\Users\Sivaharan\QBMigration\QBMigrationServer
python app.py

# 5. Test endpoints
curl http://localhost:5000/api/health
curl http://localhost:5000/api/health/compliance
```

---

## ✅ VERIFICATION TESTS

### Test 1: AWS Connection
```python
import boto3
s3 = boto3.client('s3', region_name='ca-central-1')
s3.list_buckets()  # Should not error
```

### Test 2: Database Connection
```bash
flask shell
>>> from models.database import db
>>> db.session.execute('SELECT 1')
```

### Test 3: Hash Generation
```bash
cd C:\Users\Sivaharan\QBMigration\QBMigrationService
python -c "from caseware_exporter import CasewareExporter; print(CasewareExporter.compute_sha256_hash({'test': 'data'}))"
```

---

## 💰 COST ESTIMATES (Monthly)

| Service | Tier | Cost |
|---------|------|------|
| AWS S3 | 100GB storage | ~$3 |
| AWS RDS (PostgreSQL) | db.t3.micro | ~$15 (or free tier) |
| AWS KMS | Per key + requests | ~$1-5 |
| Domain | .com | ~$12/year |
| SSL | Let's Encrypt | FREE |
| SendGrid | Free tier | FREE (100 emails/day) |

**Total:** ~$20-25/month for startup scale

---

## 🚀 GO-LIVE CHECKLIST

Final verification before launch:

- [ ] All .env variables populated
- [ ] AWS credentials working
- [ ] S3 bucket accessible
- [ ] Database connected
- [ ] Server starts without errors
- [ ] `/api/health` returns 200
- [ ] `/api/health/compliance` shows `canadian_residency: true`
- [ ] QuickBooks OAuth flow works
- [ ] Caseware bundle generates with hashes
- [ ] SSL certificate valid
- [ ] Domain DNS propagated
