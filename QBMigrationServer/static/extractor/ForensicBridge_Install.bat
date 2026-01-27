@echo off
:: ForensicBridge Extractor - Smart Installer
:: This script downloads the ForensicBridge extractor from the best available source
:: Version 2.0 - Server-first approach with multiple fallbacks

setlocal EnableDelayedExpansion
title ForensicBridge Extractor Installer

echo.
echo ============================================================
echo   ForensicBridge Extractor - Smart Installer
echo ============================================================
echo.
echo This will download and install the ForensicBridge Extractor
echo for QuickBooks Desktop data migration.
echo.
echo Press any key to continue or close this window to cancel...
pause > nul

:: Configuration
set "SERVER_URL=https://api.forensicbridge.ca"
set "GITHUB_URL=https://github.com/sivaharanj7805/QBMigration/releases/latest/download/ForensicBridge_Setup.exe"
set "GITHUB_RELEASES=https://github.com/sivaharanj7805/QBMigration/releases"

:: Create temp directory
set "TEMP_DIR=%TEMP%\ForensicBridge"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

set "INSTALLER=%TEMP_DIR%\ForensicBridge_Setup.exe"
set "DOWNLOAD_SUCCESS=0"

echo.
echo Checking download sources...
echo.

:: =============================================================
:: PRIORITY 1: Try server API first (most reliable)
:: The server will either serve the installer or a smart fallback
:: =============================================================

echo [1/4] Trying ForensicBridge server...

:: First check if server has the installer info
powershell -Command "& { try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $response = Invoke-RestMethod -Uri '%SERVER_URL%/api/extractor/info' -TimeoutSec 10; if ($response.source -eq 'local') { Write-Host '  Server has installer ready!' -ForegroundColor Green; exit 0 } else { Write-Host '  Server will use bootstrap method' -ForegroundColor Yellow; exit 1 } } catch { Write-Host '  Server unavailable' -ForegroundColor Yellow; exit 1 } }"

if %errorLevel% equ 0 (
    echo.
    echo Downloading from ForensicBridge server...
    powershell -Command "& { try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $wc = New-Object Net.WebClient; $wc.DownloadFile('%SERVER_URL%/api/extractor/download', '%INSTALLER%'); exit 0 } catch { exit 1 } }"

    if !errorLevel! equ 0 (
        if exist "%INSTALLER%" (
            for %%A in ("%INSTALLER%") do set "FILE_SIZE=%%~zA"
            if !FILE_SIZE! GTR 1000000 (
                set "DOWNLOAD_SUCCESS=1"
                echo Download successful from server!
                goto :VERIFY_AND_INSTALL
            )
        )
    )
)

:: =============================================================
:: PRIORITY 2: Try GitHub releases
:: =============================================================

echo.
echo [2/4] Trying GitHub releases...

:: Delete any partial download
if exist "%INSTALLER%" del "%INSTALLER%" 2>nul

powershell -Command "& { try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $wc = New-Object Net.WebClient; $wc.DownloadFile('%GITHUB_URL%', '%INSTALLER%'); exit 0 } catch { Write-Host ('  ' + $_.Exception.Message) -ForegroundColor Yellow; exit 1 } }"

if %errorLevel% equ 0 (
    if exist "%INSTALLER%" (
        for %%A in ("%INSTALLER%") do set "FILE_SIZE=%%~zA"
        if !FILE_SIZE! GTR 1000000 (
            set "DOWNLOAD_SUCCESS=1"
            echo   Download successful from GitHub!
            goto :VERIFY_AND_INSTALL
        ) else (
            echo   Downloaded file too small (likely 404 page)
        )
    )
)

:: =============================================================
:: PRIORITY 3: Try curl (Windows 10+)
:: =============================================================

echo.
echo [3/4] Trying alternative download method (curl)...

if exist "%INSTALLER%" del "%INSTALLER%" 2>nul

curl --version >nul 2>&1
if %errorLevel% equ 0 (
    curl -L -s -o "%INSTALLER%" "%GITHUB_URL%" 2>nul

    if exist "%INSTALLER%" (
        for %%A in ("%INSTALLER%") do set "FILE_SIZE=%%~zA"
        if !FILE_SIZE! GTR 1000000 (
            set "DOWNLOAD_SUCCESS=1"
            echo   Download successful via curl!
            goto :VERIFY_AND_INSTALL
        )
    )
)

