"""
Webhook Delivery Log
====================
Provides visibility into webhook delivery status for the dashboard.
Users can see exactly when the server acknowledged status updates from workers.

Features:
- Persistent delivery log in database
- Dashboard API endpoints
- Delivery analytics
"""

from flask import Blueprint, request, jsonify
from models.database import db
from datetime import datetime, timedelta
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

webhook_logs_bp = Blueprint('webhook_logs', __name__, url_prefix='/api/webhook-logs')


# =============================================================================
# DATABASE MODEL
# =============================================================================

class WebhookDeliveryLog(db.Model):
    """Stores webhook delivery records for visibility and debugging"""
    
    __tablename__ = 'webhook_delivery_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    webhook_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    migration_id = db.Column(db.String(64), nullable=False, index=True)
    
    # Webhook metadata
    webhook_type = db.Column(db.String(50), nullable=False)  # started, progress, completed, failed
    source_ip = db.Column(db.String(45))  # IPv4 or IPv6
    instance_id = db.Column(db.String(64))
    
    # Timing
    received_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processed_at = db.Column(db.DateTime)
    processing_time_ms = db.Column(db.Integer)
    
    # Status
    status = db.Column(db.String(20), default='received')  # received, verified, processed, rejected
    verification_result = db.Column(db.String(50))  # passed, signature_invalid, expired, replay
    
    # Payload summary (not full payload for privacy)
    payload_summary = db.Column(db.Text)
    
    # Response
    response_code = db.Column(db.Integer)
    error_message = db.Column(db.Text)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'webhook_id': self.webhook_id,
            'migration_id': self.migration_id,
            'webhook_type': self.webhook_type,
            'source_ip': self.source_ip,
            'instance_id': self.instance_id,
            'received_at': self.received_at.isoformat() if self.received_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'processing_time_ms': self.processing_time_ms,
            'status': self.status,
            'verification_result': self.verification_result,
            'response_code': self.response_code,
            'error_message': self.error_message
        }


# =============================================================================
# LOGGING SERVICE
# =============================================================================

