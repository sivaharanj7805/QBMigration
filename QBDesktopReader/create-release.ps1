# ForensicBridge Release Script v4.4
# Creates a release package with signed executables
#
# Usage:
#   .\create-release.ps1                    # Build release
#   .\create-release.ps1 -Version "4.4.1"   # Specific version
#   .\create-release.ps1 -Upload            # Build and upload to GitHub
#   .\create-release.ps1 -SignCode          # Sign executables (requires cert)

param(
    [string]$Version = "4.4.0",
    [switch]$Upload,
    [switch]$SignCode,
    [string]$CertificatePath = "",
    [switch]$SkipBuild,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$PublishDir = "$ProjectRoot\publish"
$ReleaseDir = "$ProjectRoot\release"

# Colors for output
function Write-Status($message) { Write-Host "[*] $message" -ForegroundColor Cyan }
function Write-Success($message) { Write-Host "[+] $message" -ForegroundColor Green }
function Write-Warning($message) { Write-Host "[!] $message" -ForegroundColor Yellow }
function Write-Error($message) { Write-Host "[-] $message" -ForegroundColor Red }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ForensicBridge Release Script v$Version" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Clean previous builds
Write-Status "Cleaning previous builds..."
Remove-Item -Path $PublishDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path $ReleaseDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -Path $PublishDir -ItemType Directory -Force | Out-Null
New-Item -Path $ReleaseDir -ItemType Directory -Force | Out-Null

# Check prerequisites
Write-Status "Checking prerequisites..."

# Check .NET SDK
$dotnetVersion = dotnet --version 2>$null
if (-not $dotnetVersion) {
    Write-Error ".NET SDK not found. Please install .NET 8.0 SDK."
    exit 1
}
Write-Success ".NET SDK: $dotnetVersion"

# Check GitHub CLI (optional, for upload)
if ($Upload) {
    $ghVersion = gh --version 2>$null
    if (-not $ghVersion) {
        Write-Error "GitHub CLI (gh) not found. Required for upload."
        Write-Host "  Install: https://cli.github.com/"
        exit 1
    }
    Write-Success "GitHub CLI: Available"
}

# Build
if (-not $SkipBuild) {
    Write-Status "Building release packages..."

    # Build x86 (32-bit) - Primary for QuickBooks compatibility
    Write-Status "Building x86 (32-bit)..."
    dotnet publish "$ProjectRoot\QBDesktopReader.csproj" `
        -c Release `
        -r win-x86 `
        --self-contained true `
        -p:PublishSingleFile=true `
        -p:IncludeNativeLibrariesForSelfExtract=true `
        -p:Version=$Version `
        -o "$PublishDir\x86"

    if (-not (Test-Path "$PublishDir\x86\QBDesktopReader.exe")) {
        Write-Error "x86 build failed!"
        exit 1
    }
    Write-Success "x86 build complete"

    # Build x64 (64-bit) - Optional
    Write-Status "Building x64 (64-bit)..."
    dotnet publish "$ProjectRoot\QBDesktopReader.csproj" `
        -c Release `
        -r win-x64 `
        --self-contained true `
        -p:PublishSingleFile=true `
        -p:IncludeNativeLibrariesForSelfExtract=true `
        -p:Version=$Version `
        -o "$PublishDir\x64"

    if (-not (Test-Path "$PublishDir\x64\QBDesktopReader.exe")) {
        Write-Error "x64 build failed!"
        exit 1
    }
    Write-Success "x64 build complete"
}

# Rename and move to release folder
Write-Status "Preparing release files..."
Copy-Item "$PublishDir\x86\QBDesktopReader.exe" "$ReleaseDir\QBExtractor.exe" -Force
Copy-Item "$PublishDir\x64\QBDesktopReader.exe" "$ReleaseDir\QBExtractor-x64.exe" -Force

# Copy installer script
$installerPath = "$ProjectRoot\..\QBMigrationServer\static\extractor\ForensicBridge_Install.bat"
if (Test-Path $installerPath) {
    Copy-Item $installerPath "$ReleaseDir\" -Force
    Write-Success "Copied installer script"
}

# Code signing (optional)
if ($SignCode) {
    if (-not $CertificatePath -or -not (Test-Path $CertificatePath)) {
        Write-Warning "No valid certificate path provided, skipping signing"
    } else {
        Write-Status "Signing executables..."
        $timestamp = "http://timestamp.digicert.com"

        foreach ($exe in @("QBExtractor.exe", "QBExtractor-x64.exe")) {
            $exePath = "$ReleaseDir\$exe"
            signtool sign /f $CertificatePath /tr $timestamp /td sha256 /fd sha256 $exePath
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Signed: $exe"
            } else {
                Write-Warning "Failed to sign: $exe"
            }
        }
    }
}

