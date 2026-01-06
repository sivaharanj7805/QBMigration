from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models.database import db
from models.migration import Migration
from utils.aws_manager import AWSMigrationManager
import logging
import re
import io
import hashlib

upload_bp = Blueprint('upload', __name__)
logger = logging.getLogger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


def scan_for_malware(data):
    """
    Scan data for malware (placeholder - implement with ClamAV or VirusTotal)
    
    Args:
        data: Data to scan
        
    Returns:
        tuple: (is_safe, error_message)
    """
    if not current_app.config.get('ENABLE_VIRUS_SCANNING', False):
        return True, None
    
    try:
        # Option 1: Use ClamAV (if installed locally)
        # import pyclamd
        # cd = pyclamd.ClamdUnixSocket()
        # result = cd.scan_stream(data.encode() if isinstance(data, str) else data)
        # if result:
        #     return False, "Malware detected"
        
        # Option 2: Use VirusTotal API
        # import requests
        # vt_api_key = current_app.config.get('VIRUSTOTAL_API_KEY')
        # response = requests.post(
        #     'https://www.virustotal.com/api/v3/files',
        #     headers={'x-apikey': vt_api_key},
        #     files={'file': data}
        # )
        # Check response for malware
        
        # For now, basic pattern matching for obvious malware signatures
        suspicious_patterns = [
            b'<script',
            b'eval(',
            b'exec(',
            b'system(',
            b'passthru(',
            b'shell_exec(',
            b'<?php',
            b'<%',
            b'#!/bin/bash',
            b'#!/bin/sh'
        ]
        
        data_bytes = data.encode() if isinstance(data, str) else data
        
        for pattern in suspicious_patterns:
            if pattern in data_bytes:
                logger.warning(f"Suspicious pattern detected: {pattern}")
                return False, "File contains suspicious content"
        
        return True, None
        
    except Exception as e:
        logger.error(f"Malware scanning failed: {str(e)}")
        # Fail closed: reject file if scanning fails
        return False, "Malware scanning failed"


