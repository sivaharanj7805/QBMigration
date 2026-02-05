"""
WebSocket API for real-time migration progress updates
Uses Flask-SocketIO for bidirectional communication

FIX CRIT-01: Added authentication to REST endpoints
FIX CRIT-03: Configured proper CORS origins instead of wildcard
FIX LOW-04: Replaced print statements with logging
"""

import hmac
import logging
import os
from datetime import datetime, timezone
from functools import wraps

import jwt
from flask import Blueprint, request
from flask_socketio import SocketIO, emit, join_room, leave_room

logger = logging.getLogger(__name__)

# Blueprint for REST endpoints related to WebSocket
websocket_bp = Blueprint("websocket", __name__, url_prefix="/api/ws")

# SocketIO instance - initialized in app.py
socketio = None

# Internal API key for worker authentication (CRIT-01 FIX)
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")


def require_internal_auth(f):
    """
    Decorator to require internal API authentication for WebSocket REST endpoints.
    FIX CRIT-01: Prevents unauthorized users from spoofing migration status.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for internal API key
        api_key = request.headers.get("X-Internal-API-Key")

        if not INTERNAL_API_KEY:
            logger.error(
                "INTERNAL_API_KEY not configured - WebSocket REST endpoints disabled"
            )
            return {"success": False, "error": "Server misconfiguration"}, 500

        if not api_key:
            logger.warning(
                f"WebSocket REST endpoint called without API key from {request.remote_addr}"
            )
            return {"success": False, "error": "Authentication required"}, 401

        # Use constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(api_key, INTERNAL_API_KEY):
            logger.warning(
                f"Invalid API key for WebSocket REST endpoint from {request.remote_addr}"
            )
            return {"success": False, "error": "Invalid API key"}, 403

        return f(*args, **kwargs)

    return decorated_function


def get_allowed_cors_origins(app):
    """
    Get allowed CORS origins from configuration.
    FIX CRIT-03: No more wildcard CORS - explicitly list allowed origins.
    """
    # Get from config or environment
    allowed_origins = app.config.get("WEBSOCKET_CORS_ORIGINS")

    if allowed_origins:
        if isinstance(allowed_origins, str):
            return [o.strip() for o in allowed_origins.split(",")]
        return allowed_origins

    # Fallback to SERVER_URL if configured
    server_url = app.config.get("SERVER_URL")
    if server_url:
        origins = [server_url]
        # Also allow www variant
        if server_url.startswith("https://"):
            domain = server_url.replace("https://", "")
            if domain.startswith("www."):
                origins.append(f"https://{domain[4:]}")
            else:
                origins.append(f"https://www.{domain}")
        return origins

    # SECURITY FIX: Only allow localhost in development mode
    # Production MUST have explicit WEBSOCKET_CORS_ORIGINS or SERVER_URL
    flask_env = os.getenv("FLASK_ENV", "development")
    if flask_env == "development" or app.config.get("DEBUG"):
        logger.warning(
            "Using development CORS origins for WebSocket (FLASK_ENV=development)"
        )
        return [
            "http://localhost:3000",
            "http://localhost:5000",
            "http://127.0.0.1:5000",
        ]

    # Production without configuration - raise error instead of silently failing
    logger.error(
        "SECURITY: No WEBSOCKET_CORS_ORIGINS configured for production! "
        "WebSocket connections will be blocked. Set WEBSOCKET_CORS_ORIGINS or SERVER_URL."
    )
    return []


def init_socketio(app, secret_key):
    """Initialize SocketIO with the Flask app"""
    global socketio

    # Use threading for testing, eventlet for production
    if app.config.get("TESTING"):
        async_mode = "threading"
    else:
        # Try eventlet first, fall back to threading
        try:
            pass

            async_mode = "eventlet"
        except ImportError:
            async_mode = "threading"

    # FIX CRIT-03: Use explicit CORS origins instead of wildcard
    allowed_origins = get_allowed_cors_origins(app)

    socketio = SocketIO(
        app,
        cors_allowed_origins=allowed_origins,
        async_mode=async_mode,
        logger=not app.config.get("TESTING"),
        engineio_logger=not app.config.get("TESTING"),
    )

    logger.info(f"WebSocket initialized with CORS origins: {allowed_origins}")

    register_handlers(socketio, secret_key)
    return socketio


def register_handlers(sio, secret_key):
    """Register SocketIO event handlers"""

    @sio.on("connect")
    def handle_connect():
        """Handle client connection"""
        # FIX LOW-04: Use logging instead of print
        logger.debug(f"[WebSocket] Client connected: {request.sid}")
        emit("connected", {"status": "connected", "sid": request.sid})

    @sio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnect"""
        # FIX LOW-04: Use logging instead of print
        logger.debug(f"[WebSocket] Client disconnected: {request.sid}")

    @sio.on("authenticate")
    def handle_authenticate(data):
        """Authenticate WebSocket connection with JWT token"""
        token = data.get("token")
        if not token:
            emit("error", {"message": "No token provided"})
            return

        try:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            user_id = payload.get("user_id")

            # Join user-specific room
            join_room(f"user_{user_id}")
            emit("authenticated", {"user_id": user_id})
            # FIX LOW-04: Use logging instead of print
            logger.info(f"[WebSocket] User {user_id} authenticated")

        except jwt.ExpiredSignatureError:
            emit("error", {"message": "Token expired"})
        except jwt.InvalidTokenError:
            emit("error", {"message": "Invalid token"})

    @sio.on("subscribe_migration")
    def handle_subscribe_migration(data):
        """Subscribe to migration progress updates"""
        migration_id = data.get("migration_id")
        if not migration_id:
            emit("error", {"message": "No migration_id provided"})
            return

        join_room(f"migration_{migration_id}")
        emit("subscribed", {"migration_id": migration_id})
        # FIX LOW-04: Use logging instead of print
        logger.debug(f"[WebSocket] Client subscribed to migration: {migration_id}")

    @sio.on("unsubscribe_migration")
    def handle_unsubscribe_migration(data):
        """Unsubscribe from migration progress updates"""
        migration_id = data.get("migration_id")
        if migration_id:
            leave_room(f"migration_{migration_id}")
            emit("unsubscribed", {"migration_id": migration_id})


