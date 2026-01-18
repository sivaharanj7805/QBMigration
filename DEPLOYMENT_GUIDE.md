# ForensicBridge Production Deployment Guide

> **Complete checklist for AWS deployment and Intuit production keys**  
> Updated: 2026-01-18

---

## Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT ROADMAP                                       │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  PHASE 1: Domain & SSL (30 min)                                            │
│  ├── Register domain (forensicbridge.ca)                                   │
│  ├── Set up SSL certificate                                                │
│  └── Configure DNS                                                         │
│                                                                            │
│  PHASE 2: AWS Infrastructure (1-2 hours)                                   │
│  ├── Create AWS account                                                    │
│  ├── Deploy CloudFormation stack                                           │
│  ├── Get Elastic IP                                                        │
│  └── Configure security groups                                             │
│                                                                            │
│  PHASE 3: Legal Pages (1 hour)                                             │
│  ├── Create Privacy Policy page                                            │
│  ├── Create EULA page                                                      │
│  └── Host on your domain                                                   │
│                                                                            │
│  PHASE 4: Intuit Registration (30 min)                                     │
│  ├── Submit app for production                                             │
│  ├── Complete security questionnaire                                       │
│  └── Get production keys                                                   │
│                                                                            │
│  PHASE 5: Final Configuration (30 min)                                     │
│  ├── Configure OAuth credentials                                           │
│  ├── Test end-to-end flow                                                  │
│  └── Go live!                                                              │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

# PHASE 1: Domain & SSL

## 1.1 Register Domain (if not done)

**Option A: AWS Route 53**
```
1. Go to AWS Console → Route 53 → Registered domains
2. Click "Register Domain"
3. Search for "forensicbridge.ca"
4. Purchase (~$12/year for .ca)
```

**Option B: External Registrar**
- GoDaddy, Namecheap, Google Domains
- Then point nameservers to Route 53

## 1.2 Get SSL Certificate (Free with AWS)

```
1. Go to AWS Console → Certificate Manager
2. Click "Request certificate"
3. Request a public certificate
4. Add domains:
   - forensicbridge.ca
   - *.forensicbridge.ca (wildcard)
5. Choose DNS validation
6. AWS will auto-validate if using Route 53
```

---

# PHASE 2: AWS Infrastructure

## 2.1 Prerequisites Checklist

- [ ] AWS Account created
- [ ] AWS CLI installed and configured
- [ ] Domain registered
- [ ] SSL certificate issued

## 2.2 Deploy CloudFormation Stack

```powershell
# Navigate to your project
cd C:\Users\Sivaharan\QBMigration

# Deploy the stack (run from AWS CLI)
aws cloudformation create-stack `
  --stack-name forensicbridge-prod `
  --template-body file://aws/cloudformation.yaml `
  --parameters `
    ParameterKey=Environment,ParameterValue=production `
    ParameterKey=DBPassword,ParameterValue=YOUR_SECURE_PASSWORD `
  --capabilities CAPABILITY_IAM `
  --region ca-central-1
```

## 2.3 Get Elastic IP (Static IP)

```
1. Go to AWS Console → EC2 → Elastic IPs
2. Click "Allocate Elastic IP address"
3. Select "Amazon's pool of IPv4 addresses"
4. Click "Allocate"
5. Associate with your EC2 instance

📝 WRITE DOWN YOUR ELASTIC IP: ___________________
```

## 2.4 Configure Security Groups

Ensure these ports are open:

| Port | Protocol | Source | Purpose |
|:-----|:---------|:-------|:--------|
| 443 | HTTPS | 0.0.0.0/0 | Web traffic |
| 80 | HTTP | 0.0.0.0/0 | Redirect to HTTPS |
| 22 | SSH | Your IP only | Admin access |
| 5432 | PostgreSQL | VPC only | Database |

## 2.5 Configure DNS Records

```
In Route 53, create these records:

Type: A
Name: forensicbridge.ca
Value: YOUR_ELASTIC_IP

Type: A
Name: app.forensicbridge.ca
Value: YOUR_ELASTIC_IP

Type: CNAME
Name: www.forensicbridge.ca
Value: forensicbridge.ca
```

---

# PHASE 3: Legal Pages

## 3.1 Privacy Policy

Create this page at: `https://forensicbridge.ca/privacy`

```html
<!-- See PRIVACY_POLICY.md for full content -->
```

**Key sections to include:**
- What data you collect (QB financial data, email, name)
- How you use it (migration only, not stored)
- Third parties (QuickBooks Online, AWS)
- Data retention (deleted after migration)
- User rights (GDPR/CCPA compliance)
- Contact information

## 3.2 End User License Agreement (EULA)

Create this page at: `https://forensicbridge.ca/eula`

**Key sections to include:**
- License grant (what users can do)
- Restrictions (what users cannot do)
- Data ownership (user owns their data)
- Liability limitations
- Termination clause
- Governing law (Canadian law)

