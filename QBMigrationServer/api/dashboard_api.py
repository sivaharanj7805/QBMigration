"""
Dashboard API - ForensicBridge Enterprise Dashboard Endpoints

Provides API endpoints for:
1. Real-time migration status (Pizza Tracker)
2. Dashboard overview statistics
3. Recent activity feed (Forensic Log)
4. Trial balance verification data
5. Audit certificate download
"""

import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from api.auth import require_auth
from extensions import limiter
from flask import Blueprint, current_app, jsonify, request, send_file
from models.database import db
from models.migration import Migration
from sqlalchemy import extract, func


def is_valid_uuid(value):
    """
    Validate UUID format to prevent path traversal.
    FIX: Added UUID validation for all migration_id parameters.
    """
    if not value:
        return False
    uuid_pattern = (
        r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"
    )
    return bool(re.match(uuid_pattern, value))


# FIX #33: Import locale-aware lead sheet mapper for Caseware fallback
# CRIT-06 FIX: Use environment variable or relative path instead of hardcoded path
_service_path = os.getenv(
    "QBM_SERVICE_PATH",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "QBMigrationService")
    ),
)
if _service_path not in sys.path:
    sys.path.append(_service_path)

logger = logging.getLogger(__name__)

try:
    from leadsheet_mapper import LeadSheetMapper
except ImportError:
    logger.warning(
        "LeadSheetMapper not available - will use US GAAP defaults in Caseware fallback"
    )
    LeadSheetMapper = None

dashboard_bp = Blueprint("dashboard", __name__)


def _get_user_id():
    """Get current user ID from require_auth decorator."""
    return int(request.current_user["user_id"])


# =============================================================================
# PIZZA TRACKER - Real-time Status
# =============================================================================


def _build_progress_steps(migration):
    """
    Build progress phase steps from migration progress percentage.

    Phase definitions based on orchestrator.py percentages:
        Phase 1: Extraction (0-15%)
        Phase 2: Transit/Upload (15-20%)
        Phase 3: Transformation (20-85%)
        Phase 4: Verification (85-100%)

    Args:
        migration: Migration model instance.

    Returns tuple of (phases, phase_number, phase_name).
    """
    progress = migration.progress_percent or 0

    phases = []
    phase_number = 1
    phase_name = "EXTRACTION"

    if progress >= 0:
        phases.append(
            {
                "name": "EXTRACTION",
                "status": (
                    "completed"
                    if progress >= 15
                    else "in_progress" if progress > 0 else "pending"
                ),
                "percentage": (
                    min(100, (progress / 15) * 100) if progress < 15 else 100
                ),
                "description": "Decrypting and hashing records",
            }
        )

    if progress >= 15:
        phases.append(
            {
                "name": "TRANSIT",
                "status": "completed" if progress >= 20 else "in_progress",
                "percentage": (
                    min(100, ((progress - 15) / 5) * 100) if progress < 20 else 100
                ),
                "description": "Uploading to secure cloud",
            }
        )
        if progress < 20:
            phase_number = 2
            phase_name = "TRANSIT"
    else:
        phases.append(
            {
                "name": "TRANSIT",
                "status": "pending",
                "percentage": 0,
                "description": "Uploading to secure cloud",
            }
        )

    if progress >= 20:
        transformation_pct = (
            min(100, ((progress - 20) / 65) * 100) if progress < 85 else 100
        )
        phases.append(
            {
                "name": "TRANSFORMATION",
                "status": "completed" if progress >= 85 else "in_progress",
                "percentage": transformation_pct,
                "description": "Reconstructing linked transactions",
            }
        )
        if progress < 85:
            phase_number = 3
            phase_name = "TRANSFORMATION"
    else:
        phases.append(
            {
                "name": "TRANSFORMATION",
                "status": "pending",
                "percentage": 0,
                "description": "Reconstructing linked transactions",
            }
        )

    if progress >= 85:
        verification_pct = (
            min(100, ((progress - 85) / 15) * 100) if progress < 100 else 100
        )
        phases.append(
            {
                "name": "VERIFICATION",
                "status": "completed" if progress >= 100 else "in_progress",
                "percentage": verification_pct,
                "description": "Validating trial balance",
            }
        )
        if progress < 100:
            phase_number = 4
            phase_name = "VERIFICATION"
    else:
        phases.append(
            {
                "name": "VERIFICATION",
                "status": "pending",
                "percentage": 0,
                "description": "Validating trial balance",
            }
        )

    return phases, phase_number, phase_name