echo   curl not available or download failed

:: =============================================================
:: PRIORITY 4: Embedded PowerShell Installer
:: This doesn't require any external downloads
:: =============================================================

echo.
echo [4/4] Using embedded installer method...
echo.
echo NOTE: No pre-built installer available. Using PowerShell-based setup.
echo This will set up ForensicBridge directly without a separate installer.
echo.

:: Create the ForensicBridge directory
set "INSTALL_DIR=%LOCALAPPDATA%\ForensicBridge"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Create a PowerShell-based extractor launcher
echo Creating ForensicBridge launcher...

powershell -Command "& {
    $installDir = '%INSTALL_DIR%'

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

$label = New-Object System.Windows.Forms.Label
$label.Location = New-Object System.Drawing.Point(20, 20)
$label.Size = New-Object System.Drawing.Size(450, 60)
$label.Text = 'Welcome to ForensicBridge QuickBooks Migration Tool!`n`nEnter your session code to begin the data extraction process.'
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
$form.Controls.Add($connectBtn)

$helpBtn = New-Object System.Windows.Forms.Button
$helpBtn.Location = New-Object System.Drawing.Point(150, 260)
$helpBtn.Size = New-Object System.Drawing.Size(120, 35)
$helpBtn.Text = 'Help'
$helpBtn.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$form.Controls.Add($helpBtn)

$exitBtn = New-Object System.Windows.Forms.Button
$exitBtn.Location = New-Object System.Drawing.Point(350, 310)
$exitBtn.Size = New-Object System.Drawing.Size(100, 35)
$exitBtn.Text = 'Exit'
$exitBtn.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$form.Controls.Add($exitBtn)

$connectBtn.Add_Click({
    $code = $textBox.Text.Trim().ToUpper()
    if ($code.Length -ne 6) {
        $statusLabel.ForeColor = 'Red'
        $statusLabel.Text = 'Please enter a valid 6-character session code.'
        return
    }

    $statusLabel.ForeColor = 'Blue'
    $statusLabel.Text = 'Validating session code...'
    $form.Refresh()

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $response = Invoke-RestMethod -Uri \"https://api.forensicbridge.ca/api/sessions/$code/validate\" -Method POST -TimeoutSec 30

        if ($response.valid) {
            $statusLabel.ForeColor = 'Green'
            $statusLabel.Text = \"Session validated!`n`nCompany: $($response.company_name)`nStatus: Ready for extraction`n`nOpening migration portal...\"
            $form.Refresh()
            Start-Sleep -Seconds 2
            Start-Process \"https://forensicbridge.ca/extract?session=$code\"
        } else {
            $statusLabel.ForeColor = 'Red'
            $statusLabel.Text = 'Invalid or expired session code. Please check and try again.'
        }
    } catch {
        $statusLabel.ForeColor = 'Orange'
        $statusLabel.Text = \"Could not connect to server.`n`nPlease visit: https://forensicbridge.ca`nand enter your session code manually.\"
    }
})

$helpBtn.Add_Click({
    Start-Process 'https://forensicbridge.ca/help/extractor'
})

$exitBtn.Add_Click({
    $form.Close()
})

$form.Add_Shown({$textBox.Select()})
[void]$form.ShowDialog()
'@

    # Save the launcher
    $launcherPath = Join-Path $installDir 'ForensicBridge.ps1'
    $launcherContent | Out-File -FilePath $launcherPath -Encoding UTF8

    # Create a batch file to run the launcher easily
    $batchContent = @'
@echo off
powershell -ExecutionPolicy Bypass -File \"%~dp0ForensicBridge.ps1\"
'@
    $batchPath = Join-Path $installDir 'ForensicBridge.bat'
    $batchContent | Out-File -FilePath $batchPath -Encoding ASCII

    # Create a VBS launcher to hide the console window
    $vbsContent = @'
