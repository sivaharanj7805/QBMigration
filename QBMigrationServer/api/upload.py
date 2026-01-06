"""
File Upload API Endpoints
- Encrypted file upload
- File validation
- S3 integration
- Duplicate detection
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models.database import db
from models.migration import Migration
from utils.aws_manager import AWSMigrationManager
import hashlib
import logging
import uuid
from datetime import datetime

# Initialize blueprint
upload_bp = Blueprint('upload', __name__, url_prefix='/api/upload')

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


@upload_bp.route('', methods=['POST'])
@limiter.limit("10 per minute")
@login_required  # Use decorator instead of manual check
def upload_file():
    """Upload encrypted QuickBooks Desktop file"""
    """
    Upload encrypted QuickBooks Desktop file
    
    Request JSON:
        {
            "encrypted_data": "IV:...:CIPHER:...:KEY:...",
            "company_name": "Company Inc",
            "qb_file_name": "company.qbw"
        }
    
    Returns:
        200: Upload successful
        400: Invalid input
        401: Unauthorized
        413: File too large
        500: Server error
    """
    # CRITICAL FIX: Check authentication FIRST
    from flask_login import current_user
    
    if not current_user or not current_user.is_authenticated:
        logger.warning(f"Unauthenticated upload attempt from {request.remote_addr}")
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        encrypted_data = data.get('encrypted_data', '')
        company_name = data.get('company_name', '')
        qb_file_name = data.get('qb_file_name', 'quickbooks.qbw')
        
        # Validate encrypted data presence
        if not encrypted_data:
            logger.warning(f"Invalid encrypted data from user {current_user.id}: Encrypted data is required")
            return jsonify({
                'success': False,
                'error': 'Encrypted data is required'
            }), 400
        
        # CRITICAL FIX: Check format BEFORE length
        allowed_prefixes = current_app.config['ALLOWED_ENCRYPTION_PREFIXES']
        has_valid_prefix = any(encrypted_data.startswith(prefix) for prefix in allowed_prefixes)
        
        if not has_valid_prefix:
            logger.warning(f"Invalid encrypted data from user {current_user.id}: Invalid encryption format")
            return jsonify({
                'success': False,
                'error': 'Invalid encryption format. Data must be properly encrypted.'
            }), 400
        
        # Check minimum length
        min_length = current_app.config['MIN_ENCRYPTED_DATA_LENGTH']
        if len(encrypted_data) < min_length:
            logger.warning(f"Invalid encrypted data from user {current_user.id}: Encrypted data too short (minimum {min_length} characters)")
            return jsonify({
                'success': False,
                'error': f'Encrypted data too short (minimum {min_length} characters)'
            }), 400
        
        # CRITICAL FIX: Check maximum length
        max_length = current_app.config['MAX_ENCRYPTED_DATA_LENGTH']
        if len(encrypted_data) > max_length:
            logger.warning(f"Invalid encrypted data from user {current_user.id}: Encrypted data too large")
            return jsonify({
                'success': False,
                'error': 'File too large. Maximum size is 50MB.'
            }), 413
        
        # Calculate file hash
        file_hash = hashlib.sha256(encrypted_data.encode()).hexdigest()
        data_size_bytes = len(encrypted_data)
        
        # Check for duplicate
        duplicate = Migration.query.filter_by(
            user_id=current_user.id,
            file_hash=file_hash,
            status='uploaded'
        ).first()
        
        if duplicate:
            logger.info(f"Duplicate file detected for user {current_user.id}, hash: {file_hash[:16]}...")
            return jsonify({
                'success': True,
                'message': 'File already uploaded',
                'migration_id': duplicate.migration_id,
                'is_duplicate': True
            }), 200
        
        # Generate migration ID
        migration_id = str(uuid.uuid4())
        
        logger.info(f"Upload request from user {current_user.id}, size: {data_size_bytes} bytes, hash: {file_hash[:16]}...")
        
        # Create migration record
        migration = Migration(
            migration_id=migration_id,
            user_id=current_user.id,
            company_name=company_name,
            qb_file_name=qb_file_name,
            file_hash=file_hash,
            data_size_bytes=data_size_bytes,
            status='pending'
        )
        
        db.session.add(migration)
        db.session.commit()
        
        # Upload to S3
        try:
            logger.info(f"Uploading migration {migration_id} to S3...")
            
            aws = AWSManager()
            s3_key = f"uploads/{current_user.id}/{migration_id}.enc"
            
            # Upload encrypted data
            from io import BytesIO
            file_obj = BytesIO(encrypted_data.encode())
            
            success = aws.upload_to_s3(
                file_obj=file_obj,
                key=s3_key,
                metadata={
                    'user_id': str(current_user.id),
                    'migration_id': migration_id,
                    'company_name': company_name,
                    'file_hash': file_hash
                }
            )
            
            if not success:
                logger.error(f"S3 upload failed for migration {migration_id}")
                migration.status = 'failed'
                migration.error_message = 'Failed to upload file to secure storage'
                db.session.commit()
                
                return jsonify({
                    'success': False,
                    'error': 'Failed to upload file to secure storage'
                }), 500
            
            # Update migration status
            migration.status = 'uploaded'
            migration.s3_key = s3_key
            db.session.commit()
            
            logger.info(f"Upload successful for migration {migration_id}")
            
            return jsonify({
                'success': True,
                'migration_id': migration_id,
                'message': 'File uploaded successfully'
            }), 200
            
        except Exception as e:
            logger.error(f"S3 upload error for migration {migration_id}: {str(e)}")
            migration.status = 'failed'
            migration.error_message = f'Upload error: {str(e)}'
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': 'Failed to upload file to secure storage'
            }), 500
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred during upload'
        }), 500


@upload_bp.route('/<migration_id>/status', methods=['GET'])
@login_required
def get_upload_status(migration_id):
    """
    Get upload status
    
    Args:
        migration_id: Migration ID
        
    Returns:
        200: Status information
        404: Migration not found
    """
    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=current_user.id
        ).first()
        
        if not migration:
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404
        
        return jsonify({
            'success': True,
            'migration': {
                'migration_id': migration.migration_id,
                'status': migration.status,
                'company_name': migration.company_name,
                'data_size_bytes': migration.data_size_bytes,
                'created_at': migration.created_at.isoformat() if migration.created_at else None,
                'updated_at': migration.updated_at.isoformat() if migration.updated_at else None
            }
        }), 200
        
    except Exception as e:
    # Check if it's an authentication error
        if 'not bound to a Session' in str(e) or 'DetachedInstanceError' in str(e):
            # This is a session issue, likely unauthenticated
            logger.warning(f"Unauthenticated upload attempt from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Authentication required'
            }), 401
        
        logger.error(f"Upload error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred during upload'
        }), 500