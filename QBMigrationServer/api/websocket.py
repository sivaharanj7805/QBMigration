"""
WebSocket API for real-time migration progress updates
Uses Flask-SocketIO for bidirectional communication
"""

from flask import Blueprint, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from functools import wraps
import jwt
from datetime import datetime

# Blueprint for REST endpoints related to WebSocket
websocket_bp = Blueprint('websocket', __name__, url_prefix='/api/ws')

# SocketIO instance - initialized in app.py
socketio = None


def init_socketio(app, secret_key):
    """Initialize SocketIO with the Flask app"""
    global socketio

    # Use threading for testing, eventlet for production
    if app.config.get('TESTING'):
        async_mode = 'threading'
    else:
        # Try eventlet first, fall back to threading
        try:
            import eventlet
            async_mode = 'eventlet'
        except ImportError:
            async_mode = 'threading'

    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode=async_mode,
        logger=not app.config.get('TESTING'),
        engineio_logger=not app.config.get('TESTING')
    )

    register_handlers(socketio, secret_key)
    return socketio


def register_handlers(sio, secret_key):
    """Register SocketIO event handlers"""
    
    @sio.on('connect')
    def handle_connect():
        """Handle client connection"""
        print(f"[WebSocket] Client connected: {request.sid}")
        emit('connected', {'status': 'connected', 'sid': request.sid})
    
    @sio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnect"""
        print(f"[WebSocket] Client disconnected: {request.sid}")
    
    @sio.on('authenticate')
    def handle_authenticate(data):
        """Authenticate WebSocket connection with JWT token"""
        token = data.get('token')
        if not token:
            emit('error', {'message': 'No token provided'})
            return
        
        try:
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            user_id = payload.get('user_id')
            
            # Join user-specific room
            join_room(f'user_{user_id}')
            emit('authenticated', {'user_id': user_id})
            print(f"[WebSocket] User {user_id} authenticated")
            
        except jwt.ExpiredSignatureError:
            emit('error', {'message': 'Token expired'})
        except jwt.InvalidTokenError:
            emit('error', {'message': 'Invalid token'})
    
    @sio.on('subscribe_migration')
    def handle_subscribe_migration(data):
        """Subscribe to migration progress updates"""
        migration_id = data.get('migration_id')
        if not migration_id:
            emit('error', {'message': 'No migration_id provided'})
            return
        
        join_room(f'migration_{migration_id}')
        emit('subscribed', {'migration_id': migration_id})
        print(f"[WebSocket] Client subscribed to migration: {migration_id}")
    
    @sio.on('unsubscribe_migration')
    def handle_unsubscribe_migration(data):
        """Unsubscribe from migration progress updates"""
        migration_id = data.get('migration_id')
        if migration_id:
            leave_room(f'migration_{migration_id}')
            emit('unsubscribed', {'migration_id': migration_id})


def emit_migration_progress(migration_id: str, progress: int, step: str, 
                           status: str = 'processing', details: dict = None):
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
        'migration_id': migration_id,
        'progress': progress,
        'step': step,
        'status': status,
        'timestamp': datetime.utcnow().isoformat(),
    }
    
    if details:
        data['details'] = details
    
    socketio.emit('migration_progress', data, room=f'migration_{migration_id}')


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
        'migration_id': migration_id,
        'status': 'completed',
        'progress': 100,
        'step': 'Migration complete',
        'results': results,
        'timestamp': datetime.utcnow().isoformat(),
    }
    
    socketio.emit('migration_completed', data, room=f'migration_{migration_id}')


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
        'migration_id': migration_id,
        'status': 'failed',
        'error': error,
        'error_code': error_code,
        'timestamp': datetime.utcnow().isoformat(),
    }
    
    socketio.emit('migration_failed', data, room=f'migration_{migration_id}')


# REST endpoints for manual progress updates (from Celery workers)
@websocket_bp.route('/emit/progress', methods=['POST'])
def emit_progress_rest():
    """REST endpoint for Celery workers to emit progress"""
    data = request.get_json()
    
    migration_id = data.get('migration_id')
    progress = data.get('progress', 0)
    step = data.get('step', '')
    status = data.get('status', 'processing')
    details = data.get('details')
    
    emit_migration_progress(migration_id, progress, step, status, details)
    
    return {'success': True}


@websocket_bp.route('/emit/completed', methods=['POST'])
def emit_completed_rest():
    """REST endpoint for completion notification"""
    data = request.get_json()
    
    migration_id = data.get('migration_id')
    results = data.get('results', {})
    
    emit_migration_completed(migration_id, results)
    
    return {'success': True}


@websocket_bp.route('/emit/failed', methods=['POST'])
def emit_failed_rest():
    """REST endpoint for failure notification"""
    data = request.get_json()
    
    migration_id = data.get('migration_id')
    error = data.get('error', 'Unknown error')
    error_code = data.get('error_code')
    
    emit_migration_failed(migration_id, error, error_code)
    
    return {'success': True}
