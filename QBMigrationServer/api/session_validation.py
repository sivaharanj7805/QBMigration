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

import os
import logging
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, current_app

from models.database import db
from models.project import Project
from models.migration_credit import MigrationCredit

logger = logging.getLogger(__name__)

session_validation_bp = Blueprint('session_validation', __name__, url_prefix='/api/session')

# Configuration
MAX_DEVICES_PER_SESSION = int(os.getenv('MAX_DEVICES_PER_SESSION', '2'))  # Allow 2 devices max
MAX_ACTIVATIONS_PER_SESSION = int(os.getenv('MAX_ACTIVATIONS_PER_SESSION', '5'))  # Max 5 activations
RATE_LIMIT_WINDOW_MINUTES = 5
RATE_LIMIT_MAX_ATTEMPTS = 10


class SessionActivation(db.Model):
    """Tracks session activations for fraud prevention"""
    __tablename__ = 'session_activations'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), nullable=False, index=True)
    device_fingerprint = db.Column(db.String(64), nullable=False)
    device_name = db.Column(db.String(255))  # Optional friendly name
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))

    # Activation status
    status = db.Column(db.String(50), default='active')  # active, revoked, expired
    activated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Usage tracking
    extraction_count = db.Column(db.Integer, default=0)
    last_extraction_at = db.Column(db.DateTime)

    __table_args__ = (
        db.Index('idx_session_device', 'session_id', 'device_fingerprint'),
        db.UniqueConstraint('session_id', 'device_fingerprint', name='uq_session_device'),
    )


class SessionValidationLog(db.Model):
    """Audit log for validation attempts"""
    __tablename__ = 'session_validation_logs'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), index=True)
    device_fingerprint = db.Column(db.String(64))
    ip_address = db.Column(db.String(50))
    action = db.Column(db.String(50))  # validate, activate, extract, reject
    result = db.Column(db.String(50))  # success, failed, rate_limited, invalid
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


def log_validation_attempt(session_id, device_fingerprint, ip_address, action, result, error=None):
    """Log a validation attempt for audit purposes"""
    try:
        log = SessionValidationLog(
            session_id=session_id,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            action=action,
            result=result,
            error_message=error
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log validation attempt: {e}")


def check_rate_limit(session_id, ip_address):
    """Check if the request is rate limited"""
    window_start = datetime.now(timezone.utc) - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)

    attempt_count = SessionValidationLog.query.filter(
        SessionValidationLog.session_id == session_id,
        SessionValidationLog.ip_address == ip_address,
        SessionValidationLog.created_at >= window_start
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
    import hmac
    from flask import current_app
    secret = current_app.config['SECRET_KEY'].encode()
    return hmac.new(secret, fingerprint.encode(), hashlib.sha256).hexdigest()


@session_validation_bp.route('/validate', methods=['POST'])
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
        return jsonify({
            'valid': False,
            'error': 'No data provided'
        }), 400

    session_id = data.get('session_id', '').strip()
    device_fingerprint = data.get('device_fingerprint', '').strip()
    device_name = data.get('device_name', '').strip()
    ip_address = request.remote_addr

    if not session_id:
        return jsonify({
            'valid': False,
            'error': 'Session ID is required'
        }), 400

    if not device_fingerprint:
        return jsonify({
            'valid': False,
            'error': 'Device fingerprint is required for security validation'
        }), 400

    # Hash the fingerprint for storage
    fingerprint_hash = hash_fingerprint(device_fingerprint)

    # Check rate limit
    if check_rate_limit(session_id, ip_address):
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'validate', 'rate_limited')
        return jsonify({
            'valid': False,
            'error': 'Too many validation attempts. Please wait a few minutes.'
        }), 429

    # Find the project by session ID
    project = Project.query.filter_by(session_id=session_id).first()

    if not project:
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'validate', 'invalid',
                              'Session ID not found')
        return jsonify({
            'valid': False,
            'error': 'Invalid session code. Please check your code and try again.'
        }), 404

    # Check if project is archived/deleted
    if project.status == 'archived':
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'validate', 'failed',
                              'Project is archived')
        return jsonify({
            'valid': False,
            'error': 'This session has been archived and is no longer active.'
        }), 403

    # Check device activation count
    existing_activations = SessionActivation.query.filter_by(
        session_id=session_id,
        status='active'
    ).all()

    # Check if this device is already activated
    device_activation = next(
        (a for a in existing_activations if a.device_fingerprint == fingerprint_hash),
        None
    )

    if not device_activation:
        # New device - check if we've reached the limit
        if len(existing_activations) >= MAX_DEVICES_PER_SESSION:
            log_validation_attempt(session_id, fingerprint_hash, ip_address, 'validate', 'failed',
                                  f'Max devices ({MAX_DEVICES_PER_SESSION}) reached')
            return jsonify({
                'valid': False,
                'error': f'This session is already activated on {MAX_DEVICES_PER_SESSION} devices. '
                         'Please contact support to deactivate old devices.',
                'max_devices_reached': True,
                'devices_active': len(existing_activations)
            }), 403

    # Calculate remaining extractions for this session
    total_extractions = sum(a.extraction_count for a in existing_activations)
    remaining = MAX_ACTIVATIONS_PER_SESSION - total_extractions

    # Log successful validation
    log_validation_attempt(session_id, fingerprint_hash, ip_address, 'validate', 'success')

    # Get tier info from the project itself (set when project was created with paid credit)
    tier = project.tier_type
    tier_name = project.get_tier_name()
    transaction_limit = project.transaction_limit
    transactions_used = project.transactions_used
    transactions_remaining = project.get_remaining_transactions()

    return jsonify({
        'valid': True,
        'session_id': session_id,
        'project_name': project.name,
        'client_name': project.client_name,
        'tier': tier,
        'tier_name': tier_name,
        'transaction_limit': transaction_limit,
        'transactions_used': transactions_used,
        'transactions_remaining': transactions_remaining if transactions_remaining != -1 else 'unlimited',
        'is_unlimited': transaction_limit == -1,
        'remaining_extractions': max(0, remaining),
        'is_new_device': device_activation is None,
        'devices_active': len(existing_activations)
    })


