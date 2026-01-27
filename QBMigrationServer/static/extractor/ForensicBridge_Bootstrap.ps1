# ForensicBridge Extractor Bootstrap Script
# Version 2.0 - Smart installer with multiple fallbacks
# Run this script in PowerShell: .\ForensicBridge_Bootstrap.ps1

param(
    [string]$SessionCode = "",
    [switch]$Silent = $false
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Configuration
$AppName = "ForensicBridge"
$InstallerName = "ForensicBridge_Setup.exe"
$TempPath = Join-Path $env:TEMP "ForensicBridge"
$InstallerPath = Join-Path $TempPath $InstallerName
$InstallDir = Join-Path $env:LOCALAPPDATA "ForensicBridge"

# Download URLs (in order of priority)
$ServerUrl = "https://api.forensicbridge.ca"
$DownloadUrls = @(
    "$ServerUrl/api/extractor/download",
    "https://github.com/sivaharanj7805/QBMigration/releases/latest/download/ForensicBridge_Setup.exe",
    "https://github.com/sivaharanj7805/QBMigration/releases/download/v1.0.0/ForensicBridge_Setup.exe"
)

# Banner
function Show-Banner {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  ForensicBridge Extractor - Smart Bootstrap Installer" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  This script will download and install the ForensicBridge" -ForegroundColor White
    Write-Host "  Extractor for QuickBooks Desktop data migration." -ForegroundColor White
    Write-Host ""
}

# Check server status and installer availability
function Get-ServerStatus {
    try {
        $response = Invoke-RestMethod -Uri "$ServerUrl/api/extractor/info" -TimeoutSec 10
        return $response
    }
    catch {
        Write-Host "  Server check failed: $($_.Exception.Message)" -ForegroundColor Yellow
        return $null
    }
}

# Download file with progress
function Download-FileWithProgress {
    param(
        [string]$Url,
        [string]$OutputPath,
        [string]$SourceName = "source"
    )

    Write-Host "  Downloading from $SourceName..." -ForegroundColor Yellow
    Write-Host "  URL: $Url" -ForegroundColor DarkGray

    try {
        $webClient = New-Object System.Net.WebClient
        $webClient.DownloadFile($Url, $OutputPath)

        if (Test-Path $OutputPath) {
            $fileSize = (Get-Item $OutputPath).Length
            if ($fileSize -gt 1000000) {
                Write-Host "  Download successful! Size: $([math]::Round($fileSize/1MB, 2)) MB" -ForegroundColor Green
                return $true
            }
            else {
                Write-Host "  Downloaded file too small (likely error page)" -ForegroundColor Yellow
                Remove-Item $OutputPath -Force -ErrorAction SilentlyContinue
                return $false
            }
        }
        return $false
    }
    catch {
        Write-Host "  Download failed: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

# Try to download from multiple URLs
function Download-Installer {
    # Create temp directory
    if (-not (Test-Path $TempPath)) {
        New-Item -ItemType Directory -Path $TempPath -Force | Out-Null
    }

    # Clean any existing partial download
    if (Test-Path $InstallerPath) {
        Remove-Item $InstallerPath -Force -ErrorAction SilentlyContinue
    }

    Write-Host ""
    Write-Host "Attempting download from available sources..." -ForegroundColor Cyan
    Write-Host ""

    # Priority 1: Check server for local installer
    Write-Host "[1/3] Checking ForensicBridge server..." -ForegroundColor White
    $serverStatus = Get-ServerStatus

    if ($serverStatus -and $serverStatus.source -eq "local") {
        Write-Host "  Server has installer available!" -ForegroundColor Green
        if (Download-FileWithProgress -Url $DownloadUrls[0] -OutputPath $InstallerPath -SourceName "ForensicBridge Server") {
            return $true
        }
    }
    else {
        Write-Host "  Server does not have pre-built installer" -ForegroundColor Yellow
    }

    # Priority 2: Try GitHub releases
    Write-Host ""
    Write-Host "[2/3] Trying GitHub releases..." -ForegroundColor White
    foreach ($url in $DownloadUrls | Select-Object -Skip 1) {
        if (Download-FileWithProgress -Url $url -OutputPath $InstallerPath -SourceName "GitHub") {
            return $true
        }
    }

    # Priority 3: Use embedded PowerShell installer
    Write-Host ""
    Write-Host "[3/3] Using embedded installer..." -ForegroundColor White
    return $false
}

# Install the embedded PowerShell-based launcher
function Install-EmbeddedLauncher {
    Write-Host ""
    Write-Host "Creating ForensicBridge launcher (no pre-built installer available)..." -ForegroundColor Cyan
    Write-Host ""

    # Create install directory
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    # Create the main launcher script
    $launcherContent = @'
# ForensicBridge Launcher
# This script helps connect to your migration session

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'ForensicBridge - QuickBooks Migration'
$form.Size = New-Object System.Drawing.Size(500, 400)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedSingle'
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::White

$label = New-Object System.Windows.Forms.Label
$label.Location = New-Object System.Drawing.Point(20, 20)
$label.Size = New-Object System.Drawing.Size(450, 60)
$label.Text = "Welcome to ForensicBridge QuickBooks Migration Tool!`n`nEnter your session code to begin the data extraction process."
$label.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$form.Controls.Add($label)

$codeLabel = New-Object System.Windows.Forms.Label
$codeLabel.Location = New-Object System.Drawing.Point(20, 100)
$codeLabel.Size = New-Object System.Drawing.Size(100, 25)
$codeLabel.Text = 'Session Code:'
$codeLabel.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$form.Controls.Add($codeLabel)

$textBox = New-Object System.Windows.Forms.TextBox
$textBox.Location = New-Object System.Drawing.Point(130, 97)
$textBox.Size = New-Object System.Drawing.Size(200, 25)
$textBox.Font = New-Object System.Drawing.Font('Consolas', 12)
$textBox.CharacterCasing = 'Upper'
$form.Controls.Add($textBox)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Location = New-Object System.Drawing.Point(20, 140)
$statusLabel.Size = New-Object System.Drawing.Size(450, 100)
$statusLabel.Text = ''
$statusLabel.Font = New-Object System.Drawing.Font('Segoe UI', 9)
$form.Controls.Add($statusLabel)

$connectBtn = New-Object System.Windows.Forms.Button
$connectBtn.Location = New-Object System.Drawing.Point(20, 260)
$connectBtn.Size = New-Object System.Drawing.Size(120, 35)
$connectBtn.Text = 'Connect'
$connectBtn.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$connectBtn.BackColor = [System.Drawing.Color]::FromArgb(0, 120, 212)
$connectBtn.ForeColor = [System.Drawing.Color]::White
$connectBtn.FlatStyle = 'Flat'
$form.Controls.Add($connectBtn)

$helpBtn = New-Object System.Windows.Forms.Button
$helpBtn.Location = New-Object System.Drawing.Point(150, 260)
$helpBtn.Size = New-Object System.Drawing.Size(120, 35)
$helpBtn.Text = 'Help'
$helpBtn.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$helpBtn.FlatStyle = 'Flat'
$form.Controls.Add($helpBtn)

$exitBtn = New-Object System.Windows.Forms.Button
$exitBtn.Location = New-Object System.Drawing.Point(350, 310)
$exitBtn.Size = New-Object System.Drawing.Size(100, 35)
$exitBtn.Text = 'Exit'
$exitBtn.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$exitBtn.FlatStyle = 'Flat'
$form.Controls.Add($exitBtn)

$connectBtn.Add_Click({
    $code = $textBox.Text.Trim().ToUpper()
    if ($code.Length -ne 6) {
        $statusLabel.ForeColor = [System.Drawing.Color]::Red
        $statusLabel.Text = 'Please enter a valid 6-character session code.'
        return
    }

    $statusLabel.ForeColor = [System.Drawing.Color]::Blue
    $statusLabel.Text = 'Validating session code...'
    $form.Refresh()

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $response = Invoke-RestMethod -Uri "https://api.forensicbridge.ca/api/sessions/$code/validate" -Method POST -TimeoutSec 30

        if ($response.valid) {
            $statusLabel.ForeColor = [System.Drawing.Color]::Green
            $statusLabel.Text = "Session validated!`n`nCompany: $($response.company_name)`nStatus: Ready for extraction`n`nOpening migration portal..."
            $form.Refresh()
            Start-Sleep -Seconds 2
            Start-Process "https://forensicbridge.ca/extract?session=$code"
        } else {
            $statusLabel.ForeColor = [System.Drawing.Color]::Red
            $statusLabel.Text = 'Invalid or expired session code. Please check and try again.'
        }
    } catch {
        $statusLabel.ForeColor = [System.Drawing.Color]::Orange
        $statusLabel.Text = "Could not connect to server.`n`nPlease visit: https://forensicbridge.ca`nand enter your session code manually."
    }
})

$helpBtn.Add_Click({
    Start-Process 'https://forensicbridge.ca/help/extractor'
})

$exitBtn.Add_Click({
    $form.Close()
})

# Check for command line session code
$args = [Environment]::GetCommandLineArgs()
foreach ($arg in $args) {
    if ($arg -match '^[A-Z0-9]{6}$') {
        $textBox.Text = $arg
        break
    }
}

$form.Add_Shown({$textBox.Select()})
[void]$form.ShowDialog()
'@

    # Save the launcher
    $launcherPath = Join-Path $InstallDir 'ForensicBridge.ps1'
    $launcherContent | Out-File -FilePath $launcherPath -Encoding UTF8
    Write-Host "  Created: ForensicBridge.ps1" -ForegroundColor Green

    # Create a batch file to run the launcher easily
    $batchContent = @"
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0ForensicBridge.ps1" %*
"@
    $batchPath = Join-Path $InstallDir 'ForensicBridge.bat'
    $batchContent | Out-File -FilePath $batchPath -Encoding ASCII
    Write-Host "  Created: ForensicBridge.bat" -ForegroundColor Green

    # Create a VBS launcher to hide the console window
    $vbsContent = @'
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & Replace(WScript.ScriptFullName, "ForensicBridge.vbs", "ForensicBridge.ps1") & """", 0, False
'@
    $vbsPath = Join-Path $InstallDir 'ForensicBridge.vbs'
    $vbsContent | Out-File -FilePath $vbsPath -Encoding ASCII
    Write-Host "  Created: ForensicBridge.vbs" -ForegroundColor Green

    # Create desktop shortcut
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shortcutPath = Join-Path $desktop 'ForensicBridge.lnk'
        $WshShell = New-Object -ComObject WScript.Shell
        $shortcut = $WshShell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = 'wscript.exe'
        $shortcut.Arguments = "`"$vbsPath`""
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.Description = 'ForensicBridge QuickBooks Migration Tool'
        $shortcut.Save()
        Write-Host "  Created desktop shortcut" -ForegroundColor Green
    }
    catch {
        Write-Host "  Could not create desktop shortcut: $_" -ForegroundColor Yellow
    }

    return $true
}

# Check if already installed
function Test-Installed {
    $exePath = Join-Path $InstallDir "ForensicBridge.ps1"
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
        Write-Host "ForensicBridge is already installed." -ForegroundColor Green
        Write-Host ""

        if (-not $Silent) {
            $response = Read-Host "Do you want to reinstall? (y/N)"
            if ($response -ne "y" -and $response -ne "Y") {
                Write-Host "Skipping installation." -ForegroundColor Yellow

                # Save session code if provided
                if (-not [string]::IsNullOrWhiteSpace($SessionCode)) {
                    Save-SessionCode -Code $SessionCode
                }

                # Offer to run extractor
                $runExtractor = Read-Host "Run ForensicBridge now? (Y/n)"
                if ($runExtractor -ne "n" -and $runExtractor -ne "N") {
                    $vbsPath = Join-Path $InstallDir "ForensicBridge.vbs"
                    if (Test-Path $vbsPath) {
                        Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`""
                    }
                    else {
                        $ps1Path = Join-Path $InstallDir "ForensicBridge.ps1"
                        Start-Process "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$ps1Path`""
                    }
                }

                exit 0
            }
        }
    }

    # Try to download installer
    $downloadSuccess = Download-Installer

    if ($downloadSuccess) {
        # We have a full installer, run it
        if (-not (Install-Application)) {
            Write-Host "Installation failed. Please try running the installer manually." -ForegroundColor Red
            Write-Host "Installer location: $InstallerPath" -ForegroundColor Yellow
            exit 1
        }
    }
    else {
        # No installer available, use embedded launcher
        Write-Host ""
        Write-Host "No pre-built installer available. Installing embedded launcher..." -ForegroundColor Yellow

        if (-not (Install-EmbeddedLauncher)) {
            Write-Host ""
            Write-Host "============================================================" -ForegroundColor Red
            Write-Host "  INSTALLATION FAILED" -ForegroundColor Red
            Write-Host "============================================================" -ForegroundColor Red
            Write-Host ""
            Write-Host "Could not install ForensicBridge." -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Please visit: https://forensicbridge.ca/download" -ForegroundColor Cyan
            Write-Host "Or contact: support@forensicbridge.com" -ForegroundColor Cyan
            Write-Host ""

            if (-not $Silent) {
                Start-Process "https://forensicbridge.ca/download"
            }
            exit 1
        }
    }

    # Save session code if provided
    if (-not [string]::IsNullOrWhiteSpace($SessionCode)) {
        Save-SessionCode -Code $SessionCode
    }

    # Cleanup installer if exists
    if (Test-Path $InstallerPath) {
        Write-Host ""
        Write-Host "Cleaning up temporary files..." -ForegroundColor Cyan
        Remove-Item -Path $InstallerPath -Force -ErrorAction SilentlyContinue
    }

    # Success message
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  INSTALLATION COMPLETE!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  ForensicBridge has been installed successfully." -ForegroundColor White
    Write-Host ""
    Write-Host "  Location: $InstallDir" -ForegroundColor Cyan
    Write-Host ""

    # Offer to run
    if (-not $Silent) {
        $runExtractor = Read-Host "Run ForensicBridge now? (Y/n)"
        if ($runExtractor -ne "n" -and $runExtractor -ne "N") {
            $vbsPath = Join-Path $InstallDir "ForensicBridge.vbs"
            if (Test-Path $vbsPath) {
                Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`""
            }
            else {
                $ps1Path = Join-Path $InstallDir "ForensicBridge.ps1"
                Start-Process "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$ps1Path`""
            }
        }
    }

    Write-Host ""
    Write-Host "Thank you for using ForensicBridge!" -ForegroundColor Cyan
    Write-Host ""
}

# Run main
Main
