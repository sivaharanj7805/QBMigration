# ForensicBridge QBExtractor - Complete Deployment Guide

This guide covers everything you need to build, deploy, and run the QBExtractor system end-to-end.

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Building the QBExtractor.exe](#3-building-the-qbextractorexe)
4. [Configuring the Backend Server](#4-configuring-the-backend-server)
5. [Configuring the Frontend Dashboard](#5-configuring-the-frontend-dashboard)
6. [Publishing the .exe for Distribution](#6-publishing-the-exe-for-distribution)
7. [Client Machine Setup](#7-client-machine-setup)
8. [Complete Workflow Test](#8-complete-workflow-test)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FORENSICBRIDGE ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   FRONTEND      │      │   BACKEND       │      │   STORAGE       │
│   (Next.js)     │◄────►│   (Flask)       │◄────►│   (AWS S3)      │
│                 │      │                 │      │                 │
│ - Dashboard     │      │ - REST APIs     │      │ - Encrypted     │
│ - Projects      │      │ - WebSocket     │      │   data files    │
│ - Progress UI   │      │ - Auth (JWT)    │      │                 │
└─────────────────┘      └─────────────────┘      └─────────────────┘
                                ▲
                                │ HTTPS
                                ▼
                    ┌─────────────────────────┐
                    │   QBEXTRACTOR.EXE       │
                    │   (Windows Client)      │
                    │                         │
                    │ - Runs on client PC     │
                    │ - Connects to QB Desktop│
                    │ - Extracts via QBFC SDK │
                    │ - Encrypts & uploads    │
                    └─────────────────────────┘
                                ▲
                                │ QBFC SDK (COM)
                                ▼
                    ┌─────────────────────────┐
                    │   QUICKBOOKS DESKTOP    │
                    │   (with .qbw file open) │
                    └─────────────────────────┘
```

---

## 2. Prerequisites

### 2.1 Development Machine (for building .exe)

| Requirement | Version | Notes |
|-------------|---------|-------|
| Windows | 10/11 | Required for .NET Framework |
| Visual Studio 2022 | 17.x | Or VS Build Tools |
| .NET Framework | 4.7.2+ | Target framework |
| .NET SDK | 6.0+ | For `dotnet build` |

### 2.2 Server Machine (for backend)

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.9+ | Flask backend |
| PostgreSQL | 13+ | Or MySQL 8+ |
| Node.js | 18+ | For Next.js frontend |
| Redis | 6+ | Optional, for caching |

### 2.3 Client Machine (end user)

| Requirement | Version | Notes |
|-------------|---------|-------|
| Windows | 10/11 | QuickBooks requirement |
| QuickBooks Desktop | 2018+ | Pro, Premier, or Enterprise |
| QBFC16 SDK | Latest | **CRITICAL** - See Section 7 |
| .NET Framework | 4.7.2+ | Usually pre-installed |

---

## 3. Building the QBExtractor.exe

### 3.1 Clone the Repository

```bash
git clone https://github.com/sivaharanj7805/QBMigration.git
cd QBMigration/QBDesktopReader
```

### 3.2 Install QBFC16 SDK (Build Dependency)

The project references `QBFC16Lib` which is a COM library. You need to:

1. **Download QuickBooks Desktop SDK:**
   - Go to: https://developer.intuit.com/app/developer/qbdesktop/docs/get-started
   - Create free Intuit Developer account
   - Download "QuickBooks Desktop SDK" (includes QBFC16)

2. **Install the SDK:**
   - Run the installer
   - This registers `QBFC16Lib.dll` as a COM object

3. **Verify installation:**
   ```powershell
   # Check if QBFC16 is registered
   reg query "HKCR\TypeLib" /s | findstr "QBFC"
   ```

### 3.3 Update Configuration

Edit `config.json` with your production server URL:

```json
{
  "$comment": "QuickBooks Extractor v4.3 Configuration",
  "serverUrl": "https://api.yourserver.com",
  "incrementalSyncFromDate": null,
  "version": "4.3",
  "schemaVersion": "4.3",
  "advanced": {
    "chunkSizeKB": 1024,
    "chunkedUploadThresholdMB": 10,
    "secureDeletePasses": 3,
    "initialBatchSize": 100,
    "enableAdaptiveBatching": true,
    "enablePreFlightCheck": true,
    "enableForensicHashing": true,
    "minimumServerVersion": "4.0",
    "enableVersionCheck": true,
    "maxFileStreamSizeMB": 2048,
    "enableLogRedaction": true,
    "logLevel": "INFO",
    "retryAttempts": 3,
    "retryDelayMs": 1000,
    "retryMaxDelayMs": 30000,
    "retryJitterPercent": 20,
    "enableExponentialBackoff": true,
    "allowInsecureHttpForLocalhost": true,
    "maxQBXMLVersion": null
  }
}
```

### 3.4 Update API URLs in Code

Edit `SessionValidator.cs` (line 39) and `LicenseValidator.cs` (line 39):

```csharp
// SessionValidator.cs - Change default URL
SESSION_API_URL = envUrl ?? "https://api.yourserver.com/api/session";

// LicenseValidator.cs - Change default URL
LICENSE_API_URL = envUrl ?? "https://api.yourserver.com/api/license";
```

Edit `ExtractionConfig.cs` (lines 15-16):

```csharp
public static class KnownUrls
{
    public const string ForensicBridge = "https://yourserver.com";
    public const string ForensicBridgeNewProject = "https://yourserver.com/projects/new";
    // ... rest unchanged
}
```

### 3.5 Build with Visual Studio

1. Open `QBDesktopReader.sln` in Visual Studio 2022
2. Set configuration to **Release** and platform to **Any CPU**
3. Build → Build Solution (Ctrl+Shift+B)
4. Output: `bin/Release/net472/QBExtractor.exe`

### 3.6 Build with Command Line

```powershell
cd QBDesktopReader

# Restore NuGet packages
dotnet restore

# Build Release version
dotnet build -c Release

# Or use MSBuild directly
msbuild QBDesktopReader.csproj /p:Configuration=Release /p:Platform="Any CPU"
```

### 3.7 Verify Build Output

```powershell
# Check the output
dir bin\Release\net472\

# Expected files:
# - QBExtractor.exe          (main executable)
# - QBExtractor.exe.config   (config)
# - Newtonsoft.Json.dll      (JSON library)
# - config.json              (runtime config)
```

### 3.8 Create Distribution Package

Create a folder with all required files:

```powershell
mkdir QBExtractor-v4.3
copy bin\Release\net472\QBExtractor.exe QBExtractor-v4.3\
copy bin\Release\net472\QBExtractor.exe.config QBExtractor-v4.3\
copy bin\Release\net472\Newtonsoft.Json.dll QBExtractor-v4.3\
copy config.json QBExtractor-v4.3\

# Create ZIP for distribution
Compress-Archive -Path QBExtractor-v4.3\* -DestinationPath QBExtractor-v4.3.zip
```

---

## 4. Configuring the Backend Server

### 4.1 Set Up Python Environment

```bash
cd QBMigrationServer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 4.2 Create Environment Variables

Create `.env` file:

```bash
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=your-super-secret-key-change-this-in-production

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/forensicbridge
# Or for MySQL:
# DATABASE_URL=mysql+pymysql://user:password@localhost:3306/forensicbridge

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_REGION=us-east-1
S3_BUCKET_NAME=forensicbridge-migrations

# Optional: Redis for caching
REDIS_URL=redis://localhost:6379/0

# Optional: Sentry for error tracking
SENTRY_DSN=https://your-sentry-dsn

# Rate Limiting
RATELIMIT_STORAGE_URL=redis://localhost:6379/1

# GitHub token for extractor downloads (optional but recommended)
GITHUB_TOKEN=ghp_your_github_token
```

### 4.3 Initialize Database

```bash
# Create database
createdb forensicbridge  # PostgreSQL

# Run migrations
flask db upgrade

# Or create tables directly
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

### 4.4 Create S3 Bucket

```bash
# Using AWS CLI
aws s3 mb s3://forensicbridge-migrations --region us-east-1

# Set bucket policy for server access only
aws s3api put-bucket-policy --bucket forensicbridge-migrations --policy '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::YOUR_ACCOUNT:user/forensicbridge-server"},
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::forensicbridge-migrations/*"
    }
  ]
}'
```

### 4.5 Place the QBExtractor.exe on Server

The server can serve the .exe directly if placed in the static directory:

```bash
mkdir -p static/extractor
cp /path/to/QBExtractor.exe static/extractor/
```

### 4.6 Run the Server

**Development:**
```bash
flask run --host=0.0.0.0 --port=5000
```

**Production (with Gunicorn + Eventlet for WebSocket):**
```bash
pip install gunicorn eventlet

gunicorn -k eventlet -w 1 -b 0.0.0.0:5000 --timeout 120 app:app
```

**Production with systemd:**

Create `/etc/systemd/system/forensicbridge.service`:
```ini
[Unit]
Description=ForensicBridge API Server
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/forensicbridge/QBMigrationServer
Environment="PATH=/var/www/forensicbridge/venv/bin"
EnvironmentFile=/var/www/forensicbridge/.env
ExecStart=/var/www/forensicbridge/venv/bin/gunicorn -k eventlet -w 1 -b 127.0.0.1:5000 --timeout 120 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable forensicbridge
sudo systemctl start forensicbridge
```

### 4.7 Configure Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name api.yourserver.com;

    ssl_certificate /etc/letsencrypt/live/api.yourserver.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourserver.com/privkey.pem;

    # WebSocket support
    location /socket.io {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API endpoints
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # For large file uploads
        client_max_body_size 100M;
        proxy_read_timeout 300s;
    }
}
```

---

## 5. Configuring the Frontend Dashboard

### 5.1 Install Dependencies

```bash
cd forensicbridge-dashboard
npm install
```

### 5.2 Configure Environment

Create `.env.local`:

```bash
# API Server URL
NEXT_PUBLIC_API_URL=https://api.yourserver.com

# WebSocket URL (same as API for Socket.IO)
NEXT_PUBLIC_WS_URL=https://api.yourserver.com

# Optional: Analytics
NEXT_PUBLIC_GA_ID=G-XXXXXXXXXX
```

### 5.3 Build for Production

```bash
npm run build
```

### 5.4 Run Production Server

```bash
npm start
# Runs on port 3000 by default
```

### 5.5 Deploy with PM2

```bash
npm install -g pm2

pm2 start npm --name "forensicbridge-dashboard" -- start
pm2 save
pm2 startup
```

### 5.6 Configure Nginx for Frontend

```nginx
server {
    listen 443 ssl http2;
    server_name yourserver.com www.yourserver.com;

    ssl_certificate /etc/letsencrypt/live/yourserver.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourserver.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

---

## 6. Publishing the .exe for Distribution

### 6.1 Option A: GitHub Releases (Recommended)

The server automatically downloads from GitHub releases. Create a release:

```bash
# Tag the release
git tag -a v4.3.0 -m "QBExtractor v4.3.0"
git push origin v4.3.0

# Create release on GitHub
# 1. Go to https://github.com/sivaharanj7805/QBMigration/releases
# 2. Click "Create new release"
# 3. Select tag v4.3.0
# 4. Upload QBExtractor.exe as release asset
# 5. Publish release
```

The server's `/api/extractor/download` endpoint will:
1. Check for local .exe
2. Check cache
3. Download from GitHub release and cache
4. Serve to user

### 6.2 Option B: Direct Server Hosting

Place the .exe directly on your server:

```bash
# On server
mkdir -p /var/www/forensicbridge/QBMigrationServer/static/extractor
cp QBExtractor.exe /var/www/forensicbridge/QBMigrationServer/static/extractor/
```

The server will find it automatically via `find_extractor_path()`.

### 6.3 Option C: Bootstrap Installer

The server can generate a bootstrap `.bat` file that downloads the .exe:

Create `static/extractor/ForensicBridge_Install.bat`:

```batch
@echo off
title ForensicBridge Extractor Installer
color 1F

echo.
echo ============================================================
echo   ForensicBridge Extractor Installer
echo ============================================================
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\ForensicBridge"
set "DOWNLOAD_URL=https://github.com/sivaharanj7805/QBMigration/releases/latest/download/QBExtractor.exe"
set "EXTRACTOR=%INSTALL_DIR%\QBExtractor.exe"

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo Downloading ForensicBridge Extractor...
echo.

powershell -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
    "Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%EXTRACTOR%' -UseBasicParsing"

if exist "%EXTRACTOR%" (
    echo.
    echo Download complete!
    echo Starting ForensicBridge Extractor...
    start "" "%EXTRACTOR%"
) else (
    echo.
    echo Download failed. Please try again or download manually from:
    echo https://github.com/sivaharanj7805/QBMigration/releases
)

echo.
pause
```

---

## 7. Client Machine Setup

### 7.1 Install QuickBooks Desktop SDK (CRITICAL)

**This is the most important step.** The QBExtractor cannot work without the SDK.

#### Option A: QBFC16 SDK (Recommended)

1. **Create Intuit Developer Account:**
   - Go to: https://developer.intuit.com
   - Sign up for free account

2. **Download SDK:**
   - Go to: https://developer.intuit.com/app/developer/qbdesktop/docs/get-started/download-and-install-the-sdk
   - Download "QuickBooks Desktop SDK"
   - File: `QBSDK13.0.exe` (or latest version)

3. **Install SDK:**
   ```
   - Run the installer as Administrator
   - Accept license agreement
   - Install to default location
   - Complete installation
   ```

4. **Verify Installation:**
   ```powershell
   # Check for QBFC16 registration
   reg query "HKCR\QBFC16.QBSessionManager" /ve

   # Should return:
   # (Default)    REG_SZ    QBFC16.QBSessionManager
   ```

#### Option B: QODBC Driver (Fallback)

If QBFC SDK installation is problematic, QODBC works as a fallback:

1. Download from: https://qodbc.com/qodbc-downloads/
2. Install QODBC Read-Only (free for read operations)
3. The extractor will auto-detect and use QODBC

### 7.2 Install .NET Framework 4.7.2

Usually pre-installed on Windows 10/11, but verify:

```powershell
# Check .NET Framework version
reg query "HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" /v Release

# Value >= 461808 means 4.7.2+
```

If missing, download from: https://dotnet.microsoft.com/download/dotnet-framework/net472

### 7.3 Download QBExtractor

Users download from the dashboard after creating a project, or directly:

```
https://yourserver.com/api/extractor/download
```

### 7.4 Run QBExtractor

1. **Open QuickBooks Desktop** with company file (.qbw)
2. **Run QBExtractor.exe**
3. **Enter Session ID** when prompted (from dashboard)
4. **Authorize in QuickBooks** - Click "Yes, always allow" when QuickBooks asks

---

## 8. Complete Workflow Test

### 8.1 Create Test User

```bash
# Via Flask shell
cd QBMigrationServer
flask shell

>>> from models import User, db
>>> user = User(email='test@example.com', name='Test User')
>>> user.set_password('testpass123')
>>> db.session.add(user)
>>> db.session.commit()
>>> print(f"User ID: {user.id}")
```

### 8.2 Test API Endpoints

```bash
# Health check
curl https://api.yourserver.com/health

# Login
curl -X POST https://api.yourserver.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}'

# Response: {"token": "eyJ..."}

# Create project
TOKEN="eyJ..."
curl -X POST https://api.yourserver.com/api/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Project","client_name":"Test Client"}'

# Response: {"project": {"session_id": "FB-20260127153045-ABC12345"}}

# Check extractor availability
curl https://api.yourserver.com/api/extractor/status
```

### 8.3 Test Extractor Download

```bash
# Download extractor
curl -O https://api.yourserver.com/api/extractor/download

# Should download QBExtractor.exe or ForensicBridge_Install.bat
```

### 8.4 Test Full Extraction (on Windows)

1. Open QuickBooks Desktop with a sample company file
2. Run QBExtractor.exe
3. Enter session ID from step 8.2
4. Approve in QuickBooks when prompted
5. Watch extraction progress
6. Verify upload completes

### 8.5 Verify in Dashboard

1. Login to dashboard
2. Go to project
3. Should see migration with status "uploaded" or "processing"
4. Check real-time WebSocket updates

---

## 9. Troubleshooting

### 9.1 "No QuickBooks extraction backend available"

**Cause:** QBFC SDK not installed

**Solution:**
```
1. Download SDK from https://developer.intuit.com
2. Install as Administrator
3. Restart computer
4. Run QBExtractor again
```

### 9.2 "QuickBooks connection failed"

**Cause:** QuickBooks not running or access denied

**Solution:**
```
1. Ensure QuickBooks Desktop is running
2. Ensure a company file is open
3. Run QBExtractor as Administrator
4. When QB prompts, click "Yes, always allow"
5. Check QB Edit menu → Preferences → Integrated Applications
```

### 9.3 "Session validation failed"

**Cause:** Invalid session ID or server unreachable

**Solution:**
```
1. Copy session ID exactly from dashboard
2. Check internet connection
3. Verify server is running: curl https://api.yourserver.com/health
4. Check config.json serverUrl is correct
```

### 9.4 "Upload failed"

**Cause:** Network issue or server error

**Solution:**
```
1. Check internet connection
2. Check server logs: tail -f /var/log/forensicbridge/app.log
3. Verify S3 credentials are correct
4. Check file size (max 100MB default)
```

### 9.5 "License validation failed"

**Cause:** No license or expired license

**Solution:**
```
1. Check if license API is configured
2. For testing, you can bypass:
   - Set environment variable: SKIP_LICENSE_CHECK=true
   - Or modify LicenseValidator.cs to return success
```

### 9.6 COM Exception / STA Thread Error

**Cause:** Thread apartment state issue

**Solution:**
```
1. Ensure running on Windows (not Wine/Mono)
2. The extractor handles STA threading internally
3. Check Windows Event Viewer for COM errors
4. Reinstall QBFC SDK
```

### 9.7 WebSocket Not Connecting

**Cause:** Nginx not configured for WebSocket

**Solution:**
```nginx
# Add to Nginx config:
location /socket.io {
    proxy_pass http://127.0.0.1:5000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## 10. Security Checklist

Before going to production:

- [ ] Change `SECRET_KEY` in .env
- [ ] Enable HTTPS on all endpoints
- [ ] Configure proper CORS origins
- [ ] Set up rate limiting
- [ ] Enable database SSL
- [ ] Configure S3 bucket policies
- [ ] Set up log rotation
- [ ] Enable Sentry error tracking
- [ ] Review firewall rules
- [ ] Test backup/restore procedures

---

## 11. Quick Reference

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | User login |
| `/api/projects` | POST | Create project |
| `/api/projects` | GET | List projects |
| `/api/extractor/download` | GET | Download .exe |
| `/api/session/validate` | POST | Validate session |
| `/api/session/activate` | POST | Activate device |
| `/api/upload` | POST | Upload data |
| `/api/migrations` | GET | List migrations |

### Exit Codes (QBExtractor.exe)

| Code | Meaning |
|------|---------|
| 0 | Success |
| 10 | Configuration error |
| 15 | License invalid |
| 20 | No backend (SDK not installed) |
| 30 | QuickBooks connection failed |
| 40 | Extraction failed |
| 50 | Upload failed |
| 60 | Cancelled by user |
| 99 | Unknown error |

### Command Line Options

```
QBExtractor.exe [options]

Required:
  --session, -s <code>    Session code from dashboard

Options:
  --config, -c <path>     Path to config.json
  --license, -l <key>     License key
  --no-pause              Don't wait for keypress
  --quiet, -q             Minimal output
  --verbose, -v           Debug output
  --ndjson                NDJSON output mode
  --extract-only          Don't upload, save locally
  --show-backends         Show available backends
  --help, -h              Show help
```

---

## Need Help?

- GitHub Issues: https://github.com/sivaharanj7805/QBMigration/issues
- Documentation: Check `/docs` folder in repository
