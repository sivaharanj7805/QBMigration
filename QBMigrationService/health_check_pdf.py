"""
Health Check PDF Report Generator
=================================
Generates a professional PDF report for pre-migration health checks.
Outputs: Red/Yellow/Green status for migration readiness.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthCheckPDFGenerator:
    """
    Generates PDF health check reports for QuickBooks files.

    Report includes:
    - Executive Summary (Red/Yellow/Green)
    - Data Quality Issues
    - Migration Recommendations
    - Estimated Migration Time
    - Required QBO Plan Tier
    """

    def __init__(self, company_name: str = "ForensicBridge"):
        self.company_name = company_name
        self.report_data = {}

    def analyze_health_check(self, scan_results: Dict) -> Dict:
        """
        Analyze scan results and categorize issues.

        Returns:
            Dict with severity levels and recommendations
        """
        analysis = {
            "overall_status": "GREEN",  # Will be updated based on issues
            "critical_issues": [],
            "warnings": [],
            "recommendations": [],
            "stats": {
                "total_records": 0,
                "problematic_records": 0,
                "estimated_migration_hours": 0,
            },
            "recommended_qbo_plan": "Plus",
        }

        # Count total records
        total = 0
        for entity_type in ["Customers", "Vendors", "Invoices", "Bills", "Accounts"]:
            count = len(scan_results.get(entity_type, []))
            total += count
        analysis["stats"]["total_records"] = total

        # Check for critical issues (RED)
        errors = scan_results.get("errors", [])
        for error in errors:
            analysis["critical_issues"].append(error)
            analysis["overall_status"] = "RED"

        # Check for warnings (YELLOW)
        warnings = scan_results.get("warnings", [])
        for warning in warnings:
            analysis["warnings"].append(warning)
            if analysis["overall_status"] == "GREEN":
                analysis["overall_status"] = "YELLOW"

        # Determine QBO plan based on record count
        if total > 500000:
            analysis["recommended_qbo_plan"] = "Advanced"
            analysis["recommendations"].append(
                f"With {total:,} records, you need QBO Advanced for optimal performance."
            )
        elif total > 100000:
            analysis["recommended_qbo_plan"] = "Plus"
            analysis["recommendations"].append(
                f"With {total:,} records, QBO Plus is recommended."
            )
        else:
            analysis["recommended_qbo_plan"] = "Essentials"

        # Estimate migration time (500K records/hour)
        hours = max(1, total / 500000)
        analysis["stats"]["estimated_migration_hours"] = round(hours, 1)

        # Add recommendations from scan
        recs = scan_results.get("recommendations", [])
        analysis["recommendations"].extend(recs)

        return analysis

    def generate_html_report(self, scan_results: Dict, output_path: str) -> str:
        """
        Generate an HTML report that can be converted to PDF.

        Args:
            scan_results: Results from SecurityManager.pre_migration_scan()
            output_path: Path to save the HTML file

        Returns:
            Path to the generated HTML file
        """
        analysis = self.analyze_health_check(scan_results)

        # Status colors
        status_colors = {"GREEN": "#10B981", "YELLOW": "#F59E0B", "RED": "#DC2626"}
        status_color = status_colors[analysis["overall_status"]]

        # Status icons
        status_icons = {"GREEN": "✓", "YELLOW": "⚠", "RED": "✗"}
        status_icon = status_icons[analysis["overall_status"]]

        # Build HTML
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Migration Health Check Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: #f8fafc;
            color: #1e293b;
            line-height: 1.6;
        }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 40px; }}
        
        /* Header */
        .header {{
            background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
            color: white;
            padding: 40px;
            border-radius: 12px 12px 0 0;
            text-align: center;
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .header .subtitle {{ opacity: 0.8; font-size: 14px; }}
        
        /* Status Badge */
        .status-badge {{
            display: inline-block;
            background: {status_color};
            color: white;
            font-size: 48px;
            width: 100px;
            height: 100px;
            border-radius: 50%;
            line-height: 100px;
            margin: 20px 0;
            font-weight: bold;
        }}
        .status-text {{
            font-size: 24px;
            color: {status_color};
            font-weight: bold;
            margin-bottom: 10px;
        }}
        
        /* Content */
        .content {{ background: white; padding: 40px; }}
        .section {{ margin-bottom: 30px; }}
        .section-title {{
            font-size: 18px;
            color: #0f172a;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }}
        
        /* Stats Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: #f1f5f9;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            color: #0f172a;
        }}
        .stat-label {{
            font-size: 12px;
            color: #64748b;
            text-transform: uppercase;
        }}
        
        /* Issues List */
        .issue {{
            padding: 12px 16px;
            margin: 8px 0;
            border-radius: 6px;
            border-left: 4px solid;
        }}
        .issue.critical {{
            background: #fef2f2;
            border-color: #dc2626;
        }}
        .issue.warning {{
            background: #fffbeb;
            border-color: #f59e0b;
        }}
        .issue.info {{
            background: #f0fdf4;
            border-color: #10b981;
        }}
        
        /* Footer */
        .footer {{
            background: #f1f5f9;
            padding: 20px 40px;
            border-radius: 0 0 12px 12px;
            text-align: center;
            font-size: 12px;
            color: #64748b;
        }}
        
        /* Print styles */
        @media print {{
            body {{ background: white; }}
            .container {{ padding: 0; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Migration Health Check Report</h1>
            <div class="subtitle">Generated by {self.company_name} • {datetime.now().strftime('%B %d, %Y')}</div>
        </div>
        
        <div class="content">
            <!-- Executive Summary -->
            <div class="section" style="text-align: center;">
                <div class="status-badge">{status_icon}</div>
                <div class="status-text">Migration Readiness: {analysis['overall_status']}</div>
                <p>
                    {self._get_status_message(analysis['overall_status'])}
                </p>
            </div>
            
            <!-- Stats -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{analysis['stats']['total_records']:,}</div>
                    <div class="stat-label">Total Records</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{analysis['stats']['estimated_migration_hours']}h</div>
                    <div class="stat-label">Est. Migration Time</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{analysis['recommended_qbo_plan']}</div>
                    <div class="stat-label">Recommended Plan</div>
                </div>
            </div>
            
            <!-- Critical Issues -->
            {self._render_issues_section("Critical Issues", analysis['critical_issues'], "critical")}
            
            <!-- Warnings -->
            {self._render_issues_section("Warnings", analysis['warnings'], "warning")}
            
            <!-- Recommendations -->
            {self._render_issues_section("Recommendations", analysis['recommendations'], "info")}
        </div>
        
        <div class="footer">
            <strong>{self.company_name}</strong> • Secure QuickBooks Migration Platform<br>
            This report is confidential and intended for the recipient only.
        </div>
    </div>
</body>
</html>
"""

        # Write HTML file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return output_path

    def _get_status_message(self, status: str) -> str:
        messages = {
            "GREEN": "Your QuickBooks file is ready for migration. No critical issues detected.",
            "YELLOW": "Your file can be migrated, but some issues should be reviewed first.",
            "RED": "Critical issues detected. These must be resolved before migration.",
        }
        return messages.get(status, "")

    def _render_issues_section(
        self, title: str, issues: List[str], css_class: str
    ) -> str:
        if not issues:
            return ""

        items = "\n".join(
            [f'<div class="issue {css_class}">{issue}</div>' for issue in issues]
        )

        return f"""
            <div class="section">
                <h3 class="section-title">{title}</h3>
                {items}
            </div>
        """

    def generate_pdf(self, scan_results: Dict, output_path: str) -> str:
        """
        Generate a PDF report.

        Note: Requires wkhtmltopdf or weasyprint installed.
        Falls back to HTML if PDF generation not available.
        """
        # Generate HTML first
        html_path = output_path.replace(".pdf", ".html")
        self.generate_html_report(scan_results, html_path)

        # Try to convert to PDF
        try:
            import subprocess

            # Try wkhtmltopdf
            result = subprocess.run(
                [
                    "wkhtmltopdf",
                    "--enable-local-file-access",
                    "--page-size",
                    "Letter",
                    "--margin-top",
                    "10mm",
                    "--margin-bottom",
                    "10mm",
                    html_path,
                    output_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                return output_path

        except FileNotFoundError:
            pass

        # Fallback: return HTML path
        logger.info(f"PDF generation not available. HTML report saved to: {html_path}")
        return html_path


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Sample scan results
    sample_results = {
        "Customers": [{"Name": "Customer 1"}, {"Name": "Customer 2"}] * 50000,
        "Invoices": [{"RefNumber": "1001"}] * 100000,
        "errors": [
            "12,340 corrupt transaction links detected",
            "Multi-user mode is enabled - please switch to single-user",
        ],
        "warnings": [
            "Duplicate customer name: 'John Smith' appears 15 times",
            "Invalid characters in 23 invoice descriptions",
        ],
        "recommendations": [
            "Clean up inactive customers before migration",
            "Archive transactions older than 3 years",
        ],
        "should_proceed": False,
    }

    # Generate report
    generator = HealthCheckPDFGenerator("ForensicBridge")
    output = generator.generate_html_report(sample_results, "health_check_report.html")
    logger.info(f"Report generated: {output}")