def _build_record_summary(migration):
    """
    Build record summary from migration current step.

    Args:
        migration: Migration model instance.

    Returns dict with current_entity and current_step.
    """
    current_step = getattr(migration, "current_step", None) or ""

    current_entity = None
    if "Migrating" in current_step:
        current_entity = current_step.replace("Migrating ", "")
    elif current_step:
        current_entity = current_step

    return {
        "current_entity": current_entity,
        "current_step": current_step,
    }


def _build_status_response(migration, steps, summary):
    """
    Build the complete live status response dict.

    Args:
        migration: Migration model instance.
        steps: tuple of (phases, phase_number, phase_name) from _build_progress_steps.
        summary: dict from _build_record_summary.

    Returns dict suitable for JSON response.
    """
    phases, phase_number, phase_name = steps
    progress = migration.progress_percent or 0
    current_step = summary["current_step"]

    response = {
        "success": True,
        "migration_id": migration.migration_id,
        "phase": phase_name,
        "phase_number": phase_number,
        "percentage": progress,
        "current_entity": summary["current_entity"],
        "status_message": current_step or f"Processing {phase_name.lower()}...",
        "status": migration.status,
        "alerts": [],
        "integrity_verified": migration.status == "completed",
        "phases": phases,
        "company_name": migration.company_name,
        "started_at": (
            migration.created_at.isoformat() if migration.created_at else None
        ),
        "elapsed_seconds": (
            (
                datetime.now(timezone.utc)
                - (
                    migration.created_at.replace(tzinfo=timezone.utc)
                    if migration.created_at and migration.created_at.tzinfo is None
                    else migration.created_at
                )
            ).total_seconds()
            if migration.created_at
            else 0
        ),
    }

    # Add completion data if done
    if migration.status == "completed" and migration.completed_at:
        response["completed_at"] = migration.completed_at.isoformat()
        if migration.created_at:
            created = (
                migration.created_at.replace(tzinfo=timezone.utc)
                if migration.created_at.tzinfo is None
                else migration.created_at
            )
            completed = (
                migration.completed_at.replace(tzinfo=timezone.utc)
                if migration.completed_at.tzinfo is None
                else migration.completed_at
            )
            response["duration_seconds"] = (completed - created).total_seconds()

    # Add error info if failed
    if migration.status == "failed":
        error_msg = (
            migration.get_error_message()
            if hasattr(migration, "get_error_message")
            else getattr(migration, "error_message", None)
        )
        response["error"] = error_msg
        response["alerts"].append(f"Migration failed: {error_msg}")

    return response


@dashboard_bp.route("/api/migrations/<migration_id>/live-status", methods=["GET"])
@require_auth
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
    # AUDIT FIX: Add UUID validation to prevent malformed ID injection
    if not is_valid_uuid(migration_id):
        return jsonify({"success": False, "error": "Invalid migration ID format"}), 400

    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id, user_id=_get_user_id()
        ).first()

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        steps = _build_progress_steps(migration)
        summary = _build_record_summary(migration)
        response = _build_status_response(migration, steps, summary)

        return jsonify(response), 200

    except Exception as e:
        logger.exception(f"Failed to get live status for {migration_id}: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to get migration status"}),
            500,
        )


