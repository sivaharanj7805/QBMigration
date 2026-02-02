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
from models.database import db
from models.migration import Migration
from utils.aws_manager import AWSMigrationManager
from extensions import limiter
import hashlib
import logging
import uuid
import base64
import re
import json
import threading
import time
from datetime import datetime, timezone
from io import BytesIO


def sanitize_input(value, max_length=255):
    """
    FIX #47: Comprehensive input validation for file uploads.
    Sanitize user input to prevent XSS, command injection, and S3 key poisoning.

    Uses whitelist approach - only allows safe characters:
    - Alphanumeric (a-z, A-Z, 0-9)
    - Spaces
    - Hyphens (-)
    - Underscores (_)
    - Periods (.)

    Blocks dangerous characters: {}[]()&|*$<>"'/\;`~!@#%^+=
    """
    if not value or not isinstance(value, str):
        return value

    # SECURITY: Whitelist only safe characters (prevent command injection, S3 key poisoning)
    # Allow: letters, numbers, spaces, hyphens, underscores, periods
    value = re.sub(r'[^a-zA-Z0-9\s\-_.]', '', value)

    # Collapse multiple spaces into one
    value = re.sub(r'\s+', ' ', value)

    # Remove leading/trailing dots and hyphens (prevent directory traversal)
    value = value.strip('. -')

    # Trim whitespace
    value = value.strip()

    # Limit length
    if max_length and len(value) > max_length:
        value = value[:max_length]

    # SECURITY FIX: Return None for empty results instead of constant string
    # This allows callers to detect and handle invalid input appropriately
    # Returning "sanitized_input" caused data corruption - multiple records with same name
    if not value:
        return None

    return value

# Initialize blueprint
upload_bp = Blueprint('upload', __name__, url_prefix='/api/upload')

# Initialize logger
logger = logging.getLogger(__name__)


# ============================================================================
# NEW: PUBLIC KEY ENDPOINT FOR v3.1 HYBRID ENCRYPTION
# ============================================================================

