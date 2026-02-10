"""
Variance Report Generator
========================
Generates side-by-side P&L and Balance Sheet comparison reports
for QBD source vs QBO destination to enable CPA sign-off.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List

logger = logging.getLogger(__name__)


class VarianceReportGenerator:
    """
    Generates automated variance reports comparing:
    - P&L for last 3 fiscal years
    - Balance Sheet comparison
    - Line-by-line variance highlighting
    """

    def __init__(self, company_name: str = ""):
        self.company_name = company_name
        self.tolerance = Decimal("0.01")  # Penny-perfect tolerance

    def generate_variance_report(
        self, source_data: Dict, destination_data: Dict, years: int = 3
    ) -> Dict:
        """
        Generate comprehensive variance report.

        Args:
            source_data: QBD trial balance, P&L, balance sheet
            destination_data: QBO trial balance, P&L, balance sheet
            years: Number of years to compare (default 3)

        Returns:
            Complete variance report dict
        """
        report = {
            "generated_at": datetime.now().isoformat(),
            "company_name": self.company_name,
            "years_compared": years,
            "overall_status": "PASS",
            "summary": {
                "total_variances": 0,
                "critical_variances": 0,
                "total_amount": Decimal("0"),
            },
            "trial_balance": self._compare_trial_balance(
                source_data.get("trial_balance", {}),
                destination_data.get("trial_balance", {}),
            ),
            "profit_loss": [],
            "balance_sheet": [],
            "account_details": [],
        }

        # Compare P&L by year
        for year in range(years):
            year_key = f"year_{year}"
            source_pl = source_data.get("profit_loss", {}).get(year_key, {})
            dest_pl = destination_data.get("profit_loss", {}).get(year_key, {})

            pl_comparison = self._compare_pl(source_pl, dest_pl, year)
            report["profit_loss"].append(pl_comparison)

            if pl_comparison["has_variance"]:
                report["summary"]["total_variances"] += len(pl_comparison["variances"])

        # Compare Balance Sheet
        source_bs = source_data.get("balance_sheet", {})
        dest_bs = destination_data.get("balance_sheet", {})
        report["balance_sheet"] = self._compare_balance_sheet(source_bs, dest_bs)

        # Compare individual accounts
        source_accounts = source_data.get("accounts", [])
        dest_accounts = destination_data.get("accounts", [])
        report["account_details"] = self._compare_accounts(
            source_accounts, dest_accounts
        )

        # Calculate totals
        for account in report["account_details"]:
            if account["has_variance"]:
                report["summary"]["total_variances"] += 1
                report["summary"]["total_amount"] += abs(
                    Decimal(str(account["variance"]))
                )

                if abs(Decimal(str(account["variance"]))) > 100:
                    report["summary"]["critical_variances"] += 1
                    report["overall_status"] = "FAIL"

        return report

    def _safe_decimal(self, value, default: str = "0") -> Decimal:
        """
        CRITICAL FIX: Safely convert value to Decimal, handling None and invalid inputs.

        Args:
            value: Value to convert (can be None, str, int, float, Decimal)
            default: Default value if conversion fails

        Returns:
            Decimal representation preserving precision
        """
        if value is None:
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        try:
            # Convert to string first to preserve precision (avoid float intermediary)
            return Decimal(str(value))
        except Exception:
            # AUDIT FIX CRIT-09: Refuse to silently default non-empty financial values
            # to zero — doing so could mask discrepancies and produce a false PASS
            str_val = str(value).strip()
            if str_val:
                raise ValueError(
                    f"Cannot convert financial value '{value}' to Decimal. "
                    "Refusing to silently default to zero."
                )
            logger.warning(
                f"Empty/whitespace value converted to default '{default}'"
            )
            return Decimal(default)

    def _decimal_to_str(self, value: Decimal) -> str:
        """
        CRITICAL FIX: Convert Decimal to string to preserve precision in JSON output.

        Using str() instead of float() prevents precision loss for financial values.
        Float cannot accurately represent values like 123.45 (becomes 123.45000000000001).
        """
        return str(value)

    def _compare_trial_balance(self, source: Dict, dest: Dict) -> Dict:
        """Compare trial balance totals."""
        # CRITICAL FIX: Use safe Decimal conversion to handle None values
        source_debits = self._safe_decimal(source.get("debits"))
        source_credits = self._safe_decimal(source.get("credits"))
        dest_debits = self._safe_decimal(dest.get("debits"))
        dest_credits = self._safe_decimal(dest.get("credits"))

        debit_variance = dest_debits - source_debits
        credit_variance = dest_credits - source_credits

        is_balanced = (
            abs(debit_variance) <= self.tolerance
            and abs(credit_variance) <= self.tolerance
        )

        # CRITICAL FIX: Use string representation to preserve Decimal precision
        # Float loses precision: float(Decimal("123.45")) may become 123.45000000000001
        return {
            "source_debits": self._decimal_to_str(source_debits),
            "source_credits": self._decimal_to_str(source_credits),
            "destination_debits": self._decimal_to_str(dest_debits),
            "destination_credits": self._decimal_to_str(dest_credits),
            "debit_variance": self._decimal_to_str(debit_variance),
            "credit_variance": self._decimal_to_str(credit_variance),
            "is_balanced": is_balanced,
            "status": "VERIFIED" if is_balanced else "VARIANCE DETECTED",
        }

    def _compare_pl(self, source: Dict, dest: Dict, year: int) -> Dict:
        """Compare P&L for a specific year."""
        variances = []

        # CRITICAL FIX: Use safe Decimal conversion to handle None values
        source_revenue = self._safe_decimal(source.get("total_revenue"))
        dest_revenue = self._safe_decimal(dest.get("total_revenue"))
        revenue_var = dest_revenue - source_revenue

        if abs(revenue_var) > self.tolerance:
            variances.append(
                {
                    "category": "Total Revenue",
                    "source": self._decimal_to_str(source_revenue),
                    "destination": self._decimal_to_str(dest_revenue),
                    "variance": self._decimal_to_str(revenue_var),
                    "severity": "CRITICAL" if abs(revenue_var) > 1000 else "WARNING",
                }
            )

        # Compare expenses
        source_expenses = self._safe_decimal(source.get("total_expenses"))
        dest_expenses = self._safe_decimal(dest.get("total_expenses"))
        expense_var = dest_expenses - source_expenses

        if abs(expense_var) > self.tolerance:
            variances.append(
                {
                    "category": "Total Expenses",
                    "source": self._decimal_to_str(source_expenses),
                    "destination": self._decimal_to_str(dest_expenses),
                    "variance": self._decimal_to_str(expense_var),
                    "severity": "CRITICAL" if abs(expense_var) > 1000 else "WARNING",
                }
            )

        # Compare net income
        source_net = source_revenue - source_expenses
        dest_net = dest_revenue - dest_expenses
        net_var = dest_net - source_net

        if abs(net_var) > self.tolerance:
            variances.append(
                {
                    "category": "Net Income",
                    "source": self._decimal_to_str(source_net),
                    "destination": self._decimal_to_str(dest_net),
                    "variance": self._decimal_to_str(net_var),
                    "severity": "CRITICAL" if abs(net_var) > 1000 else "WARNING",
                }
            )

        # CRITICAL FIX: Use string representation for all financial values
        return {
            "year_offset": year,
            "fiscal_year": datetime.now().year - year,
            "source_net_income": self._decimal_to_str(source_net),
            "destination_net_income": self._decimal_to_str(dest_net),
            "variance": self._decimal_to_str(net_var),
            "has_variance": len(variances) > 0,
            "variances": variances,
        }

    def _compare_balance_sheet(self, source: Dict, dest: Dict) -> Dict:
        """Compare balance sheet."""
        variances = []

        categories = [
            ("total_assets", "Total Assets"),
            ("total_liabilities", "Total Liabilities"),
            ("total_equity", "Total Equity"),
        ]

        # CRITICAL FIX: Use safe Decimal conversion
        for key, label in categories:
            source_val = self._safe_decimal(source.get(key))
            dest_val = self._safe_decimal(dest.get(key))
            variance = dest_val - source_val

            if abs(variance) > self.tolerance:
                variances.append(
                    {
                        "category": label,
                        "source": self._decimal_to_str(source_val),
                        "destination": self._decimal_to_str(dest_val),
                        "variance": self._decimal_to_str(variance),
                        "severity": "CRITICAL" if abs(variance) > 1000 else "WARNING",
                    }
                )

        # Check accounting equation: Assets = Liabilities + Equity
        source_assets = self._safe_decimal(source.get("total_assets"))
        source_liabilities = self._safe_decimal(source.get("total_liabilities"))
        source_equity = self._safe_decimal(source.get("total_equity"))
        source_balanced = (
            abs(source_assets - source_liabilities - source_equity) <= self.tolerance
        )

        dest_assets = self._safe_decimal(dest.get("total_assets"))
        dest_liabilities = self._safe_decimal(dest.get("total_liabilities"))
        dest_equity = self._safe_decimal(dest.get("total_equity"))
        dest_balanced = (
            abs(dest_assets - dest_liabilities - dest_equity) <= self.tolerance
        )

        # CRITICAL FIX: Use string representation for all financial values
        return {
            "source_assets": self._decimal_to_str(source_assets),
            "destination_assets": self._decimal_to_str(dest_assets),
            "source_liabilities": self._decimal_to_str(source_liabilities),
            "destination_liabilities": self._decimal_to_str(dest_liabilities),
            "source_equity": self._decimal_to_str(source_equity),
            "destination_equity": self._decimal_to_str(dest_equity),
            "source_balanced": source_balanced,
            "destination_balanced": dest_balanced,
            "has_variance": len(variances) > 0,
            "variances": variances,
        }

    def _compare_accounts(self, source: List, dest: List) -> List:
        """Compare individual accounts."""
        results = []

        # Create lookup by account name
        dest_lookup = {a.get("name", "").lower(): a for a in dest}

        for source_acct in source:
            name = source_acct.get("name", "")
            # CRITICAL FIX: Use safe Decimal conversion
            source_balance = self._safe_decimal(source_acct.get("balance"))

            dest_acct = dest_lookup.get(name.lower(), {})
            dest_balance = self._safe_decimal(dest_acct.get("balance"))

            variance = dest_balance - source_balance

            # CRITICAL FIX: Use string representation for financial values
            results.append(
                {
                    "account_name": name,
                    "account_type": source_acct.get("type", ""),
                    "source_balance": self._decimal_to_str(source_balance),
                    "destination_balance": self._decimal_to_str(dest_balance),
                    "variance": self._decimal_to_str(variance),
                    "has_variance": abs(variance) > self.tolerance,
                    "severity": self._get_severity(variance),
                    "matched_in_destination": name.lower() in dest_lookup,
                }
            )

        return results

    def _get_severity(self, variance: Decimal) -> str:
        """Determine severity level based on variance amount."""
        abs_var = abs(variance)
        if abs_var <= self.tolerance:
            return "OK"
        elif abs_var <= 10:
            return "INFO"
        elif abs_var <= 100:
            return "WARNING"
        else:
            return "CRITICAL"

    def generate_html_report(self, report: Dict, output_path: str) -> str:
        """Generate HTML variance report suitable for PDF conversion."""

        # Status colors
        status_color = "#10B981" if report["overall_status"] == "PASS" else "#DC2626"

        # Build account rows
        account_rows = ""
        for acct in report.get("account_details", []):
            severity_class = acct["severity"].lower()
            # FIX: Values are already strings from _decimal_to_str(), use directly
            variance_display = (
                f"${acct['variance']}" if acct["has_variance"] else "-"
            )
            account_rows += f"""
            <tr class="severity-{severity_class}">
                <td>{acct['account_name']}</td>
                <td>{acct['account_type']}</td>
                <td class="amount">${acct['source_balance']}</td>
                <td class="amount">${acct['destination_balance']}</td>
                <td class="amount variance">{variance_display}</td>
            </tr>
            """

        # Build P&L comparison rows
        pl_rows = ""
        for pl in report.get("profit_loss", []):
            status = "✓" if not pl["has_variance"] else "⚠"
            # FIX: Values are strings from _decimal_to_str(), use directly
            pl_rows += f"""
            <tr>
                <td>FY {pl['fiscal_year']}</td>
                <td class="amount">${pl['source_net_income']}</td>
                <td class="amount">${pl['destination_net_income']}</td>
                <td class="amount">${pl['variance']}</td>
                <td>{status}</td>
            </tr>
            """

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Variance Report - {report['company_name']}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif;
            background: #f8fafc; color: #1e293b; line-height: 1.6; }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 40px; }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
            color: white; padding: 30px; border-radius: 12px 12px 0 0; }}
        .header h1 {{ font-size: 24px; margin-bottom: 5px; }}
        .content {{ background: white; padding: 30px; border-radius: 0 0 12px 12px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; }}
        .summary-card {{ background: #f1f5f9; padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-value {{ font-size: 28px; font-weight: bold; }}
        .summary-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; }}
        .status-badge {{ display: inline-block; padding: 8px 16px;
            border-radius: 20px; font-weight: bold;
            color: white; background: {status_color}; }}
        h2 {{ margin: 30px 0 15px 0; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f8fafc; font-weight: 600; }}
        .amount {{ text-align: right; font-family: 'Consolas', monospace; }}
        .variance {{ font-weight: bold; }}
        .severity-ok td {{ background: #f0fdf4; }}
        .severity-info td {{ background: #f0f9ff; }}
        .severity-warning td {{ background: #fffbeb; }}
        .severity-critical td {{ background: #fef2f2; }}
        .footer {{ text-align: center; padding: 20px; color: #64748b; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Migration Variance Report</h1>
            <p>{report['company_name']} | Generated: {report['generated_at'][:10]}</p>
        </div>

        <div class="content">
            <div style="text-align: center; margin-bottom: 30px;">
                <span class="status-badge">{report['overall_status']}</span>
            </div>

            <div class="summary-grid">
                <div class="summary-card">
                    <div class="summary-value">{report['summary']['total_variances']}</div>
                    <div class="summary-label">Total Variances</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value">{report['summary']['critical_variances']}</div>
                    <div class="summary-label">Critical Variances</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value">${float(report['summary']['total_amount']):,.2f}</div>
                    <div class="summary-label">Total Variance Amount</div>
                </div>
            </div>

            <h2>Trial Balance Comparison</h2>
            <table>
                <tr>
                    <th></th>
                    <th class="amount">Source (QBD)</th>
                    <th class="amount">Destination (QBO)</th>
                    <th class="amount">Variance</th>
                </tr>
                <tr>
                    <td>Total Debits</td>
                    <td class="amount">${report['trial_balance']['source_debits']:,.2f}</td>
                    <td class="amount">${report['trial_balance']['destination_debits']:,.2f}</td>
                    <td class="amount">${report['trial_balance']['debit_variance']:,.2f}</td>
                </tr>
                <tr>
                    <td>Total Credits</td>
                    <td class="amount">${report['trial_balance']['source_credits']:,.2f}</td>
                    <td class="amount">${report['trial_balance']['destination_credits']:,.2f}</td>
                    <td class="amount">${report['trial_balance']['credit_variance']:,.2f}</td>
                </tr>
            </table>
            <p><strong>Status:</strong> {report['trial_balance']['status']}</p>

            <h2>Profit & Loss Comparison ({report['years_compared']} Years)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Fiscal Year</th>
                        <th class="amount">Source Net Income</th>
                        <th class="amount">Dest Net Income</th>
                        <th class="amount">Variance</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {pl_rows or '<tr><td colspan="5">No P&L data available</td></tr>'}
                </tbody>
            </table>

            <h2>Account-Level Detail</h2>
            <table>
                <thead>
                    <tr>
                        <th>Account</th>
                        <th>Type</th>
                        <th class="amount">Source</th>
                        <th class="amount">Destination</th>
                        <th class="amount">Variance</th>
                    </tr>
                </thead>
                <tbody>
                    {account_rows or '<tr><td colspan="5">No account data available</td></tr>'}
                </tbody>
            </table>
        </div>

        <div class="footer">
            <p>ForensicBridge Variance Report | CPA Sign-Off Document</p>
            <p>This report compares source QuickBooks Desktop data with destination QuickBooks Online data.</p>
        </div>
    </div>
</body>
</html>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return output_path


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Sample data
    source_data = {
        "trial_balance": {"debits": 1500000, "credits": 1500000},
        "profit_loss": {
            "year_0": {"total_revenue": 800000, "total_expenses": 600000},
            "year_1": {"total_revenue": 750000, "total_expenses": 550000},
            "year_2": {"total_revenue": 700000, "total_expenses": 500000},
        },
        "balance_sheet": {
            "total_assets": 1500000,
            "total_liabilities": 700000,
            "total_equity": 800000,
        },
        "accounts": [
            {"name": "Cash", "type": "Bank", "balance": 250000},
            {"name": "Accounts Receivable", "type": "AR", "balance": 125000},
            {"name": "Revenue", "type": "Income", "balance": 800000},
        ],
    }

    dest_data = {
        "trial_balance": {"debits": 1500000, "credits": 1500000},
        "profit_loss": {
            "year_0": {"total_revenue": 800000, "total_expenses": 600000},
            "year_1": {"total_revenue": 750000, "total_expenses": 550000},
            "year_2": {"total_revenue": 700000, "total_expenses": 500000},
        },
        "balance_sheet": {
            "total_assets": 1500000,
            "total_liabilities": 700000,
            "total_equity": 800000,
        },
        "accounts": [
            {"name": "Cash", "type": "Bank", "balance": 250000},
            {"name": "Accounts Receivable", "type": "AR", "balance": 125000},
            {"name": "Revenue", "type": "Income", "balance": 800000},
        ],
    }

    generator = VarianceReportGenerator("Test Company Inc.")
    report = generator.generate_variance_report(source_data, dest_data)

    logger.info(f"Overall Status: {report['overall_status']}")
    logger.info(f"Total Variances: {report['summary']['total_variances']}")

    # Generate HTML
    generator.generate_html_report(report, "variance_report.html")
    logger.info("HTML report generated: variance_report.html")