Set WshShell = CreateObject(\"WScript.Shell\")
WshShell.Run \"powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File \"\"\" & Replace(WScript.ScriptFullName, \"ForensicBridge.vbs\", \"ForensicBridge.ps1\") & \"\"\"\", 0, False
'@
    $vbsPath = Join-Path $installDir 'ForensicBridge.vbs'
    $vbsContent | Out-File -FilePath $vbsPath -Encoding ASCII

    # Create desktop shortcut
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'ForensicBridge.lnk'
    $WshShell = New-Object -ComObject WScript.Shell
    $shortcut = $WshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = 'wscript.exe'
    $shortcut.Arguments = \"`\"$vbsPath`\"\"
    $shortcut.WorkingDirectory = $installDir
    $shortcut.Description = 'ForensicBridge QuickBooks Migration Tool'
    $shortcut.Save()

    Write-Host 'ForensicBridge has been installed!' -ForegroundColor Green
    Write-Host ''
    Write-Host 'Location: ' -NoNewline
    Write-Host $installDir -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'A shortcut has been created on your desktop.' -ForegroundColor Yellow
}"

if %errorLevel% equ 0 (
    echo.
    echo ============================================================
    echo   INSTALLATION COMPLETE!
    echo ============================================================
    echo.
    echo ForensicBridge has been installed to:
    echo   %INSTALL_DIR%
    echo.
    echo A shortcut has been created on your Desktop.
    echo.
    echo Would you like to run ForensicBridge now?
    set /p "RUN_NOW=Run now? (Y/n): "
    if /i not "!RUN_NOW!"=="n" (
        start "" wscript.exe "%INSTALL_DIR%\ForensicBridge.vbs"
    )
    echo.
    echo Press any key to exit...
    pause > nul
    exit /b 0
)

echo   Embedded installation failed.
goto :DOWNLOAD_FAILED

:VERIFY_AND_INSTALL
:: =============================================================
:: Verify downloaded file and run installer
:: =============================================================

echo.
echo Verifying download...

if not exist "%INSTALLER%" (
    echo Download verification failed - file not found.
    goto :DOWNLOAD_FAILED
)

:: Check file size (should be > 1MB for a real installer)
for %%A in ("%INSTALLER%") do set "FILE_SIZE=%%~zA"
if %FILE_SIZE% LSS 1000000 (
    echo Download incomplete or corrupted (file too small: %FILE_SIZE% bytes).
    del "%INSTALLER%" 2>nul
    goto :DOWNLOAD_FAILED
)

echo Download verified! File size: %FILE_SIZE% bytes
echo.
echo Starting installer...
echo.

:: Run the installer
start "" /wait "%INSTALLER%"

if %errorLevel% equ 0 (
    echo.
    echo ============================================================
    echo   INSTALLATION COMPLETE!
    echo ============================================================
    echo.
    echo ForensicBridge Extractor has been installed.
    echo.
    echo You can run the extractor from:
    echo   - Start Menu: ForensicBridge
    echo   - Or: %LOCALAPPDATA%\ForensicBridge\
    echo.
) else (
    echo.
    echo Installation may have been cancelled or encountered an error.
    echo The installer is saved at: %INSTALLER%
    echo.
)

:: Cleanup
del "%INSTALLER%" 2>nul

echo Press any key to exit...
pause > nul
exit /b 0

:DOWNLOAD_FAILED
:: =============================================================
:: All download methods failed
:: =============================================================

echo.
echo ============================================================
echo   SETUP OPTIONS
echo ============================================================
echo.
echo The automatic installer download is not currently available.
echo.
echo Please choose an option:
echo.
echo   1. Visit ForensicBridge website (recommended)
echo   2. Check GitHub Releases
echo   3. Contact Support
echo   4. Exit
echo.
set /p "CHOICE=Enter choice (1-4): "

if "%CHOICE%"=="1" (
    start "" "https://forensicbridge.ca/download"
) else if "%CHOICE%"=="2" (
    start "" "%GITHUB_RELEASES%"
) else if "%CHOICE%"=="3" (
    echo.
    echo Contact support at: support@forensicbridge.com
    echo.
)

echo.
echo Press any key to exit...
pause > nul
exit /b 1
