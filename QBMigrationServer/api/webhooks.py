import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from models.database import db, is_postgresql
from models.migration import Migration
from utils.pii_redaction import hash_email

webhooks_bp = Blueprint("webhooks", __name__)
logger = logging.getLogger(__name__)


def verify_webhook_signature(migration_id, signature, timestamp):
    """
    Verify webhook signature with replay attack prevention

    Args:
        migration_id: Migration ID
        signature: HMAC signature from request
        timestamp: ISO format timestamp

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        webhook_secret = current_app.config.get("WEBHOOK_SECRET")

        if not webhook_secret:
            # CRIT-04 FIX: Fail-closed when webhook secret is not configured
            logger.error("WEBHOOK_SECRET not configured - rejecting webhook")
            return (
                False,
                "Webhook secret not configured. Set WEBHOOK_SECRET environment variable.",
            )

        # Parse timestamp
        try:
            webhook_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except Exception as e:
            logger.error(f"Invalid timestamp format: {timestamp}")
            return False, "Invalid timestamp format"

        # Check timestamp is recent (prevent replay attacks)
        # Ensure webhook_time is timezone-aware before comparison
        if webhook_time.tzinfo is None:
            webhook_time = webhook_time.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - webhook_time
        max_age = timedelta(
            minutes=current_app.config.get("WEBHOOK_REPLAY_WINDOW_MINUTES", 5)
        )

        if age > max_age:
            logger.warning(
                f"Webhook expired: age={age.total_seconds()}s, max={max_age.total_seconds()}s"
            )
            return (
                False,
                f"Webhook expired (older than {max_age.total_seconds():.0f} seconds)",
            )

        if age < timedelta(seconds=-30):
            logger.warning(f"Webhook timestamp in future: {timestamp}")
            return False, "Webhook timestamp in future"

        # Calculate expected signature (include timestamp to prevent replay)
        message = f"{migration_id}:{timestamp}".encode("utf-8")
        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"), message, hashlib.sha256
        ).hexdigest()

        # Compare signatures (constant time to prevent timing attacks)
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning(f"Invalid webhook signature for {migration_id}")
            return False, "Invalid signature"

        return True, None

    except Exception as e:
        logger.exception(f"Signature verification failed: {str(e)}")
        return False, str(e)


@webhooks_bp.route("/api/webhooks/migration-started", methods=["POST"])
def migration_started():
    """
    Webhook called when EC2 instance starts migration

    Request Headers:
        X-Migration-Id: Migration ID
        X-Webhook-Signature: HMAC signature
        X-Webhook-Timestamp: ISO 8601 timestamp
        X-Webhook-Id: Unique webhook ID (for idempotency)

    Request Body:
        migration_id (str): Migration ID
        instance_id (str): EC2 instance ID

    Returns:
        200: Acknowledged
        400: Invalid request
        401: Invalid signature
        404: Migration not found
        409: Already processed (idempotent)
        500: Server error
    """
    try:
        # Extract headers
        migration_id = request.headers.get("X-Migration-Id")
        signature = request.headers.get("X-Webhook-Signature")
        timestamp = request.headers.get("X-Webhook-Timestamp")
        webhook_id = request.headers.get("X-Webhook-Id")

        if not all([migration_id, signature, timestamp, webhook_id]):
            logger.warning(f"Missing webhook headers from {request.remote_addr}")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Missing required headers: X-Migration-Id, X-Webhook-Signature, X-Webhook-Timestamp, X-Webhook-Id",
                    }
                ),
                400,
            )

        # Verify signature
        is_valid, error = verify_webhook_signature(migration_id, signature, timestamp)
        if not is_valid:
            logger.warning(f"Invalid webhook signature for {migration_id}: {error}")
            return (
                jsonify(
                    {"success": False, "error": f"Webhook verification failed: {error}"}
                ),
                401,
            )

        # Get request data
        data = request.get_json() or {}
        instance_id = data.get("instance_id")

        # CRITICAL FIX: Use SELECT FOR UPDATE to prevent race conditions
        # This ensures only one webhook handler can process the same migration at a time
        # FIX: Use nowait=True to prevent indefinite blocking, with retry logic
        # Note: FOR UPDATE only works with PostgreSQL; SQLite has implicit locking
        from models.database import is_postgresql

        try:
            query = db.session.query(Migration).filter_by(migration_id=migration_id)
            if is_postgresql():
                migration = query.with_for_update(nowait=True).first()
            else:
                migration = query.first()
        except Exception as lock_error:
            # Row is locked by another process - this is expected under high concurrency
            logger.warning(
                f"Migration {migration_id} is locked by another webhook handler, retrying..."
            )
            db.session.rollback()
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Migration is being processed by another request. Please retry.",
                        "retry_after": 1,
                    }
                ),
                503,
            )

        if not migration:
            logger.error(f"Migration not found: {migration_id}")
            return jsonify({"success": False, "error": "Migration not found"}), 404

        # Check idempotency (prevent duplicate processing)
        # Now protected by row-level lock from SELECT FOR UPDATE
        if migration.is_webhook_processed(webhook_id):
            logger.info(f"Webhook {webhook_id} already processed for {migration_id}")
            db.session.commit()  # Release the lock
            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Already processed",
                        "idempotent": True,
                    }
                ),
                200,
            )

        # Mark webhook as processed (atomic with the lock)
        migration.mark_webhook_processed(webhook_id)

        # Update migration
        if instance_id and not migration.aws_instance_id:
            migration.mark_as_processing(instance_id)
        else:
            migration.status = "processing"
            migration.started_at = datetime.now(timezone.utc)
            db.session.commit()

        logger.info(f"Migration {migration_id} started on instance {instance_id}")

        return (
            jsonify({"success": True, "message": "Migration start acknowledged"}),
            200,
        )

    except Exception as e:
        logger.exception(f"Failed to process migration-started webhook: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": "Internal server error"}), 500


@webhooks_bp.route("/api/webhooks/migration-progress", methods=["POST"])
def migration_progress():
    """
    Webhook called to update migration progress

    Request Body:
        migration_id (str): Migration ID
        progress_percent (int): Progress percentage (0-100)
        current_step (str): Current step description

    Returns:
        200: Acknowledged
        401: Invalid signature
        404: Migration not found
        409: Already processed
        500: Server error
    """
    try:
        # Extract headers
        migration_id = request.headers.get("X-Migration-Id")
        signature = request.headers.get("X-Webhook-Signature")
        timestamp = request.headers.get("X-Webhook-Timestamp")
        webhook_id = request.headers.get("X-Webhook-Id")

        # CRITICAL FIX: Always require ALL headers (no fallback UUID generation)
        if not all([migration_id, signature, timestamp, webhook_id]):
            logger.warning(
                f"Missing required webhook headers from {request.remote_addr}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Missing required headers: X-Migration-Id, X-Webhook-Signature, X-Webhook-Timestamp, X-Webhook-Id",
                    }
                ),
                400,
            )

        # Verify signature
        is_valid, error = verify_webhook_signature(migration_id, signature, timestamp)
        if not is_valid:
            logger.warning(f"Invalid webhook signature for {migration_id}: {error}")
            return (
                jsonify({"success": False, "error": f"Verification failed: {error}"}),
                401,
            )

        # Get data
        data = request.get_json() or {}
        progress_percent = min(data.get("progress_percent", 0), 100)
        current_step = data.get("current_step", "")

        # CRITICAL FIX: Use SELECT FOR UPDATE to prevent race conditions
        # FIX: Use nowait=True to prevent indefinite blocking
        # Note: FOR UPDATE only works with PostgreSQL; SQLite has implicit locking
        try:
            query = db.session.query(Migration).filter_by(migration_id=migration_id)
            if is_postgresql():
                migration = query.with_for_update(nowait=True).first()
            else:
                migration = query.first()
        except Exception as lock_error:
            logger.warning(f"Migration {migration_id} is locked, retrying...")
            db.session.rollback()
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Migration is being processed by another request. Please retry.",
                        "retry_after": 1,
                    }
                ),
                503,
            )

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        # Check idempotency (protected by row-level lock)
        if migration.is_webhook_processed(webhook_id):
            db.session.commit()  # Release the lock
            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Already processed",
                        "idempotent": True,
                    }
                ),
                200,
            )

        # Mark processed (atomic with the lock)
        migration.mark_webhook_processed(webhook_id)

        # Update progress
        migration.progress_percent = progress_percent
        migration.current_step = current_step[:255]
        db.session.commit()

        logger.info(
            f"Migration {migration_id} progress: {progress_percent}% - {current_step}"
        )

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.exception(f"Failed to process migration-progress webhook: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": "Internal server error"}), 500


@webhooks_bp.route("/api/webhooks/migration-completed", methods=["POST"])
def migration_completed():
    """
    Webhook called when migration completes successfully

    Request Body:
        migration_id (str): Migration ID
        status (str): Final status
        results (dict): Migration results

    Returns:
        200: Acknowledged
        401: Invalid signature
        404: Migration not found
        409: Already processed
        500: Server error
    """
    try:
        # Extract headers
        migration_id = request.headers.get("X-Migration-Id")
        signature = request.headers.get("X-Webhook-Signature")
        timestamp = request.headers.get("X-Webhook-Timestamp")
        webhook_id = request.headers.get("X-Webhook-Id")

        # SECURITY: Require all headers (no UUID fallback)
        if not all([migration_id, signature, timestamp, webhook_id]):
            logger.warning(
                f"Missing required webhook headers from {request.remote_addr}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Missing required headers: X-Migration-Id, X-Webhook-Signature, X-Webhook-Timestamp, X-Webhook-Id",
                    }
                ),
                400,
            )

        # Verify signature
        is_valid, error = verify_webhook_signature(migration_id, signature, timestamp)
        if not is_valid:
            return (
                jsonify({"success": False, "error": f"Verification failed: {error}"}),
                401,
            )

        # Get data
        data = request.get_json() or {}
        results = data.get("results", {})

        # CRITICAL FIX: Use SELECT FOR UPDATE to prevent race conditions
        # FIX: Use nowait=True to prevent indefinite blocking
        # Note: FOR UPDATE only works with PostgreSQL; SQLite has implicit locking
        try:
            query = db.session.query(Migration).filter_by(migration_id=migration_id)
            if is_postgresql():
                migration = query.with_for_update(nowait=True).first()
            else:
                migration = query.first()
        except Exception as lock_error:
            logger.warning(f"Migration {migration_id} is locked, retrying...")
            db.session.rollback()
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Migration is being processed by another request. Please retry.",
                        "retry_after": 1,
                    }
                ),
                503,
            )

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        # Check idempotency (protected by row-level lock)
        if migration.is_webhook_processed(webhook_id):
            db.session.commit()  # Release the lock
            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Already processed",
                        "idempotent": True,
                    }
                ),
                200,
            )

        # Mark processed (atomic with the lock)
        migration.mark_webhook_processed(webhook_id)

        # Mark as completed
        migration.mark_as_completed(results)

        logger.info(f"Migration {migration_id} completed successfully")

        # PRODUCTION FIX: Trigger async cleanup via Celery task
        # This prevents webhook response delays from AWS API calls
        try:
            from tasks import cleanup_migration_async

            cleanup_migration_async.delay(migration_id, migration.aws_instance_id)
            logger.info(f"Scheduled async cleanup for migration {migration_id}")
        except Exception as e:
            logger.error(
                f"Failed to schedule async cleanup for {migration_id}: {str(e)}"
            )
            # Fall back to synchronous cleanup if Celery unavailable
            try:
                from utils.aws_manager import AWSMigrationManager

                aws_manager = AWSMigrationManager()
                aws_manager.cleanup_migration(migration_id, migration.aws_instance_id)
            except Exception as sync_err:
                logger.error(
                    f"Sync cleanup also failed for {migration_id}: {str(sync_err)}"
                )

        return jsonify({"success": True, "message": "Migration completed"}), 200

    except Exception as e:
        logger.exception(f"Failed to process migration-completed webhook: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": "Internal server error"}), 500


@webhooks_bp.route("/api/webhooks/migration-failed", methods=["POST"])
def migration_failed():
    """
    Webhook called when migration fails

    Request Body:
        migration_id (str): Migration ID
        error (str): Error message
        error_code (str): Error code

    Returns:
        200: Acknowledged
        401: Invalid signature
        404: Migration not found
        409: Already processed
        500: Server error
    """
    try:
        # Extract headers
        migration_id = request.headers.get("X-Migration-Id")
        signature = request.headers.get("X-Webhook-Signature")
        timestamp = request.headers.get("X-Webhook-Timestamp")
        webhook_id = request.headers.get("X-Webhook-Id")

        # SECURITY: Require all headers (no UUID fallback)
        if not all([migration_id, signature, timestamp, webhook_id]):
            logger.warning(
                f"Missing required webhook headers from {request.remote_addr}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Missing required headers: X-Migration-Id, X-Webhook-Signature, X-Webhook-Timestamp, X-Webhook-Id",
                    }
                ),
                400,
            )

        # Verify signature
        is_valid, error = verify_webhook_signature(migration_id, signature, timestamp)
        if not is_valid:
            return (
                jsonify({"success": False, "error": f"Verification failed: {error}"}),
                401,
            )

        # Get data
        data = request.get_json() or {}
        error_message = data.get("error", "Unknown error")
        error_code = data.get("error_code", "UNKNOWN_ERROR")

        # CRITICAL FIX: Use SELECT FOR UPDATE to prevent race conditions
        # FIX: Use nowait=True to prevent indefinite blocking
        # Note: FOR UPDATE only works with PostgreSQL; SQLite has implicit locking
        try:
            query = db.session.query(Migration).filter_by(migration_id=migration_id)
            if is_postgresql():
                migration = query.with_for_update(nowait=True).first()
            else:
                migration = query.first()
        except Exception as lock_error:
            logger.warning(f"Migration {migration_id} is locked, retrying...")
            db.session.rollback()
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Migration is being processed by another request. Please retry.",
                        "retry_after": 1,
                    }
                ),
                503,
            )

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        # Check idempotency (protected by row-level lock)
        if migration.is_webhook_processed(webhook_id):
            db.session.commit()  # Release the lock
            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Already processed",
                        "idempotent": True,
                    }
                ),
                200,
            )

        # Mark processed (atomic with the lock)
        migration.mark_webhook_processed(webhook_id)

        # Mark as failed
        migration.mark_as_failed(error_message, error_code)

        logger.error(f"Migration {migration_id} failed: {error_message}")

        # Send alert if critical
        if migration.retry_count >= migration.max_retries:
            try:
                from utils.notifications import send_migration_failure_alert

                send_migration_failure_alert(migration)
            except Exception as e:
                logger.warning(f"Failed to send failure alert for {migration_id}: {e}")

        # Trigger cleanup
        try:
            from utils.aws_manager import AWSMigrationManager

            aws_manager = AWSMigrationManager()
            aws_manager.cleanup_migration(migration_id, migration.aws_instance_id)
        except Exception as e:
            logger.error(f"Cleanup trigger failed for {migration_id}: {str(e)}")

        return jsonify({"success": True, "message": "Failure acknowledged"}), 200

    except Exception as e:
        logger.exception(f"Failed to process migration-failed webhook: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": "Internal server error"}), 500


@webhooks_bp.route("/api/webhooks/health", methods=["GET"])
def webhook_health():
    """Health check for webhook endpoint"""
    return (
        jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            }
        ),
        200,
    )
