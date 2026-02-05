"""
Health Check Blueprint
=====================
Provides health check endpoint for monitoring, load balancers, and testing.

Enhanced with:
- Canadian Data Residency Verification (ca-central-1)
- S3 bucket location validation
- Multi-AZ status

FIX CRIT-05: Added admin authentication to detailed health endpoint
FIX HIGH-03: Added rate limiting to health endpoints
"""

import hmac
import logging
import os
from datetime import timezone
from functools import wraps

from extensions import limiter
from flask import Blueprint, current_app, jsonify, request
from models.database import db
from sqlalchemy import text

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)

# FIX HIGH-03: Rate limiting for health endpoints
HEALTH_RATE_LIMIT = "60 per minute"
DETAILED_RATE_LIMIT = "10 per minute"

# Admin API key for sensitive endpoints
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")


def require_admin_auth(f):
    """
    Decorator to require admin authentication for sensitive health endpoints.
    FIX CRIT-05: Prevents information disclosure.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-Admin-API-Key")

        if not ADMIN_API_KEY:
            logger.error("ADMIN_API_KEY not configured - admin endpoints disabled")
            return jsonify({"error": "Admin endpoints not configured"}), 503

        if not api_key:
            logger.warning(
                f"Detailed health check attempted without auth from {request.remote_addr}"
            )
            return jsonify({"error": "Admin authentication required"}), 401

        if not hmac.compare_digest(api_key, ADMIN_API_KEY):
            logger.warning(f"Invalid admin API key from {request.remote_addr}")
            return jsonify({"error": "Invalid credentials"}), 403

        return f(*args, **kwargs)

    return decorated_function


# Canadian Data Residency Enforcement
REQUIRED_REGION = "ca-central-1"  # Montreal


@health_bp.route("/api/health", methods=["GET"])
@limiter.limit(HEALTH_RATE_LIMIT)
def health_check():
    """
    Health check endpoint
    Returns server status, database connectivity, and configuration info
    """

    health_status = {
        "status": "healthy",
        "environment": current_app.config.get("ENV", "unknown"),
        "database": "unknown",
        "aws_configured": False,
        "canadian_residency": False,
        "timestamp": None,
    }

    # Check database connectivity
    try:
        db.session.execute(text("SELECT 1"))
        health_status["database"] = "connected"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["database"] = "disconnected"
        current_app.logger.error(f"Database health check failed: {str(e)}")

    # Check AWS configuration
    aws_bucket = current_app.config.get("AWS_S3_BUCKET")
    aws_region = current_app.config.get("AWS_REGION")
    if aws_bucket and aws_region:
        health_status["aws_configured"] = True
        health_status["aws_region"] = aws_region

        # Verify Canadian Data Residency
        if aws_region == REQUIRED_REGION:
            health_status["canadian_residency"] = True
            health_status["data_residency_region"] = "ca-central-1 (Montreal)"
        else:
            health_status["status"] = "degraded"
            health_status["canadian_residency"] = False
            health_status["data_residency_warning"] = (
                f"Region '{aws_region}' does not meet Canadian data residency requirements. Must use '{REQUIRED_REGION}'."
            )

    # Add timestamp
    from datetime import datetime, timezone

    health_status["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Return appropriate status code
    status_code = 200 if health_status["status"] == "healthy" else 503

    return jsonify(health_status), status_code


@health_bp.route("/api/health/detailed", methods=["GET"])
@limiter.limit(DETAILED_RATE_LIMIT)
@require_admin_auth
def detailed_health_check():
    """
    Detailed health check with full compliance verification.
    Used for enterprise deployment validation.
    FIX CRIT-05: Now requires admin authentication.
    FIX HIGH-03: Rate limited.
    """
    from datetime import datetime

    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
    }

    # 1. Database Check
    try:
        db.session.execute(text("SELECT 1"))
        health_status["checks"]["database"] = {"status": "pass", "message": "Connected"}
    except Exception as e:
        health_status["checks"]["database"] = {"status": "fail", "message": str(e)}
        health_status["status"] = "unhealthy"

    # 2. Canadian Data Residency Check
    aws_region = current_app.config.get("AWS_REGION", "not_configured")
    if aws_region == REQUIRED_REGION:
        health_status["checks"]["canadian_residency"] = {
            "status": "pass",
            "region": aws_region,
            "location": "Montreal, Quebec, Canada",
        }
    else:
        health_status["checks"]["canadian_residency"] = {
            "status": "fail",
            "region": aws_region,
            "required": REQUIRED_REGION,
            "message": "Data residency violation - must use ca-central-1",
        }
        health_status["status"] = "unhealthy"

    # 3. S3 Bucket Location Verification
    aws_bucket = current_app.config.get("AWS_S3_BUCKET")
    if aws_bucket:
        try:
            import boto3

            s3 = boto3.client("s3", region_name=aws_region)
            response = s3.get_bucket_location(Bucket=aws_bucket)
            bucket_location = response.get("LocationConstraint") or "us-east-1"

            if bucket_location == REQUIRED_REGION:
                health_status["checks"]["s3_bucket"] = {
                    "status": "pass",
                    "bucket": aws_bucket,
                    "location": bucket_location,
                }
            else:
                health_status["checks"]["s3_bucket"] = {
                    "status": "fail",
                    "bucket": aws_bucket,
                    "location": bucket_location,
                    "required": REQUIRED_REGION,
                    "message": "S3 bucket not in required region",
                }
                health_status["status"] = "unhealthy"
        except Exception as e:
            health_status["checks"]["s3_bucket"] = {
                "status": "warn",
                "bucket": aws_bucket,
                "message": f"Could not verify: {str(e)}",
            }

    # 4. SSO Configuration Check
    sso_enabled = current_app.config.get("ENABLE_SSO", False)
    health_status["checks"]["sso"] = {
        "status": "pass" if sso_enabled else "info",
        "enabled": sso_enabled,
        "providers": current_app.config.get("SSO_PROVIDERS", []),
    }

    # 5. WORM Storage Check
    worm_enabled = current_app.config.get("ENABLE_WORM_STORAGE", False)
    health_status["checks"]["worm_storage"] = {
        "status": "pass" if worm_enabled else "info",
        "enabled": worm_enabled,
        "retention_years": 7 if worm_enabled else None,
    }

    # 6. Multi-AZ Check
    multi_az = current_app.config.get("ENABLE_MULTI_AZ", False)
    health_status["checks"]["multi_az"] = {
        "status": "pass" if multi_az else "info",
        "enabled": multi_az,
        "availability_zones": (
            ["ca-central-1a", "ca-central-1b", "ca-central-1d"] if multi_az else []
        ),
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
            pool_usage_pct = (
                (active_connections / max_connections) * 100
                if max_connections > 0
                else 0
            )

            status = "pass"
            if pool_usage_pct >= 90:
                status = "warn"
            if pool_usage_pct >= 95:
                status = "critical"

            health_status["checks"]["connection_pool"] = {
                "status": status,
                "active_connections": active_connections,
                "max_connections": max_connections,
                "usage_percent": round(pool_usage_pct, 2),
            }

            if status in ("warn", "critical"):
                health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["connection_pool"] = {
            "status": "unknown",
            "message": f"Could not check: {str(e)}",
        }

    # FIX #40: AWS S3 Service Connectivity Check
    try:
        import boto3
        from botocore.exceptions import ClientError

        s3 = boto3.client("s3", region_name=aws_region)

        # Simple connectivity test - list buckets
        s3.list_buckets()

        health_status["checks"]["aws_s3_service"] = {
            "status": "pass",
            "message": "S3 service reachable",
        }
    except ClientError as e:
        health_status["checks"]["aws_s3_service"] = {
            "status": "fail",
            "message": f'S3 service error: {e.response["Error"]["Code"]}',
        }
        health_status["status"] = "unhealthy"
    except Exception as e:
        health_status["checks"]["aws_s3_service"] = {
            "status": "fail",
            "message": f"Cannot reach S3: {str(e)}",
        }
        health_status["status"] = "unhealthy"

    # FIX #40: QuickBooks Online API Connectivity Check (optional)
    try:
        import requests

        # Check QBO API status page or a lightweight endpoint
        # Using a simple HTTP check to verify network connectivity
        qbo_status_response = requests.get(
            "https://status.quickbooks.com/api/v2/status.json", timeout=5
        )

        if qbo_status_response.status_code == 200:
            health_status["checks"]["qbo_api"] = {
                "status": "pass",
                "message": "QuickBooks Online API reachable",
            }
        else:
            health_status["checks"]["qbo_api"] = {
                "status": "warn",
                "message": f"QBO API returned {qbo_status_response.status_code}",
            }
    except requests.exceptions.Timeout:
        health_status["checks"]["qbo_api"] = {
            "status": "fail",
            "message": "QBO API timeout",
        }
        health_status["status"] = "degraded"
    except requests.exceptions.RequestException as e:
        health_status["checks"]["qbo_api"] = {
            "status": "fail",
            "message": f"Cannot reach QBO API: {str(e)}",
        }
        health_status["status"] = "degraded"
    except Exception:
        # Requests library not available - skip this check
        health_status["checks"]["qbo_api"] = {
            "status": "skipped",
            "message": "Requests library not available",
        }

    # FIX #40: Encryption Service Check
    encryption_key = os.getenv("ENCRYPTION_KEY")
    encryption_key_b64 = os.getenv("ENCRYPTION_KEY_B64")

    if encryption_key or encryption_key_b64:
        health_status["checks"]["encryption"] = {
            "status": "pass",
            "configured": True,
            "key_source": (
                "ENCRYPTION_KEY_B64" if encryption_key_b64 else "ENCRYPTION_KEY"
            ),
        }
    else:
        health_status["checks"]["encryption"] = {
            "status": "fail",
            "configured": False,
            "message": "No encryption key configured",
        }
        health_status["status"] = "unhealthy"

    # FIX: Circuit Breaker Status for health check
    try:
        # Check if any circuit breakers are open
        circuit_breaker_status = {"status": "pass", "breakers": {}}

        # Get circuit breaker states from config or global state
        # Common circuit breakers: database, s3, qbo_api
        breakers = current_app.config.get("CIRCUIT_BREAKERS", {})

        for breaker_name, breaker_state in breakers.items():
            is_open = breaker_state.get("is_open", False)
            failure_count = breaker_state.get("failure_count", 0)
            last_failure = breaker_state.get("last_failure_time")
            reset_timeout = breaker_state.get("reset_timeout_seconds", 60)

            circuit_breaker_status["breakers"][breaker_name] = {
                "state": "open" if is_open else "closed",
                "failure_count": failure_count,
                "last_failure": last_failure,
                "reset_timeout_seconds": reset_timeout,
            }

            if is_open:
                circuit_breaker_status["status"] = "warn"

        # Add circuit breaker summary
        open_breakers = sum(
            1
            for b in circuit_breaker_status["breakers"].values()
            if b["state"] == "open"
        )
        circuit_breaker_status["open_count"] = open_breakers
        circuit_breaker_status["total_count"] = len(circuit_breaker_status["breakers"])

        if open_breakers > 0:
            health_status["status"] = "degraded"
            circuit_breaker_status["message"] = (
                f"{open_breakers} circuit breaker(s) open"
            )

        health_status["checks"]["circuit_breakers"] = circuit_breaker_status

    except Exception as e:
        health_status["checks"]["circuit_breakers"] = {
            "status": "unknown",
            "message": f"Could not check circuit breakers: {str(e)}",
        }

    # FIX: Redis Cache Health Check
    try:
        redis_url = os.getenv("REDIS_URL") or current_app.config.get("REDIS_URL")
        if redis_url:
            import redis

            redis_client = redis.from_url(redis_url, socket_connect_timeout=5)

            # Ping test
            redis_client.ping()

            # Get basic info
            info = redis_client.info("server")
            memory_info = redis_client.info("memory")

            health_status["checks"]["redis"] = {
                "status": "pass",
                "connected": True,
                "version": info.get("redis_version", "unknown"),
                "used_memory_human": memory_info.get("used_memory_human", "unknown"),
                "connected_clients": redis_client.info("clients").get(
                    "connected_clients", 0
                ),
            }
        else:
            health_status["checks"]["redis"] = {
                "status": "info",
                "configured": False,
                "message": "Redis URL not configured",
            }
    except redis.exceptions.ConnectionError as e:
        health_status["checks"]["redis"] = {
            "status": "fail",
            "connected": False,
            "message": f"Connection failed: {str(e)}",
        }
        health_status["status"] = "degraded"
    except redis.exceptions.TimeoutError:
        health_status["checks"]["redis"] = {
            "status": "fail",
            "connected": False,
            "message": "Connection timeout",
        }
        health_status["status"] = "degraded"
    except ImportError:
        health_status["checks"]["redis"] = {
            "status": "skipped",
            "message": "Redis library not installed",
        }
    except Exception as e:
        health_status["checks"]["redis"] = {
            "status": "unknown",
            "message": f"Could not check Redis: {str(e)}",
        }

    # FIX: Database Pool Status (SQLAlchemy connection pool)
    try:
        from sqlalchemy import pool as sa_pool

        engine = db.engine

        if hasattr(engine, "pool"):
            pool = engine.pool
            pool_status = {
                "status": "pass",
                "size": pool.size() if hasattr(pool, "size") else "unknown",
                "checked_in": (
                    pool.checkedin() if hasattr(pool, "checkedin") else "unknown"
                ),
                "checked_out": (
                    pool.checkedout() if hasattr(pool, "checkedout") else "unknown"
                ),
                "overflow": pool.overflow() if hasattr(pool, "overflow") else "unknown",
                "invalid": (
                    pool.invalidatedcount()
                    if hasattr(pool, "invalidatedcount")
                    else "unknown"
                ),
            }

            # Calculate pool health
            if hasattr(pool, "size") and hasattr(pool, "checkedout"):
                checked_out = pool.checkedout()
                max_size = pool.size() + (
                    pool.overflow() if hasattr(pool, "overflow") else 0
                )
                if max_size > 0:
                    usage_pct = (checked_out / max_size) * 100
                    pool_status["usage_percent"] = round(usage_pct, 1)

                    if usage_pct >= 80:
                        pool_status["status"] = "warn"
                        pool_status["message"] = "Pool usage high"
                    if usage_pct >= 95:
                        pool_status["status"] = "critical"
                        pool_status["message"] = "Pool nearly exhausted"
                        health_status["status"] = "degraded"

            health_status["checks"]["sqlalchemy_pool"] = pool_status
        else:
            health_status["checks"]["sqlalchemy_pool"] = {
                "status": "info",
                "message": "No connection pool (NullPool or direct connection)",
            }

    except Exception as e:
        health_status["checks"]["sqlalchemy_pool"] = {
            "status": "unknown",
            "message": f"Could not check SQLAlchemy pool: {str(e)}",
        }

    status_code = 200 if health_status["status"] in ("healthy", "degraded") else 503
    return jsonify(health_status), status_code


@health_bp.route("/api/health/compliance", methods=["GET"])
@limiter.limit(DETAILED_RATE_LIMIT)
@require_admin_auth
def compliance_check():
    """
    Compliance verification endpoint for enterprise audits.
    Returns all compliance-relevant configuration.
    FIX CRIT-05: Now requires admin authentication.
    FIX HIGH-03: Rate limited.
    """
    from datetime import datetime

    compliance = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_residency": {
            "requirement": "Canadian Data Residency",
            "region": current_app.config.get("AWS_REGION", "not_configured"),
            "required_region": REQUIRED_REGION,
            "compliant": current_app.config.get("AWS_REGION") == REQUIRED_REGION,
        },
        "encryption": {
            "s3_encryption": current_app.config.get("AWS_S3_ENCRYPTION", "AES256"),
            "customer_managed_keys": current_app.config.get("ENABLE_CMK", False),
        },
        "retention": {
            "financial_data_ttl_hours": current_app.config.get(
                "AWS_S3_FILE_TTL_HOURS", 24
            ),
            "metadata_archival_years": 7,
            "worm_enabled": current_app.config.get("ENABLE_WORM_STORAGE", False),
        },
        "authentication": {
            "sso_enabled": current_app.config.get("ENABLE_SSO", False),
            "mfa_enabled": current_app.config.get("ENABLE_2FA", False),
        },
        "high_availability": {
            "multi_az_enabled": current_app.config.get("ENABLE_MULTI_AZ", False)
        },
    }

    return jsonify(compliance)
