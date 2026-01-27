"""
ForensicBridge Extractor Download API v2.1
Serves the QBExtractor package (zip containing exe + DLLs + config)

Distribution: The extractor is distributed as a zip file because .NET Framework 4.8
does not support single-file publishing. The zip contains:
  - QBExtractor.exe (main extractor)
  - Dependency DLLs (Newtonsoft.Json, etc.)
  - config.json (production configuration)

Download Priority:
1. Local .zip file (if deployed on server)
2. Cached GitHub release (downloaded and cached)
3. Redirect to GitHub releases (fallback)
4. Bootstrap installer script (last resort)
"""

import os
import logging
import requests
import hashlib
import json
from datetime import datetime, timedelta
from flask import Blueprint, send_file, jsonify, redirect, Response, request

logger = logging.getLogger(__name__)

extractor_bp = Blueprint('extractor', __name__, url_prefix='/api/extractor')

# GitHub repository for releases
GITHUB_REPO = 'sivaharanj7805/QBMigration'
GITHUB_API_URL = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
GITHUB_RELEASE_ZIP_URL = f'https://github.com/{GITHUB_REPO}/releases/latest/download/QBExtractor.zip'
GITHUB_RELEASES_PAGE = f'https://github.com/{GITHUB_REPO}/releases'

# Get the static directory path
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
EXTRACTOR_DIR = os.path.join(STATIC_DIR, 'extractor')
CACHE_DIR = os.path.join(EXTRACTOR_DIR, 'cache')

# Bootstrap installer paths
BOOTSTRAP_BAT = os.path.join(EXTRACTOR_DIR, 'ForensicBridge_Install.bat')
BOOTSTRAP_PS1 = os.path.join(EXTRACTOR_DIR, 'ForensicBridge_Bootstrap.ps1')

# Default locations to search for the extractor zip
DEFAULT_ZIP_PATHS = [
    '/var/www/forensicbridge/extractor/QBExtractor.zip',
    '/opt/forensicbridge/extractor/QBExtractor.zip',
    os.path.join(STATIC_DIR, 'QBExtractor.zip'),
    os.path.join(EXTRACTOR_DIR, 'QBExtractor.zip'),
    os.path.join(CACHE_DIR, 'QBExtractor.zip'),
]

# Cache settings
CACHE_DURATION_HOURS = 24
CACHE_METADATA_FILE = os.path.join(CACHE_DIR, 'metadata.json')
CACHED_ZIP_PATH = os.path.join(CACHE_DIR, 'QBExtractor.zip')

# Minimum zip size (exe + DLLs + config should be at least 100KB)
MIN_ZIP_SIZE = 100000


