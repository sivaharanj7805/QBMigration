using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace QBMigrationLauncher.Services
{
    /// <summary>
    /// Generates Variance Reports comparing QB Desktop data to QBO data.
    /// This is the "CPA Sign-Off" feature - automatically verifies migration accuracy.
    /// </summary>
    public class VarianceReportService
    {
        private readonly string _outputDirectory;

        public VarianceReportService(string outputDirectory)
        {
            _outputDirectory = outputDirectory;
            Directory.CreateDirectory(_outputDirectory);
        }

        /// <summary>
        /// Generates a comprehensive variance report comparing source and destination.
        /// </summary>
        public string GenerateVarianceReport(VarianceReportData data)
        {
            var accountRows = new StringBuilder();
            foreach (var item in data.AccountComparisons)
            {
                var varianceClass = Math.Abs(item.Variance) > 0.50m ? "variance-high" : 
                                    Math.Abs(item.Variance) > 0.01m ? "variance-low" : "";
                
                accountRows.AppendLine($@"
                <tr class='{varianceClass}'>
                    <td>{EscapeHtml(item.AccountName)}</td>
                    <td>{EscapeHtml(item.AccountType)}</td>
                    <td class='amount'>${item.DesktopBalance:N2}</td>
                    <td class='amount'>${item.OnlineBalance:N2}</td>
                    <td class='amount'>${item.Variance:N2}</td>
                </tr>");
            }

            var html = $@"
<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <title>Post-Migration Variance Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .report {{ background: white; padding: 40px; max-width: 1000px; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ border-bottom: 3px solid #2CA01C; padding-bottom: 20px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; }}
        .logo {{ font-size: 36px; color: #2CA01C; font-weight: bold; }}
        .summary-box {{ background: #e8f5e9; padding: 20px; border-radius: 8px; margin: 20px 0; display: flex; justify-content: space-around; }}
        .summary-item {{ text-align: center; }}
        .summary-value {{ font-size: 32px; font-weight: bold; color: #2CA01C; }}
        .summary-label {{ color: #666; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f0f8f0; color: #333; }}
        .amount {{ text-align: right; font-family: 'Courier New', monospace; }}
        .variance-high {{ background: #ffebee; }}
        .variance-low {{ background: #fff8e1; }}
        .footer {{ text-align: center; margin-top: 40px; color: #666; font-size: 12px; }}
        .status-passed {{ color: #2CA01C; font-weight: bold; }}
        .status-warning {{ color: #ff9800; font-weight: bold; }}
        .status-failed {{ color: #d32f2f; font-weight: bold; }}
    </style>
</head>
<body>
    <div class='report'>
        <div class='header'>
            <div>
                <span class='logo'>Q</span>
                <h1 style='display:inline; margin-left:20px;'>Post-Migration Variance Report</h1>
            </div>
            <div>
                <p><strong>Company:</strong> {EscapeHtml(data.CompanyName)}</p>
                <p><strong>Migration ID:</strong> {EscapeHtml(data.MigrationId)}</p>
            </div>
        </div>
        
        <div class='summary-box'>
            <div class='summary-item'>
                <div class='summary-value'>${data.TotalDesktop:N2}</div>
                <div class='summary-label'>Desktop Total</div>
            </div>
            <div class='summary-item'>
                <div class='summary-value'>${data.TotalOnline:N2}</div>
                <div class='summary-label'>Online Total</div>
            </div>
            <div class='summary-item'>
                <div class='summary-value {(Math.Abs(data.TotalVariance) <= 0.50m ? "status-passed" : "status-warning")}'>${data.TotalVariance:N2}</div>
                <div class='summary-label'>Net Variance</div>
            </div>
        </div>
        
        <h2>Verification Status</h2>
        <p>{GetVerificationStatus(data.TotalVariance)}</p>
        
        <h2>Account-by-Account Comparison</h2>
        <table>
            <thead>
                <tr>
                    <th>Account Name</th>
                    <th>Type</th>
                    <th class='amount'>Desktop</th>
                    <th class='amount'>Online</th>
                    <th class='amount'>Variance</th>
                </tr>
            </thead>
            <tbody>
                {accountRows}
            </tbody>
        </table>
        
        <h2>Report Period</h2>
        <p><strong>From:</strong> {data.PeriodStart:MMM dd, yyyy} <strong>To:</strong> {data.PeriodEnd:MMM dd, yyyy}</p>
        
        <div class='footer'>
            <p>This report was generated automatically after migration verification.</p>
            <p>Generated: {DateTime.Now:yyyy-MM-dd HH:mm:ss}</p>
        </div>
    </div>
</body>
</html>";

            var fileName = $"VarianceReport_{data.MigrationId}.html";
            var filePath = Path.Combine(_outputDirectory, fileName);
            File.WriteAllText(filePath, html, Encoding.UTF8);
            
            return filePath;
        }

        private string GetVerificationStatus(decimal variance)
        {
            if (Math.Abs(variance) <= 0.01m)
                return "<span class='status-passed'>✓ VERIFIED: Perfect match - no variance detected.</span>";
            if (Math.Abs(variance) <= 0.50m)
                return "<span class='status-passed'>✓ VERIFIED: Acceptable variance (rounding).</span>";
            if (Math.Abs(variance) <= 10.00m)
                return "<span class='status-warning'>⚠ WARNING: Minor variance detected. Review highlighted rows.</span>";
            return "<span class='status-failed'>✗ ATTENTION REQUIRED: Significant variance detected. Manual review needed.</span>";
        }

        private string EscapeHtml(string? input)
        {
            if (string.IsNullOrEmpty(input)) return "";
            return input
                .Replace("&", "&amp;")
                .Replace("<", "&lt;")
                .Replace(">", "&gt;")
                .Replace("\"", "&quot;");
        }
    }

    public class VarianceReportData
    {
        public string CompanyName { get; set; } = "";
        public string MigrationId { get; set; } = "";
        public DateTime PeriodStart { get; set; }
        public DateTime PeriodEnd { get; set; }
        public decimal TotalDesktop { get; set; }
        public decimal TotalOnline { get; set; }
        public decimal TotalVariance => TotalOnline - TotalDesktop;
        public List<AccountComparison> AccountComparisons { get; set; } = new List<AccountComparison>();
    }

    public class AccountComparison
    {
        public string AccountName { get; set; } = "";
        public string AccountType { get; set; } = "";
        public decimal DesktopBalance { get; set; }
        public decimal OnlineBalance { get; set; }
        public decimal Variance => OnlineBalance - DesktopBalance;
    }
}