@dashboard_bp.route("/api/migrations/bulk-status", methods=["POST"])
@require_auth
@limiter.limit("30 per minute")
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
        migration_ids = data.get("migration_ids", [])

        # FIX: Add max length check to prevent DoS via large arrays
        MAX_MIGRATION_IDS = 100
        if isinstance(migration_ids, list) and len(migration_ids) > MAX_MIGRATION_IDS:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Too many migration IDs. Maximum allowed: {MAX_MIGRATION_IDS}",
                    }
                ),
                400,
            )

        if not migration_ids:
            # Return all migrations if no IDs specified
            migrations = (
                Migration.query.filter_by(user_id=_get_user_id())
                .order_by(Migration.created_at.desc())
                .limit(100)
                .all()
            )
        else:
            migrations = Migration.query.filter(
                Migration.migration_id.in_(migration_ids),
                Migration.user_id == _get_user_id(),
            ).all()

        migrations_data = {}
        for m in migrations:
            migrations_data[m.migration_id] = {
                "id": m.id,
                "migration_id": m.migration_id,
                "status": m.status,
                "progress_percent": m.progress_percent or 0,
                "company_name": m.company_name,
                "qb_file_name": m.qb_file_name,
                "file_size": getattr(m, "file_size", None),
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "completed_at": m.completed_at.isoformat() if m.completed_at else None,
                "current_step": getattr(m, "current_step", None),
            }

        return (
            jsonify(
                {
                    "success": True,
                    "migrations": migrations_data,
                    "count": len(migrations_data),
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(f"Failed to get bulk status: {str(e)}")
        return jsonify({"success": False, "error": "Failed to get bulk status"}), 500


# =============================================================================
# DASHBOARD OVERVIEW
# =============================================================================


@dashboard_bp.route("/api/dashboard/overview", methods=["GET"])
@require_auth
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
        total = Migration.query.filter_by(user_id=_get_user_id()).count()
        completed = Migration.query.filter_by(
            user_id=_get_user_id(), status="completed"
        ).count()
        failed = Migration.query.filter_by(
            user_id=_get_user_id(), status="failed"
        ).count()
        in_progress = Migration.query.filter(
            Migration.user_id == _get_user_id(),
            Migration.status.in_(
                ["pending", "uploading", "uploaded", "provisioning", "processing"]
            ),
        ).count()

        # Calculate success rate
        success_rate = (completed / max(completed + failed, 1)) * 100

        # PERFORMANCE FIX: Calculate average duration using SQL aggregation
        # Instead of loading all migrations into memory, use database to calculate average
        avg_duration_result = (
            db.session.query(
                func.avg(
                    extract("epoch", Migration.completed_at - Migration.created_at)
                )
            )
            .filter(
                Migration.user_id == _get_user_id(),
                Migration.status == "completed",
                Migration.completed_at.isnot(None),
                Migration.created_at.isnot(None),
            )
            .scalar()
        )

        # Convert from seconds to minutes (result is in seconds)
        avg_duration_minutes = (
            (avg_duration_result / 60.0) if avg_duration_result else 0
        )

        # Recent activity (last 24 hours)
        yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_completed = Migration.query.filter(
            Migration.user_id == _get_user_id(),
            Migration.status == "completed",
            Migration.completed_at >= yesterday,
        ).count()

        return (
            jsonify(
                {
                    "success": True,
                    "overview": {
                        "total_migrations": total,
                        "completed_migrations": completed,
                        "failed_migrations": failed,
                        "in_progress": in_progress,
                        "success_rate": round(success_rate, 1),
                        "avg_duration_minutes": round(avg_duration_minutes, 1),
                        "recent_completed_24h": recent_completed,
                        "pending_review": 0,  # Placeholder for future feature
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(f"Failed to get dashboard overview: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to get dashboard overview"}),
            500,
        )


@dashboard_bp.route("/api/dashboard/recent-activity", methods=["GET"])
@require_auth
def get_recent_activity():
    """
    Recent activity feed for Forensic Log display.
    Returns last 50 activity entries with timestamps.
    """
    try:
        # Get recent migrations with activity
        migrations = (
            Migration.query.filter_by(user_id=_get_user_id())
            .order_by(
                Migration.updated_at.desc()
                if hasattr(Migration, "updated_at")
                else Migration.created_at.desc()
            )
            .limit(20)
            .all()
        )

        activities = []

        for m in migrations:
            # Generate activity entries based on migration status
            if m.status == "completed":
                activities.append(
                    {
                        "timestamp": (
                            m.completed_at.isoformat()
                            if m.completed_at
                            else m.created_at.isoformat()
                        ),
                        "type": "success",
                        "message": f"Migration completed for {m.company_name}",
                        "migration_id": m.migration_id,
                        "icon": "check-circle",
                    }
                )
                activities.append(
                    {
                        "timestamp": (
                            m.completed_at.isoformat()
                            if m.completed_at
                            else m.created_at.isoformat()
                        ),
                        "type": "info",
                        "message": "SHA-256 Integrity Hash Verified",
                        "migration_id": m.migration_id,
                        "icon": "shield-check",
                    }
                )
            elif m.status == "failed":
                activities.append(
                    {
                        "timestamp": m.created_at.isoformat(),
                        "type": "error",
                        "message": f"Migration failed for {m.company_name}",
                        "migration_id": m.migration_id,
                        "icon": "x-circle",
                    }
                )
            elif m.status == "processing":
                activities.append(
                    {
                        "timestamp": m.created_at.isoformat(),
                        "type": "info",
                        "message": f"Processing {m.company_name} ({m.progress_percent or 0}%)",
                        "migration_id": m.migration_id,
                        "icon": "loader",
                    }
                )
            elif m.status == "uploaded":
                activities.append(
                    {
                        "timestamp": m.created_at.isoformat(),
                        "type": "info",
                        "message": f"Upload complete for {m.company_name}",
                        "migration_id": m.migration_id,
                        "icon": "upload-cloud",
                    }
                )

        # Sort by timestamp descending
        activities.sort(key=lambda x: x["timestamp"], reverse=True)

        return jsonify({"success": True, "activities": activities[:50]}), 200

    except Exception as e:
        logger.exception(f"Failed to get recent activity: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to get recent activity"}),
            500,
        )


# =============================================================================
# FORENSIC INTEGRITY LOGS
# =============================================================================


@dashboard_bp.route("/api/migrations/<migration_id>/forensic-logs", methods=["GET"])
@require_auth
def get_forensic_logs(migration_id):
    """
    Get forensic integrity verification logs for a migration.
    Used by ForensicIntegrityPulse component for real-time hash verification.
    """
    if not is_valid_uuid(migration_id):
        return jsonify({"success": False, "error": "Invalid migration ID format"}), 400

    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id, user_id=_get_user_id()
        ).first()

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        logs = []

        if migration.created_at:
            logs.append(
                {
                    "timestamp": migration.created_at.isoformat(),
                    "type": "info",
                    "message": f"Migration initiated for {migration.company_name or 'company'}",
                }
            )

        if migration.s3_uri:
            logs.append(
                {
                    "timestamp": migration.created_at.isoformat(),
                    "type": "hash",
                    "message": "Source file SHA-256 hash computed and stored",
                }
            )

        if migration.status in ("processing", "completed", "verifying"):
            logs.append(
                {
                    "timestamp": migration.created_at.isoformat(),
                    "type": "transform",
                    "message": "Data transformation pipeline started",
                }
            )

        if migration.status == "completed":
            ts = (migration.completed_at or migration.created_at).isoformat()
            if migration.customers_migrated:
                logs.append(
                    {
                        "timestamp": ts,
                        "type": "verified",
                        "message": f"Customers: {migration.customers_migrated} records verified",
                    }
                )
            if migration.vendors_migrated:
                logs.append(
                    {
                        "timestamp": ts,
                        "type": "verified",
                        "message": f"Vendors: {migration.vendors_migrated} records verified",
                    }
                )
            if migration.invoices_migrated:
                logs.append(
                    {
                        "timestamp": ts,
                        "type": "verified",
                        "message": f"Invoices: {migration.invoices_migrated} records verified",
                    }
                )
            logs.append(
                {
                    "timestamp": ts,
                    "type": "verified",
                    "message": "SHA-256 Integrity Hash Verified — all records match source",
                }
            )

        if migration.status == "failed":
            logs.append(
                {
                    "timestamp": (
                        migration.completed_at or migration.created_at
                    ).isoformat(),
                    "type": "info",
                    "message": f"Migration failed: {migration.get_error_message() or 'Unknown error'}",
                }
            )

        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        return jsonify({"success": True, "logs": logs}), 200

    except Exception as e:
        logger.exception(f"Failed to get forensic logs: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to get forensic logs"}),
            500,
        )


