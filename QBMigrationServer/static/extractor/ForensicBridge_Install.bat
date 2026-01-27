@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: ForensicBridge Installer v4.4
:: Downloads and installs the ForensicBridge QuickBooks Desktop Extractor
::
:: This installer:
:: 1. Checks system prerequisites
:: 2. Detects available QuickBooks backends (QBFC SDK or QODBC)
:: 3. Downloads the extractor from multiple fallback sources
:: 4. Installs to AppData\Local\ForensicBridge
:: 5. Creates desktop and Start Menu shortcuts
:: 6. Optionally runs with session code
::
:: IMPORTANT: The extractor works with EITHER:
::   - QuickBooks SDK (QBFC16) - Official, recommended
::   - QODBC Driver - Third-party ODBC, fallback option
::
:: If neither is installed, the extractor will guide you through installation.
:: ============================================================================

title ForensicBridge Setup v4.4
color 1F

:: Configuration
set "VERSION=4.4.0"
set "INSTALL_DIR=%LOCALAPPDATA%\ForensicBridge"
set "EXTRACTOR_EXE=%INSTALL_DIR%\QBExtractor.exe"
set "CONFIG_DIR=%INSTALL_DIR%\config"
set "LOG_FILE=%INSTALL_DIR%\install.log"
set "GITHUB_REPO=sivaharanj7805/QBMigration"
set "GITHUB_DIRECT_URL=https://github.com/%GITHUB_REPO%/releases/latest/download/QBExtractor.exe"
set "SERVER_API_URL=https://api.forensicbridge.ca/api/extractor"
set "SESSION_CODE="
set "AUTO_RUN=0"
set "QUIET_MODE=0"

:: Backend detection flags
set "QBFC_INSTALLED=0"
set "QODBC_INSTALLED=0"
set "HAS_BACKEND=0"

:: Parse command line arguments
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--session" (
    set "SESSION_CODE=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="-s" (
    set "SESSION_CODE=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--auto" (
    set "AUTO_RUN=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--quiet" (
    set "QUIET_MODE=1"
    shift
    goto :parse_args
)
if /i "%~1"=="-q" (
    set "QUIET_MODE=1"
    shift
    goto :parse_args
)
shift
goto :parse_args
:args_done

:: ============================================================================
:: HEADER
:: ============================================================================
cls
echo.
echo  ============================================================
echo   ForensicBridge - QuickBooks Desktop Migration Tool
echo   Installer Version %VERSION%
echo  ============================================================
echo.
echo   This tool extracts data from QuickBooks Desktop for
echo   migration to cloud accounting systems.
echo.

:: ============================================================================
:: STEP 1: Check Prerequisites
:: ============================================================================
echo  [1/6] Checking system requirements...
echo.

:: Check Windows version
for /f "tokens=4-5 delims=. " %%i in ('ver') do set VERSION_NUM=%%i.%%j
echo        Windows Version: %VERSION_NUM%

:: Check PowerShell
where powershell >nul 2>&1
if errorlevel 1 (
    echo        [ERROR] PowerShell not found!
    echo        PowerShell is required for installation.
    goto :fatal_error
)
echo        PowerShell: OK

:: Check .NET (informational only - self-contained build doesn't need it)
powershell -NoProfile -Command "try { [System.Runtime.InteropServices.RuntimeInformation]::FrameworkDescription } catch { '.NET not detected' }" 2>nul
echo        .NET Runtime: Bundled with extractor

echo.

:: ============================================================================
:: STEP 2: Detect QuickBooks Backends
:: ============================================================================
echo  [2/6] Detecting QuickBooks extraction backends...
echo.

:: Check QBFC16 SDK (official QuickBooks SDK)
echo        Checking QuickBooks SDK (QBFC16)...
powershell -NoProfile -Command "if ([Type]::GetTypeFromProgID('QBFC16.QBSessionManager')) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    set "QBFC_INSTALLED=1"
    set "HAS_BACKEND=1"
    echo        [FOUND] QuickBooks SDK (QBFC16) - RECOMMENDED
) else (
    echo        [NOT FOUND] QuickBooks SDK (QBFC16)
)

:: Check QODBC Driver
echo        Checking QODBC Driver...
powershell -NoProfile -Command "$found = $false; try { $key = 'HKLM:\SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers'; if (Test-Path $key) { $drivers = Get-ItemProperty $key; foreach ($prop in $drivers.PSObject.Properties) { if ($prop.Name -match 'QODBC|QuickBooks') { $found = $true; break } } } } catch {}; try { $key = 'HKLM:\SOFTWARE\WOW6432Node\ODBC\ODBCINST.INI\ODBC Drivers'; if (Test-Path $key) { $drivers = Get-ItemProperty $key; foreach ($prop in $drivers.PSObject.Properties) { if ($prop.Name -match 'QODBC|QuickBooks') { $found = $true; break } } } } catch {}; if ($found) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    set "QODBC_INSTALLED=1"
    set "HAS_BACKEND=1"
    echo        [FOUND] QODBC Driver - Fallback option
) else (
    echo        [NOT FOUND] QODBC Driver
)