@session_validation_bp.route('/activate', methods=['POST'])
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
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    session_id = data.get('session_id', '').strip()
    device_fingerprint = data.get('device_fingerprint', '').strip()
    device_name = data.get('device_name', 'Unknown Device').strip()
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')

    if not session_id or not device_fingerprint:
        return jsonify({
            'success': False,
            'error': 'Session ID and device fingerprint are required'
        }), 400

    fingerprint_hash = hash_fingerprint(device_fingerprint)

    # Check rate limit
    if check_rate_limit(session_id, ip_address):
        return jsonify({
            'success': False,
            'error': 'Too many attempts. Please wait a few minutes.'
        }), 429

    # Verify session exists
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'activate', 'invalid')
        return jsonify({
            'success': False,
            'error': 'Invalid session code'
        }), 404

    # RACE CONDITION FIX: Use database-level locking to prevent duplicate activations
    # This ensures that concurrent requests don't both pass the device limit check
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from models.database import is_postgresql

    try:
        # Lock existing activations for this session to prevent race conditions
        # This ensures only one request can check and create at a time
        # PostgreSQL uses FOR UPDATE, SQLite has implicit database-level locking
        if is_postgresql():
            locked_activations = db.session.execute(
                text("""
                    SELECT id, device_fingerprint, extraction_count, status
                    FROM session_activations
                    WHERE session_id = :session_id
                    FOR UPDATE
                """),
                {"session_id": session_id}
            ).fetchall()
        else:
            locked_activations = db.session.execute(
                text("""
                    SELECT id, device_fingerprint, extraction_count, status
                    FROM session_activations
                    WHERE session_id = :session_id
                """),
                {"session_id": session_id}
            ).fetchall()

        # Check for existing activation for this device
        existing = None
        active_count = 0
        for row in locked_activations:
            if row.device_fingerprint == fingerprint_hash:
                existing = db.session.get(SessionActivation, row.id)
            if row.status == 'active':
                active_count += 1

        if existing:
            # Update last used
            existing.last_used_at = datetime.now(timezone.utc)
            existing.status = 'active'
            db.session.commit()

            log_validation_attempt(session_id, fingerprint_hash, ip_address, 'activate', 'success',
                                  'Existing activation renewed')

            return jsonify({
                'success': True,
                'message': 'Device already activated',
                'activation_id': existing.id,
                'extractions_used': existing.extraction_count
            })

        # Check device limit (with lock held, this is race-safe)
        if active_count >= MAX_DEVICES_PER_SESSION:
            db.session.rollback()  # Release lock
            log_validation_attempt(session_id, fingerprint_hash, ip_address, 'activate', 'failed',
                                  'Device limit reached')
            return jsonify({
                'success': False,
                'error': f'Maximum of {MAX_DEVICES_PER_SESSION} devices allowed per session'
            }), 403

        # Create new activation (still holding lock)
        activation = SessionActivation(
            session_id=session_id,
            device_fingerprint=fingerprint_hash,
            device_name=device_name[:255] if device_name else 'Unknown',
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
            status='active'
        )

        db.session.add(activation)
        db.session.commit()

        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'activate', 'success')

        # Update project status
        if project.status == 'pending':
            project.status = 'active'
            project.updated_at = datetime.now(timezone.utc)
            db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Device activated successfully',
            'activation_id': activation.id,
            'device_number': active_count + 1,
            'max_devices': MAX_DEVICES_PER_SESSION
        })

    except IntegrityError as e:
        # Unique constraint violation - device was activated by concurrent request
        db.session.rollback()
        logger.warning(f"Concurrent activation detected for session {session_id}: {e}")

        # Fetch the existing activation
        existing = SessionActivation.query.filter_by(
            session_id=session_id,
            device_fingerprint=fingerprint_hash
        ).first()

        if existing:
            return jsonify({
                'success': True,
                'message': 'Device already activated (concurrent request)',
                'activation_id': existing.id,
                'extractions_used': existing.extraction_count
            })

        return jsonify({
            'success': False,
            'error': 'Activation conflict. Please try again.'
        }), 409

    except Exception as e:
        db.session.rollback()
        logger.error(f"Activation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Activation failed. Please try again.'
        }), 500


