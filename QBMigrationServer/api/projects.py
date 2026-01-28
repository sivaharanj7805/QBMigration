"""
ForensicBridge Projects API
Manage migration projects for clients
"""

from flask import Blueprint, request, jsonify
from datetime import datetime

from models import db, Project, Migration
from models.project import generate_session_id
from api.auth import require_auth

projects_bp = Blueprint('projects', __name__, url_prefix='/api/projects')


@projects_bp.route('', methods=['GET'])
@require_auth
def list_projects():
    """List all projects for the current user"""
    user_id = request.current_user['user_id']
    
    projects = Project.query.filter_by(user_id=user_id).order_by(Project.created_at.desc()).all()
    
    return jsonify({
        'projects': [{
            'id': p.id,
            'name': p.name,
            'client_name': p.client_name,
            'status': p.status,
            'session_id': p.session_id,
            'created_at': p.created_at.isoformat(),
            'migration_count': len(p.migrations)
        } for p in projects]
    })


@projects_bp.route('', methods=['POST'])
@require_auth
def create_project():
    """Create a new migration project"""
    user_id = request.current_user['user_id']
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    name = data.get('name', '').strip()
    client_name = data.get('client_name', '').strip()
    client_email = data.get('client_email', '').strip()
    notes = data.get('notes', '').strip()
    
    if not name or not client_name:
        return jsonify({'error': 'Project name and client name are required'}), 400
    
    # Generate unique session ID
    session_id = generate_session_id()
    
    project = Project(
        user_id=user_id,
        name=name,
        client_name=client_name,
        client_email=client_email,
        notes=notes,
        session_id=session_id,
        status='pending'
    )
    
    try:
        db.session.add(project)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create project'}), 500
    
    return jsonify({
        'success': True,
        'project': {
            'id': project.id,
            'name': project.name,
            'client_name': project.client_name,
            'session_id': project.session_id,
            'status': project.status,
            'created_at': project.created_at.isoformat()
        }
    }), 201


@projects_bp.route('/<int:project_id>', methods=['GET'])
@require_auth
def get_project(project_id):
    """Get project details"""
    user_id = request.current_user['user_id']
    
    project = Project.query.filter_by(id=project_id, user_id=user_id).first()
    
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Get migrations for this project
    migrations = Migration.query.filter_by(session_id=project.session_id).all()
    
    return jsonify({
        'project': {
            'id': project.id,
            'name': project.name,
            'client_name': project.client_name,
            'client_email': project.client_email,
            'notes': project.notes,
            'session_id': project.session_id,
            'status': project.status,
            'created_at': project.created_at.isoformat(),
            'updated_at': project.updated_at.isoformat() if project.updated_at else None
        },
        'migrations': [{
            'id': m.id,
            'status': m.status,
            'progress_percent': m.progress_percent,
            'company_name': m.company_name,
            'started_at': m.started_at.isoformat() if m.started_at else None,
            'completed_at': m.completed_at.isoformat() if m.completed_at else None
        } for m in migrations]
    })


@projects_bp.route('/<int:project_id>', methods=['PUT'])
@require_auth
def update_project(project_id):
    """Update project details"""
    user_id = request.current_user['user_id']
    data = request.get_json()
    
    project = Project.query.filter_by(id=project_id, user_id=user_id).first()
    
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Update allowed fields
    if 'name' in data:
        project.name = data['name'].strip()
    if 'client_name' in data:
        project.client_name = data['client_name'].strip()
    if 'client_email' in data:
        project.client_email = data['client_email'].strip()
    if 'notes' in data:
        project.notes = data['notes'].strip()
    
    project.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update project'}), 500
    
    return jsonify({'success': True})


@projects_bp.route('/<int:project_id>', methods=['DELETE'])
@require_auth
def delete_project(project_id):
    """Delete a project"""
    user_id = request.current_user['user_id']
    
    project = Project.query.filter_by(id=project_id, user_id=user_id).first()
    
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Check if there are active migrations
    active_migrations = Migration.query.filter(
        Migration.session_id == project.session_id,
        Migration.status.in_(['uploading', 'processing', 'migrating'])
    ).count()
    
    if active_migrations > 0:
        return jsonify({'error': 'Cannot delete project with active migrations'}), 400
    
    try:
        db.session.delete(project)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete project'}), 500
    
    return jsonify({'success': True})


@projects_bp.route('/<int:project_id>/download-extractor', methods=['GET'])
@require_auth
def get_extractor_download(project_id):
    """Get download link for ForensicBridge extractor with embedded session ID"""
    user_id = request.current_user['user_id']
    
    project = Project.query.filter_by(id=project_id, user_id=user_id).first()
    
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Return the API endpoint for extractor download
    return jsonify({
        'download_url': '/api/extractor/download',
        'session_id': project.session_id,
        'instructions': (
            '1. Download and run the installer\n'
            '2. When prompted, enter this Session ID: ' + project.session_id + '\n'
            '3. Follow the on-screen instructions to connect to QuickBooks\n'
            '4. Return to this dashboard to monitor progress'
        )
    })