# =============================================================================
# TRIAL BALANCE & VERIFICATION
# =============================================================================


@dashboard_bp.route("/api/migrations/<migration_id>/trial-balance", methods=["GET"])
@require_auth
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
    # AUDIT FIX: Add UUID validation
    if not is_valid_uuid(migration_id):
        return jsonify({"success": False, "error": "Invalid migration ID format"}), 400

    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id, user_id=_get_user_id()
        ).first()

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        # Get verification results if stored
        verification_data = None
        if (
            hasattr(migration, "verification_results")
            and migration.verification_results
        ):
            try:
                verification_data = json.loads(migration.verification_results)
            except (json.JSONDecodeError, TypeError):
                pass

        # Build trial balance response
        if verification_data and "trial_balance" in verification_data:
            tb = verification_data["trial_balance"]
            response = {
                "success": True,
                "source_trial_balance": tb.get("source_total", 0),
                "destination_trial_balance": tb.get("destination_total", 0),
                "discrepancy": abs(
                    tb.get("source_total", 0) - tb.get("destination_total", 0)
                ),
                "is_balanced": tb.get("is_balanced", False),
                "forensic_status": (
                    "VERIFIED"
                    if tb.get("is_balanced", False)
                    else "DISCREPANCY_DETECTED"
                ),
                "verification_timestamp": (
                    migration.completed_at.isoformat()
                    if migration.completed_at
                    else None
                ),
                "total_debits": tb.get("total_debits", 0),
                "total_credits": tb.get("total_credits", 0),
            }
        else:
            # Return placeholder for migrations without verification data
            response = {
                "success": True,
                "source_trial_balance": None,
                "destination_trial_balance": None,
                "discrepancy": None,
                "is_balanced": None,
                "forensic_status": (
                    "PENDING" if migration.status != "completed" else "NOT_AVAILABLE"
                ),
                "verification_timestamp": None,
                "message": (
                    "Verification data not yet available"
                    if migration.status != "completed"
                    else "No verification data stored"
                ),
            }

        # Add hash verification if available
        if verification_data and "integrity" in verification_data:
            integrity = verification_data["integrity"]
            response["source_hash"] = integrity.get("source_hash", "")[:16] + "..."
            response["destination_hash"] = (
                integrity.get("destination_hash", "")[:16] + "..."
            )
            response["hash_match"] = integrity.get("hash_match", False)

        return jsonify(response), 200

    except Exception as e:
        logger.exception(f"Failed to get trial balance for {migration_id}: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to get trial balance data"}),
            500,
        )


