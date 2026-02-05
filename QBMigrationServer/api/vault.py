"""
Vault API - ForensicBridge Archival Vault
Provides endpoints for viewing and restoring archived (completed) migrations.
"""

from flask import Blueprint, request, jsonify
from api.auth import require_auth
from models.database import db
from models.migration import Migration
from extensions import limiter
import logging

vault_bp = Blueprint("vault", __name__, url_prefix="/api/vault")
logger = logging.getLogger(__name__)


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
        logger.exception(f"Failed to list vault for user {user_id}: {e}")
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

        # Mark as pending restore
        migration.status = "pending"
        migration.current_step = "Restore requested"
        migration.cleanup_completed = False
        db.session.commit()

        logger.info(
            f"Vault restore requested: migration {migration_id} by user {user_id}"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Restore initiated",
                    "migration_id": migration_id,
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(
            f"Failed to restore vault item {migration_id} for user {user_id}: {e}"
        )
        db.session.rollback()
        return jsonify({"success": False, "error": "Failed to initiate restore"}), 500