def validate_encrypted_data(encrypted_data):
    """
    Validate encrypted data format and content
    
    Args:
        encrypted_data: Encrypted data string
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not encrypted_data:
        return False, "Encrypted data is required"
    
    if len(encrypted_data.strip()) == 0:
        return False, "Encrypted data cannot be empty"
    
    if len(encrypted_data) < 100:
        return False, "Encrypted data too short (minimum 100 characters)"
    
    max_size = current_app.config.get('MAX_ENCRYPTED_DATA_LENGTH', 50 * 1024 * 1024)
    if len(encrypted_data) > max_size:
        return False, f"Encrypted data too large (max {max_size / 1024 / 1024:.0f}MB)"
    
    # Validate format
    valid_prefixes = current_app.config.get('ALLOWED_ENCRYPTION_PREFIXES', ['IV:', 'AES:', 'ENC:'])
    has_valid_prefix = any(encrypted_data.startswith(prefix) for prefix in valid_prefixes)
    
    if not has_valid_prefix:
        return False, "Invalid encrypted data format (missing encryption header)"
    
    # Check for key separator
    if ':KEY:' not in encrypted_data and ':' not in encrypted_data:
        return False, "Invalid encrypted data format (malformed structure)"
    
    # Validate it's not plaintext JSON
    if encrypted_data.strip().startswith('{') or encrypted_data.strip().startswith('['):
        return False, "Data appears to be unencrypted (plaintext JSON detected)"
    
    return True, None


@upload_bp.route('/api/upload', methods=['POST'])
@limiter.limit("20 per hour")
@login_required
def upload_encrypted_data():
    """
    Upload encrypted QuickBooks data to S3 (NOT local disk)
    
    Features:
    - Duplicate detection (via file hash)
    - Malware scanning
    - Cost estimation
    - S3 upload with encryption
    - Zero local storage
    
    Rate Limited: 20 requests per hour
    Max Size: 50MB
    Storage: AWS S3 (ephemeral, auto-deleted after 24h)
    
    Request Body:
        encrypted_data (str): Encrypted QuickBooks data
        company_name (str, optional): Company name
        qb_file_name (str, optional): Original QB filename
    
    Returns:
        200: Upload successful (or duplicate detected)
        400: Invalid input
        401: Not authenticated
        413: Payload too large
        429: Too many requests
        500: Server error
    """
    
    try:
        # Get request ID for tracing
        request_id = request.headers.get('X-Request-ID', 'unknown')
        
        # Validate request
        if not request.is_json:
            logger.warning(f"Non-JSON upload attempt from user {current_user.id}")
            return jsonify({
                'success': False,
                'error': 'Content-Type must be application/json'
            }), 400
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is empty'
            }), 400
        
        # Extract fields
        if 'encrypted_data' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required field: encrypted_data'
            }), 400
        
        encrypted_data = data['encrypted_data']
        company_name = data.get('company_name', '').strip()[:255]
        qb_file_name = data.get('qb_file_name', '').strip()[:255]
        
        # Validate encrypted data
        is_valid, error = validate_encrypted_data(encrypted_data)
        if not is_valid:
            logger.warning(f"Invalid encrypted data from user {current_user.id}: {error}")
            return jsonify({
                'success': False,
                'error': error
            }), 400
        
        # Scan for malware
        is_safe, error = scan_for_malware(encrypted_data)
        if not is_safe:
            logger.warning(f"Malware detected in upload from user {current_user.id}: {error}")
            return jsonify({
                'success': False,
                'error': 'File rejected: security scan failed'
            }), 400
        
        # Calculate file hash for duplicate detection
        file_hash = hashlib.sha256(encrypted_data.encode()).hexdigest()
        
        # Check for duplicate
        duplicate = Migration.find_duplicate(current_user.id, file_hash)
        if duplicate:
            logger.info(f"Duplicate file detected for user {current_user.id}: {duplicate.migration_id}")
            return jsonify({
                'success': True,
                'migration_id': duplicate.migration_id,
                'status': duplicate.status,
                'message': 'File already uploaded (duplicate detected)',
                'duplicate': True
            }), 200
        
        # Log data size
        data_size = len(encrypted_data)
        logger.info(f"Upload request from user {current_user.id}, size: {data_size} bytes, hash: {file_hash[:16]}...")
        
        # Create migration record
        try:
            migration = Migration(
                user_id=current_user.id,
                status='pending',
                company_name=company_name if company_name else None,
                qb_file_name=qb_file_name if qb_file_name else None,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')[:500],
                request_id=request_id,
                data_size_bytes=data_size
            )
            
            # Set file hash
            migration.file_hash = file_hash
            
            # Estimate cost
            migration.estimate_cost()
            
            db.session.add(migration)
            db.session.commit()
            
            migration_id = migration.migration_id
            
        except Exception as e:
            logger.error(f"Database error creating migration for user {current_user.id}: {str(e)}")
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': 'Failed to create migration record'
            }), 500
        
        # Mark as uploading
        migration.mark_as_uploading()
        
        # Upload to S3 (NOT local disk)
        try:
            logger.info(f"Uploading migration {migration_id} to S3...")
            
            # Initialize AWS manager
            aws_manager = AWSMigrationManager(
                region=current_app.config.get('AWS_REGION', 'us-east-1')
            )
            
            # Convert string to file-like object for S3 upload
            encrypted_file = io.BytesIO(encrypted_data.encode('utf-8'))
            
            # Upload to S3
            s3_result = aws_manager.upload_to_s3(
                file_obj=encrypted_file,
                migration_id=migration_id,
                metadata={
                    'user_id': str(current_user.id),
                    'company_name': company_name,
                    'qb_file_name': qb_file_name,
                    'original_size': str(data_size),
                    'file_hash': file_hash
                }
            )
            
            if not s3_result:
                logger.error(f"S3 upload failed for migration {migration_id}")
                migration.mark_as_failed('Failed to upload to S3', 'S3_UPLOAD_ERROR')
                return jsonify({
                    'success': False,
                    'error': 'Failed to upload file to secure storage'
                }), 500
            
            s3_uri = s3_result['uri']
            s3_bucket = s3_result['bucket']
            s3_key = s3_result['key']
            
            logger.info(f"Successfully uploaded to S3: {s3_uri}")
            
        except Exception as e:
            logger.exception(f"S3 upload error for migration {migration_id}: {str(e)}")
            migration.mark_as_failed(f'Upload error: {str(e)}', 'UPLOAD_ERROR')
            return jsonify({
                'success': False,
                'error': 'Failed to upload file'
            }), 500
        
        # Mark as uploaded
        try:
            migration.mark_as_uploaded(s3_uri, s3_bucket, s3_key)
            
        except Exception as e:
            logger.error(f"Failed to update migration status for {migration_id}: {str(e)}")
            db.session.rollback()
            
            # Try to clean up S3 file
            try:
                aws_manager.delete_s3_file(migration_id)
            except:
                pass
            
            return jsonify({
                'success': False,
                'error': 'Failed to finalize upload'
            }), 500
        
        logger.info(f"Upload successful: migration_id={migration_id}, "
                   f"user_id={current_user.id}, size={data_size} bytes, "
                   f"estimated_cost=${migration.estimated_cost_usd}")
        
        return jsonify({
            'success': True,
            'migration_id': migration_id,
            'status': 'uploaded',
            'message': 'Data uploaded successfully to secure cloud storage',
            'estimated_cost_usd': float(migration.estimated_cost_usd) if migration.estimated_cost_usd else None,
            'data_size_mb': round(data_size / (1024 ** 2), 2)
        }), 200
        
    except Exception as e:
        logger.exception(f"Unexpected error in upload from user {current_user.id if current_user.is_authenticated else 'anonymous'}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500