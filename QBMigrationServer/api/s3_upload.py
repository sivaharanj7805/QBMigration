"""
S3 Upload API with Pre-signed URLs
Enables direct uploads from C# client to S3
"""

import logging
import os
import re as _re
from datetime import datetime, timezone

import boto3
from api.auth import require_auth
from botocore.config import Config
from extensions import limiter
from flask import Blueprint, jsonify, request
from models import Migration, db
from utils.anomaly_detector import check_upload_anomalies, log_anomaly
from utils.error_sanitizer import sanitize_error_message
from utils.pii_redaction import hash_ip

logger = logging.getLogger(__name__)

s3_upload_bp = Blueprint("s3_upload", __name__, url_prefix="/api/upload")

# S3 client with retry config
s3_config = Config(
    retries={"max_attempts": 3, "mode": "adaptive"}, signature_version="s3v4"
)


def get_s3_client():
    """Get configured S3 client"""
    return boto3.client(
        "s3", region_name=os.getenv("AWS_REGION", "ca-central-1"), config=s3_config
    )


@s3_upload_bp.route("/presigned-url", methods=["POST"])
@require_auth
@limiter.limit("20 per minute")
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
    user_id = request.current_user["user_id"]

    session_id = data.get("session_id")
    file_name = data.get("file_name", "data.enc")
    file_size = data.get("file_size", 0)
    content_type = data.get("content_type", "application/octet-stream")
    sha256_hash = data.get("sha256_hash")

    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    # SECURITY FIX: Sanitize session_id and file_name to prevent path traversal
    if not _re.match(r"^[a-zA-Z0-9\-]{1,100}$", session_id):
        return jsonify({"error": "Invalid session_id format"}), 400

    safe_file_name = _re.sub(r"[^a-zA-Z0-9._\-]", "_", file_name)[:255]
    if ".." in safe_file_name or safe_file_name.startswith("/"):
        return jsonify({"error": "Invalid file_name"}), 400

    # SECURITY FIX: Validate file_size to prevent abuse (max 10 GB)
    max_file_size = 10 * 1024 * 1024 * 1024
    if file_size and int(file_size) > max_file_size:
        return jsonify({"error": "File too large"}), 400

    # Generate S3 key with sanitized inputs
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    s3_key = f"migrations/{session_id}/{timestamp}_{safe_file_name}"

    bucket = os.getenv("AWS_S3_BUCKET", "forensicbridge-migrations")

    try:
        s3 = get_s3_client()

        # Generate pre-signed URL for PUT
        presigned_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": bucket,
                "Key": s3_key,
                "ContentType": content_type,
                "ServerSideEncryption": "aws:kms",
            },
            ExpiresIn=3600,  # 1 hour
            HttpMethod="PUT",
        )

        # Create migration record
        # FIX BE-01: Hash IP address for GDPR compliance
        migration = Migration(
            user_id=user_id,
            session_id=session_id,
            status="uploading",
            s3_bucket=bucket,
            s3_key=s3_key,
            data_size_bytes=file_size,
            file_hash=sha256_hash,
            ip_address=hash_ip(request.remote_addr),
        )

        db.session.add(migration)
        db.session.commit()

        return jsonify(
            {
                "upload_url": presigned_url,
                "migration_id": migration.migration_id,
                "expires_in": 3600,
                "s3_key": s3_key,
                "s3_bucket": bucket,
            }
        )

    except Exception as e:
        db.session.rollback()
        # FIX #34: Sanitize error message for security
        sanitized_error = sanitize_error_message(e, context="upload")
        return jsonify({"error": sanitized_error}), 500


