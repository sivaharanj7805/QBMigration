"""
Session Validation API
Validates session codes from the ForensicBridge extractor to prevent fraud.

Security Features:
- Session ID validation against database
- Device fingerprint tracking (prevents sharing sessions)
- Usage limit enforcement
- Rate limiting
- Audit logging
"""

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from extensions import limiter
from flask import Blueprint, jsonify, request
from models.database import db
from models.project import Project
from utils.pii_redaction import hash_ip

logger = logging.getLogger(__name__)

session_validation_bp = Blueprint(
    "session_validation", __name__, url_prefix="/api/session"
)

# Configuration
MAX_DEVICES_PER_SESSION = int(
    os.getenv("MAX_DEVICES_PER_SESSION", "2")
)  # Allow 2 devices max
MAX_ACTIVATIONS_PER_SESSION = int(
    os.getenv("MAX_ACTIVATIONS_PER_SESSION", "5")
)  # Max 5 activations
RATE_LIMIT_WINDOW_MINUTES = 5
RATE_LIMIT_MAX_ATTEMPTS = 10


class SessionActivation(db.Model):
    """Tracks session activations for fraud prevention"""

    __tablename__ = "session_activations"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), nullable=False, index=True)
    device_fingerprint = db.Column(db.String(64), nullable=False)
    device_name = db.Column(db.String(255))  # Optional friendly name
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))

    # Activation status
    status = db.Column(db.String(50), default="active")  # active, revoked, expired
    activated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Usage tracking
    extraction_count = db.Column(db.Integer, default=0)
    last_extraction_at = db.Column(db.DateTime)

    # CRIT-03 FIX: Store extraction token for chain-of-custody validation.
    # start_extraction generates this token; complete_extraction must present it.
    extraction_token = db.Column(db.String(64), nullable=True)

    __table_args__ = (
        db.Index("idx_session_device", "session_id", "device_fingerprint"),
        db.UniqueConstraint(
            "session_id", "device_fingerprint", name="uq_session_device"
        ),
    )


class SessionValidationLog(db.Model):
    """Audit log for validation attempts"""

    __tablename__ = "session_validation_logs"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), index=True)
    device_fingerprint = db.Column(db.String(64))
    ip_address = db.Column(db.String(50))
    action = db.Column(db.String(50))  # validate, activate, extract, reject
    result = db.Column(db.String(50))  # success, failed, rate_limited, invalid
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


