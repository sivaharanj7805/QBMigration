# ============================================================================
# ForensicBridge Bootstrap Installer v2.0
# Downloads and runs the ForensicBridge QuickBooks Desktop Extractor
#
# This script:
# 1. Shows a professional GUI for session code entry
# 2. Downloads the real extractor from GitHub releases
# 3. Validates prerequisites (QuickBooks SDK)
# 4. Runs the extractor with the session code
# ============================================================================

param(
    [string]$SessionCode = "",
    [switch]$Silent = $false
)

$ErrorActionPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Configuration
$GitHubRepo = "sivaharanj7805/QBMigration"
$GitHubExeUrl = "https://github.com/$GitHubRepo/releases/latest/download/QBExtractor.exe"
$ServerApiUrl = "https://api.forensicbridge.ca/api/extractor"
$InstallDir = Join-Path $env:LOCALAPPDATA "ForensicBridge"
$ExtractorPath = Join-Path $InstallDir "QBExtractor.exe"

# Ensure install directory exists
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# ============================================================================
# Download Functions
# ============================================================================

function Download-Extractor {
    param([System.Windows.Forms.Label]$StatusLabel = $null)

    if (Test-Path $ExtractorPath) {
        $fileSize = (Get-Item $ExtractorPath).Length
        if ($fileSize -gt 50000) {
            return $true
        }
    }

    $methods = @(
        @{ Name = "primary server"; Url = "$ServerApiUrl/download-exe"; Timeout = 60 },
        @{ Name = "GitHub releases"; Url = $GitHubExeUrl; Timeout = 120 }
    )

    foreach ($method in $methods) {
        if ($StatusLabel) {
            $StatusLabel.Text = "Downloading from $($method.Name)..."
            $StatusLabel.Refresh()
        }

        try {
            Invoke-WebRequest -Uri $method.Url -OutFile $ExtractorPath -UseBasicParsing -TimeoutSec $method.Timeout
            if ((Test-Path $ExtractorPath) -and (Get-Item $ExtractorPath).Length -gt 50000) {
                return $true
            }
        } catch {
            continue
        }
    }

    # Method 3: GitHub API
    if ($StatusLabel) {
        $StatusLabel.Text = "Querying GitHub API..."
        $StatusLabel.Refresh()
    }

    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$GitHubRepo/releases/latest" -UseBasicParsing -TimeoutSec 30
        $asset = $release.assets | Where-Object { $_.name -like "*QBExtractor*.exe" } | Select-Object -First 1
        if ($asset) {
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $ExtractorPath -UseBasicParsing -TimeoutSec 120
            if ((Test-Path $ExtractorPath) -and (Get-Item $ExtractorPath).Length -gt 50000) {
                return $true
            }
        }
    } catch { }

    return $false
}

# ============================================================================
# GUI
# ============================================================================

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object Windows.Forms.Form
$form.Text = "ForensicBridge"
$form.Size = New-Object Drawing.Size(500, 380)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedSingle"
$form.MaximizeBox = $false
$form.BackColor = [Drawing.Color]::FromArgb(245, 247, 250)

# Header panel
$headerPanel = New-Object Windows.Forms.Panel
$headerPanel.Dock = "Top"
$headerPanel.Height = 70
$headerPanel.BackColor = [Drawing.Color]::FromArgb(37, 99, 235)
$form.Controls.Add($headerPanel)

$title = New-Object Windows.Forms.Label
$title.Text = "ForensicBridge"
$title.Font = New-Object Drawing.Font("Segoe UI", 20, [Drawing.FontStyle]::Bold)
$title.ForeColor = [Drawing.Color]::White
$title.Location = New-Object Drawing.Point(15, 8)
$title.AutoSize = $true
$headerPanel.Controls.Add($title)

$subtitle = New-Object Windows.Forms.Label
$subtitle.Text = "QuickBooks Desktop Data Migration Tool"
$subtitle.Font = New-Object Drawing.Font("Segoe UI", 9)
$subtitle.ForeColor = [Drawing.Color]::FromArgb(200, 220, 255)
$subtitle.Location = New-Object Drawing.Point(17, 42)
$subtitle.AutoSize = $true
$headerPanel.Controls.Add($subtitle)

# QB Status
$lblQBStatus = New-Object Windows.Forms.Label
$lblQBStatus.Font = New-Object Drawing.Font("Segoe UI", 9)
$lblQBStatus.Location = New-Object Drawing.Point(15, 80)
$lblQBStatus.Size = New-Object Drawing.Size(460, 20)
$form.Controls.Add($lblQBStatus)

$qbfcInstalled = $null -ne [Type]::GetTypeFromProgID("QBFC16.QBSessionManager")
if ($qbfcInstalled) {
    $lblQBStatus.Text = "QuickBooks SDK: Ready"
    $lblQBStatus.ForeColor = [Drawing.Color]::Green
} else {
    $lblQBStatus.Text = "QuickBooks SDK (QBFC16): Not detected - required for extraction"
    $lblQBStatus.ForeColor = [Drawing.Color]::Orange
}

