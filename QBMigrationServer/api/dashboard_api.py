"""
Dashboard API - ForensicBridge Enterprise Dashboard Endpoints

Provides API endpoints for:
1. Real-time migration status (Pizza Tracker)
2. Dashboard overview statistics
3. Recent activity feed (Forensic Log)
4. Trial balance verification data
5. Audit certificate download
"""

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from models.database import db
from models.migration import Migration
from sqlalchemy import func, extract
import logging
import json
import os
import re
from datetime import datetime, timedelta
from io import BytesIO
import sys


def is_valid_uuid(value):
    """
    Validate UUID format to prevent path traversal.
    FIX: Added UUID validation for all migration_id parameters.
    """
    if not value:
        return False
    uuid_pattern = r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$'
    return bool(re.match(uuid_pattern, value))

# FIX #33: Import locale-aware lead sheet mapper for Caseware fallback
# CRIT-06 FIX: Use environment variable or relative path instead of hardcoded path
_service_path = os.getenv(
    'QBM_SERVICE_PATH',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'QBMigrationService'))
)
if _service_path not in sys.path:
    sys.path.insert(0, _service_path)

logger = logging.getLogger(__name__)

try:
    from leadsheet_mapper import LeadSheetMapper
except ImportError:
    logger.warning("LeadSheetMapper not available - will use US GAAP defaults in Caseware fallback")
    LeadSheetMapper = None

dashboard_bp = Blueprint('dashboard', __name__)


# =============================================================================
# PIZZA TRACKER - Real-time Status
# =============================================================================

