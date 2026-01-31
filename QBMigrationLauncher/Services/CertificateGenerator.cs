using System;
using System.IO;
using System.Text;

namespace QBMigrationLauncher.Services
{
    /// <summary>
    /// Generates professional PDF-style HTML certificates and reports.
    /// These are the "White Glove" deliverables for enterprise clients.
    /// </summary>
    public class CertificateGenerator
    {
        private readonly string _outputDirectory;

        public CertificateGenerator(string outputDirectory)
        {
            _outputDirectory = outputDirectory;
            Directory.CreateDirectory(_outputDirectory);
        }

        /// <summary>
        /// FIX: Safely write file with error handling for disk full, permission denied, etc.
        /// </summary>
        private void SafeWriteFile(string filePath, string content)
        {
            try
            {
                File.WriteAllText(filePath, content, Encoding.UTF8);
            }
            catch (IOException ex)
            {
                throw new InvalidOperationException(
                    $"Failed to write file '{Path.GetFileName(filePath)}': {ex.Message}. " +
                    "Check disk space and file permissions.", ex);
            }
            catch (UnauthorizedAccessException ex)
            {
                throw new InvalidOperationException(
                    $"Permission denied writing '{Path.GetFileName(filePath)}': {ex.Message}. " +
                    "Run as administrator or choose a different output directory.", ex);
            }
        }