echo.

:: Display backend status summary
if "%HAS_BACKEND%"=="1" (
    echo        --------------------------------------------------------
    if "%QBFC_INSTALLED%"=="1" (
        echo        Primary backend: QuickBooks SDK ^(QBFC16^) - READY
    )
    if "%QODBC_INSTALLED%"=="1" (
        if "%QBFC_INSTALLED%"=="1" (
            echo        Fallback backend: QODBC Driver - READY
        ) else (
            echo        Backend: QODBC Driver - READY
        )
    )
    echo        --------------------------------------------------------
) else (
    echo        --------------------------------------------------------
    echo        [WARNING] No extraction backend detected!
    echo.
    echo        The extractor needs ONE of these to work:
    echo.
    echo        Option 1 - QuickBooks SDK ^(QBFC16^) [RECOMMENDED]
    echo          Download: https://developer.intuit.com
    echo          ^(Free, requires Intuit Developer account^)
    echo.
    echo        Option 2 - QODBC Driver
    echo          Download: https://qodbc.com/qodbc-downloads/
    echo          ^(Free for read-only operations^)
    echo.
    echo        The extractor will guide you through installation.
    echo        --------------------------------------------------------
)

echo.

:: ============================================================================
:: STEP 3: Create Installation Directory
:: ============================================================================
echo  [3/6] Preparing installation directory...

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%" 2>nul
    if errorlevel 1 (
        echo        [ERROR] Failed to create directory: %INSTALL_DIR%
        goto :fatal_error
    )
)

if not exist "%CONFIG_DIR%" (
    mkdir "%CONFIG_DIR%" 2>nul
)

echo        Directory: %INSTALL_DIR%
echo.

:: ============================================================================
:: STEP 4: Download Extractor
:: ============================================================================
echo  [4/6] Downloading ForensicBridge Extractor...
echo.

set "DOWNLOAD_SUCCESS=0"
set "DOWNLOAD_SOURCE="

:: Check if already installed and up to date
if exist "%EXTRACTOR_EXE%" (
    for %%A in ("%EXTRACTOR_EXE%") do (
        if %%~zA GTR 50000 (
            echo        Existing installation found.
            set /p "REINSTALL=        Reinstall latest version? (Y/n): "
            if /i "!REINSTALL!"=="n" (
                echo        Using existing installation.
                set "DOWNLOAD_SUCCESS=1"
                set "DOWNLOAD_SOURCE=existing"
                goto :download_complete
            )
        )
    )
)

:: Method 1: Try ForensicBridge API server first
echo        Trying ForensicBridge server...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
    "try { " ^
    "    $ProgressPreference = 'SilentlyContinue'; " ^
    "    Invoke-WebRequest -Uri '%SERVER_API_URL%/download-exe' -OutFile '%EXTRACTOR_EXE%' -UseBasicParsing -TimeoutSec 120; " ^
    "    if ((Get-Item '%EXTRACTOR_EXE%').Length -gt 50000) { exit 0 } else { exit 1 } " ^
    "} catch { exit 1 }" >nul 2>&1

if not errorlevel 1 (
    if exist "%EXTRACTOR_EXE%" (
        for %%A in ("%EXTRACTOR_EXE%") do if %%~zA GTR 50000 (
            set "DOWNLOAD_SUCCESS=1"
            set "DOWNLOAD_SOURCE=ForensicBridge server"
            echo        Downloaded from ForensicBridge server.
        )
    )
)

