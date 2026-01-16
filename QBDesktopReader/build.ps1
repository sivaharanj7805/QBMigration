# ForensicBridge Build Script
# Builds the C# extractor and creates Windows installer

param(
    [switch]$Release,
    [switch]$CreateInstaller,
    [switch]$SignCode,
    [string]$CertificatePath = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$PublishDir = "$ProjectRoot\publish"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ForensicBridge Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Clean
Write-Host "[1/5] Cleaning previous build..." -ForegroundColor Yellow
if (Test-Path $PublishDir) {
    Remove-Item -Recurse -Force $PublishDir
}
New-Item -ItemType Directory -Path $PublishDir -Force | Out-Null

# Step 2: Restore NuGet packages
Write-Host "[2/5] Restoring packages..." -ForegroundColor Yellow
dotnet restore "$ProjectRoot\QBDesktopReader.csproj"

# Step 3: Build
Write-Host "[3/5] Building..." -ForegroundColor Yellow
$config = if ($Release) { "Release" } else { "Debug" }

dotnet publish "$ProjectRoot\QBDesktopReader.csproj" `
    -c $config `
    -r win-x86 `
    --self-contained true `
    -p:PublishSingleFile=false `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $PublishDir

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

# Rename output to ForensicBridge
$exePath = "$PublishDir\QBExtractor.exe"
$newExePath = "$PublishDir\ForensicBridge.exe"
if (Test-Path $exePath) {
    Rename-Item -Path $exePath -NewName "ForensicBridge.exe"
}

Write-Host "Build successful: $newExePath" -ForegroundColor Green

# Step 4: Code signing (optional)
if ($SignCode -and $CertificatePath) {
    Write-Host "[4/5] Signing executable..." -ForegroundColor Yellow
    
    $signtool = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe"
    if (Test-Path $signtool) {
        & $signtool sign `
            /tr http://timestamp.digicert.com `
            /td sha256 `
            /fd sha256 `
            /f $CertificatePath `
            $newExePath
    } else {
        Write-Host "signtool.exe not found. Install Windows SDK." -ForegroundColor Yellow
    }
} else {
    Write-Host "[4/5] Skipping code signing" -ForegroundColor Gray
}

# Step 5: Create installer (optional)
if ($CreateInstaller) {
    Write-Host "[5/5] Creating installer..." -ForegroundColor Yellow
    
    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $iscc) {
        & $iscc "$ProjectRoot\ForensicBridge.iss"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Installer created: $ProjectRoot\installer\ForensicBridge_Setup_1.0.0.exe" -ForegroundColor Green
        }
    } else {
        Write-Host "Inno Setup not found. Download from https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
    }
} else {
    Write-Host "[5/5] Skipping installer creation" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Output: $PublishDir\ForensicBridge.exe"
Write-Host ""
Write-Host "To create installer:"
Write-Host "  .\build.ps1 -Release -CreateInstaller"
Write-Host ""
