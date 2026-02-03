from flask import Blueprint, request, jsonify, current_app
from models.database import db
from models.migration import Migration
from models.user import User
from utils.aws_manager import AWSMigrationManager
from extensions import limiter
from api.auth import require_auth
import logging
import re

migrations_bp = Blueprint('migrations', __name__)
logger = logging.getLogger(__name__)


def _get_current_user_id():
    """Get current user ID from require_auth decorator (request.current_user)."""
    return int(request.current_user['user_id'])


# HIGH-07 FIX: UUID format validation for migration IDs
def validate_migration_id(migration_id: str) -> bool:
    """
    Validate migration ID is a valid UUID format.

    HIGH-07 FIX: Prevents unnecessary database queries for malformed IDs
    and provides defense in depth against injection attacks.

    Args:
        migration_id: The migration ID to validate

    Returns:
        True if valid UUID format, False otherwise
    """
    if not migration_id or not isinstance(migration_id, str):
        return False

    # UUID format: 8-4-4-4-12 hexadecimal characters
    uuid_pattern = r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$'
    return bool(re.match(uuid_pattern, migration_id))


# FIX #42: SQL injection prevention helpers
def validate_pagination_param(value, param_name, default, min_val, max_val):
    """
    Validate pagination parameter with comprehensive SQL injection prevention.

    Args:
        value: The parameter value (may be string or int)
        param_name: Parameter name for error messages
        default: Default value if validation fails
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Validated integer value

    Raises:
        ValueError: If value contains SQL injection patterns
    """
    # If None, return default
    if value is None:
        return default

    # Convert to string for regex validation
    value_str = str(value).strip()

    # FIX #42: Regex validation - must be pure integer
    # Prevents SQL injection via malformed integers like "1; DROP TABLE"
    if not re.match(r'^\d+$', value_str):
        logger.warning(f"Invalid {param_name} parameter format: {value_str[:50]}")
        return default

    # Convert to integer
    try:
        value_int = int(value_str)
    except (ValueError, OverflowError):
        logger.warning(f"Failed to convert {param_name} to integer: {value_str[:50]}")
        return default

    # Range validation
    if value_int < min_val or value_int > max_val:
        logger.warning(f"{param_name} out of range: {value_int} (allowed: {min_val}-{max_val})")
        return default

    return value_int


@migrations_bp.route('/api/migrations', methods=['POST'])
@limiter.limit("10 per minute")
@require_auth
def create_migration():
    """
    Create a new migration from previously uploaded/validated files.

    Request Body:
        {
            "destination": "qbo" | "caseware",
            "files": ["file1.qbw", "file2.csv"]
        }

    Returns:
        201: {success, migration_id}
        400: Invalid input
    """
    import uuid

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        destination = data.get('destination', 'qbo')
        files = data.get('files', [])

        if destination not in ('qbo', 'caseware'):
            return jsonify({
                'success': False,
                'error': 'destination must be "qbo" or "caseware"'
            }), 400

        if not files:
            return jsonify({
                'success': False,
                'error': 'At least one file is required'
            }), 400

        user_id = _get_current_user_id()
        migration_id = str(uuid.uuid4())

        # Use first file name as company name hint
        company_name = files[0].rsplit('.', 1)[0] if files else 'Unknown Company'

        migration = Migration(
            migration_id=migration_id,
            user_id=user_id,
            company_name=company_name,
            qb_file_name=files[0] if files else '',
            status='pending',
            destination=destination,
        )
        db.session.add(migration)
        db.session.commit()

        logger.info(f"Created migration {migration_id} for user {user_id}, destination: {destination}")

        return jsonify({
            'success': True,
            'migration_id': migration_id,
            'status': 'pending'
        }), 201

    except Exception as e:
        logger.exception(f"Failed to create migration: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to create migration'
        }), 500


