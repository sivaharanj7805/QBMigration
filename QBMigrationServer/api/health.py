"""
Health Check Blueprint
=====================
Provides health check endpoint for monitoring, load balancers, and testing.
"""

from flask import Blueprint, jsonify, current_app
from sqlalchemy import text
from models.database import db
import os

health_bp = Blueprint('health', __name__)

@health_bp.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    Returns server status, database connectivity, and configuration info
    """
    
    health_status = {
        'status': 'healthy',
        'environment': current_app.config.get('ENV', 'unknown'),
        'database': 'unknown',
        'aws_configured': False,
        'timestamp': None
    }
    
    # Check database connectivity
    try:
        db.session.execute(text('SELECT 1'))
        health_status['database'] = 'connected'
    except Exception as e:
        health_status['status'] = 'degraded'
        health_status['database'] = 'disconnected'
        current_app.logger.error(f"Database health check failed: {str(e)}")
    
    # Check AWS configuration
    aws_bucket = current_app.config.get('AWS_S3_BUCKET')
    aws_region = current_app.config.get('AWS_REGION')
    if aws_bucket and aws_region:
        health_status['aws_configured'] = True
        health_status['aws_region'] = aws_region
    
    # Add timestamp
    from datetime import datetime
    health_status['timestamp'] = datetime.utcnow().isoformat()
    
    # Return appropriate status code
    status_code = 200 if health_status['status'] == 'healthy' else 503
    
    return jsonify(health_status), status_code