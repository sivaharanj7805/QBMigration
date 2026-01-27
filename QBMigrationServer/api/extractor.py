"""
ForensicBridge Extractor Download API
Serves the ForensicBridge Windows extractor executable
"""

import os
import logging
from flask import Blueprint, send_file, jsonify, current_app

logger = logging.getLogger(__name__)

extractor_bp = Blueprint('extractor', __name__, url_prefix='/api/extractor')

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
        - The executable file if found
        - 404 with helpful error message if not found
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

    # File not found - provide helpful error
    logger.warning("Extractor file not found in any configured location")

    return jsonify({
        'success': False,
        'error': 'Extractor not available',
        'message': 'The ForensicBridge extractor has not been deployed yet. '
                   'Please contact support or check back later.',
        'hint': 'For administrators: Set EXTRACTOR_PATH environment variable '
                'or place ForensicBridge_Setup.exe in /var/www/forensicbridge/extractor/'
    }), 404


@extractor_bp.route('/info', methods=['GET'])
def extractor_info():
    """
    Get information about the extractor availability.

    Returns:
        - available: whether the extractor is available for download
        - version: the extractor version (if available)
    """
    extractor_path = find_extractor_path()

    if extractor_path:
        # Get file size
        file_size = os.path.getsize(extractor_path)

        return jsonify({
            'available': True,
            'download_url': '/api/extractor/download',
            'file_size': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2)
        })

    return jsonify({
        'available': False,
        'message': 'Extractor not yet deployed'
    })
