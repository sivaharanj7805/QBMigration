from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from models.database import db
from models.migration import Migration
import os

migrations_bp = Blueprint('migrations', __name__)

@migrations_bp.route('/api/migrations', methods=['GET'])
@login_required
def list_migrations():
    """Get all migrations for current user"""
    
    migrations = Migration.query.filter_by(
        user_id=current_user.id
    ).order_by(Migration.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'migrations': [m.to_dict() for m in migrations]
    }), 200


@migrations_bp.route('/api/migrations/<migration_id>', methods=['GET'])
@login_required
def get_migration(migration_id):
    """Get specific migration details"""
    
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


@migrations_bp.route('/api/migrations/<migration_id>/status', methods=['GET'])
@login_required
def get_migration_status(migration_id):
    """Get migration status (for polling)"""
    
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
        'error_message': migration.error_message
    }), 200


@migrations_bp.route('/api/migrations/<migration_id>/report', methods=['GET'])
@login_required
def download_report(migration_id):
    """Download verification report"""
    
    migration = Migration.query.filter_by(
        migration_id=migration_id,
        user_id=current_user.id
    ).first()
    
    if not migration:
        return jsonify({
            'success': False,
            'error': 'Migration not found'
        }), 404
    
    if not migration.verification_report_path:
        return jsonify({
            'success': False,
            'error': 'Report not available yet'
        }), 404
    
    if not os.path.exists(migration.verification_report_path):
        return jsonify({
            'success': False,
            'error': 'Report file not found'
        }), 404
    
    return send_file(
        migration.verification_report_path,
        as_attachment=True,
        download_name=f"verification_report_{migration_id}.json"
    )


@migrations_bp.route('/api/migrations/<migration_id>/cancel', methods=['POST'])
@login_required
def cancel_migration(migration_id):
    """Cancel a pending migration"""
    
    migration = Migration.query.filter_by(
        migration_id=migration_id,
        user_id=current_user.id
    ).first()
    
    if not migration:
        return jsonify({
            'success': False,
            'error': 'Migration not found'
        }), 404
    
    if migration.status not in ['pending', 'processing']:
        return jsonify({
            'success': False,
            'error': f'Cannot cancel migration with status: {migration.status}'
        }), 400
    
    migration.status = 'cancelled'
    migration.completed_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Migration cancelled'
    }), 200