def log_validation_attempt(
    session_id, device_fingerprint, ip_address, action, result, error=None
):
    """Log a validation attempt for audit purposes"""
    try:
        log = SessionValidationLog(
            session_id=session_id,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            action=action,
            result=result,
            error_message=error,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log validation attempt: {e}")


def check_rate_limit(session_id, ip_address):
    """Check if the request is rate limited"""
    window_start = datetime.now(timezone.utc) - timedelta(
        minutes=RATE_LIMIT_WINDOW_MINUTES
    )

    attempt_count = SessionValidationLog.query.filter(
        SessionValidationLog.session_id == session_id,
        SessionValidationLog.ip_address == ip_address,
        SessionValidationLog.created_at >= window_start,
    ).count()

    return attempt_count >= RATE_LIMIT_MAX_ATTEMPTS


def hash_fingerprint(fingerprint):
    """
    Hash the device fingerprint for storage using HMAC-SHA256.

    SECURITY FIX: Uses HMAC with app secret instead of plain SHA-256.
    This prevents rainbow table attacks on low-entropy fingerprints.
    """
    if not fingerprint:
        return None

    from flask import current_app

    secret = current_app.config["SECRET_KEY"].encode()
    return hmac.new(secret, fingerprint.encode(), hashlib.sha256).hexdigest()


@session_validation_bp.route("/validate", methods=["POST"])
@limiter.limit("20 per minute")
def validate_session():
    """
    Validate a session code before allowing extraction.

    Request body:
    {
        "session_id": "FB-20260127123456-ABCD1234",
        "device_fingerprint": "hardware-specific-id",
        "device_name": "John's Workstation" (optional)
    }

    Response:
    {
        "valid": true/false,
        "session_id": "...",
        "project_name": "...",
        "client_name": "...",
        "tier": "starter/business/professional/enterprise/forensic",
        "remaining_extractions": 5,
        "error": "..." (if invalid)
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"valid": False, "error": "No data provided"}), 400

    session_id = data.get("session_id", "").strip()
    device_fingerprint = data.get("device_fingerprint", "").strip()
    device_name = data.get("device_name", "").strip()
    ip_address = hash_ip(request.remote_addr)

    if not session_id:
        return jsonify({"valid": False, "error": "Session ID is required"}), 400

    if not device_fingerprint:
        return (
            jsonify(
                {
                    "valid": False,
                    "error": "Device fingerprint is required for security validation",
                }
            ),
            400,
        )

    # Hash the fingerprint for storage
    fingerprint_hash = hash_fingerprint(device_fingerprint)

    # Check rate limit
    if check_rate_limit(session_id, ip_address):
        log_validation_attempt(
            session_id, fingerprint_hash, ip_address, "validate", "rate_limited"
        )
        return (
            jsonify(
                {
                    "valid": False,
                    "error": "Too many validation attempts. Please wait a few minutes.",
                }
            ),
            429,
        )

    # Find the project by session ID
    project = Project.query.filter_by(session_id=session_id).first()

    if not project:
        log_validation_attempt(
            session_id,
            fingerprint_hash,
            ip_address,
            "validate",
            "invalid",
            "Session ID not found",
        )
        return (
            jsonify(
                {
                    "valid": False,
                    "error": "Invalid session code. Please check your code and try again.",
                }
            ),
            404,
        )

    # Check if project is archived/deleted
    if project.status == "archived":
        log_validation_attempt(
            session_id,
            fingerprint_hash,
            ip_address,
            "validate",
            "failed",
            "Project is archived",
        )
        return (
            jsonify(
                {
                    "valid": False,
                    "error": "This session has been archived and is no longer active.",
                }
            ),
            403,
        )

    # FIX M-07/M-08: Use constant-time comparison for fingerprints and
    # lock rows to prevent TOCTOU race on device count and extraction limits
    # HIGH-02 FIX: Use SELECT FOR UPDATE on PostgreSQL to prevent TOCTOU race
    # where concurrent requests both pass the device limit check before either commits.
    from models.database import is_postgresql

    query = SessionActivation.query.filter_by(
        session_id=session_id, status="active"
    )
    if is_postgresql():
        query = query.with_for_update()
    existing_activations = query.all()

    # FIX M-07: Use hmac.compare_digest for constant-time fingerprint comparison
    device_activation = next(
        (
            a
            for a in existing_activations
            if hmac.compare_digest(a.device_fingerprint or "", fingerprint_hash or "")
        ),
        None,
    )

    # HIGH-08 FIX: Update device_name on existing activation if provided
    if device_activation and device_name:
        device_activation.device_name = device_name[:255]

    if not device_activation:
        # New device - check if we've reached the limit
        if len(existing_activations) >= MAX_DEVICES_PER_SESSION:
            log_validation_attempt(
                session_id,
                fingerprint_hash,
                ip_address,
                "validate",
                "failed",
                f"Max devices ({MAX_DEVICES_PER_SESSION}) reached",
            )
            return (
                jsonify(
                    {
                        "valid": False,
                        "error": f"This session is already activated on {MAX_DEVICES_PER_SESSION} devices. "
                        "Please contact support to deactivate old devices.",
                        "max_devices_reached": True,
                        "devices_active": len(existing_activations),
                    }
                ),
                403,
            )

    # FIX M-08: Calculate remaining extractions per-device, not just per-session
    total_extractions = sum(a.extraction_count for a in existing_activations)
    device_extractions = device_activation.extraction_count if device_activation else 0
    remaining = MAX_ACTIVATIONS_PER_SESSION - total_extractions

    # Log successful validation
    log_validation_attempt(
        session_id, fingerprint_hash, ip_address, "validate", "success"
    )

    # Get tier info from the project itself (set when project was created with paid credit)
    tier = project.tier_type
    tier_name = project.get_tier_name()
    transaction_limit = project.transaction_limit
    transactions_used = project.transactions_used
    transactions_remaining = project.get_remaining_transactions()

    return jsonify(
        {
            "valid": True,
            "session_id": session_id,
            "project_name": project.name,
            "client_name": project.client_name,
            "tier": tier,
            "tier_name": tier_name,
            "transaction_limit": transaction_limit,
            "transactions_used": transactions_used,
            "transactions_remaining": (
                transactions_remaining if transactions_remaining != -1 else "unlimited"
            ),
            "is_unlimited": transaction_limit == -1,
            "remaining_extractions": max(0, remaining),
            "is_new_device": device_activation is None,
            "devices_active": len(existing_activations),
        }
    )


def _validate_hardware_fingerprint(data):
    """Validate request data for session activation.

    Extracts and validates session_id / device_fingerprint, checks rate limits,
    and verifies the session exists in the database.

    Returns:
        tuple: (session_id, fingerprint_hash, ip_address, user_agent, device_name, project)
               on success, or (None, error_response) on failure.
    """
    if not data:
        return None, (jsonify({"success": False, "error": "No data provided"}), 400)

    session_id = data.get("session_id", "").strip()
    device_fingerprint = data.get("device_fingerprint", "").strip()
    device_name = data.get("device_name", "Unknown Device").strip()
    ip_address = hash_ip(request.remote_addr)
    user_agent = request.headers.get("User-Agent", "")

    if not session_id or not device_fingerprint:
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": "Session ID and device fingerprint are required",
                }
            ),
            400,
        )

    fingerprint_hash = hash_fingerprint(device_fingerprint)

    # Check rate limit
    if check_rate_limit(session_id, ip_address):
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": "Too many attempts. Please wait a few minutes.",
                }
            ),
            429,
        )

    # Verify session exists
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        log_validation_attempt(
            session_id, fingerprint_hash, ip_address, "activate", "invalid"
        )
        return None, (jsonify({"success": False, "error": "Invalid session code"}), 404)

    return (session_id, fingerprint_hash, ip_address, user_agent, device_name, project), None


def _bind_session(session_id, fingerprint_hash, ip_address, user_agent, device_name):
    """Bind a device to a session using database-level locking.

    Handles race-condition-safe activation: checks for existing activation,
    enforces device limits, and creates new activations under row-level locks.

    Returns:
        tuple: (activation, active_count) on success, or an error response tuple on failure.
    """
    # RACE CONDITION FIX: Use database-level locking to prevent duplicate activations
    from models.database import is_postgresql
    from sqlalchemy import text

    # Lock existing activations for this session to prevent race conditions
    # PostgreSQL uses FOR UPDATE, SQLite has implicit database-level locking
    if is_postgresql():
        locked_activations = db.session.execute(
            text("""
                SELECT id, device_fingerprint, extraction_count, status
                FROM session_activations
                WHERE session_id = :session_id
                FOR UPDATE
            """),
            {"session_id": session_id},
        ).fetchall()
    else:
        locked_activations = db.session.execute(
            text("""
                SELECT id, device_fingerprint, extraction_count, status
                FROM session_activations
                WHERE session_id = :session_id
            """),
            {"session_id": session_id},
        ).fetchall()

    # Check for existing activation for this device
    existing = None
    active_count = 0
    for row in locked_activations:
        if hmac.compare_digest(row.device_fingerprint or "", fingerprint_hash or ""):
            existing = db.session.get(SessionActivation, row.id)
        if row.status == "active":
            active_count += 1

    if existing:
        # Update last used
        existing.last_used_at = datetime.now(timezone.utc)
        existing.status = "active"
        db.session.commit()

        log_validation_attempt(
            session_id,
            fingerprint_hash,
            ip_address,
            "activate",
            "success",
            "Existing activation renewed",
        )

        return None, jsonify(
            {
                "success": True,
                "message": "Device already activated",
                "activation_id": existing.id,
                "extractions_used": existing.extraction_count,
            }
        )

    # Check device limit (with lock held, this is race-safe)
    if active_count >= MAX_DEVICES_PER_SESSION:
        db.session.rollback()  # Release lock
        log_validation_attempt(
            session_id,
            fingerprint_hash,
            ip_address,
            "activate",
            "failed",
            "Device limit reached",
        )
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": f"Maximum of {MAX_DEVICES_PER_SESSION} devices allowed per session",
                }
            ),
            403,
        )

    # Create new activation (still holding lock)
    activation = SessionActivation(
        session_id=session_id,
        device_fingerprint=fingerprint_hash,
        device_name=device_name[:255] if device_name else "Unknown",
        ip_address=ip_address,
        user_agent=user_agent[:500] if user_agent else None,
        status="active",
    )

    db.session.add(activation)
    db.session.commit()

    log_validation_attempt(
        session_id, fingerprint_hash, ip_address, "activate", "success"
    )

    return (activation, active_count), None


def _generate_session_tokens(activation, active_count, project):
    """Finalize session activation and generate the success response.

    Updates the project status from 'pending' to 'active' if needed,
    and returns the activation details.

    Returns:
        Flask JSON response with activation details.
    """
    # Update project status
    if project.status == "pending":
        project.status = "active"
        project.updated_at = datetime.now(timezone.utc)
        db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": "Device activated successfully",
            "activation_id": activation.id,
            "device_number": active_count + 1,
            "max_devices": MAX_DEVICES_PER_SESSION,
        }
    )


@session_validation_bp.route("/activate", methods=["POST"])
@limiter.limit("10 per minute")
def activate_session():
    """
    Activate a session on a new device.
    Must be called after validate() confirms the session is valid.

    Request body:
    {
        "session_id": "FB-20260127123456-ABCD1234",
        "device_fingerprint": "hardware-specific-id",
        "device_name": "John's Workstation" (optional)
    }
    """
    from sqlalchemy.exc import IntegrityError

    data = request.get_json()

    # Validate inputs, rate limit, and look up session
    validated, error_response = _validate_hardware_fingerprint(data)
    if error_response is not None:
        return error_response

    session_id, fingerprint_hash, ip_address, user_agent, device_name, project = validated

    try:
        # Bind device to session with race-condition-safe locking
        bind_result, bind_response = _bind_session(
            session_id, fingerprint_hash, ip_address, user_agent, device_name
        )

        if bind_response is not None:
            # Either an existing-activation renewal or a device-limit error
            return bind_response

        activation, active_count = bind_result

        # Generate final success response and update project status
        return _generate_session_tokens(activation, active_count, project)

    except IntegrityError as e:
        # Unique constraint violation - device was activated by concurrent request
        db.session.rollback()
        logger.warning(f"Concurrent activation detected for session {session_id}: {e}")

        # Fetch the existing activation
        existing = SessionActivation.query.filter_by(
            session_id=session_id, device_fingerprint=fingerprint_hash
        ).first()

        if existing:
            return jsonify(
                {
                    "success": True,
                    "message": "Device already activated (concurrent request)",
                    "activation_id": existing.id,
                    "extractions_used": existing.extraction_count,
                }
            )

        return (
            jsonify(
                {"success": False, "error": "Activation conflict. Please try again."}
            ),
            409,
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Activation failed: {e}")
        return (
            jsonify(
                {"success": False, "error": "Activation failed. Please try again."}
            ),
            500,
        )


def _setup_s3_for_extraction(session_id, fingerprint_hash, ip_address):
    """Validate session and device for extraction, and check all limits.

    Verifies that the session exists, the device is activated, the extraction
    limit has not been reached, and the project's transaction limit is not exhausted.

    Returns:
        tuple: (project, activation, total_extractions, transactions_remaining) on
               success, or (None, error_response) on failure.
    """
    # Verify session and device
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        log_validation_attempt(
            session_id, fingerprint_hash, ip_address, "extract", "invalid"
        )
        return None, (jsonify({"success": False, "error": "Invalid session code"}), 404)

    # Verify device is activated
    activation = SessionActivation.query.filter_by(
        session_id=session_id, device_fingerprint=fingerprint_hash, status="active"
    ).first()

    if not activation:
        log_validation_attempt(
            session_id,
            fingerprint_hash,
            ip_address,
            "extract",
            "failed",
            "Device not activated",
        )
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": "This device is not activated for this session. Please activate first.",
                }
            ),
            403,
        )

    # Check extraction limit per session
    total_extractions = (
        SessionActivation.query.filter_by(session_id=session_id, status="active")
        .with_entities(db.func.sum(SessionActivation.extraction_count))
        .scalar()
        or 0
    )

    if total_extractions >= MAX_ACTIVATIONS_PER_SESSION:
        log_validation_attempt(
            session_id,
            fingerprint_hash,
            ip_address,
            "extract",
            "failed",
            "Extraction limit reached",
        )
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": f"Maximum extractions ({MAX_ACTIVATIONS_PER_SESSION}) reached for this session. "
                    "Please create a new project.",
                    "limit_reached": True,
                }
            ),
            403,
        )

    # Check project's transaction limit (from the paid tier)
    transactions_remaining = project.get_remaining_transactions()
    if transactions_remaining == 0:
        log_validation_attempt(
            session_id,
            fingerprint_hash,
            ip_address,
            "extract",
            "failed",
            "Transaction limit reached",
        )
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": f"Transaction limit ({project.transaction_limit:,}) reached for this session. "
                    f"Used: {project.transactions_used:,}. Please purchase a higher tier.",
                    "transaction_limit_reached": True,
                    "tier": project.tier_type,
                    "transaction_limit": project.transaction_limit,
                    "transactions_used": project.transactions_used,
                }
            ),
            403,
        )

    return (project, activation, total_extractions, transactions_remaining), None


def _generate_extraction_credentials(
    session_id, fingerprint_hash, ip_address, project, activation,
    total_extractions, transactions_remaining
):
    """Generate an extraction token and update activation tracking.

    Creates a cryptographically secure token for chain-of-custody validation
    (CRIT-03 FIX), increments the extraction counter, and commits to the database.

    Returns:
        Flask JSON response with extraction credentials on success,
        or an error response on failure.
    """
    # Generate extraction token (used to complete extraction)
    extraction_token = secrets.token_urlsafe(32)

    # CRIT-03 FIX: Store token in DB so complete_extraction can validate it.
    # This ensures only the caller who started the extraction can complete it,
    # maintaining forensic chain of custody.
    activation.extraction_token = hashlib.sha256(
        extraction_token.encode()
    ).hexdigest()

    # Update activation tracking
    activation.extraction_count += 1
    activation.last_extraction_at = datetime.now(timezone.utc)
    activation.last_used_at = datetime.now(timezone.utc)

    try:
        db.session.commit()

        log_validation_attempt(
            session_id, fingerprint_hash, ip_address, "extract", "success"
        )

        return jsonify(
            {
                "success": True,
                "extraction_token": extraction_token,
                "extraction_number": activation.extraction_count,
                "remaining_extractions": MAX_ACTIVATIONS_PER_SESSION
                - total_extractions
                - 1,
                "tier": project.tier_type,
                "tier_name": project.get_tier_name(),
                "transaction_limit": project.transaction_limit,
                "transactions_used": project.transactions_used,
                "transactions_remaining": (
                    transactions_remaining
                    if transactions_remaining != -1
                    else "unlimited"
                ),
                "is_unlimited": project.transaction_limit == -1,
            }
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Start extraction failed: {e}")
        return jsonify({"success": False, "error": "Failed to start extraction"}), 500


@session_validation_bp.route("/start-extraction", methods=["POST"])
@limiter.limit("10 per minute")
def start_extraction():
    """
    Called when the extractor starts an extraction.
    Validates the session and increments the extraction counter.

    Request body:
    {
        "session_id": "FB-20260127123456-ABCD1234",
        "device_fingerprint": "hardware-specific-id",
        "company_name": "Client Company" (optional, for logging)
    }

    Returns an extraction_token that must be passed to complete-extraction.
    """
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    session_id = data.get("session_id", "").strip()
    device_fingerprint = data.get("device_fingerprint", "").strip()
    ip_address = hash_ip(request.remote_addr)

    if not session_id or not device_fingerprint:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Session ID and device fingerprint are required",
                }
            ),
            400,
        )

    fingerprint_hash = hash_fingerprint(device_fingerprint)

    # Validate session, device activation, and all limits
    setup_result, error_response = _setup_s3_for_extraction(
        session_id, fingerprint_hash, ip_address
    )
    if error_response is not None:
        return error_response

    project, activation, total_extractions, transactions_remaining = setup_result

    # Generate token, update counters, and return credentials
    return _generate_extraction_credentials(
        session_id, fingerprint_hash, ip_address, project, activation,
        total_extractions, transactions_remaining
    )


def _verify_upload_completion(session_id, fingerprint_hash, ip_address,
                              extraction_token, transaction_count):
    """Verify extraction token and transaction limits before completing extraction.

    Validates the chain-of-custody token (CRIT-03 FIX), clears the single-use
    token, looks up the project, and checks whether the transaction count is
    within the tier's remaining limit.

    Returns:
        tuple: (project, activation) on success, or (None, error_response) on failure.
    """
    # CRIT-03 FIX: Validate extraction_token against stored hash.
    # Only the caller who received the token from start_extraction can complete.
    activation = SessionActivation.query.filter_by(
        session_id=session_id, device_fingerprint=fingerprint_hash, status="active"
    ).first()

    if not activation or not activation.extraction_token:
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": "No active extraction found. Call start-extraction first.",
                }
            ),
            403,
        )

    token_hash = hashlib.sha256(extraction_token.encode()).hexdigest()
    if not hmac.compare_digest(token_hash, activation.extraction_token):
        log_validation_attempt(
            session_id, fingerprint_hash, ip_address, "complete", "failed",
            "Invalid extraction token — chain of custody violation"
        )
        return None, (
            jsonify({"success": False, "error": "Invalid extraction token"}),
            403,
        )

    # Clear the token after validation (single-use)
    activation.extraction_token = None

    # Verify session
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return None, (jsonify({"success": False, "error": "Invalid session"}), 404)

    # Check if project can handle this transaction count
    if not project.can_extract_transactions(transaction_count):
        remaining = project.get_remaining_transactions()
        log_validation_attempt(
            session_id,
            fingerprint_hash,
            ip_address,
            "complete",
            "failed",
            f"Transaction limit exceeded: {transaction_count} > {remaining}",
        )
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": f"Transaction count ({transaction_count:,}) exceeds remaining limit ({remaining:,}). "
                    f"Your {project.get_tier_name()} tier allows {project.transaction_limit:,} transactions.",
                    "transaction_count": transaction_count,
                    "transaction_limit": project.transaction_limit,
                    "transactions_used": project.transactions_used,
                    "transactions_remaining": remaining,
                }
            ),
            403,
        )

    return (project, activation), None


def _update_extraction_status(session_id, fingerprint_hash, ip_address,
                               project, transaction_count):
    """Record transactions and update project status after extraction completes.

    Generates a migration ID, records the transaction count against the project,
    marks the project as 'completed' if all transactions are used, and commits.

    Returns:
        Flask JSON response with extraction result.
    """
    # Generate a migration ID for tracking
    migration_id = (
        f"MIG-{session_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )

    # Record the transactions against the project
    if project.record_transactions(transaction_count):
        log_validation_attempt(
            session_id, fingerprint_hash, ip_address, "complete", "success"
        )

        # Update project status if all transactions used
        remaining = project.get_remaining_transactions()
        if remaining == 0:
            project.status = "completed"

        project.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "migration_id": migration_id,
                "tier": project.tier_type,
                "tier_name": project.get_tier_name(),
                "transaction_count": transaction_count,
                "transactions_used": project.transactions_used,
                "transactions_remaining": remaining if remaining != -1 else "unlimited",
                "is_unlimited": project.transaction_limit == -1,
                "message": "Extraction completed successfully",
            }
        )
    else:
        log_validation_attempt(
            session_id,
            fingerprint_hash,
            ip_address,
            "complete",
            "failed",
            "Transaction recording failed",
        )
        return (
            jsonify({"success": False, "error": "Failed to record transactions"}),
            500,
        )


@session_validation_bp.route("/complete-extraction", methods=["POST"])
@limiter.limit("10 per minute")
def complete_extraction():
    """
    Called when extraction completes successfully.
    Records the transaction count against the project's tier limit.

    Request body:
    {
        "session_id": "FB-20260127123456-ABCD1234",
        "device_fingerprint": "hardware-specific-id",
        "extraction_token": "token-from-start-extraction",
        "transaction_count": 5000,
        "company_name": "Client Company",
        "qb_version": "Enterprise 2024"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    session_id = data.get("session_id", "").strip()
    device_fingerprint = data.get("device_fingerprint", "").strip()
    extraction_token = data.get("extraction_token", "").strip()
    transaction_count = data.get("transaction_count")
    if transaction_count is not None:
        try:
            transaction_count = int(transaction_count)
            if transaction_count < 0 or transaction_count > 10000000:
                return jsonify({"error": "Invalid transaction count"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid transaction count format"}), 400
    else:
        transaction_count = 0
    ip_address = hash_ip(request.remote_addr)

    if not session_id or not device_fingerprint:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Session ID and device fingerprint are required",
                }
            ),
            400,
        )

    # CRIT-03 FIX: Require extraction_token for chain-of-custody validation
    if not extraction_token:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Extraction token is required. Call start-extraction first.",
                }
            ),
            400,
        )

    fingerprint_hash = hash_fingerprint(device_fingerprint)

    # Verify extraction token chain-of-custody and transaction limits
    verified, error_response = _verify_upload_completion(
        session_id, fingerprint_hash, ip_address, extraction_token, transaction_count
    )
    if error_response is not None:
        return error_response

    project, activation = verified

    # Record transactions and finalize extraction status
    return _update_extraction_status(
        session_id, fingerprint_hash, ip_address, project, transaction_count
    )


