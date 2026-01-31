using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace QBMigrationLauncher.Services
{
    /// <summary>
    /// Pre-Migration Health Check - Validates QB data before migration.
    /// Reads extracted NDJSON files to perform real data quality checks.
    /// </summary>
    public class HealthCheckService
    {
        public HealthCheckResult RunHealthCheck(string extractedDataPath)
        {
            var result = new HealthCheckResult
            {
                CheckedAt = DateTime.UtcNow,
                OverallStatus = HealthStatus.Ready
            };

            // Look for extracted data in the output directory
            var extractedDir = Path.Combine(extractedDataPath, "extracted");
            bool hasData = Directory.Exists(extractedDir) &&
                           Directory.GetFiles(extractedDir, "*.ndjson").Length > 0;

            // Check 1: Trial Balance
            result.Checks.Add(CheckTrialBalance(extractedDir, hasData));

            // Check 2: Orphaned Transactions
            result.Checks.Add(CheckOrphanedTransactions(extractedDir, hasData));

            // Check 3: Duplicate Names
            result.Checks.Add(CheckDuplicateNames(extractedDir, hasData));

            // Check 4: Invalid Characters
            result.Checks.Add(CheckInvalidCharacters(extractedDir, hasData));

            // Check 5: File Size Estimation
            result.Checks.Add(EstimateMigrationTime(extractedDir, hasData));

            // Determine overall status
            if (result.Checks.Any(c => c.Severity == CheckSeverity.Critical && !c.Passed))
                result.OverallStatus = HealthStatus.NotReady;
            else if (result.Checks.Any(c => c.Severity == CheckSeverity.Warning && !c.Passed))
                result.OverallStatus = HealthStatus.ReadyWithWarnings;

            return result;
        }

        private HealthCheck CheckTrialBalance(string extractedDir, bool hasData)
        {
            if (!hasData)
            {
                return new HealthCheck
                {
                    Name = "Trial Balance",
                    Description = "Verifies Debits = Credits",
                    Severity = CheckSeverity.Critical,
                    Passed = true,
                    Message = "No extracted data found. Trial balance will be verified after extraction."
                };
            }

            try
            {
                var accountsFile = Path.Combine(extractedDir, "accounts.ndjson");
                if (!File.Exists(accountsFile))
                {
                    return new HealthCheck
                    {
                        Name = "Trial Balance",
                        Description = "Verifies Debits = Credits",
                        Severity = CheckSeverity.Critical,
                        Passed = true,
                        Message = "Accounts file not found. Trial balance check skipped."
                    };
                }

                decimal totalDebits = 0m;
                decimal totalCredits = 0m;

                foreach (var line in File.ReadLines(accountsFile))
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    var obj = JObject.Parse(line);
                    var balance = obj.Value<decimal?>("Balance") ?? 0m;
                    var accountType = obj.Value<string>("AccountType") ?? "";

                    // FIX #42: Properly calculate trial balance without destroying sign information
                    // Debit-normal accounts: Assets, Expenses, CostOfGoodsSold
                    // Credit-normal accounts: Liabilities, Equity, Income/Revenue
                    bool isDebitNormal = accountType.Contains("Asset") ||
                                         accountType.Contains("Expense") ||
                                         accountType.Contains("CostOfGoodsSold") ||
                                         accountType.Contains("OtherExpense");

                    if (isDebitNormal)
                    {
                        // Positive balance = debit, negative balance = credit (contra)
                        if (balance >= 0)
                            totalDebits += balance;
                        else
                            totalCredits += Math.Abs(balance);
                    }
                    else
                    {
                        // Credit-normal account: positive balance = credit, negative balance = debit (contra)
                        if (balance >= 0)
                            totalCredits += balance;
                        else
                            totalDebits += Math.Abs(balance);
                    }
                }

                var difference = Math.Abs(totalDebits - totalCredits);
                bool isBalanced = difference < 0.01m;

                return new HealthCheck
                {
                    Name = "Trial Balance",
                    Description = "Verifies Debits = Credits",
                    Severity = CheckSeverity.Critical,
                    Passed = isBalanced,
                    Message = isBalanced
                        ? $"Trial balance is balanced. Debits: {totalDebits:C2}, Credits: {totalCredits:C2}"
                        : $"IMBALANCE DETECTED: Debits ({totalDebits:C2}) != Credits ({totalCredits:C2}), Difference: {difference:C2}"
                };
            }
            catch (Exception ex)
            {
                return new HealthCheck
                {
                    Name = "Trial Balance",
                    Description = "Verifies Debits = Credits",
                    Severity = CheckSeverity.Critical,
                    Passed = false,
                    Message = $"Error reading accounts data: {ex.Message}"
                };
            }
        }

        private HealthCheck CheckOrphanedTransactions(string extractedDir, bool hasData)
        {
            if (!hasData)
            {
                return new HealthCheck
                {
                    Name = "Orphaned Transactions",
                    Description = "Invoices/Bills linked to deleted entities",
                    Severity = CheckSeverity.Warning,
                    Passed = true,
                    Message = "No extracted data found. Orphan check will run after extraction."
                };
            }

            try
            {
                // Build set of known entity IDs (customers, vendors)
                var knownIds = new HashSet<string>();
                foreach (var entityFile in new[] { "customers.ndjson", "vendors.ndjson" })
                {
                    var filePath = Path.Combine(extractedDir, entityFile);
                    if (!File.Exists(filePath)) continue;
                    foreach (var line in File.ReadLines(filePath))
                    {
                        if (string.IsNullOrWhiteSpace(line)) continue;
                        var obj = JObject.Parse(line);
                        var id = obj.Value<string>("ListID") ?? obj.Value<string>("Id") ?? "";
                        if (!string.IsNullOrEmpty(id)) knownIds.Add(id);
                    }
                }

                if (knownIds.Count == 0)
                {
                    return new HealthCheck
                    {
                        Name = "Orphaned Transactions",
                        Description = "Invoices/Bills linked to deleted entities",
                        Severity = CheckSeverity.Warning,
                        Passed = true,
                        Message = "No customer/vendor data to cross-reference."
                    };
                }

                // Check transactions for references to unknown entities
                int orphanCount = 0;
                foreach (var txnFile in new[] { "invoices.ndjson", "bills.ndjson" })
                {
                    var filePath = Path.Combine(extractedDir, txnFile);
                    if (!File.Exists(filePath)) continue;
                    foreach (var line in File.ReadLines(filePath))
                    {
                        if (string.IsNullOrWhiteSpace(line)) continue;
                        var obj = JObject.Parse(line);
                        var refId = obj.Value<string>("CustomerRef_ListID")
                                 ?? obj.Value<string>("VendorRef_ListID")
                                 ?? obj.Value<string>("EntityRef_ListID") ?? "";
                        if (!string.IsNullOrEmpty(refId) && !knownIds.Contains(refId))
                            orphanCount++;
                    }
                }

                return new HealthCheck
                {
                    Name = "Orphaned Transactions",
                    Description = "Invoices/Bills linked to deleted entities",
                    Severity = CheckSeverity.Warning,
                    Passed = orphanCount == 0,
                    Message = orphanCount == 0
                        ? "No orphaned transactions found."
                        : $"{orphanCount} transaction(s) reference deleted or missing entities."
                };
            }
            catch (Exception ex)
            {
                return new HealthCheck
                {
                    Name = "Orphaned Transactions",
                    Description = "Invoices/Bills linked to deleted entities",
                    Severity = CheckSeverity.Warning,
                    Passed = false,
                    Message = $"Error checking orphaned transactions: {ex.Message}"
                };
            }
        }

        private HealthCheck CheckDuplicateNames(string extractedDir, bool hasData)
        {
            if (!hasData)
            {
                return new HealthCheck
                {
                    Name = "Duplicate Names",
                    Description = "Similar customer/vendor names that may cause conflicts",
                    Severity = CheckSeverity.Warning,
                    Passed = true,
                    Message = "No extracted data found. Duplicate check will run after extraction."
                };
            }

            try
            {
                var names = new List<string>();
                foreach (var entityFile in new[] { "customers.ndjson", "vendors.ndjson" })
                {
                    var filePath = Path.Combine(extractedDir, entityFile);
                    if (!File.Exists(filePath)) continue;
                    foreach (var line in File.ReadLines(filePath))
                    {
                        if (string.IsNullOrWhiteSpace(line)) continue;
                        var obj = JObject.Parse(line);
                        var name = obj.Value<string>("Name") ?? obj.Value<string>("FullName") ?? "";
                        if (!string.IsNullOrEmpty(name)) names.Add(name);
                    }
                }

                // Check for exact duplicates (case-insensitive)
                var duplicates = names
                    .GroupBy(n => n.Trim().ToLowerInvariant())
                    .Where(g => g.Count() > 1)
                    .Select(g => g.Key)
                    .ToList();

                return new HealthCheck
                {
                    Name = "Duplicate Names",
                    Description = "Similar customer/vendor names that may cause conflicts",
                    Severity = CheckSeverity.Warning,
                    Passed = duplicates.Count == 0,
                    Message = duplicates.Count == 0
                        ? $"No duplicate names detected across {names.Count} entities."
                        : $"{duplicates.Count} duplicate name(s) found: {string.Join(", ", duplicates.Take(5))}{(duplicates.Count > 5 ? "..." : "")}"
                };
            }
            catch (Exception ex)
            {
                return new HealthCheck
                {
                    Name = "Duplicate Names",
                    Description = "Similar customer/vendor names that may cause conflicts",
                    Severity = CheckSeverity.Warning,
                    Passed = false,
                    Message = $"Error checking duplicate names: {ex.Message}"
                };
            }
        }

        private HealthCheck CheckInvalidCharacters(string extractedDir, bool hasData)
        {
            if (!hasData)
            {
                return new HealthCheck
                {
                    Name = "Invalid Characters",
                    Description = "Characters that QBO API will reject",
                    Severity = CheckSeverity.Warning,
                    Passed = true,
                    Message = "No extracted data found. Character check will run after extraction."
                };
            }

            try
            {
                // QBO rejects: colons in names, angle brackets, pipe chars, certain control chars
                var invalidPattern = new Regex(@"[<>|\\"":\x00-\x1F]", RegexOptions.Compiled);
                int invalidCount = 0;
                var affectedFields = new List<string>();

                foreach (var file in Directory.GetFiles(extractedDir, "*.ndjson"))
                {
                    var fileName = Path.GetFileNameWithoutExtension(file);
                    foreach (var line in File.ReadLines(file))
                    {
                        if (string.IsNullOrWhiteSpace(line)) continue;
                        var obj = JObject.Parse(line);
                        foreach (var prop in obj.Properties())
                        {
                            if (prop.Value.Type != JTokenType.String) continue;
                            var val = prop.Value.ToString();
                            if (invalidPattern.IsMatch(val))
                            {
                                invalidCount++;
                                if (affectedFields.Count < 5)
                                    affectedFields.Add($"{fileName}.{prop.Name}");
                            }
                        }
                    }
                }

                return new HealthCheck
                {
                    Name = "Invalid Characters",
                    Description = "Characters that QBO API will reject",
                    Severity = CheckSeverity.Warning,
                    Passed = invalidCount == 0,
                    Message = invalidCount == 0
                        ? "All text fields are QBO-compatible."
                        : $"{invalidCount} field(s) contain invalid characters: {string.Join(", ", affectedFields)}{(invalidCount > 5 ? "..." : "")}"
                };
            }
            catch (Exception ex)
            {
                return new HealthCheck
                {
                    Name = "Invalid Characters",
                    Description = "Characters that QBO API will reject",
                    Severity = CheckSeverity.Warning,
                    Passed = false,
                    Message = $"Error checking invalid characters: {ex.Message}"
                };
            }
        }

        private HealthCheck EstimateMigrationTime(string extractedDir, bool hasData)
        {
            if (!hasData)
            {
                return new HealthCheck
                {
                    Name = "Migration Time Estimate",
                    Description = "Estimated time based on data volume",
                    Severity = CheckSeverity.Info,
                    Passed = true,
                    Message = "No extracted data found. Estimate will be calculated after extraction."
                };
            }

            try
            {
                long totalBytes = 0;
                int totalRecords = 0;
                foreach (var file in Directory.GetFiles(extractedDir, "*.ndjson"))
                {
                    var info = new FileInfo(file);
                    totalBytes += info.Length;
                    totalRecords += File.ReadLines(file).Count(l => !string.IsNullOrWhiteSpace(l));
                }

                double totalMB = totalBytes / (1024.0 * 1024.0);

                // Estimate: ~500 records/minute for QBO API, plus upload time
                int estimatedMinutes = Math.Max(1, (int)Math.Ceiling(totalRecords / 500.0) + (int)Math.Ceiling(totalMB / 10.0));

                string timeEstimate;
                if (estimatedMinutes < 60)
                    timeEstimate = $"{estimatedMinutes} minutes";
                else
                    timeEstimate = $"{estimatedMinutes / 60}h {estimatedMinutes % 60}m";

                return new HealthCheck
                {
                    Name = "Migration Time Estimate",
                    Description = "Estimated time based on data volume",
                    Severity = CheckSeverity.Info,
                    Passed = true,
                    Message = $"Data: {totalRecords:N0} records ({totalMB:F1} MB). Estimated migration time: {timeEstimate}."
                };
            }
            catch (Exception ex)
            {
                return new HealthCheck
                {
                    Name = "Migration Time Estimate",
                    Description = "Estimated time based on data volume",
                    Severity = CheckSeverity.Info,
                    Passed = true,
                    Message = $"Could not estimate: {ex.Message}"
                };
            }
        }
    }

    public class HealthCheckResult
    {
        public DateTime CheckedAt { get; set; }
        public HealthStatus OverallStatus { get; set; }
        public List<HealthCheck> Checks { get; set; } = new List<HealthCheck>();
        
        public string GetSummary()
        {
            var critical = Checks.Count(c => c.Severity == CheckSeverity.Critical && !c.Passed);
            var warnings = Checks.Count(c => c.Severity == CheckSeverity.Warning && !c.Passed);
            
            if (critical > 0)
                return $"NOT READY: {critical} critical issue(s) found.";
            if (warnings > 0)
                return $"READY WITH WARNINGS: {warnings} warning(s) found.";
            return "READY: All checks passed!";
        }
    }

    public class HealthCheck
    {
        public string Name { get; set; } = "";
        public string Description { get; set; } = "";
        public CheckSeverity Severity { get; set; }
        public bool Passed { get; set; }
        public string Message { get; set; } = "";
    }

    public enum HealthStatus
    {
        Ready,
        ReadyWithWarnings,
        NotReady
    }

    public enum CheckSeverity
    {
        Info,
        Warning,
        Critical
    }
}