def emit_migration_progress(
    migration_id: str,
    progress: int,
    step: str,
    status: str = "processing",
    details: dict = None,
):
    """
    Emit progress update to all clients subscribed to a migration

    Args:
        migration_id: The migration ID
        progress: Progress percentage (0-100)
        step: Current step description
        status: Status (uploading, processing, completed, failed)
        details: Optional additional details
    """
    if socketio is None:
        return

    data = {
        "migration_id": migration_id,
        "progress": progress,
        "step": step,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if details:
        data["details"] = details

    socketio.emit("migration_progress", data, room=f"migration_{migration_id}")


def emit_migration_completed(migration_id: str, results: dict):
    """
    Emit completion notification

    Args:
        migration_id: The migration ID
        results: Migration results (totals, errors, etc.)
    """
    if socketio is None:
        return

    data = {
        "migration_id": migration_id,
        "status": "completed",
        "progress": 100,
        "step": "Migration complete",
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    socketio.emit("migration_completed", data, room=f"migration_{migration_id}")


def emit_migration_failed(migration_id: str, error: str, error_code: str = None):
    """
    Emit failure notification

    Args:
        migration_id: The migration ID
        error: Error message
        error_code: Optional error code
    """
    if socketio is None:
        return

    data = {
        "migration_id": migration_id,
        "status": "failed",
        "error": error,
        "error_code": error_code,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    socketio.emit("migration_failed", data, room=f"migration_{migration_id}")


# REST endpoints for manual progress updates (from Celery workers)
# FIX CRIT-01: All REST endpoints now require internal API authentication
@websocket_bp.route("/emit/progress", methods=["POST"])
@require_internal_auth
def emit_progress_rest():
    """REST endpoint for Celery workers to emit progress (requires internal auth)"""
    data = request.get_json()

    migration_id = data.get("migration_id")
    progress = data.get("progress", 0)
    step = data.get("step", "")
    status = data.get("status", "processing")
    details = data.get("details")

    emit_migration_progress(migration_id, progress, step, status, details)

    return {"success": True}


@websocket_bp.route("/emit/completed", methods=["POST"])
@require_internal_auth
def emit_completed_rest():
    """REST endpoint for completion notification (requires internal auth)"""
    data = request.get_json()

    migration_id = data.get("migration_id")
    results = data.get("results", {})

    emit_migration_completed(migration_id, results)

    return {"success": True}


@websocket_bp.route("/emit/failed", methods=["POST"])
@require_internal_auth
def emit_failed_rest():
    """REST endpoint for failure notification (requires internal auth)"""
    data = request.get_json()

    migration_id = data.get("migration_id")
    error = data.get("error", "Unknown error")
    error_code = data.get("error_code")

    emit_migration_failed(migration_id, error, error_code)

    return {"success": True}
