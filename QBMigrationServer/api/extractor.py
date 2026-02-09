"""
ForensicBridge Extractor Download API v4.4
Serves the ForensicBridge Windows extractor executable

Download Priority:
1. Local .exe file (if deployed on server)
2. Cached GitHub release (downloaded and cached)
3. Redirect to GitHub releases (fallback)
4. Bootstrap installer script (last resort)

Endpoints:
- GET  /download      - Smart download (exe or bootstrap)
- GET  /download-exe  - Direct exe download
- GET  /bootstrap     - Bootstrap installer (.bat)
- GET  /info          - Availability info
- GET  /status        - Full status of all sources
- GET  /version       - Current version info
- POST /cache/refresh - Force refresh from GitHub
- POST /cache/clear   - Clear cached files
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, Response, jsonify, redirect, request, send_file
from api.auth import require_auth
from extensions import limiter
from utils.auth import admin_required

logger = logging.getLogger(__name__)

extractor_bp = Blueprint("extractor", __name__, url_prefix="/api/extractor")


# FIX: Helper function to sanitize URLs from error messages
def _sanitize_url_for_logging(url: str) -> str:
    """
    Sanitize a URL for safe logging by removing internal infrastructure details.

    This prevents internal URLs, tokens, and paths from being exposed in logs.
    """
    from urllib.parse import urlparse

    if not url:
        return "[NO_URL]"

    try:
        parsed = urlparse(url)
        # Only log the domain and path basename, not full internal paths
        if parsed.netloc:
            # Extract just the filename from the path
            path_parts = parsed.path.rstrip("/").split("/")
            filename = path_parts[-1] if path_parts else ""
            return (
                f"{parsed.scheme}://{parsed.netloc}/.../{filename}"
                if filename
                else f"{parsed.scheme}://{parsed.netloc}/..."
            )
        else:
            # Local path - sanitize to just the filename
            return f"[LOCAL]/{os.path.basename(url)}"
    except Exception:
        return "[SANITIZED_URL]"


def _sanitize_error_for_logging(error: Exception) -> str:
    """
    Sanitize an exception message for safe logging by removing internal URLs and paths.
    """
    import re

    error_str = str(error)

    # Remove full URLs (http/https)
    error_str = re.sub(r'https?://[^\s<>"\']+', "[URL_REDACTED]", error_str)

    # Remove internal file paths
    error_str = re.sub(
        r'(/var/www|/opt|/home|/tmp|/etc)[^\s<>"\']*', "[PATH_REDACTED]", error_str
    )

    # Remove Windows paths
    error_str = re.sub(r'[A-Za-z]:\\[^\s<>"\']*', "[PATH_REDACTED]", error_str)

    return error_str


# GitHub repository for releases
GITHUB_REPO = "sivaharanj7805/QBMigration"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASE_URL = (
    f"https://github.com/{GITHUB_REPO}/releases/latest/download/QBExtractor.exe"
)
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"

# Get the static directory path
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
EXTRACTOR_DIR = os.path.join(STATIC_DIR, "extractor")
CACHE_DIR = os.path.join(EXTRACTOR_DIR, "cache")

# Bootstrap installer paths
BOOTSTRAP_BAT = os.path.join(EXTRACTOR_DIR, "ForensicBridge_Install.bat")
BOOTSTRAP_PS1 = os.path.join(EXTRACTOR_DIR, "ForensicBridge_Bootstrap.ps1")

# Zip deployment package paths
DEFAULT_ZIP_PATHS = [
    "/var/www/forensicbridge/extractor/QBExtractor-deploy.zip",
    "/opt/forensicbridge/extractor/QBExtractor-deploy.zip",
    os.path.join(EXTRACTOR_DIR, "QBExtractor-deploy.zip"),
    os.path.join(STATIC_DIR, "QBExtractor-deploy.zip"),
]
ZIP_METADATA_FILE = os.path.join(EXTRACTOR_DIR, "zip_metadata.json")

# Default locations to search for the extractor
DEFAULT_EXTRACTOR_PATHS = [
    "/var/www/forensicbridge/extractor/QBExtractor.exe",
    "/opt/forensicbridge/extractor/QBExtractor.exe",
    os.path.join(STATIC_DIR, "QBExtractor.exe"),
    os.path.join(EXTRACTOR_DIR, "QBExtractor.exe"),
    os.path.join(CACHE_DIR, "QBExtractor.exe"),
]

# Cache settings
CACHE_DURATION_HOURS = 24
CACHE_METADATA_FILE = os.path.join(CACHE_DIR, "metadata.json")

# Current extractor version (should match QBDesktopReader version)
EXTRACTOR_VERSION = "4.4.0"
MINIMUM_FILE_SIZE = 50000  # 50KB minimum for valid executable

# Windows security bypass instructions for unsigned executables
WINDOWS_SECURITY_INSTRUCTIONS = {
    "title": "Windows Security Notice",
    "summary": (
        "Windows may show a security warning because this software"
        " is not yet code-signed. This is normal for new software."
    ),
    "browser_warning": {
        "title": "Browser Download Warning",
        "description": 'Your browser may show "This file is not commonly downloaded" or similar.',
        "steps": [
            'Click the "..." or dropdown arrow next to the download',
            'Select "Keep" or "Keep anyway"',
            'If prompted again, click "Keep anyway" or "Show more" → "Keep anyway"',
        ],
    },
    "smartscreen_warning": {
        "title": "Windows SmartScreen Warning",
        "description": 'When running the file, Windows Defender SmartScreen may show "Windows protected your PC".',
        "steps": [
            'Click "More info" on the SmartScreen popup',
            'Click "Run anyway" button that appears',
            "The application will now start normally",
        ],
    },
    "zip_extraction": {
        "title": "Extracting the ZIP file",
        "steps": [
            "Right-click the downloaded ZIP file",
            'Select "Extract All..." or use your preferred extraction tool',
            "Choose a destination folder (e.g., Desktop or Documents)",
            "After extraction, navigate to the folder and run QBExtractor.exe",
        ],
    },
    "why_warning": (
        "Windows shows these warnings for any software that is not signed"
        " with an Extended Validation (EV) code signing certificate."
        " Our software is safe and verified - we are working on"
        " obtaining an EV certificate."
    ),
    "support_url": "https://forensicbridge.ca/support",
}


def ensure_cache_dir():
    """Ensure the cache directory exists"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)


