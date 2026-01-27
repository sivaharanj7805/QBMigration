# ForensicBridge QBExtractor - Complete Deployment Guide

This guide covers everything you need to build, deploy, and run the QBExtractor system end-to-end.

> **IMPORTANT UPDATE (2025):** The official Intuit QuickBooks Desktop SDK (QBFC) is **no longer available for download** from Intuit. This guide uses **QODBC Driver** as the primary solution, which is fully supported and actively maintained.

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Understanding How QBExtractor Works](#2-understanding-how-qbextractor-works)
3. [Prerequisites](#3-prerequisites)
4. [Installing QODBC Driver](#4-installing-qodbc-driver)
5. [Building the QBExtractor.exe](#5-building-the-qbextractorexe)
6. [Configuring the Backend Server](#6-configuring-the-backend-server)
7. [Configuring the Frontend Dashboard](#7-configuring-the-frontend-dashboard)
8. [Publishing the .exe for Distribution](#8-publishing-the-exe-for-distribution)
9. [Client Machine Setup](#9-client-machine-setup)
10. [Complete Workflow Test](#10-complete-workflow-test)
11. [Troubleshooting](#11-troubleshooting)

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
                    │ - Connects via QODBC    │
                    │ - Extracts via SQL/ODBC │
                    │ - Encrypts & uploads    │
                    └─────────────────────────┘
                                ▲
                                │ ODBC Connection
                                ▼
                    ┌─────────────────────────┐
                    │   QUICKBOOKS DESKTOP    │
                    │   (with .qbw file open) │
                    └─────────────────────────┘
```

---

## 2. Understanding How QBExtractor Works

### CRITICAL: The .exe Does NOT Read .qbw Files Directly

The QBExtractor.exe **does NOT** parse or read .qbw files directly. Here's why:

1. **.qbw files are encrypted** with proprietary Intuit encryption
2. **.qbw files have no public specification** - the format is undocumented
3. **Direct file access is not supported** by Intuit

### How Extraction Actually Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTRACTION FLOW                                      │
└─────────────────────────────────────────────────────────────────────────────┘

  1. User opens QuickBooks Desktop with company file (.qbw)
                    │
                    ▼
  2. QBExtractor.exe runs and detects available backend:
     ┌─────────────────────────────────────────────────────┐
     │  BACKEND OPTIONS (in priority order):               │
     │                                                     │
     │  [1] QBFC SDK (if installed from old QB version)   │
     │      └─ COM/ActiveX interface                       │
     │      └─ Uses QBXML messages                         │
     │                                                     │
     │  [2] QODBC Driver (PRIMARY - always available)     │ ◄── RECOMMENDED
     │      └─ ODBC interface                              │
     │      └─ Uses SQL queries                            │
     │      └─ Free for read-only operations               │
     └─────────────────────────────────────────────────────┘
                    │
                    ▼
  3. Backend connects to QuickBooks application (NOT the file)
     - QuickBooks MUST be running
     - Company file MUST be open
     - User MUST authorize the connection
                    │
                    ▼
  4. Extract data via SQL queries (QODBC) or QBXML (QBFC)
     - SELECT * FROM Customer
     - SELECT * FROM Invoice
     - SELECT * FROM Account
     - ... 55+ entity types
                    │
                    ▼
  5. Encrypt extracted data (AES-256-GCM)
                    │
                    ▼
  6. Upload to server via HTTPS
```

---

## 3. Prerequisites

### 3.1 Development Machine (for building .exe)

| Requirement | Version | Notes |
|-------------|---------|-------|
| Windows | 10/11 | Required for .NET Framework |
| Visual Studio 2022 | 17.x | Or VS Build Tools |
| .NET Framework | 4.8 | Target framework |
| .NET SDK | 6.0+ | For `dotnet build` |

### 3.2 Server Machine (for backend)

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.9+ | Flask backend |
| PostgreSQL | 13+ | Or MySQL 8+ |
| Node.js | 18+ | For Next.js frontend |
| Redis | 6+ | Optional, for caching |

### 3.3 Client Machine (end user)

| Requirement | Version | Notes |
|-------------|---------|-------|
| Windows | 10/11 | QuickBooks requirement |
| QuickBooks Desktop | 2018+ | Pro, Premier, or Enterprise |
| **QODBC Driver** | Latest | **PRIMARY** - See Section 4 |
| .NET Framework | 4.7.2+ | Usually pre-installed |

---

## 4. Installing QODBC Driver

### 4.1 What is QODBC?

QODBC is a third-party ODBC driver that provides SQL access to QuickBooks data. It's:
- **Actively maintained** (unlike deprecated Intuit SDK)
- **Free for read-only** operations
- **Works with all QuickBooks Desktop versions** (2018+)

### 4.2 Download QODBC

1. Go to: **https://qodbc.com/qodbc-downloads/**

2. Download the appropriate version:
   - **QODBC Desktop Read-Only** (FREE) - Sufficient for extraction
   - QODBC Desktop (Paid) - If you need write access

3. File to download: `QODBCDesktopSetup.exe`

### 4.3 Install QODBC

```
1. Run QODBCDesktopSetup.exe as Administrator
2. Accept license agreement
3. Choose "Typical" installation
4. Complete installation wizard
5. Restart computer (recommended)
```

### 4.4 Verify QODBC Installation

```powershell
# Check if QODBC driver is registered
reg query "HKLM\SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers"

# Should show something like:
# QODBC Driver for QuickBooks    REG_SZ    Installed
```

Or check via ODBC Data Sources:
```
1. Press Windows + R
2. Type: odbcad32.exe
3. Go to "Drivers" tab
4. Look for "QODBC" or "QuickBooks"
```

### 4.5 Configure QODBC (Optional)

After installation, configure the DSN:

```
1. Open ODBC Data Sources (32-bit): odbcad32.exe
2. Go to "System DSN" tab
3. Click "Add"
4. Select "QODBC Driver for QuickBooks"
5. Configure:
   - Data Source Name: QuickBooks Data
   - Description: QODBC Connection
   - Leave other settings default
6. Click "Test Connection" (QuickBooks must be open)
7. Click "OK"
```

---

## 5. Building the QBExtractor.exe

### 5.1 Clone the Repository

```bash
git clone https://github.com/sivaharanj7805/QBMigration.git
cd QBMigration/QBDesktopReader
```

### 5.2 Understanding the Build (No SDK Required!)

**Good news:** Since we're using QODBC as the primary backend, you **do NOT need** the deprecated Intuit QBFC SDK to build the .exe.

The project is configured to:
1. Reference QBFC as an optional COM component (works if installed)
2. Automatically fall back to QODBC if QBFC is not available
3. Build successfully even without QBFC SDK installed

### 5.3 Modify Project for QODBC-Only Build

If you don't have QBFC SDK installed, modify the `.csproj` to skip the COM reference:

Edit `QBDesktopReader.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net48</TargetFramework>
    <PlatformTarget>x86</PlatformTarget>
    <RuntimeIdentifier>win-x86</RuntimeIdentifier>
    <LangVersion>9.0</LangVersion>

    <AssemblyName>QBExtractor</AssemblyName>
    <RootNamespace>QBDesktopExtractor</RootNamespace>
    <Version>4.4.0</Version>

    <!-- Skip QBFC if not available -->
    <UseQBFC>false</UseQBFC>
  </PropertyGroup>

  <!-- QBFC COM Reference - COMMENTED OUT (deprecated SDK not available)
  <ItemGroup Condition="'$(UseQBFC)' == 'true'">
    <COMReference Include="QBFC16Lib">
      <Guid>{4EADF8C9-0D1E-4F68-83D6-3F9F0E6FE0FE}</Guid>
      <VersionMajor>1</VersionMajor>
      <VersionMinor>0</VersionMinor>
      <Lcid>0</Lcid>
      <WrapperTool>tlbimp</WrapperTool>
      <Isolated>False</Isolated>
      <EmbedInteropTypes>True</EmbedInteropTypes>
    </COMReference>
  </ItemGroup>
  -->

  <!-- NuGet packages -->
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
    <PackageReference Include="JsonSchema.Net" Version="7.0.0" />
    <PackageReference Include="System.Security.Cryptography.ProtectedData" Version="8.0.0" />
    <PackageReference Include="System.Text.Json" Version="8.0.0" />
    <PackageReference Include="System.Management" Version="8.0.0" />
    <PackageReference Include="System.Data.Odbc" Version="8.0.0" />
    <PackageReference Include="Microsoft.VisualBasic" Version="10.3.0" />
  </ItemGroup>

  <!-- Copy config files to output -->
  <ItemGroup>
    <None Update="config.json">
      <CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>
    </None>
  </ItemGroup>

</Project>
```

### 5.4 Update Configuration

Edit `config.json` with your production server URL:

```json
{
  "$comment": "QuickBooks Extractor v4.4 Configuration",
  "serverUrl": "https://api.yourserver.com",
  "incrementalSyncFromDate": null,
  "version": "4.4",
  "schemaVersion": "4.4",
  "advanced": {
    "chunkSizeKB": 1024,
    "chunkedUploadThresholdMB": 10,
    "enableForensicHashing": true,
    "logLevel": "INFO",
    "retryAttempts": 3
  }
}
```

### 5.5 Update API URLs in Code

Edit `SessionValidator.cs` (line 39):
```csharp
SESSION_API_URL = envUrl ?? "https://api.yourserver.com/api/session";
```

Edit `LicenseValidator.cs` (line 39):
```csharp
LICENSE_API_URL = envUrl ?? "https://api.yourserver.com/api/license";
```

### 5.6 Build the Executable

**Option A: Using Visual Studio 2022**

```
1. Open QBDesktopReader.sln in Visual Studio 2022
2. Set configuration to "Release"
3. Set platform to "x86" (required for ODBC compatibility)
4. Build → Build Solution (Ctrl+Shift+B)
5. Output: bin\Release\net48\QBExtractor.exe
```

**Option B: Using Command Line**

```powershell
cd QBDesktopReader

# Restore NuGet packages
dotnet restore

# Build Release version (x86)
dotnet build -c Release -r win-x86

# Or using MSBuild
msbuild QBDesktopReader.csproj /p:Configuration=Release /p:Platform=x86
```

### 5.7 Verify Build Output

```powershell
dir bin\Release\net48\

# Expected files:
# - QBExtractor.exe           (main executable, ~2-3 MB)
# - QBExtractor.exe.config    (runtime config)
# - Newtonsoft.Json.dll       (JSON library)
# - config.json               (runtime config)
# - System.Data.Odbc.dll      (ODBC support)
```

### 5.8 Test the Build Locally

```powershell
# Run with --show-backends to verify detection
.\bin\Release\net48\QBExtractor.exe --show-backends

# Expected output:
# ============================================================
# Available QuickBooks Backends:
# ============================================================
# [✓] QODBC Driver - QODBC Driver for QuickBooks
# [✗] QBFC16 SDK - Not installed
#
# Primary backend: QODBC
# ============================================================
```

### 5.9 Create Distribution Package

```powershell
# Create distribution folder
$version = "4.4.0"
$distDir = "QBExtractor-v$version"
New-Item -ItemType Directory -Path $distDir -Force

# Copy required files
Copy-Item "bin\Release\net48\QBExtractor.exe" $distDir
Copy-Item "bin\Release\net48\QBExtractor.exe.config" $distDir
Copy-Item "bin\Release\net48\*.dll" $distDir
Copy-Item "config.json" $distDir

# Create README for users
@"
ForensicBridge QBExtractor v$version
=====================================

REQUIREMENTS:
1. Windows 10/11
2. QuickBooks Desktop 2018 or later
3. QODBC Driver (download from https://qodbc.com/qodbc-downloads/)
4. .NET Framework 4.7.2+ (usually pre-installed)

USAGE:
1. Open QuickBooks Desktop with your company file
2. Run QBExtractor.exe
3. Enter your Session ID from the ForensicBridge dashboard
4. Approve access when QuickBooks prompts
5. Wait for extraction to complete

For support, visit: https://github.com/sivaharanj7805/QBMigration
"@ | Out-File "$distDir\README.txt"

# Create ZIP
Compress-Archive -Path "$distDir\*" -DestinationPath "QBExtractor-v$version.zip" -Force

Write-Host "Created: QBExtractor-v$version.zip"
```

---

## 6. Configuring the Backend Server

### 6.1 Set Up Python Environment

```bash
cd QBMigrationServer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 6.2 Create Environment Variables

Create `.env` file:

```bash
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=your-super-secret-key-change-this-in-production

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/forensicbridge

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_REGION=us-east-1
S3_BUCKET_NAME=forensicbridge-migrations

# Optional: Redis for caching
REDIS_URL=redis://localhost:6379/0
```

### 6.3 Initialize Database

```bash
# Create database
createdb forensicbridge  # PostgreSQL

# Run migrations
flask db upgrade
```

### 6.4 Create S3 Bucket

```bash
aws s3 mb s3://forensicbridge-migrations --region us-east-1
```

### 6.5 Place QBExtractor.exe on Server

```bash
mkdir -p static/extractor
cp /path/to/QBExtractor.exe static/extractor/
```

### 6.6 Run the Server

**Development:**
```bash
flask run --host=0.0.0.0 --port=5000
```

**Production (with Gunicorn + Eventlet for WebSocket):**
```bash
pip install gunicorn eventlet
gunicorn -k eventlet -w 1 -b 0.0.0.0:5000 --timeout 120 app:app
```

### 6.7 Configure Nginx Reverse Proxy

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
    }

    # API endpoints
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 100M;
    }
}
```

---

## 7. Configuring the Frontend Dashboard

### 7.1 Install Dependencies

```bash
cd forensicbridge-dashboard
npm install
```

### 7.2 Configure Environment

Create `.env.local`:

```bash
NEXT_PUBLIC_API_URL=https://api.yourserver.com
NEXT_PUBLIC_WS_URL=https://api.yourserver.com
```

### 7.3 Build and Run

```bash
npm run build
npm start
```

---

## 8. Publishing the .exe for Distribution

### 8.1 Option A: GitHub Releases (Recommended)

```bash
git tag -a v4.4.0 -m "QBExtractor v4.4.0 - QODBC Primary"
git push origin v4.4.0

# Create release on GitHub and upload QBExtractor.exe
```

### 8.2 Option B: Direct Server Hosting

```bash
mkdir -p /var/www/forensicbridge/static/extractor
cp QBExtractor.exe /var/www/forensicbridge/static/extractor/
```

---

## 9. Client Machine Setup

### 9.1 Prerequisites Checklist

- [ ] Windows 10/11
- [ ] QuickBooks Desktop 2018+ installed
- [ ] QODBC Driver installed (see below)
- [ ] .NET Framework 4.7.2+ (usually pre-installed)

### 9.2 Install QODBC Driver (REQUIRED)

**This is the most important step for client machines.**

1. **Download from:** https://qodbc.com/qodbc-downloads/
   - Choose: **QODBC Desktop Read-Only Driver** (FREE)
   - Or: QODBC Desktop Driver (paid, if write access needed)

2. **Install:**
   ```
   - Run installer as Administrator
   - Accept license agreement
   - Choose "Typical" installation
   - Restart computer
   ```

3. **Verify installation:**
   ```powershell
   # Check ODBC drivers
   Get-OdbcDriver | Where-Object { $_.Name -like "*QODBC*" -or $_.Name -like "*QuickBooks*" }
   ```

### 9.3 Download QBExtractor

Users download from the dashboard after creating a project:
```
https://yourserver.com/api/extractor/download
```

### 9.4 Run QBExtractor

1. **Open QuickBooks Desktop** with company file (.qbw)
2. **Run QBExtractor.exe**
3. **Enter Session ID** when prompted (from dashboard)
4. **Authorize in QuickBooks** - Click "Yes, always allow" when QuickBooks asks

---

## 10. Complete Workflow Test

### 10.1 Create Test User

```bash
cd QBMigrationServer
flask shell

>>> from models import User, db
>>> user = User(email='test@example.com', name='Test User')
>>> user.set_password('testpass123')
>>> db.session.add(user)
>>> db.session.commit()
```

### 10.2 Test API Endpoints

```bash
# Health check
curl https://api.yourserver.com/health

# Login
curl -X POST https://api.yourserver.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}'

# Create project
curl -X POST https://api.yourserver.com/api/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Project"}'
```

### 10.3 Test Full Extraction

1. Open QuickBooks Desktop with a sample company file
2. Run QBExtractor.exe
3. Enter session ID
4. Approve in QuickBooks when prompted
5. Verify upload completes
6. Check dashboard for migration status

---

## 11. Troubleshooting

### 11.1 "No QuickBooks extraction backend available"

**Cause:** QODBC driver not installed

**Solution:**
```
1. Download QODBC from https://qodbc.com/qodbc-downloads/
2. Install the Read-Only version (free)
3. Restart your computer
4. Run QBExtractor.exe again
```

### 11.2 "QODBC connection failed"

**Cause:** QuickBooks not running or QODBC can't connect

**Solution:**
```
1. Ensure QuickBooks Desktop is RUNNING (not just installed)
2. Ensure a company file is OPEN in QuickBooks
3. Run QBExtractor as Administrator
4. Check QODBC configuration:
   - Open ODBC Data Sources (32-bit)
   - Find QODBC driver
   - Click "Configure" and test connection
```

### 11.3 "QuickBooks access denied"

**Cause:** QuickBooks hasn't authorized the application

**Solution:**
```
1. In QuickBooks, go to:
   Edit → Preferences → Integrated Applications → Company Preferences
2. Find "QODBC" or "QuickBooks Data" in the list
3. Ensure it's checked and has "Allow Access" enabled
4. If not listed, try connecting again - QB will prompt for authorization
```

### 11.4 "32-bit / 64-bit mismatch"

**Cause:** Using wrong ODBC architecture

**Solution:**
```
The QBExtractor.exe is built for x86 (32-bit).
QODBC must also be 32-bit.

1. Install QODBC 32-bit version
2. Use odbcad32.exe (not odbcad64.exe) to configure
3. The 32-bit ODBC is at: C:\Windows\SysWOW64\odbcad32.exe
```

### 11.5 "Session validation failed"

**Cause:** Invalid session ID or server unreachable

**Solution:**
```
1. Copy session ID exactly from dashboard (case-sensitive)
2. Check internet connection
3. Verify config.json serverUrl is correct
4. Test: curl https://api.yourserver.com/health
```

### 11.6 Build Error: "QBFC16Lib not found"

**Cause:** Trying to build with QBFC references but SDK not installed

**Solution:**
```
Since Intuit no longer provides QBFC SDK downloads:
1. Comment out the COMReference section in .csproj
2. Set <UseQBFC>false</UseQBFC> in PropertyGroup
3. The extractor will use QODBC automatically
```

---

## 12. Alternative Connection Methods

If QODBC doesn't work for your use case, here are alternatives:

### 12.1 CData QuickBooks Driver

- Website: https://www.cdata.com/drivers/quickbooks/
- Provides ODBC, JDBC, ADO.NET drivers
- Commercial license required
- Works similarly to QODBC

### 12.2 QuickBooks Web Connector

- Uses QBXML over SOAP
- Requires running a local web service
- More complex setup but Intuit-supported
- Not currently implemented in QBExtractor

### 12.3 Legacy QBFC SDK (If Available)

If you have an old QuickBooks installation, the SDK might still be installed:

```powershell
# Check if QBFC is already installed
reg query "HKCR\QBFC16.QBSessionManager" /ve

# If found, you can use QBFC as primary backend
# The extractor automatically detects and prefers it
```

---

## 13. Quick Reference

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 10 | Configuration error |
| 15 | License invalid |
| 20 | No backend (QODBC not installed) |
| 30 | QuickBooks connection failed |
| 40 | Extraction failed |
| 50 | Upload failed |
| 99 | Unknown error |

### Command Line Options

```
QBExtractor.exe [options]

Required:
  --session, -s <code>    Session code from dashboard

Options:
  --show-backends         Show available backends and exit
  --config, -c <path>     Path to config.json
  --no-pause              Don't wait for keypress on exit
  --verbose, -v           Debug output
  --help, -h              Show help
```

### QODBC SQL Examples

The extractor runs queries like:

```sql
-- Accounts
SELECT * FROM Account

-- Customers
SELECT * FROM Customer

-- Invoices with line items
SELECT * FROM Invoice
SELECT * FROM InvoiceLine WHERE InvoiceRefListID = '...'

-- And 50+ more entity types...
```

---

## Need Help?

- **GitHub Issues:** https://github.com/sivaharanj7805/QBMigration/issues
- **QODBC Support:** https://qodbc.com/support/
- **QODBC Documentation:** https://qodbc.com/qodbc-doc/