# Session code section
$lblCode = New-Object Windows.Forms.Label
$lblCode.Text = "Session Code:"
$lblCode.Font = New-Object Drawing.Font("Segoe UI", 10, [Drawing.FontStyle]::Bold)
$lblCode.Location = New-Object Drawing.Point(15, 115)
$lblCode.AutoSize = $true
$form.Controls.Add($lblCode)

$txtCode = New-Object Windows.Forms.TextBox
$txtCode.Font = New-Object Drawing.Font("Consolas", 12)
$txtCode.Location = New-Object Drawing.Point(15, 140)
$txtCode.Size = New-Object Drawing.Size(300, 30)
$txtCode.CharacterCasing = "Upper"
if ($SessionCode) { $txtCode.Text = $SessionCode }
$form.Controls.Add($txtCode)

# Status label
$lblStatus = New-Object Windows.Forms.Label
$lblStatus.Text = "Enter your session code from the migration portal."
$lblStatus.Font = New-Object Drawing.Font("Segoe UI", 9)
$lblStatus.Location = New-Object Drawing.Point(15, 180)
$lblStatus.Size = New-Object Drawing.Size(460, 40)
$form.Controls.Add($lblStatus)

# Progress bar
$progressBar = New-Object Windows.Forms.ProgressBar
$progressBar.Location = New-Object Drawing.Point(15, 220)
$progressBar.Size = New-Object Drawing.Size(455, 20)
$progressBar.Style = "Continuous"
$progressBar.Visible = $false
$form.Controls.Add($progressBar)

# Start button
$btnStart = New-Object Windows.Forms.Button
$btnStart.Text = "Start Migration"
$btnStart.Font = New-Object Drawing.Font("Segoe UI", 11, [Drawing.FontStyle]::Bold)
$btnStart.Location = New-Object Drawing.Point(15, 255)
$btnStart.Size = New-Object Drawing.Size(220, 45)
$btnStart.BackColor = [Drawing.Color]::FromArgb(34, 197, 94)
$btnStart.ForeColor = [Drawing.Color]::White
$btnStart.FlatStyle = "Flat"
$btnStart.Cursor = "Hand"
$form.Controls.Add($btnStart)

# Exit button
$btnExit = New-Object Windows.Forms.Button
$btnExit.Text = "Exit"
$btnExit.Font = New-Object Drawing.Font("Segoe UI", 10)
$btnExit.Location = New-Object Drawing.Point(370, 255)
$btnExit.Size = New-Object Drawing.Size(100, 45)
$btnExit.FlatStyle = "Flat"
$btnExit.Cursor = "Hand"
$form.Controls.Add($btnExit)

# ============================================================================
# Button Handlers
# ============================================================================

$btnStart.Add_Click({
    $code = $txtCode.Text.Trim().ToUpper()

    if ($code.Length -lt 4) {
        $lblStatus.ForeColor = [Drawing.Color]::Red
        $lblStatus.Text = "Please enter a valid session code."
        return
    }

    $btnStart.Enabled = $false
    $progressBar.Visible = $true
    $progressBar.Value = 10

    # Check if extractor exists, download if needed
    $lblStatus.ForeColor = [Drawing.Color]::Blue
    $lblStatus.Text = "Checking extractor..."
    $form.Refresh()

    if (-not (Test-Path $ExtractorPath) -or (Get-Item $ExtractorPath -ErrorAction SilentlyContinue).Length -lt 50000) {
        $progressBar.Value = 20
        $lblStatus.Text = "Downloading ForensicBridge extractor..."
        $form.Refresh()

        $downloaded = Download-Extractor -StatusLabel $lblStatus

        if (-not $downloaded) {
            $lblStatus.ForeColor = [Drawing.Color]::Red
            $lblStatus.Text = "Download failed. Opening GitHub releases..."
            $progressBar.Visible = $false
            $btnStart.Enabled = $true
            Start-Process "https://github.com/$GitHubRepo/releases"
            return
        }
    }

    $progressBar.Value = 80
    $lblStatus.ForeColor = [Drawing.Color]::Blue
    $lblStatus.Text = "Starting ForensicBridge with session code..."
    $form.Refresh()

    # Launch the real extractor with the session code
    try {
        Start-Process -FilePath $ExtractorPath -ArgumentList "--session", $code -WorkingDirectory $InstallDir
        $progressBar.Value = 100
        $lblStatus.ForeColor = [Drawing.Color]::Green
        $lblStatus.Text = "ForensicBridge started! You can close this window."

        # Close this launcher after a short delay
        Start-Sleep -Seconds 2
        $form.Close()
    } catch {
        $lblStatus.ForeColor = [Drawing.Color]::Red
        $lblStatus.Text = "Failed to start extractor: $_"
        $progressBar.Visible = $false
        $btnStart.Enabled = $true
    }
})

$btnExit.Add_Click({ $form.Close() })

$form.Add_Shown({
    $txtCode.Focus()
    if ($SessionCode -and $SessionCode.Length -ge 4) {
        $btnStart.PerformClick()
    }
})

[void]$form.ShowDialog()
