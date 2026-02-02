from datetime import timezone
"""
Internal API Endpoints

CRIT-09 FIX: Secure internal API endpoints for Lambda and service-to-service communication.

These endpoints are NOT for public use. They are authenticated via:
1. X-Internal-API-Key header (secret shared with Lambda)
2. X-Lambda-Source header (identifies the calling Lambda function)

SECURITY: These endpoints should NEVER be exposed to the public internet.
Use VPC, security groups, or API Gateway with IAM auth in production.
"""

from functools import wraps
import logging
import os

from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger(__name__)

internal_bp = Blueprint('internal', __name__, url_prefix='/api/internal')


def require_internal_auth(f):
    """
    CRIT-09 FIX: Decorator to require internal API authentication.

    Validates:
    1. X-Internal-API-Key header matches configured key
    2. X-Lambda-Source header is present (optional validation)

    Returns 401 if authentication fails.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get the expected API key from environment/config
        expected_key = os.environ.get('INTERNAL_API_KEY') or current_app.config.get('INTERNAL_API_KEY')

        if not expected_key:
            logger.error("INTERNAL_API_KEY not configured - rejecting all internal API requests")
            return jsonify({
                'success': False,
                'error': 'Internal API not configured'
            }), 500

        # Validate the API key
        provided_key = request.headers.get('X-Internal-API-Key')

        if not provided_key:
            logger.warning(f"Internal API call without API key from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Authentication required'
            }), 401

        # Constant-time comparison to prevent timing attacks
        import hmac
        if not hmac.compare_digest(provided_key, expected_key):
            logger.warning(f"Invalid internal API key from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Invalid authentication'
            }), 401

        # Log the Lambda source for audit trail
        lambda_source = request.headers.get('X-Lambda-Source', 'unknown')
        logger.info(f"Authenticated internal API call from {lambda_source}")

        return f(*args, **kwargs)
    return decorated_function


@internal_bp.route('/trigger-processing', methods=['POST'])
@require_internal_auth
def trigger_processing():
    """
    Trigger migration processing after S3 upload.

    Called by Lambda when an encrypted file is uploaded to S3.

    Request:
    {
        "session_id": "uuid",
        "s3_bucket": "bucket-name",
        "s3_key": "path/to/file"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({
            'success': False,
            'error': 'No data provided'
        }), 400

    session_id = data.get('session_id')
    s3_bucket = data.get('s3_bucket')
    s3_key = data.get('s3_key')

    if not session_id or not s3_bucket or not s3_key:
        return jsonify({
            'success': False,
            'error': 'Missing required fields: session_id, s3_bucket, s3_key'
        }), 400

    logger.info(f"Processing triggered for session {session_id}, bucket: {s3_bucket}, key: {s3_key}")

    try:
        # Find the migration by session_id
        from models.migration import Migration
        from models.database import db
        import re

        # SECURITY FIX: Validate session_id format (UUID) to prevent injection
        uuid_pattern = r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$'
        if not re.match(uuid_pattern, session_id):
            logger.warning(f"Invalid session_id format from internal API: {session_id[:50]}")
            return jsonify({
                'success': False,
                'error': 'Invalid session_id format'
            }), 400

        # SECURITY FIX: Validate s3_key doesn't contain path traversal
        if '..' in s3_key or s3_key.startswith('/'):
            logger.warning(f"Invalid s3_key from internal API: {s3_key[:100]}")
            return jsonify({
                'success': False,
                'error': 'Invalid s3_key format'
            }), 400

        migration = Migration.query.filter_by(migration_id=session_id).first()

        if not migration:
            # Session ID might be in a different format - use parameterized query
            migration = Migration.query.filter(
                Migration.s3_key == s3_key
            ).first()

        if not migration:
            logger.warning(f"Migration not found for session {session_id}")
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404

        # AUTHORIZATION FIX: Verify migration is in expected state
        # Only pending/uploading migrations can be triggered
        if migration.status not in ['pending', 'uploading']:
            logger.warning(f"Migration {session_id} in unexpected state {migration.status} for trigger")
            return jsonify({
                'success': False,
                'error': f'Migration cannot be triggered from state: {migration.status}'
            }), 400

        # Update migration with S3 details if not already set
        if not migration.s3_bucket:
            migration.s3_bucket = s3_bucket
            migration.s3_key = s3_key
            migration.s3_uri = f"s3://{s3_bucket}/{s3_key}"

        # Mark as uploaded if still pending/uploading
        if migration.status in ['pending', 'uploading']:
            migration.status = 'uploaded'
            migration.current_step = 'File received, queued for processing'

        db.session.commit()

        logger.info(f"Migration {migration.migration_id} updated, status: {migration.status}")

        return jsonify({
            'success': True,
            'migration_id': migration.migration_id,
            'status': migration.status
        }), 200

    except Exception as e:
        logger.error(f"Error processing trigger for session {session_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal processing error'
        }), 500


@internal_bp.route('/health', methods=['GET'])
def internal_health():
    """
    Health check endpoint for internal services.

    This endpoint does NOT require authentication (for load balancer health checks).
    """
    return jsonify({
        'status': 'healthy',
        'service': 'forensicbridge-internal-api',
        'timestamp': __import__('datetime').datetime.now(timezone.utc).isoformat()
    }), 200


@internal_bp.route('/cleanup-expired', methods=['POST'])
@require_internal_auth
def cleanup_expired():
    """
    Trigger cleanup of expired resources.

    Called by scheduled Lambda or CloudWatch Events.
    """
    try:
        from models.team_invite import TeamInvite
        from models.migration_credit import MigrationCredit

        results = {}

        # Cleanup expired team invites
        expired_invites = TeamInvite.cleanup_expired()
        results['expired_invites'] = expired_invites

        # Cleanup expired credits
        expired_credits = MigrationCredit.cleanup_expired()
        results['expired_credits'] = expired_credits

        logger.info(f"Cleanup completed: {results}")

        return jsonify({
            'success': True,
            'results': results
        }), 200

    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Cleanup failed'
        }), 500
