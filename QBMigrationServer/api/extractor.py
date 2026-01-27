"""
ForensicBridge Extractor Download API
Serves the ForensicBridge Windows extractor executable

Download Priority:
1. Local .exe file (if deployed on server)
2. Bootstrap installer script (always available)
"""

import os
import logging
import requests
from flask import Blueprint, send_file, jsonify, current_app, redirect, Response, request

logger = logging.getLogger(__name__)

extractor_bp = Blueprint('extractor', __name__, url_prefix='/api/extractor')

# GitHub repository for releases
GITHUB_REPO = 'sivaharanj7805/QBMigration'
GITHUB_RELEASE_URL = f'https://github.com/{GITHUB_REPO}/releases/latest/download/ForensicBridge_Setup.exe'
GITHUB_RELEASES_PAGE = f'https://github.com/{GITHUB_REPO}/releases'

# Get the static directory path
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
EXTRACTOR_DIR = os.path.join(STATIC_DIR, 'extractor')

# Bootstrap installer paths
BOOTSTRAP_BAT = os.path.join(EXTRACTOR_DIR, 'ForensicBridge_Install.bat')
BOOTSTRAP_PS1 = os.path.join(EXTRACTOR_DIR, 'ForensicBridge_Bootstrap.ps1')

# Default locations to search for the extractor
DEFAULT_EXTRACTOR_PATHS = [
    '/var/www/forensicbridge/extractor/ForensicBridge_Setup.exe',
    '/opt/forensicbridge/extractor/ForensicBridge_Setup.exe',
    os.path.join(STATIC_DIR, 'ForensicBridge_Setup.exe'),
    os.path.join(EXTRACTOR_DIR, 'ForensicBridge_Setup.exe'),
]


def find_extractor_path():
    """Find the extractor executable in configured or default locations"""
    # Check environment variable first
    env_path = os.getenv('EXTRACTOR_PATH')
    if env_path and os.path.isfile(env_path):
        return env_path

    # Check default locations
    for path in DEFAULT_EXTRACTOR_PATHS:
        if os.path.isfile(path):
            return path

    return None


def check_github_release_exists():
    """Check if the GitHub release file actually exists"""
    try:
        # Do a HEAD request to check if file exists
        response = requests.head(GITHUB_RELEASE_URL, allow_redirects=True, timeout=5)
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"Could not check GitHub release: {e}")
        return False


@extractor_bp.route('/download', methods=['GET'])
def download_extractor():
    """
    Download the ForensicBridge extractor.

    Priority:
    1. Local .exe file if available
    2. Bootstrap installer script (always works)
    """
    # First, try to serve the full installer
    extractor_path = find_extractor_path()

    if extractor_path:
        logger.info(f"Serving extractor from: {extractor_path}")
        return send_file(
            extractor_path,
            as_attachment=True,
            download_name='ForensicBridge_Setup.exe',
            mimetype='application/octet-stream'
        )

    # Fallback: serve the bootstrap installer batch file
    if os.path.isfile(BOOTSTRAP_BAT):
        logger.info("Serving bootstrap installer (BAT)")
        return send_file(
            BOOTSTRAP_BAT,
            as_attachment=True,
            download_name='ForensicBridge_Install.bat',
            mimetype='application/x-msdos-program'
        )

    # Last resort: generate a simple batch file on the fly
    logger.warning("No extractor or bootstrap found, generating fallback script")
    return Response(
        generate_fallback_installer(),
        mimetype='application/x-msdos-program',
        headers={
            'Content-Disposition': 'attachment; filename=ForensicBridge_Install.bat'
        }
    )


def generate_fallback_installer():
    """Generate a minimal batch installer script on the fly"""
    return '''@echo off
:: ForensicBridge Extractor - Download Script
:: This script downloads the ForensicBridge extractor

title ForensicBridge Extractor Download

echo.
echo ============================================================
echo   ForensicBridge Extractor Download
echo ============================================================
echo.

set "DOWNLOAD_URL=https://github.com/sivaharanj7805/QBMigration/releases/latest/download/ForensicBridge_Setup.exe"
set "INSTALLER=%TEMP%\\ForensicBridge_Setup.exe"

echo Downloading ForensicBridge Extractor...
echo.

powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%DOWNLOAD_URL%', '%INSTALLER%'); }"

if exist "%INSTALLER%" (
    echo Download complete!
    echo.
    echo Starting installer...
    start "" "%INSTALLER%"
) else (
    echo.
    echo Download failed. Opening GitHub releases page...
    start "" "https://github.com/sivaharanj7805/QBMigration/releases"
)

pause
'''


