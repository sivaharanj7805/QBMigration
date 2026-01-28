# ForensicBridge Extractor Deployment Guide v4.4

## Overview

This directory contains the ForensicBridge QuickBooks Desktop Extractor distribution files. The extractor is downloaded by users to extract data from QuickBooks Desktop for migration.

## Directory Structure

```
extractor/
├── ForensicBridge_Install.bat    # Bootstrap installer (users download this)
├── ForensicBridge_Bootstrap.ps1  # PowerShell alternative (optional)
├── QBExtractor.exe               # Main executable (optional - can be cached from GitHub)
├── QBExtractor-deploy.zip        # Full deployment package with all DLLs
├── zip_metadata.json             # Zip hash/size for verification
├── cache/                        # Auto-populated cache directory
│   ├── QBExtractor.exe          # Cached executable from GitHub
│   └── metadata.json            # Cache metadata (hash, date, source)
└── README.md                    # This file
```

## How It Works

### Download Flow

```
User clicks "Download Extractor" in Dashboard
                    │
                    ▼
         API: GET /api/extractor/download
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   Local .exe   Cached .exe   GitHub Release
   (fastest)    (fast)        (fallback)
        │           │           │
        └───────────┼───────────┘
                    │
                    ▼
            User gets .exe
                    │
              (if no .exe)
                    │
                    ▼
        Bootstrap .bat served
        (downloads .exe itself)
```

### Installation Flow (on user's Windows machine)

```
1. User downloads ForensicBridge_Install.bat
2. User right-clicks → "Run as Administrator"
3. Installer checks prerequisites:
   - PowerShell available
   - QuickBooks backends (QBFC SDK or QODBC)
4. Downloads QBExtractor.exe from:
   - ForensicBridge server (primary)
   - GitHub releases (fallback)
   - GitHub API (fallback)
5. Creates shortcuts (Desktop + Start Menu)
6. Launches extractor (optional)
```

### Extraction Flow

```
1. User opens QuickBooks Desktop with company file
2. User runs QBExtractor.exe
3. Extractor detects available backends:
   - QBFC16 (QuickBooks SDK) - preferred
   - QODBC (ODBC driver) - fallback
4. User enters session code from dashboard
5. Extractor validates session with server
6. Extraction begins (55+ entity types)
7. Data encrypted and uploaded to S3
8. Dashboard shows completion
```

## Deployment Options

### Option 1: GitHub Releases (Recommended)

The server will automatically cache from GitHub releases. Just create a release:

```bash
# Using GitHub Actions (automatic)
git tag v4.4.0
git push origin v4.4.0
# GitHub Actions builds and creates release

# Using manual script (local build)
cd QBDesktopReader
.\create-release.ps1 -Upload
```

### Option 2: Deploy to Server

Copy the built executable directly to the server:

```bash
# Build locally
cd QBDesktopReader
.\build.ps1 -Release

# Copy to server
scp publish/QBExtractor.exe user@server:/var/www/forensicbridge/static/extractor/
```

### Option 3: Environment Variable

Set `EXTRACTOR_PATH` to point to the executable:

```bash
export EXTRACTOR_PATH=/opt/forensicbridge/extractor/QBExtractor.exe
```

### Option 4: Deploy Zip Package to Ubuntu EC2

The zip package includes QBExtractor.exe plus all required DLLs. This is recommended for users who don't have .NET runtime installed.

#### Quick Deploy (Copy and Hash)

```bash
# 1. SSH into your EC2 instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# 2. Create the extractor directory
sudo mkdir -p /var/www/forensicbridge/extractor

# 3. Copy the zip file (from local machine)
scp -i your-key.pem QBExtractor-deploy.zip ubuntu@your-ec2-ip:/tmp/

# 4. Move to deployment location
sudo mv /tmp/QBExtractor-deploy.zip /var/www/forensicbridge/extractor/

# 5. Generate and save the hash metadata
cd /var/www/forensicbridge/extractor
SHA256=$(sha256sum QBExtractor-deploy.zip | cut -d' ' -f1)
SIZE=$(stat -c%s QBExtractor-deploy.zip)
sudo tee zip_metadata.json << EOF
{
  "sha256": "$SHA256",
  "size": $SIZE,
  "filename": "QBExtractor-deploy.zip",
  "generated_at": "$(date -Iseconds)",
  "version": "4.4.0"
}
EOF

# 6. Set permissions
sudo chown -R www-data:www-data /var/www/forensicbridge/extractor
sudo chmod 644 /var/www/forensicbridge/extractor/*

# 7. Verify deployment
curl https://your-api-domain/api/extractor/zip/info
```

#### Alternative: Use App Static Directory

```bash
# Copy to the Flask static directory instead
sudo cp QBExtractor-deploy.zip /path/to/QBMigrationServer/static/extractor/

# Regenerate hash via API
curl -X POST https://your-api-domain/api/extractor/zip/regenerate-hash
```

#### Zip Search Locations

The API checks these paths for the zip file (in order):

1. `EXTRACTOR_ZIP_PATH` environment variable (if set)
2. `/var/www/forensicbridge/extractor/QBExtractor-deploy.zip`
3. `/opt/forensicbridge/extractor/QBExtractor-deploy.zip`
4. `static/extractor/QBExtractor-deploy.zip`
5. `static/QBExtractor-deploy.zip`

## Zip Package Verification

Clients can verify the downloaded zip hasn't been tampered with:

### Get Expected Hash (Before Download)

```bash
curl https://your-api-domain/api/extractor/zip/info
# Response:
# {
#   "available": true,
#   "sha256": "728140ebeddc98b4b5154c105fc917a0a943db786e342ca8f5d4ff530d5b8ed3",
#   "size": 1175316,
#   "download_url": "/api/extractor/download-zip"
# }
```