def ensure_cache_dir():
    """Ensure the cache directory exists"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)


def find_zip_path():
    """Find the extractor zip in configured or default locations"""
    env_path = os.getenv('EXTRACTOR_ZIP_PATH')
    if env_path and os.path.isfile(env_path):
        if os.path.getsize(env_path) > MIN_ZIP_SIZE:
            return env_path

    for path in DEFAULT_ZIP_PATHS:
        if os.path.isfile(path):
            if os.path.getsize(path) > MIN_ZIP_SIZE:
                return path

    return None


def get_cache_metadata():
    """Load cache metadata"""
    try:
        if os.path.exists(CACHE_METADATA_FILE):
            with open(CACHE_METADATA_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read cache metadata: {e}")
    return {}


def save_cache_metadata(metadata):
    """Save cache metadata"""
    try:
        ensure_cache_dir()
        with open(CACHE_METADATA_FILE, 'w') as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save cache metadata: {e}")


def is_cache_valid():
    """Check if the cached extractor zip is still valid"""
    metadata = get_cache_metadata()
    cached_at = metadata.get('cached_at')

    if not cached_at:
        return False

    try:
        cache_time = datetime.fromisoformat(cached_at)
        if datetime.now() - cache_time > timedelta(hours=CACHE_DURATION_HOURS):
            return False
    except Exception:
        return False

    if not os.path.exists(CACHED_ZIP_PATH):
        return False

    file_size = os.path.getsize(CACHED_ZIP_PATH)
    if file_size < MIN_ZIP_SIZE:
        return False

    expected_hash = metadata.get('sha256')
    if expected_hash:
        try:
            with open(CACHED_ZIP_PATH, 'rb') as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            if actual_hash != expected_hash:
                logger.warning("Cache hash mismatch, invalidating cache")
                return False
        except Exception:
            pass

    return True


def download_and_cache_from_github():
    """Download the extractor zip from GitHub and cache it"""
    ensure_cache_dir()

    try:
        headers = {'User-Agent': 'ForensicBridge-Server/2.1'}
        github_token = os.getenv('GITHUB_TOKEN')
        if github_token:
            headers['Authorization'] = f'token {github_token}'

        release_info = None
        download_url = GITHUB_RELEASE_ZIP_URL

        try:
            api_response = requests.get(GITHUB_API_URL, headers=headers, timeout=10)
            if api_response.status_code == 200:
                release_info = api_response.json()
                for asset in release_info.get('assets', []):
                    if 'QBExtractor' in asset.get('name', '') and asset.get('name', '').endswith('.zip'):
                        download_url = asset.get('browser_download_url', download_url)
                        break
        except Exception as e:
            logger.warning(f"Could not fetch GitHub API: {e}")

        logger.info(f"Downloading extractor zip from: {download_url}")
        response = requests.get(download_url, headers=headers, stream=True, timeout=180)

        if response.status_code != 200:
            logger.error(f"GitHub download failed with status {response.status_code}")
            return None

        content_type = response.headers.get('content-type', '')
        if 'html' in content_type.lower():
            logger.error("GitHub returned HTML instead of binary, release may not exist")
            return None

        sha256_hash = hashlib.sha256()
        total_size = 0

        with open(CACHED_ZIP_PATH, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    sha256_hash.update(chunk)
                    total_size += len(chunk)

        if total_size < MIN_ZIP_SIZE:
            logger.error(f"Downloaded file too small: {total_size} bytes")
            os.remove(CACHED_ZIP_PATH)
            return None

        metadata = {
            'cached_at': datetime.now().isoformat(),
            'sha256': sha256_hash.hexdigest(),
            'size': total_size,
            'source_url': download_url,
            'release_tag': release_info.get('tag_name') if release_info else None,
            'release_name': release_info.get('name') if release_info else None,
            'format': 'zip'
        }
        save_cache_metadata(metadata)

        logger.info(f"Successfully cached extractor zip: {total_size} bytes")
        return CACHED_ZIP_PATH

    except requests.exceptions.Timeout:
        logger.error("GitHub download timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to download from GitHub: {e}")
        return None


def check_github_release_exists():
    """Check if the GitHub release zip actually exists"""
    try:
        headers = {'User-Agent': 'ForensicBridge-Server/2.1'}
        response = requests.head(GITHUB_RELEASE_ZIP_URL, allow_redirects=True, timeout=10, headers=headers)
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"Could not check GitHub release: {e}")
        return False


# ============================================================================
# API ENDPOINTS
# ============================================================================

@extractor_bp.route('/download', methods=['GET'])
def download_extractor():
    """
    Download the QBExtractor package.

    Priority:
    1. Local .zip file if available
    2. Cached GitHub release zip
    3. Bootstrap installer script (fallback)

    Query params:
        ?format=bat - Force bootstrap .bat download
        ?format=ps1 - Force bootstrap .ps1 download
    """
    requested_format = request.args.get('format', '').lower()

    if requested_format == 'bat':
        return download_bootstrap()
    if requested_format == 'ps1':
        return download_bootstrap_ps1()

    return _serve_zip_or_fallback()


@extractor_bp.route('/download-zip', methods=['GET'])
def download_extractor_zip():
    """
    Download the QBExtractor.zip package directly.
    Contains exe + DLLs + config.json (net48 cannot produce single-file exe).
    Will attempt to serve cached/local version, or redirect to GitHub.
    """
    return _serve_zip_or_fallback()


def _serve_zip_or_fallback():
    """Internal: serve the zip from local/cache/github, or fallback to bootstrap"""
    # Try local file
    zip_path = find_zip_path()
    if zip_path:
        logger.info(f"Serving extractor zip from: {zip_path}")
        return send_file(
            zip_path,
            as_attachment=True,
            download_name='QBExtractor.zip',
            mimetype='application/zip'
        )

    # Try cached version
    if is_cache_valid():
        logger.info(f"Serving extractor zip from cache: {CACHED_ZIP_PATH}")
        return send_file(
            CACHED_ZIP_PATH,
            as_attachment=True,
            download_name='QBExtractor.zip',
            mimetype='application/zip'
        )

    # Try to download and cache from GitHub
    cached_path = download_and_cache_from_github()
    if cached_path:
        logger.info(f"Serving freshly cached extractor zip: {cached_path}")
        return send_file(
            cached_path,
            as_attachment=True,
            download_name='QBExtractor.zip',
            mimetype='application/zip'
        )

    # Check if we can redirect to GitHub
    if check_github_release_exists():
        return redirect(GITHUB_RELEASE_ZIP_URL, code=302)

    # Fallback: serve the bootstrap installer
    if os.path.isfile(BOOTSTRAP_BAT):
        logger.info("Serving bootstrap installer (BAT) as fallback")
        return send_file(
            BOOTSTRAP_BAT,
            as_attachment=True,
            download_name='ForensicBridge_Install.bat',
            mimetype='application/x-msdos-program'
        )

    # Last resort: generate on the fly
    logger.warning("No extractor zip or bootstrap found, generating fallback script")
    return Response(
        generate_fallback_installer(),
        mimetype='application/x-msdos-program',
        headers={
            'Content-Disposition': 'attachment; filename=ForensicBridge_Install.bat'
        }
    )


@extractor_bp.route('/bootstrap', methods=['GET'])
def download_bootstrap():
    """Download the bootstrap installer batch file."""
    if os.path.isfile(BOOTSTRAP_BAT):
        return send_file(
            BOOTSTRAP_BAT,
            as_attachment=True,
            download_name='ForensicBridge_Install.bat',
            mimetype='application/x-msdos-program'
        )

    return Response(
        generate_fallback_installer(),
        mimetype='application/x-msdos-program',
        headers={
            'Content-Disposition': 'attachment; filename=ForensicBridge_Install.bat'
        }
    )


@extractor_bp.route('/bootstrap-ps1', methods=['GET'])
def download_bootstrap_ps1():
    """Download the PowerShell bootstrap installer script."""
    if os.path.isfile(BOOTSTRAP_PS1):
        return send_file(
            BOOTSTRAP_PS1,
            as_attachment=True,
            download_name='ForensicBridge_Bootstrap.ps1',
            mimetype='application/octet-stream'
        )

    return jsonify({
        'error': 'PowerShell bootstrap script not found',
        'alternative': '/api/extractor/bootstrap'
    }), 404


@extractor_bp.route('/info', methods=['GET'])
def extractor_info():
    """Get information about the extractor availability."""
    zip_path = find_zip_path()
    cache_valid = is_cache_valid()
    cache_metadata = get_cache_metadata() if cache_valid else {}

    if zip_path:
        file_size = os.path.getsize(zip_path)
        return jsonify({
            'available': True,
            'source': 'local',
            'type': 'zip_package',
            'download_url': '/api/extractor/download-zip',
            'file_size': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2)
        })

    if cache_valid:
        file_size = os.path.getsize(CACHED_ZIP_PATH)
        return jsonify({
            'available': True,
            'source': 'cached',
            'type': 'zip_package',
            'download_url': '/api/extractor/download-zip',
            'file_size': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2),
            'cached_at': cache_metadata.get('cached_at'),
            'release_tag': cache_metadata.get('release_tag')
        })

    github_available = check_github_release_exists()
    if github_available:
        return jsonify({
            'available': True,
            'source': 'github',
            'type': 'zip_package',
            'download_url': '/api/extractor/download-zip',
            'github_direct_url': GITHUB_RELEASE_ZIP_URL,
            'github_releases_page': GITHUB_RELEASES_PAGE
        })

    return jsonify({
        'available': True,
        'source': 'bootstrap',
        'type': 'bootstrap_installer',
        'download_url': '/api/extractor/download',
        'bootstrap_url': '/api/extractor/bootstrap',
        'github_releases_page': GITHUB_RELEASES_PAGE,
        'message': 'Full extractor zip not cached. Bootstrap installer will download it.'
    })


@extractor_bp.route('/github-download', methods=['GET'])
def github_download():
    """Direct redirect to GitHub releases download."""
    return redirect(GITHUB_RELEASE_ZIP_URL, code=302)


@extractor_bp.route('/releases', methods=['GET'])
def releases_page():
    """Redirect to GitHub releases page."""
    return redirect(GITHUB_RELEASES_PAGE, code=302)


@extractor_bp.route('/status', methods=['GET'])
def extractor_status():
    """Check the current status of all download options."""
    zip_path = find_zip_path()
    cache_valid = is_cache_valid()
    cache_metadata = get_cache_metadata()
    github_available = check_github_release_exists()

    return jsonify({
        'local_zip': {
            'available': zip_path is not None,
            'path': zip_path,
            'size': os.path.getsize(zip_path) if zip_path else None
        },
        'cached_zip': {
            'available': cache_valid,
            'path': CACHED_ZIP_PATH if cache_valid else None,
            'size': os.path.getsize(CACHED_ZIP_PATH) if cache_valid and os.path.exists(CACHED_ZIP_PATH) else None,
            'cached_at': cache_metadata.get('cached_at'),
            'sha256': cache_metadata.get('sha256', '')[:16] + '...' if cache_metadata.get('sha256') else None,
            'release_tag': cache_metadata.get('release_tag')
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
            'url': GITHUB_RELEASE_ZIP_URL
        },
        'fallback_generator': {
            'available': True,
            'description': 'Can always generate a minimal download script'
        },
        'recommended_download': '/api/extractor/download-zip' if (zip_path or cache_valid or github_available) else '/api/extractor/download',
        'cache_dir': CACHE_DIR
    })


@extractor_bp.route('/cache/refresh', methods=['POST'])
def refresh_cache():
    """Force refresh the cached extractor zip from GitHub."""
    logger.info("Force refreshing extractor cache...")

    if os.path.exists(CACHED_ZIP_PATH):
        os.remove(CACHED_ZIP_PATH)
    if os.path.exists(CACHE_METADATA_FILE):
        os.remove(CACHE_METADATA_FILE)

    cached_path = download_and_cache_from_github()

    if cached_path:
        metadata = get_cache_metadata()
        return jsonify({
            'success': True,
            'message': 'Cache refreshed successfully',
            'cached_at': metadata.get('cached_at'),
            'size': metadata.get('size'),
            'sha256': metadata.get('sha256', '')[:16] + '...' if metadata.get('sha256') else None
        })

    return jsonify({
        'success': False,
        'error': 'Failed to refresh cache from GitHub'
    }), 500


@extractor_bp.route('/cache/clear', methods=['POST'])
def clear_cache():
    """Clear the cached extractor zip."""
    try:
        if os.path.exists(CACHED_ZIP_PATH):
            os.remove(CACHED_ZIP_PATH)
        if os.path.exists(CACHE_METADATA_FILE):
            os.remove(CACHE_METADATA_FILE)

        return jsonify({
            'success': True,
            'message': 'Cache cleared successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def generate_fallback_installer():
    """Generate a minimal batch installer script on the fly"""
    return f'''@echo off
:: ForensicBridge Extractor - Fallback Download Script

title ForensicBridge Extractor Download
color 1F

echo.
echo ============================================================
echo   ForensicBridge Extractor Download
echo ============================================================
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\\ForensicBridge"
set "ZIP_PATH=%INSTALL_DIR%\\QBExtractor.zip"
set "DOWNLOAD_URL=https://github.com/{GITHUB_REPO}/releases/latest/download/QBExtractor.zip"

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo Downloading QBExtractor package...
echo.

powershell -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
    "try {{ " ^
    "    Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%ZIP_PATH%' -UseBasicParsing; " ^
    "    if ((Get-Item '%ZIP_PATH%').Length -gt 100000) {{ " ^
    "        Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%INSTALL_DIR%' -Force; " ^
    "        Remove-Item '%ZIP_PATH%' -Force; " ^
    "        exit 0 " ^
    "    }} else {{ exit 1 }} " ^
    "}} catch {{ exit 1 }}"

set "EXTRACTOR=%INSTALL_DIR%\\QBExtractor.exe"

if exist "%EXTRACTOR%" (
    echo Download and extraction complete!
    echo.
    echo Starting ForensicBridge...
    start "" "%EXTRACTOR%"
    goto :end
)

echo.
echo Download failed. Opening GitHub releases page...
start "" "{GITHUB_RELEASES_PAGE}"

:end
echo.
pause
'''
