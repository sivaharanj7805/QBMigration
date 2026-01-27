# ForensicBridge Extractor Bootstrap Script
# This script downloads and installs the ForensicBridge Extractor
# Run this script in PowerShell as Administrator

param(
    [string]$SessionCode = "",
    [switch]$Silent = $false
)

$ErrorActionPreference = "Stop"

# Configuration
$AppName = "ForensicBridge Extractor"
$InstallerName = "ForensicBridge_Setup.exe"
$TempPath = Join-Path $env:TEMP "ForensicBridge"
$InstallerPath = Join-Path $TempPath $InstallerName
$InstallDir = Join-Path $env:LOCALAPPDATA "ForensicBridge"

# Download URLs (in order of priority)
$DownloadUrls = @(
    "https://github.com/sivaharanj7805/QBMigration/releases/latest/download/ForensicBridge_Setup.exe",
    "https://github.com/sivaharanj7805/QBMigration/releases/download/v1.0.0/ForensicBridge_Setup.exe"
)

# Banner
function Show-Banner {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  ForensicBridge Extractor - Bootstrap Installer" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  This script will download and install the ForensicBridge" -ForegroundColor White
    Write-Host "  Extractor for QuickBooks Desktop data migration." -ForegroundColor White
    Write-Host ""
}

# Check if running as administrator
function Test-Administrator {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Download file with progress
function Download-FileWithProgress {
    param(
        [string]$Url,
        [string]$OutputPath
    )

    Write-Host "Downloading from: $Url" -ForegroundColor Yellow

    try {
        # Use .NET WebClient for progress
        $webClient = New-Object System.Net.WebClient

        # Add event handler for progress
        $webClient.DownloadProgressChanged += {
            param($sender, $e)
            Write-Progress -Activity "Downloading ForensicBridge" -Status "$($e.ProgressPercentage)% Complete" -PercentComplete $e.ProgressPercentage
        }

        # Synchronous download with progress via async workaround
        $webClient.DownloadFile($Url, $OutputPath)
        Write-Progress -Activity "Downloading ForensicBridge" -Completed

        return $true
    }
    catch {
        Write-Host "Download failed: $_" -ForegroundColor Red
        return $false
    }
}

# Try to download from multiple URLs
function Download-Installer {
    # Create temp directory
    if (-not (Test-Path $TempPath)) {
        New-Item -ItemType Directory -Path $TempPath -Force | Out-Null
    }

    foreach ($url in $DownloadUrls) {
        Write-Host ""
        Write-Host "Attempting download..." -ForegroundColor Cyan

        if (Download-FileWithProgress -Url $url -OutputPath $InstallerPath) {
            # Verify file was downloaded and has content
            if ((Test-Path $InstallerPath) -and ((Get-Item $InstallerPath).Length -gt 1000000)) {
                Write-Host "Download successful!" -ForegroundColor Green
                return $true
            }
        }
    }

    return $false
}

# Check if already installed
function Test-Installed {
    $exePath = Join-Path $InstallDir "QBExtractor.exe"
    return Test-Path $exePath
}

# Run the installer
function Install-Application {
    if (-not (Test-Path $InstallerPath)) {
        Write-Host "Error: Installer not found at $InstallerPath" -ForegroundColor Red
        return $false
    }

    Write-Host ""
    Write-Host "Running installer..." -ForegroundColor Cyan

    try {
        if ($Silent) {
            Start-Process -FilePath $InstallerPath -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
        }
        else {
            Start-Process -FilePath $InstallerPath -Wait
        }

        Write-Host "Installation completed!" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "Installation failed: $_" -ForegroundColor Red
        return $false
    }
}

# Save session code for extractor
function Save-SessionCode {
    param([string]$Code)

    if ([string]::IsNullOrWhiteSpace($Code)) {
        return
    }

    $sessionFile = Join-Path $InstallDir "session.txt"

    # Create install directory if needed
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    # Save session code
    $Code | Out-File -FilePath $sessionFile -Encoding UTF8 -Force
    Write-Host "Session code saved for extractor." -ForegroundColor Green
}

# Main entry point
function Main {
    Show-Banner

    # Check Windows
    if ($env:OS -ne "Windows_NT") {
        Write-Host "Error: This script requires Windows." -ForegroundColor Red
        Write-Host "QuickBooks Desktop is only available on Windows." -ForegroundColor Yellow
        exit 1
    }

    # Check if already installed
    if (Test-Installed) {
        Write-Host "ForensicBridge Extractor is already installed." -ForegroundColor Green
        Write-Host ""

        $response = Read-Host "Do you want to reinstall? (y/N)"
        if ($response -ne "y" -and $response -ne "Y") {
            Write-Host "Skipping installation." -ForegroundColor Yellow

            # Save session code if provided
            if (-not [string]::IsNullOrWhiteSpace($SessionCode)) {
                Save-SessionCode -Code $SessionCode
            }

            # Offer to run extractor
            $runExtractor = Read-Host "Run the extractor now? (Y/n)"
            if ($runExtractor -ne "n" -and $runExtractor -ne "N") {
                $exePath = Join-Path $InstallDir "QBExtractor.exe"
                if ($SessionCode) {
                    Start-Process -FilePath $exePath -ArgumentList "--session", $SessionCode
                }
                else {
                    Start-Process -FilePath $exePath
                }
            }

            exit 0
        }
    }

    # Download installer
    Write-Host "Downloading ForensicBridge Extractor..." -ForegroundColor Cyan

    if (-not (Download-Installer)) {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Red
        Write-Host "  DOWNLOAD FAILED" -ForegroundColor Red
        Write-Host "============================================================" -ForegroundColor Red
        Write-Host ""
        Write-Host "The installer could not be downloaded automatically." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Please try one of these options:" -ForegroundColor White
        Write-Host ""
        Write-Host "  1. Visit GitHub Releases directly:" -ForegroundColor Cyan
        Write-Host "     https://github.com/sivaharanj7805/QBMigration/releases" -ForegroundColor White
        Write-Host ""
        Write-Host "  2. Contact support at:" -ForegroundColor Cyan
        Write-Host "     support@forensicbridge.com" -ForegroundColor White
        Write-Host ""
        Write-Host "  3. Check your internet connection and try again." -ForegroundColor Cyan
        Write-Host ""

        # Open browser to releases page
        $openBrowser = Read-Host "Open GitHub Releases in browser? (Y/n)"
        if ($openBrowser -ne "n" -and $openBrowser -ne "N") {
            Start-Process "https://github.com/sivaharanj7805/QBMigration/releases"
        }

        exit 1
    }

    # Install
    if (-not (Install-Application)) {
        Write-Host "Installation failed. Please try running the installer manually." -ForegroundColor Red
        Write-Host "Installer location: $InstallerPath" -ForegroundColor Yellow
        exit 1
    }

    # Save session code if provided
    if (-not [string]::IsNullOrWhiteSpace($SessionCode)) {
        Save-SessionCode -Code $SessionCode
    }

    # Cleanup
    Write-Host ""
    Write-Host "Cleaning up temporary files..." -ForegroundColor Cyan
    Remove-Item -Path $InstallerPath -Force -ErrorAction SilentlyContinue

    # Success message
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  INSTALLATION COMPLETE!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  ForensicBridge Extractor has been installed successfully." -ForegroundColor White
    Write-Host ""
    Write-Host "  Location: $InstallDir" -ForegroundColor Cyan
    Write-Host ""

    # Offer to run extractor
    if (-not $Silent) {
        $runExtractor = Read-Host "Run the extractor now? (Y/n)"
        if ($runExtractor -ne "n" -and $runExtractor -ne "N") {
            $exePath = Join-Path $InstallDir "QBExtractor.exe"
            if ($SessionCode) {
                Start-Process -FilePath $exePath -ArgumentList "--session", $SessionCode
            }
            else {
                Start-Process -FilePath $exePath
            }
        }
    }

    Write-Host ""
    Write-Host "Thank you for using ForensicBridge!" -ForegroundColor Cyan
    Write-Host ""
}

# Run main
Main
