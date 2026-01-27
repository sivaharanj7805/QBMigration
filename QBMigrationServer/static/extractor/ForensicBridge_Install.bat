@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: ForensicBridge Installer v2.1
:: Downloads and installs the QBExtractor package (exe + DLLs + config)
::
:: This installer:
:: 1. Checks system prerequisites (.NET 4.8, QuickBooks SDK)
:: 2. Downloads QBExtractor.zip from GitHub releases
:: 3. Extracts to AppData\Local\ForensicBridge
:: 4. Creates desktop shortcut
:: 5. Optionally runs with session code
::
:: NOTE: The extractor is distributed as a zip because .NET Framework 4.8
:: does not support single-file publishing. The zip contains:
::   - QBExtractor.exe (main extractor)
::   - Dependency DLLs (Newtonsoft.Json, etc.)
::   - config.json (production configuration)
:: ============================================================================

title ForensicBridge Setup
color 1F

:: Configuration
set "VERSION=2.1.0"
set "INSTALL_DIR=%LOCALAPPDATA%\ForensicBridge"
set "EXTRACTOR_EXE=%INSTALL_DIR%\QBExtractor.exe"
set "EXTRACTOR_ZIP=%INSTALL_DIR%\QBExtractor.zip"
set "GITHUB_REPO=sivaharanj7805/QBMigration"
set "GITHUB_ZIP_URL=https://github.com/%GITHUB_REPO%/releases/latest/download/QBExtractor.zip"
set "SERVER_API_URL=https://api.forensicbridge.ca/api/extractor"
set "SESSION_CODE="
set "AUTO_RUN=0"

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

:: ============================================================================
:: STEP 1: Check Prerequisites
:: ============================================================================
echo  [1/5] Checking system requirements...
echo.

:: Check PowerShell
where powershell >nul 2>&1
if errorlevel 1 (
    echo        [ERROR] PowerShell not found!
    goto :fatal_error
)
echo        PowerShell: OK

:: Check .NET Framework 4.8
powershell -NoProfile -Command "if ((Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full' -ErrorAction SilentlyContinue).Release -ge 528040) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo        .NET Framework 4.8: Installed
) else (
    echo        [WARNING] .NET Framework 4.8 not detected.
    echo        The extractor requires .NET Framework 4.8.
)

:: Check if QuickBooks SDK (QBFC16) is installed
set "QBFC_INSTALLED=0"
powershell -NoProfile -Command "if ([Type]::GetTypeFromProgID('QBFC16.QBSessionManager')) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    set "QBFC_INSTALLED=1"
    echo        QuickBooks SDK (QBFC16): Installed
) else (
    echo        QuickBooks SDK (QBFC16): Not found
    echo        [NOTE] The extractor requires QBFC16 to connect to QuickBooks.
)

echo.

:: ============================================================================
:: STEP 2: Create Installation Directory
:: ============================================================================
echo  [2/5] Preparing installation directory...

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%" 2>nul
    if errorlevel 1 (
        echo        [ERROR] Failed to create directory: %INSTALL_DIR%
        goto :fatal_error
    )
)
echo        Directory: %INSTALL_DIR%
echo.

:: ============================================================================
:: STEP 3: Download and Extract QBExtractor Package
:: ============================================================================
echo  [3/5] Downloading QBExtractor package...
echo.
echo        NOTE: The extractor is a zip package containing the exe,
echo        dependency DLLs, and configuration files.
echo.

set "DOWNLOAD_SUCCESS=0"

:: Method 1: Try server API first (serves the zip)
echo        Trying primary server...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
    "try { " ^
    "    Invoke-WebRequest -Uri '%SERVER_API_URL%/download-zip' -OutFile '%EXTRACTOR_ZIP%' -UseBasicParsing -TimeoutSec 120; " ^
    "    if ((Get-Item '%EXTRACTOR_ZIP%').Length -gt 100000) { exit 0 } else { exit 1 } " ^
    "} catch { exit 1 }" >nul 2>&1

if not errorlevel 1 (
    if exist "%EXTRACTOR_ZIP%" (
        for %%A in ("%EXTRACTOR_ZIP%") do if %%~zA GTR 100000 (
            set "DOWNLOAD_SUCCESS=1"
            echo        Downloaded from primary server.
        )
    )
)

:: Method 2: Try GitHub releases
if "%DOWNLOAD_SUCCESS%"=="0" (
    echo        Primary server unavailable, trying GitHub releases...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
        "try { " ^
        "    Invoke-WebRequest -Uri '%GITHUB_ZIP_URL%' -OutFile '%EXTRACTOR_ZIP%' -UseBasicParsing -TimeoutSec 180; " ^
        "    if ((Get-Item '%EXTRACTOR_ZIP%').Length -gt 100000) { exit 0 } else { exit 1 } " ^
        "} catch { exit 1 }" >nul 2>&1

    if not errorlevel 1 (
        if exist "%EXTRACTOR_ZIP%" (
            for %%A in ("%EXTRACTOR_ZIP%") do if %%~zA GTR 100000 (
                set "DOWNLOAD_SUCCESS=1"
                echo        Downloaded from GitHub releases.
            )
        )
    )
)