:: Method 2: Try GitHub releases
if "%DOWNLOAD_SUCCESS%"=="0" (
    echo        Server unavailable, trying GitHub releases...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
        "try { " ^
        "    $ProgressPreference = 'SilentlyContinue'; " ^
        "    Invoke-WebRequest -Uri '%GITHUB_DIRECT_URL%' -OutFile '%EXTRACTOR_EXE%' -UseBasicParsing -TimeoutSec 180; " ^
        "    if ((Get-Item '%EXTRACTOR_EXE%').Length -gt 50000) { exit 0 } else { exit 1 } " ^
        "} catch { exit 1 }" >nul 2>&1

    if not errorlevel 1 (
        if exist "%EXTRACTOR_EXE%" (
            for %%A in ("%EXTRACTOR_EXE%") do if %%~zA GTR 50000 (
                set "DOWNLOAD_SUCCESS=1"
                set "DOWNLOAD_SOURCE=GitHub releases"
                echo        Downloaded from GitHub releases.
            )
        )
    )
)

:: Method 3: Try GitHub API to find asset URL
if "%DOWNLOAD_SUCCESS%"=="0" (
    echo        Direct download failed, querying GitHub API...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
        "try { " ^
        "    $ProgressPreference = 'SilentlyContinue'; " ^
        "    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/%GITHUB_REPO%/releases/latest' -UseBasicParsing -TimeoutSec 30; " ^
        "    $asset = $release.assets | Where-Object { $_.name -like '*QBExtractor*.exe' -and $_.name -notlike '*x64*' } | Select-Object -First 1; " ^
        "    if (-not $asset) { $asset = $release.assets | Where-Object { $_.name -like '*.exe' } | Select-Object -First 1 } " ^
        "    if ($asset) { " ^
        "        Write-Host 'Found: ' $asset.name; " ^
        "        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile '%EXTRACTOR_EXE%' -UseBasicParsing -TimeoutSec 180; " ^
        "        if ((Get-Item '%EXTRACTOR_EXE%').Length -gt 50000) { exit 0 } else { exit 1 } " ^
        "    } else { exit 1 } " ^
        "} catch { Write-Host $_.Exception.Message; exit 1 }" 2>&1

    if not errorlevel 1 (
        if exist "%EXTRACTOR_EXE%" (
            for %%A in ("%EXTRACTOR_EXE%") do if %%~zA GTR 50000 (
                set "DOWNLOAD_SUCCESS=1"
                set "DOWNLOAD_SOURCE=GitHub API"
                echo        Downloaded via GitHub API.
            )
        )
    )
)

:download_complete

if "%DOWNLOAD_SUCCESS%"=="0" (
    echo.
    echo        --------------------------------------------------------
    echo        [ERROR] Could not download extractor executable.
    echo.
    echo        This may be due to:
    echo          - Network connectivity issues
    echo          - Firewall blocking downloads
    echo          - No release available yet
    echo.
    echo        Please download manually from:
    echo          https://github.com/%GITHUB_REPO%/releases
    echo.
    echo        Or build from source:
    echo          cd QBDesktopReader
    echo          dotnet publish -c Release
    echo        --------------------------------------------------------
    echo.
    start "" "https://github.com/%GITHUB_REPO%/releases"
    goto :fatal_error
)

:: Verify the download
if not "%DOWNLOAD_SOURCE%"=="existing" (
    echo.
    echo        Verifying download...
    for %%A in ("%EXTRACTOR_EXE%") do (
        set "FILE_SIZE=%%~zA"
        echo        File size: !FILE_SIZE! bytes
        if %%~zA LSS 50000 (
            echo        [ERROR] Downloaded file is too small, may be corrupted.
            del "%EXTRACTOR_EXE%" 2>nul
            goto :fatal_error
        )
    )
    echo        Download verified successfully.
)
echo.

:: ============================================================================
:: STEP 5: Create Shortcuts
:: ============================================================================
echo  [5/6] Creating shortcuts...

:: Create desktop shortcut
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; " ^
    "$Shortcut = $WshShell.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\ForensicBridge.lnk'); " ^
    "$Shortcut.TargetPath = '%EXTRACTOR_EXE%'; " ^
    "$Shortcut.WorkingDirectory = '%INSTALL_DIR%'; " ^
    "$Shortcut.Description = 'ForensicBridge QuickBooks Migration Tool v%VERSION%'; " ^
    "$Shortcut.Save()" >nul 2>&1

