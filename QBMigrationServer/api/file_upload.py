"""
File Upload API for QuickBooks Desktop exports
Handles IIF, CSV, and Excel file uploads for migration
"""

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
import tempfile
import json
from datetime import datetime

from api.auth import require_auth
from models import db, Migration
import logging


logger = logging.getLogger(__name__)

file_upload_bp = Blueprint('file_upload', __name__, url_prefix='/api/files')

ALLOWED_EXTENSIONS = {'iif', 'csv', 'xls', 'xlsx', 'qbw'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@file_upload_bp.route('/upload', methods=['POST'])
@require_auth
def upload_qb_export():
    """
    Upload QuickBooks Desktop export files (IIF, CSV, Excel)
    
    This replaces the need for the C# extractor + QBFC SDK.
    Users export from QB Desktop manually, then upload here.
    """
    user_id = request.current_user['user_id']
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    session_id = request.form.get('session_id')
    file_type = request.form.get('file_type', 'unknown')  # customers, vendors, etc.
    
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({
            'error': f'File type not allowed. Supported: {", ".join(ALLOWED_EXTENSIONS)}'
        }), 400
    
    # Save file temporarily
    filename = secure_filename(file.filename)
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, filename)
    file.save(file_path)
    
    # Get file size
    file_size = os.path.getsize(file_path)
    
    try:
        # Parse the file
        from services.iif_parser import QuickBooksExportParser
        
        parser = QuickBooksExportParser()
        parsed_data = parser.parse(file_path)
        
        # Create or update migration record
        migration = Migration.query.filter_by(
            session_id=session_id, 
            user_id=user_id
        ).first()
        
        if not migration:
            migration = Migration(
                user_id=user_id,
                session_id=session_id,
                status='parsing',
                ip_address=request.remote_addr
            )
            db.session.add(migration)
        
        migration.data_size_bytes = file_size
        migration.status = 'parsed'
        
        db.session.commit()
        
        # Clean up temp file
        os.remove(file_path)
        os.rmdir(temp_dir)
        
        return jsonify({
            'success': True,
            'migration_id': migration.migration_id,
            'filename': filename,
            'file_size': file_size,
            'summary': parsed_data.get('summary', {}),
            'message': f'File parsed successfully. Found {sum(parsed_data.get("summary", {}).values())} records.'
        })
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)

        # FIX #34: Sanitize error message for security
        from utils.error_sanitizer import sanitize_error_message
        sanitized_error = sanitize_error_message(e, context='upload')
        return jsonify({'error': sanitized_error}), 500


@file_upload_bp.route('/supported-exports', methods=['GET'])
def get_supported_exports():
    """Get list of supported QuickBooks export types"""
    return jsonify({
        'formats': [
            {
                'extension': 'iif',
                'name': 'IIF (Intuit Interchange Format)',
                'description': 'Export from QB Desktop: File > Utilities > Export > Lists/Transactions to IIF'
            },
            {
                'extension': 'csv',
                'name': 'CSV (Comma Separated Values)',
                'description': 'Export reports or lists to Excel, then save as CSV'
            },
            {
                'extension': 'xlsx',
                'name': 'Excel Spreadsheet',
                'description': 'Export reports directly to Excel'
            }
        ],
        'entity_types': [
            'customers',
            'vendors', 
            'items',
            'accounts',
            'invoices',
            'bills',
            'payments',
            'journal_entries',
            'employees'
        ],
        'max_file_size_mb': MAX_FILE_SIZE // (1024 * 1024),
        'instructions': {
            'iif_export': [
                '1. Open QuickBooks Desktop',
                '2. Go to File > Utilities > Export',
                '3. Select "Lists to IIF Files" or "Transactions"',
                '4. Choose what to export (Customers, Vendors, etc.)',
                '5. Save the .IIF file',
                '6. Upload it here'
            ],
            'csv_export': [
                '1. Open QuickBooks Desktop',
                '2. Go to Reports > Customers & Receivables > Customer Contact List',
                '3. Click "Export" at top of report',
                '4. Choose "Export to Excel" or "Export to CSV"',
                '5. Upload the file here'
            ]
        }
    })


@file_upload_bp.route('/export-guide/<entity_type>', methods=['GET'])
def get_export_guide(entity_type):
    """Get specific export instructions for an entity type"""
    
    guides = {
        'customers': {
            'title': 'Export Customer List',
            'steps': [
                'Open QuickBooks Desktop',
                'Go to: Customers > Customer Center',
                'Click "Excel" dropdown at top',
                'Select "Export Customer List"',
                'Save the Excel/CSV file',
                'Upload the file to ForensicBridge'
            ],
            'alternative_iif': [
                'Go to: File > Utilities > Export > Lists to IIF Files',
                'Check "Customer List"',
                'Click OK and save the .IIF file'
            ]
        },
        'vendors': {
            'title': 'Export Vendor List',
            'steps': [
                'Open QuickBooks Desktop',
                'Go to: Vendors > Vendor Center',
                'Click "Excel" dropdown at top',
                'Select "Export Vendor List"',
                'Save the Excel/CSV file',
                'Upload the file to ForensicBridge'
            ]
        },
        'chart_of_accounts': {
            'title': 'Export Chart of Accounts',
            'steps': [
                'Open QuickBooks Desktop',
                'Go to: Lists > Chart of Accounts',
                'Right-click > "Print List"',
                'In Print dialog, choose "File" instead of Printer',
                'Save as Tab-delimited file',
                'Upload the file'
            ],
            'alternative_iif': [
                'Go to: File > Utilities > Export > Lists to IIF Files',
                'Check "Chart of Accounts"',
                'Click OK and save'
            ]
        },
        'items': {
            'title': 'Export Item List',
            'steps': [
                'Open QuickBooks Desktop',
                'Go to: Lists > Item List',
                'Click "Excel" at bottom',
                'Select "Export All Items"',
                'Save the file'
            ]
        },
        'invoices': {
            'title': 'Export Invoices',
            'steps': [
                'Open QuickBooks Desktop',  
                'Go to: Reports > Customers & Receivables > Open Invoices',
                'Or: Reports > Custom Reports > Transaction Detail Report',
                'Set date range as needed',
                'Click "Export" and save as Excel/CSV'
            ]
        },
        'all': {
            'title': 'Export Everything (IIF Bundle)',
            'steps': [
                'Open QuickBooks Desktop',
                'Go to: File > Utilities > Export > Lists to IIF Files',
                'Check ALL boxes (Customer, Vendor, Items, etc.)',
                'Click OK',
                'Save the .IIF file',
                'Upload single file - contains all lists'
            ]
        }
    }
    
    if entity_type not in guides:
        return jsonify({'error': f'Unknown entity type. Available: {list(guides.keys())}'}), 404
    
    return jsonify(guides[entity_type])
