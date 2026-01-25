# ForensicBridge Production Setup Guide

**Complete step-by-step instructions to run ForensicBridge in production.**

> This guide is based on the actual codebase. Follow each step exactly.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [System Requirements](#2-system-requirements)
3. [Step 1: Clone and Setup](#step-1-clone-and-setup)
4. [Step 2: PostgreSQL Database](#step-2-postgresql-database)
5. [Step 3: Redis Setup](#step-3-redis-setup)
6. [Step 4: Backend Configuration](#step-4-backend-configuration)
7. [Step 5: AWS Configuration](#step-5-aws-configuration)
8. [Step 6: QuickBooks Online Setup](#step-6-quickbooks-online-setup)
9. [Step 7: Initialize Database](#step-7-initialize-database)
10. [Step 8: Start Backend Server](#step-8-start-backend-server)
11. [Step 9: Start Celery Workers](#step-9-start-celery-workers)
12. [Step 10: Frontend Configuration](#step-10-frontend-configuration)
13. [Step 11: Build and Start Frontend](#step-11-build-and-start-frontend)
14. [Step 12: Nginx Reverse Proxy](#step-12-nginx-reverse-proxy)
15. [Step 13: SSL Certificate](#step-13-ssl-certificate)
16. [Step 14: Systemd Services](#step-14-systemd-services)
17. [Step 15: Verification](#step-15-verification)
18. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

You need:
- Ubuntu 22.04 LTS server (or similar Linux)
- Root/sudo access
- Domain name pointing to your server
- AWS account with access keys or IAM role
- QuickBooks Developer account (for QBO integration)

---

## 2. System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Storage | 50 GB SSD | 100 GB SSD |
| OS | Ubuntu 22.04 | Ubuntu 22.04 |

---

## Step 1: Clone and Setup

### 1.1 Install System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    nodejs \
    npm \
    nginx \
    postgresql \
    postgresql-contrib \
    redis-server \
    git \
    certbot \
    python3-certbot-nginx
```

### 1.2 Install Node.js 20+ (if not already 20+)

```bash
# Check Node version
node --version

# If below v20, install Node 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### 1.3 Clone the Repository

```bash
# Clone to /opt (or your preferred location)
cd /opt
sudo git clone <your-repo-url> QBMigration
sudo chown -R $USER:$USER QBMigration
cd QBMigration
```

---

## Step 2: PostgreSQL Database

### 2.1 Start PostgreSQL

```bash
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 2.2 Create Database and User

```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL shell, run these commands:
```

```sql
-- Create the database
CREATE DATABASE qbmigration;

-- Create the user (CHANGE THE PASSWORD!)
CREATE USER forensicbridge WITH PASSWORD 'YOUR_STRONG_PASSWORD_HERE';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE qbmigration TO forensicbridge;

-- Connect to the database and grant schema permissions
\c qbmigration
GRANT ALL ON SCHEMA public TO forensicbridge;

-- Exit
\q
```

### 2.3 Test Database Connection

```bash
psql -h localhost -U forensicbridge -d qbmigration -c "SELECT 1;"
# Enter password when prompted - should return "1"
```

---

## Step 3: Redis Setup

### 3.1 Start Redis

```bash
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### 3.2 Verify Redis

```bash
redis-cli ping
# Should return: PONG
```

### 3.3 (Optional) Set Redis Password

```bash
# Edit Redis config
sudo nano /etc/redis/redis.conf

# Find and uncomment/set:
requirepass YOUR_REDIS_PASSWORD

# Restart Redis
sudo systemctl restart redis-server
```

---

## Step 4: Backend Configuration

### 4.1 Create Python Virtual Environment

```bash
cd /opt/QBMigration/QBMigrationServer
python3.11 -m venv venv
source venv/bin/activate
```

### 4.2 Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4.3 Create Environment File

```bash
# Copy template
cp .env.example .env

# Edit with your values
nano .env
```

### 4.4 Configure .env File

**Replace ALL placeholder values with your actual values:**

```bash
# ============================================================================
# FLASK CONFIGURATION (REQUIRED)
# ============================================================================
FLASK_ENV=production
DEBUG=false

# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=PASTE_YOUR_GENERATED_SECRET_HERE

# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
WEBHOOK_SECRET=PASTE_YOUR_GENERATED_WEBHOOK_SECRET_HERE

# Your domain (EC2 instances call back to this URL)
SERVER_URL=https://yourdomain.com

# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
BACKUP_ENCRYPTION_KEY=PASTE_YOUR_FERNET_KEY_HERE

# ============================================================================
# DATABASE (REQUIRED)
# ============================================================================
DATABASE_URL=postgresql://forensicbridge:YOUR_DB_PASSWORD@localhost:5432/qbmigration

# ============================================================================
# REDIS (REQUIRED)
# ============================================================================
REDIS_URL=redis://localhost:6379/0
# If Redis has password: redis://:YOUR_REDIS_PASSWORD@localhost:6379/0

# ============================================================================
# AWS CONFIGURATION (REQUIRED)
# ============================================================================
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=ca-central-1

# S3 Bucket (create this in AWS Console)
AWS_S3_BUCKET=your-forensicbridge-bucket

# EC2 Configuration (for migration processing)
AWS_EC2_AMI_ID=ami-xxxxxxxxxxxxxxxxx
AWS_EC2_INSTANCE_TYPE=t3.medium
AWS_EC2_KEY_NAME=your-key-pair-name
AWS_EC2_SECURITY_GROUP=sg-xxxxxxxxxxxxxxxxx
AWS_EC2_SUBNET_ID=subnet-xxxxxxxxxxxxxxxxx
AWS_IAM_INSTANCE_PROFILE=QB-Migration-Instance-Role

# ============================================================================
# QUICKBOOKS ONLINE (REQUIRED FOR QBO MIGRATIONS)
# ============================================================================
QBO_CLIENT_ID=your-qbo-client-id
QBO_CLIENT_SECRET=your-qbo-client-secret
QBO_ENVIRONMENT=production
QBO_REDIRECT_URI=https://yourdomain.com/api/qbo/callback

# ============================================================================
# MONITORING (RECOMMENDED)
# ============================================================================
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project

# ============================================================================
# SECURITY SETTINGS
# ============================================================================
MAX_LOGIN_ATTEMPTS=5
ACCOUNT_LOCKOUT_MINUTES=15
SESSION_TIMEOUT_HOURS=24

# ============================================================================
# CLEANUP SETTINGS
# ============================================================================
AUTO_CLEANUP_ENABLED=true
CLEANUP_CHECK_INTERVAL_MINUTES=15
```

### 4.5 Generate Required Keys

Run these commands and paste the output into your .env file:

```bash
# Generate SECRET_KEY
python -c "import secrets; print('SECRET_KEY:', secrets.token_urlsafe(32))"

# Generate WEBHOOK_SECRET
python -c "import secrets; print('WEBHOOK_SECRET:', secrets.token_hex(32))"

# Generate BACKUP_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print('BACKUP_ENCRYPTION_KEY:', Fernet.generate_key().decode())"
```

---

## Step 5: AWS Configuration

### 5.1 Create S3 Bucket

```bash
# Using AWS CLI (install if needed: pip install awscli)
aws s3 mb s3://your-forensicbridge-bucket --region ca-central-1

# Enable versioning
aws s3api put-bucket-versioning \
    --bucket your-forensicbridge-bucket \
    --versioning-configuration Status=Enabled

# Block public access
aws s3api put-public-access-block \
    --bucket your-forensicbridge-bucket \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Enable encryption
aws s3api put-bucket-encryption \
    --bucket your-forensicbridge-bucket \
    --server-side-encryption-configuration \
    '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}'
```

### 5.2 Create IAM Role for EC2 (Migration Workers)

Create a role named `QB-Migration-Instance-Role` with these permissions:
- S3 read/write to your bucket
- Secrets Manager read access
- CloudWatch Logs write access

### 5.3 Create Security Group

Create security group allowing:
- Inbound: SSH (22) from your IP, HTTPS (443) from anywhere
- Outbound: All traffic

---

## Step 6: QuickBooks Online Setup

### 6.1 Create Intuit Developer Account

1. Go to https://developer.intuit.com
2. Sign up / Log in
3. Create a new app
4. Select "QuickBooks Online and Payments"

### 6.2 Get OAuth Credentials

1. Go to your app dashboard
2. Navigate to "Keys & OAuth"
3. Copy:
   - **Client ID** → `QBO_CLIENT_ID`
   - **Client Secret** → `QBO_CLIENT_SECRET`

### 6.3 Set Redirect URI

Add this redirect URI in your Intuit app settings:
```
https://yourdomain.com/api/qbo/callback
```

### 6.4 Switch to Production (When Ready)

1. Complete Intuit's production checklist
2. Change `QBO_ENVIRONMENT=production` in .env
3. Use production Client ID/Secret

---

## Step 7: Initialize Database

### 7.1 Run Database Initialization

```bash
cd /opt/QBMigration/QBMigrationServer
source venv/bin/activate

# Initialize tables
python init_database.py
```

**Expected output:**
```
============================================================
ForensicBridge Database Initialization
============================================================

1. Creating all database tables...
   [OK] Tables created successfully

2. Checking for missing columns...
   [--] Column exists: subscription_tier
   [--] Column exists: migrations_purchased
   ...

3. Verifying tables...
   [OK] Table exists: users
   [OK] Table exists: migrations
   [OK] Table exists: licenses

4. Current database stats:
   - Users: 0
   - Migrations: 0

============================================================
Database initialization complete!
============================================================
```

### 7.2 Run Migrations (If Needed)

```bash
python scripts/migrate_database.py
```

---

## Step 8: Start Backend Server

### 8.1 Test Run (Verify Everything Works)

```bash
cd /opt/QBMigration/QBMigrationServer
source venv/bin/activate

# Test with Flask development server first
python run.py
```

You should see:
```
================================================================================
QB MIGRATION SERVER - DEVELOPMENT MODE
================================================================================

Server starting at: http://localhost:5000

Press CTRL+C to stop
================================================================================
```

Press Ctrl+C to stop.

### 8.2 Production Run with Gunicorn

```bash
# Start Gunicorn (production server)
gunicorn \
    --workers 4 \
    --worker-class gevent \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --access-logfile /var/log/forensicbridge/access.log \
    --error-logfile /var/log/forensicbridge/error.log \
    "app:app"
```

### 8.3 Create Log Directory

```bash
sudo mkdir -p /var/log/forensicbridge
sudo chown $USER:$USER /var/log/forensicbridge
```

---

## Step 9: Start Celery Workers

### 9.1 Start Celery Worker

Open a new terminal:

```bash
cd /opt/QBMigration/QBMigrationServer
source venv/bin/activate

celery -A tasks worker \
    --loglevel=info \
    --concurrency=4 \
    -P gevent
```

---

## Step 10: Frontend Configuration

### 10.1 Install Node Dependencies

```bash
cd /opt/QBMigration/forensicbridge-dashboard
npm install
```

### 10.2 Create Frontend Environment File

```bash
nano .env.local
```

Add:
```bash
# API URL - points to your backend
NEXT_PUBLIC_API_URL=https://yourdomain.com
```

---

## Step 11: Build and Start Frontend

### 11.1 Build Production Bundle

```bash
cd /opt/QBMigration/forensicbridge-dashboard

# Build
npm run build
```

**Expected output:**
```
✓ Compiled successfully
✓ Collecting page data
✓ Generating static pages
...
```

### 11.2 Start Frontend Server

```bash
# Start on port 3000
npm start
```

Or with custom port:
```bash
PORT=3001 npm start
```

---

## Step 12: Nginx Reverse Proxy

### 12.1 Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/forensicbridge
```

Paste this configuration:

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# Main HTTPS server
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL certificates (will be configured by Certbot)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Increase upload size for QB files
    client_max_body_size 100M;

    # API routes → Backend (Gunicorn on port 8000)
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # WebSocket support
    location /socket.io {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # Frontend → Next.js (port 3000)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 12.2 Enable Site

```bash
# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Enable ForensicBridge
sudo ln -s /etc/nginx/sites-available/forensicbridge /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# If test passes, reload
sudo systemctl reload nginx
```

---

## Step 13: SSL Certificate

### 13.1 Get Let's Encrypt Certificate

```bash
# Get certificate (before running, ensure domain points to server)
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### 13.2 Auto-Renewal (Already Set Up by Certbot)

Verify auto-renewal:
```bash
sudo certbot renew --dry-run
```

---

## Step 14: Systemd Services

### 14.1 Create Backend Service

```bash
sudo nano /etc/systemd/system/forensicbridge.service
```

Paste:

```ini
[Unit]
Description=ForensicBridge API Server
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/QBMigration/QBMigrationServer
Environment="PATH=/opt/QBMigration/QBMigrationServer/venv/bin"
EnvironmentFile=/opt/QBMigration/QBMigrationServer/.env
ExecStart=/opt/QBMigration/QBMigrationServer/venv/bin/gunicorn \
    --workers 4 \
    --worker-class gevent \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile /var/log/forensicbridge/access.log \
    --error-logfile /var/log/forensicbridge/error.log \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 14.2 Create Celery Service

```bash
sudo nano /etc/systemd/system/forensicbridge-celery.service
```

Paste:

```ini
[Unit]
Description=ForensicBridge Celery Worker
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/QBMigration/QBMigrationServer
Environment="PATH=/opt/QBMigration/QBMigrationServer/venv/bin"
EnvironmentFile=/opt/QBMigration/QBMigrationServer/.env
ExecStart=/opt/QBMigration/QBMigrationServer/venv/bin/celery \
    -A tasks worker \
    --loglevel=info \
    --concurrency=4 \
    -P gevent
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 14.3 Create Frontend Service

```bash
sudo nano /etc/systemd/system/forensicbridge-frontend.service
```

Paste:

```ini
[Unit]
Description=ForensicBridge Frontend (Next.js)
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/QBMigration/forensicbridge-dashboard
Environment="NODE_ENV=production"
Environment="NEXT_PUBLIC_API_URL=https://yourdomain.com"
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 14.4 Enable and Start All Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services (start on boot)
sudo systemctl enable forensicbridge
sudo systemctl enable forensicbridge-celery
sudo systemctl enable forensicbridge-frontend

# Start services
sudo systemctl start forensicbridge
sudo systemctl start forensicbridge-celery
sudo systemctl start forensicbridge-frontend

# Check status
sudo systemctl status forensicbridge
sudo systemctl status forensicbridge-celery
sudo systemctl status forensicbridge-frontend
```

---

## Step 15: Verification

### 15.1 Check All Services Running

```bash
# Backend API
curl -s http://localhost:8000/health | jq .

# Expected: {"status": "healthy", ...}

# Frontend
curl -s http://localhost:3000 | head -20
# Should return HTML

# Full stack via Nginx
curl -s https://yourdomain.com/health | jq .
```

### 15.2 Test Full Flow

1. Open `https://yourdomain.com` in browser
2. Register a new account
3. Verify email (if enabled)
4. Login
5. Check dashboard loads correctly

### 15.3 Check Logs

```bash
# Backend logs
sudo journalctl -u forensicbridge -f

# Celery logs
sudo journalctl -u forensicbridge-celery -f

# Frontend logs
sudo journalctl -u forensicbridge-frontend -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

---

## Troubleshooting

### Database Connection Failed

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection string
psql -h localhost -U forensicbridge -d qbmigration

# Check .env DATABASE_URL format
```

### Redis Connection Failed

```bash
# Check Redis is running
sudo systemctl status redis-server

# Test connection
redis-cli ping

# If password required
redis-cli -a YOUR_PASSWORD ping
```

### Backend Won't Start

```bash
# Check logs
sudo journalctl -u forensicbridge -n 100

# Common issues:
# - Missing .env values
# - Wrong DATABASE_URL
# - Port already in use

# Test manually
cd /opt/QBMigration/QBMigrationServer
source venv/bin/activate
python run.py
```

### Frontend Build Failed

```bash
# Check Node version (need 20+)
node --version

# Clear cache and rebuild
cd /opt/QBMigration/forensicbridge-dashboard
rm -rf node_modules .next
npm install
npm run build
```

### Nginx 502 Bad Gateway

```bash
# Check backend is running
curl http://localhost:8000/health

# Check nginx config
sudo nginx -t

# Check nginx error log
sudo tail -f /var/log/nginx/error.log
```

### SSL Certificate Issues

```bash
# Renew certificate
sudo certbot renew

# Check certificate status
sudo certbot certificates
```

---

## Quick Reference Commands

```bash
# Start all services
sudo systemctl start forensicbridge forensicbridge-celery forensicbridge-frontend

# Stop all services
sudo systemctl stop forensicbridge forensicbridge-celery forensicbridge-frontend

# Restart all services
sudo systemctl restart forensicbridge forensicbridge-celery forensicbridge-frontend

# View logs
sudo journalctl -u forensicbridge -f

# Check health
curl https://yourdomain.com/health

# Database backup
pg_dump -U forensicbridge qbmigration > backup.sql
```

---

## Production Checklist

Before going live, verify:

- [ ] All .env values are production values (not defaults)
- [ ] SECRET_KEY is unique and secure (32+ characters)
- [ ] DATABASE_URL uses strong password
- [ ] AWS credentials have minimal required permissions
- [ ] SSL certificate is installed and auto-renews
- [ ] All services start on boot (systemd enabled)
- [ ] Logs are being written
- [ ] Health check returns healthy
- [ ] Firewall allows only 80, 443, 22
- [ ] Regular backups configured
- [ ] Monitoring (Sentry) configured

---

**Document Generated**: January 25, 2026
**Based on Codebase Version**: Current HEAD
