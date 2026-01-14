using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;

namespace QBMigrationLauncher.Services
{
    /// <summary>
    /// Active Archival Service - Stores and retrieves historical QuickBooks data.
    /// Provides a "Data Museum" for companies that need to keep records but want
    /// to migrate to a fresh QBO with only recent data.
    /// </summary>
    public class ActiveArchivalService
    {
        private readonly string _archiveDirectory;
        private readonly string _indexPath;
        private ArchiveIndex _index;

        public event EventHandler<string>? LogMessage;

        public ActiveArchivalService(string archiveDirectory)
        {
            _archiveDirectory = archiveDirectory;
            _indexPath = Path.Combine(_archiveDirectory, "archive_index.json");
            
            Directory.CreateDirectory(_archiveDirectory);
            _index = LoadOrCreateIndex();
        }

        /// <summary>
        /// Archive a company's extracted data.
        /// </summary>
        public async Task<ArchiveEntry> ArchiveCompanyDataAsync(string companyName, string extractedDataPath)
        {
            var archiveId = $"ARC-{DateTime.Now:yyyyMMdd}-{Guid.NewGuid().ToString("N").Substring(0, 6).ToUpper()}";
            var archiveFolder = Path.Combine(_archiveDirectory, archiveId);
            Directory.CreateDirectory(archiveFolder);

            LogMessage?.Invoke(this, $"[ARCHIVE] Creating archive: {archiveId}");

            var entry = new ArchiveEntry
            {
                ArchiveId = archiveId,
                CompanyName = companyName,
                SourcePath = extractedDataPath,
                ArchivePath = archiveFolder,
                CreatedAt = DateTime.Now,
                Status = ArchiveStatus.Active
            };

            // Copy extracted data to archive
            if (Directory.Exists(extractedDataPath))
            {
                foreach (var file in Directory.GetFiles(extractedDataPath))
                {
                    var destFile = Path.Combine(archiveFolder, Path.GetFileName(file));
                    File.Copy(file, destFile, true);
                }
            }

            // Create metadata file
            var metadataPath = Path.Combine(archiveFolder, "metadata.json");
            await File.WriteAllTextAsync(metadataPath, JsonSerializer.Serialize(entry, new JsonSerializerOptions { WriteIndented = true }));

            // Parse and index transactions
            entry.TransactionCount = await IndexTransactionsAsync(archiveFolder, entry);

            // Update main index
            _index.Entries.Add(entry);
            await SaveIndexAsync();

            LogMessage?.Invoke(this, $"[ARCHIVE] Completed: {archiveId} ({entry.TransactionCount} transactions)");
            return entry;
        }