@upload_bp.route('/public-key', methods=['GET'])
@limiter.limit("30 per minute")  # SECURITY FIX: Rate limit public key endpoint
def get_public_key():
    """
    Get server's RSA public key for hybrid encryption (v3.1 feature)

    Rate limited to prevent key enumeration attacks and resource exhaustion.

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
    # SECURITY FIX: Sanitize all user inputs
    company_name = sanitize_input(data.get('company_name', ''), max_length=255)
    qb_file_name = sanitize_input(data.get('qb_file_name', 'quickbooks.qbw'), max_length=255)
    
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
            migration.set_error_message('Failed to upload file to secure storage')
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
        migration.set_error_message(f'Upload error: {str(e)}')
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
    
    # SECURITY FIX: Get and sanitize company info
    company_name = sanitize_input(company_info.get('company_name', 'Unknown Company'), max_length=255)
    qb_file_name = sanitize_input(company_info.get('qb_file_name', 'quickbooks.qbw'), max_length=255)
    
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

    # SECURITY: Calculate SHA-256 hash for data integrity verification
    file_hash = hashlib.sha256(encrypted_data_bytes).hexdigest()

    # FIX #44: FORENSIC REQUIREMENT - MANDATORY hash verification (no backward compatibility)
    # Client must provide data_hash for integrity verification
    client_hash = encryption.get('data_hash', '').lower().strip()

    if not client_hash:
        logger.error(f"Client did not provide mandatory data_hash for verification (session_id: {session_id})")
        return jsonify({
            'success': False,
            'error': 'Data integrity hash (data_hash) is required for forensic-grade verification.',
            'error_code': 'HASH_REQUIRED'
        }), 400

    # Validate hash format (64 hex characters for SHA-256)
    if not re.match(r'^[a-f0-9]{64}$', client_hash):
        logger.error(f"Invalid hash format provided: {client_hash[:16]}...")
        return jsonify({
            'success': False,
            'error': 'Invalid SHA-256 hash format. Expected 64 hexadecimal characters.',
            'error_code': 'INVALID_HASH_FORMAT'
        }), 400

    # Verify client hash matches server calculation
    if client_hash != file_hash:
        logger.error(f"Hash mismatch! Client: {client_hash[:16]}... Server: {file_hash[:16]}...")
        return jsonify({
            'success': False,
            'error': 'Data integrity verification failed. Upload may be corrupted or tampered.',
            'error_code': 'HASH_MISMATCH'
        }), 400

    logger.info(f"Hash verification passed: {file_hash[:16]}...")

    # Check file size
    max_size_mb = current_app.config.get('MAX_UPLOAD_SIZE_MB', 100)
    max_size_bytes = max_size_mb * 1024 * 1024

    if data_size_bytes > max_size_bytes:
        return jsonify({
            'success': False,
            'error': f'File too large. Maximum size is {max_size_mb}MB.'
        }), 413
    
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
            migration.set_error_message('Failed to upload to secure storage')
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
        migration.set_error_message(f'Upload error: {str(e)}')
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
        
        # SECURITY FIX: Get and sanitize company name
        company_name = sanitize_input(company_info.get('company_name', 'Unknown Company'), max_length=255)
        
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
            migration.set_error_message(f'Bundle upload error: {str(e)}')
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
# CHUNKED UPLOAD ENDPOINTS (v4.3)
# ============================================================================

# In-memory storage for chunked upload sessions.
# In production, consider Redis or database for persistence across restarts.
_chunked_uploads = {}
_chunked_uploads_lock = threading.Lock()
CHUNKED_UPLOAD_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours


@upload_bp.route('/initiate', methods=['POST'])
@limiter.limit("10 per minute")
@login_required
def initiate_chunked_upload():
    """
    Initiate a chunked upload session.

    Request JSON:
        {
            "session_id": "guid",
            "total_chunks": 10,
            "key_id": "key-uuid",
            "algorithm": "AES-256-GCM",
            "encrypted_hash": "sha256-of-encrypted-file"
        }

    Returns:
        200: {upload_id, expires_at}
        400: Invalid input
        401: Unauthorized
    """
    if not current_user or not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        session_id = data.get('session_id', '')
        total_chunks = data.get('total_chunks', 0)
        key_id = data.get('key_id', '')
        algorithm = data.get('algorithm', '')
        encrypted_hash = data.get('encrypted_hash', '')

        if not session_id or not total_chunks or total_chunks < 1:
            return jsonify({
                'success': False,
                'error': 'session_id and total_chunks (>= 1) are required'
            }), 400

        upload_id = str(uuid.uuid4())
        now = time.time()
        expires_at = now + CHUNKED_UPLOAD_EXPIRY_SECONDS
        expires_at_iso = datetime.utcfromtimestamp(expires_at).isoformat() + 'Z'

        session_data = {
            'upload_id': upload_id,
            'session_id': session_id,
            'user_id': current_user.id,
            'total_chunks': total_chunks,
            'key_id': key_id,
            'algorithm': algorithm,
            'encrypted_hash': encrypted_hash,
            'chunks': {},
            'created_at': now,
            'expires_at': expires_at,
        }

        with _chunked_uploads_lock:
            _chunked_uploads[upload_id] = session_data

        logger.info(f"Chunked upload initiated: {upload_id}, {total_chunks} chunks, session: {session_id}")

        return jsonify({
            'success': True,
            'upload_id': upload_id,
            'expires_at': expires_at_iso
        }), 200

    except Exception as e:
        logger.error(f"Initiate chunked upload error: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to initiate upload'}), 500


@upload_bp.route('/chunk', methods=['POST'])
@limiter.limit("120 per minute")
@login_required
def upload_chunk():
    """
    Upload a single chunk of a chunked upload.

    Multipart form data:
        - chunk: binary file data
        - upload_id: string
        - chunk_index: int
        - total_chunks: int
        - chunk_hash: base64-encoded SHA-256 hash

    Returns:
        200: {received_hash, stored}
        400: Invalid input / hash mismatch
        401: Unauthorized
        404: Upload session not found
        410: Upload session expired
    """
    if not current_user or not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        upload_id = request.form.get('upload_id', '')
        chunk_index_str = request.form.get('chunk_index', '')
        total_chunks_str = request.form.get('total_chunks', '')
        chunk_hash = request.form.get('chunk_hash', '')

        if not upload_id or chunk_index_str == '' or not total_chunks_str:
            return jsonify({
                'success': False,
                'error': 'upload_id, chunk_index, and total_chunks are required'
            }), 400

        chunk_index = int(chunk_index_str)
        total_chunks = int(total_chunks_str)

        # Validate upload session
        with _chunked_uploads_lock:
            session_data = _chunked_uploads.get(upload_id)

        if not session_data:
            return jsonify({'success': False, 'error': 'Upload session not found'}), 404

        if session_data['user_id'] != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401

        if time.time() > session_data['expires_at']:
            with _chunked_uploads_lock:
                _chunked_uploads.pop(upload_id, None)
            return jsonify({'success': False, 'error': 'Upload session expired'}), 410

        # Get chunk file data
        chunk_file = request.files.get('chunk')
        if not chunk_file:
            return jsonify({'success': False, 'error': 'No chunk data provided'}), 400

        chunk_data = chunk_file.read()

        # Verify chunk hash (base64-encoded SHA-256)
        computed_hash = base64.b64encode(hashlib.sha256(chunk_data).digest()).decode('utf-8')
        if chunk_hash and computed_hash != chunk_hash:
            logger.warning(f"Chunk {chunk_index} hash mismatch for upload {upload_id}")
            return jsonify({
                'success': False,
                'error': f'Chunk hash mismatch: expected {chunk_hash}, got {computed_hash}'
            }), 400

        # Store chunk in S3
        aws = AWSMigrationManager()

        result = aws.upload_to_s3(
            file_obj=BytesIO(chunk_data),
            migration_id=upload_id,
            file_name=f"chunk_{chunk_index:06d}.bin",
            metadata={
                'upload_id': upload_id,
                'chunk_index': str(chunk_index),
                'chunk_hash': computed_hash
            }
        )

        if not result:
            return jsonify({'success': False, 'error': 'Failed to store chunk'}), 500

        # Track chunk in session
        with _chunked_uploads_lock:
            if upload_id in _chunked_uploads:
                _chunked_uploads[upload_id]['chunks'][chunk_index] = {
                    'hash': computed_hash,
                    's3_key': result.get('key', ''),
                    'size': len(chunk_data)
                }

        logger.debug(f"Chunk {chunk_index}/{total_chunks} stored for upload {upload_id}")

        return jsonify({
            'success': True,
            'received_hash': computed_hash,
            'stored': True
        }), 200

    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid chunk_index or total_chunks'}), 400
    except Exception as e:
        logger.error(f"Upload chunk error: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to upload chunk'}), 500


@upload_bp.route('/chunk/exists', methods=['GET'])
@limiter.limit("120 per minute")
@login_required
def chunk_exists():
    """
    Check if a chunk has already been uploaded (for resume support).

    Query params:
        - uploadId: string
        - chunkIndex: int

    Returns:
        200: {exists, chunk_hash}
    """
    if not current_user or not current_user.is_authenticated:
        return jsonify({'exists': False, 'chunk_hash': None}), 200

    try:
        upload_id = request.args.get('uploadId', '')
        chunk_index_str = request.args.get('chunkIndex', '')

        if not upload_id or chunk_index_str == '':
            return jsonify({'exists': False, 'chunk_hash': None}), 200

        chunk_index = int(chunk_index_str)

        with _chunked_uploads_lock:
            session_data = _chunked_uploads.get(upload_id)

        if not session_data:
            return jsonify({'exists': False, 'chunk_hash': None}), 200

        if session_data['user_id'] != current_user.id:
            return jsonify({'exists': False, 'chunk_hash': None}), 200

        chunk_info = session_data['chunks'].get(chunk_index)

        if chunk_info:
            return jsonify({
                'exists': True,
                'chunk_hash': chunk_info['hash']
            }), 200
        else:
            return jsonify({
                'exists': False,
                'chunk_hash': None
            }), 200

    except (ValueError, Exception) as e:
        logger.error(f"Chunk exists check error: {str(e)}")
        return jsonify({'exists': False, 'chunk_hash': None}), 200


@upload_bp.route('/commit', methods=['POST'])
@limiter.limit("10 per minute")
@login_required
def commit_chunked_upload():
    """
    Commit a chunked upload - finalizes the upload and creates migration record.

    Request JSON:
        {
            "upload_id": "guid",
            "session_id": "guid",
            "key_id": "key-uuid",
            "encryption_metadata": {
                "algorithm": "AES-256-GCM",
                "data_hash_sha256": "...",
                "encrypted_hash_sha256": "...",
                "chunk_size": 1048576,
                "total_chunks": 10,
                "plaintext_size_bytes": 10000000,
                "encrypted_size_bytes": 10000128
            },
            "metadata": {
                "schema_version": "4.3",
                "extraction_version": "4.3.0",
                "is_incremental": false,
                "incremental_from_date": null,
                "qb_version": "Enterprise 23.0",
                "extracted_at": "2024-01-01T00:00:00Z"
            }
        }

    Returns:
        200: Success with migration_id
        400: Invalid input / missing chunks
        401: Unauthorized
        404: Upload session not found
        410: Upload session expired
    """
    if not current_user or not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        upload_id = data.get('upload_id', '')
        session_id = data.get('session_id', '')
        key_id = data.get('key_id', '')
        encryption_metadata = data.get('encryption_metadata', {})
        metadata = data.get('metadata', {})

        if not upload_id:
            return jsonify({'success': False, 'error': 'upload_id is required'}), 400

        # Validate upload session
        with _chunked_uploads_lock:
            session_data = _chunked_uploads.get(upload_id)

        if not session_data:
            return jsonify({'success': False, 'error': 'Upload session not found'}), 404

        if session_data['user_id'] != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401

        if time.time() > session_data['expires_at']:
            with _chunked_uploads_lock:
                _chunked_uploads.pop(upload_id, None)
            return jsonify({'success': False, 'error': 'Upload session expired'}), 410

        # Verify all chunks are present
        total_chunks = session_data['total_chunks']
        received_chunks = session_data['chunks']

        missing_chunks = [i for i in range(total_chunks) if i not in received_chunks]

        if missing_chunks:
            return jsonify({
                'success': False,
                'error': f'Missing {len(missing_chunks)} chunks',
                'missing_chunks': missing_chunks[:20]
            }), 400

        # Calculate total size from chunks
        total_size = sum(c.get('size', 0) for c in received_chunks.values())

        # Generate migration ID
        migration_id = str(uuid.uuid4())

        # Use encrypted hash from session or encryption_metadata
        file_hash = encryption_metadata.get('encrypted_hash_sha256', session_data.get('encrypted_hash', ''))

        logger.info(f"Committing chunked upload {upload_id}: {total_chunks} chunks, "
                    f"{total_size:,} bytes, session: {session_id}")

        # Create migration record
        migration = Migration(
            migration_id=migration_id,
            user_id=current_user.id,
            company_name=sanitize_input(metadata.get('company_name', 'Chunked Upload'), max_length=255),
            qb_file_name=sanitize_input(metadata.get('qb_file_name', 'chunked_upload.enc'), max_length=255),
            file_hash=file_hash,
            data_size_bytes=total_size,
            status='uploaded'
        )

        db.session.add(migration)

        # Store commit manifest and encryption metadata in S3
        try:
            aws = AWSMigrationManager()

            commit_manifest = {
                'upload_id': upload_id,
                'session_id': session_id,
                'key_id': key_id,
                'encryption_metadata': encryption_metadata,
                'extraction_metadata': metadata,
                'chunks': {
                    str(k): {
                        'hash': v['hash'],
                        's3_key': v['s3_key'],
                        'size': v.get('size', 0)
                    }
                    for k, v in received_chunks.items()
                },
                'total_size_bytes': total_size,
                'committed_at': datetime.now(timezone.utc).isoformat() + 'Z'
            }

            # Store commit manifest
            aws.upload_to_s3(
                file_obj=BytesIO(json.dumps(commit_manifest, indent=2).encode('utf-8')),
                migration_id=migration_id,
                file_name='commit_manifest.json',
                metadata={
                    'upload_id': upload_id,
                    'migration_id': migration_id,
                    'type': 'commit_manifest'
                }
            )

            # Store encryption metadata separately
            aws.store_encryption_metadata(migration_id, {
                'key_id': key_id,
                'algorithm': encryption_metadata.get('algorithm', ''),
                'data_hash_sha256': encryption_metadata.get('data_hash_sha256', ''),
                'encrypted_hash_sha256': encryption_metadata.get('encrypted_hash_sha256', ''),
                'chunk_size': encryption_metadata.get('chunk_size', 0),
                'total_chunks': total_chunks
            })

        except Exception as e:
            logger.error(f"Failed to store commit metadata for {upload_id}: {str(e)}")
            # Continue - chunks are already stored in S3

        db.session.commit()

        # Clean up in-memory session
        with _chunked_uploads_lock:
            _chunked_uploads.pop(upload_id, None)

        logger.info(f"Chunked upload committed: {upload_id} -> migration {migration_id}")

        return jsonify({
            'success': True,
            'migration_id': migration_id,
            'status': 'uploaded',
            'total_chunks': total_chunks,
            'total_size_bytes': total_size,
            'message': 'Chunked upload committed successfully'
        }), 200

    except Exception as e:
        logger.error(f"Commit chunked upload error: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to commit upload'}), 500


@upload_bp.route('/abort', methods=['POST'])
@limiter.limit("10 per minute")
@login_required
def abort_chunked_upload():
    """
    Abort a chunked upload session and clean up stored chunks.

    Request JSON:
        {
            "upload_id": "guid",
            "reason": "client_error"
        }

    Returns:
        200: Success
        400: Invalid input
        401: Unauthorized
    """
    if not current_user or not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        upload_id = data.get('upload_id', '')
        reason = data.get('reason', 'unknown')

        if not upload_id:
            return jsonify({'success': False, 'error': 'upload_id is required'}), 400

        with _chunked_uploads_lock:
            session_data = _chunked_uploads.pop(upload_id, None)

        if session_data:
            if session_data['user_id'] != current_user.id:
                # Put it back - not authorized to abort this session
                with _chunked_uploads_lock:
                    _chunked_uploads[upload_id] = session_data
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401

            chunks_count = len(session_data['chunks'])
            logger.info(f"Chunked upload aborted: {upload_id}, reason: {reason}, "
                        f"chunks uploaded: {chunks_count}/{session_data['total_chunks']}")

            # Best-effort cleanup of stored chunks from S3
            try:
                aws = AWSMigrationManager()
                for chunk_info in session_data['chunks'].values():
                    s3_key = chunk_info.get('s3_key')
                    if s3_key:
                        try:
                            aws.delete_from_s3(s3_key)
                        except Exception:
                            pass  # Best effort
            except Exception as e:
                logger.warning(f"Cleanup failed for aborted upload {upload_id}: {str(e)}")
        else:
            logger.info(f"Abort request for unknown/already-cleaned upload: {upload_id}")

        return jsonify({
            'success': True,
            'message': 'Upload aborted'
        }), 200

    except Exception as e:
        logger.error(f"Abort chunked upload error: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to abort upload'}), 500


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