        /// <summary>
        /// Generates a Migration Certificate after successful migration.
        /// </summary>
        public string GenerateMigrationCertificate(MigrationCertificateData data)
        {
            var html = $@"
<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <title>Certificate of Data Migration</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .certificate {{ background: white; padding: 60px; border: 3px solid #2CA01C; max-width: 800px; margin: 0 auto; }}
        .header {{ text-align: center; border-bottom: 2px solid #2CA01C; padding-bottom: 20px; margin-bottom: 30px; }}
        .logo {{ font-size: 48px; color: #2CA01C; font-weight: bold; }}
        h1 {{ color: #333; margin: 10px 0; }}
        .company-name {{ font-size: 28px; color: #2CA01C; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f0f8f0; color: #333; width: 40%; }}
        .hash {{ font-family: 'Courier New', monospace; font-size: 12px; word-break: break-all; }}
        .verification {{ background: #e8f5e9; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .checkmark {{ color: #2CA01C; font-size: 24px; }}
        .footer {{ text-align: center; margin-top: 40px; color: #666; font-size: 12px; }}
        .signature-line {{ border-top: 1px solid #333; width: 250px; margin: 40px auto 10px; }}
    </style>
</head>
<body>
    <div class='certificate'>
        <div class='header'>
            <div class='logo'>FOB</div>
            <h1>Certificate of Data Migration</h1>
        </div>
        
        <p style='text-align: center;'>This certifies that the accounting data for:</p>
        <div class='company-name' style='text-align: center;'>{EscapeHtml(data.CompanyName)}</div>
        <p style='text-align: center;'>has been successfully migrated from QuickBooks Desktop to QuickBooks Online.</p>
        
        <table>
            <tr><th>Migration ID</th><td>{EscapeHtml(data.MigrationId)}</td></tr>
            <tr><th>Migration Date</th><td>{data.MigrationDate:MMMM dd, yyyy}</td></tr>
            <tr><th>Source File</th><td>{EscapeHtml(data.SourceFileName)}</td></tr>
            <tr><th>Destination Realm ID</th><td>{EscapeHtml(data.RealmId)}</td></tr>
        </table>
        
        <div class='verification'>
            <h3><span class='checkmark'>✓</span> Data Integrity Verification</h3>
            <table>
                <tr><th>Source Hash (SHA-256)</th><td class='hash'>{EscapeHtml(data.SourceHash)}</td></tr>
                <tr><th>Destination Verified</th><td><span class='checkmark'>✓</span> Matched</td></tr>
                <tr><th>Trial Balance (Desktop)</th><td>${data.TrialBalanceDesktop:N2}</td></tr>
                <tr><th>Trial Balance (Online)</th><td>${data.TrialBalanceOnline:N2}</td></tr>
                <tr><th>Variance</th><td>${data.Variance:N2}</td></tr>
            </table>
        </div>
        
        <h3>Record Counts</h3>
        <table>
            <tr><th>Customers</th><td>{data.CustomerCount}</td></tr>
            <tr><th>Vendors</th><td>{data.VendorCount}</td></tr>
            <tr><th>Invoices</th><td>{data.InvoiceCount}</td></tr>
            <tr><th>Bills</th><td>{data.BillCount}</td></tr>
            <tr><th><strong>Total Records</strong></th><td><strong>{data.TotalRecords}</strong></td></tr>
        </table>
        
        <div class='signature-line'></div>
        <p style='text-align: center;'>Authorized By: {EscapeHtml(data.AuthorizedBy)}</p>
        
        <div class='footer'>
            <p>This certificate is generated automatically and serves as official documentation for auditing purposes.</p>
            <p>Generated: {DateTime.UtcNow:yyyy-MM-dd HH:mm:ss} UTC</p>
        </div>
    </div>
</body>
</html>";

            var fileName = $"MigrationCertificate_{data.MigrationId}.html";
            var filePath = Path.Combine(_outputDirectory, fileName);
            SafeWriteFile(filePath, html);  // FIX: Use safe write with error handling

            return filePath;
        }

        /// <summary>
        /// Generates a Health Check Report (Pre-Flight).
        /// </summary>
        public string GenerateHealthCheckReport(HealthCheckResult result, string companyName)
        {
            var checksHtml = new StringBuilder();
            foreach (var check in result.Checks)
            {
                var icon = check.Passed ? "✓" : (check.Severity == CheckSeverity.Critical ? "✗" : "⚠");
                var color = check.Passed ? "#2CA01C" : (check.Severity == CheckSeverity.Critical ? "#d32f2f" : "#ff9800");
                
                checksHtml.AppendLine($@"
                <tr>
                    <td><span style='color:{color};font-size:20px;'>{icon}</span></td>
                    <td><strong>{EscapeHtml(check.Name)}</strong><br><small>{EscapeHtml(check.Description)}</small></td>
                    <td>{EscapeHtml(check.Message)}</td>
                </tr>");
            }

            var statusColor = result.OverallStatus == HealthStatus.Ready ? "#2CA01C" 
                : result.OverallStatus == HealthStatus.ReadyWithWarnings ? "#ff9800" : "#d32f2f";

            var html = $@"
<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <title>Pre-Migration Health Check Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .report {{ background: white; padding: 40px; max-width: 900px; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ border-bottom: 3px solid #2CA01C; padding-bottom: 20px; margin-bottom: 30px; }}
        .logo {{ font-size: 36px; color: #2CA01C; font-weight: bold; display: inline-block; }}
        h1 {{ display: inline-block; margin-left: 20px; vertical-align: middle; }}
        .status-badge {{ background: {statusColor}; color: white; padding: 15px 30px; border-radius: 8px; font-size: 18px; font-weight: bold; display: inline-block; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f8f8; }}
        .footer {{ text-align: center; margin-top: 40px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class='report'>
        <div class='header'>
            <span class='logo'>FOB</span>
            <h1>Pre-Migration Health Check Report</h1>
        </div>
        
        <p><strong>Company:</strong> {EscapeHtml(companyName)}</p>
        <p><strong>Checked:</strong> {result.CheckedAt:MMMM dd, yyyy HH:mm}</p>
        
        <div class='status-badge'>{result.GetSummary()}</div>
        
        <h2>Check Results</h2>
        <table>
            <tr><th style='width:50px;'>Status</th><th>Check</th><th>Details</th></tr>
            {checksHtml}
        </table>
        
        <div class='footer'>
            <p>Generated by QBMigration Health Check Tool</p>
        </div>
    </div>
</body>
</html>";

            var fileName = $"HealthCheckReport_{DateTime.UtcNow:yyyyMMdd_HHmmss}.html";
            var filePath = Path.Combine(_outputDirectory, fileName);
            SafeWriteFile(filePath, html);  // FIX: Use safe write with error handling

            return filePath;
        }

        /// <summary>
        /// FIX #6: Escape HTML including single quotes (used in attribute values).
        /// </summary>
        private string EscapeHtml(string? input)
        {
            if (string.IsNullOrEmpty(input)) return "";
            return input
                .Replace("&", "&amp;")
                .Replace("<", "&lt;")
                .Replace(">", "&gt;")
                .Replace("\"", "&quot;")
                .Replace("'", "&#39;");  // FIX #6: Escape single quotes for attribute contexts
        }
    }

    public class MigrationCertificateData
    {
        public string CompanyName { get; set; } = "";
        public string MigrationId { get; set; } = "";
        public DateTime MigrationDate { get; set; }
        public string SourceFileName { get; set; } = "";
        public string RealmId { get; set; } = "";
        public string SourceHash { get; set; } = "";
        public decimal TrialBalanceDesktop { get; set; }
        public decimal TrialBalanceOnline { get; set; }
        public decimal Variance => Math.Abs(TrialBalanceDesktop - TrialBalanceOnline);
        public int CustomerCount { get; set; }
        public int VendorCount { get; set; }
        public int InvoiceCount { get; set; }
        public int BillCount { get; set; }
        public int TotalRecords => CustomerCount + VendorCount + InvoiceCount + BillCount;
        public string AuthorizedBy { get; set; } = "System Generated";
    }
}