@extractor_bp.route('/bootstrap', methods=['GET'])
def download_bootstrap():
    """
    Download the bootstrap installer script.
    This is a small batch file that downloads and runs the full installer.
    """
    if os.path.isfile(BOOTSTRAP_BAT):
        return send_file(
            BOOTSTRAP_BAT,
            as_attachment=True,
            download_name='ForensicBridge_Install.bat',
            mimetype='application/x-msdos-program'
        )

    # Fallback: generate on the fly
    return Response(
        generate_fallback_installer(),
        mimetype='application/x-msdos-program',
        headers={
            'Content-Disposition': 'attachment; filename=ForensicBridge_Install.bat'
        }
    )


@extractor_bp.route('/bootstrap-ps1', methods=['GET'])
def download_bootstrap_ps1():
    """
    Download the PowerShell bootstrap installer script.
    More feature-rich than the batch version.
    """
    if os.path.isfile(BOOTSTRAP_PS1):
        return send_file(
            BOOTSTRAP_PS1,
            as_attachment=True,
            download_name='ForensicBridge_Bootstrap.ps1',
            mimetype='application/octet-stream'
        )

    # Return error if not found
    return jsonify({
        'error': 'PowerShell bootstrap script not found',
        'alternative': '/api/extractor/bootstrap'
    }), 404


@extractor_bp.route('/info', methods=['GET'])
def extractor_info():
    """
    Get information about the extractor availability.

    Returns:
        - available: whether the extractor is available for download
        - source: 'local', 'github', or 'bootstrap'
        - download_url: URL to download the extractor
    """
    extractor_path = find_extractor_path()

    if extractor_path:
        # Local full installer available
        file_size = os.path.getsize(extractor_path)
        return jsonify({
            'available': True,
            'source': 'local',
            'type': 'full_installer',
            'download_url': '/api/extractor/download',
            'file_size': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2)
        })

    # Check if GitHub release exists
    github_available = check_github_release_exists()

    # Bootstrap installer is always available
    return jsonify({
        'available': True,
        'source': 'bootstrap',
        'type': 'bootstrap_installer',
        'download_url': '/api/extractor/download',
        'bootstrap_url': '/api/extractor/bootstrap',
        'github_available': github_available,
        'github_direct_url': GITHUB_RELEASE_URL if github_available else None,
        'github_releases_page': GITHUB_RELEASES_PAGE,
        'message': 'Download will provide a bootstrap installer that downloads the full extractor'
    })


@extractor_bp.route('/github-download', methods=['GET'])
def github_download():
    """
    Direct redirect to GitHub releases download.
    Use this endpoint when you want to explicitly download from GitHub.
    """
    return redirect(GITHUB_RELEASE_URL, code=302)


@extractor_bp.route('/releases', methods=['GET'])
def releases_page():
    """
    Redirect to GitHub releases page where users can see all versions.
    """
    return redirect(GITHUB_RELEASES_PAGE, code=302)


@extractor_bp.route('/status', methods=['GET'])
def extractor_status():
    """
    Check the current status of all download options.
    Useful for debugging and monitoring.
    """
    extractor_path = find_extractor_path()
    github_available = check_github_release_exists()

    return jsonify({
        'local_installer': {
            'available': extractor_path is not None,
            'path': extractor_path
        },
        'bootstrap_bat': {
            'available': os.path.isfile(BOOTSTRAP_BAT),
            'path': BOOTSTRAP_BAT if os.path.isfile(BOOTSTRAP_BAT) else None
        },
        'bootstrap_ps1': {
            'available': os.path.isfile(BOOTSTRAP_PS1),
            'path': BOOTSTRAP_PS1 if os.path.isfile(BOOTSTRAP_PS1) else None
        },
        'github_release': {
            'available': github_available,
            'url': GITHUB_RELEASE_URL
        },
        'fallback_generator': {
            'available': True,
            'description': 'Can always generate a minimal download script'
        },
        'recommended_download': '/api/extractor/download'
    })