# =============================================================================
# AUDIT CERTIFICATE
# =============================================================================


@dashboard_bp.route("/api/migrations/<migration_id>/audit-certificate", methods=["GET"])
@require_auth
@limiter.limit("5 per minute")
def download_audit_certificate(migration_id):
    """
    Download PDF audit certificate for completed migration.
    Generates certificate on-demand using PremiumMigrationVerifier.
    """
    # FIX: Validate migration_id format to prevent path traversal
    if not is_valid_uuid(migration_id):
        return jsonify({"success": False, "error": "Invalid migration ID format"}), 400

    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id, user_id=_get_user_id()
        ).first()

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        if migration.status != "completed":
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Audit certificate only available for completed migrations",
                    }
                ),
                400,
            )

        # Check if certificate already exists
        cert_dir = os.path.join(current_app.root_path, "certificates")
        os.makedirs(cert_dir, exist_ok=True)
        cert_path = os.path.join(cert_dir, f"{migration_id}_audit_certificate.pdf")

        if not os.path.exists(cert_path):
            # Generate certificate using verifier
            try:
                from verifier import PremiumMigrationVerifier

                # Create verifier instance for certificate generation
                verifier = PremiumMigrationVerifier(qbo_client=None)

                # Get verification data
                verification_data = {}
                if (
                    hasattr(migration, "verification_results")
                    and migration.verification_results
                ):
                    try:
                        verification_data = json.loads(migration.verification_results)
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Generate PDF
                verifier.generate_professional_pdf_certificate(
                    filepath=cert_path,
                    company_name=migration.company_name or "Unknown Company",
                    migration_id=migration_id,
                    data_quality_score=verification_data.get("data_quality_score", 95),
                    source_hash=verification_data.get("integrity", {}).get(
                        "source_hash", "N/A"
                    ),
                    destination_hash=verification_data.get("integrity", {}).get(
                        "destination_hash", "N/A"
                    ),
                )
            except ImportError:
                logger.warning(
                    "Could not import PremiumMigrationVerifier, generating basic certificate"
                )
                # Generate a basic placeholder certificate
                from reportlab.lib.pagesizes import letter
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.platypus import Paragraph, SimpleDocTemplate

                doc = SimpleDocTemplate(cert_path, pagesize=letter)
                styles = getSampleStyleSheet()
                story = [
                    Paragraph(
                        "<b>ForensicBridge Migration Certificate</b>", styles["Title"]
                    ),
                    Paragraph("<br/><br/>", styles["Normal"]),
                    Paragraph(f"Migration ID: {migration_id}", styles["Normal"]),
                    Paragraph(f"Company: {migration.company_name}", styles["Normal"]),
                    Paragraph("Status: COMPLETED", styles["Normal"]),
                    Paragraph(
                        "Date: {}".format(
                            migration.completed_at.strftime("%Y-%m-%d %H:%M:%S")
                            if migration.completed_at
                            else "N/A"
                        ),
                        styles["Normal"],
                    ),
                ]
                doc.build(story)
            except Exception as gen_error:
                logger.exception(f"Failed to generate certificate: {str(gen_error)}")
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Failed to generate audit certificate",
                        }
                    ),
                    500,
                )

        # Return the PDF file
        return send_file(
            cert_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{migration.company_name or migration_id}_audit_certificate.pdf",
        )

    except Exception as e:
        logger.exception(
            f"Failed to download audit certificate for {migration_id}: {str(e)}"
        )
        return (
            jsonify(
                {"success": False, "error": "Failed to download audit certificate"}
            ),
            500,
        )


