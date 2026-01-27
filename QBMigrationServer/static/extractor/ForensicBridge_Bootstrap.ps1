# ForensicBridge Bootstrap Installer
# Creates ForensicBridge launcher on Windows

param(
    [string]$SessionCode = ""
)

$ErrorActionPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Configuration
$InstallDir = Join-Path $env:LOCALAPPDATA "ForensicBridge"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ForensicBridge Installer" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Create install directory
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
Write-Host "  Install directory: $InstallDir" -ForegroundColor White

# Create the launcher script
Write-Host "  Creating launcher..." -ForegroundColor White

$LauncherScript = @'
# ForensicBridge Launcher
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object Windows.Forms.Form
$form.Text = "ForensicBridge"
$form.Size = New-Object Drawing.Size(460, 300)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedSingle"
$form.MaximizeBox = $false
$form.BackColor = [Drawing.Color]::FromArgb(245, 247, 250)

# Title
$title = New-Object Windows.Forms.Label
$title.Text = "ForensicBridge"
$title.Font = New-Object Drawing.Font("Segoe UI", 20, [Drawing.FontStyle]::Bold)
$title.ForeColor = [Drawing.Color]::FromArgb(37, 99, 235)
$title.Location = New-Object Drawing.Point(20, 15)
$title.AutoSize = $true
$form.Controls.Add($title)

# Subtitle
$subtitle = New-Object Windows.Forms.Label
$subtitle.Text = "QuickBooks Desktop Migration Tool"
$subtitle.Font = New-Object Drawing.Font("Segoe UI", 9)
$subtitle.ForeColor = [Drawing.Color]::Gray
$subtitle.Location = New-Object Drawing.Point(22, 50)
$subtitle.AutoSize = $true
$form.Controls.Add($subtitle)

# Session code label
$lblCode = New-Object Windows.Forms.Label
$lblCode.Text = "Session Code:"
$lblCode.Font = New-Object Drawing.Font("Segoe UI", 10)
$lblCode.Location = New-Object Drawing.Point(20, 100)
$lblCode.AutoSize = $true
$form.Controls.Add($lblCode)

# Session code textbox
$txtCode = New-Object Windows.Forms.TextBox
$txtCode.Font = New-Object Drawing.Font("Consolas", 14)
$txtCode.Location = New-Object Drawing.Point(130, 96)
$txtCode.Size = New-Object Drawing.Size(150, 30)
$txtCode.CharacterCasing = "Upper"
$txtCode.MaxLength = 6
$form.Controls.Add($txtCode)

# Status message
$lblStatus = New-Object Windows.Forms.Label
$lblStatus.Text = "Enter your 6-character session code from the migration portal."
$lblStatus.Font = New-Object Drawing.Font("Segoe UI", 9)
$lblStatus.Location = New-Object Drawing.Point(20, 140)
$lblStatus.Size = New-Object Drawing.Size(420, 40)
$form.Controls.Add($lblStatus)

# Start button
$btnStart = New-Object Windows.Forms.Button
$btnStart.Text = "Start Migration"
$btnStart.Font = New-Object Drawing.Font("Segoe UI", 11, [Drawing.FontStyle]::Bold)
$btnStart.Location = New-Object Drawing.Point(20, 185)
$btnStart.Size = New-Object Drawing.Size(180, 40)
$btnStart.BackColor = [Drawing.Color]::FromArgb(37, 99, 235)
$btnStart.ForeColor = [Drawing.Color]::White
$btnStart.FlatStyle = "Flat"
$btnStart.Cursor = "Hand"
$form.Controls.Add($btnStart)

# Portal button
$btnPortal = New-Object Windows.Forms.Button
$btnPortal.Text = "Open Portal"
$btnPortal.Font = New-Object Drawing.Font("Segoe UI", 10)
$btnPortal.Location = New-Object Drawing.Point(210, 185)
$btnPortal.Size = New-Object Drawing.Size(110, 40)
$btnPortal.FlatStyle = "Flat"
$btnPortal.Cursor = "Hand"
$form.Controls.Add($btnPortal)

# Exit button
$btnExit = New-Object Windows.Forms.Button
$btnExit.Text = "Exit"
$btnExit.Font = New-Object Drawing.Font("Segoe UI", 10)
$btnExit.Location = New-Object Drawing.Point(330, 185)
$btnExit.Size = New-Object Drawing.Size(100, 40)
$btnExit.FlatStyle = "Flat"
$btnExit.Cursor = "Hand"
$form.Controls.Add($btnExit)

# Button click handlers
$btnStart.Add_Click({
    $code = $txtCode.Text.Trim().ToUpper()
    if ($code.Length -ne 6) {
        $lblStatus.ForeColor = [Drawing.Color]::Red
        $lblStatus.Text = "Please enter a valid 6-character session code."
        return
    }
    $lblStatus.ForeColor = [Drawing.Color]::Blue
    $lblStatus.Text = "Opening migration portal..."
    $form.Refresh()
    Start-Process "https://forensicbridge.ca/extract?session=$code"
})

$btnPortal.Add_Click({ Start-Process "https://forensicbridge.ca" })
$btnExit.Add_Click({ $form.Close() })
$form.Add_Shown({ $txtCode.Focus() })

[void]$form.ShowDialog()
'@

$LauncherPath = Join-Path $InstallDir "ForensicBridge.ps1"
$LauncherScript | Out-File -FilePath $LauncherPath -Encoding UTF8
Write-Host "  [OK] ForensicBridge.ps1" -ForegroundColor Green

# Create batch launcher
$BatchContent = '@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0ForensicBridge.ps1"'
$BatchPath = Join-Path $InstallDir "ForensicBridge.bat"
$BatchContent | Out-File -FilePath $BatchPath -Encoding ASCII
Write-Host "  [OK] ForensicBridge.bat" -ForegroundColor Green

# Create VBS launcher (hides console)
$VbsContent = @'
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & Replace(WScript.ScriptFullName, "ForensicBridge.vbs", "ForensicBridge.ps1") & """", 0, False
'@
$VbsPath = Join-Path $InstallDir "ForensicBridge.vbs"
$VbsContent | Out-File -FilePath $VbsPath -Encoding ASCII
Write-Host "  [OK] ForensicBridge.vbs" -ForegroundColor Green

# Create desktop shortcut
Write-Host "  Creating shortcut..." -ForegroundColor White
try {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("$Desktop\ForensicBridge.lnk")
    $Shortcut.TargetPath = "wscript.exe"
    $Shortcut.Arguments = "`"$VbsPath`""
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "ForensicBridge QuickBooks Migration"
    $Shortcut.Save()
    Write-Host "  [OK] Desktop shortcut" -ForegroundColor Green
} catch {
    Write-Host "  [--] Could not create shortcut" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  ForensicBridge installed to: $InstallDir" -ForegroundColor Cyan
Write-Host ""

# Ask to launch
$Launch = Read-Host "  Launch ForensicBridge now? (Y/n)"
if ($Launch -ne "n" -and $Launch -ne "N") {
    Write-Host "  Starting ForensicBridge..." -ForegroundColor White
    Start-Process "wscript.exe" -ArgumentList "`"$VbsPath`""
}

Write-Host ""
