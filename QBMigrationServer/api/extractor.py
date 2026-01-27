"""
ForensicBridge Extractor Download API v2.0
Serves the ForensicBridge Windows extractor executable

Download Priority:
1. Local .exe file (if deployed on server)
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
GITHUB_RELEASE_URL = f'https://github.com/{GITHUB_REPO}/releases/latest/download/QBExtractor.exe'
GITHUB_RELEASES_PAGE = f'https://github.com/{GITHUB_REPO}/releases'

# Get the static directory path
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
EXTRACTOR_DIR = os.path.join(STATIC_DIR, 'extractor')
CACHE_DIR = os.path.join(EXTRACTOR_DIR, 'cache')

# Bootstrap installer paths
BOOTSTRAP_BAT = os.path.join(EXTRACTOR_DIR, 'ForensicBridge_Install.bat')
BOOTSTRAP_PS1 = os.path.join(EXTRACTOR_DIR, 'ForensicBridge_Bootstrap.ps1')

# Default locations to search for the extractor
DEFAULT_EXTRACTOR_PATHS = [
    '/var/www/forensicbridge/extractor/QBExtractor.exe',
    '/opt/forensicbridge/extractor/QBExtractor.exe',
    os.path.join(STATIC_DIR, 'QBExtractor.exe'),
    os.path.join(EXTRACTOR_DIR, 'QBExtractor.exe'),
    os.path.join(CACHE_DIR, 'QBExtractor.exe'),
]

# Cache settings
CACHE_DURATION_HOURS = 24
CACHE_METADATA_FILE = os.path.join(CACHE_DIR, 'metadata.json')


def ensure_cache_dir():
    """Ensure the cache directory exists"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)


def find_extractor_path():
    """Find the extractor executable in configured or default locations"""
    env_path = os.getenv('EXTRACTOR_PATH')
    if env_path and os.path.isfile(env_path):
        file_size = os.path.getsize(env_path)
        if file_size > 50000:
            return env_path

    for path in DEFAULT_EXTRACTOR_PATHS:
        if os.path.isfile(path):
            file_size = os.path.getsize(path)
            if file_size > 50000:
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
    """Check if the cached extractor is still valid"""
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

    cache_path = os.path.join(CACHE_DIR, 'QBExtractor.exe')
    if not os.path.exists(cache_path):
        return False

    file_size = os.path.getsize(cache_path)
    if file_size < 50000:
        return False

    expected_hash = metadata.get('sha256')
    if expected_hash:
        try:
            with open(cache_path, 'rb') as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            if actual_hash != expected_hash:
                logger.warning("Cache hash mismatch, invalidating cache")
                return False
        except Exception:
            pass

    return True


