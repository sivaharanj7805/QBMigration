from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models.database import db
from models.migration import Migration
from workers.migration_worker import process_migration
import os
from datetime import datetime, timedelta

upload_bp = Blueprint('upload', __name__)

@upload_bp.route('/api/upload', methods=['POST'])
@login_required
def upload_encrypted_data():
    """
    Receive encrypted QuickBooks data from client
    
    Expected payload:
    {
        "session_id": "unique-session-id",
        "encrypted_data": "base64-encoded-encrypted-blob",
        "timestamp": "2026-01-02T12:00:00Z"
    }
    """
    
    try:
        # Get JSON data
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        # Validate required fields
        required_fields = ['session_id', 'encrypted_data', 'timestamp']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        session_id = data['session_id']
        encrypted_data = data['encrypted_data']
        
        # Validate data size
        if len(encrypted_data) > current_app.config['MAX_CONTENT_LENGTH']:
            return jsonify({
                'success': False,
                'error': 'Data too large'
            }), 413
        
        # Create migration record
        migration = Migration(
            user_id=current_user.id,
            status='pending'
        )
        db.session.add(migration)
        db.session.commit()
        
        # Save encrypted data to file
        upload_dir = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)
        
        encrypted_file_path = os.path.join(
            upload_dir,
            f"{migration.migration_id}.enc"
        )
        
        with open(encrypted_file_path, 'w') as f:
            f.write(encrypted_data)
        
        # Update migration record
        migration.encrypted_file_path = encrypted_file_path
        migration.scheduled_deletion_at = datetime.utcnow() + timedelta(
            hours=current_app.config['DATA_RETENTION_HOURS']
        )
        db.session.commit()
        
        # Queue background job to process migration
        process_migration.delay(migration.id)
        
        # Log upload
        current_app.logger.info(
            f"Upload received: migration_id={migration.migration_id}, "
            f"user_id={current_user.id}, size={len(encrypted_data)}"
        )
        
        return jsonify({
            'success': True,
            'migration_id': migration.migration_id,
            'status': 'uploaded',
            'message': 'Data received successfully. Migration will begin shortly.',
            'estimated_time': '5-10 minutes'
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Upload error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Upload failed. Please try again.'
        }), 500