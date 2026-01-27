"""
ForensicBridge Extractor Download API
Serves the ForensicBridge Windows extractor executable
"""

import os
import logging
from flask import Blueprint, send_file, jsonify, current_app, redirect

logger = logging.getLogger(__name__)

extractor_bp = Blueprint('extractor', __name__, url_prefix='/api/extractor')

# GitHub repository for releases
GITHUB_REPO = 'sivaharanj7805/QBMigration'
GITHUB_RELEASE_URL = f'https://github.com/{GITHUB_REPO}/releases/latest/download/ForensicBridge_Setup.exe'
GITHUB_RELEASES_PAGE = f'https://github.com/{GITHUB_REPO}/releases'

# Default locations to search for the extractor
DEFAULT_EXTRACTOR_PATHS = [
    '/var/www/forensicbridge/extractor/ForensicBridge_Setup.exe',
    '/opt/forensicbridge/extractor/ForensicBridge_Setup.exe',
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'ForensicBridge_Setup.exe'),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'extractor', 'ForensicBridge_Setup.exe'),
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


@extractor_bp.route('/download', methods=['GET'])
def download_extractor():
    """
    Download the ForensicBridge extractor executable.

    Returns:
        - The executable file if found locally
        - Redirect to GitHub releases if not found locally
    """
    extractor_path = find_extractor_path()

    if extractor_path:
        logger.info(f"Serving extractor from: {extractor_path}")
        return send_file(
            extractor_path,
            as_attachment=True,
            download_name='ForensicBridge_Setup.exe',
            mimetype='application/octet-stream'
        )

    # File not found locally - redirect to GitHub releases
    logger.info("Extractor not found locally, redirecting to GitHub releases")
    return redirect(GITHUB_RELEASE_URL, code=302)


@extractor_bp.route('/info', methods=['GET'])
def extractor_info():
    """
    Get information about the extractor availability.

    Returns:
        - available: whether the extractor is available for download
        - source: 'local' or 'github'
        - download_url: URL to download the extractor
    """
    extractor_path = find_extractor_path()

    if extractor_path:
        # Get file size
        file_size = os.path.getsize(extractor_path)

        return jsonify({
            'available': True,
            'source': 'local',
            'download_url': '/api/extractor/download',
            'file_size': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2)
        })

    # Local file not available, but GitHub release is always available
    return jsonify({
        'available': True,
        'source': 'github',
        'download_url': '/api/extractor/download',
        'github_direct_url': GITHUB_RELEASE_URL,
        'github_releases_page': GITHUB_RELEASES_PAGE,
        'message': 'Download will redirect to GitHub releases'
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