## 3.3 Quick Setup with Static HTML

If you don't have a CMS, create simple HTML pages:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Privacy Policy - ForensicBridge</title>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p>Last updated: January 18, 2026</p>
    <!-- Your privacy policy content -->
</body>
</html>
```

Host in S3 bucket with CloudFront, or on your EC2 instance.

---

# PHASE 4: Intuit App Registration

## 4.1 Complete Registration Form

Go to: https://developer.intuit.com/app/developer/myapps

### Legal URLs
| Field | Value |
|:------|:------|
| End-user license agreement URL | `https://forensicbridge.ca/eula` |
| Privacy policy URL | `https://forensicbridge.ca/privacy` |

### OAuth URLs
| Field | Value |
|:------|:------|
| Host domain | `app.forensicbridge.ca` |
| Launch URL | `https://app.forensicbridge.ca/dashboard` |
| Disconnect URL | `https://app.forensicbridge.ca/api/qbo/disconnect` |

### Regulated Industries
| Industry | Answer |
|:---------|:-------|
| Insurance | ❌ No |
| Investment / financial planning | ❌ No |
| Lending | ❌ No |
| Payments / money movement | ❌ No |

### Categories (Select these 4)
- [x] Data Management
- [x] Accounting
- [x] Document Management
- [x] Legal and Regulatory Compliance

### IP Whitelisting
| Field | Value |
|:------|:------|
| Country | Canada |
| IP Address | YOUR_ELASTIC_IP (from Phase 2.3) |

## 4.2 Scopes to Request

Request these OAuth scopes:

| Scope | Purpose |
|:------|:--------|
| `com.intuit.quickbooks.accounting` | Read/write accounting data |
| `openid` | User authentication |
| `profile` | User name |
| `email` | User email |

## 4.3 Security Questionnaire

Intuit will ask about:

| Question | Your Answer |
|:---------|:------------|
| Do you store OAuth tokens? | Yes, encrypted with AES-256-GCM |
| Do you store financial data? | No, processed in memory only |
| Do you use HTTPS? | Yes, TLS 1.3 |
| Do you have audit logging? | Yes, all API calls logged |
| Data residency? | Canada (ca-central-1) |

---

# PHASE 5: Final Configuration

## 5.1 Set Environment Variables

On your EC2 instance, set these environment variables:

```bash
# Intuit OAuth (from developer.intuit.com)
export QBO_CLIENT_ID="your_production_client_id"
export QBO_CLIENT_SECRET="your_production_client_secret"
export QBO_REDIRECT_URI="https://app.forensicbridge.ca/api/qbo/callback"

# AWS
export AWS_REGION="ca-central-1"
export AWS_KMS_KEY_ID="alias/forensicbridge-cmk"

# Database
export DATABASE_URL="postgresql://user:pass@localhost/forensicbridge"

# Security
export SECRET_KEY="your_random_secret_key"
export ENCRYPTION_KEY="your_32_byte_encryption_key"
```

## 5.2 Test OAuth Flow

```
1. Go to https://app.forensicbridge.ca
2. Click "Connect to QuickBooks"
3. Login with Intuit sandbox account
4. Grant permissions
5. Verify redirect to dashboard
6. Verify token storage
```

## 5.3 Go Live Checklist

- [ ] Domain configured with SSL
- [ ] AWS stack deployed
- [ ] Elastic IP assigned and DNS updated
- [ ] Legal pages published
- [ ] Intuit production keys received
- [ ] Environment variables configured
- [ ] OAuth flow tested
- [ ] Desktop installer updated with production URLs

---

# Quick Reference

## Important URLs

| Purpose | URL |
|:--------|:----|
| **Your App** | https://app.forensicbridge.ca |
| **OAuth Callback** | https://app.forensicbridge.ca/api/qbo/callback |
| **Disconnect** | https://app.forensicbridge.ca/api/qbo/disconnect |
| **Privacy Policy** | https://forensicbridge.ca/privacy |
| **EULA** | https://forensicbridge.ca/eula |
| **Intuit Developer Portal** | https://developer.intuit.com |

## AWS Resources Created

| Resource | Purpose |
|:---------|:--------|
| EC2 Instance | Flask server |
| RDS PostgreSQL | User/migration database |
| S3 Bucket | File uploads |
| CloudWatch | Logging |
| KMS Key | Encryption |
| Elastic IP | Static IP for OAuth |

## Estimated Costs

| Service | Monthly Cost |
|:--------|:-------------|
| EC2 (t3.small) | ~$15 |
| RDS (db.t3.micro) | ~$15 |
| S3 | ~$5 |
| Elastic IP | ~$3.65 |
| Route 53 | ~$0.50 |
| **Total** | **~$40/month** |

---

*For support: support@forensicbridge.ca*