def find_extractor_path():
    """Find the extractor executable in configured or default locations"""
    env_path = os.getenv("EXTRACTOR_PATH")
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


def find_zip_path():
    """Find the deployment zip file in configured or default locations"""
    env_path = os.getenv("EXTRACTOR_ZIP_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    for path in DEFAULT_ZIP_PATHS:
        if os.path.isfile(path):
            return path

    return None


def get_zip_metadata():
    """Load zip metadata (hash, size, etc.)"""
    try:
        if os.path.exists(ZIP_METADATA_FILE):
            with open(ZIP_METADATA_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read zip metadata: {e}")
    return {}


def save_zip_metadata(metadata):
    """Save zip metadata"""
    try:
        with open(ZIP_METADATA_FILE, "w") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save zip metadata: {e}")


def compute_zip_hash(zip_path):
    """Compute SHA256 hash of the zip file"""
    sha256_hash = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def generate_zip_metadata(zip_path):
    """Generate and save metadata for the zip file"""
    if not os.path.exists(zip_path):
        return None

    file_size = os.path.getsize(zip_path)
    sha256 = compute_zip_hash(zip_path)

    metadata = {
        "sha256": sha256,
        "size": file_size,
        "filename": os.path.basename(zip_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": EXTRACTOR_VERSION,
    }

    save_zip_metadata(metadata)
    return metadata


def get_cache_metadata():
    """Load cache metadata"""
    try:
        if os.path.exists(CACHE_METADATA_FILE):
            with open(CACHE_METADATA_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read cache metadata: {e}")
    return {}


def save_cache_metadata(metadata):
    """Save cache metadata"""
    try:
        ensure_cache_dir()
        with open(CACHE_METADATA_FILE, "w") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save cache metadata: {e}")


def is_cache_valid():
    """Check if the cached extractor is still valid"""
    metadata = get_cache_metadata()
    cached_at = metadata.get("cached_at")

    if not cached_at:
        return False

    try:
        cache_time = datetime.fromisoformat(cached_at)
        # Ensure both datetimes are timezone-aware for comparison
        if cache_time.tzinfo is None:
            cache_time = cache_time.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - cache_time > timedelta(
            hours=CACHE_DURATION_HOURS
        ):
            return False
    except Exception:
        return False

    cache_path = os.path.join(CACHE_DIR, "QBExtractor.exe")
    if not os.path.exists(cache_path):
        return False

    file_size = os.path.getsize(cache_path)
    if file_size < 50000:
        return False

    expected_hash = metadata.get("sha256")
    if expected_hash:
        try:
            with open(cache_path, "rb") as f:
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
    cache_path = os.path.join(CACHE_DIR, "QBExtractor.exe")

    try:
        headers = {"User-Agent": "ForensicBridge-Server/2.0"}
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        release_info = None
        download_url = GITHUB_RELEASE_URL

        try:
            api_response = requests.get(GITHUB_API_URL, headers=headers, timeout=10)
            if api_response.status_code == 200:
                release_info = api_response.json()
                for asset in release_info.get("assets", []):
                    if "QBExtractor" in asset.get("name", "") and asset.get(
                        "name", ""
                    ).endswith(".exe"):
                        download_url = asset.get("browser_download_url", download_url)
                        break
        except Exception as e:
            # FIX: Sanitize error to remove internal URLs
            logger.warning(
                f"Could not fetch GitHub API: {_sanitize_error_for_logging(e)}"
            )

        # FIX: Sanitize URL for logging to avoid exposing internal infrastructure
        logger.info(
            f"Downloading extractor from: {_sanitize_url_for_logging(download_url)}"
        )
        response = requests.get(download_url, headers=headers, stream=True, timeout=120)

        if response.status_code != 200:
            logger.error(f"GitHub download failed with status {response.status_code}")
            return None

        content_type = response.headers.get("content-type", "")
        if "html" in content_type.lower():
            logger.error(
                "GitHub returned HTML instead of binary, release may not exist"
            )
            return None

        sha256_hash = hashlib.sha256()
        total_size = 0

        with open(cache_path, "wb") as f:
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
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "sha256": sha256_hash.hexdigest(),
            "size": total_size,
            "source_url": download_url,
            "release_tag": release_info.get("tag_name") if release_info else None,
            "release_name": release_info.get("name") if release_info else None,
        }
        save_cache_metadata(metadata)

        logger.info(f"Successfully cached extractor: {total_size} bytes")
        return cache_path

    except requests.exceptions.Timeout:
        logger.error("GitHub download timed out")
        return None
    except Exception as e:
        # FIX: Sanitize error to remove internal URLs
        logger.error(
            f"Failed to download from GitHub: {_sanitize_error_for_logging(e)}"
        )
        return None


def check_github_release_exists():
    """Check if the GitHub release file actually exists"""
    try:
        headers = {"User-Agent": "ForensicBridge-Server/2.0"}
        response = requests.head(
            GITHUB_RELEASE_URL, allow_redirects=True, timeout=10, headers=headers
        )
        return response.status_code == 200
    except Exception as e:
        # FIX: Sanitize error to remove internal URLs
        logger.warning(
            f"Could not check GitHub release: {_sanitize_error_for_logging(e)}"
        )
        return False


# ============================================================================
# API ENDPOINTS
# ============================================================================


@extractor_bp.route("/download", methods=["GET"])
@limiter.limit("10 per minute")
def download_extractor():
    """
    Download the ForensicBridge extractor.

    Priority:
    1. Zip package (recommended - includes all DLLs)
    2. Local .exe file if available
    3. Cached GitHub release
    4. Bootstrap installer script (fallback)

    Query params:
        ?format=zip - Force zip package download
        ?format=exe - Force exe-only download
        ?format=bat - Force bootstrap .bat download
    """
    requested_format = request.args.get("format", "").lower()

    if requested_format == "bat":
        return download_bootstrap()

    if requested_format == "exe":
        return download_extractor_exe()

    # Try zip package first (recommended - includes all dependencies)
    zip_path = find_zip_path()
    if zip_path:
        logger.info(f"Serving deployment zip from: {zip_path}")
        return send_file(
            zip_path,
            as_attachment=True,
            download_name="QBExtractor-deploy.zip",
            mimetype="application/zip",
        )

    # Fall back to local exe file
    extractor_path = find_extractor_path()
    if extractor_path:
        logger.info(f"Serving extractor from: {extractor_path}")
        return send_file(
            extractor_path,
            as_attachment=True,
            download_name="QBExtractor.exe",
            mimetype="application/octet-stream",
        )

    # Try cached version
    if is_cache_valid():
        cache_path = os.path.join(CACHE_DIR, "QBExtractor.exe")
        logger.info(f"Serving extractor from cache: {cache_path}")
        return send_file(
            cache_path,
            as_attachment=True,
            download_name="QBExtractor.exe",
            mimetype="application/octet-stream",
        )

    # Try to download and cache from GitHub
    cached_path = download_and_cache_from_github()
    if cached_path:
        logger.info(f"Serving freshly cached extractor: {cached_path}")
        return send_file(
            cached_path,
            as_attachment=True,
            download_name="QBExtractor.exe",
            mimetype="application/octet-stream",
        )

    # Fallback: serve the bootstrap installer
    if os.path.isfile(BOOTSTRAP_BAT):
        logger.info("Serving bootstrap installer (BAT) as fallback")
        return send_file(
            BOOTSTRAP_BAT,
            as_attachment=True,
            download_name="ForensicBridge_Install.bat",
            mimetype="application/x-msdos-program",
        )

    # Last resort: generate on the fly
    logger.warning("No extractor or bootstrap found, generating fallback script")
    return Response(
        generate_fallback_installer(),
        mimetype="application/x-msdos-program",
        headers={
            "Content-Disposition": "attachment; filename=ForensicBridge_Install.bat"
        },
    )


@extractor_bp.route("/download-exe", methods=["GET"])
@limiter.limit("10 per minute")
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
            download_name="QBExtractor.exe",
            mimetype="application/octet-stream",
        )

    if is_cache_valid():
        cache_path = os.path.join(CACHE_DIR, "QBExtractor.exe")
        return send_file(
            cache_path,
            as_attachment=True,
            download_name="QBExtractor.exe",
            mimetype="application/octet-stream",
        )

    cached_path = download_and_cache_from_github()
    if cached_path:
        return send_file(
            cached_path,
            as_attachment=True,
            download_name="QBExtractor.exe",
            mimetype="application/octet-stream",
        )

    if check_github_release_exists():
        return redirect(GITHUB_RELEASE_URL, code=302)

    return (
        jsonify(
            {
                "error": "Extractor executable not available",
                "message": "Please download from GitHub releases directly",
                "github_releases": GITHUB_RELEASES_PAGE,
            }
        ),
        404,
    )


@extractor_bp.route("/bootstrap", methods=["GET"])
@limiter.limit("10 per minute")
def download_bootstrap():
    """Download the bootstrap installer batch file."""
    if os.path.isfile(BOOTSTRAP_BAT):
        return send_file(
            BOOTSTRAP_BAT,
            as_attachment=True,
            download_name="ForensicBridge_Install.bat",
            mimetype="application/x-msdos-program",
        )

    return Response(
        generate_fallback_installer(),
        mimetype="application/x-msdos-program",
        headers={
            "Content-Disposition": "attachment; filename=ForensicBridge_Install.bat"
        },
    )


@extractor_bp.route("/bootstrap-ps1", methods=["GET"])
@limiter.limit("10 per minute")
def download_bootstrap_ps1():
    """Download the PowerShell bootstrap installer script."""
    if os.path.isfile(BOOTSTRAP_PS1):
        return send_file(
            BOOTSTRAP_PS1,
            as_attachment=True,
            download_name="ForensicBridge_Bootstrap.ps1",
            mimetype="application/octet-stream",
        )

    return (
        jsonify(
            {
                "error": "PowerShell bootstrap script not found",
                "alternative": "/api/extractor/bootstrap",
            }
        ),
        404,
    )


@extractor_bp.route("/info", methods=["GET"])
def extractor_info():
    """Get information about the extractor availability."""
    zip_path = find_zip_path()
    zip_metadata = get_zip_metadata() if zip_path else {}
    extractor_path = find_extractor_path()
    cache_valid = is_cache_valid()
    cache_metadata = get_cache_metadata() if cache_valid else {}

    # Prefer zip package (includes all DLLs)
    if zip_path:
        file_size = os.path.getsize(zip_path)
        # Regenerate metadata if needed
        if not zip_metadata or zip_metadata.get("size") != file_size:
            zip_metadata = generate_zip_metadata(zip_path)
        return jsonify(
            {
                "available": True,
                "source": "zip_package",
                "type": "full_package",
                "download_url": "/api/extractor/download",
                "direct_zip_url": "/api/extractor/download-zip",
                "file_size": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "sha256": zip_metadata.get("sha256"),
                "version": zip_metadata.get("version", EXTRACTOR_VERSION),
                "verify_url": "/api/extractor/zip/verify",
                "message": "Full deployment package with all DLLs included",
                "security_info_url": "/api/extractor/security-info",
                "security_note": WINDOWS_SECURITY_INSTRUCTIONS["summary"],
            }
        )

    if extractor_path:
        file_size = os.path.getsize(extractor_path)
        return jsonify(
            {
                "available": True,
                "source": "local",
                "type": "full_installer",
                "download_url": "/api/extractor/download-exe",
                "file_size": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
            }
        )

    if cache_valid:
        cache_path = os.path.join(CACHE_DIR, "QBExtractor.exe")
        file_size = os.path.getsize(cache_path)
        return jsonify(
            {
                "available": True,
                "source": "cached",
                "type": "full_installer",
                "download_url": "/api/extractor/download-exe",
                "file_size": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "cached_at": cache_metadata.get("cached_at"),
                "release_tag": cache_metadata.get("release_tag"),
            }
        )

    github_available = check_github_release_exists()
    if github_available:
        return jsonify(
            {
                "available": True,
                "source": "github",
                "type": "full_installer",
                "download_url": "/api/extractor/download-exe",
                "github_direct_url": GITHUB_RELEASE_URL,
                "github_releases_page": GITHUB_RELEASES_PAGE,
            }
        )

    return jsonify(
        {
            "available": True,
            "source": "bootstrap",
            "type": "bootstrap_installer",
            "download_url": "/api/extractor/download",
            "bootstrap_url": "/api/extractor/bootstrap",
            "github_releases_page": GITHUB_RELEASES_PAGE,
            "message": "Full extractor not cached. Bootstrap installer will download it.",
        }
    )


@extractor_bp.route("/github-download", methods=["GET"])
@limiter.limit("10 per minute")
def github_download():
    """Direct redirect to GitHub releases download."""
    return redirect(GITHUB_RELEASE_URL, code=302)


@extractor_bp.route("/releases", methods=["GET"])
def releases_page():
    """Redirect to GitHub releases page."""
    return redirect(GITHUB_RELEASES_PAGE, code=302)


@extractor_bp.route("/security-info", methods=["GET"])
def security_info():
    """
    Get Windows security bypass instructions for the extractor.

    Windows may show security warnings when downloading or running the extractor
    because it is not signed with an EV code signing certificate. These instructions
    help users understand and bypass these warnings safely.
    """
    return jsonify(
        {
            "success": True,
            "security_instructions": WINDOWS_SECURITY_INSTRUCTIONS,
            "version": EXTRACTOR_VERSION,
        }
    )


@extractor_bp.route("/status", methods=["GET"])
@require_auth
def extractor_status():
    """Check the current status of all download options. Requires authentication."""
    extractor_path = find_extractor_path()
    cache_valid = is_cache_valid()
    cache_metadata = get_cache_metadata()
    github_available = check_github_release_exists()
    zip_path = find_zip_path()
    zip_metadata = get_zip_metadata() if zip_path else {}

    cache_path = os.path.join(CACHE_DIR, "QBExtractor.exe")

    return jsonify(
        {
            "local_installer": {
                "available": extractor_path is not None,
                "size": os.path.getsize(extractor_path) if extractor_path else None,
            },
            "cached_installer": {
                "available": cache_valid,
                "size": (
                    os.path.getsize(cache_path)
                    if cache_valid and os.path.exists(cache_path)
                    else None
                ),
                "cached_at": cache_metadata.get("cached_at"),
                "sha256": (
                    cache_metadata.get("sha256", "")[:16] + "..."
                    if cache_metadata.get("sha256")
                    else None
                ),
                "release_tag": cache_metadata.get("release_tag"),
            },
            "zip_package": {
                "available": zip_path is not None,
                "size": os.path.getsize(zip_path) if zip_path else None,
                "sha256": (
                    zip_metadata.get("sha256", "")[:16] + "..."
                    if zip_metadata.get("sha256")
                    else None
                ),
                "download_url": "/api/extractor/download-zip" if zip_path else None,
            },
            "bootstrap_bat": {
                "available": os.path.isfile(BOOTSTRAP_BAT),
            },
            "bootstrap_ps1": {
                "available": os.path.isfile(BOOTSTRAP_PS1),
            },
            "github_release": {
                "available": github_available,
                "url": GITHUB_RELEASE_URL,
            },
            "fallback_generator": {
                "available": True,
                "description": "Can always generate a minimal download script",
            },
            "recommended_download": (
                "/api/extractor/download-zip"
                if zip_path
                else (
                    "/api/extractor/download-exe"
                    if (extractor_path or cache_valid or github_available)
                    else "/api/extractor/download"
                )
            ),
        }
    )


@extractor_bp.route("/cache/refresh", methods=["POST"])
@admin_required
def refresh_cache():
    """Force refresh the cached extractor from GitHub."""
    logger.info("Force refreshing extractor cache...")

    cache_path = os.path.join(CACHE_DIR, "QBExtractor.exe")
    if os.path.exists(cache_path):
        os.remove(cache_path)
    if os.path.exists(CACHE_METADATA_FILE):
        os.remove(CACHE_METADATA_FILE)

    cached_path = download_and_cache_from_github()

    if cached_path:
        metadata = get_cache_metadata()
        return jsonify(
            {
                "success": True,
                "message": "Cache refreshed successfully",
                "cached_at": metadata.get("cached_at"),
                "size": metadata.get("size"),
                "sha256": (
                    metadata.get("sha256", "")[:16] + "..."
                    if metadata.get("sha256")
                    else None
                ),
            }
        )

    return (
        jsonify({"success": False, "error": "Failed to refresh cache from GitHub"}),
        500,
    )


@extractor_bp.route("/cache/clear", methods=["POST"])
@admin_required
def clear_cache():
    """Clear the cached extractor."""
    try:
        cache_path = os.path.join(CACHE_DIR, "QBExtractor.exe")
        if os.path.exists(cache_path):
            os.remove(cache_path)
        if os.path.exists(CACHE_METADATA_FILE):
            os.remove(CACHE_METADATA_FILE)

        return jsonify({"success": True, "message": "Cache cleared successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def generate_fallback_installer():
    """Generate a minimal batch installer script on the fly"""
    return f"""@echo off
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
"""


@extractor_bp.route("/version", methods=["GET"])
def extractor_version():
    """Get the current extractor version and compatibility info."""
    return jsonify(
        {
            "version": EXTRACTOR_VERSION,
            "minimum_qb_version": "QuickBooks Desktop 2018+",
            "supported_backends": [
                {
                    "name": "QBFC16",
                    "type": "QuickBooks SDK",
                    "recommended": True,
                    "download_url": "https://developer.intuit.com",
                },
                {
                    "name": "QODBC",
                    "type": "ODBC Driver",
                    "recommended": False,
                    "download_url": "https://qodbc.com/qodbc-downloads/",
                },
            ],
            "features": [
                "Multi-backend support (QBFC + QODBC)",
                "Automatic backend detection",
                "Retry with exponential backoff",
                "Entity-level failure isolation",
                "Checkpoint/resume support",
                "AES-256-GCM encryption",
                "Low-memory streaming",
            ],
            "documentation": "/api/extractor/docs",
        }
    )


@extractor_bp.route("/docs", methods=["GET"])
def extractor_docs():
    """Return documentation for the extractor API."""
    return jsonify(
        {
            "title": "ForensicBridge Extractor API",
            "version": EXTRACTOR_VERSION,
            "endpoints": {
                "GET /api/extractor/download": {
                    "description": "Smart download - returns zip package (preferred), exe, or bootstrap installer",
                    "params": {
                        "format": 'Optional: "zip", "exe", or "bat" to force specific format'
                    },
                },
                "GET /api/extractor/download-exe": {
                    "description": "Direct executable download, falls back to GitHub redirect"
                },
                "GET /api/extractor/download-zip": {
                    "description": "Download the full deployment package (zip with exe + all DLLs)"
                },
                "GET /api/extractor/zip/info": {
                    "description": "Get zip file info including SHA256 hash for verification"
                },
                "POST /api/extractor/zip/verify": {
                    "description": "Verify a downloaded zip by submitting its SHA256 hash",
                    "body": {"sha256": "your_computed_hash"},
                },
                "POST /api/extractor/zip/regenerate-hash": {
                    "description": "Regenerate zip metadata after updating the file on server"
                },
                "GET /api/extractor/bootstrap": {
                    "description": "Download the bootstrap installer batch file"
                },
                "GET /api/extractor/info": {
                    "description": "Get availability information about the extractor"
                },
                "GET /api/extractor/status": {
                    "description": "Full status of all download sources"
                },
                "GET /api/extractor/version": {
                    "description": "Get current version and compatibility info"
                },
                "POST /api/extractor/cache/refresh": {
                    "description": "Force refresh cached extractor from GitHub"
                },
                "POST /api/extractor/cache/clear": {
                    "description": "Clear cached extractor files"
                },
            },
            "installation_steps": [
                "1. Download ForensicBridge_Install.bat from /api/extractor/bootstrap",
                '2. Right-click and "Run as Administrator"',
                "3. The installer will download and install QBExtractor.exe",
                "4. Open QuickBooks Desktop with your company file",
                "5. Run QBExtractor.exe and enter your session code",
                '6. When prompted in QuickBooks, click "Yes, always allow"',
            ],
            "troubleshooting": {
                "no_backend": "Install QuickBooks SDK (QBFC16) from developer.intuit.com or QODBC from qodbc.com",
                "connection_failed": "Ensure QuickBooks Desktop is open with a company file",
                "permission_denied": "Run as Administrator and allow the application in QuickBooks",
                "download_failed": "Check firewall settings or download directly from GitHub releases",
            },
        }
    )


# ============================================================================
# ZIP DEPLOYMENT PACKAGE ENDPOINTS
# ============================================================================


@extractor_bp.route("/download-zip", methods=["GET"])
@limiter.limit("10 per minute")
def download_zip():
    """
    Download the full QBExtractor deployment package (zip).

    The zip contains:
    - QBExtractor.exe
    - All required DLLs
    - Configuration files
    """
    zip_path = find_zip_path()

    if not zip_path:
        return (
            jsonify(
                {
                    "error": "Deployment package not available",
                    "message": "The QBExtractor-deploy.zip file is not deployed on this server",
                    "alternative": "/api/extractor/download-exe",
                }
            ),
            404,
        )

    logger.info(f"Serving deployment zip from: {zip_path}")
    return send_file(
        zip_path,
        as_attachment=True,
        download_name="QBExtractor-deploy.zip",
        mimetype="application/zip",
    )


@extractor_bp.route("/zip/info", methods=["GET"])
def zip_info():
    """
    Get information about the deployment zip including hash for verification.

    Returns:
    - sha256: SHA256 hash for verification
    - size: File size in bytes
    - available: Whether the zip is available for download
    """
    zip_path = find_zip_path()

    if not zip_path:
        return jsonify(
            {
                "available": False,
                "message": "Deployment zip not available on this server",
            }
        )

    # Check if we have cached metadata
    metadata = get_zip_metadata()

    # Regenerate if metadata is missing or file has changed
    current_size = os.path.getsize(zip_path)
    if not metadata or metadata.get("size") != current_size:
        metadata = generate_zip_metadata(zip_path)

    return jsonify(
        {
            "available": True,
            "filename": "QBExtractor-deploy.zip",
            "sha256": metadata.get("sha256"),
            "size": metadata.get("size"),
            "size_mb": round(metadata.get("size", 0) / (1024 * 1024), 2),
            "version": metadata.get("version", EXTRACTOR_VERSION),
            "download_url": "/api/extractor/download-zip",
            "generated_at": metadata.get("generated_at"),
        }
    )


@extractor_bp.route("/zip/verify", methods=["POST"])
def verify_zip():
    """
    Verify a downloaded zip file by its hash.

    Request body:
    {
        "sha256": "client_computed_hash"
    }

    Returns:
    - valid: Boolean indicating if hash matches
    - expected_hash: The server's hash (first 16 chars for security)
    """
    zip_path = find_zip_path()

    if not zip_path:
        return jsonify({"error": "Deployment zip not available for verification"}), 404

    data = request.get_json() or {}
    client_hash = data.get("sha256", "").lower().strip()

    if not client_hash:
        return (
            jsonify(
                {
                    "error": "Missing sha256 hash in request body",
                    "example": {"sha256": "your_computed_hash_here"},
                }
            ),
            400,
        )

    # Get or compute server hash
    metadata = get_zip_metadata()
    current_size = os.path.getsize(zip_path)
    if not metadata or metadata.get("size") != current_size:
        metadata = generate_zip_metadata(zip_path)

    server_hash = metadata.get("sha256", "").lower()
    is_valid = client_hash == server_hash

    response = {
        "valid": is_valid,
        "message": (
            "Hash verification successful"
            if is_valid
            else "Hash mismatch - file may be corrupted or tampered"
        ),
    }

    if not is_valid:
        # Provide partial hash for debugging
        response["expected_hash_prefix"] = server_hash[:16] + "..."
        response["provided_hash_prefix"] = client_hash[:16] + "..."

    return jsonify(response)


@extractor_bp.route("/zip/regenerate-hash", methods=["POST"])
@admin_required
def regenerate_zip_hash():
    """
    Force regeneration of the zip file hash metadata.
    Use this after updating the zip file on the server.
    """
    zip_path = find_zip_path()

    if not zip_path:
        return jsonify({"error": "No deployment zip found to hash"}), 404

    logger.info(f"Regenerating hash for: {zip_path}")
    metadata = generate_zip_metadata(zip_path)

    return jsonify(
        {
            "success": True,
            "sha256": metadata.get("sha256"),
            "size": metadata.get("size"),
            "generated_at": metadata.get("generated_at"),
        }
    )


@extractor_bp.route("/health", methods=["GET"])
def extractor_health():
    """Health check endpoint for monitoring."""
    extractor_path = find_extractor_path()
    cache_valid = is_cache_valid()
    github_available = check_github_release_exists()
    zip_path = find_zip_path()

    # Determine overall health
    is_healthy = (
        extractor_path is not None
        or cache_valid
        or github_available
        or zip_path is not None
    )

    response = {
        "healthy": is_healthy,
        "version": EXTRACTOR_VERSION,
        "sources": {
            "local": extractor_path is not None,
            "cache": cache_valid,
            "github": github_available,
            "bootstrap": os.path.isfile(BOOTSTRAP_BAT),
            "zip_package": zip_path is not None,
        },
    }

    status_code = 200 if is_healthy else 503
    return jsonify(response), status_code