@session_validation_bp.route('/start-extraction', methods=['POST'])
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
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    session_id = data.get('session_id', '').strip()
    device_fingerprint = data.get('device_fingerprint', '').strip()
    company_name = data.get('company_name', '')
    ip_address = request.remote_addr

    if not session_id or not device_fingerprint:
        return jsonify({
            'success': False,
            'error': 'Session ID and device fingerprint are required'
        }), 400

    fingerprint_hash = hash_fingerprint(device_fingerprint)

    # Verify session and device
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'extract', 'invalid')
        return jsonify({
            'success': False,
            'error': 'Invalid session code'
        }), 404

    # Verify device is activated
    activation = SessionActivation.query.filter_by(
        session_id=session_id,
        device_fingerprint=fingerprint_hash,
        status='active'
    ).first()

    if not activation:
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'extract', 'failed',
                              'Device not activated')
        return jsonify({
            'success': False,
            'error': 'This device is not activated for this session. Please activate first.'
        }), 403

    # Check extraction limit per session
    total_extractions = SessionActivation.query.filter_by(
        session_id=session_id,
        status='active'
    ).with_entities(db.func.sum(SessionActivation.extraction_count)).scalar() or 0

    if total_extractions >= MAX_ACTIVATIONS_PER_SESSION:
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'extract', 'failed',
                              'Extraction limit reached')
        return jsonify({
            'success': False,
            'error': f'Maximum extractions ({MAX_ACTIVATIONS_PER_SESSION}) reached for this session. '
                     'Please create a new project.',
            'limit_reached': True
        }), 403

    # Check project's transaction limit (from the paid tier)
    transactions_remaining = project.get_remaining_transactions()
    if transactions_remaining == 0:
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'extract', 'failed',
                              'Transaction limit reached')
        return jsonify({
            'success': False,
            'error': f'Transaction limit ({project.transaction_limit:,}) reached for this session. '
                     f'Used: {project.transactions_used:,}. Please purchase a higher tier.',
            'transaction_limit_reached': True,
            'tier': project.tier_type,
            'transaction_limit': project.transaction_limit,
            'transactions_used': project.transactions_used
        }), 403

    # Generate extraction token and store its hash for verification
    # at complete-extraction time. This prevents replay attacks where
    # a stolen token could be used to record fraudulent transaction counts.
    extraction_token = secrets.token_urlsafe(32)
    extraction_token_hash = hashlib.sha256(extraction_token.encode()).hexdigest()

    # Store the token hash on the activation record for later verification
    activation.extraction_count += 1
    activation.last_extraction_at = datetime.now(timezone.utc)
    activation.last_used_at = datetime.now(timezone.utc)

    # Store token hash as a simple attribute for verification
    # Using a dedicated field would require a migration; use a JSON-safe approach
    if not hasattr(activation, '_pending_extraction_tokens'):
        activation._pending_extraction_tokens = {}

    # Store in database via a simple column update
    # We store the hash in the device_name suffix temporarily - not ideal but avoids migration
    # Better: Add an extraction_token_hash column in next migration
    try:
        # Store token hash in the session validation log for verification
        token_log = SessionValidationLog(
            session_id=session_id,
            device_fingerprint=fingerprint_hash,
            ip_address=ip_address,
            action='extraction_token',
            result=extraction_token_hash,
            error_message=None
        )
        db.session.add(token_log)
        db.session.commit()

        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'extract', 'success')

        return jsonify({
            'success': True,
            'extraction_token': extraction_token,
            'extraction_number': activation.extraction_count,
            'remaining_extractions': MAX_ACTIVATIONS_PER_SESSION - total_extractions - 1,
            'tier': project.tier_type,
            'tier_name': project.get_tier_name(),
            'transaction_limit': project.transaction_limit,
            'transactions_used': project.transactions_used,
            'transactions_remaining': transactions_remaining if transactions_remaining != -1 else 'unlimited',
            'is_unlimited': project.transaction_limit == -1
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Start extraction failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to start extraction'
        }), 500


