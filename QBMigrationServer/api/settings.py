"""
ForensicBridge Settings API
Whitelabel branding configuration endpoints.
"""

import logging

from api.auth import require_auth
from extensions import limiter
from flask import Blueprint, jsonify, request
from models.database import db
from models.whitelabel_settings import WhitelabelSettings

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")
logger = logging.getLogger(__name__)


@settings_bp.route("/whitelabel", methods=["GET"])
@require_auth
def get_whitelabel():
    """Get current user's whitelabel branding config."""
    user_id = request.current_user["user_id"]

    settings = WhitelabelSettings.query.filter_by(user_id=user_id).first()
    if not settings:
        # Return defaults
        return jsonify({"success": True, "config": WhitelabelSettings().to_dict()}), 200

    return jsonify({"success": True, "config": settings.to_dict()}), 200


@settings_bp.route("/whitelabel", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def save_whitelabel():
    """Save whitelabel branding config for current user."""
    user_id = request.current_user["user_id"]
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    # Validate input
    cleaned, error = WhitelabelSettings.validate_config(data)
    if error:
        return jsonify({"success": False, "error": error}), 400

    try:
        settings = WhitelabelSettings.query.filter_by(user_id=user_id).first()

        if settings:
            # Update existing
            for key, value in cleaned.items():
                setattr(settings, key, value)
        else:
            # Create new
            settings = WhitelabelSettings(user_id=user_id, **cleaned)
            db.session.add(settings)

        db.session.commit()
        logger.info(f"Whitelabel settings saved for user {user_id}")

        return (
            jsonify(
                {
                    "success": True,
                    "config": settings.to_dict(),
                    "message": "Branding settings saved",
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(f"Failed to save whitelabel settings for user {user_id}: {e}")
        db.session.rollback()
        return (
            jsonify({"success": False, "error": "Failed to save branding settings"}),
            500,
        )