class WebhookLogger:
    """Service for logging webhook deliveries"""
    
    @staticmethod
    def log_received(webhook_id: str, migration_id: str, webhook_type: str,
                     source_ip: str = None, instance_id: str = None) -> WebhookDeliveryLog:
        """
        Log that a webhook was received.
        Called at the start of webhook processing.
        """
        log_entry = WebhookDeliveryLog(
            webhook_id=webhook_id,
            migration_id=migration_id,
            webhook_type=webhook_type,
            source_ip=source_ip,
            instance_id=instance_id,
            received_at=datetime.utcnow(),
            status='received'
        )
        
        try:
            db.session.add(log_entry)
            db.session.commit()
            logger.debug(f"Logged webhook received: {webhook_id}")
            return log_entry
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to log webhook: {str(e)}")
            return None
    
    @staticmethod
    def log_verified(webhook_id: str, verification_result: str) -> bool:
        """
        Log webhook verification result.
        """
        try:
            log_entry = WebhookDeliveryLog.query.filter_by(webhook_id=webhook_id).first()
            if log_entry:
                log_entry.verification_result = verification_result
                log_entry.status = 'verified' if verification_result == 'passed' else 'rejected'
                db.session.commit()
                return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update webhook log: {str(e)}")
        return False
    
    @staticmethod
    def log_processed(webhook_id: str, response_code: int, 
                      error_message: str = None) -> bool:
        """
        Log webhook processing completion.
        """
        try:
            log_entry = WebhookDeliveryLog.query.filter_by(webhook_id=webhook_id).first()
            if log_entry:
                log_entry.processed_at = datetime.utcnow()
                log_entry.processing_time_ms = int(
                    (log_entry.processed_at - log_entry.received_at).total_seconds() * 1000
                )
                log_entry.response_code = response_code
                log_entry.error_message = error_message
                log_entry.status = 'processed' if response_code == 200 else 'failed'
                db.session.commit()
                return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update webhook log: {str(e)}")
        return False
    
    @staticmethod
    def get_logs_for_migration(migration_id: str, limit: int = 50) -> List[dict]:
        """
        Get all webhook logs for a migration.
        """
        logs = WebhookDeliveryLog.query.filter_by(migration_id=migration_id) \
            .order_by(WebhookDeliveryLog.received_at.desc()) \
            .limit(limit).all()
        return [log.to_dict() for log in logs]
    
    @staticmethod
    def get_recent_logs(hours: int = 24, limit: int = 100) -> List[dict]:
        """
        Get recent webhook logs across all migrations.
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        logs = WebhookDeliveryLog.query.filter(
            WebhookDeliveryLog.received_at >= cutoff
        ).order_by(WebhookDeliveryLog.received_at.desc()).limit(limit).all()
        return [log.to_dict() for log in logs]
    
    @staticmethod
    def get_delivery_stats(hours: int = 24) -> dict:
        """
        Get delivery statistics for monitoring dashboard.
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        logs = WebhookDeliveryLog.query.filter(
            WebhookDeliveryLog.received_at >= cutoff
        ).all()
        
        total = len(logs)
        if total == 0:
            return {
                'period_hours': hours,
                'total_webhooks': 0,
                'by_status': {},
                'by_type': {},
                'avg_processing_time_ms': 0,
                'success_rate': 0
            }
        
        by_status = {}
        by_type = {}
        processing_times = []
        successful = 0
        
        for log in logs:
            by_status[log.status] = by_status.get(log.status, 0) + 1
            by_type[log.webhook_type] = by_type.get(log.webhook_type, 0) + 1
            
            if log.processing_time_ms:
                processing_times.append(log.processing_time_ms)
            
            if log.response_code == 200:
                successful += 1
        
        avg_time = sum(processing_times) / len(processing_times) if processing_times else 0
        
        return {
            'period_hours': hours,
            'total_webhooks': total,
            'by_status': by_status,
            'by_type': by_type,
            'avg_processing_time_ms': round(avg_time, 2),
            'success_rate': round(successful / total * 100, 2)
        }


# =============================================================================
# API ENDPOINTS
# =============================================================================

@webhook_logs_bp.route('/migration/<migration_id>', methods=['GET'])
def get_migration_logs(migration_id):
    """
    Get webhook delivery logs for a specific migration.
    Shows users exactly when the server acknowledged status updates.
    """
    limit = request.args.get('limit', 50, type=int)
    logs = WebhookLogger.get_logs_for_migration(migration_id, limit)
    
    return jsonify({
        'migration_id': migration_id,
        'logs': logs,
        'count': len(logs)
    })


@webhook_logs_bp.route('/recent', methods=['GET'])
def get_recent():
    """
    Get recent webhook deliveries across all migrations.
    """
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 100, type=int)
    logs = WebhookLogger.get_recent_logs(hours, limit)
    
    return jsonify({
        'period_hours': hours,
        'logs': logs,
        'count': len(logs)
    })


@webhook_logs_bp.route('/stats', methods=['GET'])
def get_stats():
    """
    Get webhook delivery statistics for monitoring.
    """
    hours = request.args.get('hours', 24, type=int)
    stats = WebhookLogger.get_delivery_stats(hours)
    
    return jsonify(stats)


@webhook_logs_bp.route('/health', methods=['GET'])
def webhook_health():
    """
    Webhook system health check.
    Returns success rate and any concerning patterns.
    """
    stats = WebhookLogger.get_delivery_stats(hours=1)
    
    health = {
        'status': 'healthy',
        'last_hour': stats
    }
    
    # Alert if success rate drops
    if stats['total_webhooks'] > 0 and stats['success_rate'] < 95:
        health['status'] = 'degraded'
        health['warning'] = f"Success rate below 95%: {stats['success_rate']}%"
    
    # Alert if processing time is high
    if stats['avg_processing_time_ms'] > 1000:
        health['status'] = 'degraded'
        health['warning'] = f"High processing time: {stats['avg_processing_time_ms']}ms"
    
    return jsonify(health)