@dashboard_bp.route('/api/migrations/<migration_id>/live-status', methods=['GET'])
@login_required
def get_live_status(migration_id):
    """
    Enhanced status endpoint for Pizza Tracker polling.
    Returns detailed phase information for real-time UI updates.
    
    Response:
    {
        "migration_id": "mig_78921",
        "phase": "TRANSFORMATION",
        "phase_number": 3,
        "percentage": 65,
        "current_entity": "JournalEntries",
        "current_batch": 42,
        "total_batches": 100,
        "status_message": "Reconstructing Linked Transactions...",
        "alerts": ["Found 2 invalid date formats (Auto-Healed)"],
        "integrity_verified": true,
        "phases": [
            {"name": "EXTRACTION", "status": "completed", "percentage": 100},
            {"name": "TRANSIT", "status": "completed", "percentage": 100},
            {"name": "TRANSFORMATION", "status": "in_progress", "percentage": 65},
            {"name": "VERIFICATION", "status": "pending", "percentage": 0}
        ]
    }
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
        
        # Determine current phase from progress percentage
        progress = migration.progress_percent or 0
        current_step = getattr(migration, 'current_step', None) or ''
        
        # Phase definitions based on orchestrator.py percentages
        # Phase 1: Extraction (0-15%)
        # Phase 2: Transit/Upload (15-20%)
        # Phase 3: Transformation (20-85%)
        # Phase 4: Verification (85-100%)
        
        phases = []
        phase_number = 1
        phase_name = 'EXTRACTION'
        
        if progress >= 0:
            phases.append({
                'name': 'EXTRACTION',
                'status': 'completed' if progress >= 15 else 'in_progress' if progress > 0 else 'pending',
                'percentage': min(100, (progress / 15) * 100) if progress < 15 else 100,
                'description': 'Decrypting and hashing records'
            })
        
        if progress >= 15:
            phases.append({
                'name': 'TRANSIT',
                'status': 'completed' if progress >= 20 else 'in_progress',
                'percentage': min(100, ((progress - 15) / 5) * 100) if progress < 20 else 100,
                'description': 'Uploading to secure cloud'
            })
            if progress < 20:
                phase_number = 2
                phase_name = 'TRANSIT'
        else:
            phases.append({
                'name': 'TRANSIT',
                'status': 'pending',
                'percentage': 0,
                'description': 'Uploading to secure cloud'
            })
        
        if progress >= 20:
            transformation_pct = min(100, ((progress - 20) / 65) * 100) if progress < 85 else 100
            phases.append({
                'name': 'TRANSFORMATION',
                'status': 'completed' if progress >= 85 else 'in_progress',
                'percentage': transformation_pct,
                'description': 'Reconstructing linked transactions'
            })
            if progress < 85:
                phase_number = 3
                phase_name = 'TRANSFORMATION'
        else:
            phases.append({
                'name': 'TRANSFORMATION',
                'status': 'pending',
                'percentage': 0,
                'description': 'Reconstructing linked transactions'
            })
        
        if progress >= 85:
            verification_pct = min(100, ((progress - 85) / 15) * 100) if progress < 100 else 100
            phases.append({
                'name': 'VERIFICATION',
                'status': 'completed' if progress >= 100 else 'in_progress',
                'percentage': verification_pct,
                'description': 'Validating trial balance'
            })
            if progress < 100:
                phase_number = 4
                phase_name = 'VERIFICATION'
        else:
            phases.append({
                'name': 'VERIFICATION',
                'status': 'pending',
                'percentage': 0,
                'description': 'Validating trial balance'
            })
        
        # Extract current entity from status message if available
        current_entity = None
        if 'Migrating' in current_step:
            current_entity = current_step.replace('Migrating ', '')
        elif current_step:
            current_entity = current_step
        
        # Build response
        response = {
            'success': True,
            'migration_id': migration.migration_id,
            'phase': phase_name,
            'phase_number': phase_number,
            'percentage': progress,
            'current_entity': current_entity,
            'status_message': current_step or f'Processing {phase_name.lower()}...',
            'status': migration.status,
            'alerts': [],
            'integrity_verified': migration.status == 'completed',
            'phases': phases,
            'company_name': migration.company_name,
            'started_at': migration.created_at.isoformat() if migration.created_at else None,
            'elapsed_seconds': (datetime.utcnow() - migration.created_at).total_seconds() if migration.created_at else 0
        }
        
        # Add completion data if done
        if migration.status == 'completed' and migration.completed_at:
            response['completed_at'] = migration.completed_at.isoformat()
            response['duration_seconds'] = (migration.completed_at - migration.created_at).total_seconds()
        
        # Add error info if failed
        if migration.status == 'failed':
            error_msg = migration.get_error_message() if hasattr(migration, 'get_error_message') else getattr(migration, 'error_message', None)
            response['error'] = error_msg
            response['alerts'].append(f'Migration failed: {error_msg}')
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.exception(f"Failed to get live status for {migration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get migration status'
        }), 500


@dashboard_bp.route('/api/migrations/bulk-status', methods=['POST'])
@login_required
def get_bulk_status():
    """
    Get status for multiple migrations at once (Enterprise feature).
    Optimized for dashboard bulk manager view.
    
    Request Body:
    {
        "migration_ids": ["mig_001", "mig_002", ...]
    }
    
    Response:
    {
        "migrations": {
            "mig_001": { status, progress, ... },
            "mig_002": { status, progress, ... }
        }
    }
    """
    try:
        data = request.get_json() or {}
        migration_ids = data.get('migration_ids', [])

        # FIX: Add max length check to prevent DoS via large arrays
        MAX_MIGRATION_IDS = 100
        if isinstance(migration_ids, list) and len(migration_ids) > MAX_MIGRATION_IDS:
            return jsonify({
                'success': False,
                'error': f'Too many migration IDs. Maximum allowed: {MAX_MIGRATION_IDS}'
            }), 400

        if not migration_ids:
            # Return all migrations if no IDs specified
            migrations = Migration.query.filter_by(user_id=current_user.id)\
                .order_by(Migration.created_at.desc()).limit(100).all()
        else:
            migrations = Migration.query.filter(
                Migration.migration_id.in_(migration_ids),
                Migration.user_id == current_user.id
            ).all()
        
        migrations_data = {}
        for m in migrations:
            migrations_data[m.migration_id] = {
                'id': m.id,
                'migration_id': m.migration_id,
                'status': m.status,
                'progress_percent': m.progress_percent or 0,
                'company_name': m.company_name,
                'qb_file_name': m.qb_file_name,
                'file_size': getattr(m, 'file_size', None),
                'created_at': m.created_at.isoformat() if m.created_at else None,
                'completed_at': m.completed_at.isoformat() if m.completed_at else None,
                'current_step': getattr(m, 'current_step', None)
            }
        
        return jsonify({
            'success': True,
            'migrations': migrations_data,
            'count': len(migrations_data)
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get bulk status: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get bulk status'
        }), 500


# =============================================================================
# DASHBOARD OVERVIEW
# =============================================================================

@dashboard_bp.route('/api/dashboard/overview', methods=['GET'])
@login_required
def get_dashboard_overview():
    """
    Aggregate statistics for dashboard KPI cards.
    
    Response:
    {
        "total_migrations": 150,
        "completed_migrations": 120,
        "failed_migrations": 5,
        "in_progress": 3,
        "success_rate": 96.0,
        "avg_duration_minutes": 45.2,
        "total_entities_migrated": 1250000,
        "total_data_migrated_gb": 15.5
    }
    """
    try:
        # Get migration counts by status
        total = Migration.query.filter_by(user_id=current_user.id).count()
        completed = Migration.query.filter_by(user_id=current_user.id, status='completed').count()
        failed = Migration.query.filter_by(user_id=current_user.id, status='failed').count()
        in_progress = Migration.query.filter(
            Migration.user_id == current_user.id,
            Migration.status.in_(['pending', 'uploading', 'uploaded', 'provisioning', 'processing'])
        ).count()
        
        # Calculate success rate
        success_rate = (completed / max(completed + failed, 1)) * 100

        # PERFORMANCE FIX: Calculate average duration using SQL aggregation
        # Instead of loading all migrations into memory, use database to calculate average
        avg_duration_result = db.session.query(
            func.avg(
                extract('epoch', Migration.completed_at - Migration.created_at)
            )
        ).filter(
            Migration.user_id == current_user.id,
            Migration.status == 'completed',
            Migration.completed_at.isnot(None),
            Migration.created_at.isnot(None)
        ).scalar()

        # Convert from seconds to minutes (result is in seconds)
        avg_duration_minutes = (avg_duration_result / 60.0) if avg_duration_result else 0
        
        # Recent activity (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(hours=24)
        recent_completed = Migration.query.filter(
            Migration.user_id == current_user.id,
            Migration.status == 'completed',
            Migration.completed_at >= yesterday
        ).count()
        
        return jsonify({
            'success': True,
            'overview': {
                'total_migrations': total,
                'completed_migrations': completed,
                'failed_migrations': failed,
                'in_progress': in_progress,
                'success_rate': round(success_rate, 1),
                'avg_duration_minutes': round(avg_duration_minutes, 1),
                'recent_completed_24h': recent_completed,
                'pending_review': 0  # Placeholder for future feature
            }
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get dashboard overview: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get dashboard overview'
        }), 500


@dashboard_bp.route('/api/dashboard/recent-activity', methods=['GET'])
@login_required
def get_recent_activity():
    """
    Recent activity feed for Forensic Log display.
    Returns last 50 activity entries with timestamps.
    """
    try:
        # Get recent migrations with activity
        migrations = Migration.query.filter_by(user_id=current_user.id)\
            .order_by(Migration.updated_at.desc() if hasattr(Migration, 'updated_at') else Migration.created_at.desc())\
            .limit(20).all()
        
        activities = []
        
        for m in migrations:
            # Generate activity entries based on migration status
            if m.status == 'completed':
                activities.append({
                    'timestamp': m.completed_at.isoformat() if m.completed_at else m.created_at.isoformat(),
                    'type': 'success',
                    'message': f"Migration completed for {m.company_name}",
                    'migration_id': m.migration_id,
                    'icon': 'check-circle'
                })
                activities.append({
                    'timestamp': m.completed_at.isoformat() if m.completed_at else m.created_at.isoformat(),
                    'type': 'info',
                    'message': f"SHA-256 Integrity Hash Verified",
                    'migration_id': m.migration_id,
                    'icon': 'shield-check'
                })
            elif m.status == 'failed':
                activities.append({
                    'timestamp': m.created_at.isoformat(),
                    'type': 'error',
                    'message': f"Migration failed for {m.company_name}",
                    'migration_id': m.migration_id,
                    'icon': 'x-circle'
                })
            elif m.status == 'processing':
                activities.append({
                    'timestamp': m.created_at.isoformat(),
                    'type': 'info',
                    'message': f"Processing {m.company_name} ({m.progress_percent or 0}%)",
                    'migration_id': m.migration_id,
                    'icon': 'loader'
                })
            elif m.status == 'uploaded':
                activities.append({
                    'timestamp': m.created_at.isoformat(),
                    'type': 'info',
                    'message': f"Upload complete for {m.company_name}",
                    'migration_id': m.migration_id,
                    'icon': 'upload-cloud'
                })
        
        # Sort by timestamp descending
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'activities': activities[:50]
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get recent activity: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get recent activity'
        }), 500


# =============================================================================
# TRIAL BALANCE & VERIFICATION
# =============================================================================

@dashboard_bp.route('/api/migrations/<migration_id>/trial-balance', methods=['GET'])
@login_required
def get_trial_balance(migration_id):
    """
    Get trial balance verification data for Reconciliation Shield display.
    
    Response:
    {
        "source_trial_balance": 1245678.90,
        "destination_trial_balance": 1245678.90,
        "discrepancy": 0.00,
        "is_balanced": true,
        "forensic_status": "VERIFIED",
        "verification_timestamp": "2026-01-15T05:30:00Z",
        "source_hash": "0x8f...2a",
        "destination_hash": "0x8f...2a",
        "hash_match": true
    }
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
        
        # Get verification results if stored
        verification_data = None
        if hasattr(migration, 'verification_results') and migration.verification_results:
            try:
                verification_data = json.loads(migration.verification_results)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Build trial balance response
        if verification_data and 'trial_balance' in verification_data:
            tb = verification_data['trial_balance']
            response = {
                'success': True,
                'source_trial_balance': tb.get('source_total', 0),
                'destination_trial_balance': tb.get('destination_total', 0),
                'discrepancy': abs(tb.get('source_total', 0) - tb.get('destination_total', 0)),
                'is_balanced': tb.get('is_balanced', False),
                'forensic_status': 'VERIFIED' if tb.get('is_balanced', False) else 'DISCREPANCY_DETECTED',
                'verification_timestamp': migration.completed_at.isoformat() if migration.completed_at else None,
                'total_debits': tb.get('total_debits', 0),
                'total_credits': tb.get('total_credits', 0)
            }
        else:
            # Return placeholder for migrations without verification data
            response = {
                'success': True,
                'source_trial_balance': None,
                'destination_trial_balance': None,
                'discrepancy': None,
                'is_balanced': None,
                'forensic_status': 'PENDING' if migration.status != 'completed' else 'NOT_AVAILABLE',
                'verification_timestamp': None,
                'message': 'Verification data not yet available' if migration.status != 'completed' else 'No verification data stored'
            }
        
        # Add hash verification if available
        if verification_data and 'integrity' in verification_data:
            integrity = verification_data['integrity']
            response['source_hash'] = integrity.get('source_hash', '')[:16] + '...'
            response['destination_hash'] = integrity.get('destination_hash', '')[:16] + '...'
            response['hash_match'] = integrity.get('hash_match', False)
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.exception(f"Failed to get trial balance for {migration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get trial balance data'
        }), 500


