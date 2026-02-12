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
from datetime import datetime, timezone
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


def require_admin_auth(f):
    """
    Decorator to require admin authentication for sensitive health endpoints.
    FIX CRIT-05: Prevents information disclosure.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-Admin-API-Key")
        admin_api_key = os.getenv("ADMIN_API_KEY")

        if not admin_api_key:
            logger.error("ADMIN_API_KEY not configured - admin endpoints disabled")
            return (
                jsonify({"success": False, "error": "Admin endpoints not configured"}),
                503,
            )

        if not api_key:
            logger.warning(
                f"Detailed health check attempted without auth from {request.remote_addr}"
            )
            return (
                jsonify({"success": False, "error": "Admin authentication required"}),
                401,
            )

        if not hmac.compare_digest(api_key, admin_api_key):
            logger.warning(f"Invalid admin API key from {request.remote_addr}")
            return jsonify({"success": False, "error": "Invalid credentials"}), 403

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
                f"Region '{aws_region}' does not meet Canadian data"
                f" residency requirements. Must use '{REQUIRED_REGION}'."
            )

    # Add timestamp
    health_status["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Return appropriate status code
    # "degraded" still passes healthcheck (200) — only "unhealthy" returns 503
    # This prevents the container from being marked unhealthy when optional
    # services (AWS, Redis) are unconfigured
    status_code = 200 if health_status["status"] in ("healthy", "degraded") else 503

    return jsonify(health_status), status_code


def _check_database_health():
    """Check database connectivity and connection pool stats.

    Returns a dict with keys: database, connection_pool, sqlalchemy_pool.
    """
    result = {"database": None, "connection_pool": None, "sqlalchemy_pool": None}

    # Basic connectivity
    try:
        db.session.execute(text("SELECT 1"))
        result["database"] = {"status": "pass", "message": "Connected"}
    except Exception as e:
        logger.error(f"Detailed health check database failure: {e}")
        result["database"] = {"status": "fail", "message": "Database connection failed"}

    # Connection pool stats (PostgreSQL)
    try:
        row = db.session.execute(text("""
            SELECT
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections
        """)).fetchone()
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

            result["connection_pool"] = {
                "status": status,
                "active_connections": active_connections,
                "max_connections": max_connections,
                "usage_percent": round(pool_usage_pct, 2),
            }
    except Exception as e:
        result["connection_pool"] = {
            "status": "unknown",
            "message": f"Could not check: {str(e)}",
        }

    # SQLAlchemy pool status
    try:
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

            result["sqlalchemy_pool"] = pool_status
        else:
            result["sqlalchemy_pool"] = {
                "status": "info",
                "message": "No connection pool (NullPool or direct connection)",
            }

    except Exception as e:
        result["sqlalchemy_pool"] = {
            "status": "unknown",
            "message": f"Could not check SQLAlchemy pool: {str(e)}",
        }

    return result


def _check_s3_health(aws_region):
    """Check S3 bucket location, S3 service connectivity, and QBO API reachability.

    Returns a dict with keys: s3_bucket (optional), aws_s3_service, qbo_api.
    """
    result = {}

    # S3 Bucket Location Verification
    aws_bucket = current_app.config.get("AWS_S3_BUCKET")
    if aws_bucket:
        try:
            import boto3

            s3 = boto3.client("s3", region_name=aws_region)
            response = s3.get_bucket_location(Bucket=aws_bucket)
            bucket_location = response.get("LocationConstraint") or "us-east-1"

            if bucket_location == REQUIRED_REGION:
                result["s3_bucket"] = {
                    "status": "pass",
                    "bucket": aws_bucket,
                    "location": bucket_location,
                }
            else:
                result["s3_bucket"] = {
                    "status": "fail",
                    "bucket": aws_bucket,
                    "location": bucket_location,
                    "required": REQUIRED_REGION,
                    "message": "S3 bucket not in required region",
                }
        except Exception as e:
            result["s3_bucket"] = {
                "status": "warn",
                "bucket": aws_bucket,
                "message": f"Could not verify: {str(e)}",
            }

    # S3 Service Connectivity
    try:
        import boto3
        from botocore.exceptions import ClientError

        s3 = boto3.client("s3", region_name=aws_region)

        # Simple connectivity test - list buckets
        s3.list_buckets()

        result["aws_s3_service"] = {
            "status": "pass",
            "message": "S3 service reachable",
        }
    except ClientError as e:
        result["aws_s3_service"] = {
            "status": "fail",
            "message": f'S3 service error: {e.response["Error"]["Code"]}',
        }
    except Exception as e:
        result["aws_s3_service"] = {
            "status": "fail",
            "message": f"Cannot reach S3: {str(e)}",
        }

    # QuickBooks Online API Connectivity Check (optional)
    try:
        import requests

        qbo_status_response = requests.get(
            "https://status.quickbooks.com/api/v2/status.json", timeout=5
        )

        if qbo_status_response.status_code == 200:
            result["qbo_api"] = {
                "status": "pass",
                "message": "QuickBooks Online API reachable",
            }
        else:
            result["qbo_api"] = {
                "status": "warn",
                "message": f"QBO API returned {qbo_status_response.status_code}",
            }
    except requests.exceptions.Timeout:
        result["qbo_api"] = {
            "status": "fail",
            "message": "QBO API timeout",
        }
    except requests.exceptions.RequestException as e:
        result["qbo_api"] = {
            "status": "fail",
            "message": f"Cannot reach QBO API: {str(e)}",
        }
    except Exception:
        # Requests library not available - skip this check
        result["qbo_api"] = {
            "status": "skipped",
            "message": "Requests library not available",
        }

    return result


def _check_redis_health():
    """Check Redis cache connectivity and stats.

    Returns a single dict with status/details.
    """
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

            return {
                "status": "pass",
                "connected": True,
                "version": info.get("redis_version", "unknown"),
                "used_memory_human": memory_info.get("used_memory_human", "unknown"),
                "connected_clients": redis_client.info("clients").get(
                    "connected_clients", 0
                ),
            }
        else:
            return {
                "status": "info",
                "configured": False,
                "message": "Redis URL not configured",
            }
    except redis.exceptions.ConnectionError as e:
        return {
            "status": "fail",
            "connected": False,
            "message": f"Connection failed: {str(e)}",
        }
    except redis.exceptions.TimeoutError:
        return {
            "status": "fail",
            "connected": False,
            "message": "Connection timeout",
        }
    except ImportError:
        return {
            "status": "skipped",
            "message": "Redis library not installed",
        }
    except Exception as e:
        return {
            "status": "unknown",
            "message": f"Could not check Redis: {str(e)}",
        }


def _check_celery_health():
    """Check circuit breaker status (used by Celery and other services).

    Returns a single dict with status/details.
    """
    try:
        circuit_breaker_status = {"status": "pass", "breakers": {}}

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

        open_breakers = sum(
            1
            for b in circuit_breaker_status["breakers"].values()
            if b["state"] == "open"
        )
        circuit_breaker_status["open_count"] = open_breakers
        circuit_breaker_status["total_count"] = len(circuit_breaker_status["breakers"])

        if open_breakers > 0:
            circuit_breaker_status["message"] = (
                f"{open_breakers} circuit breaker(s) open"
            )

        return circuit_breaker_status

    except Exception as e:
        return {
            "status": "unknown",
            "message": f"Could not check circuit breakers: {str(e)}",
        }


def _check_disk_health(aws_region):
    """Check Canadian data residency, SSO, WORM storage, and Multi-AZ configuration.

    Returns a dict with keys: canadian_residency, sso, worm_storage, multi_az.
    """
    result = {}

    # Canadian Data Residency Check
    if aws_region == REQUIRED_REGION:
        result["canadian_residency"] = {
            "status": "pass",
            "region": aws_region,
            "location": "Montreal, Quebec, Canada",
        }
    else:
        result["canadian_residency"] = {
            "status": "fail",
            "region": aws_region,
            "required": REQUIRED_REGION,
            "message": "Data residency violation - must use ca-central-1",
        }

    # SSO Configuration Check
    sso_enabled = current_app.config.get("ENABLE_SSO", False)
    result["sso"] = {
        "status": "pass" if sso_enabled else "info",
        "enabled": sso_enabled,
        "providers": current_app.config.get("SSO_PROVIDERS", []),
    }

    # WORM Storage Check
    worm_enabled = current_app.config.get("ENABLE_WORM_STORAGE", False)
    result["worm_storage"] = {
        "status": "pass" if worm_enabled else "info",
        "enabled": worm_enabled,
        "retention_years": 7 if worm_enabled else None,
    }

    # Multi-AZ Check
    multi_az = current_app.config.get("ENABLE_MULTI_AZ", False)
    result["multi_az"] = {
        "status": "pass" if multi_az else "info",
        "enabled": multi_az,
        "availability_zones": (
            ["ca-central-1a", "ca-central-1b", "ca-central-1d"] if multi_az else []
        ),
    }

    return result


def _check_memory_health():
    """Check encryption service configuration.

    Returns a single dict with status/details.
    """
    encryption_key = os.getenv("ENCRYPTION_KEY")
    encryption_key_b64 = os.getenv("ENCRYPTION_KEY_B64")

    if encryption_key or encryption_key_b64:
        return {
            "status": "pass",
            "configured": True,
            "key_source": (
                "ENCRYPTION_KEY_B64" if encryption_key_b64 else "ENCRYPTION_KEY"
            ),
        }
    else:
        return {
            "status": "fail",
            "configured": False,
            "message": "No encryption key configured",
        }


def _derive_overall_status(health_status):
    """Derive the overall health status from individual check results.

    Replicates the original status-setting logic:
    - database/canadian_residency/s3_bucket/aws_s3_service/encryption fail -> unhealthy
    - connection_pool/sqlalchemy_pool warn/critical -> degraded
    - circuit_breakers open -> degraded
    - redis fail -> degraded
    - qbo_api fail -> degraded
    """
    checks = health_status.get("checks", {})
    status = "healthy"

    # Any "fail" in core checks -> unhealthy
    for key in (
        "database",
        "canadian_residency",
        "s3_bucket",
        "aws_s3_service",
        "encryption",
    ):
        check = checks.get(key)
        if check and check.get("status") == "fail":
            return "unhealthy"

    # Connection pool critical or warn -> degraded
    for key in ("connection_pool", "sqlalchemy_pool"):
        check = checks.get(key)
        if check and check.get("status") in ("warn", "critical"):
            status = "degraded"

    # Circuit breakers open -> degraded
    cb = checks.get("circuit_breakers")
    if cb and cb.get("open_count", 0) > 0:
        status = "degraded"

    # Redis failure -> degraded
    redis_check = checks.get("redis")
    if redis_check and redis_check.get("status") == "fail":
        status = "degraded"

    # QBO API failure -> degraded
    qbo_check = checks.get("qbo_api")
    if qbo_check and qbo_check.get("status") == "fail":
        status = "degraded"

    return status


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
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
    }

    aws_region = current_app.config.get("AWS_REGION", "not_configured")

    # 1. Database health (connectivity, connection pool, SQLAlchemy pool)
    db_checks = _check_database_health()
    health_status["checks"]["database"] = db_checks["database"]
    if db_checks["connection_pool"] is not None:
        health_status["checks"]["connection_pool"] = db_checks["connection_pool"]
    if db_checks["sqlalchemy_pool"] is not None:
        health_status["checks"]["sqlalchemy_pool"] = db_checks["sqlalchemy_pool"]

    # 2. Infrastructure checks (residency, SSO, WORM, Multi-AZ)
    disk_checks = _check_disk_health(aws_region)
    health_status["checks"].update(disk_checks)

    # 3. S3 and external API checks
    s3_checks = _check_s3_health(aws_region)
    health_status["checks"].update(s3_checks)

    # 4. Redis cache health
    health_status["checks"]["redis"] = _check_redis_health()

    # 5. Circuit breaker / Celery health
    health_status["checks"]["circuit_breakers"] = _check_celery_health()

    # 6. Encryption / memory health
    health_status["checks"]["encryption"] = _check_memory_health()

    # Derive overall status from all checks
    health_status["status"] = _derive_overall_status(health_status)

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