@session_validation_bp.route('/complete-extraction', methods=['POST'])
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
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    session_id = data.get('session_id', '').strip()
    device_fingerprint = data.get('device_fingerprint', '').strip()
    extraction_token = data.get('extraction_token', '').strip()
    transaction_count = data.get('transaction_count', 0)
    company_name = data.get('company_name', '')
    qb_version = data.get('qb_version', '')
    ip_address = request.remote_addr

    if not session_id or not device_fingerprint:
        return jsonify({
            'success': False,
            'error': 'Session ID and device fingerprint are required'
        }), 400

    # SECURITY FIX: Verify extraction token to prevent unauthorized completions
    if not extraction_token:
        return jsonify({
            'success': False,
            'error': 'Extraction token is required (from start-extraction response)'
        }), 400

    fingerprint_hash = hash_fingerprint(device_fingerprint)

    # Verify the extraction token matches one issued by start-extraction
    token_hash = hashlib.sha256(extraction_token.encode()).hexdigest()
    token_log = SessionValidationLog.query.filter_by(
        session_id=session_id,
        device_fingerprint=fingerprint_hash,
        action='extraction_token',
        result=token_hash
    ).first()

    if not token_log:
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'complete', 'failed',
                              'Invalid or expired extraction token')
        return jsonify({
            'success': False,
            'error': 'Invalid extraction token. Please start a new extraction.'
        }), 403

    # Delete the token log to prevent replay attacks (one-time use)
    db.session.delete(token_log)

    # Verify session
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return jsonify({
            'success': False,
            'error': 'Invalid session'
        }), 404

    # Check if project can handle this transaction count
    if not project.can_extract_transactions(transaction_count):
        remaining = project.get_remaining_transactions()
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'complete', 'failed',
                              f'Transaction limit exceeded: {transaction_count} > {remaining}')
        return jsonify({
            'success': False,
            'error': f'Transaction count ({transaction_count:,}) exceeds remaining limit ({remaining:,}). '
                     f'Your {project.get_tier_name()} tier allows {project.transaction_limit:,} transactions.',
            'transaction_count': transaction_count,
            'transaction_limit': project.transaction_limit,
            'transactions_used': project.transactions_used,
            'transactions_remaining': remaining
        }), 403

    # Generate a migration ID for tracking
    migration_id = f"MIG-{session_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    # Record the transactions against the project
    if project.record_transactions(transaction_count):
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'complete', 'success')

        # Update project status if all transactions used
        remaining = project.get_remaining_transactions()
        if remaining == 0:
            project.status = 'completed'

        project.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({
            'success': True,
            'migration_id': migration_id,
            'tier': project.tier_type,
            'tier_name': project.get_tier_name(),
            'transaction_count': transaction_count,
            'transactions_used': project.transactions_used,
            'transactions_remaining': remaining if remaining != -1 else 'unlimited',
            'is_unlimited': project.transaction_limit == -1,
            'message': 'Extraction completed successfully'
        })
    else:
        log_validation_attempt(session_id, fingerprint_hash, ip_address, 'complete', 'failed',
                              'Transaction recording failed')
        return jsonify({
            'success': False,
            'error': 'Failed to record transactions'
        }), 500


@session_validation_bp.route('/status/<session_id>', methods=['GET'])
def session_status(session_id):
    """
    Get the current status of a session.

    SECURITY: This endpoint requires authentication to prevent information disclosure.
    Exposes project names, client names, and tier information.
    """
    # SECURITY FIX: Require authentication for session status
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({
            'error': 'Authentication required',
            'message': 'Please log in to view session status'
        }), 401
    project = Project.query.filter_by(session_id=session_id).first()

    if not project:
        return jsonify({
            'found': False,
            'error': 'Session not found'
        }), 404

    # Get activation stats
    activations = SessionActivation.query.filter_by(
        session_id=session_id,
        status='active'
    ).all()

    total_extractions = sum(a.extraction_count for a in activations)

    transactions_remaining = project.get_remaining_transactions()

    return jsonify({
        'found': True,
        'session_id': session_id,
        'project_name': project.name,
        'client_name': project.client_name,
        'status': project.status,
        'tier': project.tier_type,
        'tier_name': project.get_tier_name(),
        'transaction_limit': project.transaction_limit,
        'transactions_used': project.transactions_used,
        'transactions_remaining': transactions_remaining if transactions_remaining != -1 else 'unlimited',
        'is_unlimited': project.transaction_limit == -1,
        'devices_active': len(activations),
        'max_devices': MAX_DEVICES_PER_SESSION,
        'extractions_used': total_extractions,
        'max_extractions': MAX_ACTIVATIONS_PER_SESSION,
        'created_at': project.created_at.isoformat()
    })