if not errorlevel 1 (
    echo        Desktop shortcut: Created
) else (
    echo        Desktop shortcut: [WARNING] Could not create
)

:: Create Start Menu shortcut
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; " ^
    "$Shortcut = $WshShell.CreateShortcut('%START_MENU%\ForensicBridge.lnk'); " ^
    "$Shortcut.TargetPath = '%EXTRACTOR_EXE%'; " ^
    "$Shortcut.WorkingDirectory = '%INSTALL_DIR%'; " ^
    "$Shortcut.Description = 'ForensicBridge QuickBooks Migration Tool v%VERSION%'; " ^
    "$Shortcut.Save()" >nul 2>&1

if not errorlevel 1 (
    echo        Start Menu shortcut: Created
) else (
    echo        Start Menu shortcut: [WARNING] Could not create
)

:: Save installation info
echo {"version":"%VERSION%","installed_at":"%date% %time%","qbfc_detected":%QBFC_INSTALLED%,"qodbc_detected":%QODBC_INSTALLED%} > "%CONFIG_DIR%\install_info.json"

echo.

:: ============================================================================
:: STEP 6: Complete
:: ============================================================================
echo  [6/6] Installation complete!
echo.

cls
echo.
echo  ============================================================
echo   Installation Complete!
echo  ============================================================
echo.
echo   ForensicBridge v%VERSION% has been installed successfully.
echo.
echo   Location: %INSTALL_DIR%
echo   Downloaded from: %DOWNLOAD_SOURCE%
echo.

:: Show backend status
echo   Backend Status:
if "%QBFC_INSTALLED%"=="1" (
    echo     [OK] QuickBooks SDK ^(QBFC16^) detected
)
if "%QODBC_INSTALLED%"=="1" (
    echo     [OK] QODBC Driver detected
)
if "%HAS_BACKEND%"=="0" (
    echo     [!] No backend detected - extractor will guide installation
)
echo.

:: Show what to do next
echo   --------------------------------------------------------
echo   NEXT STEPS:
echo   --------------------------------------------------------
echo.
echo   1. Open QuickBooks Desktop and your company file
echo   2. Launch ForensicBridge from the desktop shortcut
echo   3. Enter your session code from the dashboard
echo   4. When prompted in QuickBooks, click "Yes, always allow"
echo   5. Wait for extraction to complete
echo.

if "%HAS_BACKEND%"=="0" (
    echo   [NOTE] You'll need to install a QuickBooks backend first.
    echo   The extractor will provide installation instructions.
    echo.
)

:: Launch or prompt
if not "%SESSION_CODE%"=="" (
    echo   Starting with session code: %SESSION_CODE%
    start "" "%EXTRACTOR_EXE%" --session "%SESSION_CODE%"
    goto :end_success
)

if "%AUTO_RUN%"=="1" (
    echo   Starting ForensicBridge...
    start "" "%EXTRACTOR_EXE%"
    goto :end_success
)

if "%QUIET_MODE%"=="1" (
    goto :end_success
)

echo.
set /p "LAUNCH=  Launch ForensicBridge now? (Y/n): "
if /i not "%LAUNCH%"=="n" (
    echo.
    echo   Starting ForensicBridge...
    start "" "%EXTRACTOR_EXE%"
)

goto :end_success

:: ============================================================================
:: Error Handler
:: ============================================================================
:fatal_error
echo.
echo  ============================================================
echo   Installation Failed
echo  ============================================================
echo.
echo   Please check the error messages above and try again.
echo.
echo   Troubleshooting:
echo     1. Run as Administrator (right-click, Run as admin)
echo     2. Check firewall allows downloads
echo     3. Try downloading manually from GitHub
echo.
echo   For support, visit: https://forensicbridge.ca/support
echo.
if not "%QUIET_MODE%"=="1" (
    pause
)
exit /b 1

:: ============================================================================
:: Success Exit
:: ============================================================================
:end_success
echo.
if not "%QUIET_MODE%"=="1" (
    echo  Press any key to exit...
    pause >nul
)
exit /b 0
