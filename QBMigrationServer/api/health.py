"""
Health Check Blueprint
=====================
Provides health check endpoint for monitoring, load balancers, and testing.

Enhanced with:
- Canadian Data Residency Verification (ca-central-1)
- S3 bucket location validation
- Multi-AZ status
"""

from flask import Blueprint, jsonify, current_app
from sqlalchemy import text
from models.database import db
import os
import logging

logger = logging.getLogger(__name__)

health_bp = Blueprint('health', __name__)

# Canadian Data Residency Enforcement
REQUIRED_REGION = 'ca-central-1'  # Montreal


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
        'canadian_residency': False,
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
        
        # Verify Canadian Data Residency
        if aws_region == REQUIRED_REGION:
            health_status['canadian_residency'] = True
            health_status['data_residency_region'] = 'ca-central-1 (Montreal)'
        else:
            health_status['status'] = 'degraded'
            health_status['canadian_residency'] = False
            health_status['data_residency_warning'] = f"Region '{aws_region}' does not meet Canadian data residency requirements. Must use '{REQUIRED_REGION}'."
    
    # Add timestamp
    from datetime import datetime
    health_status['timestamp'] = datetime.utcnow().isoformat()
    
    # Return appropriate status code
    status_code = 200 if health_status['status'] == 'healthy' else 503
    
    return jsonify(health_status), status_code


@health_bp.route('/api/health/detailed', methods=['GET'])
def detailed_health_check():
    """
    Detailed health check with full compliance verification.
    Used for enterprise deployment validation.
    """
    from datetime import datetime
    
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'checks': {}
    }
    
    # 1. Database Check
    try:
        db.session.execute(text('SELECT 1'))
        health_status['checks']['database'] = {'status': 'pass', 'message': 'Connected'}
    except Exception as e:
        health_status['checks']['database'] = {'status': 'fail', 'message': str(e)}
        health_status['status'] = 'unhealthy'
    
    # 2. Canadian Data Residency Check
    aws_region = current_app.config.get('AWS_REGION', 'not_configured')
    if aws_region == REQUIRED_REGION:
        health_status['checks']['canadian_residency'] = {
            'status': 'pass',
            'region': aws_region,
            'location': 'Montreal, Quebec, Canada'
        }
    else:
        health_status['checks']['canadian_residency'] = {
            'status': 'fail',
            'region': aws_region,
            'required': REQUIRED_REGION,
            'message': 'Data residency violation - must use ca-central-1'
        }
        health_status['status'] = 'unhealthy'
    
    # 3. S3 Bucket Location Verification
    aws_bucket = current_app.config.get('AWS_S3_BUCKET')
    if aws_bucket:
        try:
            import boto3
            s3 = boto3.client('s3', region_name=aws_region)
            response = s3.get_bucket_location(Bucket=aws_bucket)
            bucket_location = response.get('LocationConstraint') or 'us-east-1'
            
            if bucket_location == REQUIRED_REGION:
                health_status['checks']['s3_bucket'] = {
                    'status': 'pass',
                    'bucket': aws_bucket,
                    'location': bucket_location
                }
            else:
                health_status['checks']['s3_bucket'] = {
                    'status': 'fail',
                    'bucket': aws_bucket,
                    'location': bucket_location,
                    'required': REQUIRED_REGION,
                    'message': 'S3 bucket not in required region'
                }
                health_status['status'] = 'unhealthy'
        except Exception as e:
            health_status['checks']['s3_bucket'] = {
                'status': 'warn',
                'bucket': aws_bucket,
                'message': f'Could not verify: {str(e)}'
            }
    
    # 4. SSO Configuration Check
    sso_enabled = current_app.config.get('ENABLE_SSO', False)
    health_status['checks']['sso'] = {
        'status': 'pass' if sso_enabled else 'info',
        'enabled': sso_enabled,
        'providers': current_app.config.get('SSO_PROVIDERS', [])
    }
    
    # 5. WORM Storage Check
    worm_enabled = current_app.config.get('ENABLE_WORM_STORAGE', False)
    health_status['checks']['worm_storage'] = {
        'status': 'pass' if worm_enabled else 'info',
        'enabled': worm_enabled,
        'retention_years': 7 if worm_enabled else None
    }
    
    # 6. Multi-AZ Check
    multi_az = current_app.config.get('ENABLE_MULTI_AZ', False)
    health_status['checks']['multi_az'] = {
        'status': 'pass' if multi_az else 'info',
        'enabled': multi_az,
        'availability_zones': ['ca-central-1a', 'ca-central-1b', 'ca-central-1d'] if multi_az else []
    }

    # FIX #40: Database Connection Pool Health Check
    try:
        result = db.session.execute(text("""
            SELECT
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections
        """))
        row = result.fetchone()
        if row:
            active_connections, max_connections = row
            pool_usage_pct = (active_connections / max_connections) * 100 if max_connections > 0 else 0

            status = 'pass'
            if pool_usage_pct >= 90:
                status = 'warn'
            if pool_usage_pct >= 95:
                status = 'critical'

            health_status['checks']['connection_pool'] = {
                'status': status,
                'active_connections': active_connections,
                'max_connections': max_connections,
                'usage_percent': round(pool_usage_pct, 2)
            }

            if status in ('warn', 'critical'):
                health_status['status'] = 'degraded'
    except Exception as e:
        health_status['checks']['connection_pool'] = {
            'status': 'unknown',
            'message': f'Could not check: {str(e)}'
        }

    # FIX #40: AWS S3 Service Connectivity Check
    try:
        import boto3
        from botocore.exceptions import ClientError
        s3 = boto3.client('s3', region_name=aws_region)

        # Simple connectivity test - list buckets
        s3.list_buckets()

        health_status['checks']['aws_s3_service'] = {
            'status': 'pass',
            'message': 'S3 service reachable'
        }
    except ClientError as e:
        health_status['checks']['aws_s3_service'] = {
            'status': 'fail',
            'message': f'S3 service error: {e.response["Error"]["Code"]}'
        }
        health_status['status'] = 'unhealthy'
    except Exception as e:
        health_status['checks']['aws_s3_service'] = {
            'status': 'fail',
            'message': f'Cannot reach S3: {str(e)}'
        }
        health_status['status'] = 'unhealthy'

    # FIX #40: QuickBooks Online API Connectivity Check (optional)
    try:
        import requests
        # Check QBO API status page or a lightweight endpoint
        # Using a simple HTTP check to verify network connectivity
        qbo_status_response = requests.get(
            'https://status.quickbooks.com/api/v2/status.json',
            timeout=5
        )

        if qbo_status_response.status_code == 200:
            health_status['checks']['qbo_api'] = {
                'status': 'pass',
                'message': 'QuickBooks Online API reachable'
            }
        else:
            health_status['checks']['qbo_api'] = {
                'status': 'warn',
                'message': f'QBO API returned {qbo_status_response.status_code}'
            }
    except requests.exceptions.Timeout:
        health_status['checks']['qbo_api'] = {
            'status': 'fail',
            'message': 'QBO API timeout'
        }
        health_status['status'] = 'degraded'
    except requests.exceptions.RequestException as e:
        health_status['checks']['qbo_api'] = {
            'status': 'fail',
            'message': f'Cannot reach QBO API: {str(e)}'
        }
        health_status['status'] = 'degraded'
    except Exception:
        # Requests library not available - skip this check
        health_status['checks']['qbo_api'] = {
            'status': 'skipped',
            'message': 'Requests library not available'
        }

    # FIX #40: Encryption Service Check
    encryption_key = os.getenv('ENCRYPTION_KEY')
    encryption_key_b64 = os.getenv('ENCRYPTION_KEY_B64')

    if encryption_key or encryption_key_b64:
        health_status['checks']['encryption'] = {
            'status': 'pass',
            'configured': True,
            'key_source': 'ENCRYPTION_KEY_B64' if encryption_key_b64 else 'ENCRYPTION_KEY'
        }
    else:
        health_status['checks']['encryption'] = {
            'status': 'fail',
            'configured': False,
            'message': 'No encryption key configured'
        }
        health_status['status'] = 'unhealthy'

    # FIX #50: Redis Health Check - Critical for rate limiting
    redis_url = current_app.config.get('REDIS_URL', os.getenv('REDIS_URL', 'memory://'))
    if redis_url and not redis_url.startswith('memory://'):
        try:
            import redis
            r = redis.from_url(redis_url, socket_connect_timeout=5)
            r.ping()
            health_status['checks']['redis'] = {
                'status': 'pass',
                'message': 'Redis connected',
                'mode': 'distributed'
            }
        except ImportError:
            health_status['checks']['redis'] = {
                'status': 'warn',
                'message': 'Redis library not installed',
                'mode': 'unknown'
            }
        except redis.ConnectionError as e:
            health_status['checks']['redis'] = {
                'status': 'fail',
                'message': f'Redis connection failed: {str(e)}',
                'mode': 'disconnected'
            }
            health_status['status'] = 'degraded'
            logger.warning(f"Redis health check failed: {e}")
        except redis.TimeoutError:
            health_status['checks']['redis'] = {
                'status': 'fail',
                'message': 'Redis connection timeout',
                'mode': 'timeout'
            }
            health_status['status'] = 'degraded'
        except Exception as e:
            health_status['checks']['redis'] = {
                'status': 'fail',
                'message': f'Redis error: {str(e)}',
                'mode': 'error'
            }
            health_status['status'] = 'degraded'
    else:
        # Using in-memory rate limiting - warn about this
        health_status['checks']['redis'] = {
            'status': 'warn',
            'message': 'Using in-memory rate limiting (not distributed)',
            'mode': 'memory',
            'warning': 'Rate limiting will not persist across restarts or scale across instances'
        }

    status_code = 200 if health_status['status'] in ('healthy', 'degraded') else 503
    return jsonify(health_status), status_code


