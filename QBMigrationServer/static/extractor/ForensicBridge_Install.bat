@echo off
:: ForensicBridge Installer
:: Downloads and installs the ForensicBridge migration tool

setlocal
title ForensicBridge Setup
color 1F

echo.
echo  ============================================================
echo   ForensicBridge - QuickBooks Desktop Migration Tool
echo  ============================================================
echo.
echo   This will install ForensicBridge on your computer.
echo.
echo   Press any key to continue...
pause > nul

cls
echo.
echo  ============================================================
echo   Installing ForensicBridge...
echo  ============================================================
echo.

:: Set paths
set "INSTALL_DIR=%LOCALAPPDATA%\ForensicBridge"
set "PS_SCRIPT=%INSTALL_DIR%\ForensicBridge.ps1"
set "SERVER_URL=https://api.forensicbridge.ca/api/extractor/bootstrap-ps1"

:: Create directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" 2>nul
echo   Install location: %INSTALL_DIR%
echo.

:: Try to download the PowerShell installer from server
echo   Downloading from server...
powershell -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri '%SERVER_URL%' -OutFile '%PS_SCRIPT%' -UseBasicParsing; exit 0 } catch { exit 1 }"

:: Check if download succeeded and file has content
if exist "%PS_SCRIPT%" (
    for %%A in ("%PS_SCRIPT%") do if %%~zA GTR 100 (
        echo   Download successful!
        echo.
        echo   Running setup...
        powershell -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
        goto :FINISH
    )
)

:: Download failed - use simple fallback
echo   Server unavailable. Using offline mode.
echo.
echo   Creating simple launcher...

:: Create a VERY simple PowerShell script using PowerShell itself
powershell -ExecutionPolicy Bypass -Command "$s = 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show(\"Welcome to ForensicBridge!`n`nClick OK to open the migration portal where you can:`n- Enter your session code`n- Start data extraction`n- View migration status\", \"ForensicBridge\", \"OKCancel\", \"Information\") -eq \"OK\" | ForEach-Object { if ($_) { Start-Process \"https://forensicbridge.ca\" } }'; $s | Out-File -FilePath '%PS_SCRIPT%' -Encoding UTF8"

if not exist "%PS_SCRIPT%" (
    echo   Creating fallback script...
    echo Start-Process "https://forensicbridge.ca" > "%PS_SCRIPT%"
)

:: Create VBS launcher
echo Set WshShell = CreateObject("WScript.Shell") > "%INSTALL_DIR%\ForensicBridge.vbs"
echo WshShell.Run "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File " ^& Chr(34) ^& Replace(WScript.ScriptFullName, "ForensicBridge.vbs", "ForensicBridge.ps1") ^& Chr(34), 0, False >> "%INSTALL_DIR%\ForensicBridge.vbs"

:: Create desktop shortcut
echo   Creating shortcut...
powershell -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $shortcut = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\ForensicBridge.lnk'); $shortcut.TargetPath = 'wscript.exe'; $shortcut.Arguments = '\"' + $env:LOCALAPPDATA + '\ForensicBridge\ForensicBridge.vbs\"'; $shortcut.WorkingDirectory = $env:LOCALAPPDATA + '\ForensicBridge'; $shortcut.Save()" 2>nul

:FINISH
cls
echo.
echo  ============================================================
echo   Installation Complete!
echo  ============================================================
echo.
echo   ForensicBridge has been installed.
echo.
echo   Location: %INSTALL_DIR%
echo.
echo   A shortcut has been created on your Desktop.
echo.
echo  ============================================================
echo.

set /p "LAUNCH=   Launch ForensicBridge now? (Y/n): "
if /i not "%LAUNCH%"=="n" (
    echo.
    echo   Starting ForensicBridge...
    if exist "%INSTALL_DIR%\ForensicBridge.vbs" (
        start "" wscript.exe "%INSTALL_DIR%\ForensicBridge.vbs"
    ) else (
        start "" "https://forensicbridge.ca"
    )
)

echo.
echo   Press any key to exit...
pause > nul
