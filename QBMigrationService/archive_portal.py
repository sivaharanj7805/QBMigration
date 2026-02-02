"""
Active Archival Web Portal - Flask API
Provides a read-only web interface for searching archived QuickBooks data.
This is the backend for the "Data Museum" feature.
"""

import json
import os
import re
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from functools import wraps

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
ARCHIVE_DIR = os.environ.get('ARCHIVE_DIR', './archives')

# CRITICAL FIX: Fail-closed if API key is not configured or is the insecure default
# This prevents accidental production deployments with weak credentials
_api_key = os.environ.get('ARCHIVE_API_KEY', '')
if not _api_key or _api_key == 'dev-key-changeme':
    _is_production = os.environ.get('FLASK_ENV', 'development') == 'production'
    if _is_production:
        raise RuntimeError(
            "CRITICAL: ARCHIVE_API_KEY environment variable must be set to a strong value in production. "
            "Do not use the default 'dev-key-changeme' value."
        )
    else:
        logger.warning(
            "ARCHIVE_API_KEY not configured - using insecure default for development. "
            "Set ARCHIVE_API_KEY environment variable for production."
        )
        _api_key = 'dev-key-changeme'  # Only allowed in development

API_KEY = _api_key


# CRITICAL FIX: Archive ID validation to prevent path traversal attacks
def validate_archive_id(archive_id: str) -> bool:
    """
    Validate archive_id format to prevent path traversal attacks.

    Only allows alphanumeric characters, underscores, and hyphens.
    Maximum length of 100 characters.

    Args:
        archive_id: The archive ID to validate

    Returns:
        True if valid, False otherwise
    """
    if not archive_id or not isinstance(archive_id, str):
        return False

    # Maximum length check
    if len(archive_id) > 100:
        return False

    # Only allow alphanumeric, underscores, hyphens
    # This prevents path traversal (../, /, etc.)
    if not re.match(r'^[a-zA-Z0-9_-]+$', archive_id):
        return False

    return True

# Simple API key authentication
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key')
        if key != API_KEY:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated


def load_index():
    """Load the main archive index."""
    index_path = os.path.join(ARCHIVE_DIR, 'archive_index.json')
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            return json.load(f)
    return {'Entries': []}


def load_transactions(archive_id):
    """Load transactions for a specific archive."""
    index = load_index()
    entry = next((e for e in index['Entries'] if e['ArchiveId'] == archive_id), None)
    if not entry:
        return []
    
    txn_path = os.path.join(entry['ArchivePath'], 'transactions_index.json')
    if os.path.exists(txn_path):
        with open(txn_path, 'r') as f:
            return json.load(f)
    return []


def log_access(archive_id, user_id, action):
    """Log access for audit trail."""
    log_path = os.path.join(ARCHIVE_DIR, 'audit_log.ndjson')
    entry = {
        'Timestamp': datetime.now().isoformat(),
        'ArchiveId': archive_id,
        'UserId': user_id,
        'Action': action,
        'IpAddress': request.remote_addr or 'unknown'
    }
    with open(log_path, 'a') as f:
        f.write(json.dumps(entry) + '\n')


# ============ API ENDPOINTS ============

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'archive_count': len(load_index().get('Entries', []))
    })


@app.route('/api/archives', methods=['GET'])
@require_api_key
def list_archives():
    """List all active archives."""
    index = load_index()
    entries = [e for e in index.get('Entries', []) if e.get('Status') == 'Active']
    
    return jsonify({
        'count': len(entries),
        'archives': [{
            'id': e['ArchiveId'],
            'company': e['CompanyName'],
            'created': e['CreatedAt'],
            'transaction_count': e.get('TransactionCount', 0)
        } for e in entries]
    })


@app.route('/api/archives/<archive_id>', methods=['GET'])
@require_api_key
def get_archive(archive_id):
    """Get details of a specific archive."""
    # CRITICAL FIX: Validate archive_id to prevent path traversal attacks
    if not validate_archive_id(archive_id):
        logger.warning(f"Invalid archive_id attempted: {archive_id[:50] if archive_id else 'None'}")
        return jsonify({'error': 'Invalid archive ID format'}), 400

    index = load_index()
    entry = next((e for e in index['Entries'] if e['ArchiveId'] == archive_id), None)
    
    if not entry:
        return jsonify({'error': 'Archive not found'}), 404
    
    log_access(archive_id, request.headers.get('X-User-Id', 'anonymous'), 'VIEW_ARCHIVE')
    
    return jsonify({
        'id': entry['ArchiveId'],
        'company': entry['CompanyName'],
        'created': entry['CreatedAt'],
        'status': entry.get('Status', 'Active'),
        'transaction_count': entry.get('TransactionCount', 0),
        'source_path': entry.get('SourcePath', ''),
        'archive_path': entry.get('ArchivePath', '')
    })


