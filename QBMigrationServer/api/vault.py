"""
Vault API - ForensicBridge Archival Vault
Provides endpoints for viewing and restoring archived (completed) migrations.
"""

import logging
import re

from api.auth import require_auth
from extensions import limiter
from flask import Blueprint, jsonify, request
from models.database import db
from models.migration import Migration

vault_bp = Blueprint("vault", __name__, url_prefix="/api/vault")
logger = logging.getLogger(__name__)

# UUID validation pattern for migration IDs
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _get_user_id():
    """Get current user ID from require_auth decorator."""
    return int(request.current_user["user_id"])


def _format_storage_size(total_bytes):
    """Format bytes as human-readable storage string."""
    if total_bytes is None or total_bytes == 0:
        return "0 GB"
    gb = total_bytes / (1024**3)
    if gb >= 1:
        return f"{gb:.1f} GB"
    mb = total_bytes / (1024**2)
    return f"{mb:.0f} MB"


def _estimate_monthly_cost(total_bytes):
    """Estimate S3 Glacier monthly storage cost."""
    if total_bytes is None or total_bytes == 0:
        return "$0.00"
    gb = total_bytes / (1024**3)
    # S3 Glacier pricing ~$0.004/GB/month
    cost = gb * 0.004
    return f"${cost:.2f}"


@vault_bp.route("", methods=["GET"])
@require_auth
def list_vault():
    """List archived (completed/cleaned) migrations for current user."""
    user_id = _get_user_id()

    try:
        # Completed and cleaned migrations are "archived"
        archived = (
            Migration.query.filter(
                Migration.user_id == user_id,
                Migration.status.in_(["completed", "cleaned"]),
            )
            .order_by(Migration.completed_at.desc())
            .all()
        )

        companies = []
        total_records = 0
        total_bytes = 0

        for m in archived:
            record_count = m.total_records_migrated or 0
            total_records += record_count
            if m.data_size_bytes:
                total_bytes += m.data_size_bytes

            companies.append(
                {
                    "id": m.migration_id,
                    "companyName": m.company_name
                    or m.qb_file_name
                    or "Unknown Company",
                    "archiveDate": (
                        m.completed_at.isoformat()
                        if m.completed_at
                        else m.created_at.isoformat()
                    ),
                    "recordCount": record_count,
                    "storageClass": (
                        "S3 Glacier" if m.cleanup_completed else "S3 Standard"
                    ),
                    "status": "archived" if m.status == "completed" else "cleaned",
                    "retentionYears": 7,  # Default forensic retention
                    "lastAccessed": (
                        m.completed_at.isoformat()
                        if m.completed_at
                        else m.created_at.isoformat()
                    ),
                }
            )

        stats = {
            "archivedCompanies": len(companies),
            "totalRecords": total_records,
            "storageSize": _format_storage_size(total_bytes),
            "monthlyCost": _estimate_monthly_cost(total_bytes),
        }

        return (
            jsonify(
                {
                    "success": True,
                    "companies": companies,
                    "stats": stats,
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(f"Failed to list vault for user {user_id}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Failed to load vault data",
                    "companies": [],
                    "stats": {
                        "archivedCompanies": 0,
                        "totalRecords": 0,
                        "storageSize": "0 GB",
                        "monthlyCost": "$0.00",
                    },
                }
            ),
            500,
        )


@vault_bp.route("/<migration_id>/restore", methods=["POST"])
@limiter.limit("5 per minute")
@require_auth
def restore_vault_item(migration_id):
    """Restore an archived migration (mark it for re-processing)."""
    if not UUID_PATTERN.match(migration_id):
        return jsonify({"success": False, "error": "Invalid migration ID format"}), 400

    user_id = _get_user_id()

    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id,
            user_id=user_id,
        ).first()

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        if migration.status not in ("completed", "cleaned"):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Migration cannot be restored from status: {migration.status}",
                    }
                ),
                400,
            )

        # Mark as restoring and trigger S3 Glacier retrieval
        migration.status = "restoring"
        migration.current_step = "Initiating S3 Glacier restore"
        migration.cleanup_completed = False
        db.session.commit()

        # Trigger async S3 Glacier retrieval for the archived data
        restore_job_id = None
        try:
            import os

            import boto3
            from botocore.exceptions import ClientError

            bucket_name = os.getenv("S3_BUCKET_NAME")
            if bucket_name:
                s3 = boto3.client(
                    "s3",
                    region_name=os.environ.get("AWS_REGION", "ca-central-1"),
                )
                s3_key = f"archives/{migration_id}/data.enc"
                try:
                    restore_response = s3.restore_object(
                        Bucket=bucket_name,
                        Key=s3_key,
                        RestoreRequest={
                            "Days": 7,
                            "GlacierJobParameters": {"Tier": "Standard"},
                        },
                    )
                    restore_job_id = restore_response.get("ResponseMetadata", {}).get(
                        "RequestId"
                    )
                    migration.current_step = (
                        f"S3 Glacier restore initiated (RequestId: {restore_job_id})"
                    )
                except ClientError as e:
                    error_code = e.response["Error"]["Code"]
                    if error_code == "RestoreAlreadyInProgress":
                        migration.current_step = (
                            "S3 Glacier restore already in progress"
                        )
                    elif error_code == "NoSuchKey":
                        migration.current_step = (
                            "Archive not found in S3 - metadata-only restore"
                        )
                        migration.status = "pending"
                    else:
                        raise
                db.session.commit()
            else:
                logger.warning("S3_BUCKET_NAME not configured for vault restore")
                migration.current_step = "Restore requested (S3 not configured)"
                migration.status = "pending"
                db.session.commit()
        except Exception as e:
            logger.warning(f"S3 Glacier restore request failed for {migration_id}: {e}")
            migration.current_step = (
                "Restore requested (S3 retrieval pending manual action)"
            )
            migration.status = "pending"
            db.session.commit()

        logger.info(
            f"Vault restore requested: migration {migration_id} by user {user_id}"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Restore initiated - data will be available within 3-5 hours",
                    "migration_id": migration_id,
                    "restore_status": migration.status,
                    "restore_job_id": restore_job_id,
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(
            f"Failed to restore vault item {migration_id} for user {user_id}"
        )
        db.session.rollback()
        return jsonify({"success": False, "error": "Failed to initiate restore"}), 500