:: Method 3: Try GitHub API to find zip asset
if "%DOWNLOAD_SUCCESS%"=="0" (
    echo        Direct download failed, querying GitHub API...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
        "try { " ^
        "    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/%GITHUB_REPO%/releases/latest' -UseBasicParsing -TimeoutSec 30; " ^
        "    $asset = $release.assets | Where-Object { $_.name -like '*QBExtractor*.zip' } | Select-Object -First 1; " ^
        "    if ($asset) { " ^
        "        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile '%EXTRACTOR_ZIP%' -UseBasicParsing -TimeoutSec 180; " ^
        "        if ((Get-Item '%EXTRACTOR_ZIP%').Length -gt 100000) { exit 0 } else { exit 1 } " ^
        "    } else { exit 1 } " ^
        "} catch { exit 1 }" >nul 2>&1

    if not errorlevel 1 (
        if exist "%EXTRACTOR_ZIP%" (
            for %%A in ("%EXTRACTOR_ZIP%") do if %%~zA GTR 100000 (
                set "DOWNLOAD_SUCCESS=1"
                echo        Downloaded via GitHub API.
            )
        )
    )
)

if "%DOWNLOAD_SUCCESS%"=="0" (
    echo.
    echo        [ERROR] Could not download extractor package.
    echo.
    echo        Please download QBExtractor.zip manually from:
    echo        https://github.com/%GITHUB_REPO%/releases
    echo.
    start "" "https://github.com/%GITHUB_REPO%/releases"
    goto :fatal_error
)

:: Extract the zip package
echo.
echo        Extracting package...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { " ^
    "    Expand-Archive -Path '%EXTRACTOR_ZIP%' -DestinationPath '%INSTALL_DIR%' -Force; " ^
    "    exit 0 " ^
    "} catch { " ^
    "    Write-Host $_.Exception.Message; " ^
    "    exit 1 " ^
    "}" >nul 2>&1

if errorlevel 1 (
    echo        [ERROR] Failed to extract package.
    del "%EXTRACTOR_ZIP%" 2>nul
    goto :fatal_error
)

:: Clean up zip
del "%EXTRACTOR_ZIP%" 2>nul

:: Verify extraction
if not exist "%EXTRACTOR_EXE%" (
    echo        [ERROR] QBExtractor.exe not found after extraction.
    echo        Checking for subdirectory...

    :: Some zips have a root folder - check for it
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$dirs = Get-ChildItem -Path '%INSTALL_DIR%' -Directory; " ^
        "foreach ($d in $dirs) { " ^
        "    $exe = Join-Path $d.FullName 'QBExtractor.exe'; " ^
        "    if (Test-Path $exe) { " ^
        "        Get-ChildItem $d.FullName | Move-Item -Destination '%INSTALL_DIR%' -Force; " ^
        "        Remove-Item $d.FullName -Recurse -Force -ErrorAction SilentlyContinue; " ^
        "        exit 0 " ^
        "    } " ^
        "}; exit 1" >nul 2>&1

    if not exist "%EXTRACTOR_EXE%" (
        echo        [ERROR] Could not find QBExtractor.exe in package.
        goto :fatal_error
    )
)

echo        Extraction complete.
echo.

:: Verify the files
echo        Verifying installation...
for %%A in ("%EXTRACTOR_EXE%") do (
    echo        QBExtractor.exe: %%~zA bytes
)

if exist "%INSTALL_DIR%\config.json" (
    echo        config.json: present
) else (
    echo        [WARNING] config.json not found
)

echo        Installation verified.
echo.

:: ============================================================================
:: STEP 4: Create Shortcuts
:: ============================================================================
echo  [4/5] Creating shortcuts...

:: Create desktop shortcut
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; " ^
    "$Shortcut = $WshShell.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\ForensicBridge.lnk'); " ^
    "$Shortcut.TargetPath = '%EXTRACTOR_EXE%'; " ^
    "$Shortcut.WorkingDirectory = '%INSTALL_DIR%'; " ^
    "$Shortcut.Description = 'ForensicBridge QuickBooks Migration Tool'; " ^
    "$Shortcut.Save()" >nul 2>&1

if not errorlevel 1 (
    echo        Desktop shortcut created.
) else (
    echo        [WARNING] Could not create desktop shortcut.
)

:: Create Start Menu shortcut
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; " ^
    "$Shortcut = $WshShell.CreateShortcut('%START_MENU%\ForensicBridge.lnk'); " ^
    "$Shortcut.TargetPath = '%EXTRACTOR_EXE%'; " ^
    "$Shortcut.WorkingDirectory = '%INSTALL_DIR%'; " ^
    "$Shortcut.Description = 'ForensicBridge QuickBooks Migration Tool'; " ^
    "$Shortcut.Save()" >nul 2>&1

if not errorlevel 1 (
    echo        Start Menu shortcut created.
)

echo.

:: ============================================================================
:: STEP 5: Complete
:: ============================================================================
echo  [5/5] Installation complete!
echo.

cls
echo.
echo  ============================================================
echo   Installation Complete!
echo  ============================================================
echo.
echo   ForensicBridge has been installed successfully.
echo.
echo   Location: %INSTALL_DIR%
echo.

if "%QBFC_INSTALLED%"=="0" (
    echo   [NOTE] QuickBooks SDK ^(QBFC16^) was not detected.
    echo   The extractor requires QBFC16 to connect to QuickBooks Desktop.
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
echo   For support, visit: https://forensicbridge.ca/support
echo.
pause
exit /b 1

:: ============================================================================
:: Success Exit
:: ============================================================================
:end_success
echo.
echo  Press any key to exit...
pause >nul
exit /b 0
