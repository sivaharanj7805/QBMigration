"""
S3 Upload API with Pre-signed URLs
Enables direct uploads from C# client to S3
"""

from flask import Blueprint, request, jsonify
import boto3
from botocore.config import Config
from datetime import datetime
import hashlib
import os

from api.auth import require_auth
from models import db, Migration

s3_upload_bp = Blueprint('s3_upload', __name__, url_prefix='/api/upload')

# S3 client with retry config
s3_config = Config(
    retries={'max_attempts': 3, 'mode': 'adaptive'},
    signature_version='s3v4'
)


def get_s3_client():
    """Get configured S3 client"""
    return boto3.client(
        's3',
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        config=s3_config
    )


@s3_upload_bp.route('/presigned-url', methods=['POST'])
@require_auth
def get_presigned_url():
    """
    Get a pre-signed URL for direct S3 upload
    
    Request body:
    {
        "session_id": "FB-...",
        "file_name": "migration_data.ndjson.enc",
        "file_size": 12345678,
        "content_type": "application/octet-stream",
        "sha256_hash": "abc123..."
    }
    
    Response:
    {
        "upload_url": "https://s3.amazonaws.com/...",
        "upload_id": "...",
        "expires_in": 3600,
        "s3_key": "migrations/FB-.../data.enc"
    }
    """
    data = request.get_json()
    user_id = request.current_user['user_id']
    
    session_id = data.get('session_id')
    file_name = data.get('file_name', 'data.enc')
    file_size = data.get('file_size', 0)
    content_type = data.get('content_type', 'application/octet-stream')
    sha256_hash = data.get('sha256_hash')
    
    if not session_id:
        return jsonify({'error': 'session_id required'}), 400
    
    # Generate S3 key
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    s3_key = f"migrations/{session_id}/{timestamp}_{file_name}"
    
    bucket = os.getenv('AWS_S3_BUCKET', 'forensicbridge-migrations')
    
    try:
        s3 = get_s3_client()
        
        # Generate pre-signed URL for PUT
        presigned_url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket,
                'Key': s3_key,
                'ContentType': content_type,
            },
            ExpiresIn=3600,  # 1 hour
            HttpMethod='PUT'
        )
        
        # Create migration record
        migration = Migration(
            user_id=user_id,
            session_id=session_id,
            status='uploading',
            s3_bucket=bucket,
            s3_key=s3_key,
            data_size_bytes=file_size,
            file_hash=sha256_hash,
            ip_address=request.remote_addr
        )
        
        db.session.add(migration)
        db.session.commit()
        
        return jsonify({
            'upload_url': presigned_url,
            'migration_id': migration.migration_id,
            'expires_in': 3600,
            's3_key': s3_key,
            's3_bucket': bucket
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to generate upload URL: {str(e)}'}), 500


@s3_upload_bp.route('/complete', methods=['POST'])
@require_auth
def complete_upload():
    """
    Mark upload as complete and trigger processing
    
    Request body:
    {
        "migration_id": "...",
        "sha256_hash": "abc123...",
        "company_name": "Acme Corp"
    }
    """
    data = request.get_json()
    user_id = request.current_user['user_id']
    
    migration_id = data.get('migration_id')
    sha256_hash = data.get('sha256_hash')
    company_name = data.get('company_name')
    
    if not migration_id:
        return jsonify({'error': 'migration_id required'}), 400
    
    # Find migration
    migration = Migration.query.filter_by(
        migration_id=migration_id,
        user_id=user_id
    ).first()
    
    if not migration:
        return jsonify({'error': 'Migration not found'}), 404
    
    # Verify hash matches (prevents tampering)
    if sha256_hash and migration.file_hash and migration.file_hash != sha256_hash:
        migration.mark_as_failed('Hash mismatch - file may be corrupted', 'HASH_MISMATCH')
        return jsonify({'error': 'Hash mismatch'}), 400
    
    # Update migration
    migration.company_name = company_name
    migration.mark_as_uploaded(
        s3_uri=f"s3://{migration.s3_bucket}/{migration.s3_key}",
        s3_bucket=migration.s3_bucket,
        s3_key=migration.s3_key
    )
    
    # Trigger processing (via Celery)
    try:
        from workers.migration_worker import process_migration
        process_migration.delay(migration_id)
    except ImportError:
        pass  # Celery not configured
    
    return jsonify({
        'success': True,
        'migration_id': migration_id,
        'status': 'uploaded',
        'message': 'Upload complete. Processing will begin shortly.'
    })


@s3_upload_bp.route('/multipart/init', methods=['POST'])
@require_auth
def init_multipart_upload():
    """
    Initialize multipart upload for large files (>100MB)
    """
    data = request.get_json()
    user_id = request.current_user['user_id']
    
    session_id = data.get('session_id')
    file_name = data.get('file_name', 'data.enc')
    file_size = data.get('file_size', 0)
    
    if not session_id:
        return jsonify({'error': 'session_id required'}), 400
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    s3_key = f"migrations/{session_id}/{timestamp}_{file_name}"
    bucket = os.getenv('AWS_S3_BUCKET', 'forensicbridge-migrations')
    
    try:
        s3 = get_s3_client()
        
        # Create multipart upload
        response = s3.create_multipart_upload(
            Bucket=bucket,
            Key=s3_key,
            ContentType='application/octet-stream'
        )
        
        upload_id = response['UploadId']
        
        # Create migration record
        migration = Migration(
            user_id=user_id,
            session_id=session_id,
            status='uploading',
            s3_bucket=bucket,
            s3_key=s3_key,
            data_size_bytes=file_size,
            ip_address=request.remote_addr
        )
        
        db.session.add(migration)
        db.session.commit()
        
        return jsonify({
            'upload_id': upload_id,
            'migration_id': migration.migration_id,
            's3_key': s3_key,
            's3_bucket': bucket
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@s3_upload_bp.route('/multipart/part-url', methods=['POST'])
@require_auth
def get_part_upload_url():
    """
    Get pre-signed URL for a multipart upload part
    """
    data = request.get_json()
    
    upload_id = data.get('upload_id')
    part_number = data.get('part_number')
    s3_key = data.get('s3_key')
    
    bucket = os.getenv('AWS_S3_BUCKET', 'forensicbridge-migrations')
    
    try:
        s3 = get_s3_client()
        
        presigned_url = s3.generate_presigned_url(
            'upload_part',
            Params={
                'Bucket': bucket,
                'Key': s3_key,
                'UploadId': upload_id,
                'PartNumber': part_number
            },
            ExpiresIn=3600
        )
        
        return jsonify({
            'upload_url': presigned_url,
            'part_number': part_number,
            'expires_in': 3600
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@s3_upload_bp.route('/multipart/complete', methods=['POST'])
@require_auth
def complete_multipart_upload():
    """
    Complete multipart upload
    """
    data = request.get_json()
    
    upload_id = data.get('upload_id')
    s3_key = data.get('s3_key')
    parts = data.get('parts', [])  # [{"PartNumber": 1, "ETag": "..."}]
    migration_id = data.get('migration_id')
    
    bucket = os.getenv('AWS_S3_BUCKET', 'forensicbridge-migrations')
    
    try:
        s3 = get_s3_client()
        
        # Complete the multipart upload
        s3.complete_multipart_upload(
            Bucket=bucket,
            Key=s3_key,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts}
        )
        
        # Update migration status
        if migration_id:
            migration = Migration.query.filter_by(migration_id=migration_id).first()
            if migration:
                migration.mark_as_uploaded(
                    s3_uri=f"s3://{bucket}/{s3_key}",
                    s3_bucket=bucket,
                    s3_key=s3_key
                )
        
        return jsonify({
            'success': True,
            'message': 'Upload complete'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