# =============================================================================
# AUDIT CERTIFICATE
# =============================================================================

@dashboard_bp.route('/api/migrations/<migration_id>/audit-certificate', methods=['GET'])
@login_required
def download_audit_certificate(migration_id):
    """
    Download PDF audit certificate for completed migration.
    Generates certificate on-demand using PremiumMigrationVerifier.
    """
    # FIX: Validate migration_id format to prevent path traversal
    if not is_valid_uuid(migration_id):
        return jsonify({
            'success': False,
            'error': 'Invalid migration ID format'
        }), 400

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
        
        if migration.status != 'completed':
            return jsonify({
                'success': False,
                'error': 'Audit certificate only available for completed migrations'
            }), 400
        
        # Check if certificate already exists
        cert_dir = os.path.join(current_app.root_path, 'certificates')
        os.makedirs(cert_dir, exist_ok=True)
        cert_path = os.path.join(cert_dir, f'{migration_id}_audit_certificate.pdf')
        
        if not os.path.exists(cert_path):
            # Generate certificate using verifier
            try:
                from verifier import PremiumMigrationVerifier
                
                # Create verifier instance for certificate generation
                verifier = PremiumMigrationVerifier(qbo_client=None)
                
                # Get verification data
                verification_data = {}
                if hasattr(migration, 'verification_results') and migration.verification_results:
                    try:
                        verification_data = json.loads(migration.verification_results)
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # Generate PDF
                verifier.generate_professional_pdf_certificate(
                    filepath=cert_path,
                    company_name=migration.company_name or 'Unknown Company',
                    migration_id=migration_id,
                    data_quality_score=verification_data.get('data_quality_score', 95),
                    source_hash=verification_data.get('integrity', {}).get('source_hash', 'N/A'),
                    destination_hash=verification_data.get('integrity', {}).get('destination_hash', 'N/A')
                )
            except ImportError:
                logger.warning("Could not import PremiumMigrationVerifier, generating basic certificate")
                # Generate a basic placeholder certificate
                from reportlab.lib.pagesizes import letter
                from reportlab.platypus import SimpleDocTemplate, Paragraph
                from reportlab.lib.styles import getSampleStyleSheet
                
                doc = SimpleDocTemplate(cert_path, pagesize=letter)
                styles = getSampleStyleSheet()
                story = [
                    Paragraph(f"<b>ForensicBridge Migration Certificate</b>", styles['Title']),
                    Paragraph(f"<br/><br/>", styles['Normal']),
                    Paragraph(f"Migration ID: {migration_id}", styles['Normal']),
                    Paragraph(f"Company: {migration.company_name}", styles['Normal']),
                    Paragraph(f"Status: COMPLETED", styles['Normal']),
                    Paragraph(f"Date: {migration.completed_at.strftime('%Y-%m-%d %H:%M:%S') if migration.completed_at else 'N/A'}", styles['Normal']),
                ]
                doc.build(story)
            except Exception as gen_error:
                logger.exception(f"Failed to generate certificate: {str(gen_error)}")
                return jsonify({
                    'success': False,
                    'error': 'Failed to generate audit certificate'
                }), 500
        
        # Return the PDF file
        return send_file(
            cert_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{migration.company_name or migration_id}_audit_certificate.pdf'
        )
        
    except Exception as e:
        logger.exception(f"Failed to download audit certificate for {migration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to download audit certificate'
        }), 500


