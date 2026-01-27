# ForensicBridge Build Script v4.4
# Builds the C# extractor with multi-backend support
# Handles both SDK-present and SDK-absent build scenarios

param(
    [switch]$Release,
    [switch]$CreateInstaller,
    [switch]$SignCode,
    [string]$CertificatePath = "",
    [switch]$SkipRestore,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$PublishDir = "$ProjectRoot\publish"
$Version = "4.4.0"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ForensicBridge Build Script v4.4" -ForegroundColor Cyan
Write-Host "  Multi-Backend QuickBooks Extractor" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 0: Check prerequisites
Write-Host "[0/6] Checking prerequisites..." -ForegroundColor Yellow

# Check .NET SDK
$dotnetVersion = dotnet --version 2>$null
if (-not $dotnetVersion) {
    Write-Host "ERROR: .NET SDK not found. Please install .NET SDK 8.0+" -ForegroundColor Red
    Write-Host "Download from: https://dotnet.microsoft.com/download" -ForegroundColor Yellow
    exit 1
}
Write-Host "  .NET SDK: $dotnetVersion" -ForegroundColor Gray

# Check for QBFC16 SDK
$qbfcAvailable = $false
$qbfcPath = "C:\Program Files (x86)\Intuit\IDN\QBSDK16.0"
if (Test-Path $qbfcPath) {
    $qbfcAvailable = $true
    Write-Host "  QBFC16 SDK: Found at $qbfcPath" -ForegroundColor Green
} else {
    # Check registry for SDK
    try {
        $regPath = "HKLM:\SOFTWARE\WOW6432Node\Intuit\QBSDK"
        if (Test-Path $regPath) {
            $qbfcAvailable = $true
            Write-Host "  QBFC16 SDK: Found (via registry)" -ForegroundColor Green
        }
    } catch {}
}

if (-not $qbfcAvailable) {
    Write-Host "  QBFC16 SDK: Not found" -ForegroundColor Yellow
    Write-Host "  Build will proceed but QBFC backend won't work without SDK" -ForegroundColor Yellow
    Write-Host "  Download SDK from: https://developer.intuit.com" -ForegroundColor Yellow
}

# Check for QODBC
$qodbcAvailable = $false
try {
    $odbcDrivers = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\ODBC\ODBCINST.INI\ODBC Drivers" -ErrorAction SilentlyContinue
    if ($odbcDrivers) {
        $odbcDrivers.PSObject.Properties | ForEach-Object {
            if ($_.Name -match "QODBC|QuickBooks") {
                $qodbcAvailable = $true
                Write-Host "  QODBC Driver: Found ($($_.Name))" -ForegroundColor Green
            }
        }
    }
} catch {}

if (-not $qodbcAvailable) {
    Write-Host "  QODBC Driver: Not found (optional fallback)" -ForegroundColor Gray
}

Write-Host ""

# Step 1: Clean
Write-Host "[1/6] Cleaning previous build..." -ForegroundColor Yellow
if (Test-Path $PublishDir) {
    Remove-Item -Recurse -Force $PublishDir
}
New-Item -ItemType Directory -Path $PublishDir -Force | Out-Null

# Step 2: Restore NuGet packages
if (-not $SkipRestore) {
    Write-Host "[2/6] Restoring packages..." -ForegroundColor Yellow
    $restoreResult = dotnet restore "$ProjectRoot\QBDesktopReader.csproj" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Package restore failed!" -ForegroundColor Red
        Write-Host $restoreResult
        exit 1
    }
} else {
    Write-Host "[2/6] Skipping package restore" -ForegroundColor Gray
}

# Step 3: Build
Write-Host "[3/6] Building..." -ForegroundColor Yellow
$config = if ($Release) { "Release" } else { "Debug" }

$buildArgs = @(
    "publish",
    "$ProjectRoot\QBDesktopReader.csproj",
    "-c", $config,
    "-r", "win-x86",
    "--self-contained", "true",
    "-p:PublishSingleFile=false",
    "-p:IncludeNativeLibrariesForSelfExtract=true",
    "-p:Version=$Version",
    "-o", $PublishDir
)

if ($Verbose) {
    $buildArgs += "-v", "detailed"
}

$buildResult = & dotnet $buildArgs 2>&1
$buildExitCode = $LASTEXITCODE

