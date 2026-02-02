"""
Variance Report Generator
========================
Generates side-by-side P&L and Balance Sheet comparison reports
for QBD source vs QBO destination to enable CPA sign-off.
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from pathlib import Path
import logging

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
        self,
        source_data: Dict,
        destination_data: Dict,
        years: int = 3
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
                "total_amount": Decimal("0")
            },
            "trial_balance": self._compare_trial_balance(
                source_data.get("trial_balance", {}),
                destination_data.get("trial_balance", {})
            ),
            "profit_loss": [],
            "balance_sheet": [],
            "account_details": []
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
        report["account_details"] = self._compare_accounts(source_accounts, dest_accounts)
        
        # Calculate totals
        for account in report["account_details"]:
            if account["has_variance"]:
                report["summary"]["total_variances"] += 1
                report["summary"]["total_amount"] += abs(Decimal(str(account["variance"])))
                
                if abs(Decimal(str(account["variance"]))) > 100:
                    report["summary"]["critical_variances"] += 1
                    report["overall_status"] = "FAIL"
        
        return report
    
    def _compare_trial_balance(self, source: Dict, dest: Dict) -> Dict:
        """Compare trial balance totals."""
        source_debits = Decimal(str(source.get("debits", 0)))
        source_credits = Decimal(str(source.get("credits", 0)))
        dest_debits = Decimal(str(dest.get("debits", 0)))
        dest_credits = Decimal(str(dest.get("credits", 0)))
        
        debit_variance = dest_debits - source_debits
        credit_variance = dest_credits - source_credits
        
        is_balanced = (
            abs(debit_variance) <= self.tolerance and 
            abs(credit_variance) <= self.tolerance
        )
        
        return {
            "source_debits": float(source_debits),
            "source_credits": float(source_credits),
            "destination_debits": float(dest_debits),
            "destination_credits": float(dest_credits),
            "debit_variance": float(debit_variance),
            "credit_variance": float(credit_variance),
            "is_balanced": is_balanced,
            "status": "VERIFIED" if is_balanced else "VARIANCE DETECTED"
        }
    
    def _compare_pl(self, source: Dict, dest: Dict, year: int) -> Dict:
        """Compare P&L for a specific year."""
        variances = []
        
        # Compare revenue
        source_revenue = Decimal(str(source.get("total_revenue", 0)))
        dest_revenue = Decimal(str(dest.get("total_revenue", 0)))
        revenue_var = dest_revenue - source_revenue
        
        if abs(revenue_var) > self.tolerance:
            variances.append({
                "category": "Total Revenue",
                "source": float(source_revenue),
                "destination": float(dest_revenue),
                "variance": float(revenue_var),
                "severity": "CRITICAL" if abs(revenue_var) > 1000 else "WARNING"
            })
        
        # Compare expenses
        source_expenses = Decimal(str(source.get("total_expenses", 0)))
        dest_expenses = Decimal(str(dest.get("total_expenses", 0)))
        expense_var = dest_expenses - source_expenses
        
        if abs(expense_var) > self.tolerance:
            variances.append({
                "category": "Total Expenses",
                "source": float(source_expenses),
                "destination": float(dest_expenses),
                "variance": float(expense_var),
                "severity": "CRITICAL" if abs(expense_var) > 1000 else "WARNING"
            })
        
        # Compare net income
        source_net = source_revenue - source_expenses
        dest_net = dest_revenue - dest_expenses
        net_var = dest_net - source_net
        
        if abs(net_var) > self.tolerance:
            variances.append({
                "category": "Net Income",
                "source": float(source_net),
                "destination": float(dest_net),
                "variance": float(net_var),
                "severity": "CRITICAL" if abs(net_var) > 1000 else "WARNING"
            })
        
        return {
            "year_offset": year,
            "fiscal_year": datetime.now().year - year,
            "source_net_income": float(source_net),
            "destination_net_income": float(dest_net),
            "variance": float(net_var),
            "has_variance": len(variances) > 0,
            "variances": variances
        }
    
    def _compare_balance_sheet(self, source: Dict, dest: Dict) -> Dict:
        """Compare balance sheet."""
        variances = []
        
        categories = [
            ("total_assets", "Total Assets"),
            ("total_liabilities", "Total Liabilities"),
            ("total_equity", "Total Equity")
        ]
        
        for key, label in categories:
            source_val = Decimal(str(source.get(key, 0)))
            dest_val = Decimal(str(dest.get(key, 0)))
            variance = dest_val - source_val
            
            if abs(variance) > self.tolerance:
                variances.append({
                    "category": label,
                    "source": float(source_val),
                    "destination": float(dest_val),
                    "variance": float(variance),
                    "severity": "CRITICAL" if abs(variance) > 1000 else "WARNING"
                })
        
        # Check accounting equation: Assets = Liabilities + Equity
        source_balanced = abs(
            Decimal(str(source.get("total_assets", 0))) -
            Decimal(str(source.get("total_liabilities", 0))) -
            Decimal(str(source.get("total_equity", 0)))
        ) <= self.tolerance
        
        dest_balanced = abs(
            Decimal(str(dest.get("total_assets", 0))) -
            Decimal(str(dest.get("total_liabilities", 0))) -
            Decimal(str(dest.get("total_equity", 0)))
        ) <= self.tolerance
        
        return {
            "source_assets": float(source.get("total_assets", 0)),
            "destination_assets": float(dest.get("total_assets", 0)),
            "source_liabilities": float(source.get("total_liabilities", 0)),
            "destination_liabilities": float(dest.get("total_liabilities", 0)),
            "source_equity": float(source.get("total_equity", 0)),
            "destination_equity": float(dest.get("total_equity", 0)),
            "source_balanced": source_balanced,
            "destination_balanced": dest_balanced,
            "has_variance": len(variances) > 0,
            "variances": variances
        }
    
    def _compare_accounts(self, source: List, dest: List) -> List:
        """Compare individual accounts."""
        results = []
        
        # Create lookup by account name
        dest_lookup = {a.get("name", "").lower(): a for a in dest}
        
        for source_acct in source:
            name = source_acct.get("name", "")
            source_balance = Decimal(str(source_acct.get("balance", 0)))
            
            dest_acct = dest_lookup.get(name.lower(), {})
            dest_balance = Decimal(str(dest_acct.get("balance", 0)))
            
            variance = dest_balance - source_balance
            
            results.append({
                "account_name": name,
                "account_type": source_acct.get("type", ""),
                "source_balance": float(source_balance),
                "destination_balance": float(dest_balance),
                "variance": float(variance),
                "has_variance": abs(variance) > self.tolerance,
                "severity": self._get_severity(variance),
                "matched_in_destination": name.lower() in dest_lookup
            })
        
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
            variance_display = f"${acct['variance']:,.2f}" if acct["has_variance"] else "-"
            account_rows += f"""
            <tr class="severity-{severity_class}">
                <td>{acct['account_name']}</td>
                <td>{acct['account_type']}</td>
                <td class="amount">${acct['source_balance']:,.2f}</td>
                <td class="amount">${acct['destination_balance']:,.2f}</td>
                <td class="amount variance">{variance_display}</td>
            </tr>
            """
        
        # Build P&L comparison rows
        pl_rows = ""
        for pl in report.get("profit_loss", []):
            status = "✓" if not pl["has_variance"] else "⚠"
            pl_rows += f"""
            <tr>
                <td>FY {pl['fiscal_year']}</td>
                <td class="amount">${pl['source_net_income']:,.2f}</td>
                <td class="amount">${pl['destination_net_income']:,.2f}</td>
                <td class="amount">${pl['variance']:,.2f}</td>
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
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.6; }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 40px; }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%); color: white; padding: 30px; border-radius: 12px 12px 0 0; }}
        .header h1 {{ font-size: 24px; margin-bottom: 5px; }}
        .content {{ background: white; padding: 30px; border-radius: 0 0 12px 12px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; }}
        .summary-card {{ background: #f1f5f9; padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-value {{ font-size: 28px; font-weight: bold; }}
        .summary-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; }}
        .status-badge {{ display: inline-block; padding: 8px 16px; border-radius: 20px; font-weight: bold; color: white; background: {status_color}; }}
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
        
        with open(output_path, 'w', encoding='utf-8') as f:
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
            "year_2": {"total_revenue": 700000, "total_expenses": 500000}
        },
        "balance_sheet": {
            "total_assets": 1500000,
            "total_liabilities": 700000,
            "total_equity": 800000
        },
        "accounts": [
            {"name": "Cash", "type": "Bank", "balance": 250000},
            {"name": "Accounts Receivable", "type": "AR", "balance": 125000},
            {"name": "Revenue", "type": "Income", "balance": 800000}
        ]
    }
    
    dest_data = {
        "trial_balance": {"debits": 1500000, "credits": 1500000},
        "profit_loss": {
            "year_0": {"total_revenue": 800000, "total_expenses": 600000},
            "year_1": {"total_revenue": 750000, "total_expenses": 550000},
            "year_2": {"total_revenue": 700000, "total_expenses": 500000}
        },
        "balance_sheet": {
            "total_assets": 1500000,
            "total_liabilities": 700000,
            "total_equity": 800000
        },
        "accounts": [
            {"name": "Cash", "type": "Bank", "balance": 250000},
            {"name": "Accounts Receivable", "type": "AR", "balance": 125000},
            {"name": "Revenue", "type": "Income", "balance": 800000}
        ]
    }
    
    generator = VarianceReportGenerator("Test Company Inc.")
    report = generator.generate_variance_report(source_data, dest_data)
    
    logger.info(f"Overall Status: {report['overall_status']}")
    logger.info(f"Total Variances: {report['summary']['total_variances']}")
    
    # Generate HTML
    generator.generate_html_report(report, "variance_report.html")
    logger.info("HTML report generated: variance_report.html")