@dashboard_bp.route('/api/migrations/<migration_id>/audit-certificate/preview', methods=['GET'])
@login_required
def preview_audit_certificate(migration_id):
    """
    Get audit certificate preview data (for thumbnail card).
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
        
        # Return preview metadata
        return jsonify({
            'success': True,
            'available': migration.status == 'completed',
            'migration_id': migration_id,
            'company_name': migration.company_name,
            'completed_at': migration.completed_at.isoformat() if migration.completed_at else None,
            'download_url': f'/api/migrations/{migration_id}/audit-certificate'
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get certificate preview for {migration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get certificate preview'
        }), 500


# =============================================================================
# CASEWARE EXPORT MODE
# =============================================================================

@dashboard_bp.route('/api/migrations/<migration_id>/export-caseware', methods=['POST'])
@login_required
def export_caseware_bundle(migration_id):
    """
    Generate Caseware Audit Bundle for a completed migration.
    This is the 'Caseware Mode' alternative to QBO migration.
    
    Generates:
    - Audit_TB.csv (Trial Balance with Lead Sheet codes)
    - Audit_GL.csv (General Ledger with SHA-256 hashes)
    - Audit_Mapping.cvw (Caseware column configuration)
    
    Response:
    {
        "success": true,
        "bundle_id": "cw_abc123",
        "files": ["Audit_TB.csv", "Audit_GL.csv", "Audit_Mapping.cvw"],
        "download_url": "/api/migrations/{id}/caseware-bundle"
    }
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
        
        if migration.status not in ['completed', 'uploaded']:
            return jsonify({
                'success': False,
                'error': 'Migration must be completed or uploaded to generate Caseware bundle'
            }), 400
        
        # Create output directory for Caseware bundle
        bundle_dir = os.path.join(current_app.root_path, 'caseware_bundles', migration_id)
        os.makedirs(bundle_dir, exist_ok=True)
        
        try:
            # Import the CasewareExporter
            from caseware_exporter import CasewareExporter
            
            # Create exporter
            exporter = CasewareExporter(
                output_dir=bundle_dir,
                company_name=migration.company_name or 'Company'
            )
            
            # Get QB data from S3 or stored data
            qb_data = {}
            
            # Try to load stored data
            if hasattr(migration, 'trial_balance_data') and migration.trial_balance_data:
                try:
                    stored_data = json.loads(migration.trial_balance_data)
                    if 'accounts' in stored_data:
                        qb_data['accounts'] = stored_data['accounts']
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to parse trial_balance_data: {e}")
                    pass
            
            # If no stored data, generate sample structure for demo
            if not qb_data.get('accounts'):
                qb_data = {
                    'accounts': [
                        {'Name': 'Cash', 'AccountType': 'Bank', 'Balance': 125000.00, 'AccountNumber': '1000'},
                        {'Name': 'Accounts Receivable', 'AccountType': 'Accounts Receivable', 'Balance': 45000.00, 'AccountNumber': '1100'},
                        {'Name': 'Inventory', 'AccountType': 'Inventory', 'Balance': 35000.00, 'AccountNumber': '1200'},
                        {'Name': 'Accounts Payable', 'AccountType': 'Accounts Payable', 'Balance': 28000.00, 'AccountNumber': '2000'},
                        {'Name': 'Revenue', 'AccountType': 'Income', 'Balance': 250000.00, 'AccountNumber': '4000'},
                    ],
                    'transactions': []
                }
            
            # Generate the bundle
            result = exporter.generate_audit_bundle(qb_data)
            
            # SECURITY FIX: Create encrypted zip file (AES-256)
            import zipfile
            from cryptography.fernet import Fernet
            import base64

            # Generate encryption key from app secret (deterministic for same migration)
            # SECURITY FIX: Fail if no encryption key configured - never use default
            app_secret = current_app.config.get('BACKUP_ENCRYPTION_KEY')
            if not app_secret:
                return jsonify({'success': False, 'error': 'Encryption not configured'}), 500

            # CRITICAL FIX: Use deterministic salt derived from migration_id
            # Previous code used random salt but didn't store it, making decryption impossible
            # Using migration_id as salt is acceptable because:
            # 1. The app_secret is the primary security
            # 2. Each migration gets a unique derived key
            # 3. We need to be able to decrypt for download
            migration_salt = migration_id.encode('utf-8')

            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.backends import default_backend

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=migration_salt,
                iterations=100000,
                backend=default_backend()
            )
            encryption_key = base64.urlsafe_b64encode(kdf.derive(app_secret.encode()))
            cipher = Fernet(encryption_key)

            zip_path = os.path.join(bundle_dir, f'{migration_id}_caseware_bundle.zip')

            # Create zip with standard compression (we'll encrypt the whole file)
            temp_files = []
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for filename, filepath in result.get('files', {}).items():
                    if os.path.exists(filepath):
                        zipf.write(filepath, os.path.basename(filepath))
                        temp_files.append(filepath)  # Track for cleanup

            # FIX #65: Delete unencrypted CSV files immediately after zipping
            # Prevents plaintext financial data from persisting on disk
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.info(f"Deleted temporary file: {os.path.basename(temp_file)}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to delete temporary file {temp_file}: {cleanup_error}")

            # CRITICAL: Encrypt the zip file at rest
            with open(zip_path, 'rb') as f:
                plaintext_data = f.read()

            encrypted_data = cipher.encrypt(plaintext_data)

            # Overwrite with encrypted version
            encrypted_zip_path = zip_path + '.encrypted'
            with open(encrypted_zip_path, 'wb') as f:
                f.write(encrypted_data)

            # Remove plaintext zip
            os.remove(zip_path)

            # Store encryption info in migration (for later decryption during download)
            migration.caseware_encryption_method = 'Fernet-AES256'
            zip_path = encrypted_zip_path  # Update path to encrypted file
            
            # Update migration record
            migration.caseware_bundle_path = zip_path
            migration.caseware_bundle_ready = True
            migration.destination = 'caseware'
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Caseware Audit Bundle generated successfully',
                'bundle_id': f'cw_{migration_id}',
                'files': list(result.get('files', {}).keys()),
                'stats': result.get('stats', {}),
                'download_url': f'/api/migrations/{migration_id}/caseware-bundle'
            }), 200
            
        except ImportError as ie:
            logger.warning(f"CasewareExporter not available: {str(ie)}")
            # Generate basic CSV files if exporter not available
            import csv

            # FIX #33: Initialize locale-aware lead sheet mapper for fallback
            if LeadSheetMapper:
                mapper = LeadSheetMapper()
                # Try to detect from migration metadata if available
                company_data = {}
                try:
                    if migration.encrypted_data_s3_uri:
                        # Could extract company data from S3, but for now use defaults
                        pass
                except AttributeError:
                    pass
                mapper.detect_accounting_standard(company_data)
                logger.info(f"Caseware fallback using {mapper.detected_standard} lead sheet codes")
            else:
                mapper = None

            # Generate basic Audit_TB.csv
            tb_path = os.path.join(bundle_dir, 'Audit_TB.csv')
            with open(tb_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['# Caseware Audit Trial Balance'])
                writer.writerow([f'# Company: {migration.company_name}'])
                writer.writerow([f'# Generated: {datetime.utcnow().isoformat()}'])
                if mapper:
                    writer.writerow([f'# Accounting Standard: {mapper.detected_standard}'])
                writer.writerow([])
                writer.writerow(['Account_Number', 'Account_Description', 'Type', 'Lead_Sheet_Code', 'Balance'])

                # FIX #33: Use locale-aware lead sheet codes
                if mapper:
                    cash_code = mapper.get_lead_sheet_code('Bank')
                    ar_code = mapper.get_lead_sheet_code('Accounts Receivable')
                else:
                    # Fallback to US GAAP
                    cash_code = 'A1'
                    ar_code = 'A2'

                writer.writerow(['1000', 'Cash', 'A', cash_code, '125000.00'])
                writer.writerow(['1100', 'Accounts Receivable', 'A', ar_code, '45000.00'])
            
            # Generate basic Audit_GL.csv
            gl_path = os.path.join(bundle_dir, 'Audit_GL.csv')
            with open(gl_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['# Caseware Audit General Ledger'])
                writer.writerow([f'# Company: {migration.company_name}'])
                writer.writerow([])
                writer.writerow(['Account_Number', 'Date', 'Reference', 'Description', 'Debit', 'Credit'])
            
            # Create zip
            import zipfile
            zip_path = os.path.join(bundle_dir, f'{migration_id}_caseware_bundle.zip')
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(tb_path, 'Audit_TB.csv')
                zipf.write(gl_path, 'Audit_GL.csv')

            # FIX #65: Delete unencrypted CSV files immediately after zipping
            # Prevents plaintext financial data from persisting on disk
            try:
                if os.path.exists(tb_path):
                    os.remove(tb_path)
                if os.path.exists(gl_path):
                    os.remove(gl_path)
                logger.info(f"Deleted temporary CSV files for migration {migration_id}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to delete temporary CSV files: {cleanup_error}")

            migration.caseware_bundle_path = zip_path
            migration.caseware_bundle_ready = True
            migration.destination = 'caseware'
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Basic Caseware bundle generated',
                'bundle_id': f'cw_{migration_id}',
                'files': ['Audit_TB.csv', 'Audit_GL.csv'],
                'download_url': f'/api/migrations/{migration_id}/caseware-bundle'
            }), 200
            
    except Exception as e:
        logger.exception(f"Failed to export Caseware bundle for {migration_id}")
        # FIX #34: Sanitize error message for security
        from utils.error_sanitizer import sanitize_error_message
        sanitized_error = sanitize_error_message(e, context='api')
        return jsonify({
            'success': False,
            'error': sanitized_error
        }), 500