@migrations_bp.route('/api/migrations', methods=['GET'])
@require_auth
def list_migrations():
    """
    List migrations for current user with pagination support.

    Query Parameters:
        page (int): Page number (default: 1)
        per_page (int): Items per page (default: 50, max: 100)
        status (str): Filter by status (optional)
    """
    try:
        # FIX #42: Enhanced SQL injection prevention for pagination
        # Use regex validation to ensure parameters are pure integers
        page = validate_pagination_param(
            request.args.get('page'),
            param_name='page',
            default=1,
            min_val=1,
            max_val=10000
        )

        per_page = validate_pagination_param(
            request.args.get('per_page'),
            param_name='per_page',
            default=50,
            min_val=1,
            max_val=100
        )

        status_filter = request.args.get('status', None, type=str)

        # FIX #42: Whitelist validation for status filter
        ALLOWED_STATUSES = ['pending', 'uploading', 'processing', 'completed', 'failed', 'cancelled']
        if status_filter:
            # Strip whitespace and convert to lowercase for comparison
            status_filter = status_filter.strip().lower()

            # Validate against whitelist
            if status_filter not in ALLOWED_STATUSES:
                logger.warning(f"Invalid status filter attempted: {status_filter[:50]}")
                return jsonify({
                    'success': False,
                    'error': f'Invalid status filter. Allowed values: {", ".join(ALLOWED_STATUSES)}'
                }), 400

            # Additional regex check: only allow alphanumeric and underscore
            if not re.match(r'^[a-z_]+$', status_filter):
                logger.warning(f"Status filter contains invalid characters: {status_filter[:50]}")
                return jsonify({
                    'success': False,
                    'error': 'Invalid status filter format'
                }), 400

        # Build query
        query = Migration.query.filter_by(user_id=_get_current_user_id())

        # Apply status filter if provided
        if status_filter:
            query = query.filter_by(status=status_filter)

        # Order by creation date (newest first)
        query = query.order_by(Migration.created_at.desc())

        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # Serialize migrations properly (handle missing fields)
        migrations_data = []
        for migration in pagination.items:
            migration_dict = {
                'id': migration.id,
                'migration_id': migration.migration_id,
                'status': migration.status,
                'company_name': migration.company_name,
                'qb_file_name': migration.qb_file_name,
                'progress_percent': migration.progress_percent,
                'created_at': migration.created_at.isoformat() if migration.created_at else None,
                'completed_at': migration.completed_at.isoformat() if migration.completed_at else None,
                's3_uri': migration.s3_uri
            }

            # Add optional fields only if they exist
            if hasattr(migration, 'error_message'):
                migration_dict['error_message'] = migration.error_message
            if hasattr(migration, 'updated_at') and migration.updated_at:
                migration_dict['updated_at'] = migration.updated_at.isoformat()

            migrations_data.append(migration_dict)

        return jsonify({
            'success': True,
            'migrations': migrations_data,
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total_pages': pagination.pages,
                'total_items': pagination.total,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            },
            # Legacy compatibility
            'count': len(migrations_data)
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to list migrations: {str(e)}")
        # SECURITY FIX: Clean up database session on error
        db.session.rollback()
        db.session.remove()
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve migrations'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>', methods=['GET'])
@require_auth
def get_migration(migration_id):
    """
    Get specific migration details

    Args:
        migration_id: Migration ID

    Returns:
        200: Migration details
        400: Invalid migration ID format
        404: Migration not found
        500: Server error
    """
    # HIGH-07 FIX: Validate UUID format before database query
    if not validate_migration_id(migration_id):
        logger.warning(f"Invalid migration ID format: {migration_id[:50] if migration_id else 'None'}")
        return jsonify({
            'success': False,
            'error': 'Invalid migration ID format'
        }), 400

    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=_get_current_user_id()
        ).first()
        
        if not migration:
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404
        
        # Use to_dict if available
        if hasattr(migration, 'to_dict') and callable(migration.to_dict):
            migration_data = migration.to_dict()
        else:
            migration_data = {
                'id': migration.id,
                'migration_id': migration.migration_id,
                'status': migration.status,
                'company_name': migration.company_name,
                'qb_file_name': migration.qb_file_name,
                'progress_percent': migration.progress_percent or 0,
                'created_at': migration.created_at.isoformat() if migration.created_at else None,
                's3_uri': migration.s3_uri
            }
        
        return jsonify({
            'success': True,
            'migration': migration_data
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get migration {migration_id}: {str(e)}")
        # SECURITY FIX: Clean up database session on error
        db.session.rollback()
        db.session.remove()
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve migration'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>/status', methods=['GET'])
@require_auth
def get_migration_status(migration_id):
    """
    Get migration status (lightweight endpoint for polling)

    Args:
        migration_id: Migration ID

    Returns:
        200: Migration status
        400: Invalid migration ID format
        404: Migration not found
        500: Server error
    """
    # HIGH-07 FIX: Validate UUID format before database query
    if not validate_migration_id(migration_id):
        return jsonify({
            'success': False,
            'error': 'Invalid migration ID format'
        }), 400

    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=_get_current_user_id()
        ).first()
        
        if not migration:
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404
        
        status_data = {
            'success': True,
            'migration_id': migration.migration_id,
            'status': migration.status,
            'progress_percent': migration.progress_percent or 0,
            'created_at': migration.created_at.isoformat() if migration.created_at else None
        }
        
        # Add optional fields
        if hasattr(migration, 'current_step') and migration.current_step:
            status_data['current_step'] = migration.current_step
        if hasattr(migration, 'completed_at') and migration.completed_at:
            status_data['completed_at'] = migration.completed_at.isoformat()
        
        return jsonify(status_data), 200
        
    except Exception as e:
        logger.exception(f"Failed to get migration status {migration_id}: {str(e)}")
        # SECURITY FIX: Clean up database session on error
        db.session.rollback()
        db.session.remove()
        return jsonify({
            'success': False,
            'error': 'Failed to get status'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>/start', methods=['POST'])
@limiter.limit("5 per minute")
@require_auth
def start_migration(migration_id):
    """
    Start migration on ephemeral AWS instance
    
    Args:
        migration_id: Migration ID
        
    Request Body:
        qbo_credentials (dict): QuickBooks Online OAuth credentials
            - client_id (str)
            - client_secret (str)
            - refresh_token (str)
    
    Returns:
        200: Migration started
        400: Invalid input or migration not ready
        404: Migration not found
        500: Server error
    """
    # HIGH-07 FIX: Validate UUID format before database query
    if not validate_migration_id(migration_id):
        return jsonify({
            'success': False,
            'error': 'Invalid migration ID format'
        }), 400

    try:
        # Verify user has available migration credits
        user_id = _get_current_user_id()
        user = db.session.get(User, user_id)

        # Check credits
        from models.migration_credit import MigrationCredit
        available_credits = MigrationCredit.query.filter_by(
            user_id=user_id,
            status='available',
            payment_status='paid'
        ).all()
        total_remaining = len(available_credits)

        if total_remaining <= 0:
            return jsonify({
                'success': False,
                'error': 'No migration credits available. Please purchase credits first.'
            }), 402

        # Use SELECT FOR UPDATE to prevent concurrent starts (race condition fix)
        migration = db.session.query(Migration).filter_by(
            migration_id=migration_id,
            user_id=user_id
        ).with_for_update().first()

        if not migration:
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404

        # Check migration status
        if migration.status != 'uploaded':
            return jsonify({
                'success': False,
                'error': f'Migration cannot be started from status: {migration.status}. Must be "uploaded".'
            }), 400
        
        # Verify S3 file exists
        if not migration.s3_uri:
            return jsonify({
                'success': False,
                'error': 'Migration file not found in cloud storage'
            }), 400
        
        # SECURITY FIX: Get QBO credentials from request with encryption support
        # Credentials can be sent in two formats:
        # 1. encrypted_credentials: Base64-encoded encrypted JSON (recommended)
        # 2. qbo_credentials: Plain JSON (only allowed if ALLOW_PLAINTEXT_CREDENTIALS=true in dev)
        data = request.get_json() or {}

        qbo_credentials = None

        # PRIORITY 1: Check for encrypted credentials (production-recommended)
        if data.get('encrypted_credentials'):
            try:
                from api.EncryptionManager import decrypt_client_credentials
                qbo_credentials = decrypt_client_credentials(data['encrypted_credentials'])
                logger.info(f"Migration {migration_id}: Using encrypted credentials")
            except Exception as e:
                logger.error(f"Failed to decrypt credentials for {migration_id}: {e}")
                return jsonify({
                    'success': False,
                    'error': 'Failed to decrypt credentials. Please re-encrypt and try again.'
                }), 400
        else:
            # PRIORITY 2: Plaintext credentials (development only)
            import os
            allow_plaintext = os.getenv('ALLOW_PLAINTEXT_CREDENTIALS', 'false').lower() == 'true'
            is_production = os.getenv('FLASK_ENV', 'development') == 'production'

            if is_production and not allow_plaintext:
                return jsonify({
                    'success': False,
                    'error': 'Plaintext credentials not allowed in production. Use encrypted_credentials field.'
                }), 400

            qbo_credentials = data.get('qbo_credentials', {})

            if allow_plaintext and qbo_credentials:
                logger.warning(f"Migration {migration_id}: Using PLAINTEXT credentials (not recommended)")

        if not qbo_credentials or not all(k in qbo_credentials for k in ['client_id', 'client_secret', 'refresh_token']):
            return jsonify({
                'success': False,
                'error': 'QuickBooks Online credentials required (client_id, client_secret, refresh_token)'
            }), 400

        # SECURITY: Validate and log receipt WITHOUT logging actual credentials
        client_id_masked = qbo_credentials.get('client_id', '')[:8] + '...' if qbo_credentials.get('client_id') else 'missing'
        logger.info(f"Received QBO credentials for migration {migration_id} (client_id: {client_id_masked})")

        # SECURITY: Immediately store credentials in Secrets Manager instead of passing through logs
        # This prevents credential exposure in CloudWatch, access logs, etc.
        
        # CRITICAL FIX: Ensure realm_id is present - use from user if not provided
        if 'realm_id' not in qbo_credentials or not qbo_credentials['realm_id']:
            from models.user import User
            user = User.query.get(_get_current_user_id())
            if user and user.qbo_realm_id:
                qbo_credentials['realm_id'] = user.qbo_realm_id
            else:
                return jsonify({
                    'success': False,
                    'error': 'realm_id required. Please connect to QuickBooks Online first.'
                }), 400
        
        # Mark as provisioning
        if hasattr(migration, 'mark_as_provisioning') and callable(migration.mark_as_provisioning):
            migration.mark_as_provisioning()
        else:
            migration.status = 'provisioning'
            db.session.commit()
        
        # Initialize AWS manager
        logger.info(f"Starting AWS migration for {migration_id}...")
        aws_manager = AWSMigrationManager(
            region=current_app.config.get('AWS_REGION', 'us-east-1')
        )
        
        # Get webhook secret
        webhook_secret = current_app.config.get('WEBHOOK_SECRET')
        
        # Create EC2 instance
        instance_id = aws_manager.create_ec2_instance(
            migration_id=migration_id,
            s3_uri=migration.s3_uri,
            qbo_credentials=qbo_credentials,
            webhook_secret=webhook_secret
        )
        
        if not instance_id:
            logger.error(f"Failed to create EC2 instance for {migration_id}")
            if hasattr(migration, 'mark_as_failed') and callable(migration.mark_as_failed):
                migration.mark_as_failed('Failed to create AWS instance', 'EC2_CREATE_ERROR')
            else:
                migration.status = 'failed'
                db.session.commit()
            return jsonify({
                'success': False,
                'error': 'Failed to create AWS instance. Please try again.'
            }), 500
        
        # Mark as processing
        if hasattr(migration, 'mark_as_processing') and callable(migration.mark_as_processing):
            migration.mark_as_processing(instance_id)
        else:
            migration.status = 'processing'
            if hasattr(migration, 'aws_instance_id'):
                migration.aws_instance_id = instance_id
            db.session.commit()
        
        logger.info(f"Migration {migration_id} started on AWS instance {instance_id}")
        
        return jsonify({
            'success': True,
            'migration_id': migration_id,
            'instance_id': instance_id,
            'status': 'processing',
            'message': 'Migration started on AWS. Instance will self-terminate when complete.'
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to start migration {migration_id}: {str(e)}")
        # SECURITY FIX: Clean up database session on error
        db.session.rollback()
        db.session.remove()
        return jsonify({
            'success': False,
            'error': 'Failed to start migration. Please try again.'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>/process', methods=['POST'])
@require_auth
@limiter.limit("5 per minute")
def process_migration(migration_id):
    """
    Process migration - alias for start_migration
    For backwards compatibility with older clients
    """
    return start_migration(migration_id)


@migrations_bp.route('/api/migrations/<migration_id>/cancel', methods=['POST'])
@require_auth
def cancel_migration(migration_id):
    """
    Cancel running migration

    Args:
        migration_id: Migration ID

    Returns:
        200: Migration cancelled
        400: Migration cannot be cancelled
        404: Migration not found
        500: Server error
    """
    # HIGH-07 FIX: Validate UUID format before database query
    if not validate_migration_id(migration_id):
        return jsonify({
            'success': False,
            'error': 'Invalid migration ID format'
        }), 400

    try:
        # Get migration
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=_get_current_user_id()
        ).first()
        
        if not migration:
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404
        
        # Check if can be cancelled
        if migration.status not in ['pending', 'uploaded', 'provisioning', 'processing']:
            return jsonify({
                'success': False,
                'error': f'Migration cannot be cancelled from status: {migration.status}'
            }), 400
        
        logger.info(f"Cancelling migration {migration_id}...")
        
        # Initialize AWS manager
        aws_manager = AWSMigrationManager()
        
        # Cleanup AWS resources
        instance_id = getattr(migration, 'aws_instance_id', None)
        cleanup_results = aws_manager.cleanup_migration(
            migration_id=migration_id,
            instance_id=instance_id
        )
        
        # Mark as failed (cancelled)
        if hasattr(migration, 'mark_as_failed') and callable(migration.mark_as_failed):
            migration.mark_as_failed('Cancelled by user', 'USER_CANCELLED')
        else:
            migration.status = 'failed'
            db.session.commit()
        
        # Update cleanup status
        if hasattr(migration, 'mark_ec2_terminated') and cleanup_results.get('instance_terminated'):
            migration.mark_ec2_terminated()
        if hasattr(migration, 'mark_s3_deleted') and cleanup_results.get('s3_deleted'):
            migration.mark_s3_deleted()
        
        if hasattr(migration, 'mark_cleanup_completed'):
            migration.mark_cleanup_completed()
        
        logger.info(f"Migration {migration_id} cancelled successfully")
        
        return jsonify({
            'success': True,
            'message': 'Migration cancelled and resources cleaned up'
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to cancel migration {migration_id}: {str(e)}")
        # SECURITY FIX: Clean up database session on error
        db.session.rollback()
        db.session.remove()
        return jsonify({
            'success': False,
            'error': 'Failed to cancel migration'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>/retry', methods=['POST'])
@require_auth
def retry_migration(migration_id):
    """
    Retry failed migration

    Args:
        migration_id: Migration ID

    Returns:
        200: Migration retried
        400: Migration cannot be retried
        404: Migration not found
        500: Server error
    """
    # HIGH-07 FIX: Validate UUID format before database query
    if not validate_migration_id(migration_id):
        return jsonify({
            'success': False,
            'error': 'Invalid migration ID format'
        }), 400

    try:
        # Get migration
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=_get_current_user_id()
        ).first()
        
        if not migration:
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404
        
        # Check if can retry
        if migration.status != 'failed':
            return jsonify({
                'success': False,
                'error': 'Only failed migrations can be retried'
            }), 400
        
        # Check retry count
        if hasattr(migration, 'can_retry') and callable(migration.can_retry):
            if not migration.can_retry():
                max_retries = getattr(migration, 'max_retries', 3)
                return jsonify({
                    'success': False,
                    'error': f'Maximum retry attempts reached ({max_retries})'
                }), 400
        
        # Increment retry count
        if hasattr(migration, 'increment_retry') and callable(migration.increment_retry):
            migration.increment_retry()
        elif hasattr(migration, 'retry_count'):
            migration.retry_count = (migration.retry_count or 0) + 1
            db.session.commit()
        
        # Reset status to uploaded
        migration.status = 'uploaded'
        migration.progress_percent = 0
        if hasattr(migration, 'current_step'):
            migration.current_step = None
        if hasattr(migration, 'error_message'):
            migration.error_message = None
        if hasattr(migration, 'error_code'):
            migration.error_code = None
        db.session.commit()
        
        retry_count = getattr(migration, 'retry_count', 1)
        max_retries = getattr(migration, 'max_retries', 3)
        logger.info(f"Migration {migration_id} reset for retry (attempt {retry_count}/{max_retries})")
        
        return jsonify({
            'success': True,
            'message': f'Migration ready to retry (attempt {retry_count}/{max_retries})',
            'migration_id': migration_id
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to retry migration {migration_id}: {str(e)}")
        # SECURITY FIX: Clean up database session on error
        db.session.rollback()
        db.session.remove()
        return jsonify({
            'success': False,
            'error': 'Failed to retry migration'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>', methods=['DELETE'])
@require_auth
def delete_migration(migration_id):
    """
    Delete migration record and cleanup resources

    Args:
        migration_id: Migration ID

    Returns:
        200: Migration deleted
        404: Migration not found
        500: Server error
    """
    # HIGH-07 FIX: Validate UUID format before database query
    if not validate_migration_id(migration_id):
        return jsonify({
            'success': False,
            'error': 'Invalid migration ID format'
        }), 400

    try:
        # Get migration
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=_get_current_user_id()
        ).first()
        
        if not migration:
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404
        
        logger.info(f"Deleting migration {migration_id}...")
        
        # Cleanup AWS resources if not already done
        cleanup_completed = getattr(migration, 'cleanup_completed', False)
        if not cleanup_completed:
            aws_manager = AWSMigrationManager()
            instance_id = getattr(migration, 'aws_instance_id', None)
            try:
                aws_manager.cleanup_migration(
                    migration_id=migration_id,
                    instance_id=instance_id
                )
            except Exception as cleanup_error:
                logger.warning(f"Cleanup failed during deletion: {str(cleanup_error)}")
                # Continue with deletion even if cleanup fails
        
        # Delete from database
        db.session.delete(migration)
        db.session.commit()
        
        logger.info(f"Migration {migration_id} deleted successfully")
        
        return jsonify({
            'success': True,
            'message': 'Migration deleted'
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to delete migration {migration_id}: {str(e)}")
        # SECURITY FIX: Clean up database session on error
        db.session.rollback()
        db.session.remove()
        return jsonify({
            'success': False,
            'error': 'Failed to delete migration'
        }), 500

# NOTE: Forensic endpoints (live-status, trial-balance, audit-certificate) 
# are implemented in dashboard_api.py to avoid route conflicts


# ============================================================================
# CELERY-BASED EXECUTION (Alternative to AWS EC2)
# ============================================================================

@migrations_bp.route('/api/migrations/<migration_id>/execute', methods=['POST'])
@require_auth
def execute_migration_celery(migration_id):
    """
    Execute migration using Celery background worker (Option B).

    This is an alternative to the AWS EC2-based execution.
    Requires Redis and Celery worker running.

    Args:
        migration_id: Migration ID

    Returns:
        202: Migration queued for execution
        400: Invalid state
        404: Migration not found
        500: Server error
    """
    # HIGH-07 FIX: Validate UUID format before database query
    if not validate_migration_id(migration_id):
        return jsonify({
            'success': False,
            'error': 'Invalid migration ID format'
        }), 400

    try:
        from tasks import run_migration_task

        # Get migration
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=_get_current_user_id()
        ).first()
        
        if not migration:
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404
        
        # Check migration status
        if migration.status not in ['uploaded', 'failed']:
            return jsonify({
                'success': False,
                'error': f'Migration cannot be executed from status: {migration.status}'
            }), 400
        
        # Get OAuth tokens from user if available
        from models.user import User
        oauth_tokens = None
        user = User.query.get(_get_current_user_id())
        if user and user.qbo_access_token:
            oauth_tokens = {
                'access_token': user.qbo_access_token,
                'refresh_token': user.qbo_refresh_token,
                'realm_id': user.qbo_realm_id
            }
        
        # Queue the migration task
        task = run_migration_task.delay(
            migration_id=migration_id,
            encrypted_file_path=migration.s3_uri or migration.file_path,
            user_id=_get_current_user_id(),
            oauth_tokens=oauth_tokens
        )
        
        # Update status to queued
        migration.status = 'queued'
        if hasattr(migration, 'celery_task_id'):
            migration.celery_task_id = task.id
        db.session.commit()
        
        logger.info(f"Migration {migration_id} queued with task {task.id}")
        
        return jsonify({
            'success': True,
            'migration_id': migration_id,
            'task_id': task.id,
            'status': 'queued',
            'message': 'Migration queued for background processing'
        }), 202
        
    except ImportError:
        # Celery not available, fall back to sync execution warning
        return jsonify({
            'success': False,
            'error': 'Background processing not available. Please start Celery workers.'
        }), 503
        
    except Exception as e:
        logger.exception(f"Failed to queue migration {migration_id}: {str(e)}")
        # SECURITY FIX: Clean up database session on error
        db.session.rollback()
        db.session.remove()
        return jsonify({
            'success': False,
            'error': 'Failed to queue migration'
        }), 500


@migrations_bp.route('/api/migrations/stats', methods=['GET'])
@require_auth
def get_migration_stats():
    """
    Get migration statistics for dashboard.
    
    Returns real data (not mock) for the current user.
    """
    try:
        from sqlalchemy import func
        from datetime import datetime, timedelta, timezone
        
        user_id = _get_current_user_id()
        
        # Get current month's migrations
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Total migrations this month
        migrations_this_month = Migration.query.filter(
            Migration.user_id == user_id,
            Migration.created_at >= month_start
        ).count()
        
        # Total records migrated (sum of records across all migrations)
        total_records = db.session.query(func.sum(Migration.total_records_migrated)).filter(
            Migration.user_id == user_id
        ).scalar() or 0
        
        # Average duration (for completed migrations)
        completed_migrations = Migration.query.filter(
            Migration.user_id == user_id,
            Migration.status == 'completed',
            Migration.completed_at.isnot(None),
            Migration.created_at.isnot(None)
        ).all()
        
        if completed_migrations:
            durations = []
            for m in completed_migrations:
                if m.completed_at and m.created_at:
                    duration = (m.completed_at - m.created_at).total_seconds()
                    if duration > 0:
                        durations.append(duration)
            avg_duration = sum(durations) / len(durations) if durations else 0
        else:
            avg_duration = 0
        
        # Success rate
        total_finished = Migration.query.filter(
            Migration.user_id == user_id,
            Migration.status.in_(['completed', 'failed'])
        ).count()
        
        successful = Migration.query.filter(
            Migration.user_id == user_id,
            Migration.status == 'completed'
        ).count()
        
        success_rate = (successful / total_finished * 100) if total_finished > 0 else 100
        
        # Format average duration
        if avg_duration > 0:
            minutes = int(avg_duration // 60)
            seconds = int(avg_duration % 60)
            avg_duration_str = f"{minutes}m {seconds}s"
        else:
            avg_duration_str = "--"
        
        # Format total records
        if total_records >= 1000000:
            records_str = f"{total_records / 1000000:.1f}M"
        elif total_records >= 1000:
            records_str = f"{total_records / 1000:.1f}K"
        else:
            records_str = str(total_records)
        
        return jsonify({
            'success': True,
            'stats': {
                'migrations_this_month': migrations_this_month,
                'total_records': records_str,
                'avg_duration': avg_duration_str,
                'success_rate': f"{success_rate:.1f}%"
            }
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get migration stats: {str(e)}")
        # SECURITY FIX: Clean up database session on error
        db.session.rollback()
        db.session.remove()
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve migration statistics'
        }), 500