@s3_upload_bp.route("/complete", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
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
    user_id = request.current_user["user_id"]

    migration_id = data.get("migration_id")
    sha256_hash = data.get("sha256_hash")
    company_name = data.get("company_name")

    if not migration_id:
        return jsonify({"error": "migration_id required"}), 400

    # Find migration
    migration = Migration.query.filter_by(
        migration_id=migration_id, user_id=user_id
    ).first()

    if not migration:
        return jsonify({"error": "Migration not found"}), 404

    # Verify hash matches (prevents tampering)
    if sha256_hash and migration.file_hash and migration.file_hash != sha256_hash:
        migration.mark_as_failed(
            "Hash mismatch - file may be corrupted", "HASH_MISMATCH"
        )
        return jsonify({"error": "Hash mismatch"}), 400

    # FIX #39: Anomaly detection for large file uploads
    file_size = migration.data_size_bytes or 0
    if file_size > 0:
        anomalies = check_upload_anomalies(user_id, file_size)

        if anomalies:
            # Log all detected anomalies
            for anomaly in anomalies:
                log_anomaly(user_id, anomaly)

            # For critical anomalies (> 5GB single file), add warning
            critical_anomalies = [a for a in anomalies if a["severity"] == "critical"]
            if critical_anomalies:
                logger.warning(
                    f"CRITICAL upload anomaly for user {user_id}: "
                    f"{', '.join(a['reason'] for a in critical_anomalies)}"
                )

    # Update migration
    migration.company_name = company_name
    migration.mark_as_uploaded(
        s3_uri=f"s3://{migration.s3_bucket}/{migration.s3_key}",
        s3_bucket=migration.s3_bucket,
        s3_key=migration.s3_key,
    )

    # Trigger processing (via Celery)
    try:
        from workers.migration_worker import process_migration

        process_migration.delay(migration_id)
        logger.info(f"Migration {migration_id} queued for processing via Celery")
    except ImportError:
        # FIX BE-06: Log when Celery is not configured instead of silent pass
        logger.warning(
            f"Celery not configured - migration {migration_id} will require manual processing"
        )

    return jsonify(
        {
            "success": True,
            "migration_id": migration_id,
            "status": "uploaded",
            "message": "Upload complete. Processing will begin shortly.",
        }
    )


@s3_upload_bp.route("/multipart/init", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def init_multipart_upload():
    """
    Initialize multipart upload for large files (>100MB)
    """
    data = request.get_json()
    user_id = request.current_user["user_id"]

    session_id = data.get("session_id")
    file_name = data.get("file_name", "data.enc")
    file_size = data.get("file_size", 0)

    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    # SECURITY FIX C-01: Sanitize session_id and file_name to prevent path traversal
    if not _re.match(r"^[a-zA-Z0-9\-]{1,100}$", session_id):
        return jsonify({"error": "Invalid session_id format"}), 400

    safe_file_name = _re.sub(r"[^a-zA-Z0-9._\-]", "_", file_name)[:255]
    if ".." in safe_file_name or safe_file_name.startswith("/"):
        return jsonify({"error": "Invalid file_name"}), 400

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    s3_key = f"migrations/{session_id}/{timestamp}_{safe_file_name}"
    bucket = os.getenv("AWS_S3_BUCKET", "forensicbridge-migrations")

    try:
        s3 = get_s3_client()

        # Create multipart upload
        response = s3.create_multipart_upload(
            Bucket=bucket,
            Key=s3_key,
            ContentType="application/octet-stream",
            ServerSideEncryption="aws:kms",
        )

        upload_id = response["UploadId"]

        # Create migration record
        # FIX BE-01: Hash IP address for GDPR compliance
        migration = Migration(
            user_id=user_id,
            session_id=session_id,
            status="uploading",
            s3_bucket=bucket,
            s3_key=s3_key,
            data_size_bytes=file_size,
            ip_address=hash_ip(request.remote_addr),
        )

        db.session.add(migration)
        db.session.commit()

        return jsonify(
            {
                "upload_id": upload_id,
                "migration_id": migration.migration_id,
                "s3_key": s3_key,
                "s3_bucket": bucket,
            }
        )

    except Exception as e:
        db.session.rollback()
        # FIX #34: Sanitize error message for security
        sanitized_error = sanitize_error_message(e, context="upload")
        return jsonify({"error": sanitized_error}), 500


@s3_upload_bp.route("/multipart/part-url", methods=["POST"])
@require_auth
@limiter.limit("120 per minute")
def get_part_upload_url():
    """
    Get pre-signed URL for a multipart upload part
    """
    data = request.get_json()
    user_id = request.current_user["user_id"]

    upload_id = data.get("upload_id")
    part_number = data.get("part_number")
    migration_id = data.get("migration_id")

    if not migration_id:
        return jsonify({"error": "migration_id required"}), 400

    # SECURITY FIX C-02a: Look up migration to get trusted s3_key instead of accepting user input
    migration = Migration.query.filter_by(
        migration_id=migration_id, user_id=user_id
    ).first()

    if not migration:
        return jsonify({"error": "Migration not found"}), 404

    s3_key = migration.s3_key
    bucket = os.getenv("AWS_S3_BUCKET", "forensicbridge-migrations")

    try:
        s3 = get_s3_client()

        presigned_url = s3.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": bucket,
                "Key": s3_key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=3600,
        )

        return jsonify(
            {
                "upload_url": presigned_url,
                "part_number": part_number,
                "expires_in": 3600,
            }
        )

    except Exception as e:
        # FIX #34: Sanitize error message for security
        sanitized_error = sanitize_error_message(e, context="upload")
        return jsonify({"error": sanitized_error}), 500


@s3_upload_bp.route("/multipart/complete", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def complete_multipart_upload():
    """
    Complete multipart upload
    """
    data = request.get_json()
    user_id = request.current_user["user_id"]

    upload_id = data.get("upload_id")
    s3_key = data.get("s3_key")
    parts = data.get("parts", [])  # [{"PartNumber": 1, "ETag": "..."}]
    migration_id = data.get("migration_id")

    if not migration_id:
        return jsonify({"error": "migration_id required"}), 400

    # SECURITY FIX C-02b: Verify s3_key matches migration record before executing S3 operation
    migration = Migration.query.filter_by(
        migration_id=migration_id, user_id=user_id
    ).first()

    if not migration:
        return jsonify({"error": "Migration not found"}), 404

    if s3_key != migration.s3_key:
        return jsonify({"error": "S3 key mismatch"}), 403

    bucket = os.getenv("AWS_S3_BUCKET", "forensicbridge-migrations")

    try:
        s3 = get_s3_client()

        # Complete the multipart upload
        s3.complete_multipart_upload(
            Bucket=bucket,
            Key=migration.s3_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

        # Update migration status
        migration.mark_as_uploaded(
            s3_uri=f"s3://{bucket}/{migration.s3_key}",
            s3_bucket=bucket,
            s3_key=migration.s3_key,
        )

        return jsonify({"success": True, "message": "Upload complete"})

    except Exception as e:
        # FIX #34: Sanitize error message for security
        sanitized_error = sanitize_error_message(e, context="upload")
        return jsonify({"error": sanitized_error}), 500
