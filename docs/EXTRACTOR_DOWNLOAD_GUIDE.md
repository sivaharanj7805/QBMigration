# ForensicBridge Extractor Download System

This document explains how the extractor download system works and how to troubleshoot issues.

## How It Works

The ForensicBridge download system has **4 fallback levels** to ensure users can always get the extractor:

```
┌─────────────────────────────────────────────────────────────┐
│  User downloads ForensicBridge_Install.bat                  │
│  (from /api/extractor/download or /api/extractor/bootstrap) │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │  [1] Try ForensicBridge Server     │
        │  https://api.forensicbridge.ca     │
        │  /api/extractor/download           │
        └──────────────┬─────────────────────┘
                       │ (if installer not on server)
                       ▼
        ┌────────────────────────────────────┐
        │  [2] Try GitHub Releases           │
        │  /releases/latest/download/        │
        │  ForensicBridge_Setup.exe          │
        └──────────────┬─────────────────────┘
                       │ (if no release exists)
                       ▼
        ┌────────────────────────────────────┐
        │  [3] Try curl (Windows 10+)        │
        │  Alternative download method       │
        └──────────────┬─────────────────────┘
                       │ (if curl fails)
                       ▼
        ┌────────────────────────────────────┐
        │  [4] Embedded PowerShell Installer │
        │  Creates ForensicBridge directly   │
        │  without external download         │
        └────────────────────────────────────┘
```

## Current Status

If you see "Download failed", it means:
1. The ForensicBridge server doesn't have the installer file
2. No GitHub Release has been created yet
3. The embedded installer will be used as fallback

## Creating a GitHub Release

### Method 1: Automatic (Recommended)

The GitHub Actions workflow automatically creates releases when:
- Code is pushed to the `main` branch
- A version tag (e.g., `v1.0.0`) is pushed

**To trigger a release:**

1. Merge your changes to `main`:
   ```bash
   git checkout main
   git merge your-branch
   git push origin main
   ```

2. Or create a version tag:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. Or manually trigger the workflow:
   - Go to: https://github.com/sivaharanj7805/QBMigration/actions
   - Click "Build ForensicBridge Installer"
   - Click "Run workflow"
   - Select branch and click "Run workflow"

### Method 2: Manual Release

If GitHub Actions isn't working, create a release manually:

1. **Build the installer locally** (requires Windows):
   ```powershell
   cd ForensicBridgeInstaller
   dotnet restore
   dotnet build --configuration Release
   dotnet publish --configuration Release --output publish

   # Then run Inno Setup on ForensicBridge.iss
   ```

2. **Create a GitHub Release**:
   - Go to: https://github.com/sivaharanj7805/QBMigration/releases/new
   - Tag: `v1.0.0` (or next version)
   - Title: `ForensicBridge v1.0.0`
   - Attach: `ForensicBridge_Setup.exe`
   - Publish

## Hosting on Server (Alternative)

You can also host the installer directly on the ForensicBridge server:

1. **Upload the installer** to one of these paths on the server:
   - `/var/www/forensicbridge/extractor/ForensicBridge_Setup.exe`
   - `/opt/forensicbridge/extractor/ForensicBridge_Setup.exe`

2. **Or set the environment variable**:
   ```bash
   export EXTRACTOR_PATH=/path/to/ForensicBridge_Setup.exe
   ```

3. **Verify** by visiting:
   ```
   https://api.forensicbridge.ca/api/extractor/info
   ```

   Should show:
   ```json
   {
     "available": true,
     "source": "local",
     "type": "full_installer"
   }
   ```

## Troubleshooting

### "Download failed" message

This is expected if no release exists yet. The embedded installer will work as a fallback.

To fix permanently:
1. Trigger a GitHub Release (see above)
2. Or upload the installer to the server

### Checking download availability

```bash
# Check server status
curl https://api.forensicbridge.ca/api/extractor/status

# Check if GitHub release exists
curl -I https://github.com/sivaharanj7805/QBMigration/releases/latest/download/ForensicBridge_Setup.exe
```

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/extractor/download` | Smart download - serves installer or bootstrap |
| `/api/extractor/bootstrap` | Always serves the .bat bootstrap script |
| `/api/extractor/bootstrap-ps1` | PowerShell bootstrap script |
| `/api/extractor/info` | Check what's available |
| `/api/extractor/status` | Full status of all download options |
| `/api/extractor/releases` | Redirect to GitHub releases page |

## Files Involved

| File | Purpose |
|------|---------|
| `QBMigrationServer/static/extractor/ForensicBridge_Install.bat` | Bootstrap batch script |
| `QBMigrationServer/static/extractor/ForensicBridge_Bootstrap.ps1` | Bootstrap PowerShell script |
| `QBMigrationServer/api/extractor.py` | Server API endpoints |
| `ForensicBridgeInstaller/` | Source code for the Windows installer |
| `.github/workflows/build-installer.yml` | CI/CD workflow |

## Expected User Experience

**When GitHub Release exists:**
```
============================================================
  ForensicBridge Extractor - Smart Installer
============================================================

Checking download sources...

[1/4] Trying ForensicBridge server...
  Server does not have pre-built installer
[2/4] Trying GitHub releases...
  Download successful from GitHub!

Verifying download...
Download verified! File size: 12345678 bytes

Starting installer...
[Windows installer runs]

INSTALLATION COMPLETE!
```

**When no release exists (fallback):**
```
============================================================
  ForensicBridge Extractor - Smart Installer
============================================================

Checking download sources...

[1/4] Trying ForensicBridge server...
  Server does not have pre-built installer
[2/4] Trying GitHub releases...
  Downloaded file too small (likely 404 page)
[3/4] Trying alternative download method (curl)...
  curl not available or download failed
[4/4] Using embedded installer method...

Creating ForensicBridge launcher...
  Created: ForensicBridge.ps1
  Created: ForensicBridge.bat
  Created: ForensicBridge.vbs
  Created desktop shortcut

INSTALLATION COMPLETE!
ForensicBridge has been installed to: C:\Users\...\AppData\Local\ForensicBridge
```

Both paths result in a working installation!