# Calculate checksums
Write-Status "Calculating checksums..."
$checksums = @()
$files = Get-ChildItem "$ReleaseDir\*.exe"
foreach ($file in $files) {
    $hash = (Get-FileHash $file.FullName -Algorithm SHA256).Hash
    $checksums += "$hash  $($file.Name)"
    Write-Host "  $($file.Name): $($hash.Substring(0,16))..." -ForegroundColor Gray
}
$checksums | Out-File "$ReleaseDir\checksums.txt" -Encoding UTF8
Write-Success "Checksums saved to checksums.txt"

# Create version info
$versionInfo = @{
    version = $Version
    build_date = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    build_machine = $env:COMPUTERNAME
    files = @{}
}
foreach ($file in $files) {
    $versionInfo.files[$file.Name] = @{
        size = $file.Length
        sha256 = (Get-FileHash $file.FullName -Algorithm SHA256).Hash
    }
}
$versionInfo | ConvertTo-Json -Depth 3 | Out-File "$ReleaseDir\version.json" -Encoding UTF8

# Show summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Release Package Ready" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Version: $Version"
Write-Host "  Location: $ReleaseDir"
Write-Host ""
Write-Host "  Files:" -ForegroundColor Cyan
Get-ChildItem $ReleaseDir | ForEach-Object {
    $sizeKB = [math]::Round($_.Length / 1KB, 1)
    $sizeMB = [math]::Round($_.Length / 1MB, 2)
    if ($sizeMB -ge 1) {
        Write-Host "    $($_.Name): $sizeMB MB"
    } else {
        Write-Host "    $($_.Name): $sizeKB KB"
    }
}
Write-Host ""

# Upload to GitHub
if ($Upload) {
    Write-Status "Creating GitHub release..."

    $tagName = "v$Version"
    $releaseName = "QBExtractor v$Version"

    # Check if release already exists
    $existingRelease = gh release view $tagName 2>$null
    if ($existingRelease) {
        Write-Warning "Release $tagName already exists. Deleting..."
        gh release delete $tagName --yes
    }

    # Create release
    $releaseNotes = @"
## QBExtractor v$Version

### Downloads
- **QBExtractor.exe** - 32-bit version (recommended for QuickBooks compatibility)
- **QBExtractor-x64.exe** - 64-bit version
- **ForensicBridge_Install.bat** - One-click installer

### Installation
1. Download ``ForensicBridge_Install.bat``
2. Right-click and "Run as Administrator"
3. Follow the prompts

Or download ``QBExtractor.exe`` directly and run it.

### Requirements
- Windows 10 or later
- QuickBooks Desktop installed and open
- One of:
  - QuickBooks SDK (QBFC16) - **Recommended**
  - QODBC Driver (fallback option)

### What's New in v$Version
- Multi-backend support (QBFC + QODBC fallback)
- Automatic backend detection
- Improved error handling with retry logic
- Better installation experience

### Checksums (SHA256)
$(Get-Content "$ReleaseDir\checksums.txt" | ForEach-Object { "``$_``" })
"@

    $releaseNotes | Out-File "$ReleaseDir\release_notes.md" -Encoding UTF8

    gh release create $tagName `
        --title "$releaseName" `
        --notes-file "$ReleaseDir\release_notes.md" `
        "$ReleaseDir\QBExtractor.exe" `
        "$ReleaseDir\QBExtractor-x64.exe" `
        "$ReleaseDir\ForensicBridge_Install.bat" `
        "$ReleaseDir\checksums.txt"

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Release created successfully!"
        Write-Host ""
        Write-Host "  View release: https://github.com/sivaharanj7805/QBMigration/releases/tag/$tagName"
    } else {
        Write-Error "Failed to create release"
        exit 1
    }
}

# Deploy to server (optional)
$serverDeployPath = "$ProjectRoot\..\QBMigrationServer\static\extractor"
if (Test-Path $serverDeployPath) {
    Write-Status "Deploying to server static folder..."
    Copy-Item "$ReleaseDir\QBExtractor.exe" "$serverDeployPath\" -Force
    Write-Success "Deployed to: $serverDeployPath"
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
Write-Host ""

# Show next steps
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Test the extractor locally"
Write-Host "  2. If not uploaded, run: .\create-release.ps1 -Upload"
Write-Host "  3. Update server cache: POST /api/extractor/cache/refresh"
Write-Host ""