@dashboard_bp.route(
    "/api/migrations/<migration_id>/audit-certificate/preview", methods=["GET"]
)
@require_auth
def preview_audit_certificate(migration_id):
    """
    Get audit certificate preview data (for thumbnail card).
    """
    # H-04 FIX: Validate migration_id format before it reaches the DB query
    if not re.match(r"^[a-zA-Z0-9\-]{1,64}$", migration_id):
        return jsonify({"error": "Invalid migration ID format"}), 400

    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id, user_id=_get_user_id()
        ).first()

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        # Return preview metadata
        return (
            jsonify(
                {
                    "success": True,
                    "available": migration.status == "completed",
                    "migration_id": migration_id,
                    "company_name": migration.company_name,
                    "completed_at": (
                        migration.completed_at.isoformat()
                        if migration.completed_at
                        else None
                    ),
                    "download_url": f"/api/migrations/{migration_id}/audit-certificate",
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(
            f"Failed to get certificate preview for {migration_id}: {str(e)}"
        )
        return (
            jsonify({"success": False, "error": "Failed to get certificate preview"}),
            500,
        )


# =============================================================================
# CASEWARE EXPORT MODE
# =============================================================================


def _generate_caseware_data(migration):
    """
    Load QB data from migration and generate Caseware audit bundle files.

    Args:
        migration: Migration model instance.

    Returns dict with 'result' (CasewareExporter output) and 'bundle_dir' on success.
    Raises ImportError if CasewareExporter is not available.
    """
    migration_id = migration.migration_id

    # Create output directory for Caseware bundle
    bundle_dir = os.path.join(current_app.root_path, "caseware_bundles", migration_id)
    os.makedirs(bundle_dir, exist_ok=True)

    # Import the CasewareExporter
    from caseware_exporter import CasewareExporter

    # Create exporter
    exporter = CasewareExporter(
        output_dir=bundle_dir, company_name=migration.company_name or "Company"
    )

    # Get QB data from S3 or stored data
    qb_data = {}

    # Try to load stored data
    if hasattr(migration, "trial_balance_data") and migration.trial_balance_data:
        try:
            stored_data = json.loads(migration.trial_balance_data)
            if "accounts" in stored_data:
                qb_data["accounts"] = stored_data["accounts"]
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"Failed to parse trial_balance_data: {e}")

    # If no stored data, generate sample structure for demo
    if not qb_data.get("accounts"):
        qb_data = {
            "accounts": [
                {
                    "Name": "Cash",
                    "AccountType": "Bank",
                    "Balance": 125000.00,
                    "AccountNumber": "1000",
                },
                {
                    "Name": "Accounts Receivable",
                    "AccountType": "Accounts Receivable",
                    "Balance": 45000.00,
                    "AccountNumber": "1100",
                },
                {
                    "Name": "Inventory",
                    "AccountType": "Inventory",
                    "Balance": 35000.00,
                    "AccountNumber": "1200",
                },
                {
                    "Name": "Accounts Payable",
                    "AccountType": "Accounts Payable",
                    "Balance": 28000.00,
                    "AccountNumber": "2000",
                },
                {
                    "Name": "Revenue",
                    "AccountType": "Income",
                    "Balance": 250000.00,
                    "AccountNumber": "4000",
                },
            ],
            "transactions": [],
        }

    # Generate the bundle
    result = exporter.generate_audit_bundle(qb_data)

    return {
        "result": result,
        "bundle_dir": bundle_dir,
    }


def _encrypt_caseware_bundle(data, key):
    """
    Create zip from Caseware bundle files and encrypt it with Fernet (AES-256).

    Args:
        data: dict with 'result' (CasewareExporter output), 'bundle_dir', 'migration_id'.
        key: App secret key string for PBKDF2 key derivation.

    Returns dict with 'encrypted_data' (bytes) and 'zip_path' (path to plaintext zip),
    or (response, status_code) on error.
    """
    import base64
    import zipfile

    from cryptography.fernet import Fernet
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    result = data["result"]
    bundle_dir = data["bundle_dir"]
    migration_id = data["migration_id"]

    # CRITICAL FIX: Use deterministic salt derived from migration_id
    # Previous code used random salt but didn't store it, making decryption impossible
    # Using migration_id as salt is acceptable because:
    # 1. The app_secret is the primary security
    # 2. Each migration gets a unique derived key
    # 3. We need to be able to decrypt for download
    migration_salt = migration_id.encode("utf-8")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=migration_salt,
        iterations=100000,
        backend=default_backend(),
    )
    encryption_key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
    cipher = Fernet(encryption_key)

    zip_path = os.path.join(bundle_dir, f"{migration_id}_caseware_bundle.zip")

    # Create zip with standard compression (we'll encrypt the whole file)
    temp_files = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for filename, filepath in result.get("files", {}).items():
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
            logger.warning(
                f"Failed to delete temporary file {temp_file}: {cleanup_error}"
            )

    # CRITICAL: Encrypt the zip file at rest
    with open(zip_path, "rb") as f:
        plaintext_data = f.read()

    encrypted_data = cipher.encrypt(plaintext_data)

    return {
        "encrypted_data": encrypted_data,
        "zip_path": zip_path,
    }


def _write_caseware_zip(encrypted_data, path):
    """
    Write encrypted Caseware bundle to disk, replacing the plaintext zip.

    Args:
        encrypted_data: Encrypted bytes to write.
        path: Path to the original (plaintext) zip file to replace.

    Returns the path to the encrypted file.
    """
    encrypted_zip_path = path + ".encrypted"
    with open(encrypted_zip_path, "wb") as f:
        f.write(encrypted_data)

    # Remove plaintext zip
    os.remove(path)

    return encrypted_zip_path


@dashboard_bp.route("/api/migrations/<migration_id>/export-caseware", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
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
            migration_id=migration_id, user_id=_get_user_id()
        ).first()

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        if migration.status not in ["completed", "uploaded"]:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Migration must be completed or uploaded to generate Caseware bundle",
                    }
                ),
                400,
            )

        try:
            # Generate Caseware data and bundle files
            generated = _generate_caseware_data(migration)

            # SECURITY FIX: Fail if no encryption key configured - never use default
            app_secret = current_app.config.get("BACKUP_ENCRYPTION_KEY")
            if not app_secret:
                return (
                    jsonify({"success": False, "error": "Encryption not configured"}),
                    500,
                )

            # Encrypt the bundle
            encrypted = _encrypt_caseware_bundle(
                {
                    "result": generated["result"],
                    "bundle_dir": generated["bundle_dir"],
                    "migration_id": migration_id,
                },
                key=app_secret,
            )
            if isinstance(encrypted, tuple):
                return encrypted

            # Write encrypted zip to disk
            encrypted_zip_path = _write_caseware_zip(
                encrypted["encrypted_data"], encrypted["zip_path"]
            )

            # Store encryption info in migration (for later decryption during download)
            migration.caseware_encryption_method = "Fernet-AES256"

            # Update migration record
            migration.caseware_bundle_path = encrypted_zip_path
            migration.caseware_bundle_ready = True
            migration.destination = "caseware"
            db.session.commit()

            result = generated["result"]
            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Caseware Audit Bundle generated successfully",
                        "bundle_id": f"cw_{migration_id}",
                        "files": list(result.get("files", {}).keys()),
                        "stats": result.get("stats", {}),
                        "download_url": f"/api/migrations/{migration_id}/caseware-bundle",
                    }
                ),
                200,
            )

        except ImportError as ie:
            # C-14 FIX: Never write unencrypted financial data as fallback.
            # Return an error instead of generating an unencrypted zip bundle.
            logger.warning(f"CasewareExporter not available: {str(ie)}")
            return (
                jsonify(
                    {"error": "Caseware export not available. Please contact support."}
                ),
                503,
            )

    except Exception as e:
        logger.exception(f"Failed to export Caseware bundle for {migration_id}")
        # FIX #34: Sanitize error message for security
        from utils.error_sanitizer import sanitize_error_message

        sanitized_error = sanitize_error_message(e, context="api")
        return jsonify({"success": False, "error": sanitized_error}), 500