def download_and_cache_from_github():
    """Download the extractor from GitHub and cache it"""
    ensure_cache_dir()
    cache_path = os.path.join(CACHE_DIR, 'QBExtractor.exe')

    try:
        headers = {'User-Agent': 'ForensicBridge-Server/2.0'}
        github_token = os.getenv('GITHUB_TOKEN')
        if github_token:
            headers['Authorization'] = f'token {github_token}'

        release_info = None
        download_url = GITHUB_RELEASE_URL

        try:
            api_response = requests.get(GITHUB_API_URL, headers=headers, timeout=10)
            if api_response.status_code == 200:
                release_info = api_response.json()
                for asset in release_info.get('assets', []):
                    if 'QBExtractor' in asset.get('name', '') and asset.get('name', '').endswith('.exe'):
                        download_url = asset.get('browser_download_url', download_url)
                        break
        except Exception as e:
            logger.warning(f"Could not fetch GitHub API: {e}")

        logger.info(f"Downloading extractor from: {download_url}")
        response = requests.get(download_url, headers=headers, stream=True, timeout=120)

        if response.status_code != 200:
            logger.error(f"GitHub download failed with status {response.status_code}")
            return None

        content_type = response.headers.get('content-type', '')
        if 'html' in content_type.lower():
            logger.error("GitHub returned HTML instead of binary, release may not exist")
            return None

        sha256_hash = hashlib.sha256()
        total_size = 0

        with open(cache_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    sha256_hash.update(chunk)
                    total_size += len(chunk)

        if total_size < 50000:
            logger.error(f"Downloaded file too small: {total_size} bytes")
            os.remove(cache_path)
            return None

        metadata = {
            'cached_at': datetime.now().isoformat(),
            'sha256': sha256_hash.hexdigest(),
            'size': total_size,
            'source_url': download_url,
            'release_tag': release_info.get('tag_name') if release_info else None,
            'release_name': release_info.get('name') if release_info else None
        }
        save_cache_metadata(metadata)

        logger.info(f"Successfully cached extractor: {total_size} bytes")
        return cache_path

    except requests.exceptions.Timeout:
        logger.error("GitHub download timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to download from GitHub: {e}")
        return None


def check_github_release_exists():
    """Check if the GitHub release file actually exists"""
    try:
        headers = {'User-Agent': 'ForensicBridge-Server/2.0'}
        response = requests.head(GITHUB_RELEASE_URL, allow_redirects=True, timeout=10, headers=headers)
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
    Download the ForensicBridge extractor.

    Priority:
    1. Local .exe file if available
    2. Cached GitHub release
    3. Bootstrap installer script (fallback)

    Query params:
        ?format=bat - Force bootstrap .bat download
    """
    requested_format = request.args.get('format', '').lower()

    if requested_format == 'bat':
        return download_bootstrap()

    # Try local file
    extractor_path = find_extractor_path()
    if extractor_path:
        logger.info(f"Serving extractor from: {extractor_path}")
        return send_file(
            extractor_path,
            as_attachment=True,
            download_name='QBExtractor.exe',
            mimetype='application/octet-stream'
        )

    # Try cached version
    if is_cache_valid():
        cache_path = os.path.join(CACHE_DIR, 'QBExtractor.exe')
        logger.info(f"Serving extractor from cache: {cache_path}")
        return send_file(
            cache_path,
            as_attachment=True,
            download_name='QBExtractor.exe',
            mimetype='application/octet-stream'
        )

    # Try to download and cache from GitHub
    cached_path = download_and_cache_from_github()
    if cached_path:
        logger.info(f"Serving freshly cached extractor: {cached_path}")
        return send_file(
            cached_path,
            as_attachment=True,
            download_name='QBExtractor.exe',
            mimetype='application/octet-stream'
        )

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
    logger.warning("No extractor or bootstrap found, generating fallback script")
    return Response(
        generate_fallback_installer(),
        mimetype='application/x-msdos-program',
        headers={
            'Content-Disposition': 'attachment; filename=ForensicBridge_Install.bat'
        }
    )


@extractor_bp.route('/download-exe', methods=['GET'])
def download_extractor_exe():
    """
    Download the ForensicBridge extractor .exe directly.
    Will attempt to serve cached/local version, or redirect to GitHub.
    """
    extractor_path = find_extractor_path()
    if extractor_path:
        return send_file(
            extractor_path,
            as_attachment=True,
            download_name='QBExtractor.exe',
            mimetype='application/octet-stream'
        )

    if is_cache_valid():
        cache_path = os.path.join(CACHE_DIR, 'QBExtractor.exe')
        return send_file(
            cache_path,
            as_attachment=True,
            download_name='QBExtractor.exe',
            mimetype='application/octet-stream'
        )

    cached_path = download_and_cache_from_github()
    if cached_path:
        return send_file(
            cached_path,
            as_attachment=True,
            download_name='QBExtractor.exe',
            mimetype='application/octet-stream'
        )

    if check_github_release_exists():
        return redirect(GITHUB_RELEASE_URL, code=302)

    return jsonify({
        'error': 'Extractor executable not available',
        'message': 'Please download from GitHub releases directly',
        'github_releases': GITHUB_RELEASES_PAGE
    }), 404


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
    extractor_path = find_extractor_path()
    cache_valid = is_cache_valid()
    cache_metadata = get_cache_metadata() if cache_valid else {}

    if extractor_path:
        file_size = os.path.getsize(extractor_path)
        return jsonify({
            'available': True,
            'source': 'local',
            'type': 'full_installer',
            'download_url': '/api/extractor/download-exe',
            'file_size': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2)
        })

    if cache_valid:
        cache_path = os.path.join(CACHE_DIR, 'QBExtractor.exe')
        file_size = os.path.getsize(cache_path)
        return jsonify({
            'available': True,
            'source': 'cached',
            'type': 'full_installer',
            'download_url': '/api/extractor/download-exe',
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
            'type': 'full_installer',
            'download_url': '/api/extractor/download-exe',
            'github_direct_url': GITHUB_RELEASE_URL,
            'github_releases_page': GITHUB_RELEASES_PAGE
        })

    return jsonify({
        'available': True,
        'source': 'bootstrap',
        'type': 'bootstrap_installer',
        'download_url': '/api/extractor/download',
        'bootstrap_url': '/api/extractor/bootstrap',
        'github_releases_page': GITHUB_RELEASES_PAGE,
        'message': 'Full extractor not cached. Bootstrap installer will download it.'
    })


@extractor_bp.route('/github-download', methods=['GET'])
def github_download():
    """Direct redirect to GitHub releases download."""
    return redirect(GITHUB_RELEASE_URL, code=302)


@extractor_bp.route('/releases', methods=['GET'])
def releases_page():
    """Redirect to GitHub releases page."""
    return redirect(GITHUB_RELEASES_PAGE, code=302)


@extractor_bp.route('/status', methods=['GET'])
def extractor_status():
    """Check the current status of all download options."""
    extractor_path = find_extractor_path()
    cache_valid = is_cache_valid()
    cache_metadata = get_cache_metadata()
    github_available = check_github_release_exists()

    cache_path = os.path.join(CACHE_DIR, 'QBExtractor.exe')

    return jsonify({
        'local_installer': {
            'available': extractor_path is not None,
            'path': extractor_path,
            'size': os.path.getsize(extractor_path) if extractor_path else None
        },
        'cached_installer': {
            'available': cache_valid,
            'path': cache_path if cache_valid else None,
            'size': os.path.getsize(cache_path) if cache_valid and os.path.exists(cache_path) else None,
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
            'url': GITHUB_RELEASE_URL
        },
        'fallback_generator': {
            'available': True,
            'description': 'Can always generate a minimal download script'
        },
        'recommended_download': '/api/extractor/download-exe' if (extractor_path or cache_valid or github_available) else '/api/extractor/download',
        'cache_dir': CACHE_DIR
    })


@extractor_bp.route('/cache/refresh', methods=['POST'])
def refresh_cache():
    """Force refresh the cached extractor from GitHub."""
    logger.info("Force refreshing extractor cache...")

    cache_path = os.path.join(CACHE_DIR, 'QBExtractor.exe')
    if os.path.exists(cache_path):
        os.remove(cache_path)
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
    """Clear the cached extractor."""
    try:
        cache_path = os.path.join(CACHE_DIR, 'QBExtractor.exe')
        if os.path.exists(cache_path):
            os.remove(cache_path)
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
set "DOWNLOAD_URL=https://github.com/{GITHUB_REPO}/releases/latest/download/QBExtractor.exe"
set "EXTRACTOR=%INSTALL_DIR%\\QBExtractor.exe"

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo Downloading ForensicBridge Extractor...
echo.

powershell -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
    "try {{ " ^
    "    Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%EXTRACTOR%' -UseBasicParsing; " ^
    "    if ((Get-Item '%EXTRACTOR%').Length -gt 50000) {{ exit 0 }} else {{ exit 1 }} " ^
    "}} catch {{ exit 1 }}"

if exist "%EXTRACTOR%" (
    for %%A in ("%EXTRACTOR%") do if %%~zA GTR 50000 (
        echo Download complete!
        echo.
        echo Starting ForensicBridge...
        start "" "%EXTRACTOR%"
        goto :end
    )
)

echo.
echo Download failed. Opening GitHub releases page...
start "" "{GITHUB_RELEASES_PAGE}"

:end
echo.
pause
'''