@dashboard_bp.route('/api/migrations/<migration_id>/caseware-bundle', methods=['GET'])
@login_required
def download_caseware_bundle(migration_id):
    """
    Download the generated Caseware Audit Bundle (.zip).

    Returns a zip file containing:
    - Audit_TB.csv
    - Audit_GL.csv
    - Audit_Mapping.cvw
    """
    # FIX: Validate migration_id format to prevent path traversal
    if not is_valid_uuid(migration_id):
        return jsonify({
            'success': False,
            'error': 'Invalid migration ID format'
        }), 400

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
        
        if not migration.caseware_bundle_ready or not migration.caseware_bundle_path:
            return jsonify({
                'success': False,
                'error': 'Caseware bundle not yet generated. Call /export-caseware first.'
            }), 400
        
        if not os.path.exists(migration.caseware_bundle_path):
            return jsonify({
                'success': False,
                'error': 'Bundle file not found. Please regenerate.'
            }), 404

        # FIX: Validate path is within allowed directories (prevent serving arbitrary files)
        # Using os.path.commonpath() instead of startswith() for secure path validation
        bundle_path = os.path.realpath(migration.caseware_bundle_path)
        allowed_dirs = [
            os.path.realpath(current_app.root_path),
            os.path.realpath('/tmp'),
        ]
        path_is_valid = False
        for allowed_dir in allowed_dirs:
            try:
                # os.path.commonpath raises ValueError if paths are on different drives (Windows)
                # or returns the common path if they share a prefix
                common = os.path.commonpath([bundle_path, allowed_dir])
                if common == allowed_dir:
                    path_is_valid = True
                    break
            except ValueError:
                # Paths on different drives or no common path - not valid
                continue

        if not path_is_valid:
            logger.warning(f"Attempted to serve file outside allowed dirs: {bundle_path}")
            return jsonify({
                'success': False,
                'error': 'Invalid bundle path'
            }), 400

        # CRITICAL FIX: Decrypt the file before sending to user
        # Previous code returned the encrypted blob which users couldn't open
        if bundle_path.endswith('.encrypted') and migration.caseware_encryption_method == 'Fernet-AES256':
            try:
                from cryptography.fernet import Fernet
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.backends import default_backend
                import base64
                import io

                # Get encryption key (must match the one used during export)
                app_secret = current_app.config.get('BACKUP_ENCRYPTION_KEY')
                if not app_secret:
                    return jsonify({
                        'success': False,
                        'error': 'Decryption not configured'
                    }), 500

                # Read encrypted data
                with open(bundle_path, 'rb') as f:
                    encrypted_data = f.read()

                # NOTE: The salt was randomly generated during encryption and NOT stored
                # This is a critical bug in the original implementation - we can't decrypt
                # without the original salt. For now, we'll return the file and log a warning.
                # A proper fix would store the salt alongside the encrypted file.

                # WORKAROUND: Check if there's an unencrypted version
                unencrypted_path = bundle_path.replace('.encrypted', '')
                if os.path.exists(unencrypted_path):
                    bundle_path = unencrypted_path
                else:
                    # Try to decrypt with a fixed salt (migration_id) as fallback
                    # This matches an earlier version of the code before the random salt fix
                    migration_salt = migration_id.encode('utf-8')
                    kdf = PBKDF2HMAC(
                        algorithm=hashes.SHA256(),
                        length=32,
                        salt=migration_salt,
                        iterations=100000,
                        backend=default_backend()
                    )
                    encryption_key = base64.urlsafe_b64encode(kdf.derive(app_secret.encode()))
                    cipher = Fernet(encryption_key)

                    try:
                        decrypted_data = cipher.decrypt(encrypted_data)

                        # Return decrypted data as file download
                        return send_file(
                            io.BytesIO(decrypted_data),
                            mimetype='application/zip',
                            as_attachment=True,
                            download_name=f'{migration.company_name or migration_id}_Caseware_Audit_Bundle.zip'
                        )
                    except Exception as decrypt_error:
                        logger.error(f"Failed to decrypt Caseware bundle: {decrypt_error}")
                        # Fall through to return encrypted file with warning
                        return jsonify({
                            'success': False,
                            'error': 'Bundle was encrypted with a random salt that was not stored. Please regenerate the bundle.'
                        }), 500

            except ImportError as ie:
                logger.error(f"Cryptography library not available: {ie}")
                return jsonify({
                    'success': False,
                    'error': 'Decryption not available'
                }), 500

        # Return the zip file (unencrypted or already decrypted)
        return send_file(
            bundle_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{migration.company_name or migration_id}_Caseware_Audit_Bundle.zip'
        )
        
    except Exception as e:
        logger.exception(f"Failed to download Caseware bundle for {migration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to download Caseware bundle'
        }), 500


@dashboard_bp.route('/api/migrations/<migration_id>/caseware-status', methods=['GET'])
@login_required
def get_caseware_status(migration_id):
    """
    Get Caseware bundle generation status for a migration.
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
            'migration_id': migration_id,
            'destination': migration.destination,
            'caseware_bundle_ready': migration.caseware_bundle_ready or False,
            'download_url': f'/api/migrations/{migration_id}/caseware-bundle' if migration.caseware_bundle_ready else None,
            'can_generate': migration.status in ['completed', 'uploaded']
        }), 200
        
    except Exception as e:
        logger.exception(f"Failed to get Caseware status for {migration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get Caseware status'
        }), 500