        /// <summary>
        /// Search archived transactions.
        /// </summary>
        public async Task<List<ArchivedTransaction>> SearchTransactionsAsync(TransactionSearchCriteria criteria)
        {
            var results = new List<ArchivedTransaction>();

            foreach (var entry in _index.Entries.Where(e => e.Status == ArchiveStatus.Active))
            {
                if (!string.IsNullOrEmpty(criteria.CompanyName) && 
                    !entry.CompanyName.Contains(criteria.CompanyName, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                var txnIndexPath = Path.Combine(entry.ArchivePath, "transactions_index.json");
                if (!File.Exists(txnIndexPath)) continue;

                var json = await File.ReadAllTextAsync(txnIndexPath);
                var transactions = JsonSerializer.Deserialize<List<ArchivedTransaction>>(json) ?? new List<ArchivedTransaction>();

                // Apply filters
                var filtered = transactions.AsEnumerable();

                if (criteria.DateFrom.HasValue)
                    filtered = filtered.Where(t => t.Date >= criteria.DateFrom.Value);

                if (criteria.DateTo.HasValue)
                    filtered = filtered.Where(t => t.Date <= criteria.DateTo.Value);

                if (!string.IsNullOrEmpty(criteria.TransactionType))
                    filtered = filtered.Where(t => t.Type.Equals(criteria.TransactionType, StringComparison.OrdinalIgnoreCase));

                if (criteria.MinAmount.HasValue)
                    filtered = filtered.Where(t => t.Amount >= criteria.MinAmount.Value);

                if (criteria.MaxAmount.HasValue)
                    filtered = filtered.Where(t => t.Amount <= criteria.MaxAmount.Value);

                if (!string.IsNullOrEmpty(criteria.SearchText))
                    filtered = filtered.Where(t => 
                        t.Memo?.Contains(criteria.SearchText, StringComparison.OrdinalIgnoreCase) == true ||
                        t.EntityName?.Contains(criteria.SearchText, StringComparison.OrdinalIgnoreCase) == true);

                results.AddRange(filtered);
            }

            return results.OrderByDescending(t => t.Date).Take(criteria.MaxResults).ToList();
        }

        /// <summary>
        /// Get all archived companies.
        /// </summary>
        public List<ArchiveEntry> GetAllArchives()
        {
            return _index.Entries.Where(e => e.Status == ArchiveStatus.Active).ToList();
        }

        /// <summary>
        /// Get a specific archive.
        /// </summary>
        public ArchiveEntry? GetArchive(string archiveId)
        {
            return _index.Entries.FirstOrDefault(e => e.ArchiveId == archiveId);
        }

        /// <summary>
        /// Export a transaction to PDF format.
        /// </summary>
        public string ExportTransactionToPdf(ArchivedTransaction transaction, string outputDirectory)
        {
            var html = GenerateTransactionHtml(transaction);
            var fileName = $"Transaction_{transaction.Id}_{transaction.Type}_{transaction.Date:yyyyMMdd}.html";
            var filePath = Path.Combine(outputDirectory, fileName);
            File.WriteAllText(filePath, html);
            return filePath;
        }

        /// <summary>
        /// Mark an archive for deletion (soft delete).
        /// </summary>
        public async Task MarkForDeletionAsync(string archiveId)
        {
            var entry = _index.Entries.FirstOrDefault(e => e.ArchiveId == archiveId);
            if (entry != null)
            {
                entry.Status = ArchiveStatus.MarkedForDeletion;
                entry.DeleteScheduledAt = DateTime.Now.AddDays(30); // 30-day grace period
                await SaveIndexAsync();
                LogMessage?.Invoke(this, $"[DELETE] Archive {archiveId} marked for deletion on {entry.DeleteScheduledAt:yyyy-MM-dd}");
            }
        }

        /// <summary>
        /// Generate audit log entry.
        /// </summary>
        public async Task LogAccessAsync(string archiveId, string userId, string action)
        {
            var auditLogPath = Path.Combine(_archiveDirectory, "audit_log.ndjson");
            var logEntry = new AuditLogEntry
            {
                Timestamp = DateTime.Now,
                ArchiveId = archiveId,
                UserId = userId,
                Action = action,
                IpAddress = "LOCAL" // Would be real IP in web version
            };

            var json = JsonSerializer.Serialize(logEntry);
            await File.AppendAllTextAsync(auditLogPath, json + Environment.NewLine);
        }

        private async Task<int> IndexTransactionsAsync(string archiveFolder, ArchiveEntry entry)
        {
            var transactions = new List<ArchivedTransaction>();
            var txnCount = 0;

            // Look for NDJSON files
            foreach (var file in Directory.GetFiles(archiveFolder, "*.ndjson"))
            {
                var fileName = Path.GetFileNameWithoutExtension(file).ToLower();
                var txnType = fileName switch
                {
                    "invoices" => "Invoice",
                    "bills" => "Bill",
                    "checks" => "Check",
                    "payments" => "Payment",
                    "journalentries" => "JournalEntry",
                    _ => "Other"
                };

                var lines = await File.ReadAllLinesAsync(file);
                foreach (var line in lines.Where(l => !string.IsNullOrWhiteSpace(l)))
                {
                    try
                    {
                        using var doc = JsonDocument.Parse(line);
                        var root = doc.RootElement;

                        var txn = new ArchivedTransaction
                        {
                            Id = txnCount++.ToString(),
                            ArchiveId = entry.ArchiveId,
                            Type = txnType,
                            RawJson = line
                        };

                        // Try to extract common fields
                        if (root.TryGetProperty("TxnNumber", out var txnNum))
                            txn.Number = txnNum.GetString();
                        
                        if (root.TryGetProperty("TxnDate", out var txnDate))
                            txn.Date = DateTime.TryParse(txnDate.GetString(), out var d) ? d : DateTime.MinValue;
                        
                        if (root.TryGetProperty("Amount", out var amount))
                            txn.Amount = amount.TryGetDecimal(out var a) ? a : 0;
                        
                        if (root.TryGetProperty("Memo", out var memo))
                            txn.Memo = memo.GetString();

                        transactions.Add(txn);
                    }
                    catch
                    {
                        // Skip malformed lines
                    }
                }
            }

            // Save transaction index
            var indexPath = Path.Combine(archiveFolder, "transactions_index.json");
            await File.WriteAllTextAsync(indexPath, JsonSerializer.Serialize(transactions, new JsonSerializerOptions { WriteIndented = true }));

            return transactions.Count;
        }

        private ArchiveIndex LoadOrCreateIndex()
        {
            if (File.Exists(_indexPath))
            {
                var json = File.ReadAllText(_indexPath);
                return JsonSerializer.Deserialize<ArchiveIndex>(json) ?? new ArchiveIndex();
            }
            return new ArchiveIndex();
        }

        private async Task SaveIndexAsync()
        {
            var json = JsonSerializer.Serialize(_index, new JsonSerializerOptions { WriteIndented = true });
            await File.WriteAllTextAsync(_indexPath, json);
        }

        private string GenerateTransactionHtml(ArchivedTransaction txn)
        {
            return $@"
<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <title>Archived Transaction</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; }}
        .header {{ border-bottom: 2px solid #2CA01C; padding-bottom: 20px; }}
        .field {{ margin: 15px 0; }}
        .label {{ font-weight: bold; color: #555; }}
        .value {{ font-size: 18px; margin-top: 5px; }}
        .raw {{ background: #f5f5f5; padding: 15px; border-radius: 8px; font-family: monospace; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class='header'>
        <h1>Archived Transaction</h1>
        <p>Archive ID: {txn.ArchiveId}</p>
    </div>
    <div class='field'><span class='label'>Type:</span><div class='value'>{txn.Type}</div></div>
    <div class='field'><span class='label'>Number:</span><div class='value'>{txn.Number ?? "N/A"}</div></div>
    <div class='field'><span class='label'>Date:</span><div class='value'>{txn.Date:MMMM dd, yyyy}</div></div>
    <div class='field'><span class='label'>Amount:</span><div class='value'>${txn.Amount:N2}</div></div>
    <div class='field'><span class='label'>Memo:</span><div class='value'>{txn.Memo ?? "N/A"}</div></div>
    <h3>Raw Data</h3>
    <div class='raw'><pre>{System.Web.HttpUtility.HtmlEncode(txn.RawJson)}</pre></div>
    <p style='color:#888; font-size:12px; margin-top:40px;'>Retrieved from archive on {DateTime.Now:yyyy-MM-dd HH:mm}</p>
</body>
</html>";
        }
    }

    #region Data Models

    public class ArchiveIndex
    {
        public List<ArchiveEntry> Entries { get; set; } = new List<ArchiveEntry>();
        public DateTime LastUpdated { get; set; } = DateTime.Now;
    }

    public class ArchiveEntry
    {
        public string ArchiveId { get; set; } = "";
        public string CompanyName { get; set; } = "";
        public string SourcePath { get; set; } = "";
        public string ArchivePath { get; set; } = "";
        public DateTime CreatedAt { get; set; }
        public ArchiveStatus Status { get; set; }
        public DateTime? DeleteScheduledAt { get; set; }
        public int TransactionCount { get; set; }
    }

    public enum ArchiveStatus
    {
        Active,
        MarkedForDeletion,
        Deleted
    }

    public class ArchivedTransaction
    {
        public string Id { get; set; } = "";
        public string ArchiveId { get; set; } = "";
        public string Type { get; set; } = "";
        public string? Number { get; set; }
        public DateTime Date { get; set; }
        public decimal Amount { get; set; }
        public string? Memo { get; set; }
        public string? EntityName { get; set; }
        public string RawJson { get; set; } = "";
    }

    public class TransactionSearchCriteria
    {
        public string? CompanyName { get; set; }
        public DateTime? DateFrom { get; set; }
        public DateTime? DateTo { get; set; }
        public string? TransactionType { get; set; }
        public decimal? MinAmount { get; set; }
        public decimal? MaxAmount { get; set; }
        public string? SearchText { get; set; }
        public int MaxResults { get; set; } = 100;
    }

    public class AuditLogEntry
    {
        public DateTime Timestamp { get; set; }
        public string ArchiveId { get; set; } = "";
        public string UserId { get; set; } = "";
        public string Action { get; set; } = "";
        public string IpAddress { get; set; } = "";
    }

    #endregion
}