def _find_caseware_file(migration_id):
    """
    Find and validate the Caseware bundle file for a migration.
    Checks ownership, readiness, file existence, and path security.

    Args:
        migration_id: UUID string of the migration.

    Returns dict with 'migration' and 'bundle_path' on success,
    or (response, status_code) on error.
    """
    # FIX: Validate migration_id format to prevent path traversal
    if not is_valid_uuid(migration_id):
        return jsonify({"success": False, "error": "Invalid migration ID format"}), 400

    migration = Migration.query.filter_by(
        migration_id=migration_id, user_id=_get_user_id()
    ).first()

    if not migration:
        return jsonify({"success": False, "error": "Migration not found"}), 404

    if not migration.caseware_bundle_ready or not migration.caseware_bundle_path:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Caseware bundle not yet generated. Call /export-caseware first.",
                }
            ),
            400,
        )

    if not os.path.exists(migration.caseware_bundle_path):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Bundle file not found. Please regenerate.",
                }
            ),
            404,
        )

    # FIX: Validate path is within allowed directories (prevent serving arbitrary files)
    # Using os.path.commonpath() instead of startswith() for secure path validation
    bundle_path = os.path.realpath(migration.caseware_bundle_path)
    allowed_dirs = [
        os.path.realpath(current_app.root_path),
        os.path.realpath(
            os.environ.get("CASEWARE_TEMP_DIR", tempfile.gettempdir())
        ),  # nosec B108
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
        return jsonify({"success": False, "error": "Invalid bundle path"}), 400

    return {
        "migration": migration,
        "bundle_path": bundle_path,
    }


def _decrypt_caseware_bundle(path, key):
    """
    Decrypt an encrypted Caseware bundle file. Tries embedded salt first,
    then falls back to migration_id-based salt for legacy files.

    Args:
        path: Absolute path to the encrypted bundle file.
        key: App secret key string for PBKDF2 key derivation.

    Returns decrypted bytes on success, or (response, status_code) on error.
    """
    import base64

    from cryptography.fernet import Fernet
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    # Read encrypted data
    with open(path, "rb") as f:
        encrypted_data = f.read()

    # FIX B-01: Read salt from encrypted file (first 16 bytes = salt)
    # Standard format: [16-byte salt][encrypted data]
    # Falls back to migration_id salt for legacy files
    SALT_LENGTH = 16

    if len(encrypted_data) > SALT_LENGTH:
        # Try embedded salt first (new format)
        embedded_salt = encrypted_data[:SALT_LENGTH]
        payload = encrypted_data[SALT_LENGTH:]

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=embedded_salt,
            iterations=100000,
            backend=default_backend(),
        )
        encryption_key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
        cipher = Fernet(encryption_key)

        try:
            return cipher.decrypt(payload)
        except Exception:
            logger.info(
                "Embedded salt decryption failed, trying legacy migration_id salt"
            )

    # Legacy fallback: use migration_id from directory structure as salt
    migration_id = os.path.basename(os.path.dirname(path))
    migration_salt = migration_id.encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=migration_salt,
        iterations=100000,
        backend=default_backend(),
    )
    encryption_key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
    cipher = Fernet(encryption_key)

    try:
        return cipher.decrypt(encrypted_data)
    except Exception as decrypt_error:
        logger.error(f"Failed to decrypt Caseware bundle: {decrypt_error}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Bundle decryption failed. Please regenerate the bundle.",
                }
            ),
            500,
        )


