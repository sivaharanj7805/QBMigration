import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone

from extensions import limiter
from flask import Blueprint, current_app, jsonify, request
from models.database import db, is_postgresql
from models.migration import Migration
from utils.aws_manager import AWSMigrationManager
from utils.notifications import send_migration_failure_alert

webhooks_bp = Blueprint("webhooks", __name__)
logger = logging.getLogger(__name__)

# Webhook payload size limit (1MB - status updates should be small)
WEBHOOK_MAX_PAYLOAD_BYTES = 1 * 1024 * 1024


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
        except Exception:
            logger.error(f"Invalid timestamp format: {timestamp}")
            return False, "Invalid timestamp format"

        # Check timestamp is recent (prevent replay attacks)
        # Ensure webhook_time is timezone-aware before comparison
        if webhook_time.tzinfo is None:
            webhook_time = webhook_time.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - webhook_time
        # MED-02 FIX: Reduced default replay window from 5 minutes to 2 minutes
        # to shrink the window for delayed replay attacks.
        max_age = timedelta(
            minutes=current_app.config.get("WEBHOOK_REPLAY_WINDOW_MINUTES", 2)
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
        return False, "Signature verification failed"


def _process_webhook(webhook_type, expected_status, handler_fn):
    """
    Common webhook processing pipeline: validates headers, verifies signature,
    performs replay detection, acquires a row lock, and delegates to handler_fn.

    Args:
        webhook_type: Human-readable webhook type for logging (e.g., "migration-started")
        expected_status: Expected migration status before processing (reserved for
            future validation)
        handler_fn: Callable(migration, data) that performs type-specific mutations.
            Must NOT call db.session.commit(); the caller handles the commit.
            Returns a (response_dict, status_code) tuple.

    Returns:
        Flask response tuple (jsonify(...), status_code)
    """
    try:
        # SECURITY: Reject oversized webhook payloads
        if (
            request.content_length
            and request.content_length > WEBHOOK_MAX_PAYLOAD_BYTES
        ):
            logger.warning(
                f"Webhook payload too large: {request.content_length} bytes "
                f"from {request.remote_addr}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Payload too large (max {WEBHOOK_MAX_PAYLOAD_BYTES} bytes)",
                    }
                ),
                413,
            )

        # Extract and validate required headers
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
                        "error": (
                            "Missing required headers: X-Migration-Id,"
                            " X-Webhook-Signature, X-Webhook-Timestamp,"
                            " X-Webhook-Id"
                        ),
                    }
                ),
                400,
            )

        # Verify signature
        is_valid, error = verify_webhook_signature(migration_id, signature, timestamp)
        if not is_valid:
            logger.warning(f"Invalid webhook signature for {migration_id}: {error}")
            return (
                jsonify({"success": False, "error": "Webhook verification failed"}),
                401,
            )

        # Parse JSON payload
        data = request.get_json() or {}

        # CRITICAL FIX: Use SELECT FOR UPDATE to prevent race conditions
        # Use nowait=True to prevent indefinite blocking, with retry logic
        # Note: FOR UPDATE only works with PostgreSQL; SQLite has implicit locking
        try:
            query = db.session.query(Migration).filter_by(migration_id=migration_id)
            if is_postgresql():
                migration = query.with_for_update(nowait=True).first()
            else:
                migration = query.first()
        except Exception:
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

        # Check idempotency (protected by row-level lock)
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

        # Delegate to type-specific handler
        response_body, status_code = handler_fn(migration, data)

        db.session.commit()
        return jsonify(response_body), status_code

    except Exception as e:
        logger.exception(f"Failed to process {webhook_type} webhook: {str(e)}")
        db.session.rollback()
        # AUDIT FIX MUST-06: Enqueue failed webhooks to PostgreSQL dead letter queue
        # instead of only logging them. This enables replay from the admin dashboard.
        import traceback as _tb

        try:
            from models.dead_letter import DeadLetterWebhook

            DeadLetterWebhook.enqueue(
                source="migration",
                event_type=webhook_type,
                payload=request.get_data(as_text=True)[:10000],
                error_message=str(e),
                event_id=request.headers.get("X-Webhook-Id"),
                migration_id=request.headers.get("X-Migration-Id"),
                headers=json.dumps(
                    {
                        k: v
                        for k, v in request.headers
                        if k.startswith("X-") and "signature" not in k.lower()
                    }
                ),
                error_traceback=_tb.format_exc(),
            )
        except Exception as dlq_err:
            # Fallback to log-only if DLQ insert fails (e.g., DB down)
            logger.error(
                f"DEAD_LETTER (DLQ insert failed: {dlq_err}): "
                f"webhook_type={webhook_type} "
                f"migration_id={request.headers.get('X-Migration-Id', 'unknown')} "
                f"webhook_id={request.headers.get('X-Webhook-Id', 'unknown')} "
                f"error={str(e)[:200]}"
            )
        return jsonify({"success": False, "error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Type-specific handler functions
# ---------------------------------------------------------------------------


def _handle_started(migration, data):
    """Update migration to 'processing' and record the EC2 instance ID."""
    instance_id = data.get("instance_id")
    if instance_id and not migration.aws_instance_id:
        migration.mark_as_processing(instance_id)
    else:
        migration.status = "processing"
        migration.started_at = datetime.now(timezone.utc)
    logger.info(f"Migration {migration.migration_id} started on instance {instance_id}")
    return {"success": True, "message": "Migration start acknowledged"}, 200


def _handle_progress(migration, data):
    """Store the latest progress percentage and step description."""
    progress_percent = min(data.get("progress_percent", 0), 100)
    current_step = data.get("current_step", "")
    migration.progress_percent = progress_percent
    migration.current_step = current_step[:255]
    logger.info(
        f"Migration {migration.migration_id} progress: "
        f"{progress_percent}% - {current_step}"
    )
    return {"success": True}, 200


def _handle_completed(migration, data):
    """Mark the migration as completed and schedule infrastructure cleanup."""
    results = data.get("results", {})
    migration.mark_as_completed(results)
    logger.info(f"Migration {migration.migration_id} completed successfully")

    # PRODUCTION FIX: Trigger async cleanup via Celery task
    # This prevents webhook response delays from AWS API calls
    cleanup_status = "scheduled"
    try:
        # Lazy import to avoid circular dependency with tasks.py
        from tasks import cleanup_migration_async

        cleanup_migration_async.delay(migration.migration_id, migration.aws_instance_id)
        logger.info(f"Scheduled async cleanup for migration {migration.migration_id}")
    except Exception as e:
        logger.error(
            f"Failed to schedule async cleanup for {migration.migration_id}: {str(e)}"
        )
        # Fall back to synchronous cleanup if Celery unavailable
        try:
            aws_manager = AWSMigrationManager()
            aws_manager.cleanup_migration(
                migration.migration_id, migration.aws_instance_id
            )
            cleanup_status = "completed_sync"
        except Exception as sync_err:
            logger.error(
                f"Sync cleanup also failed for {migration.migration_id}: "
                f"{str(sync_err)}"
            )
            cleanup_status = "failed"

    # FIX B-03: Always return 200 (migration IS completed) but include cleanup status
    return {
        "success": True,
        "message": "Migration completed",
        "cleanup_status": cleanup_status,
    }, 200


def _handle_failed(migration, data):
    """Mark the migration as failed, alert if retries exhausted, and clean up."""
    error_message = data.get("error", "Unknown error")
    error_code = data.get("error_code", "UNKNOWN_ERROR")
    migration.mark_as_failed(error_message, error_code)
    logger.error(f"Migration {migration.migration_id} failed: {error_message}")

    # Send alert if critical
    if migration.retry_count >= migration.max_retries:
        try:
            send_migration_failure_alert(migration)
        except Exception as e:
            logger.warning(
                f"Failed to send failure alert for {migration.migration_id}: {e}"
            )

    # AUDIT FIX HIGH-02: Use async Celery cleanup (matching _handle_completed)
    # to prevent slow AWS API calls from delaying the webhook response.
    cleanup_status = "scheduled"
    try:
        from tasks import cleanup_migration_async

        cleanup_migration_async.delay(migration.migration_id, migration.aws_instance_id)
        logger.info(
            f"Scheduled async cleanup for failed migration {migration.migration_id}"
        )
    except Exception as e:
        logger.error(
            f"Failed to schedule async cleanup for {migration.migration_id}: {str(e)}"
        )
        # Fall back to synchronous cleanup if Celery unavailable
        try:
            aws_manager = AWSMigrationManager()
            aws_manager.cleanup_migration(
                migration.migration_id, migration.aws_instance_id
            )
            cleanup_status = "completed_sync"
        except Exception as sync_err:
            logger.error(
                f"Sync cleanup also failed for {migration.migration_id}: {str(sync_err)}"
            )
            cleanup_status = "failed"

    return {
        "success": True,
        "message": "Failure acknowledged",
        "cleanup_status": cleanup_status,
    }, 200


# ---------------------------------------------------------------------------
# Route definitions
# ---------------------------------------------------------------------------


@webhooks_bp.route("/api/webhooks/migration-started", methods=["POST"])
@limiter.limit("60 per minute")
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
    return _process_webhook("migration-started", "pending", _handle_started)


@webhooks_bp.route("/api/webhooks/migration-progress", methods=["POST"])
@limiter.limit("300 per minute")
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
    return _process_webhook("migration-progress", "processing", _handle_progress)


@webhooks_bp.route("/api/webhooks/migration-completed", methods=["POST"])
@limiter.limit("60 per minute")
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
    return _process_webhook("migration-completed", "processing", _handle_completed)


@webhooks_bp.route("/api/webhooks/migration-failed", methods=["POST"])
@limiter.limit("60 per minute")
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
    return _process_webhook("migration-failed", "processing", _handle_failed)


@webhooks_bp.route("/api/webhooks/health", methods=["GET"])
@limiter.limit("120 per minute")
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
