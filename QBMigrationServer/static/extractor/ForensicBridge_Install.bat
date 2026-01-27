@echo off
:: ForensicBridge Extractor - Easy Installer
:: Double-click this file to download and install ForensicBridge

title ForensicBridge Extractor Installer

echo.
echo ============================================================
echo   ForensicBridge Extractor - Easy Installer
echo ============================================================
echo.
echo This will download and install the ForensicBridge Extractor
echo for QuickBooks Desktop data migration.
echo.
echo Press any key to continue or close this window to cancel...
pause > nul

:: Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo Note: Some features may require administrator privileges.
    echo If installation fails, right-click and "Run as administrator"
    echo.
)

:: Create temp directory
set "TEMP_DIR=%TEMP%\ForensicBridge"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

set "INSTALLER=%TEMP_DIR%\ForensicBridge_Setup.exe"
set "DOWNLOAD_URL=https://github.com/sivaharanj7805/QBMigration/releases/latest/download/ForensicBridge_Setup.exe"

echo.
echo Downloading ForensicBridge Extractor...
echo.

:: Try PowerShell download first (most reliable)
powershell -Command "& { try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%DOWNLOAD_URL%', '%INSTALLER%'); Write-Host 'Download complete!' -ForegroundColor Green } catch { Write-Host 'Download failed.' -ForegroundColor Red; exit 1 } }"

if %errorLevel% neq 0 (
    echo.
    echo Trying alternative download method...

    :: Try curl (Windows 10+)
    curl -L -o "%INSTALLER%" "%DOWNLOAD_URL%" 2>nul

    if %errorLevel% neq 0 (
        echo.
        echo ============================================================
        echo   DOWNLOAD FAILED
        echo ============================================================
        echo.
        echo Could not download the installer automatically.
        echo.
        echo Please download manually from:
        echo   https://github.com/sivaharanj7805/QBMigration/releases
        echo.
        echo Opening browser...
        start "" "https://github.com/sivaharanj7805/QBMigration/releases"
        echo.
        pause
        exit /b 1
    )
)

:: Verify download
if not exist "%INSTALLER%" (
    echo.
    echo Download verification failed. File not found.
    echo Please download manually from GitHub Releases.
    echo.
    start "" "https://github.com/sivaharanj7805/QBMigration/releases"
    pause
    exit /b 1
)

:: Check file size (should be > 1MB)
for %%A in ("%INSTALLER%") do set "FILE_SIZE=%%~zA"
if %FILE_SIZE% LSS 1000000 (
    echo.
    echo Download incomplete or corrupted (file too small).
    echo Please try again or download manually.
    echo.
    del "%INSTALLER%" 2>nul
    start "" "https://github.com/sivaharanj7805/QBMigration/releases"
    pause
    exit /b 1
)

echo.
echo Download successful! File size: %FILE_SIZE% bytes
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
    echo You can now run the extractor from the Start Menu or
    echo from: %LOCALAPPDATA%\ForensicBridge\QBExtractor.exe
    echo.
) else (
    echo.
    echo Installation may have been cancelled or failed.
    echo You can run the installer manually from:
    echo   %INSTALLER%
    echo.
)

:: Cleanup
del "%INSTALLER%" 2>nul

echo.
echo Press any key to exit...
pause > nul
