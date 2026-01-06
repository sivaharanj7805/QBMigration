from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models.database import db
from models.migration import Migration
from utils.aws_manager import AWSMigrationManager
import logging

migrations_bp = Blueprint('migrations', __name__)
logger = logging.getLogger(__name__)


@migrations_bp.route('/api/migrations', methods=['GET'])
@login_required
def list_migrations():
    """
    List all migrations for current user
    
    Query Parameters:
        status (str, optional): Filter by status
        limit (int, optional): Max results (default 50)
        offset (int, optional): Pagination offset
    
    Returns:
        200: List of migrations
        500: Server error
    """
    try:
        # Get query parameters
        status_filter = request.args.get('status')
        limit = min(int(request.args.get('limit', 50)), 100)
        offset = int(request.args.get('offset', 0))
        
        # Build query
        query = Migration.query.filter_by(user_id=current_user.id)
        
        if status_filter:
            query = query.filter_by(status=status_filter)
        
        # Order by created date (newest first)
        query = query.order_by(Migration.created_at.desc())
        
        # Paginate
        total = query.count()
        migrations = query.limit(limit).offset(offset).all()
        
        return jsonify({
            'success': True,
            'migrations': [m.to_dict() for m in migrations],
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to list migrations: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve migrations'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>', methods=['GET'])
@login_required
def get_migration(migration_id):
    """
    Get specific migration details
    
    Args:
        migration_id: Migration ID
    
    Returns:
        200: Migration details
        404: Migration not found
        500: Server error
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
            'migration': migration.to_dict()
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get migration {migration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve migration'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>/status', methods=['GET'])
@login_required
def get_migration_status(migration_id):
    """
    Get migration status (lightweight endpoint for polling)
    
    Args:
        migration_id: Migration ID
    
    Returns:
        200: Migration status
        404: Migration not found
        500: Server error
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
            'migration_id': migration.migration_id,
            'status': migration.status,
            'progress_percent': migration.progress_percent,
            'current_step': migration.current_step,
            'created_at': migration.created_at.isoformat() if migration.created_at else None,
            'completed_at': migration.completed_at.isoformat() if migration.completed_at else None
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get migration status {migration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get status'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>/start', methods=['POST'])
@login_required
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
    try:
        # Get migration
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=current_user.id
        ).first()
        
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
        
        # Get QBO credentials from request
        data = request.get_json() or {}
        qbo_credentials = data.get('qbo_credentials', {})
        
        if not qbo_credentials or not all(k in qbo_credentials for k in ['client_id', 'client_secret', 'refresh_token']):
            return jsonify({
                'success': False,
                'error': 'QuickBooks Online credentials required (client_id, client_secret, refresh_token)'
            }), 400
        
        # Mark as provisioning
        migration.mark_as_provisioning()
        
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
            migration.mark_as_failed('Failed to create AWS instance', 'EC2_CREATE_ERROR')
            return jsonify({
                'success': False,
                'error': 'Failed to create AWS instance. Please try again.'
            }), 500
        
        # Mark as processing
        migration.mark_as_processing(instance_id)
        
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
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to start migration. Please try again.'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>/cancel', methods=['POST'])
@login_required
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
    try:
        # Get migration
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=current_user.id
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
        cleanup_results = aws_manager.cleanup_migration(
            migration_id=migration_id,
            instance_id=migration.aws_instance_id
        )
        
        # Mark as failed (cancelled)
        migration.mark_as_failed('Cancelled by user', 'USER_CANCELLED')
        
        # Update cleanup status
        if cleanup_results.get('instance_terminated'):
            migration.mark_ec2_terminated()
        if cleanup_results.get('s3_deleted'):
            migration.mark_s3_deleted()
        
        migration.mark_cleanup_completed()
        
        logger.info(f"Migration {migration_id} cancelled successfully")
        
        return jsonify({
            'success': True,
            'message': 'Migration cancelled and resources cleaned up'
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to cancel migration {migration_id}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to cancel migration'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>/retry', methods=['POST'])
@login_required
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
    try:
        # Get migration
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=current_user.id
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
        
        if not migration.can_retry():
            return jsonify({
                'success': False,
                'error': f'Maximum retry attempts reached ({migration.max_retries})'
            }), 400
        
        # Increment retry count
        migration.increment_retry()
        
        # Reset status to uploaded
        migration.status = 'uploaded'
        migration.progress_percent = 0
        migration.current_step = None
        migration.error_message = None
        migration.error_code = None
        db.session.commit()
        
        logger.info(f"Migration {migration_id} reset for retry (attempt {migration.retry_count}/{migration.max_retries})")
        
        return jsonify({
            'success': True,
            'message': f'Migration ready to retry (attempt {migration.retry_count}/{migration.max_retries})',
            'migration_id': migration_id
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to retry migration {migration_id}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to retry migration'
        }), 500


@migrations_bp.route('/api/migrations/<migration_id>', methods=['DELETE'])
@login_required
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
    try:
        # Get migration
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=current_user.id
        ).first()
        
        if not migration:
            return jsonify({
                'success': False,
                'error': 'Migration not found'
            }), 404
        
        logger.info(f"Deleting migration {migration_id}...")
        
        # Cleanup AWS resources if not already done
        if not migration.cleanup_completed:
            aws_manager = AWSMigrationManager()
            aws_manager.cleanup_migration(
                migration_id=migration_id,
                instance_id=migration.aws_instance_id
            )
        
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
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to delete migration'
        }), 500