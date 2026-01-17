# ForensicBridge™ Complete Launch Checklist

**Target Launch Date:** Week of January 20-24, 2026  
**Version:** 4.2.0  
**Prepared For:** Caseware Partnership  
**Last Updated:** January 16, 2026

---

## Executive Summary

This document provides a **complete, institutional-grade** checklist for launching the ForensicBridge™ QuickBooks Migration solution. It consolidates requirements from all project documentation and covers:

- ✅ File type support verification
- ✅ AWS infrastructure setup  
- ✅ Intuit developer portal & API keys
- ✅ Security credentials configuration
- ✅ Testing & verification procedures
- ✅ Build & deployment procedures
- ✅ Production go-live checklist

**Estimated Total Time:** 4-6 hours (spread across multiple days for API approval processes)

---

## Table of Contents

1. [File Type Support Matrix](#1-file-type-support-matrix)
2. [Pre-Launch Requirements](#2-pre-launch-requirements)
3. [AWS Infrastructure Setup](#3-aws-infrastructure-setup)
4. [Intuit Developer Portal Setup](#4-intuit-developer-portal-setup)
5. [Security Credentials Configuration](#5-security-credentials-configuration)
6. [Database Setup](#6-database-setup)
7. [Build & Deploy the Installer](#7-build--deploy-the-installer)
8. [Testing & Verification](#8-testing--verification)
9. [Known Issues & Fixes](#9-known-issues--fixes)
10. [Production Go-Live Checklist](#10-production-go-live-checklist)
11. [Post-Launch Monitoring](#11-post-launch-monitoring)
12. [Credentials Reference Sheet](#12-credentials-reference-sheet)

---

## 1. File Type Support Matrix

> [!IMPORTANT]  
> This section answers: **"Which QuickBooks file types can ForensicBridge handle?"**

### ✅ FULLY SUPPORTED (Production Ready)

| File Type | Extension | Support Level | How It Works |
|-----------|-----------|---------------|--------------|
| **QuickBooks Working File** | `.QBW` | ✅ **NATIVE** | Direct extraction via QBFC16 SDK. This is the primary use case. |
| **QBXML Requests** | `.QBXML` | ✅ **NATIVE** | The C# engine speaks QBXML natively (versions 1-16 supported). |
| **Intuit Interchange Format** | `.IIF` | ✅ **FULL** | Parsed via `QBMigrationService/iif_parser.py`. Supports customers, vendors, items, accounts, employees. |
| **CSV Exports** | `.CSV` | ✅ **FULL** | Parsed via `QuickBooksExportParser` class with auto-detection. |
| **Excel Exports** | `.XLS`, `.XLSX` | ✅ **FULL** | Parsed via `QuickBooksExportParser` with entity type detection. |

### ⚠️ REQUIRES MANUAL STEP FIRST

| File Type | Extension | Support Level | What's Required |
|-----------|-----------|---------------|-----------------|
| **QuickBooks Backup File** | `.QBB` | ⚠️ **INDIRECT** | User must restore to `.QBW` in QuickBooks Desktop first, then ForensicBridge extracts from the restored file. |
| **QuickBooks Portable File** | `.QBM` | ⚠️ **INDIRECT** | User must restore to `.QBW` in QuickBooks Desktop first, then ForensicBridge extracts from the restored file. |

### ❌ NOT SUPPORTED (Out of Scope)

| File Type | Extension | Reason |
|-----------|-----------|--------|
| QuickBooks Mac Files | `.qbb` (Mac) | Different SDK - Mac uses different internal format |
| Encrypted QBB without password | `.QBB` | Cannot decrypt without user password |

### Why .QBB/.QBM Require Manual Restore

The `.QBB` and `.QBM` files are **compressed/encrypted container formats**, not databases. QuickBooks Desktop itself must decompress them:

1. User opens QuickBooks Desktop
2. File → Restore Backup (for .QBB) or Portable Company (for .QBM)
3. QuickBooks creates a `.QBW` file
4. ForensicBridge reads the `.QBW` directly

> [!TIP]  
> **Valuation Impact:** Adding direct .QBB extraction (bypassing manual restore) would require reverse-engineering Intuit's compression format. This is technically possible but adds significant development time. Consider this for v5.0.

### QBXML Version Support

Our C# engine (`QBSessionManager.cs`) supports QBXML versions 1-16:

| QB Desktop Version | QBXML Version | Supported |
|-------------------|---------------|-----------|
| QB 2000-2003 | 1.0 - 3.0 | ✅ |
| QB 2004-2006 | 4.0 - 6.0 | ✅ |
| QB 2007-2010 | 7.0 - 10.0 | ✅ |
| QB 2011-2015 | 11.0 - 13.0 | ✅ |
| QB 2016-2024 | 13.0 - 16.0 | ✅ |

---

## 2. Pre-Launch Requirements

### ✅ Accounts You Must Have

| Account | Purpose | Sign Up URL | Status |
|---------|---------|-------------|--------|
| **AWS Account** | Cloud infrastructure | [aws.amazon.com](https://aws.amazon.com) | ⬜ |
| **Intuit Developer Account** | QuickBooks Online API | [developer.intuit.com](https://developer.intuit.com) | ⬜ |
| **GitHub Account** | Code hosting & CI/CD | [github.com](https://github.com) | ⬜ |
| **Sentry Account** (Optional) | Error monitoring | [sentry.io](https://sentry.io) | ⬜ |

### ✅ Local Tools Required

- [ ] **Git** installed (`git --version`)
- [ ] **Text editor** (VS Code, Notepad++, etc.)
- [ ] **Web browser** for AWS/Intuit consoles
- [ ] **SSH client** (built into Windows 10/11)

### ✅ Assets You Must Create

| Asset | Location | Status |
|-------|----------|--------|
| Application icon | `QBDesktopReader/assets/icon.ico` | ⬜ Missing - **BLOCKER** |
| SSL Certificate | AWS Certificate Manager | ⬜ |
| Production secrets | Generate new ones (see Section 5) | ⬜ |

---

## 3. AWS Infrastructure Setup

### 3.1 Current AWS Credentials (Development)

> [!CAUTION]  
> These are development credentials. Generate new ones for production!

| Credential | Current Value | Production Status |
|------------|---------------|-------------------|
| `AWS_ACCESS_KEY_ID` | `AKIAQS67ZLOOWF7CKZUU` | ⚠️ Replace for production |
| `AWS_SECRET_ACCESS_KEY` | `RHDqB7jCwp...` | ⚠️ Replace for production |
| `AWS_REGION` | `us-east-1` | ✅ OK |
| `AWS_S3_BUCKET` | `qb-migration-blossummico` | ⚠️ Replace with CF output |

### 3.2 Deploy CloudFormation Stack

> [!IMPORTANT]
> This creates your entire production infrastructure with one click.

**Steps:**

- [ ] 1. Log in to [AWS Console](https://console.aws.amazon.com)
- [ ] 2. Navigate to **CloudFormation** service
- [ ] 3. Click **Create stack** → **With new resources (standard)**
- [ ] 4. Select **Upload a template file**
- [ ] 5. Upload: `c:\Users\Sivaharan\QBMigration\aws\cloudformation.yaml`
- [ ] 6. Configure parameters:
   - **Stack name:** `ForensicBridge-Prod`
   - **Environment:** `production`
   - **DBPassword:** Generate 16+ char password → **SAVE THIS!**
   - **DomainName:** `api.forensicbridge.io` (or your domain)
- [ ] 7. Click **Next** → **Next** → Check "I acknowledge IAM resources" → **Submit**
- [ ] 8. Wait ~10-15 minutes for `CREATE_COMPLETE`
- [ ] 9. Go to **Outputs** tab and record:

| Output Key | Your Value |
|------------|------------|
| `ALBDNS` | ______________ |
| `S3Bucket` | ______________ |
| `DatabaseEndpoint` | ______________ |
| `RedisEndpoint` | ______________ |
| `EC2PublicIP` | ______________ |

### 3.3 AWS Resources Created

| Resource | Type | Purpose |
|----------|------|---------|
| VPC + Subnets | Networking | Isolated network |
| EC2 Instance | t3.small | Flask API server |
| RDS PostgreSQL | db.t3.micro | Migration database |
| ElastiCache Redis | cache.t3.micro | Rate limiting/sessions |
| S3 Bucket | Storage | Encrypted migration data |
| ALB | Load Balancer | HTTPS termination |
| IAM Roles | Security | Least-privilege access |

---

## 4. Intuit Developer Portal Setup

> [!CAUTION]
> **START THIS TODAY!** Production keys require Intuit approval (3-5 business days).

### 4.1 Create an App

- [ ] 1. Go to [developer.intuit.com](https://developer.intuit.com)
- [ ] 2. Sign in or create account
- [ ] 3. Click **Dashboard** → **+ Create an app**
- [ ] 4. Select **QuickBooks Online and Payments**
- [ ] 5. App Name: `ForensicBridge Migration`

### 4.2 Get Sandbox Keys (for testing)

- [ ] 1. Go to **Keys & OAuth** → **Sandbox** tab
- [ ] 2. Copy **Client ID (Sandbox):** _______________
- [ ] 3. Copy **Client Secret (Sandbox):** _______________
- [ ] 4. Add Redirect URI: `http://localhost:5000/api/qbo/callback`

### 4.3 Apply for Production Keys (CRITICAL!)

- [ ] 1. Go to **Keys & OAuth** → **Production** tab
- [ ] 2. Click **Get production keys**
- [ ] 3. Complete security questionnaire
- [ ] 4. Wait for approval email (3-5 business days)
- [ ] 5. After approval, copy:
   - **Client ID (Production):** _______________
   - **Client Secret (Production):** _______________

### 4.4 Required OAuth Scopes

| Scope | Purpose | Required |
|-------|---------|----------|
| `com.intuit.quickbooks.accounting` | Read/write accounting data | ✅ Yes |
| `openid` | User authentication | ✅ Yes |
| `profile` | Basic user info | ✅ Yes |
| `email` | User email | ✅ Yes |

---

## 5. Security Credentials Configuration

### 5.1 Generate Production Secrets

> [!WARNING]
> Never use development secrets in production!

**PowerShell Commands:**

```powershell
# SECRET_KEY (32+ characters)
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]])

# WEBHOOK_SECRET (64 hex characters)
-join ((1..64) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })

# BACKUP_ENCRYPTION_KEY (requires Python + cryptography)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 5.2 Production `.env` Template

```env
# ============================================================================
# PRODUCTION - ForensicBridge v4.2.0
# ============================================================================

FLASK_ENV=production
DEBUG=False

# Security (GENERATE NEW!)
SECRET_KEY=[YOUR_32+_CHAR_KEY]
WEBHOOK_SECRET=[YOUR_64_HEX_CHARS]
BACKUP_ENCRYPTION_KEY=[FERNET_KEY]

# Server URL (from CloudFormation ALBDNS)
SERVER_URL=https://[YOUR_ALB_DNS]

# Database (from CloudFormation)
DATABASE_URL=postgresql://forensicbridge:[DB_PASSWORD]@[RDS_ENDPOINT]:5432/forensicbridge

# AWS (from CloudFormation)
AWS_ACCESS_KEY_ID=[PROD_ACCESS_KEY]
AWS_SECRET_ACCESS_KEY=[PROD_SECRET_KEY]
AWS_REGION=us-east-1
AWS_S3_BUCKET=[S3_BUCKET_NAME]

# Redis (from CloudFormation)
REDIS_URL=redis://[REDIS_ENDPOINT]:6379/0

# QuickBooks Online (from Intuit)
QBO_CLIENT_ID=[PROD_CLIENT_ID]
QBO_CLIENT_SECRET=[PROD_CLIENT_SECRET]
QBO_ENVIRONMENT=production
QBO_REDIRECT_URI=https://[YOUR_DOMAIN]/api/qbo/callback

# Production Guards
QBO_PRODUCTION_GUARD=true
QBO_CONFIRM_PRODUCTION=true

# Monitoring
SENTRY_DSN=[YOUR_SENTRY_DSN]
```

### 5.3 Deploy to EC2

- [ ] 1. SSH into EC2:
```bash
ssh -i qb-migration-key.pem ubuntu@[EC2_PUBLIC_IP]
```
- [ ] 2. Edit config:
```bash
sudo nano /opt/forensicbridge/.env
```
- [ ] 3. Paste production values
- [ ] 4. Restart:
```bash
sudo systemctl restart forensicbridge
```

---

## 6. Database Setup

### 6.1 Run Migrations

```bash
# SSH into EC2
cd /opt/forensicbridge
source venv/bin/activate
flask db upgrade
```

### 6.2 Create Admin User (Optional)

```bash
flask create-admin --email admin@yourcompany.com --password [SECURE_PASSWORD]
```

### 6.3 Verify Connectivity

```bash
psql -h [RDS_ENDPOINT] -U forensicbridge -d forensicbridge
# Run: \dt to list tables
```

---

## 7. Build & Deploy the Installer

### 7.1 Fix Missing Assets (BLOCKER)

- [ ] Create application icon:
  - Download/create a 32x32 or 64x64 `.ico` file
  - Save to: `QBDesktopReader/assets/icon.ico`

### 7.2 Update Configuration

- [ ] Edit `QBDesktopReader/config.json`:
```json
{
  "serverUrl": "https://[YOUR_ALB_DNS_OR_DOMAIN]"
}
```

### 7.3 Push to GitHub & Build

```bash
cd c:\Users\Sivaharan\QBMigration

git add .
git commit -m "Release v4.2.0 - Production"
git push origin main
```

### 7.4 Download Installer

- [ ] 1. Go to GitHub → **Actions** tab
- [ ] 2. Find **"Build ForensicBridge Installer"** workflow
- [ ] 3. Wait for ✅ green checkmark
- [ ] 4. Download **ForensicBridge-Setup.zip** from Artifacts
- [ ] 5. Extract to get **ForensicBridge-Setup.exe**

---

## 8. Testing & Verification

### 8.1 Automated Test Suite

```bash
cd c:\Users\Sivaharan\QBMigration

# Install dependencies
pip install pytest pytest-cov

# Run all tests
python run_all_tests.py

# Expected: 22+ tests passing
```

### 8.2 Test Coverage Summary

| Category | Status | Tests |
|----------|--------|-------|
| User Registration & Login | ✅ Pass | test_complete.py |
| Password Complexity | ✅ Pass | test_complete.py |
| Account Lockout | ✅ Pass | test_complete.py |
| File Upload | ✅ Pass | test_complete.py |
| SQL Injection Prevention | ✅ Pass | test_complete.py |
| Migration Status Tracking | ✅ Pass | test_complete.py |
| Webhook HMAC Validation | ✅ Pass | test_complete.py |
| AES-256-GCM Encryption | ✅ Pass | test_e2e_flow.py |
| Rate Limiting | ✅ Pass | test_complete.py |
| QBO Client Operations | ✅ Pass | test_qbo_client.py |

### 8.3 Manual End-to-End Test

> [!IMPORTANT]
> Test with **sandbox** QuickBooks Online first!

**Procedure:**

- [ ] 1. Install `ForensicBridge-Setup.exe` on Windows PC with QB Desktop
- [ ] 2. Launch ForensicBridge
- [ ] 3. Accept Forensic Audit terms
- [ ] 4. Drag test `.QBW` file onto window
- [ ] 5. Verify:
   - [ ] QuickBooks opens in background
   - [ ] Progress bar updates
   - [ ] Data extracts successfully
   - [ ] Upload completes
   - [ ] Migration ID displayed
- [ ] 6. Check QBO sandbox for migrated data
- [ ] 7. Verify `ForensicAuditCertificate.pdf` generation

### 8.4 Entity Type Verification

| Entity Type | Extraction | Transformation | QBO Upload |
|-------------|-----------|----------------|------------|
| Accounts | ⬜ | ⬜ | ⬜ |
| Customers | ⬜ | ⬜ | ⬜ |
| Vendors | ⬜ | ⬜ | ⬜ |
| Items | ⬜ | ⬜ | ⬜ |
| Invoices | ⬜ | ⬜ | ⬜ |
| Bills | ⬜ | ⬜ | ⬜ |
| Journal Entries | ⬜ | ⬜ | ⬜ |
| Trial Balance | ⬜ | ⬜ | ⬜ |

### 8.5 Security Checklist

- [ ] HTTPS enabled on production URL
- [ ] SSL certificate valid
- [ ] SECRET_KEY is 32+ characters
- [ ] Database password is 16+ characters
- [ ] AWS IAM uses least-privilege
- [ ] S3 bucket has no public access
- [ ] Rate limiting enabled in production
- [ ] Sentry error tracking configured

---

## 9. Known Issues & Fixes

### From CODEBASE_AUDIT.md

| Issue | Priority | Fix |
|-------|----------|-----|
| Empty `installer/` directory | 🔴 CRITICAL | Run GitHub Actions build |
| Missing `icon.ico` | 🔴 CRITICAL | Create and add to `assets/` |
| Placeholder QBO credentials | 🔴 CRITICAL | Get from Intuit Portal |
| Missing project reference | 🟡 HIGH | Add in QBMigrationLauncher.csproj |
| Empty `aws/lambda/` | 🟢 LOW | Optional cleanup function |

### From COMPREHENSIVE_TESTING_REPORT.md

| Recommendation | Priority | Status |
|----------------|----------|--------|
| Add network timeout configuration | HIGH | ✅ Implemented in config.py |
| Implement retry logic with backoff | HIGH | ✅ Implemented |
| Add correlation IDs for logging | MEDIUM | ⬜ To do |
| Add date format auto-detection | MEDIUM | ⬜ To do |

---

## 10. Production Go-Live Checklist

### Pre-Launch Verification

| Item | Status |
|------|--------|
| CloudFormation stack `CREATE_COMPLETE` | ⬜ |
| EC2 instance running and healthy | ⬜ |
| RDS database accessible | ⬜ |
| Redis cluster running | ⬜ |
| S3 bucket created with encryption | ⬜ |
| Intuit **production** keys obtained | ⬜ |
| `.env` updated with production values | ⬜ |
| Server returning `/health` OK | ⬜ |
| Installer built successfully | ⬜ |
| End-to-end test passed with sandbox | ⬜ |
| `icon.ico` file created | ⬜ |

### Domain & SSL Setup

- [ ] 1. Register/configure domain
- [ ] 2. Create CNAME record → ALB DNS
- [ ] 3. Request SSL certificate in AWS Certificate Manager
- [ ] 4. Attach certificate to ALB listener (port 443)
- [ ] 5. Update all URLs to `https://`

### Go-Live Commands

```bash
# SSH into EC2
ssh -i qb-migration-key.pem ubuntu@[EC2_IP]

# Verify production mode
cat /opt/forensicbridge/.env | grep FLASK_ENV
# Should show: FLASK_ENV=production

# Restart services
sudo systemctl restart forensicbridge
sudo systemctl restart forensicbridge-worker

# Check logs
sudo journalctl -u forensicbridge -f

# Verify health
curl https://[YOUR_DOMAIN]/health
```

---

## 11. Post-Launch Monitoring

### Health Check Endpoint

```bash
curl https://[YOUR_DOMAIN]/health
# Expected: {"status": "healthy", "database": "connected", "redis": "connected"}
```

### CloudWatch Alerts (Recommended)

| Metric | Threshold | Action |
|--------|-----------|--------|
| EC2 CPU | > 80% for 5 min | Email alert |
| RDS Connections | > 50 | Scale up |
| S3 Request Errors | > 10/min | Investigate |
| ALB 5xx Errors | > 5/min | Page on-call |

### Monitoring Dashboards

- AWS CloudWatch: [console.aws.amazon.com/cloudwatch](https://console.aws.amazon.com/cloudwatch)
- Sentry: [sentry.io](https://sentry.io)
- AWS EC2: [console.aws.amazon.com/ec2](https://console.aws.amazon.com/ec2)

---

## 12. Credentials Reference Sheet

> [!CAUTION]
> Store this securely in a password manager!

### AWS

| Name | Value |
|------|-------|
| Access Key ID | ______________ |
| Secret Access Key | ______________ |
| Region | us-east-1 |
| S3 Bucket | ______________ |

### Database (RDS)

| Name | Value |
|------|-------|
| Host | ______________ |
| Port | 5432 |
| Username | forensicbridge |
| Password | ______________ |
| Database | forensicbridge |

### QuickBooks Online

| Name | Sandbox | Production |
|------|---------|------------|
| Client ID | ______________ | ______________ |
| Client Secret | ______________ | ______________ |
| Redirect URI | localhost:5000 | [prod domain] |
| Environment | sandbox | production |

### Application Secrets

| Name | Value | Generation |
|------|-------|------------|
| SECRET_KEY | ______________ | 32+ base64 chars |
| WEBHOOK_SECRET | ______________ | 64 hex chars |
| BACKUP_ENCRYPTION_KEY | ______________ | Fernet key |

---

## Quick Reference Commands

```bash
# Deploy CloudFormation
aws cloudformation deploy --template-file aws/cloudformation.yaml \
  --stack-name ForensicBridge-Prod --capabilities CAPABILITY_IAM

# Run tests
python run_all_tests.py

# SSH into server  
ssh -i qb-migration-key.pem ubuntu@[EC2_IP]

# Check server logs
sudo journalctl -u forensicbridge -f

# Restart server
sudo systemctl restart forensicbridge

# Health check
curl https://[YOUR_DOMAIN]/health
```

---

## Timeline Summary

| Day | Tasks |
|-----|-------|
| **Day 1 (Today)** | Apply for Intuit production keys, deploy CloudFormation, create icon |
| **Day 2** | Configure production secrets, run database migrations |
| **Day 3** | Run full test suite, fix any issues |
| **Day 4** | End-to-end testing with sandbox QBO |
| **Day 5** | Receive Intuit approval, configure production keys |
| **Day 6** | Final testing, build production installer |
| **Day 7** | Go-live! 🚀 |

---

**Document Status:** Ready for Caseware Review  
**Prepared by:** ForensicBridge Development Team  
**Version:** 2.0 (Comprehensive Edition)
