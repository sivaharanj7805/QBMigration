# ForensicBridge Build Script
# Builds the C# extractor with optional SDK support
#
# BUILD MODES:
#   .\build.ps1 -Release               # QODBC-only build (no SDK required)
#   .\build.ps1 -Release -UseSDK       # Full build with SDK support
#
# The QODBC-only build can be done on any machine.
# The SDK build requires QBFC16 to be installed.

param(
    [switch]$Release,
    [switch]$UseSDK,
    [switch]$CreateInstaller,
    [switch]$SignCode,
    [string]$CertificatePath = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$PublishDir = "$ProjectRoot\publish"

function Write-Header {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  ForensicBridge Build Script v4.4" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Step, [string]$Message)
    Write-Host "[$Step] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Yellow
}

function Test-SDKInstalled {
    # Check if QBFC16 SDK is installed
    $sdkPaths = @(
        "C:\Program Files (x86)\Intuit\IDN\QBSDK16.0",
        "C:\Program Files\Intuit\IDN\QBSDK16.0"
    )

    foreach ($path in $sdkPaths) {
        if (Test-Path $path) {
            return $true
        }
    }

    # Also check registry for COM registration
    try {
        $comGuid = "{4EADF8C9-0D1E-4F68-83D6-3F9F0E6FE0FE}"
        $regPath = "HKLM:\SOFTWARE\Classes\CLSID\$comGuid"
        if (Test-Path $regPath) {
            return $true
        }

        # 32-bit registry on 64-bit Windows
        $regPath32 = "HKLM:\SOFTWARE\WOW6432Node\Classes\CLSID\$comGuid"
        if (Test-Path $regPath32) {
            return $true
        }
    } catch {}

    return $false
}

Write-Header

# Display build mode
if ($UseSDK) {
    Write-Host "Build Mode: SDK + QODBC (full features)" -ForegroundColor Cyan

    # Verify SDK is installed
    if (-not (Test-SDKInstalled)) {
        Write-Host ""
        Write-Host "ERROR: QuickBooks SDK (QBFC16) not found!" -ForegroundColor Red
        Write-Host ""
        Write-Host "To build with SDK support, install the QuickBooks Desktop SDK:" -ForegroundColor Yellow
        Write-Host "  1. Visit: https://developer.intuit.com/app/developer/qbdesktop" -ForegroundColor White
        Write-Host "  2. Download QBFC16 SDK" -ForegroundColor White
        Write-Host "  3. Run the installer as Administrator" -ForegroundColor White
        Write-Host ""
        Write-Host "Or build without SDK support (QODBC only):" -ForegroundColor Yellow
        Write-Host "  .\build.ps1 -Release" -ForegroundColor White
        Write-Host ""
        exit 1
    }
    Write-Success "QuickBooks SDK detected"
} else {
    Write-Host "Build Mode: QODBC-only (no SDK required)" -ForegroundColor Cyan
}
Write-Host ""

# Step 1: Clean
Write-Step "1/5" "Cleaning previous build..."
if (Test-Path $PublishDir) {
    Remove-Item -Recurse -Force $PublishDir
}
New-Item -ItemType Directory -Path $PublishDir -Force | Out-Null

if ($Clean) {
    Write-Host "Cleaning obj and bin directories..."
    Get-ChildItem -Path $ProjectRoot -Include "obj", "bin" -Recurse -Directory | Remove-Item -Recurse -Force
    Write-Success "Clean complete"
    exit 0
}

# Step 2: Restore NuGet packages
Write-Step "2/5" "Restoring packages..."
dotnet restore "$ProjectRoot\QBDesktopReader.csproj"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Package restore failed!" -ForegroundColor Red
    exit 1
}

# Step 3: Build
Write-Step "3/5" "Building..."
$config = if ($Release) { "Release" } else { "Debug" }

$buildArgs = @(
    "publish"
    "$ProjectRoot\QBDesktopReader.csproj"
    "-c", $config
    "-r", "win-x86"
    "--self-contained", "true"
    "-p:PublishSingleFile=false"
    "-p:IncludeNativeLibrariesForSelfExtract=true"
    "-o", $PublishDir
)

# Add SDK flag if requested
if ($UseSDK) {
    $buildArgs += "-p:UseSDK=true"
    Write-Host "  Including QBFC16 SDK support" -ForegroundColor Gray
} else {
    Write-Host "  Building QODBC-only version" -ForegroundColor Gray
}

& dotnet @buildArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

# Verify output
$exePath = "$PublishDir\QBExtractor.exe"
if (Test-Path $exePath) {
    $fileInfo = Get-Item $exePath
    $sizeKB = [math]::Round($fileInfo.Length / 1KB, 1)
    Write-Success "Build successful: $exePath ($sizeKB KB)"
} else {
    Write-Host "Build output not found at expected path" -ForegroundColor Red
    exit 1
}

# Step 4: Code signing (optional)
if ($SignCode -and $CertificatePath) {
    Write-Step "4/5" "Signing executable..."

    $signtoolPaths = @(
        "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22000.0\x64\signtool.exe",
        "C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe",
        "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
    )

    $signtool = $null
    foreach ($path in $signtoolPaths) {
        if (Test-Path $path) {
            $signtool = $path
            break
        }
    }

    if ($signtool) {
        & $signtool sign `
            /tr http://timestamp.digicert.com `
            /td sha256 `
            /fd sha256 `
            /f $CertificatePath `
            $exePath

        if ($LASTEXITCODE -eq 0) {
            Write-Success "Code signing successful"
        } else {
            Write-Warn "Code signing failed (continuing anyway)"
        }
    } else {
        Write-Warn "signtool.exe not found. Install Windows SDK for code signing."
    }
} else {
    Write-Step "4/5" "Skipping code signing"
}

# Step 5: Create installer (optional)
if ($CreateInstaller) {
    Write-Step "5/5" "Creating installer..."

    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $iscc) {
        & $iscc "$ProjectRoot\ForensicBridge.iss"

        if ($LASTEXITCODE -eq 0) {
            Write-Success "Installer created"
        } else {
            Write-Warn "Installer creation failed"
        }
    } else {
        Write-Warn "Inno Setup not found. Download from https://jrsoftware.org/isinfo.php"
    }
} else {
    Write-Step "5/5" "Skipping installer creation"
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Output: $PublishDir\QBExtractor.exe"
Write-Host ""

if ($UseSDK) {
    Write-Host "This build supports BOTH backends:" -ForegroundColor Cyan
    Write-Host "  - SDK (QBFC16): Full QuickBooks API access"
    Write-Host "  - QODBC: SQL-based access (requires QODBC driver)"
} else {
    Write-Host "This build supports QODBC backend only:" -ForegroundColor Cyan
    Write-Host "  - Requires QODBC driver installed on target machine"
    Write-Host "  - Download: https://qodbc.com/qodbc-downloads/"
    Write-Host ""
    Write-Host "To build with SDK support:" -ForegroundColor Gray
    Write-Host "  .\build.ps1 -Release -UseSDK"
}

Write-Host ""
Write-Host "To create installer:"
Write-Host "  .\build.ps1 -Release -CreateInstaller"
Write-Host ""

# Return success
exit 0