if ($buildExitCode -ne 0) {
    Write-Host ""
    Write-Host "Build failed!" -ForegroundColor Red
    Write-Host ""

    # Check if it's a COM reference issue
    if ($buildResult -match "QBFC16" -or $buildResult -match "COM reference") {
        Write-Host "The build failed due to missing QBFC16 SDK COM reference." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Options:" -ForegroundColor Cyan
        Write-Host "  1. Install QuickBooks Desktop SDK (QBFC16)" -ForegroundColor White
        Write-Host "     Download from: https://developer.intuit.com" -ForegroundColor Gray
        Write-Host ""
        Write-Host "  2. Build without QBFC support (QODBC only)" -ForegroundColor White
        Write-Host "     This requires modifying the project to remove QBFC reference" -ForegroundColor Gray
    } else {
        Write-Host "Build output:" -ForegroundColor Gray
        Write-Host $buildResult
    }

    exit 1
}

# Verify output
$exePath = "$PublishDir\QBExtractor.exe"
if (Test-Path $exePath) {
    $fileInfo = Get-Item $exePath
    Write-Host "Build successful!" -ForegroundColor Green
    Write-Host "  Output: $exePath" -ForegroundColor Gray
    Write-Host "  Size: $([math]::Round($fileInfo.Length / 1MB, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "Build output not found at expected path" -ForegroundColor Yellow
}

# Step 4: Copy config files
Write-Host "[4/6] Copying configuration files..." -ForegroundColor Yellow
@("config.json", "config_production.json", "config_schema.json") | ForEach-Object {
    $src = "$ProjectRoot\$_"
    if (Test-Path $src) {
        Copy-Item $src -Destination $PublishDir -Force
        Write-Host "  Copied: $_" -ForegroundColor Gray
    }
}

# Step 5: Code signing (optional)
if ($SignCode -and $CertificatePath) {
    Write-Host "[5/6] Signing executable..." -ForegroundColor Yellow

    $signtool = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe"
    if (-not (Test-Path $signtool)) {
        # Try to find signtool
        $signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
                    Sort-Object -Property DirectoryName -Descending |
                    Select-Object -First 1 -ExpandProperty FullName
    }

    if ($signtool -and (Test-Path $signtool)) {
        & $signtool sign `
            /tr http://timestamp.digicert.com `
            /td sha256 `
            /fd sha256 `
            /f $CertificatePath `
            $exePath

        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Code signing successful" -ForegroundColor Green
        } else {
            Write-Host "  Code signing failed" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  signtool.exe not found. Install Windows SDK." -ForegroundColor Yellow
    }
} else {
    Write-Host "[5/6] Skipping code signing" -ForegroundColor Gray
}

# Step 6: Create installer (optional)
if ($CreateInstaller) {
    Write-Host "[6/6] Creating installer..." -ForegroundColor Yellow

    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $iscc) {
        & $iscc "$ProjectRoot\ForensicBridge.iss"

        if ($LASTEXITCODE -eq 0) {
            Write-Host "Installer created successfully!" -ForegroundColor Green
        } else {
            Write-Host "Installer creation failed" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Inno Setup not found. Download from https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
    }
} else {
    Write-Host "[6/6] Skipping installer creation" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Output: $PublishDir\QBExtractor.exe"
Write-Host "Version: $Version"
Write-Host ""

# Show backend status
Write-Host "Backend Support:" -ForegroundColor Cyan
if ($qbfcAvailable) {
    Write-Host "  [x] QBFC (Official SDK) - Full support" -ForegroundColor Green
} else {
    Write-Host "  [ ] QBFC - SDK not installed (runtime detection)" -ForegroundColor Yellow
}
if ($qodbcAvailable) {
    Write-Host "  [x] QODBC - Available as fallback" -ForegroundColor Green
} else {
    Write-Host "  [ ] QODBC - Not installed (runtime detection)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "Usage examples:" -ForegroundColor Cyan
Write-Host "  .\QBExtractor.exe --show-backends     # Show available backends"
Write-Host "  .\QBExtractor.exe --session <code>    # Run extraction"
Write-Host "  .\QBExtractor.exe --help              # Show all options"
Write-Host ""

Write-Host "To create installer:"
Write-Host "  .\build.ps1 -Release -CreateInstaller"
Write-Host ""