@app.route('/api/archives/<archive_id>/transactions', methods=['GET'])
@require_api_key
def search_transactions(archive_id):
    """Search transactions in an archive."""
    # CRITICAL FIX: Validate archive_id to prevent path traversal attacks
    if not validate_archive_id(archive_id):
        logger.warning(f"Invalid archive_id in transactions search: {archive_id[:50] if archive_id else 'None'}")
        return jsonify({'error': 'Invalid archive ID format'}), 400

    transactions = load_transactions(archive_id)
    
    if not transactions:
        return jsonify({'error': 'No transactions found'}), 404
    
    # Apply filters from query params
    txn_type = request.args.get('type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    min_amount = request.args.get('min_amount', type=float)
    max_amount = request.args.get('max_amount', type=float)
    search = request.args.get('q', '').lower()
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    results = transactions
    
    if txn_type:
        results = [t for t in results if t.get('Type', '').lower() == txn_type.lower()]
    
    if date_from:
        results = [t for t in results if t.get('Date', '') >= date_from]
    
    if date_to:
        results = [t for t in results if t.get('Date', '') <= date_to]
    
    if min_amount is not None:
        results = [t for t in results if t.get('Amount', 0) >= min_amount]
    
    if max_amount is not None:
        results = [t for t in results if t.get('Amount', 0) <= max_amount]
    
    if search:
        results = [t for t in results if 
                   search in (t.get('Memo') or '').lower() or
                   search in (t.get('EntityName') or '').lower() or
                   search in (t.get('Number') or '').lower()]
    
    total = len(results)
    results = results[offset:offset + limit]
    
    log_access(archive_id, request.headers.get('X-User-Id', 'anonymous'), f'SEARCH_TRANSACTIONS (q={search})')
    
    return jsonify({
        'total': total,
        'limit': limit,
        'offset': offset,
        'transactions': [{
            'id': t.get('Id'),
            'type': t.get('Type'),
            'number': t.get('Number'),
            'date': t.get('Date'),
            'amount': t.get('Amount'),
            'memo': t.get('Memo'),
            'entity': t.get('EntityName')
        } for t in results]
    })


@app.route('/api/archives/<archive_id>/transactions/<txn_id>', methods=['GET'])
@require_api_key
def get_transaction(archive_id, txn_id):
    """Get a specific transaction with full details."""
    # CRITICAL FIX: Validate archive_id to prevent path traversal attacks
    if not validate_archive_id(archive_id):
        logger.warning(f"Invalid archive_id in transaction get: {archive_id[:50] if archive_id else 'None'}")
        return jsonify({'error': 'Invalid archive ID format'}), 400

    # Also validate txn_id
    if not txn_id or not isinstance(txn_id, str) or len(txn_id) > 100:
        return jsonify({'error': 'Invalid transaction ID format'}), 400

    transactions = load_transactions(archive_id)
    txn = next((t for t in transactions if t.get('Id') == txn_id), None)
    
    if not txn:
        return jsonify({'error': 'Transaction not found'}), 404
    
    log_access(archive_id, request.headers.get('X-User-Id', 'anonymous'), f'VIEW_TRANSACTION ({txn_id})')
    
    return jsonify({
        'id': txn.get('Id'),
        'archive_id': archive_id,
        'type': txn.get('Type'),
        'number': txn.get('Number'),
        'date': txn.get('Date'),
        'amount': txn.get('Amount'),
        'memo': txn.get('Memo'),
        'entity': txn.get('EntityName'),
        'raw_json': txn.get('RawJson')
    })


@app.route('/api/audit-log', methods=['GET'])
@require_api_key
def get_audit_log():
    """Get audit log entries."""
    log_path = os.path.join(ARCHIVE_DIR, 'audit_log.ndjson')
    entries = []
    
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
    
    # Return most recent first
    entries.reverse()
    
    limit = request.args.get('limit', 100, type=int)
    return jsonify({
        'total': len(entries),
        'entries': entries[:limit]
    })


# ============ WEB UI ============

PORTAL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>QuickBooks Archive Portal</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #f5f5f5; }
        .header { background: linear-gradient(135deg, #2CA01C, #1a6b12); color: white; padding: 20px 40px; }
        .header h1 { font-size: 24px; }
        .container { max-width: 1200px; margin: 20px auto; padding: 0 20px; }
        .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .search-box { display: flex; gap: 10px; margin-bottom: 20px; }
        .search-box input, .search-box select { padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        .search-box input[type="text"] { flex: 1; }
        .search-box button { background: #2CA01C; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f8f8; }
        .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
        .badge-invoice { background: #e3f2fd; color: #1565c0; }
        .badge-bill { background: #fff3e0; color: #e65100; }
        .badge-check { background: #e8f5e9; color: #2e7d32; }
        .amount { text-align: right; font-family: monospace; }
        .footer { text-align: center; padding: 20px; color: #888; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📦 QuickBooks Archive Portal</h1>
        <p>Historical Data Access (Read-Only)</p>
    </div>
    <div class="container">
        <div class="card">
            <h2>Search Archived Transactions</h2>
            <div class="search-box">
                <select id="archiveSelect">
                    <option value="">Select Archive...</option>
                </select>
                <input type="text" id="searchInput" placeholder="Search by memo, entity, or number...">
                <select id="typeSelect">
                    <option value="">All Types</option>
                    <option value="Invoice">Invoice</option>
                    <option value="Bill">Bill</option>
                    <option value="Check">Check</option>
                    <option value="Payment">Payment</option>
                    <option value="JournalEntry">Journal Entry</option>
                </select>
                <button onclick="search()">🔍 Search</button>
            </div>
        </div>
        <div class="card">
            <h3>Results</h3>
            <table>
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>Number</th>
                        <th>Date</th>
                        <th>Entity</th>
                        <th>Memo</th>
                        <th class="amount">Amount</th>
                    </tr>
                </thead>
                <tbody id="resultsBody">
                    <tr><td colspan="6" style="text-align:center;color:#888;">Select an archive and search to see results</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    <div class="footer">
        <p>QuickBooks Archive Portal v1.0 | Data is read-only and audited</p>
    </div>
    <script>
        // FIX CRIT-02: API key is now injected from server-side environment variable
        // This prevents hardcoded credentials in frontend code
        const API_KEY = '{{ api_key }}';

        // FIX CRIT-03: HTML escaping function to prevent XSS attacks
        // All user-controlled data must be escaped before inserting into DOM
        function escapeHtml(text) {
            if (text === null || text === undefined) return '';
            const div = document.createElement('div');
            div.textContent = String(text);
            return div.innerHTML;
        }

        async function loadArchives() {
            const res = await fetch('/api/archives', { headers: { 'X-API-Key': API_KEY } });
            const data = await res.json();
            const select = document.getElementById('archiveSelect');
            data.archives.forEach(a => {
                const opt = document.createElement('option');
                opt.value = a.id;
                opt.textContent = `${a.company} (${a.transaction_count} transactions)`;
                select.appendChild(opt);
            });
        }
        
        async function search() {
            const archiveId = document.getElementById('archiveSelect').value;
            if (!archiveId) { alert('Please select an archive'); return; }
            
            const q = document.getElementById('searchInput').value;
            const type = document.getElementById('typeSelect').value;
            
            let url = `/api/archives/${archiveId}/transactions?limit=100`;
            if (q) url += `&q=${encodeURIComponent(q)}`;
            if (type) url += `&type=${encodeURIComponent(type)}`;
            
            const res = await fetch(url, { headers: { 'X-API-Key': API_KEY } });
            const data = await res.json();
            
            const tbody = document.getElementById('resultsBody');
            if (data.transactions.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888;">No results found</td></tr>';
                return;
            }
            
            // FIX CRIT-03: Use escapeHtml to prevent XSS from user-controlled data
            tbody.innerHTML = data.transactions.map(t => `
                <tr>
                    <td><span class="badge badge-${escapeHtml((t.type || '').toLowerCase())}">${escapeHtml(t.type)}</span></td>
                    <td>${escapeHtml(t.number) || '-'}</td>
                    <td>${t.date ? new Date(t.date).toLocaleDateString() : '-'}</td>
                    <td>${escapeHtml(t.entity) || '-'}</td>
                    <td>${escapeHtml(t.memo) || '-'}</td>
                    <td class="amount">$${(parseFloat(t.amount) || 0).toFixed(2)}</td>
                </tr>
            `).join('');
        }
        
        loadArchives();
    </script>
</body>
</html>
"""

@app.route('/')
def portal():
    """Render the web portal."""
    # FIX CRIT-02: Pass API key from environment variable to template
    # This prevents hardcoded credentials and allows configuration per environment
    return render_template_string(PORTAL_HTML, api_key=API_KEY)


if __name__ == '__main__':
    # FIX: Use logging instead of print for production-ready code
    logger.info("Starting Active Archival Web Portal...")
    logger.info(f"Archive directory: {ARCHIVE_DIR}")
    # FIX: Bind to localhost only to prevent accidental network exposure
    # In production, use a proper WSGI server (gunicorn) with reverse proxy
    app.run(host='127.0.0.1', port=5001, debug=False)