### Download and Verify (Client Side)

```bash
# Download the zip
curl -O https://your-api-domain/api/extractor/download-zip

# Compute local hash
LOCAL_HASH=$(sha256sum QBExtractor-deploy.zip | cut -d' ' -f1)

# Verify with server
curl -X POST https://your-api-domain/api/extractor/zip/verify \
  -H "Content-Type: application/json" \
  -d "{\"sha256\": \"$LOCAL_HASH\"}"

# Response if valid:
# {"valid": true, "message": "Hash verification successful"}
```

### PowerShell Verification (Windows)

```powershell
# Download
Invoke-WebRequest -Uri "https://your-api-domain/api/extractor/download-zip" -OutFile "QBExtractor-deploy.zip"

# Compute hash
$hash = (Get-FileHash -Path "QBExtractor-deploy.zip" -Algorithm SHA256).Hash.ToLower()

# Verify
$body = @{sha256 = $hash} | ConvertTo-Json
$result = Invoke-RestMethod -Uri "https://your-api-domain/api/extractor/zip/verify" -Method POST -Body $body -ContentType "application/json"
Write-Host "Valid: $($result.valid)"
```

## Server Search Order

The API checks these locations in order:
1. `EXTRACTOR_PATH` environment variable (if set)
2. `/var/www/forensicbridge/extractor/QBExtractor.exe`
3. `/opt/forensicbridge/extractor/QBExtractor.exe`
4. `static/QBExtractor.exe`
5. `static/extractor/QBExtractor.exe`
6. `static/extractor/cache/QBExtractor.exe`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/extractor/download` | GET | Smart download (exe or bootstrap) |
| `/api/extractor/download-exe` | GET | Direct exe download |
| `/api/extractor/download-zip` | GET | Download full deployment package (zip) |
| `/api/extractor/zip/info` | GET | Get zip info + SHA256 hash for verification |
| `/api/extractor/zip/verify` | POST | Verify downloaded zip by hash |
| `/api/extractor/zip/regenerate-hash` | POST | Regenerate hash after updating zip |
| `/api/extractor/bootstrap` | GET | Download bootstrap .bat |
| `/api/extractor/info` | GET | Availability info |
| `/api/extractor/status` | GET | Full status of all sources |
| `/api/extractor/version` | GET | Version and compatibility |
| `/api/extractor/health` | GET | Health check for monitoring |
| `/api/extractor/docs` | GET | API documentation |
| `/api/extractor/cache/refresh` | POST | Force refresh from GitHub |
| `/api/extractor/cache/clear` | POST | Clear cached files |

## Cache Management

The server automatically caches the extractor from GitHub releases:

```bash
# Check cache status
curl https://api.forensicbridge.ca/api/extractor/status

# Force refresh cache
curl -X POST https://api.forensicbridge.ca/api/extractor/cache/refresh

# Clear cache
curl -X POST https://api.forensicbridge.ca/api/extractor/cache/clear
```

Cache settings:
- **Duration**: 24 hours
- **Validation**: SHA256 hash + file size check
- **Minimum size**: 50KB (to detect corrupted downloads)

## Backend Requirements

Users need ONE of these backends installed:

### QuickBooks SDK (QBFC16) - Recommended

- **Download**: https://developer.intuit.com
- **Free**: Yes (requires Intuit Developer account)
- **Best for**: Full feature support, all entity types

### QODBC Driver - Fallback

- **Download**: https://qodbc.com/qodbc-downloads/
- **Free**: Yes (read-only version)
- **Best for**: When SDK installation is not possible

## Creating a New Release

### Automatic (GitHub Actions)

```bash
# Tag and push
git tag v4.4.1
git push origin v4.4.1

# GitHub Actions will:
# 1. Build x86 and x64 versions
# 2. Create GitHub release
# 3. Upload executables
# 4. Server cache will auto-refresh on next request
```

### Manual

```powershell
# On Windows with .NET SDK
cd QBDesktopReader

# Build only
.\create-release.ps1 -Version "4.4.1"

# Build and upload to GitHub
.\create-release.ps1 -Version "4.4.1" -Upload

# Build with code signing
.\create-release.ps1 -Version "4.4.1" -SignCode -CertificatePath "cert.pfx"
```

## Troubleshooting

### "Extractor not available"

1. Check if GitHub release exists:
   ```bash
   curl https://api.github.com/repos/sivaharanj7805/QBMigration/releases/latest
   ```

2. Force cache refresh:
   ```bash
   curl -X POST https://api.forensicbridge.ca/api/extractor/cache/refresh
   ```

3. Deploy manually to server

### "Download failed" (user side)

1. Check firewall allows downloads
2. Try direct GitHub download
3. Build from source and distribute manually

### "No backend detected"

Users need to install either:
- QuickBooks SDK (QBFC16) from developer.intuit.com
- QODBC Driver from qodbc.com

The extractor will guide them through this.

## File Requirements

- **Minimum file size**: 50KB (smaller files are rejected as invalid)
- **Expected size**: ~15-25 MB for self-contained .NET executable

## Version History

| Version | Changes |
|---------|---------|
| 4.4.0 | Multi-backend support, QODBC fallback, retry logic |
| 4.3.0 | Session validation, device fingerprinting |
| 4.2.0 | Low-memory streaming, AES-256-GCM encryption |
| 4.1.0 | NDJSON output, incremental sync |
| 4.0.0 | Initial production release |

## Security

- **Encryption**: AES-256-GCM for data in transit
- **Hashing**: SHA256 per-record for audit trail
- **Session**: Validated server-side, device-bound
- **Extraction limits**: Max 5 per session, max 2 devices
- **PII**: Redacted from logs by default
