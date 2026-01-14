"""
File Upload API Endpoints
- Encrypted file upload
- File validation
- S3 integration
- Duplicate detection
- v3.1 QB Extractor compatibility (NEW)
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
import base64
from datetime import datetime
from io import BytesIO

# Initialize blueprint
upload_bp = Blueprint('upload', __name__, url_prefix='/api/upload')

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


# ============================================================================
# NEW: PUBLIC KEY ENDPOINT FOR v3.1 HYBRID ENCRYPTION
# ============================================================================

@upload_bp.route('/public-key', methods=['GET'])
def get_public_key():
    """
    Get server's RSA public key for hybrid encryption (v3.1 feature)
    
    Returns:
        200: Public key in XML format
        500: Key generation failed
    """
    try:
        from utils.encryption import get_encryption_manager
        
        rsa = get_encryption_manager()
        public_key_xml = rsa.get_public_key_xml()
        
        return jsonify({
            'success': True,
            'public_key': public_key_xml,
            'key_format': 'XML',
            'key_size_bits': 4096,
            'algorithm': 'RSA-4096'
        }), 200
        
    except Exception as e:
        logger.error(f"Public key retrieval error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Could not retrieve public key'
        }), 500


# ============================================================================
# ORIGINAL UPLOAD ENDPOINT - NOW SUPPORTS BOTH OLD AND v3.1 FORMATS
# ============================================================================

@upload_bp.route('', methods=['POST'])
@limiter.limit("10 per minute")
@login_required  # Use decorator instead of manual check
def upload_file():
    """
    Upload encrypted QuickBooks Desktop file
    
    SUPPORTS TWO FORMATS:
    
    1. ORIGINAL FORMAT (backward compatible):
        {
            "encrypted_data": "IV:...:CIPHER:...:KEY:...",
            "company_name": "Company Inc",
            "qb_file_name": "company.qbw"
        }
    
    2. v3.1 FORMAT (new):
        {
            "session_id": "guid",
            "encryption": {
                "encrypted_data": "base64...",
                "key": "base64..." OR null,
                "encrypted_key": "base64..." OR null,
                "is_key_encrypted": true/false,
                "iv": "base64...",
                "tag": "base64...",
                "algorithm": "AES-256-GCM + RSA-4096",
                "version": "3.1"
            },
            "metadata": {...},
            "company_info": {...}
        }
    
    Returns:
        200: Upload successful
        400: Invalid input
        401: Unauthorized
        413: File too large
        500: Server error
    """
    # CRITICAL FIX: Check authentication FIRST
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
        
        # DETECT FORMAT: v3.1 or original
        is_v31_format = 'encryption' in data and isinstance(data.get('encryption'), dict)
        
        if is_v31_format:
            # NEW v3.1 FORMAT
            return _handle_v31_upload(data, current_user)
        else:
            # ORIGINAL FORMAT (unchanged)
            return _handle_original_upload(data, current_user)
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred during upload'
        }), 500


def _handle_original_upload(data, user):
    """
    Handle original format upload (UNCHANGED from your original code)
    """
    encrypted_data = data.get('encrypted_data', '')
    company_name = data.get('company_name', '')
    qb_file_name = data.get('qb_file_name', 'quickbooks.qbw')
    
    # Validate encrypted data presence
    if not encrypted_data:
        logger.warning(f"Invalid encrypted data from user {user.id}: Encrypted data is required")
        return jsonify({
            'success': False,
            'error': 'Encrypted data is required'
        }), 400
    
    # CRITICAL FIX: Check format BEFORE length
    allowed_prefixes = current_app.config['ALLOWED_ENCRYPTION_PREFIXES']
    has_valid_prefix = any(encrypted_data.startswith(prefix) for prefix in allowed_prefixes)
    
    if not has_valid_prefix:
        logger.warning(f"Invalid encrypted data from user {user.id}: Invalid encryption format")
        return jsonify({
            'success': False,
            'error': 'Invalid encryption format. Data must be properly encrypted.'
        }), 400
    
    # Check minimum length
    min_length = current_app.config['MIN_ENCRYPTED_DATA_LENGTH']
    if len(encrypted_data) < min_length:
        logger.warning(f"Invalid encrypted data from user {user.id}: Encrypted data too short (minimum {min_length} characters)")
        return jsonify({
            'success': False,
            'error': f'Encrypted data too short (minimum {min_length} characters)'
        }), 400
    
    # CRITICAL FIX: Check maximum length
    max_length = current_app.config['MAX_ENCRYPTED_DATA_LENGTH']
    if len(encrypted_data) > max_length:
        logger.warning(f"Invalid encrypted data from user {user.id}: Encrypted data too large")
        return jsonify({
            'success': False,
            'error': 'File too large. Maximum size is 50MB.'
        }), 413
    
    # Calculate file hash
    file_hash = hashlib.sha256(encrypted_data.encode()).hexdigest()
    data_size_bytes = len(encrypted_data)
    
    # Check for duplicate
    duplicate = Migration.query.filter_by(
        user_id=user.id,
        file_hash=file_hash,
        status='uploaded'
    ).first()
    
    if duplicate:
        logger.info(f"Duplicate file detected for user {user.id}, hash: {file_hash[:16]}...")
        return jsonify({
            'success': True,
            'message': 'File already uploaded',
            'migration_id': duplicate.migration_id,
            'is_duplicate': True
        }), 200
    
    # Generate migration ID
    migration_id = str(uuid.uuid4())
    
    logger.info(f"Upload request from user {user.id}, size: {data_size_bytes} bytes, hash: {file_hash[:16]}...")
    
    # Create migration record
    migration = Migration(
        migration_id=migration_id,
        user_id=user.id,
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
        
        aws = AWSMigrationManager()
        
        # Upload encrypted data
        file_obj = BytesIO(encrypted_data.encode())
        
        result = aws.upload_to_s3(
            file_obj=file_obj,
            migration_id=migration_id,
            metadata={
                'user_id': str(user.id),
                'migration_id': migration_id,
                'company_name': company_name,
                'file_hash': file_hash
            }
        )

        if not result:
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
        migration.s3_uri = result['uri']
        migration.s3_bucket = result['bucket']
        migration.s3_key = result['key']
        db.session.commit()
        
        logger.info(f"Upload successful for migration {migration_id}")
        
        return jsonify({
            'success': True,
            'migration_id': migration_id,
            'message': 'File uploaded successfully'
        }), 201
        
    except Exception as e:
        logger.error(f"S3 upload error for migration {migration_id}: {str(e)}")
        migration.status = 'failed'
        migration.error_message = f'Upload error: {str(e)}'
        db.session.commit()
        
        return jsonify({
            'success': False,
            'error': 'Failed to upload file to secure storage'
        }), 500


def _handle_v31_upload(data, user):
    """
    Handle v3.1 format upload (NEW)
    """
    session_id = data.get('session_id', str(uuid.uuid4()))
    encryption = data.get('encryption', {})
    metadata = data.get('metadata', {})
    company_info = data.get('company_info', {})
    
    # Extract encryption fields
    encrypted_data = encryption.get('encrypted_data', '')
    aes_key = encryption.get('key')
    encrypted_aes_key = encryption.get('encrypted_key')
    is_key_encrypted = encryption.get('is_key_encrypted', False)
    iv = encryption.get('iv', '')
    tag = encryption.get('tag', '')
    algorithm = encryption.get('algorithm', 'AES-256-GCM')
    
    # Validate required fields
    if not encrypted_data:
        return jsonify({
            'success': False,
            'error': 'Encrypted data is required'
        }), 400
    
    if not iv or not tag:
        return jsonify({
            'success': False,
            'error': 'IV and authentication tag are required'
        }), 400
    
    # Validate we have either plaintext key OR encrypted key
    if not aes_key and not encrypted_aes_key:
        return jsonify({
            'success': False,
            'error': 'AES key (encrypted or plaintext) is required'
        }), 400
    
    # Get company info
    company_name = company_info.get('company_name', 'Unknown Company')
    qb_file_name = company_info.get('qb_file_name', 'quickbooks.qbw')
    
    # Decode to check size
    try:
        encrypted_data_bytes = base64.b64decode(encrypted_data)
        data_size_bytes = len(encrypted_data_bytes)
    except Exception as e:
        logger.error(f"Base64 decode error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Invalid base64 encoding in encrypted data'
        }), 400
    
    # Check file size
    max_size_mb = current_app.config.get('MAX_UPLOAD_SIZE_MB', 100)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if data_size_bytes > max_size_bytes:
        return jsonify({
            'success': False,
            'error': f'File too large. Maximum size is {max_size_mb}MB.'
        }), 413
    
    # Calculate hash for duplicate detection
    file_hash = hashlib.sha256(encrypted_data_bytes).hexdigest()
    
    # Check for duplicate
    duplicate = Migration.query.filter_by(
        user_id=user.id,
        file_hash=file_hash,
        status='uploaded'
    ).first()
    
    if duplicate:
        logger.info(f"Duplicate file detected for user {user.id}, hash: {file_hash[:16]}...")
        return jsonify({
            'success': True,
            'message': 'File already uploaded',
            'migration_id': duplicate.migration_id,
            'status': duplicate.status,
            'is_duplicate': True
        }), 200
    
    # Generate migration ID
    migration_id = str(uuid.uuid4())
    
    logger.info(f"v3.1 Upload from user {user.id}: {data_size_bytes:,} bytes, session: {session_id}")
    
    # Create migration record
    migration = Migration(
        migration_id=migration_id,
        user_id=user.id,
        company_name=company_name,
        qb_file_name=qb_file_name,
        file_hash=file_hash,
        data_size_bytes=data_size_bytes,
        status='pending'
    )
    
    db.session.add(migration)
    db.session.commit()
    
    # Prepare encryption metadata for storage
    encryption_metadata = {
        'iv': iv,
        'tag': tag,
        'algorithm': algorithm,
        'version': encryption.get('version', '3.1'),
        'is_key_encrypted': is_key_encrypted
    }
    
    # Store the AES key (encrypted or plaintext depending on client)
    if is_key_encrypted and encrypted_aes_key:
        encryption_metadata['encrypted_aes_key'] = encrypted_aes_key
        logger.info(f"Migration {migration_id}: Using RSA-encrypted AES key")
    elif aes_key:
        encryption_metadata['aes_key'] = aes_key
        logger.info(f"Migration {migration_id}: Using TLS-protected AES key")
    
    # Upload to S3
    try:
        logger.info(f"Uploading migration {migration_id} to S3...")
        
        aws = AWSMigrationManager()
        
        # Create file object from encrypted data
        file_obj = BytesIO(encrypted_data_bytes)
        
        # Upload encrypted data to S3
        result = aws.upload_to_s3(
            file_obj=file_obj,
            migration_id=migration_id,
            metadata={
                'user_id': str(user.id),
                'migration_id': migration_id,
                'company_name': company_name,
                'file_hash': file_hash,
                'session_id': session_id,
                'client_version': metadata.get('client_version', '3.1.0'),
                'data_version': metadata.get('data_version', 'qb_desktop_3.1')
            }
        )
        
        if not result:
            logger.error(f"S3 upload failed for migration {migration_id}")
            migration.status = 'failed'
            migration.error_message = 'Failed to upload to secure storage'
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': 'Failed to upload to secure storage'
            }), 500
        
        # Store encryption metadata separately (NEW - v3.1 feature)
        aws.store_encryption_metadata(migration_id, encryption_metadata)
        
        # Update migration status
        migration.status = 'uploaded'
        migration.s3_uri = result['uri']
        migration.s3_bucket = result['bucket']
        migration.s3_key = result['key']
        db.session.commit()
        
        logger.info(f"✓ Upload successful: {migration_id}")
        
        return jsonify({
            'success': True,
            'migration_id': migration_id,
            'status': 'uploaded_to_s3',
            'message': 'File uploaded successfully',
            's3_location': f"s3://{result['bucket']}/{result['key']}"
        }), 201
        
    except Exception as e:
        logger.error(f"S3 upload error for migration {migration_id}: {str(e)}")
        migration.status = 'failed'
        migration.error_message = f'Upload error: {str(e)}'
        db.session.commit()
        
        return jsonify({
            'success': False,
            'error': 'Failed to upload to secure storage'
        }), 500


# ============================================================================
# NEW: NDJSON BUNDLE UPLOAD ENDPOINT (v4.3)
# ============================================================================

@upload_bp.route('/ndjson-bundle', methods=['POST'])
@limiter.limit("10 per minute")
@login_required
def upload_ndjson_bundle():
    """
    Upload NDJSON bundle (multiple files from NDJSONWriter)
    
    Format:
        {
            "session_id": "guid",
            "format": "ndjson_bundle",
            "version": "4.3",
            "total_records": 1000,
            "total_entities": 55,
            "company_fingerprint": "sha256...",
            "files": [
                {
                    "file_name": "customers.ndjson",
                    "entity_type": "Customer",
                    "record_count": 100,
                    "content_base64": "...",
                    "sha256": "..."
                },
                ...
            ],
            "company_info": {...}
        }
    
    Returns:
        201: Bundle uploaded successfully
        400: Invalid input
        401: Unauthorized
        500: Server error
    """
    if not current_user or not current_user.is_authenticated:
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        session_id = data.get('session_id', str(uuid.uuid4()))
        files = data.get('files', [])
        company_info = data.get('company_info', {})
        total_records = data.get('total_records', 0)
        company_fingerprint = data.get('company_fingerprint', '')
        
        if not files:
            return jsonify({
                'success': False,
                'error': 'No files in bundle'
            }), 400
        
        # Calculate total size
        total_size = 0
        for file_entry in files:
            content_b64 = file_entry.get('content_base64', '')
            if content_b64:
                total_size += len(base64.b64decode(content_b64))
        
        # Generate migration ID
        migration_id = str(uuid.uuid4())
        
        logger.info(f"NDJSON bundle upload: {len(files)} files, {total_records} records, "
                   f"{total_size:,} bytes, session: {session_id}")
        
        # Get company name
        company_name = company_info.get('company_name', 'Unknown Company')
        
        # Create migration record
        migration = Migration(
            migration_id=migration_id,
            user_id=current_user.id,
            company_name=company_name,
            qb_file_name=company_info.get('qb_file_name', 'ndjson_bundle'),
            file_hash=company_fingerprint,
            data_size_bytes=total_size,
            status='pending'
        )
        
        db.session.add(migration)
        db.session.commit()
        
        # Store bundle in S3
        try:
            aws = AWSMigrationManager()
            
            # Store each file with entity prefix
            stored_files = []
            for file_entry in files:
                file_name = file_entry.get('file_name', 'unknown.ndjson')
                content_b64 = file_entry.get('content_base64', '')
                
                if content_b64:
                    content_bytes = base64.b64decode(content_b64)
                    s3_key = f"migrations/{migration_id}/{file_name}"
                    
                    # Upload to S3
                    result = aws.upload_to_s3(
                        file_obj=BytesIO(content_bytes),
                        migration_id=migration_id,
                        file_name=file_name,
                        metadata={
                            'entity_type': file_entry.get('entity_type', 'unknown'),
                            'record_count': str(file_entry.get('record_count', 0)),
                            'sha256': file_entry.get('sha256', '')
                        }
                    )
                    
                    if result:
                        stored_files.append({
                            'file_name': file_name,
                            's3_key': result.get('key'),
                            'record_count': file_entry.get('record_count', 0)
                        })
            
            # Update migration status
            migration.status = 'uploaded'
            migration.s3_uri = f"s3://{aws.bucket_name}/migrations/{migration_id}/"
            db.session.commit()
            
            logger.info(f"✓ NDJSON bundle uploaded: {migration_id}, {len(stored_files)} files")
            
            return jsonify({
                'success': True,
                'migration_id': migration_id,
                'status': 'uploaded_ndjson_bundle',
                'total_files': len(stored_files),
                'total_records': total_records,
                'message': 'NDJSON bundle uploaded successfully'
            }), 201
            
        except Exception as e:
            logger.error(f"S3 upload error for NDJSON bundle {migration_id}: {str(e)}")
            migration.status = 'failed'
            migration.error_message = f'Bundle upload error: {str(e)}'
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': 'Failed to upload bundle to secure storage'
            }), 500
        
    except Exception as e:
        logger.error(f"NDJSON bundle upload error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred during bundle upload'
        }), 500


# ============================================================================
# ORIGINAL STATUS ENDPOINT - UNCHANGED
# ============================================================================

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