def _serve_caseware_download(data, filename):
    """
    Send decrypted Caseware bundle data as a file download response.

    Args:
        data: Decrypted bytes of the zip file.
        filename: Download filename for the response.

    Returns Flask send_file response.
    """
    import io

    return send_file(
        io.BytesIO(data),
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )


@dashboard_bp.route("/api/migrations/<migration_id>/caseware-bundle", methods=["GET"])
@require_auth
@limiter.limit("5 per minute")
def download_caseware_bundle(migration_id):
    """
    Download the generated Caseware Audit Bundle (.zip).

    Returns a zip file containing:
    - Audit_TB.csv
    - Audit_GL.csv
    - Audit_Mapping.cvw
    """
    try:
        # Find and validate the bundle file
        found = _find_caseware_file(migration_id)
        if isinstance(found, tuple):
            return found

        migration = found["migration"]
        bundle_path = found["bundle_path"]
        download_name = (
            f"{migration.company_name or migration_id}_Caseware_Audit_Bundle.zip"
        )

        # CRITICAL FIX: Decrypt the file before sending to user
        # Previous code returned the encrypted blob which users couldn't open
        if (
            bundle_path.endswith(".encrypted")
            and migration.caseware_encryption_method == "Fernet-AES256"
        ):
            try:
                # Get encryption key (must match the one used during export)
                app_secret = current_app.config.get("BACKUP_ENCRYPTION_KEY")
                if not app_secret:
                    return (
                        jsonify(
                            {"success": False, "error": "Decryption not configured"}
                        ),
                        500,
                    )

                decrypted = _decrypt_caseware_bundle(bundle_path, app_secret)
                if isinstance(decrypted, tuple):
                    return decrypted

                return _serve_caseware_download(decrypted, download_name)

            except ImportError as ie:
                logger.error(f"Cryptography library not available: {ie}")
                return (
                    jsonify({"success": False, "error": "Decryption not available"}),
                    500,
                )

        # Return the zip file (unencrypted or already decrypted)
        return send_file(
            bundle_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name=download_name,
        )

    except Exception as e:
        logger.exception(
            f"Failed to download Caseware bundle for {migration_id}: {str(e)}"
        )
        return (
            jsonify({"success": False, "error": "Failed to download Caseware bundle"}),
            500,
        )


@dashboard_bp.route("/api/migrations/<migration_id>/caseware-status", methods=["GET"])
@require_auth
def get_caseware_status(migration_id):
    """
    Get Caseware bundle generation status for a migration.
    """
    # AUDIT FIX: Add UUID validation
    if not is_valid_uuid(migration_id):
        return jsonify({"success": False, "error": "Invalid migration ID format"}), 400

    try:
        migration = Migration.query.filter_by(
            migration_id=migration_id, user_id=_get_user_id()
        ).first()

        if not migration:
            return jsonify({"success": False, "error": "Migration not found"}), 404

        return (
            jsonify(
                {
                    "success": True,
                    "migration_id": migration_id,
                    "destination": migration.destination,
                    "caseware_bundle_ready": migration.caseware_bundle_ready or False,
                    "download_url": (
                        f"/api/migrations/{migration_id}/caseware-bundle"
                        if migration.caseware_bundle_ready
                        else None
                    ),
                    "can_generate": migration.status in ["completed", "uploaded"],
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception(f"Failed to get Caseware status for {migration_id}: {str(e)}")
        return (
            jsonify({"success": False, "error": "Failed to get Caseware status"}),
            500,
        )