@session_validation_bp.route("/status/<session_id>", methods=["GET"])
def session_status(session_id):
    """
    Get the current status of a session.

    SECURITY: This endpoint requires authentication to prevent information disclosure.
    Exposes project names, client names, and tier information.
    """
    # SECURITY FIX: Require authentication for session status
    from flask_login import current_user

    if not current_user.is_authenticated:
        return (
            jsonify(
                {
                    "error": "Authentication required",
                    "message": "Please log in to view session status",
                }
            ),
            401,
        )
    project = Project.query.filter_by(session_id=session_id).first()

    if not project:
        return jsonify({"found": False, "error": "Session not found"}), 404

    # Get activation stats
    activations = SessionActivation.query.filter_by(
        session_id=session_id, status="active"
    ).all()

    total_extractions = sum(a.extraction_count for a in activations)

    transactions_remaining = project.get_remaining_transactions()

    return jsonify(
        {
            "found": True,
            "session_id": session_id,
            "project_name": project.name,
            "client_name": project.client_name,
            "status": project.status,
            "tier": project.tier_type,
            "tier_name": project.get_tier_name(),
            "transaction_limit": project.transaction_limit,
            "transactions_used": project.transactions_used,
            "transactions_remaining": (
                transactions_remaining if transactions_remaining != -1 else "unlimited"
            ),
            "is_unlimited": project.transaction_limit == -1,
            "devices_active": len(activations),
            "max_devices": MAX_DEVICES_PER_SESSION,
            "extractions_used": total_extractions,
            "max_extractions": MAX_ACTIVATIONS_PER_SESSION,
            "created_at": project.created_at.isoformat(),
        }
    )