@health_bp.route('/api/health/compliance', methods=['GET'])
def compliance_check():
    """
    Compliance verification endpoint for enterprise audits.
    Returns all compliance-relevant configuration.
    """
    from datetime import datetime
    
    compliance = {
        'timestamp': datetime.utcnow().isoformat(),
        'data_residency': {
            'requirement': 'Canadian Data Residency',
            'region': current_app.config.get('AWS_REGION', 'not_configured'),
            'required_region': REQUIRED_REGION,
            'compliant': current_app.config.get('AWS_REGION') == REQUIRED_REGION
        },
        'encryption': {
            's3_encryption': current_app.config.get('AWS_S3_ENCRYPTION', 'AES256'),
            'customer_managed_keys': current_app.config.get('ENABLE_CMK', False)
        },
        'retention': {
            'financial_data_ttl_hours': current_app.config.get('AWS_S3_FILE_TTL_HOURS', 24),
            'metadata_archival_years': 7,
            'worm_enabled': current_app.config.get('ENABLE_WORM_STORAGE', False)
        },
        'authentication': {
            'sso_enabled': current_app.config.get('ENABLE_SSO', False),
            'mfa_enabled': current_app.config.get('ENABLE_2FA', False)
        },
        'high_availability': {
            'multi_az_enabled': current_app.config.get('ENABLE_MULTI_AZ', False)
        }
    }
    
    return jsonify(compliance)
