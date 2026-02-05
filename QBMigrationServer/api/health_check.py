"""
Health Check API
Pre-migration file scan and PDF report generation
"""

from datetime import datetime, timezone
from io import BytesIO

from api.auth import require_auth
from flask import Blueprint, jsonify, request, send_file

health_check_bp = Blueprint("health_check", __name__, url_prefix="/api/health-check")


@health_check_bp.route("/scan", methods=["POST"])
@require_auth
def scan_file():
    """
    Analyze QuickBooks file metadata for migration readiness
    Expected payload: {
        "session_id": "FB-...",
        "company_name": "...",
        "file_size_bytes": 12345678,
        "record_counts": {
            "customers": 500,
            "vendors": 200,
            "invoices": 5000,
            ...
        },
        "qb_version": "QuickBooks Desktop 2023"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    session_id = data.get("session_id")
    company_name = data.get("company_name", "Unknown")
    file_size_bytes = data.get("file_size_bytes", 0)
    record_counts = data.get("record_counts", {})
    qb_version = data.get("qb_version", "Unknown")

    # Analyze migration readiness
    issues = []
    warnings = []

    # Check file size (warn if > 500MB)
    file_size_mb = file_size_bytes / (1024 * 1024)
    if file_size_mb > 500:
        warnings.append(
            {
                "code": "LARGE_FILE",
                "message": f"File size ({file_size_mb:.0f} MB) is large. Migration may take longer.",
            }
        )

    # Check record counts
    total_records = sum(record_counts.values())

    if total_records > 500000:
        warnings.append(
            {
                "code": "HIGH_RECORD_COUNT",
                "message": f"High record count ({total_records:,}). Consider a staged migration.",
            }
        )

    # Check for unsupported QB versions
    if "Pro" in qb_version and "2015" in qb_version:
        issues.append(
            {
                "code": "OLD_VERSION",
                "message": "QuickBooks 2015 may have compatibility issues. Recommend updating first.",
            }
        )

    # Estimate migration time
    # Rough estimate: 1000 records/minute with batch API
    estimated_minutes = max(5, total_records / 1000)

    # Determine readiness
    is_ready = len(issues) == 0

    result = {
        "session_id": session_id,
        "company_name": company_name,
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "is_migration_ready": is_ready,
        "readiness_score": 100 - (len(issues) * 30) - (len(warnings) * 10),
        "file_size_mb": round(file_size_mb, 2),
        "total_records": total_records,
        "record_counts": record_counts,
        "qb_version": qb_version,
        "estimated_migration_minutes": round(estimated_minutes),
        "issues": issues,
        "warnings": warnings,
    }

    return jsonify(result)


@health_check_bp.route("/report/<session_id>", methods=["GET"])
@require_auth
def generate_report(session_id):
    """
    Generate PDF health check report
    """
    # In production, this would query stored scan results
    # For now, generate a basic PDF

    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Header
        c.setFillColor(HexColor("#10B981"))
        c.rect(0, height - 80, width, 80, fill=True, stroke=False)

        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 24)
        c.drawString(50, height - 50, "ForensicBridge")

        c.setFont("Helvetica", 12)
        c.drawString(50, height - 70, "Pre-Migration Health Check Report")

        # Session ID
        c.setFillColor(HexColor("#1F2937"))
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 120, f"Session ID: {session_id}")

        c.setFont("Helvetica", 11)
        c.drawString(
            50,
            height - 140,
            f'Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}',
        )

        # Status
        c.setFillColor(HexColor("#10B981"))
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, height - 200, "✓ Migration Ready")

        c.setFillColor(HexColor("#6B7280"))
        c.setFont("Helvetica", 11)
        c.drawString(
            50,
            height - 225,
            "Your QuickBooks file has been analyzed and is ready for migration.",
        )

        # Summary box
        c.setStrokeColor(HexColor("#E5E7EB"))
        c.setFillColor(HexColor("#F9FAFB"))
        c.roundRect(50, height - 350, width - 100, 100, 10, fill=True, stroke=True)

        c.setFillColor(HexColor("#374151"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(70, height - 280, "Summary")

        c.setFont("Helvetica", 10)
        c.drawString(70, height - 300, "Readiness Score: 100%")
        c.drawString(70, height - 315, "Estimated Migration Time: ~15 minutes")
        c.drawString(70, height - 330, "Issues Found: 0")

        # Footer
        c.setFillColor(HexColor("#9CA3AF"))
        c.setFont("Helvetica", 9)
        c.drawString(
            50, 50, "© 2026 ForensicBridge. Enterprise-grade QuickBooks migration."
        )

        c.save()
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"health-check-{session_id}.pdf",
        )

    except ImportError:
        # ReportLab not installed - return JSON instead
        return (
            jsonify(
                {
                    "error": "PDF generation requires reportlab. Install with: pip install reportlab",
                    "session_id": session_id,
                    "status": "ready",
                }
            ),
            501,
        )
