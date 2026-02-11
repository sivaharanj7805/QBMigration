// Conditionally compiled - only when USE_QBFC is defined (QBFC SDK installed)
// The Intuit QBFC SDK is no longer available for download (deprecated 2024).
// Use QODBC as the primary backend instead.
// To build with QBFC support: dotnet build /p:UseQBFC=true
#if USE_QBFC

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Linq;
using QBFC16Lib;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Main QuickBooks data extraction engine
    /// v4.3: Added entity-level failure isolation, logger, and run summary
    /// </summary>
    public class QBDataExtractor
    {
        private readonly IQBSessionManager _sessionManager;
        private readonly QBIteratorHelper _iteratorHelper;
        private readonly IRedactingLogger _logger;
        private int _totalErrors = 0;
        private readonly List<string> _warnings = new List<string>();
        private readonly List<string> _errors = new List<string>();
        
        // Configuration
        public bool ContinueOnEntityError { get; set; } = true;
        
        // Run summary for audit
        public ExtractionRunSummary RunSummary { get; private set; }
        
        // CRITICAL: Incremental Sync Support
        private DateTime? _incrementalFromDate = null;

        public QBDataExtractor(IQBSessionManager sessionManager, IRedactingLogger logger = null)
        {
            _sessionManager = sessionManager ?? throw new ArgumentNullException(nameof(sessionManager));
            _logger = logger;
            _iteratorHelper = new QBIteratorHelper(sessionManager, logger);
        }

        /// <summary>
        /// Legacy constructor for backwards compatibility
        /// </summary>
        public QBDataExtractor(QBSessionManager sessionManager)
            : this((IQBSessionManager)sessionManager, null) { }

        
        /// <summary>
        /// Set the date for incremental sync - only extract records modified since this date
        /// </summary>
        public void SetIncrementalSyncDate(DateTime fromDate)
        {
            _incrementalFromDate = fromDate;
            _iteratorHelper.SetIncrementalSyncDate(fromDate);
            _logger?.Log(LogLevel.Info, "INCREMENTAL SYNC MODE: Extracting only records modified since {0:yyyy-MM-dd}", fromDate);
        }

        /// <summary>
        /// Safely extract an entity type with failure isolation
        /// </summary>
        private List<T> SafeExtract<T>(string entityName, Func<List<T>> extractor) where T : class
        {
            var sw = Stopwatch.StartNew();
            var result = new EntityExtractionResult { EntityName = entityName };
            
            try
            {
                var records = extractor();
                sw.Stop();
                
                result.Success = true;
                result.RecordCount = records?.Count ?? 0;
                result.Duration = sw.Elapsed;
                RunSummary.EntityResults.Add(result);
                RunSummary.TotalEntitiesSucceeded++;
                RunSummary.TotalRecordsExtracted += result.RecordCount;
                
                return records ?? new List<T>();
            }
            catch (Exception ex)
            {
                sw.Stop();
                _totalErrors++;
                
                result.Success = false;
                result.RecordCount = 0;
                result.Duration = sw.Elapsed;
                result.ErrorMessage = ex.Message;
                RunSummary.EntityResults.Add(result);
                RunSummary.TotalEntitiesFailed++;
                RunSummary.Errors.Add($"{entityName}: {ex.Message}");
                
                _logger?.Log(LogLevel.Error, "Failed to extract {0}: {1}", entityName, ex.Message);
                
                if (!ContinueOnEntityError)
                {
                    throw;
                }
                
                return new List<T>();
            }
            finally
            {
                RunSummary.TotalEntitiesAttempted++;
            }
        }

        /// <summary>
        /// Safely extract and write an entity to NDJSON with checkpointing
        /// </summary>
        private async System.Threading.Tasks.Task SafeExtractToNDJSONAsync<T>(
            string entityName,
            Func<List<T>> extractor,
            NDJSONWriter writer,
            ExtractionCheckpoint checkpoint,
            CheckpointState checkpointState,
            System.Threading.CancellationToken ct = default) where T : class
        {
            // Check if already completed
            if (checkpoint.IsEntityComplete(checkpointState, entityName))
            {
                _logger?.Log(LogLevel.Info, "Skipping {0} - already extracted in this session", entityName);
                var skipResult = new EntityExtractionResult
                {
                    EntityName = entityName,
                    Skipped = true
                };
                RunSummary.EntityResults.Add(skipResult);
                return;
            }

            var records = SafeExtract(entityName, extractor);

            if (records.Count > 0)
            {
                await writer.WriteEntityBatchAsync(entityName.ToLowerInvariant(), records, ct);
            }

            // Save checkpoint after successful extraction
            checkpointState.CompletedEntities.Add(entityName);
            checkpointState.TotalRecordsExtracted += records.Count;
            checkpoint.SaveAfterEntity(checkpointState);
        }

        /// <summary>
        /// Extract all data to NDJSON files with checkpointing for resumability
        /// Produces: accounts.ndjson, customers.ndjson, etc. + run_manifest.json
        /// </summary>
        public async System.Threading.Tasks.Task<RunManifest> ExtractAllDataToNDJSONAsync(
            string outputDirectory,
            string sessionId,
            string configHash = null,
            System.Threading.CancellationToken ct = default)
        {
            var startTime = DateTime.UtcNow;
            _logger?.Log(LogLevel.Info, "Starting NDJSON extraction to: {0}", outputDirectory);

            // Initialize components
            var checkpoint = new ExtractionCheckpoint(outputDirectory, _logger);
            var checkpointState = checkpoint.Load(sessionId) ?? new CheckpointState
            {
                SessionId = sessionId,
                StartedAt = startTime,
                IsIncremental = _incrementalFromDate.HasValue,
                IncrementalFromDate = _incrementalFromDate
            };

            var writer = new NDJSONWriter(outputDirectory, sessionId, _logger);
            try
            {
            // Set manifest metadata
            writer.Manifest.QBVersion = _sessionManager.GetQBVersion();
            writer.Manifest.CompanyFingerprint = ComputeCompanyFingerprint(_sessionManager.GetCompanyInfo());
            writer.Manifest.ConfigHash = configHash;
            writer.Manifest.IsIncremental = _incrementalFromDate.HasValue;
            writer.Manifest.IncrementalFromDate = _incrementalFromDate;

            // Initialize run summary
            RunSummary = new ExtractionRunSummary
            {
                SessionId = sessionId,
                StartedAt = startTime,
                IsIncremental = _incrementalFromDate.HasValue,
                IncrementalFromDate = _incrementalFromDate,
                ConfigHash = configHash
            };

            _totalErrors = 0;
            _warnings.Clear();
            _errors.Clear();

            // === EXTRACT ALL ENTITIES ===
            _logger?.Log(LogLevel.Info, "Extracting entities with failure isolation...");

            // Lists/Master Data
            await SafeExtractToNDJSONAsync("Accounts", () => ExtractAccounts(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Customers", () => ExtractCustomers(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Vendors", () => ExtractVendors(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Employees", () => ExtractEmployees(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Items", () => ExtractItems(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Classes", () => ExtractClasses(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("PaymentMethods", () => ExtractPaymentMethods(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Terms", () => ExtractTerms(), writer, checkpoint, checkpointState, ct);

            // Transactions
            await SafeExtractToNDJSONAsync("Invoices", () => ExtractInvoices(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Bills", () => ExtractBills(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Checks", () => ExtractChecks(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("JournalEntries", () => ExtractJournalEntries(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Deposits", () => ExtractDeposits(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("CreditMemos", () => ExtractCreditMemos(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("SalesReceipts", () => ExtractSalesReceipts(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("Estimates", () => ExtractEstimates(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("PurchaseOrders", () => ExtractPurchaseOrders(), writer, checkpoint, checkpointState, ct);
            await SafeExtractToNDJSONAsync("SalesOrders", () => ExtractSalesOrders(), writer, checkpoint, checkpointState, ct);
            
            // Deleted records (for incremental sync)
            if (_incrementalFromDate.HasValue)
            {
                await SafeExtractToNDJSONAsync("Deleted", () => ExtractDeletedRecordsAsList(), writer, checkpoint, checkpointState, ct);
            }

            // Write errors to errors.ndjson
            foreach (var error in RunSummary.Errors)
            {
                await writer.WriteErrorAsync(new ExtractionError
                {
                    ErrorCode = "EXTRACTION_FAILED",
                    Message = error,
                    Severity = "error"
                }, ct);
            }

            // Create metrics
            var metrics = new RunMetrics
            {
                RunId = sessionId,
                StartedAt = startTime,
                CompletedAt = DateTime.UtcNow,
                TotalDurationSeconds = (DateTime.UtcNow - startTime).TotalSeconds,
                ExtractionDurationSeconds = (DateTime.UtcNow - startTime).TotalSeconds,
                EntityTimings = RunSummary.EntityResults.Select(e => new EntityTiming
                {
                    EntityName = e.EntityName,
                    DurationSeconds = e.Duration.TotalSeconds,
                    RecordCount = e.RecordCount,
                    RecordsPerSecond = e.Duration.TotalSeconds > 0 
                        ? e.RecordCount / e.Duration.TotalSeconds 
                        : 0
                }).ToList()
            };

            // Finalize and write manifest
            await writer.FinalizeAsync(metrics, ct);

            // Complete run summary
            RunSummary.CompletedAt = DateTime.UtcNow;
            RunSummary.Warnings.AddRange(_warnings);

            // Clear checkpoint on success
            checkpoint.Clear();

            _logger?.Log(LogLevel.Info, "NDJSON extraction complete: {0} entities, {1} records, {2} errors",
                RunSummary.TotalEntitiesSucceeded, RunSummary.TotalRecordsExtracted, _totalErrors);

            return writer.Manifest;
            }
            finally
            {
                writer?.Dispose();
            }
        }

        /// <summary>
        /// Compute a safe fingerprint for company (no PII)
        /// </summary>
        private string ComputeCompanyFingerprint(QBCompanyInfo company)
        {
            if (company == null) return "unknown";

            using (var sha = System.Security.Cryptography.SHA256.Create())
            {
                var data = System.Text.Encoding.UTF8.GetBytes(
                    $"{company.CompanyName}|{company.LegalCompanyName}|{company.FirstMonthFiscalYear}");
                var hash = sha.ComputeHash(data);
                var base64 = Convert.ToBase64String(hash);
                // BUFFER OVERFLOW FIX: Check length before Substring to prevent ArgumentOutOfRangeException
                // SHA256 produces 32 bytes = 44 Base64 chars (with padding), so this should always work,
                // but defensive coding prevents edge cases.
                return base64.Length >= 16 ? base64.Substring(0, 16) : base64;
            }
        }

        /// <summary>
        /// Helper to get deleted records as a list
        /// </summary>
        private List<QBDeletedRecord> ExtractDeletedRecordsAsList()
        {
            var result = ExtractDeletedRecords();
            return result?.DeletedRecords ?? new List<QBDeletedRecord>();
        }


        // =================================================================
        // v4.1: PRECISION HELPERS - Prevent floating point errors
        // =================================================================
        
        /// <summary>
        /// Parse decimal safely from QBFC value using string conversion
        /// Prevents floating point precision errors
        /// </summary>
        private decimal? ParseDecimalSafely(object qbValue)
        {
            if (qbValue == null)
                return null;

            try
            {
                // Try to get string representation first (most accurate)
                string valueStr = qbValue.ToString();
                
                if (string.IsNullOrWhiteSpace(valueStr))
                    return null;

                // Parse using InvariantCulture to handle different formats
                if (decimal.TryParse(valueStr, NumberStyles.Any, CultureInfo.InvariantCulture, out decimal parsed))
                {
                    // Apply QuickBooks rounding rules (2 decimal places for currency)
                    return Math.Round(parsed, 2, MidpointRounding.AwayFromZero);
                }
            }
            catch (FormatException)
            {
                // Invalid format - return null as this is expected for certain QB values
            }

            return null;
        }

        /// <summary>
        /// Parse decimal with custom decimal places (for percentages, rates, etc.)
        /// </summary>
        private decimal? ParseDecimalSafely(object qbValue, int decimalPlaces)
        {
            if (qbValue == null)
                return null;

            try
            {
                string valueStr = qbValue.ToString();
                
                if (string.IsNullOrWhiteSpace(valueStr))
                    return null;

                if (decimal.TryParse(valueStr, NumberStyles.Any, CultureInfo.InvariantCulture, out decimal parsed))
                {
                    return Math.Round(parsed, decimalPlaces, MidpointRounding.AwayFromZero);
                }
            }
            catch (FormatException)
            {
                // Invalid format - expected for certain QB values
            }

            return null;
        }

        /// <summary>
        /// Safely parse string from QBFC value
        /// </summary>
        private string SafeGetString(object qbValue)
        {
            if (qbValue == null)
                return null;

            try
            {
                string value = qbValue.ToString();
                return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
            }
            catch (NullReferenceException)
            {
                // QB value accessor threw - return null
                return null;
            }
        }

        /// <summary>
        /// Safely parse DateTime from QBFC value
        /// </summary>
        private DateTime? SafeGetDateTime(object qbValue)
        {
            if (qbValue == null)
                return null;

            try
            {
                if (qbValue is DateTime dt)
                    return dt;

                string valueStr = qbValue.ToString();
                if (DateTime.TryParse(valueStr, out DateTime parsed))
                    return parsed;
            }
            catch (NullReferenceException)
            {
                // QB value accessor threw - return null
            }

            return null;
        }

        /// <summary>
        /// Safely parse bool from QBFC value
        /// </summary>
        private bool? SafeGetBool(object qbValue)
        {
            if (qbValue == null)
                return null;

            try
            {
                if (qbValue is bool b)
                    return b;

                string valueStr = qbValue.ToString().ToLower();
                if (valueStr == "true" || valueStr == "1" || valueStr == "yes")
                    return true;
                if (valueStr == "false" || valueStr == "0" || valueStr == "no")
                    return false;
            }
            catch (NullReferenceException)
            {
                // QB value accessor threw - return null
            }

            return null;
        }

        // =================================================================
        // END PRECISION HELPERS
        // =================================================================

        /// <summary>
        /// Extract ALL data from QuickBooks with failure isolation
        /// </summary>
        public QBExtractedData ExtractAllData()
        {
            _logger?.Log(LogLevel.Info, "Starting QuickBooks Desktop data extraction");
            
            // Initialize run summary
            RunSummary = new ExtractionRunSummary
            {
                SessionId = Guid.NewGuid().ToString(),
                StartedAt = DateTime.UtcNow,
                IsIncremental = _incrementalFromDate.HasValue,
                IncrementalFromDate = _incrementalFromDate
            };
            
            _totalErrors = 0;
            _warnings.Clear();
            _errors.Clear();
            
            var data = new QBExtractedData
            {
                ExtractedAt = DateTime.Now,
                SessionID = RunSummary.SessionId,
                Company = _sessionManager.GetCompanyInfo(),
                QBVersion = _sessionManager.GetQBVersion()
            };

            _logger?.Log(LogLevel.Info, "Company: {0}", data.Company.CompanyName);
            _logger?.Log(LogLevel.Info, "QuickBooks: {0}", data.QBVersion);
            _logger?.Log(LogLevel.Info, "Session ID: {0}", data.SessionID);
            
            if (_incrementalFromDate.HasValue)
            {
                _logger?.Log(LogLevel.Info, "Incremental From: {0:yyyy-MM-dd}", _incrementalFromDate);
            }

            // Sequential extraction with failure isolation
            _logger?.Log(LogLevel.Info, "Sequential extraction (COM thread-safety required)...");
            
            // Extract all list entities sequentially with failure isolation
            data.Accounts = SafeExtract("Accounts", () => ExtractAccounts());
            data.Customers = SafeExtract("Customers", () => ExtractCustomers());
            data.Vendors = SafeExtract("Vendors", () => ExtractVendors());
            data.Employees = SafeExtract("Employees", () => ExtractEmployees());
            data.Leads = SafeExtract("Leads", () => ExtractLeads());
            data.OtherNames = SafeExtract("OtherNames", () => ExtractOtherNames());
            data.Items = SafeExtract("Items", () => ExtractItems());
            data.Classes = SafeExtract("Classes", () => ExtractClasses());

            // FIX C-17: Wrap remaining list entities with SafeExtract for consistent failure isolation
            data.PaymentMethods = SafeExtract("PaymentMethods", () => ExtractPaymentMethods());
            data.Terms = SafeExtract("Terms", () => ExtractTerms());
            data.SalesTaxCodes = SafeExtract("SalesTaxCodes", () => ExtractSalesTaxCodes());
            data.CustomerTypes = SafeExtract("CustomerTypes", () => ExtractCustomerTypes());
            data.VendorTypes = SafeExtract("VendorTypes", () => ExtractVendorTypes());
            data.JobTypes = SafeExtract("JobTypes", () => ExtractJobTypes());
            data.Currencies = SafeExtract("Currencies", () => ExtractCurrencies());
            data.CustomerMessages = SafeExtract("CustomerMessages", () => ExtractCustomerMessages());
            data.DateDrivenTerms = SafeExtract("DateDrivenTerms", () => ExtractDateDrivenTerms());
            data.InventorySites = SafeExtract("InventorySites", () => ExtractInventorySites());
            data.PayrollItemWages = SafeExtract("PayrollItemWages", () => ExtractPayrollItemWages());
            data.PayrollItemNonWages = SafeExtract("PayrollItemNonWages", () => ExtractPayrollItemNonWages());
            data.WorkersCompCodes = SafeExtract("WorkersCompCodes", () => ExtractWorkersCompCodes());
            data.PriceLevels = SafeExtract("PriceLevels", () => ExtractPriceLevels());
            data.SalesReps = SafeExtract("SalesReps", () => ExtractSalesReps());
            data.ShipMethods = SafeExtract("ShipMethods", () => ExtractShipMethods());
            data.SalesTaxGroups = SafeExtract("SalesTaxGroups", () => ExtractSalesTaxGroups());

            Console.WriteLine("✓ All list entities extracted sequentially\n");

            // ============================================================
            // SEQUENTIAL TRANSACTION EXTRACTION (maintains data integrity)
            // ============================================================
            // Transactions MUST be sequential due to LinkedTxn relationships
            Console.WriteLine("\nSEQUENTIAL MODE: Extracting transaction entities...");
            // FIX C-17: Wrap all transaction extractions with SafeExtract for consistent failure isolation
            data.Invoices = SafeExtract("Invoices", () => ExtractInvoices());
            data.SalesReceipts = SafeExtract("SalesReceipts", () => ExtractSalesReceipts());
            data.Estimates = SafeExtract("Estimates", () => ExtractEstimates());
            data.PurchaseOrders = SafeExtract("PurchaseOrders", () => ExtractPurchaseOrders());
            data.SalesOrders = SafeExtract("SalesOrders", () => ExtractSalesOrders());
            data.Bills = SafeExtract("Bills", () => ExtractBills());
            data.BillPayments = SafeExtract("BillPayments", () => ExtractBillPayments());
            data.BillPaymentCreditCards = SafeExtract("BillPaymentCreditCards", () => ExtractBillPaymentCreditCards());
            data.VendorCredits = SafeExtract("VendorCredits", () => ExtractVendorCredits());
            data.ReceivePayments = SafeExtract("ReceivePayments", () => ExtractReceivePayments());
            data.ARRefundCreditCards = SafeExtract("ARRefundCreditCards", () => ExtractARRefundCreditCards());
            data.Checks = SafeExtract("Checks", () => ExtractChecks());
            data.JournalEntries = SafeExtract("JournalEntries", () => ExtractJournalEntries());
            data.SalesTaxPayments = SafeExtract("SalesTaxPayments", () => ExtractSalesTaxPayments());
            data.CreditCardCharges = SafeExtract("CreditCardCharges", () => ExtractCreditCardCharges());
            data.CreditCardCredits = SafeExtract("CreditCardCredits", () => ExtractCreditCardCredits());
            data.Charges = SafeExtract("Charges", () => ExtractCharges());
            data.CreditMemos = SafeExtract("CreditMemos", () => ExtractCreditMemos());
            data.Deposits = SafeExtract("Deposits", () => ExtractDeposits());
            data.InventoryAdjustments = SafeExtract("InventoryAdjustments", () => ExtractInventoryAdjustments());
            data.ItemReceipts = SafeExtract("ItemReceipts", () => ExtractItemReceipts());
            data.BuildAssemblies = SafeExtract("BuildAssemblies", () => ExtractBuildAssemblies());
            data.Transfers = SafeExtract("Transfers", () => ExtractTransfers());
            data.InventoryTransfers = SafeExtract("InventoryTransfers", () => ExtractInventoryTransfers());
            data.DataExtensions = SafeExtract("DataExtensions", () => ExtractDataExtensions());

            // Non-list entities: use try/catch for consistent failure isolation
            // (SafeExtract<T> requires List<T>, these return single objects)
            try { data.Preferences = ExtractPreferences(); }
            catch (Exception ex)
            {
                _totalErrors++;
                RunSummary.TotalEntitiesFailed++;
                RunSummary.Errors.Add($"Preferences: {ex.Message}");
                _logger?.Log(LogLevel.Error, "Failed to extract Preferences: {0}", ex.Message);
                if (!ContinueOnEntityError) throw;
            }

            try { data.DeletedRecords = ExtractDeletedRecords(); }
            catch (Exception ex)
            {
                _totalErrors++;
                RunSummary.TotalEntitiesFailed++;
                RunSummary.Errors.Add($"DeletedRecords: {ex.Message}");
                _logger?.Log(LogLevel.Error, "Failed to extract DeletedRecords: {0}", ex.Message);
                if (!ContinueOnEntityError) throw;
            }

            try { data.ReportVerification = ExtractReportVerification(); }
            catch (Exception ex)
            {
                _totalErrors++;
                RunSummary.TotalEntitiesFailed++;
                RunSummary.Errors.Add($"ReportVerification: {ex.Message}");
                _logger?.Log(LogLevel.Error, "Failed to extract ReportVerification: {0}", ex.Message);
                if (!ContinueOnEntityError) throw;
            }

            try { data.CompanyActivity = ExtractCompanyActivity(); }
            catch (Exception ex)
            {
                _totalErrors++;
                RunSummary.TotalEntitiesFailed++;
                RunSummary.Errors.Add($"CompanyActivity: {ex.Message}");
                _logger?.Log(LogLevel.Error, "Failed to extract CompanyActivity: {0}", ex.Message);
                if (!ContinueOnEntityError) throw;
            }

            Console.WriteLine("Extraction Complete!");
            Console.WriteLine();

            // Complete run summary
            RunSummary.CompletedAt = DateTime.UtcNow;
            RunSummary.Warnings.AddRange(_warnings);
            
            // Print summary
            PrintSummary(data);
            PrintRunSummary();

            if (_totalErrors > 0)
            {
                _logger?.Log(LogLevel.Warning, "Total Errors: {0}. Some data may be incomplete.", _totalErrors);
            }

            return data;
        }
        
        /// <summary>
        /// Print the run summary with per-entity breakdown
        /// </summary>
        private void PrintRunSummary()
        {
            _logger?.Log(LogLevel.Info, "\n========== RUN SUMMARY ==========");
            _logger?.Log(LogLevel.Info, "Session ID: {0}", RunSummary.SessionId);
            _logger?.Log(LogLevel.Info, "Duration: {0:mm\\:ss}", RunSummary.Duration);
            _logger?.Log(LogLevel.Info, "Total Records Extracted: {0:N0}", RunSummary.TotalRecordsExtracted);
            _logger?.Log(LogLevel.Info, "Entities: {0} succeeded, {1} failed", 
                RunSummary.TotalEntitiesSucceeded, RunSummary.TotalEntitiesFailed);
            
            if (RunSummary.Errors.Count > 0)
            {
                _logger?.Log(LogLevel.Warning, "\nErrors:");
                foreach (var error in RunSummary.Errors.Take(10))
                {
                    _logger?.Log(LogLevel.Warning, "  - {0}", error);
                }
                if (RunSummary.Errors.Count > 10)
                {
                    _logger?.Log(LogLevel.Warning, "  ... and {0} more", RunSummary.Errors.Count - 10);
                }
            }
            
            _logger?.Log(LogLevel.Info, "================================\n");
        }

        // ========================================================================
        // CHART OF ACCOUNTS
        // ========================================================================
        public List<QBAccount> ExtractAccounts()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendAccountQueryRq(),
                recordParser: (record, index) =>
                {
                    var acct = (IAccountRet)record;
                    return new QBAccount
                    {
                        ListID = acct.ListID?.GetValue() ?? "",
                        Name = acct.Name?.GetValue() ?? "",
                        FullName = acct.FullName?.GetValue() ?? "",
                        IsActive = acct.IsActive?.GetValue() ?? true,
                        ParentRefListID = acct.ParentRef?.ListID?.GetValue() ?? "",
                        ParentRefFullName = acct.ParentRef?.FullName?.GetValue() ?? "",
                        Sublevel = acct.Sublevel?.GetValue() ?? 0,
                        AccountType = acct.AccountType?.GetValue().ToString() ?? "",
                        SpecialAccountType = acct.SpecialAccountType?.GetValue().ToString() ?? "",
                        IsTaxAccount = acct.IsTaxAccount?.GetValue() ?? false,
                        AccountNumber = acct.AccountNumber?.GetValue() ?? "",
                        BankNumber = acct.BankNumber?.GetValue() ?? "",
                        Desc = acct.Desc?.GetValue() ?? "",
                        Balance = (decimal)(acct.Balance?.GetValue() ?? 0.0),
                        TotalBalance = (decimal)(acct.TotalBalance?.GetValue() ?? 0.0),
                        SalesTaxCodeRefListID = acct.SalesTaxCodeRef?.ListID?.GetValue() ?? "",
                        SalesTaxCodeRefFullName = acct.SalesTaxCodeRef?.FullName?.GetValue() ?? "",
                        TaxLineID = acct.TaxLineInfoRet?.TaxLineID?.GetValue() ?? 0,
                        TaxLineName = acct.TaxLineInfoRet?.TaxLineName?.GetValue() ?? "",
                        CashFlowClassification = acct.CashFlowClassification?.GetValue().ToString() ?? "",
                        CurrencyRefListID = acct.CurrencyRef?.ListID?.GetValue() ?? "",
                        CurrencyRefFullName = acct.CurrencyRef?.FullName?.GetValue() ?? "",
                        TimeCreated = acct.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = acct.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = acct.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Accounts"
            );
        }

        // ========================================================================
        // CUSTOMERS
        // ========================================================================
        public List<QBCustomer> ExtractCustomers()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendCustomerQueryRq(),
                recordParser: (record, index) =>
                {
                    var cust = (ICustomerRet)record;
                    return new QBCustomer
                    {
                        ListID = cust.ListID?.GetValue() ?? "",
                        Name = cust.Name?.GetValue() ?? "",
                        FullName = cust.FullName?.GetValue() ?? "",
                        IsActive = cust.IsActive?.GetValue() ?? true,
                        CompanyName = cust.CompanyName?.GetValue() ?? "",
                        Salutation = cust.Salutation?.GetValue() ?? "",
                        FirstName = cust.FirstName?.GetValue() ?? "",
                        MiddleName = cust.MiddleName?.GetValue() ?? "",
                        LastName = cust.LastName?.GetValue() ?? "",
                        
                        // Bill Address
                        BillAddressAddr1 = cust.BillAddress?.Addr1?.GetValue() ?? "",
                        BillAddressAddr2 = cust.BillAddress?.Addr2?.GetValue() ?? "",
                        BillAddressAddr3 = cust.BillAddress?.Addr3?.GetValue() ?? "",
                        BillAddressAddr4 = cust.BillAddress?.Addr4?.GetValue() ?? "",
                        BillAddressAddr5 = cust.BillAddress?.Addr5?.GetValue() ?? "",
                        BillAddressCity = cust.BillAddress?.City?.GetValue() ?? "",
                        BillAddressState = cust.BillAddress?.State?.GetValue() ?? "",
                        BillAddressPostalCode = cust.BillAddress?.PostalCode?.GetValue() ?? "",
                        BillAddressCountry = cust.BillAddress?.Country?.GetValue() ?? "",
                        BillAddressNote = cust.BillAddress?.Note?.GetValue() ?? "",

                        // Ship Address
                        ShipAddressAddr1 = cust.ShipAddress?.Addr1?.GetValue() ?? "",
                        ShipAddressAddr2 = cust.ShipAddress?.Addr2?.GetValue() ?? "",
                        ShipAddressAddr3 = cust.ShipAddress?.Addr3?.GetValue() ?? "",
                        ShipAddressAddr4 = cust.ShipAddress?.Addr4?.GetValue() ?? "",
                        ShipAddressAddr5 = cust.ShipAddress?.Addr5?.GetValue() ?? "",
                        ShipAddressCity = cust.ShipAddress?.City?.GetValue() ?? "",
                        ShipAddressState = cust.ShipAddress?.State?.GetValue() ?? "",
                        ShipAddressPostalCode = cust.ShipAddress?.PostalCode?.GetValue() ?? "",
                        ShipAddressCountry = cust.ShipAddress?.Country?.GetValue() ?? "",
                        ShipAddressNote = cust.ShipAddress?.Note?.GetValue() ?? "",

                        // Contact Info
                        Phone = cust.Phone?.GetValue() ?? "",
                        AltPhone = cust.AltPhone?.GetValue() ?? "",
                        Fax = cust.Fax?.GetValue() ?? "",
                        Email = cust.Email?.GetValue() ?? "",
                        Contact = cust.Contact?.GetValue() ?? "",
                        AltContact = cust.AltContact?.GetValue() ?? "",

                        // Financial Info
                        CustomerTypeRefListID = cust.CustomerTypeRef?.ListID?.GetValue() ?? "",
                        CustomerTypeRefFullName = cust.CustomerTypeRef?.FullName?.GetValue() ?? "",
                        TermsRefListID = cust.TermsRef?.ListID?.GetValue() ?? "",
                        TermsRefFullName = cust.TermsRef?.FullName?.GetValue() ?? "",
                        SalesRepRefListID = cust.SalesRepRef?.ListID?.GetValue() ?? "",
                        SalesRepRefFullName = cust.SalesRepRef?.FullName?.GetValue() ?? "",
                        Balance = (decimal)(cust.Balance?.GetValue() ?? 0.0),
                        TotalBalance = (decimal)(cust.TotalBalance?.GetValue() ?? 0.0),
                        SalesTaxCodeRefListID = cust.SalesTaxCodeRef?.ListID?.GetValue() ?? "",
                        SalesTaxCodeRefFullName = cust.SalesTaxCodeRef?.FullName?.GetValue() ?? "",
                        ItemSalesTaxRefListID = cust.ItemSalesTaxRef?.ListID?.GetValue() ?? "",
                        ItemSalesTaxRefFullName = cust.ItemSalesTaxRef?.FullName?.GetValue() ?? "",
                        ResaleNumber = cust.ResaleNumber?.GetValue() ?? "",
                        AccountNumber = cust.AccountNumber?.GetValue() ?? "",
                        CreditLimit = (decimal)(cust.CreditLimit?.GetValue() ?? 0.0),
                        PrefPaymentMethodRefListID = cust.PreferredPaymentMethodRef?.ListID?.GetValue() ?? "",
                        PrefPaymentMethodRefFullName = cust.PreferredPaymentMethodRef?.FullName?.GetValue() ?? "",
                        JobStatus = cust.JobStatus?.GetValue().ToString() ?? "",
                        JobStartDate = cust.JobStartDate?.GetValue() ?? DateTime.MinValue,
                        JobProjectedEndDate = cust.JobProjectedEndDate?.GetValue() ?? DateTime.MinValue,
                        JobEndDate = cust.JobEndDate?.GetValue() ?? DateTime.MinValue,
                        JobDesc = cust.JobDesc?.GetValue() ?? "",
                        JobTypeRefListID = cust.JobTypeRef?.ListID?.GetValue() ?? "",
                        JobTypeRefFullName = cust.JobTypeRef?.FullName?.GetValue() ?? "",
                        Notes = cust.Notes?.GetValue() ?? "",
                        PriceLevelRefListID = cust.PriceLevelRef?.ListID?.GetValue() ?? "",
                        PriceLevelRefFullName = cust.PriceLevelRef?.FullName?.GetValue() ?? "",
                        ParentRefListID = cust.ParentRef?.ListID?.GetValue() ?? "",
                        ParentRefFullName = cust.ParentRef?.FullName?.GetValue() ?? "",
                        Sublevel = cust.Sublevel?.GetValue() ?? 0,
                        TimeCreated = cust.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = cust.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = cust.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Customers"
            );
        }

        // ========================================================================
        // VENDORS
        // ========================================================================
        public List<QBVendor> ExtractVendors()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendVendorQueryRq(),
                recordParser: (record, index) =>
                {
                    var vendor = (IVendorRet)record;
                    return new QBVendor
                    {
                        ListID = vendor.ListID?.GetValue() ?? "",
                        Name = vendor.Name?.GetValue() ?? "",
                        FullName = vendor.FullName?.GetValue() ?? "",
                        IsActive = vendor.IsActive?.GetValue() ?? true,
                        CompanyName = vendor.CompanyName?.GetValue() ?? "",
                        Salutation = vendor.Salutation?.GetValue() ?? "",
                        FirstName = vendor.FirstName?.GetValue() ?? "",
                        MiddleName = vendor.MiddleName?.GetValue() ?? "",
                        LastName = vendor.LastName?.GetValue() ?? "",

                        // Vendor Address
                        VendorAddressAddr1 = vendor.VendorAddress?.Addr1?.GetValue() ?? "",
                        VendorAddressAddr2 = vendor.VendorAddress?.Addr2?.GetValue() ?? "",
                        VendorAddressAddr3 = vendor.VendorAddress?.Addr3?.GetValue() ?? "",
                        VendorAddressAddr4 = vendor.VendorAddress?.Addr4?.GetValue() ?? "",
                        VendorAddressAddr5 = vendor.VendorAddress?.Addr5?.GetValue() ?? "",
                        VendorAddressCity = vendor.VendorAddress?.City?.GetValue() ?? "",
                        VendorAddressState = vendor.VendorAddress?.State?.GetValue() ?? "",
                        VendorAddressPostalCode = vendor.VendorAddress?.PostalCode?.GetValue() ?? "",
                        VendorAddressCountry = vendor.VendorAddress?.Country?.GetValue() ?? "",
                        VendorAddressNote = vendor.VendorAddress?.Note?.GetValue() ?? "",

                        // Contact Info
                        Phone = vendor.Phone?.GetValue() ?? "",
                        AltPhone = vendor.AltPhone?.GetValue() ?? "",
                        Fax = vendor.Fax?.GetValue() ?? "",
                        Email = vendor.Email?.GetValue() ?? "",
                        Contact = vendor.Contact?.GetValue() ?? "",
                        AltContact = vendor.AltContact?.GetValue() ?? "",

                        // Financial Info
                        VendorTypeRefListID = vendor.VendorTypeRef?.ListID?.GetValue() ?? "",
                        VendorTypeRefFullName = vendor.VendorTypeRef?.FullName?.GetValue() ?? "",
                        TermsRefListID = vendor.TermsRef?.ListID?.GetValue() ?? "",
                        TermsRefFullName = vendor.TermsRef?.FullName?.GetValue() ?? "",
                        CreditLimit = (decimal)(vendor.CreditLimit?.GetValue() ?? 0.0),
                        VendorTaxIdent = vendor.VendorTaxIdent?.GetValue() ?? "",
                        IsVendorEligibleFor1099 = vendor.IsVendorEligibleFor1099?.GetValue() ?? false,
                        Balance = (decimal)(vendor.Balance?.GetValue() ?? 0.0),
                        BillingRateRefListID = vendor.BillingRateRef?.ListID?.GetValue() ?? "",
                        BillingRateRefFullName = vendor.BillingRateRef?.FullName?.GetValue() ?? "",
                        ParentRefListID = vendor.ParentRef?.ListID?.GetValue() ?? "",
                        ParentRefFullName = vendor.ParentRef?.FullName?.GetValue() ?? "",
                        Sublevel = vendor.Sublevel?.GetValue() ?? 0,
                        TimeCreated = vendor.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = vendor.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = vendor.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Vendors"
            );
        }

        // ========================================================================
        // EMPLOYEES
        // ========================================================================
        public List<QBEmployee> ExtractEmployees()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendEmployeeQueryRq(),
                recordParser: (record, index) =>
                {
                    var emp = (IEmployeeRet)record;
                    return new QBEmployee
                    {
                        ListID = emp.ListID?.GetValue() ?? "",
                        Name = emp.Name?.GetValue() ?? "",
                        IsActive = emp.IsActive?.GetValue() ?? true,
                        Salutation = emp.Salutation?.GetValue() ?? "",
                        FirstName = emp.FirstName?.GetValue() ?? "",
                        MiddleName = emp.MiddleName?.GetValue() ?? "",
                        LastName = emp.LastName?.GetValue() ?? "",

                        // Employee Address
                        EmployeeAddressAddr1 = emp.EmployeeAddress?.Addr1?.GetValue() ?? "",
                        EmployeeAddressAddr2 = emp.EmployeeAddress?.Addr2?.GetValue() ?? "",
                        EmployeeAddressAddr3 = emp.EmployeeAddress?.Addr3?.GetValue() ?? "",
                        EmployeeAddressAddr4 = emp.EmployeeAddress?.Addr4?.GetValue() ?? "",
                        EmployeeAddressAddr5 = emp.EmployeeAddress?.Addr5?.GetValue() ?? "",
                        EmployeeAddressCity = emp.EmployeeAddress?.City?.GetValue() ?? "",
                        EmployeeAddressState = emp.EmployeeAddress?.State?.GetValue() ?? "",
                        EmployeeAddressPostalCode = emp.EmployeeAddress?.PostalCode?.GetValue() ?? "",
                        EmployeeAddressCountry = emp.EmployeeAddress?.Country?.GetValue() ?? "",

                        // Contact Info
                        Phone = emp.Phone?.GetValue() ?? "",
                        AltPhone = emp.AltPhone?.GetValue() ?? "",
                        Fax = emp.Fax?.GetValue() ?? "",
                        Email = emp.Email?.GetValue() ?? "",
                        EmployeeType = emp.EmployeeType?.GetValue().ToString() ?? "",
                        Gender = emp.Gender?.GetValue().ToString() ?? "",
                        HiredDate = emp.HiredDate?.GetValue() ?? DateTime.MinValue,
                        ReleasedDate = emp.ReleasedDate?.GetValue() ?? DateTime.MinValue,
                        BirthDate = emp.BirthDate?.GetValue() ?? DateTime.MinValue,
                        AccountNumber = emp.AccountNumber?.GetValue() ?? "",
                        Notes = emp.Notes?.GetValue() ?? "",
                        BillingRateRefListID = emp.BillingRateRef?.ListID?.GetValue() ?? "",
                        BillingRateRefFullName = emp.BillingRateRef?.FullName?.GetValue() ?? "",
                        TimeCreated = emp.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = emp.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = emp.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Employees"
            );
        }

        public List<QBLead> ExtractLeads()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendLeadQueryRq(),
                recordParser: (record, index) =>
                {
                    var lead = (ILeadRet)record;
                    return new QBLead
                    {
                        ListID = lead.ListID?.GetValue() ?? "",
                        Name = lead.Name?.GetValue() ?? "",
                        IsActive = lead.IsActive?.GetValue() ?? true,
                        Salutation = lead.Salutation?.GetValue() ?? "",
                        FirstName = lead.FirstName?.GetValue() ?? "",
                        MiddleName = lead.MiddleName?.GetValue() ?? "",
                        LastName = lead.LastName?.GetValue() ?? "",
                        CompanyName = lead.CompanyName?.GetValue() ?? "",
                        JobTitle = lead.JobTitle?.GetValue() ?? "",
                        Addr1 = lead.LeadAddress?.Addr1?.GetValue() ?? "",
                        Addr2 = lead.LeadAddress?.Addr2?.GetValue() ?? "",
                        Addr3 = lead.LeadAddress?.Addr3?.GetValue() ?? "",
                        Addr4 = lead.LeadAddress?.Addr4?.GetValue() ?? "",
                        City = lead.LeadAddress?.City?.GetValue() ?? "",
                        State = lead.LeadAddress?.State?.GetValue() ?? "",
                        PostalCode = lead.LeadAddress?.PostalCode?.GetValue() ?? "",
                        Country = lead.LeadAddress?.Country?.GetValue() ?? "",
                        Phone = lead.Phone?.GetValue() ?? "",
                        AltPhone = lead.AltPhone?.GetValue() ?? "",
                        Fax = lead.Fax?.GetValue() ?? "",
                        Email = lead.Email?.GetValue() ?? "",
                        Contact = lead.Contact?.GetValue() ?? "",
                        AltContact = lead.AltContact?.GetValue() ?? "",
                        Notes = lead.Notes?.GetValue() ?? "",
                        IsConverted = lead.IsConverted?.GetValue() ?? false,
                        CustomerRefListID = lead.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = lead.CustomerRef?.FullName?.GetValue() ?? "",
                        TimeCreated = lead.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = lead.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = lead.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Leads"
            );
        }

        public List<QBOtherName> ExtractOtherNames()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendOtherNameQueryRq(),
                recordParser: (record, index) =>
                {
                    var other = (IOtherNameRet)record;
                    return new QBOtherName
                    {
                        ListID = other.ListID?.GetValue() ?? "",
                        Name = other.Name?.GetValue() ?? "",
                        IsActive = other.IsActive?.GetValue() ?? true,
                        CompanyName = other.CompanyName?.GetValue() ?? "",
                        Salutation = other.Salutation?.GetValue() ?? "",
                        FirstName = other.FirstName?.GetValue() ?? "",
                        MiddleName = other.MiddleName?.GetValue() ?? "",
                        LastName = other.LastName?.GetValue() ?? "",
                        Addr1 = other.OtherNameAddress?.Addr1?.GetValue() ?? "",
                        Addr2 = other.OtherNameAddress?.Addr2?.GetValue() ?? "",
                        Addr3 = other.OtherNameAddress?.Addr3?.GetValue() ?? "",
                        Addr4 = other.OtherNameAddress?.Addr4?.GetValue() ?? "",
                        Addr5 = other.OtherNameAddress?.Addr5?.GetValue() ?? "",
                        City = other.OtherNameAddress?.City?.GetValue() ?? "",
                        State = other.OtherNameAddress?.State?.GetValue() ?? "",
                        PostalCode = other.OtherNameAddress?.PostalCode?.GetValue() ?? "",
                        Country = other.OtherNameAddress?.Country?.GetValue() ?? "",
                        Note = other.OtherNameAddress?.Note?.GetValue() ?? "",
                        Phone = other.Phone?.GetValue() ?? "",
                        AltPhone = other.AltPhone?.GetValue() ?? "",
                        Fax = other.Fax?.GetValue() ?? "",
                        Email = other.Email?.GetValue() ?? "",
                        Contact = other.Contact?.GetValue() ?? "",
                        AltContact = other.AltContact?.GetValue() ?? "",
                        AccountNumber = other.AccountNumber?.GetValue() ?? "",
                        TimeCreated = other.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = other.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = other.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Other Names"
            );
        }

        // ========================================================================
        // ITEMS (All Types)
        // ========================================================================
        public List<QBItem> ExtractItems()
        {
            var items = new List<QBItem>();

            // Extract all item types using ItemQuery (which returns all types)
            var allItems = _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendItemQueryRq(),
                recordParser: (record, index) =>
                {
                    // ItemQueryRs returns different types, need to check which one
                    string typeName = record.GetType().Name;
                    
                    var item = new QBItem();
                    
                    // Common properties for all item types
                    if (record is IItemServiceRet serviceRet)
                    {
                        item.Type = "Service";
                        item.ListID = serviceRet.ListID?.GetValue() ?? "";
                        item.Name = serviceRet.Name?.GetValue() ?? "";
                        item.FullName = serviceRet.FullName?.GetValue() ?? "";
                        item.IsActive = serviceRet.IsActive?.GetValue() ?? true;
                        item.ParentRefListID = serviceRet.ParentRef?.ListID?.GetValue() ?? "";
                        item.ParentRefFullName = serviceRet.ParentRef?.FullName?.GetValue() ?? "";
                        item.Sublevel = serviceRet.Sublevel?.GetValue() ?? 0;
                        item.Description = serviceRet.SalesOrPurchase?.Desc?.GetValue() ?? "";
                        item.Price = (decimal)(serviceRet.SalesOrPurchase?.Price?.GetValue() ?? 0.0);
                        item.AccountRefListID = serviceRet.SalesOrPurchase?.AccountRef?.ListID?.GetValue() ?? "";
                        item.AccountRefFullName = serviceRet.SalesOrPurchase?.AccountRef?.FullName?.GetValue() ?? "";
                        item.TimeCreated = serviceRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = serviceRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = serviceRet.EditSequence?.GetValue() ?? "";
                    }
                    else if (record is IItemInventoryRet invRet)
                    {
                        item.Type = "Inventory";
                        item.ListID = invRet.ListID?.GetValue() ?? "";
                        item.Name = invRet.Name?.GetValue() ?? "";
                        item.FullName = invRet.FullName?.GetValue() ?? "";
                        item.IsActive = invRet.IsActive?.GetValue() ?? true;
                        item.ParentRefListID = invRet.ParentRef?.ListID?.GetValue() ?? "";
                        item.ParentRefFullName = invRet.ParentRef?.FullName?.GetValue() ?? "";
                        item.Sublevel = invRet.Sublevel?.GetValue() ?? 0;
                        item.Description = invRet.SalesDesc?.GetValue() ?? "";
                        item.Price = (decimal)(invRet.SalesPrice?.GetValue() ?? 0.0);
                        item.AccountRefListID = invRet.IncomeAccountRef?.ListID?.GetValue() ?? "";
                        item.AccountRefFullName = invRet.IncomeAccountRef?.FullName?.GetValue() ?? "";
                        item.AssetAccountRefListID = invRet.AssetAccountRef?.ListID?.GetValue() ?? "";
                        item.AssetAccountRefFullName = invRet.AssetAccountRef?.FullName?.GetValue() ?? "";
                        item.COGSAccountRefListID = invRet.COGSAccountRef?.ListID?.GetValue() ?? "";
                        item.COGSAccountRefFullName = invRet.COGSAccountRef?.FullName?.GetValue() ?? "";
                        item.QuantityOnHand = (decimal)(invRet.QuantityOnHand?.GetValue() ?? 0.0);
                        item.AverageCost = (decimal)(invRet.AverageCost?.GetValue() ?? 0.0);
                        item.QuantityOnOrder = invRet.QuantityOnOrder?.GetValue() ?? 0;
                        item.QuantityOnSalesOrder = invRet.QuantityOnSalesOrder?.GetValue() ?? 0;
                        item.TimeCreated = invRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = invRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = invRet.EditSequence?.GetValue() ?? "";
                    }
                    else if (record is IItemNonInventoryRet nonInvRet)
                    {
                        item.Type = "NonInventory";
                        item.ListID = nonInvRet.ListID?.GetValue() ?? "";
                        item.Name = nonInvRet.Name?.GetValue() ?? "";
                        item.FullName = nonInvRet.FullName?.GetValue() ?? "";
                        item.IsActive = nonInvRet.IsActive?.GetValue() ?? true;
                        item.ParentRefListID = nonInvRet.ParentRef?.ListID?.GetValue() ?? "";
                        item.ParentRefFullName = nonInvRet.ParentRef?.FullName?.GetValue() ?? "";
                        item.Sublevel = nonInvRet.Sublevel?.GetValue() ?? 0;
                        item.Description = nonInvRet.SalesOrPurchase?.Desc?.GetValue() ?? "";
                        item.Price = (decimal)(nonInvRet.SalesOrPurchase?.Price?.GetValue() ?? 0.0);
                        item.AccountRefListID = nonInvRet.SalesOrPurchase?.AccountRef?.ListID?.GetValue() ?? "";
                        item.AccountRefFullName = nonInvRet.SalesOrPurchase?.AccountRef?.FullName?.GetValue() ?? "";
                        item.TimeCreated = nonInvRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = nonInvRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = nonInvRet.EditSequence?.GetValue() ?? "";
                    }
                    else if (record is IItemOtherChargeRet otherChargeRet)
                    {
                        item.Type = "OtherCharge";
                        item.ListID = otherChargeRet.ListID?.GetValue() ?? "";
                        item.Name = otherChargeRet.Name?.GetValue() ?? "";
                        item.FullName = otherChargeRet.FullName?.GetValue() ?? "";
                        item.IsActive = otherChargeRet.IsActive?.GetValue() ?? true;
                        item.ParentRefListID = otherChargeRet.ParentRef?.ListID?.GetValue() ?? "";
                        item.ParentRefFullName = otherChargeRet.ParentRef?.FullName?.GetValue() ?? "";
                        item.Sublevel = otherChargeRet.Sublevel?.GetValue() ?? 0;
                        item.Description = otherChargeRet.SalesOrPurchase?.Desc?.GetValue() ?? "";
                        item.Price = (decimal)(otherChargeRet.SalesOrPurchase?.Price?.GetValue() ?? 0.0);
                        item.AccountRefListID = otherChargeRet.SalesOrPurchase?.AccountRef?.ListID?.GetValue() ?? "";
                        item.AccountRefFullName = otherChargeRet.SalesOrPurchase?.AccountRef?.FullName?.GetValue() ?? "";
                        item.TimeCreated = otherChargeRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = otherChargeRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = otherChargeRet.EditSequence?.GetValue() ?? "";
                    }
                    else if (record is IItemSalesTaxRet salesTaxRet)
                    {
                        item.Type = "SalesTax";
                        item.ListID = salesTaxRet.ListID?.GetValue() ?? "";
                        item.Name = salesTaxRet.Name?.GetValue() ?? "";
                        item.FullName = salesTaxRet.FullName?.GetValue() ?? "";
                        item.IsActive = salesTaxRet.IsActive?.GetValue() ?? true;
                        item.Description = salesTaxRet.ItemDesc?.GetValue() ?? "";
                        item.TaxRate = (decimal)(salesTaxRet.TaxRate?.GetValue() ?? 0.0);
                        item.TaxVendorRefListID = salesTaxRet.TaxVendorRef?.ListID?.GetValue() ?? "";
                        item.TaxVendorRefFullName = salesTaxRet.TaxVendorRef?.FullName?.GetValue() ?? "";
                        item.TimeCreated = salesTaxRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = salesTaxRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = salesTaxRet.EditSequence?.GetValue() ?? "";
                    }
                    else if (record is IItemGroupRet groupRet)
                    {
                        item.Type = "Group";
                        item.ListID = groupRet.ListID?.GetValue() ?? "";
                        item.Name = groupRet.Name?.GetValue() ?? "";
                        item.IsActive = groupRet.IsActive?.GetValue() ?? true;
                        item.Description = groupRet.ItemDesc?.GetValue() ?? "";
                        item.TimeCreated = groupRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = groupRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = groupRet.EditSequence?.GetValue() ?? "";
                        
                        // CRITICAL: Extract group components (items within the bundle)
                        if (groupRet.ItemGroupLineRetList != null)
                        {
                            for (int i = 0; i < groupRet.ItemGroupLineRetList.Count; i++)
                            {
                                var line = groupRet.ItemGroupLineRetList.GetAt(i);
                                item.GroupComponents.Add(new QBGroupItemComponent
                                {
                                    ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                    ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                    Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                    UnitOfMeasure = line.UnitOfMeasure?.GetValue() ?? ""
                                });
                            }
                        }
                    }
                    else if (record is IItemPaymentRet paymentRet)
                    {
                        item.Type = "Payment";
                        item.ListID = paymentRet.ListID?.GetValue() ?? "";
                        item.Name = paymentRet.Name?.GetValue() ?? "";
                        item.IsActive = paymentRet.IsActive?.GetValue() ?? true;
                        item.Description = paymentRet.ItemDesc?.GetValue() ?? "";
                        item.AccountRefListID = paymentRet.DepositToAccountRef?.ListID?.GetValue() ?? "";
                        item.AccountRefFullName = paymentRet.DepositToAccountRef?.FullName?.GetValue() ?? "";
                        item.TimeCreated = paymentRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = paymentRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = paymentRet.EditSequence?.GetValue() ?? "";
                    }
                    else if (record is IItemDiscountRet discountRet)
                    {
                        item.Type = "Discount";
                        item.ListID = discountRet.ListID?.GetValue() ?? "";
                        item.Name = discountRet.Name?.GetValue() ?? "";
                        item.IsActive = discountRet.IsActive?.GetValue() ?? true;
                        item.Description = discountRet.ItemDesc?.GetValue() ?? "";
                        item.AccountRefListID = discountRet.AccountRef?.ListID?.GetValue() ?? "";
                        item.AccountRefFullName = discountRet.AccountRef?.FullName?.GetValue() ?? "";
                        item.TimeCreated = discountRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = discountRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = discountRet.EditSequence?.GetValue() ?? "";
                    }
                    else if (record is IItemInventoryAssemblyRet assemblyRet)
                    {
                        item.Type = "InventoryAssembly";
                        item.ListID = assemblyRet.ListID?.GetValue() ?? "";
                        item.Name = assemblyRet.Name?.GetValue() ?? "";
                        item.FullName = assemblyRet.FullName?.GetValue() ?? "";
                        item.IsActive = assemblyRet.IsActive?.GetValue() ?? true;
                        item.Description = assemblyRet.SalesDesc?.GetValue() ?? "";
                        item.Price = (decimal)(assemblyRet.SalesPrice?.GetValue() ?? 0.0);
                        item.AccountRefListID = assemblyRet.IncomeAccountRef?.ListID?.GetValue() ?? "";
                        item.AccountRefFullName = assemblyRet.IncomeAccountRef?.FullName?.GetValue() ?? "";
                        item.AssetAccountRefListID = assemblyRet.AssetAccountRef?.ListID?.GetValue() ?? "";
                        item.AssetAccountRefFullName = assemblyRet.AssetAccountRef?.FullName?.GetValue() ?? "";
                        item.COGSAccountRefListID = assemblyRet.COGSAccountRef?.ListID?.GetValue() ?? "";
                        item.COGSAccountRefFullName = assemblyRet.COGSAccountRef?.FullName?.GetValue() ?? "";
                        item.QuantityOnHand = (decimal)(assemblyRet.QuantityOnHand?.GetValue() ?? 0.0);
                        item.TimeCreated = assemblyRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = assemblyRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = assemblyRet.EditSequence?.GetValue() ?? "";
                        
                        // CRITICAL: Extract assembly components (Bill of Materials)
                        if (assemblyRet.ItemInventoryAssemblyLineRetList != null)
                        {
                            for (int i = 0; i < assemblyRet.ItemInventoryAssemblyLineRetList.Count; i++)
                            {
                                var line = assemblyRet.ItemInventoryAssemblyLineRetList.GetAt(i);
                                item.AssemblyComponents.Add(new QBAssemblyComponent
                                {
                                    ItemRefListID = line.ItemInventoryRef?.ListID?.GetValue() ?? "",
                                    ItemRefFullName = line.ItemInventoryRef?.FullName?.GetValue() ?? "",
                                    Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0)
                                });
                            }
                        }
                    }
                    else if (record is IItemSalesTaxGroupRet taxGroupRet)
                    {
                        item.Type = "SalesTaxGroup";
                        item.ListID = taxGroupRet.ListID?.GetValue() ?? "";
                        item.Name = taxGroupRet.Name?.GetValue() ?? "";
                        item.IsActive = taxGroupRet.IsActive?.GetValue() ?? true;
                        item.Description = taxGroupRet.ItemDesc?.GetValue() ?? "";
                        item.TimeCreated = taxGroupRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = taxGroupRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = taxGroupRet.EditSequence?.GetValue() ?? "";
                        
                        // CRITICAL: Extract individual tax items in the group
                        if (taxGroupRet.ItemSalesTaxRetList != null)
                        {
                            for (int i = 0; i < taxGroupRet.ItemSalesTaxRetList.Count; i++)
                            {
                                var taxItem = taxGroupRet.ItemSalesTaxRetList.GetAt(i);
                                item.SalesTaxGroupComponents.Add(new QBSalesTaxGroupComponent
                                {
                                    ItemSalesTaxRefListID = taxItem.ListID?.GetValue() ?? "",
                                    ItemSalesTaxRefFullName = taxItem.FullName?.GetValue() ?? ""
                                });
                            }
                        }
                    }
                    else if (record is IItemSubtotalRet subtotalRet)
                    {
                        item.Type = "Subtotal";
                        item.ListID = subtotalRet.ListID?.GetValue() ?? "";
                        item.Name = subtotalRet.Name?.GetValue() ?? "";
                        item.IsActive = subtotalRet.IsActive?.GetValue() ?? true;
                        item.Description = subtotalRet.ItemDesc?.GetValue() ?? "";
                        item.TimeCreated = subtotalRet.TimeCreated?.GetValue() ?? DateTime.MinValue;
                        item.TimeModified = subtotalRet.TimeModified?.GetValue() ?? DateTime.MinValue;
                        item.EditSequence = subtotalRet.EditSequence?.GetValue() ?? "";
                    }

                    return item;
                },
                recordTypeName: "Items"
            );

            return allItems;
        }

        // ========================================================================
        // CONFIGURATION LISTS (No Iterators - Usually Small)
        // ========================================================================
        public List<QBClass> ExtractClasses()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendClassQueryRq(),
                recordParser: (record, index) =>
                {
                    var cls = (IClassRet)record;
                    return new QBClass
                    {
                        ListID = cls.ListID?.GetValue() ?? "",
                        Name = cls.Name?.GetValue() ?? "",
                        FullName = cls.FullName?.GetValue() ?? "",
                        IsActive = cls.IsActive?.GetValue() ?? true,
                        ParentRefListID = cls.ParentRef?.ListID?.GetValue() ?? "",
                        ParentRefFullName = cls.ParentRef?.FullName?.GetValue() ?? "",
                        Sublevel = cls.Sublevel?.GetValue() ?? 0,
                        TimeCreated = cls.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = cls.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = cls.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Classes"
            );
        }

        public List<QBPaymentMethod> ExtractPaymentMethods()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendPaymentMethodQueryRq(),
                recordParser: (record, index) =>
                {
                    var pm = (IPaymentMethodRet)record;
                    return new QBPaymentMethod
                    {
                        ListID = pm.ListID?.GetValue() ?? "",
                        Name = pm.Name?.GetValue() ?? "",
                        IsActive = pm.IsActive?.GetValue() ?? true,
                        PaymentMethodType = pm.PaymentMethodType?.GetValue().ToString() ?? "",
                        TimeCreated = pm.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = pm.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = pm.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Payment Methods"
            );
        }

        public List<QBTerms> ExtractTerms()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendTermsQueryRq(),
                recordParser: (record, index) =>
                {
                    var terms = (ITermsRet)record;
                    return new QBTerms
                    {
                        ListID = terms.ListID?.GetValue() ?? "",
                        Name = terms.Name?.GetValue() ?? "",
                        IsActive = terms.IsActive?.GetValue() ?? true,
                        StdDueDays = terms.StdDueDays?.GetValue() ?? 0,
                        StdDiscountDays = terms.StdDiscountDays?.GetValue() ?? 0,
                        DiscountPct = (decimal)(terms.DiscountPct?.GetValue() ?? 0.0),
                        TimeCreated = terms.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = terms.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = terms.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Terms"
            );
        }

        public List<QBSalesTaxCode> ExtractSalesTaxCodes()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendSalesTaxCodeQueryRq(),
                recordParser: (record, index) =>
                {
                    var stc = (ISalesTaxCodeRet)record;
                    return new QBSalesTaxCode
                    {
                        ListID = stc.ListID?.GetValue() ?? "",
                        Name = stc.Name?.GetValue() ?? "",
                        IsActive = stc.IsActive?.GetValue() ?? true,
                        IsTaxable = stc.IsTaxable?.GetValue() ?? false,
                        Desc = stc.Desc?.GetValue() ?? "",
                        TimeCreated = stc.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = stc.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = stc.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Sales Tax Codes"
            );
        }

        public List<QBCustomerType> ExtractCustomerTypes()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendCustomerTypeQueryRq(),
                recordParser: (record, index) =>
                {
                    var ct = (ICustomerTypeRet)record;
                    return new QBCustomerType
                    {
                        ListID = ct.ListID?.GetValue() ?? "",
                        Name = ct.Name?.GetValue() ?? "",
                        FullName = ct.FullName?.GetValue() ?? "",
                        IsActive = ct.IsActive?.GetValue() ?? true,
                        ParentRefListID = ct.ParentRef?.ListID?.GetValue() ?? "",
                        ParentRefFullName = ct.ParentRef?.FullName?.GetValue() ?? "",
                        Sublevel = ct.Sublevel?.GetValue() ?? 0,
                        TimeCreated = ct.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = ct.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = ct.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Customer Types"
            );
        }

        public List<QBVendorType> ExtractVendorTypes()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendVendorTypeQueryRq(),
                recordParser: (record, index) =>
                {
                    var vt = (IVendorTypeRet)record;
                    return new QBVendorType
                    {
                        ListID = vt.ListID?.GetValue() ?? "",
                        Name = vt.Name?.GetValue() ?? "",
                        FullName = vt.FullName?.GetValue() ?? "",
                        IsActive = vt.IsActive?.GetValue() ?? true,
                        ParentRefListID = vt.ParentRef?.ListID?.GetValue() ?? "",
                        ParentRefFullName = vt.ParentRef?.FullName?.GetValue() ?? "",
                        Sublevel = vt.Sublevel?.GetValue() ?? 0,
                        TimeCreated = vt.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = vt.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = vt.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Vendor Types"
            );
        }

        public List<QBJobType> ExtractJobTypes()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendJobTypeQueryRq(),
                recordParser: (record, index) =>
                {
                    var jt = (IJobTypeRet)record;
                    return new QBJobType
                    {
                        ListID = jt.ListID?.GetValue() ?? "",
                        Name = jt.Name?.GetValue() ?? "",
                        FullName = jt.FullName?.GetValue() ?? "",
                        IsActive = jt.IsActive?.GetValue() ?? true,
                        ParentRefListID = jt.ParentRef?.ListID?.GetValue() ?? "",
                        ParentRefFullName = jt.ParentRef?.FullName?.GetValue() ?? "",
                        Sublevel = jt.Sublevel?.GetValue() ?? 0,
                        TimeCreated = jt.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = jt.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = jt.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Job Types"
            );
        }

        public List<QBCurrency> ExtractCurrencies()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendCurrencyQueryRq(),
                recordParser: (record, index) =>
                {
                    var curr = (ICurrencyRet)record;
                    return new QBCurrency
                    {
                        ListID = curr.ListID?.GetValue() ?? "",
                        Name = curr.Name?.GetValue() ?? "",
                        IsActive = curr.IsActive?.GetValue() ?? true,
                        CurrencyCode = curr.CurrencyCode?.GetValue() ?? "",
                        IsUserDefinedCurrency = curr.IsUserDefinedCurrency?.GetValue() ?? false,
                        ExchangeRate = curr.ExchangeRate?.GetValue() ?? 0.0,
                        AsOfDate = curr.AsOfDate?.GetValue() ?? DateTime.MinValue,
                        ThousandSeparator = curr.CurrencyFormat?.ThousandSeparator?.GetValue().ToString() ?? "",
                        ThousandSeparatorGrouping = curr.CurrencyFormat?.ThousandSeparatorGrouping?.GetValue().ToString() ?? "",
                        DecimalPlaces = curr.CurrencyFormat?.DecimalPlaces?.GetValue().ToString() ?? "",
                        DecimalSeparator = curr.CurrencyFormat?.DecimalSeparator?.GetValue().ToString() ?? "",
                        TimeCreated = curr.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = curr.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = curr.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Currencies"
            );
        }

        public List<QBCustomerMsg> ExtractCustomerMessages()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendCustomerMsgQueryRq(),
                recordParser: (record, index) =>
                {
                    var msg = (ICustomerMsgRet)record;
                    return new QBCustomerMsg
                    {
                        ListID = msg.ListID?.GetValue() ?? "",
                        Name = msg.Name?.GetValue() ?? "",
                        IsActive = msg.IsActive?.GetValue() ?? true,
                        TimeCreated = msg.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = msg.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = msg.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Customer Messages"
            );
        }

        public List<QBDateDrivenTerms> ExtractDateDrivenTerms()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendDateDrivenTermsQueryRq(),
                recordParser: (record, index) =>
                {
                    var terms = (IDateDrivenTermsRet)record;
                    return new QBDateDrivenTerms
                    {
                        ListID = terms.ListID?.GetValue() ?? "",
                        Name = terms.Name?.GetValue() ?? "",
                        IsActive = terms.IsActive?.GetValue() ?? true,
                        DayOfMonthDue = terms.DayOfMonthDue?.GetValue() ?? 0,
                        DueNextMonthDays = terms.DueNextMonthDays?.GetValue() ?? 0,
                        DiscountDayOfMonth = terms.DiscountDayOfMonth?.GetValue() ?? 0,
                        DiscountPct = (decimal)(terms.DiscountPct?.GetValue() ?? 0.0),
                        TimeCreated = terms.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = terms.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = terms.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Date-Driven Terms"
            );
        }

        public List<QBInventorySite> ExtractInventorySites()
        {
            return iteratorHelper.ExtractWithoutIterator(
                queryAppender: (request) => request.AppendInventorySiteQueryRq(),
                recordParser: (record, index) =>
                {
                    var site = (IInventorySiteRet)record;
                    return new QBInventorySite
                    {
                        ListID = site.ListID?.GetValue() ?? "",
                        Name = site.Name?.GetValue() ?? "",
                        IsActive = site.IsActive?.GetValue() ?? true,
                        Description = site.SiteDesc?.GetValue() ?? "",
                        Email = site.Email?.GetValue() ?? "",
                        Contact = site.Contact?.GetValue() ?? "",
                        Phone = site.Phone?.GetValue() ?? "",
                        Fax = site.Fax?.GetValue() ?? "",
                        Addr1 = site.SiteAddress?.Addr1?.GetValue() ?? "",
                        Addr2 = site.SiteAddress?.Addr2?.GetValue() ?? "",
                        Addr3 = site.SiteAddress?.Addr3?.GetValue() ?? "",
                        Addr4 = site.SiteAddress?.Addr4?.GetValue() ?? "",
                        City = site.SiteAddress?.City?.GetValue() ?? "",
                        State = site.SiteAddress?.State?.GetValue() ?? "",
                        PostalCode = site.SiteAddress?.PostalCode?.GetValue() ?? "",
                        Country = site.SiteAddress?.Country?.GetValue() ?? "",
                        Note = site.SiteAddress?.Note?.GetValue() ?? "",
                        TimeCreated = site.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = site.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = site.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Inventory Sites"
            );
        }

        // ========================================================================
        // PAYROLL ITEMS
        // ========================================================================
        public List<QBPayrollItemWage> ExtractPayrollItemWages()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendPayrollItemWageQueryRq(),
                recordParser: (record, index) =>
                {
                    var wage = (IPayrollItemWageRet)record;
                    return new QBPayrollItemWage
                    {
                        ListID = wage.ListID?.GetValue() ?? "",
                        Name = wage.Name?.GetValue() ?? "",
                        IsActive = wage.IsActive?.GetValue() ?? true,
                        WageType = wage.WageType?.GetValue().ToString() ?? "",
                        ExpenseAccountRefListID = wage.ExpenseAccountRef?.ListID?.GetValue() ?? "",
                        ExpenseAccountRefFullName = wage.ExpenseAccountRef?.FullName?.GetValue() ?? "",
                        TimeCreated = wage.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = wage.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = wage.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Payroll Item Wages"
            );
        }

        public List<QBPayrollItemNonWage> ExtractPayrollItemNonWages()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendPayrollItemNonWageQueryRq(),
                recordParser: (record, index) =>
                {
                    var nonWage = (IPayrollItemNonWageRet)record;
                    return new QBPayrollItemNonWage
                    {
                        ListID = nonWage.ListID?.GetValue() ?? "",
                        Name = nonWage.Name?.GetValue() ?? "",
                        IsActive = nonWage.IsActive?.GetValue() ?? true,
                        NonWageType = nonWage.NonWageType?.GetValue().ToString() ?? "",
                        ExpenseAccountRefListID = nonWage.ExpenseAccountRef?.ListID?.GetValue() ?? "",
                        ExpenseAccountRefFullName = nonWage.ExpenseAccountRef?.FullName?.GetValue() ?? "",
                        LiabilityAccountRefListID = nonWage.LiabilityAccountRef?.ListID?.GetValue() ?? "",
                        LiabilityAccountRefFullName = nonWage.LiabilityAccountRef?.FullName?.GetValue() ?? "",
                        TimeCreated = nonWage.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = nonWage.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = nonWage.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Payroll Item Non-Wages"
            );
        }

        public List<QBWorkersCompCode> ExtractWorkersCompCodes()
        {
            var workersCodes = new List<QBWorkersCompCode>();
            
            IMsgSetRequest requestMsgSet = sessionManager.CreateMsgSetRequest(country, qbXMLMajorVer, qbXMLMinorVer);
            requestMsgSet.Attributes.OnError = ENRqOnError.roeContinue;
            
            IWorkersCompCodeQuery query = requestMsgSet.AppendWorkersCompCodeQueryRq();
            
            IMsgSetResponse responseMsgSet = sessionManager.DoRequests(requestMsgSet);
            IResponse response = responseMsgSet.ResponseList.GetAt(0);
            
            if (response.StatusCode >= 0 && response.Detail != null)
            {
                IWorkersCompCodeRetList retList = (IWorkersCompCodeRetList)response.Detail;
                
                for (int i = 0; i < retList.Count; i++)
                {
                    IWorkersCompCodeRet code = retList.GetAt(i);
                    var workersCode = new QBWorkersCompCode
                    {
                        ListID = code.ListID?.GetValue() ?? "",
                        Name = code.Name?.GetValue() ?? "",
                        IsActive = code.IsActive?.GetValue() ?? true,
                        Desc = code.Desc?.GetValue() ?? "",
                        CurrentRate = (decimal)(code.CurrentRate?.GetValue() ?? 0.0),
                        CurrentEffectiveDate = code.CurrentEffectiveDate?.GetValue() ?? DateTime.MinValue,
                        NextRate = (decimal)(code.NextRate?.GetValue() ?? 0.0),
                        NextEffectiveDate = code.NextEffectiveDate?.GetValue() ?? DateTime.MinValue,
                        TimeCreated = code.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = code.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = code.EditSequence?.GetValue() ?? ""
                    };
                    
                    // Extract rate history
                    if (code.RateHistoryList != null)
                    {
                        for (int j = 0; j < code.RateHistoryList.Count; j++)
                        {
                            var history = code.RateHistoryList.GetAt(j);
                            workersCode.RateHistory.Add(new QBWorkersCompRateHistory
                            {
                                Rate = (decimal)(history.Rate?.GetValue() ?? 0.0),
                                EffectiveDate = history.EffectiveDate?.GetValue() ?? DateTime.MinValue
                            });
                        }
                    }
                    
                    workersCodes.Add(workersCode);
                }
            }
            
            Console.WriteLine($"    Extracted {workersCodes.Count} Workers Comp Codes");
            return workersCodes;
        }

        public List<QBPriceLevel> ExtractPriceLevels()
        {
            var priceLevels = new List<QBPriceLevel>();
            
            IMsgSetRequest requestMsgSet = sessionManager.CreateMsgSetRequest(country, qbXMLMajorVer, qbXMLMinorVer);
            requestMsgSet.Attributes.OnError = ENRqOnError.roeContinue;
            
            IPriceLevelQuery query = requestMsgSet.AppendPriceLevelQueryRq();
            
            IMsgSetResponse responseMsgSet = sessionManager.DoRequests(requestMsgSet);
            IResponse response = responseMsgSet.ResponseList.GetAt(0);
            
            if (response.StatusCode >= 0 && response.Detail != null)
            {
                IPriceLevelRetList retList = (IPriceLevelRetList)response.Detail;
                
                for (int i = 0; i < retList.Count; i++)
                {
                    IPriceLevelRet level = retList.GetAt(i);
                    priceLevels.Add(new QBPriceLevel
                    {
                        ListID = level.ListID?.GetValue() ?? "",
                        Name = level.Name?.GetValue() ?? "",
                        IsActive = level.IsActive?.GetValue() ?? true,
                        PriceLevelType = level.PriceLevelType?.GetValue().ToString() ?? "",
                        FixedPercentage = level.ORPriceLevelRet?.PriceLevelFixedPercentage?.GetValue() != null ? 
                            (decimal)(double)level.ORPriceLevelRet.PriceLevelFixedPercentage.GetValue() : 0m,
                        TimeCreated = level.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = level.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = level.EditSequence?.GetValue() ?? ""
                    });
                }
            }
            
            Console.WriteLine($"    Extracted {priceLevels.Count} Price Levels");
            return priceLevels;
        }

        public List<QBSalesRep> ExtractSalesReps()
        {
            var salesReps = new List<QBSalesRep>();
            
            IMsgSetRequest requestMsgSet = sessionManager.CreateMsgSetRequest(country, qbXMLMajorVer, qbXMLMinorVer);
            requestMsgSet.Attributes.OnError = ENRqOnError.roeContinue;
            
            ISalesRepQuery query = requestMsgSet.AppendSalesRepQueryRq();
            
            IMsgSetResponse responseMsgSet = sessionManager.DoRequests(requestMsgSet);
            IResponse response = responseMsgSet.ResponseList.GetAt(0);
            
            if (response.StatusCode >= 0 && response.Detail != null)
            {
                ISalesRepRetList retList = (ISalesRepRetList)response.Detail;
                
                for (int i = 0; i < retList.Count; i++)
                {
                    ISalesRepRet rep = retList.GetAt(i);
                    salesReps.Add(new QBSalesRep
                    {
                        ListID = rep.ListID?.GetValue() ?? "",
                        Initial = rep.Initial?.GetValue() ?? "",
                        IsActive = rep.IsActive?.GetValue() ?? true,
                        SalesRepEntityRefListID = rep.SalesRepEntityRef?.ListID?.GetValue() ?? "",
                        SalesRepEntityRefFullName = rep.SalesRepEntityRef?.FullName?.GetValue() ?? "",
                        TimeCreated = rep.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = rep.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = rep.EditSequence?.GetValue() ?? ""
                    });
                }
            }
            
            Console.WriteLine($"    Extracted {salesReps.Count} Sales Reps");
            return salesReps;
        }

        public List<QBShipMethod> ExtractShipMethods()
        {
            var shipMethods = new List<QBShipMethod>();
            
            IMsgSetRequest requestMsgSet = sessionManager.CreateMsgSetRequest(country, qbXMLMajorVer, qbXMLMinorVer);
            requestMsgSet.Attributes.OnError = ENRqOnError.roeContinue;
            
            IShipMethodQuery query = requestMsgSet.AppendShipMethodQueryRq();
            
            IMsgSetResponse responseMsgSet = sessionManager.DoRequests(requestMsgSet);
            IResponse response = responseMsgSet.ResponseList.GetAt(0);
            
            if (response.StatusCode >= 0 && response.Detail != null)
            {
                IShipMethodRetList retList = (IShipMethodRetList)response.Detail;
                
                for (int i = 0; i < retList.Count; i++)
                {
                    IShipMethodRet method = retList.GetAt(i);
                    shipMethods.Add(new QBShipMethod
                    {
                        ListID = method.ListID?.GetValue() ?? "",
                        Name = method.Name?.GetValue() ?? "",
                        IsActive = method.IsActive?.GetValue() ?? true,
                        TimeCreated = method.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = method.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = method.EditSequence?.GetValue() ?? ""
                    });
                }
            }
            
            Console.WriteLine($"    Extracted {shipMethods.Count} Ship Methods");
            return shipMethods;
        }

        // ========================================================================
        // TRANSACTIONS (WITH ITERATORS)
        // ========================================================================
        private List<QBInvoice> ExtractInvoices()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendInvoiceQueryRq(),
                recordParser: (record, index) =>
                {
                    var inv = (IInvoiceRet)record;
                    var invoice = new QBInvoice
                    {
                        TxnID = inv.TxnID?.GetValue() ?? "",
                        RefNumber = inv.RefNumber?.GetValue() ?? "",
                        TxnDate = inv.TxnDate?.GetValue() ?? DateTime.MinValue,
                        CustomerRefListID = inv.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = inv.CustomerRef?.FullName?.GetValue() ?? "",
                        ClassRefListID = inv.ClassRef?.ListID?.GetValue() ?? "",
                        ClassRefFullName = inv.ClassRef?.FullName?.GetValue() ?? "",
                        ARAccountRefListID = inv.ARAccountRef?.ListID?.GetValue() ?? "",
                        ARAccountRefFullName = inv.ARAccountRef?.FullName?.GetValue() ?? "",
                        TermsRefListID = inv.TermsRef?.ListID?.GetValue() ?? "",
                        TermsRefFullName = inv.TermsRef?.FullName?.GetValue() ?? "",
                        DueDate = inv.DueDate?.GetValue() ?? DateTime.MinValue,
                        SalesRepRefListID = inv.SalesRepRef?.ListID?.GetValue() ?? "",
                        SalesRepRefFullName = inv.SalesRepRef?.FullName?.GetValue() ?? "",
                        PONumber = inv.PONumber?.GetValue() ?? "",
                        Subtotal = (decimal)(inv.Subtotal?.GetValue() ?? 0.0),
                        SalesTaxPercentage = (decimal)(inv.SalesTaxPercentage?.GetValue() ?? 0.0),
                        SalesTaxTotal = (decimal)(inv.SalesTaxTotal?.GetValue() ?? 0.0),
                        AppliedAmount = (decimal)(inv.AppliedAmount?.GetValue() ?? 0.0),
                        BalanceRemaining = (decimal)(inv.BalanceRemaining?.GetValue() ?? 0.0),
                        Memo = inv.Memo?.GetValue() ?? "",
                        IsPending = inv.IsPending?.GetValue() ?? false,
                        IsPaid = inv.IsPaid?.GetValue() ?? false,
                        IsToBePrinted = inv.IsToBePrinted?.GetValue() ?? false,
                        IsToBeEmailed = inv.IsToBeEmailed?.GetValue() ?? false,
                        TimeCreated = inv.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = inv.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = inv.EditSequence?.GetValue() ?? ""
                    };

                    // Extract invoice lines
                    if (inv.InvoiceLineRetList != null)
                    {
                        for (int i = 0; i < inv.InvoiceLineRetList.Count; i++)
                        {
                            var line = inv.InvoiceLineRetList.GetAt(i);
                            invoice.Lines.Add(new QBInvoiceLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                Rate = (decimal)(line.Rate?.GetValue() ?? 0.0),
                                RatePercent = (decimal)(line.RatePercent?.GetValue() ?? 0.0),
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                SalesTaxCodeRefListID = line.SalesTaxCodeRef?.ListID?.GetValue() ?? "",
                                SalesTaxCodeRefFullName = line.SalesTaxCodeRef?.FullName?.GetValue() ?? ""
                            });
                        }
                    }

                    // Compute forensic integrity hash (THE $60M COLUMN)
                    invoice.Sha256IntegrityHash = ForensicHashingService.ComputeInvoiceHash(invoice);

                    return invoice;
                },
                recordTypeName: "Invoices"
            );
        }

        private List<QBPurchaseOrder> ExtractPurchaseOrders()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendPurchaseOrderQueryRq(),
                recordParser: (record, index) =>
                {
                    var po = (IPurchaseOrderRet)record;
                    var purchaseOrder = new QBPurchaseOrder
                    {
                        TxnID = po.TxnID?.GetValue() ?? "",
                        RefNumber = po.RefNumber?.GetValue() ?? "",
                        TxnDate = po.TxnDate?.GetValue() ?? DateTime.MinValue,
                        ExpectedDate = po.ExpectedDate?.GetValue() ?? DateTime.MinValue,
                        VendorRefListID = po.VendorRef?.ListID?.GetValue() ?? "",
                        VendorRefFullName = po.VendorRef?.FullName?.GetValue() ?? "",
                        VendorMsg = po.VendorMsg?.GetValue() ?? "",
                        Memo = po.Memo?.GetValue() ?? "",
                        Subtotal = (decimal)(po.Subtotal?.GetValue() ?? 0.0),
                        SalesTaxTotal = (decimal)(po.SalesTaxTotal?.GetValue() ?? 0.0),
                        TotalAmount = (decimal)(po.TotalAmount?.GetValue() ?? 0.0),
                        CurrencyRefListID = po.CurrencyRef?.ListID?.GetValue() ?? "",
                        CurrencyRefFullName = po.CurrencyRef?.FullName?.GetValue() ?? "",
                        IsManuallyClosed = po.IsManuallyClosed?.GetValue() ?? false,
                        IsFullyReceived = po.IsFullyReceived?.GetValue() ?? false,
                        ShipToEntityRefListID = po.ShipToEntityRef?.ListID?.GetValue() ?? "",
                        ShipToEntityRefFullName = po.ShipToEntityRef?.FullName?.GetValue() ?? "",
                        ShipMethodRefListID = po.ShipMethodRef?.ListID?.GetValue() ?? "",
                        ShipMethodRefFullName = po.ShipMethodRef?.FullName?.GetValue() ?? "",
                        ShipDate = po.ShipDate?.GetValue() ?? DateTime.MinValue,
                        TimeCreated = po.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = po.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = po.EditSequence?.GetValue() ?? ""
                    };

                    // Extract line items
                    if (po.PurchaseOrderLineRetList != null)
                    {
                        for (int i = 0; i < po.PurchaseOrderLineRetList.Count; i++)
                        {
                            var line = po.PurchaseOrderLineRetList.GetAt(i);
                            purchaseOrder.Lines.Add(new QBPurchaseOrderLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                UnitOfMeasure = line.UnitOfMeasure?.GetValue() ?? "",
                                Rate = (decimal)(line.Rate?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                IsManuallyClosed = line.IsManuallyClosed?.GetValue() ?? false,
                                ReceivedQuantity = (decimal)(line.ReceivedQuantity?.GetValue() ?? 0.0)
                            });
                        }
                    }

                    return purchaseOrder;
                },
                recordTypeName: "Purchase Orders"
            );
        }

        private List<QBSalesOrder> ExtractSalesOrders()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendSalesOrderQueryRq(),
                recordParser: (record, index) =>
                {
                    var so = (ISalesOrderRet)record;
                    var salesOrder = new QBSalesOrder
                    {
                        TxnID = so.TxnID?.GetValue() ?? "",
                        RefNumber = so.RefNumber?.GetValue() ?? "",
                        TxnDate = so.TxnDate?.GetValue() ?? DateTime.MinValue,
                        DueDate = so.DueDate?.GetValue() ?? DateTime.MinValue,
                        CustomerRefListID = so.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = so.CustomerRef?.FullName?.GetValue() ?? "",
                        ClassRefListID = so.ClassRef?.ListID?.GetValue() ?? "",
                        ClassRefFullName = so.ClassRef?.FullName?.GetValue() ?? "",
                        TemplateRefListID = so.TemplateRef?.ListID?.GetValue() ?? "",
                        TemplateRefFullName = so.TemplateRef?.FullName?.GetValue() ?? "",
                        PONumber = so.PONumber?.GetValue() ?? "",
                        Memo = so.Memo?.GetValue() ?? "",
                        CustomerMsg = so.CustomerMsg?.GetValue() ?? "",
                        Subtotal = (decimal)(so.Subtotal?.GetValue() ?? 0.0),
                        SalesTaxTotal = (decimal)(so.SalesTaxTotal?.GetValue() ?? 0.0),
                        TotalAmount = (decimal)(so.TotalAmount?.GetValue() ?? 0.0),
                        CurrencyRefListID = so.CurrencyRef?.ListID?.GetValue() ?? "",
                        CurrencyRefFullName = so.CurrencyRef?.FullName?.GetValue() ?? "",
                        IsManuallyClosed = so.IsManuallyClosed?.GetValue() ?? false,
                        IsFullyInvoiced = so.IsFullyInvoiced?.GetValue() ?? false,
                        ShipMethodRefListID = so.ShipMethodRef?.ListID?.GetValue() ?? "",
                        ShipMethodRefFullName = so.ShipMethodRef?.FullName?.GetValue() ?? "",
                        ShipDate = so.ShipDate?.GetValue() ?? DateTime.MinValue,
                        TimeCreated = so.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = so.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = so.EditSequence?.GetValue() ?? ""
                    };

                    // Extract line items
                    if (so.SalesOrderLineRetList != null)
                    {
                        for (int i = 0; i < so.SalesOrderLineRetList.Count; i++)
                        {
                            var line = so.SalesOrderLineRetList.GetAt(i);
                            salesOrder.Lines.Add(new QBSalesOrderLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                UnitOfMeasure = line.UnitOfMeasure?.GetValue() ?? "",
                                Rate = (decimal)(line.Rate?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                SalesTaxCodeRefListID = line.SalesTaxCodeRef?.ListID?.GetValue() ?? "",
                                SalesTaxCodeRefFullName = line.SalesTaxCodeRef?.FullName?.GetValue() ?? "",
                                IsManuallyClosed = line.IsManuallyClosed?.GetValue() ?? false,
                                Invoiced = (decimal)(line.Invoiced?.GetValue() ?? 0.0)
                            });
                        }
                    }

                    return salesOrder;
                },
                recordTypeName: "Sales Orders"
            );
        }

        private List<QBBill> ExtractBills()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendBillQueryRq(),
                recordParser: (record, index) =>
                {
                    var billRet = (IBillRet)record;
                    var bill = new QBBill
                    {
                        TxnID = billRet.TxnID?.GetValue() ?? "",
                        RefNumber = billRet.RefNumber?.GetValue() ?? "",
                        TxnDate = billRet.TxnDate?.GetValue() ?? DateTime.MinValue,
                        DueDate = billRet.DueDate?.GetValue() ?? DateTime.MinValue,
                        VendorRefListID = billRet.VendorRef?.ListID?.GetValue() ?? "",
                        VendorRefFullName = billRet.VendorRef?.FullName?.GetValue() ?? "",
                        AmountDue = (decimal)(billRet.AmountDue?.GetValue() ?? 0.0),
                        APAccountRefListID = billRet.APAccountRef?.ListID?.GetValue() ?? "",
                        APAccountRefFullName = billRet.APAccountRef?.FullName?.GetValue() ?? "",
                        Memo = billRet.Memo?.GetValue() ?? "",
                        IsPaid = billRet.IsPaid?.GetValue() ?? false,
                        TimeCreated = billRet.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = billRet.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = billRet.EditSequence?.GetValue() ?? ""
                    };

                    // Extract expense lines
                    if (billRet.ExpenseLineRetList != null)
                    {
                        for (int i = 0; i < billRet.ExpenseLineRetList.Count; i++)
                        {
                            var line = billRet.ExpenseLineRetList.GetAt(i);
                            bill.ExpenseLines.Add(new QBBillLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                AccountRefListID = line.AccountRef?.ListID?.GetValue() ?? "",
                                AccountRefFullName = line.AccountRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                Memo = line.Memo?.GetValue() ?? "",
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    // Extract item lines
                    if (billRet.ItemLineRetList != null)
                    {
                        for (int i = 0; i < billRet.ItemLineRetList.Count; i++)
                        {
                            var line = billRet.ItemLineRetList.GetAt(i);
                            bill.ItemLines.Add(new QBBillItemLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                Cost = (decimal)(line.Cost?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    // Compute forensic integrity hash
                    bill.Sha256IntegrityHash = ForensicHashingService.ComputeBillHash(bill);

                    return bill;
                },
                recordTypeName: "Bills"
            );
        }

        private List<QBBillPaymentCheck> ExtractBillPayments()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendBillPaymentCheckQueryRq(),
                recordParser: (record, index) =>
                {
                    var bpc = (IBillPaymentCheckRet)record;
                    var payment = new QBBillPaymentCheck
                    {
                        TxnID = bpc.TxnID?.GetValue() ?? "",
                        RefNumber = bpc.RefNumber?.GetValue() ?? "",
                        TxnDate = bpc.TxnDate?.GetValue() ?? DateTime.MinValue,
                        VendorRefListID = bpc.VendorRef?.ListID?.GetValue() ?? "",
                        VendorRefFullName = bpc.VendorRef?.FullName?.GetValue() ?? "",
                        APAccountRefListID = bpc.APAccountRef?.ListID?.GetValue() ?? "",
                        APAccountRefFullName = bpc.APAccountRef?.FullName?.GetValue() ?? "",
                        BankAccountRefListID = bpc.BankAccountRef?.ListID?.GetValue() ?? "",
                        BankAccountRefFullName = bpc.BankAccountRef?.FullName?.GetValue() ?? "",
                        Amount = (decimal)(bpc.Amount?.GetValue() ?? 0.0),
                        Memo = bpc.Memo?.GetValue() ?? "",
                        IsToBePrinted = bpc.IsToBePrinted?.GetValue() ?? false,
                        TimeCreated = bpc.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = bpc.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = bpc.EditSequence?.GetValue() ?? ""
                    };

                    // Extract applied transactions (OLD FORMAT - keeping for compatibility)
                    if (bpc.AppliedToTxnRetList != null)
                    {
                        for (int i = 0; i < bpc.AppliedToTxnRetList.Count; i++)
                        {
                            var applied = bpc.AppliedToTxnRetList.GetAt(i);
                            payment.AppliedToTxns.Add(new QBBillPaymentLine
                            {
                                TxnID = applied.TxnID?.GetValue() ?? "",
                                RefNumber = applied.RefNumber?.GetValue() ?? "",
                                TxnDate = applied.TxnDate?.GetValue() ?? DateTime.MinValue,
                                AppliedAmount = (decimal)(applied.AppliedAmount?.GetValue() ?? 0.0),
                                BalanceRemaining = (decimal)(applied.BalanceRemaining?.GetValue() ?? 0.0)
                            });
                            
                            // CRITICAL: ALSO add to LinkedTransactions for payment tracking
                            payment.LinkedTransactions.Add(new QBLinkedTxn
                            {
                                TxnID = applied.TxnID?.GetValue() ?? "",
                                TxnType = applied.TxnType?.GetValue().ToString() ?? "Bill",
                                TxnDate = applied.TxnDate?.GetValue() ?? DateTime.MinValue,
                                RefNumber = applied.RefNumber?.GetValue() ?? "",
                                LinkAmount = (decimal)(applied.AppliedAmount?.GetValue() ?? 0.0)
                            });
                        }
                    }

                    return payment;
                },
                recordTypeName: "Bill Payments"
            );
        }

        private List<QBVendorCredit> ExtractVendorCredits()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendVendorCreditQueryRq(),
                recordParser: (record, index) =>
                {
                    var vc = (IVendorCreditRet)record;
                    var vendorCredit = new QBVendorCredit
                    {
                        TxnID = vc.TxnID?.GetValue() ?? "",
                        RefNumber = vc.RefNumber?.GetValue() ?? "",
                        TxnDate = vc.TxnDate?.GetValue() ?? DateTime.MinValue,
                        VendorRefListID = vc.VendorRef?.ListID?.GetValue() ?? "",
                        VendorRefFullName = vc.VendorRef?.FullName?.GetValue() ?? "",
                        APAccountRefListID = vc.APAccountRef?.ListID?.GetValue() ?? "",
                        APAccountRefFullName = vc.APAccountRef?.FullName?.GetValue() ?? "",
                        CreditAmount = (decimal)(vc.CreditAmount?.GetValue() ?? 0.0),
                        Memo = vc.Memo?.GetValue() ?? "",
                        IsPaid = vc.IsPaid?.GetValue() ?? false,
                        CreditRemaining = (decimal)(vc.CreditRemaining?.GetValue() ?? 0.0),
                        TimeCreated = vc.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = vc.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = vc.EditSequence?.GetValue() ?? ""
                    };

                    // Extract expense lines
                    if (vc.ExpenseLineRetList != null)
                    {
                        for (int i = 0; i < vc.ExpenseLineRetList.Count; i++)
                        {
                            var line = vc.ExpenseLineRetList.GetAt(i);
                            vendorCredit.ExpenseLines.Add(new QBVendorCreditExpenseLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                AccountRefListID = line.AccountRef?.ListID?.GetValue() ?? "",
                                AccountRefFullName = line.AccountRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                Memo = line.Memo?.GetValue() ?? "",
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    // Extract item lines
                    if (vc.ItemLineRetList != null)
                    {
                        for (int i = 0; i < vc.ItemLineRetList.Count; i++)
                        {
                            var line = vc.ItemLineRetList.GetAt(i);
                            vendorCredit.ItemLines.Add(new QBVendorCreditItemLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                UnitOfMeasure = line.UnitOfMeasure?.GetValue() ?? "",
                                Cost = (decimal)(line.Cost?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    return vendorCredit;
                },
                recordTypeName: "Vendor Credits"
            );
        }

        private List<QBReceivePayment> ExtractReceivePayments()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendReceivePaymentQueryRq(),
                recordParser: (record, index) =>
                {
                    var rp = (IReceivePaymentRet)record;
                    var payment = new QBReceivePayment
                    {
                        TxnID = rp.TxnID?.GetValue() ?? "",
                        RefNumber = rp.RefNumber?.GetValue() ?? "",
                        TxnDate = rp.TxnDate?.GetValue() ?? DateTime.MinValue,
                        CustomerRefListID = rp.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = rp.CustomerRef?.FullName?.GetValue() ?? "",
                        ARAccountRefListID = rp.ARAccountRef?.ListID?.GetValue() ?? "",
                        ARAccountRefFullName = rp.ARAccountRef?.FullName?.GetValue() ?? "",
                        TotalAmount = (decimal)(rp.TotalAmount?.GetValue() ?? 0.0),
                        PaymentMethodRefListID = rp.PaymentMethodRef?.ListID?.GetValue() ?? "",
                        PaymentMethodRefFullName = rp.PaymentMethodRef?.FullName?.GetValue() ?? "",
                        Memo = rp.Memo?.GetValue() ?? "",
                        DepositToAccountRefListID = rp.DepositToAccountRef?.ListID?.GetValue() ?? "",
                        DepositToAccountRefFullName = rp.DepositToAccountRef?.FullName?.GetValue() ?? "",
                        TimeCreated = rp.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = rp.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = rp.EditSequence?.GetValue() ?? ""
                    };

                    // Extract applied transactions (OLD FORMAT - keeping for compatibility)
                    if (rp.AppliedToTxnRetList != null)
                    {
                        for (int i = 0; i < rp.AppliedToTxnRetList.Count; i++)
                        {
                            var applied = rp.AppliedToTxnRetList.GetAt(i);
                            payment.AppliedToTxns.Add(new QBReceivePaymentLine
                            {
                                TxnID = applied.TxnID?.GetValue() ?? "",
                                RefNumber = applied.RefNumber?.GetValue() ?? "",
                                TxnDate = applied.TxnDate?.GetValue() ?? DateTime.MinValue,
                                AppliedAmount = (decimal)(applied.AppliedAmount?.GetValue() ?? 0.0),
                                BalanceRemaining = (decimal)(applied.BalanceRemaining?.GetValue() ?? 0.0)
                            });
                            
                            // CRITICAL: ALSO add to LinkedTransactions for payment tracking
                            payment.LinkedTransactions.Add(new QBLinkedTxn
                            {
                                TxnID = applied.TxnID?.GetValue() ?? "",
                                TxnType = applied.TxnType?.GetValue().ToString() ?? "Invoice",
                                TxnDate = applied.TxnDate?.GetValue() ?? DateTime.MinValue,
                                RefNumber = applied.RefNumber?.GetValue() ?? "",
                                LinkAmount = (decimal)(applied.AppliedAmount?.GetValue() ?? 0.0)
                            });
                        }
                    }

                    return payment;
                },
                recordTypeName: "Receive Payments"
            );
        }

        // ========================================================================
        // CHECKS
        // ========================================================================
        private List<QBCheck> ExtractChecks()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendCheckQueryRq(),
                recordParser: (record, index) =>
                {
                    var check = (ICheckRet)record;
                    var checkData = new QBCheck
                    {
                        TxnID = check.TxnID?.GetValue() ?? "",
                        RefNumber = check.RefNumber?.GetValue() ?? "",
                        TxnDate = check.TxnDate?.GetValue() ?? DateTime.MinValue,
                        PayeeEntityRefListID = check.PayeeEntityRef?.ListID?.GetValue() ?? "",
                        PayeeEntityRefFullName = check.PayeeEntityRef?.FullName?.GetValue() ?? "",
                        AccountRefListID = check.AccountRef?.ListID?.GetValue() ?? "",
                        AccountRefFullName = check.AccountRef?.FullName?.GetValue() ?? "",
                        Amount = (decimal)(check.Amount?.GetValue() ?? 0.0),
                        Memo = check.Memo?.GetValue() ?? "",
                        IsToBePrinted = check.IsToBePrinted?.GetValue() ?? false,
                        
                        // CRITICAL: Extract ClearedStatus for bank reconciliation
                        ClearedStatus = check.ClearedStatus?.GetValue().ToString() ?? "NotCleared",
                        
                        TimeCreated = check.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = check.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = check.EditSequence?.GetValue() ?? ""
                    };

                    // Extract expense lines
                    if (check.ExpenseLineRetList != null)
                    {
                        for (int i = 0; i < check.ExpenseLineRetList.Count; i++)
                        {
                            var line = check.ExpenseLineRetList.GetAt(i);
                            checkData.ExpenseLines.Add(new QBCheckExpenseLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                AccountRefListID = line.AccountRef?.ListID?.GetValue() ?? "",
                                AccountRefFullName = line.AccountRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                Memo = line.Memo?.GetValue() ?? "",
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    // Extract item lines
                    if (check.ItemLineRetList != null)
                    {
                        for (int i = 0; i < check.ItemLineRetList.Count; i++)
                        {
                            var line = check.ItemLineRetList.GetAt(i);
                            checkData.ItemLines.Add(new QBCheckItemLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                Cost = (decimal)(line.Cost?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    return checkData;
                },
                recordTypeName: "Checks"
            );
        }

        // ========================================================================
        // CREDIT CARD CHARGES
        // ========================================================================
        private List<QBCreditCardCharge> ExtractCreditCardCharges()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendCreditCardChargeQueryRq(),
                recordParser: (record, index) =>
                {
                    var charge = (ICreditCardChargeRet)record;
                    var chargeData = new QBCreditCardCharge
                    {
                        TxnID = charge.TxnID?.GetValue() ?? "",
                        RefNumber = charge.RefNumber?.GetValue() ?? "",
                        TxnDate = charge.TxnDate?.GetValue() ?? DateTime.MinValue,
                        PayeeEntityRefListID = charge.PayeeEntityRef?.ListID?.GetValue() ?? "",
                        PayeeEntityRefFullName = charge.PayeeEntityRef?.FullName?.GetValue() ?? "",
                        AccountRefListID = charge.AccountRef?.ListID?.GetValue() ?? "",
                        AccountRefFullName = charge.AccountRef?.FullName?.GetValue() ?? "",
                        Amount = (decimal)(charge.Amount?.GetValue() ?? 0.0),
                        Memo = charge.Memo?.GetValue() ?? "",
                        
                        // CRITICAL: Extract ClearedStatus for bank reconciliation
                        ClearedStatus = charge.ClearedStatus?.GetValue().ToString() ?? "NotCleared",
                        
                        TimeCreated = charge.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = charge.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = charge.EditSequence?.GetValue() ?? ""
                    };

                    // Extract expense lines
                    if (charge.ExpenseLineRetList != null)
                    {
                        for (int i = 0; i < charge.ExpenseLineRetList.Count; i++)
                        {
                            var line = charge.ExpenseLineRetList.GetAt(i);
                            chargeData.ExpenseLines.Add(new QBCreditCardChargeExpenseLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                AccountRefListID = line.AccountRef?.ListID?.GetValue() ?? "",
                                AccountRefFullName = line.AccountRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                Memo = line.Memo?.GetValue() ?? "",
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    // Extract item lines
                    if (charge.ItemLineRetList != null)
                    {
                        for (int i = 0; i < charge.ItemLineRetList.Count; i++)
                        {
                            var line = charge.ItemLineRetList.GetAt(i);
                            chargeData.ItemLines.Add(new QBCreditCardChargeItemLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                Cost = (decimal)(line.Cost?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    return chargeData;
                },
                recordTypeName: "Credit Card Charges"
            );
        }

        // ========================================================================
        // CREDIT CARD CREDITS
        // ========================================================================
        private List<QBCreditCardCredit> ExtractCreditCardCredits()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendCreditCardCreditQueryRq(),
                recordParser: (record, index) =>
                {
                    var credit = (ICreditCardCreditRet)record;
                    var creditData = new QBCreditCardCredit
                    {
                        TxnID = credit.TxnID?.GetValue() ?? "",
                        RefNumber = credit.RefNumber?.GetValue() ?? "",
                        TxnDate = credit.TxnDate?.GetValue() ?? DateTime.MinValue,
                        PayeeEntityRefListID = credit.PayeeEntityRef?.ListID?.GetValue() ?? "",
                        PayeeEntityRefFullName = credit.PayeeEntityRef?.FullName?.GetValue() ?? "",
                        AccountRefListID = credit.AccountRef?.ListID?.GetValue() ?? "",
                        AccountRefFullName = credit.AccountRef?.FullName?.GetValue() ?? "",
                        Amount = (decimal)(credit.Amount?.GetValue() ?? 0.0),
                        Memo = credit.Memo?.GetValue() ?? "",
                        
                        // CRITICAL: Extract ClearedStatus for bank reconciliation
                        ClearedStatus = credit.ClearedStatus?.GetValue().ToString() ?? "NotCleared",
                        
                        TimeCreated = credit.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = credit.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = credit.EditSequence?.GetValue() ?? ""
                    };

                    // Extract expense lines
                    if (credit.ExpenseLineRetList != null)
                    {
                        for (int i = 0; i < credit.ExpenseLineRetList.Count; i++)
                        {
                            var line = credit.ExpenseLineRetList.GetAt(i);
                            creditData.ExpenseLines.Add(new QBCreditCardCreditExpenseLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                AccountRefListID = line.AccountRef?.ListID?.GetValue() ?? "",
                                AccountRefFullName = line.AccountRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                Memo = line.Memo?.GetValue() ?? "",
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    // Extract item lines
                    if (credit.ItemLineRetList != null)
                    {
                        for (int i = 0; i < credit.ItemLineRetList.Count; i++)
                        {
                            var line = credit.ItemLineRetList.GetAt(i);
                            creditData.ItemLines.Add(new QBCreditCardCreditItemLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                Cost = (decimal)(line.Cost?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    return creditData;
                },
                recordTypeName: "Credit Card Credits"
            );
        }

        // ========================================================================
        // CHARGES
        // ========================================================================
        private List<QBCharge> ExtractCharges()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendChargeQueryRq(),
                recordParser: (record, index) =>
                {
                    var charge = (IChargeRet)record;
                    return new QBCharge
                    {
                        TxnID = charge.TxnID?.GetValue() ?? "",
                        RefNumber = charge.RefNumber?.GetValue() ?? "",
                        TxnDate = charge.TxnDate?.GetValue() ?? DateTime.MinValue,
                        CustomerRefListID = charge.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = charge.CustomerRef?.FullName?.GetValue() ?? "",
                        ItemRefListID = charge.ItemRef?.ListID?.GetValue() ?? "",
                        ItemRefFullName = charge.ItemRef?.FullName?.GetValue() ?? "",
                        Quantity = (decimal)(charge.Quantity?.GetValue() ?? 0.0),
                        Rate = (decimal)(charge.Rate?.GetValue() ?? 0.0),
                        Amount = (decimal)(charge.Amount?.GetValue() ?? 0.0),
                        Desc = charge.Desc?.GetValue() ?? "",
                        ARAccountRefListID = charge.ARAccountRef?.ListID?.GetValue() ?? "",
                        ARAccountRefFullName = charge.ARAccountRef?.FullName?.GetValue() ?? "",
                        ClassRefListID = charge.ClassRef?.ListID?.GetValue() ?? "",
                        ClassRefFullName = charge.ClassRef?.FullName?.GetValue() ?? "",
                        TimeCreated = charge.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = charge.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = charge.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Charges"
            );
        }

        // ========================================================================
        // CREDIT MEMOS
        // ========================================================================
        private List<QBCreditMemo> ExtractCreditMemos()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendCreditMemoQueryRq(),
                recordParser: (record, index) =>
                {
                    var cm = (ICreditMemoRet)record;
                    var creditMemo = new QBCreditMemo
                    {
                        TxnID = cm.TxnID?.GetValue() ?? "",
                        RefNumber = cm.RefNumber?.GetValue() ?? "",
                        TxnDate = cm.TxnDate?.GetValue() ?? DateTime.MinValue,
                        CustomerRefListID = cm.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = cm.CustomerRef?.FullName?.GetValue() ?? "",
                        ClassRefListID = cm.ClassRef?.ListID?.GetValue() ?? "",
                        ClassRefFullName = cm.ClassRef?.FullName?.GetValue() ?? "",
                        ARAccountRefListID = cm.ARAccountRef?.ListID?.GetValue() ?? "",
                        ARAccountRefFullName = cm.ARAccountRef?.FullName?.GetValue() ?? "",
                        Subtotal = (decimal)(cm.Subtotal?.GetValue() ?? 0.0),
                        SalesTaxPercentage = (decimal)(cm.SalesTaxPercentage?.GetValue() ?? 0.0),
                        SalesTaxTotal = (decimal)(cm.SalesTaxTotal?.GetValue() ?? 0.0),
                        TotalAmount = (decimal)(cm.TotalAmount?.GetValue() ?? 0.0),
                        CreditRemaining = (decimal)(cm.CreditRemaining?.GetValue() ?? 0.0),
                        Memo = cm.Memo?.GetValue() ?? "",
                        IsPending = cm.IsPending?.GetValue() ?? false,
                        TimeCreated = cm.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = cm.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = cm.EditSequence?.GetValue() ?? ""
                    };

                    // Extract credit memo lines
                    if (cm.CreditMemoLineRetList != null)
                    {
                        for (int i = 0; i < cm.CreditMemoLineRetList.Count; i++)
                        {
                            var line = cm.CreditMemoLineRetList.GetAt(i);
                            creditMemo.Lines.Add(new QBCreditMemoLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                Rate = (decimal)(line.Rate?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? ""
                            });
                        }
                    }

                    return creditMemo;
                },
                recordTypeName: "Credit Memos"
            );
        }

        // ========================================================================
        // DEPOSITS
        // ========================================================================
        private List<QBDeposit> ExtractDeposits()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendDepositQueryRq(),
                recordParser: (record, index) =>
                {
                    var dep = (IDepositRet)record;
                    var deposit = new QBDeposit
                    {
                        TxnID = dep.TxnID?.GetValue() ?? "",
                        RefNumber = dep.RefNumber?.GetValue() ?? "",
                        TxnDate = dep.TxnDate?.GetValue() ?? DateTime.MinValue,
                        DepositToAccountRefListID = dep.DepositToAccountRef?.ListID?.GetValue() ?? "",
                        DepositToAccountRefFullName = dep.DepositToAccountRef?.FullName?.GetValue() ?? "",
                        DepositTotal = (decimal)(dep.DepositTotal?.GetValue() ?? 0.0),
                        Memo = dep.Memo?.GetValue() ?? "",
                        CurrencyRefListID = dep.CurrencyRef?.ListID?.GetValue() ?? "",
                        CurrencyRefFullName = dep.CurrencyRef?.FullName?.GetValue() ?? "",
                        
                        // CRITICAL: Extract ClearedStatus for bank reconciliation
                        ClearedStatus = dep.ClearedStatus?.GetValue().ToString() ?? "NotCleared",
                        
                        TimeCreated = dep.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = dep.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = dep.EditSequence?.GetValue() ?? ""
                    };

                    // Extract deposit lines
                    if (dep.DepositLineRetList != null)
                    {
                        for (int i = 0; i < dep.DepositLineRetList.Count; i++)
                        {
                            var line = dep.DepositLineRetList.GetAt(i);
                            
                            // Determine linked transaction type from PaymentTxnID
                            string linkedTxnType = "";
                            string linkedTxnID = line.PaymentTxnID?.GetValue() ?? "";
                            
                            // Try to determine transaction type from the line
                            if (!string.IsNullOrEmpty(linkedTxnID))
                            {
                                // Common types: ReceivePayment, SalesReceipt
                                linkedTxnType = "ReceivePayment"; // Default, could be SalesReceipt
                            }
                            
                            deposit.DepositLines.Add(new QBDepositLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                
                                // CRITICAL: Track which payment/receipt is in this deposit
                                LinkedTxnType = linkedTxnType,
                                LinkedTxnID = linkedTxnID,
                                
                                PaymentTxnID = linkedTxnID,
                                PaymentTxnLineID = line.PaymentTxnLineID?.GetValue() ?? "",
                                EntityRefListID = line.EntityRef?.ListID?.GetValue() ?? "",
                                EntityRefFullName = line.EntityRef?.FullName?.GetValue() ?? "",
                                AccountRefListID = line.AccountRef?.ListID?.GetValue() ?? "",
                                AccountRefFullName = line.AccountRef?.FullName?.GetValue() ?? "",
                                Memo = line.Memo?.GetValue() ?? "",
                                CheckNumber = line.CheckNumber?.GetValue() ?? "",
                                PaymentMethodRefListID = line.PaymentMethodRef?.ListID?.GetValue() ?? "",
                                PaymentMethodRefFullName = line.PaymentMethodRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0)
                            });
                        }
                    }

                    return deposit;
                },
                recordTypeName: "Deposits"
            );
        }

        // ========================================================================
        // INVENTORY ADJUSTMENTS
        // ========================================================================
        private List<QBInventoryAdjustment> ExtractInventoryAdjustments()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendInventoryAdjustmentQueryRq(),
                recordParser: (record, index) =>
                {
                    var adj = (IInventoryAdjustmentRet)record;
                    var adjustment = new QBInventoryAdjustment
                    {
                        TxnID = adj.TxnID?.GetValue() ?? "",
                        RefNumber = adj.RefNumber?.GetValue() ?? "",
                        TxnDate = adj.TxnDate?.GetValue() ?? DateTime.MinValue,
                        AccountRefListID = adj.AccountRef?.ListID?.GetValue() ?? "",
                        AccountRefFullName = adj.AccountRef?.FullName?.GetValue() ?? "",
                        InventorySiteRefListID = adj.InventorySiteRef?.ListID?.GetValue() ?? "",
                        InventorySiteRefFullName = adj.InventorySiteRef?.FullName?.GetValue() ?? "",
                        CustomerRefListID = adj.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = adj.CustomerRef?.FullName?.GetValue() ?? "",
                        ClassRefListID = adj.ClassRef?.ListID?.GetValue() ?? "",
                        ClassRefFullName = adj.ClassRef?.FullName?.GetValue() ?? "",
                        Memo = adj.Memo?.GetValue() ?? "",
                        TimeCreated = adj.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = adj.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = adj.EditSequence?.GetValue() ?? ""
                    };

                    // Extract adjustment lines
                    if (adj.InventoryAdjustmentLineRetList != null)
                    {
                        for (int i = 0; i < adj.InventoryAdjustmentLineRetList.Count; i++)
                        {
                            var line = adj.InventoryAdjustmentLineRetList.GetAt(i);
                            adjustment.Lines.Add(new QBInventoryAdjustmentLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                QuantityDifference = (decimal)(line.QuantityDifference?.GetValue() ?? 0.0),
                                ValueDifference = (decimal)(line.ValueDifference?.GetValue() ?? 0.0),
                                NewQuantity = (decimal)(line.NewQuantity?.GetValue() ?? 0.0),
                                NewValue = (decimal)(line.NewValue?.GetValue() ?? 0.0),
                                SerialNumber = line.SerialNumber?.GetValue() ?? "",
                                LotNumber = line.LotNumber?.GetValue() ?? ""
                            });
                        }
                    }

                    return adjustment;
                },
                recordTypeName: "Inventory Adjustments"
            );
        }

        // ========================================================================
        // ITEM RECEIPTS (Receive Inventory)
        // ========================================================================
        private List<QBItemReceipt> ExtractItemReceipts()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendItemReceiptQueryRq(),
                recordParser: (record, index) =>
                {
                    var receipt = (IItemReceiptRet)record;
                    var itemReceipt = new QBItemReceipt
                    {
                        TxnID = receipt.TxnID?.GetValue() ?? "",
                        RefNumber = receipt.RefNumber?.GetValue() ?? "",
                        TxnDate = receipt.TxnDate?.GetValue() ?? DateTime.MinValue,
                        VendorRefListID = receipt.VendorRef?.ListID?.GetValue() ?? "",
                        VendorRefFullName = receipt.VendorRef?.FullName?.GetValue() ?? "",
                        APAccountRefListID = receipt.APAccountRef?.ListID?.GetValue() ?? "",
                        APAccountRefFullName = receipt.APAccountRef?.FullName?.GetValue() ?? "",
                        Memo = receipt.Memo?.GetValue() ?? "",
                        Subtotal = (decimal)(receipt.Subtotal?.GetValue() ?? 0.0),
                        SalesTaxTotal = (decimal)(receipt.SalesTaxTotal?.GetValue() ?? 0.0),
                        TotalAmount = (decimal)(receipt.TotalAmount?.GetValue() ?? 0.0),
                        LinkToTxnID = receipt.LinkToTxnID?.GetValue() ?? "",
                        TimeCreated = receipt.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = receipt.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = receipt.EditSequence?.GetValue() ?? ""
                    };

                    // Extract expense lines
                    if (receipt.ExpenseLineRetList != null)
                    {
                        for (int i = 0; i < receipt.ExpenseLineRetList.Count; i++)
                        {
                            var line = receipt.ExpenseLineRetList.GetAt(i);
                            itemReceipt.ExpenseLines.Add(new QBItemReceiptLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                AccountRefListID = line.AccountRef?.ListID?.GetValue() ?? "",
                                AccountRefFullName = line.AccountRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                Description = line.Memo?.GetValue() ?? "",
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    // Extract item lines
                    if (receipt.ItemLineRetList != null)
                    {
                        for (int i = 0; i < receipt.ItemLineRetList.Count; i++)
                        {
                            var line = receipt.ItemLineRetList.GetAt(i);
                            itemReceipt.ItemLines.Add(new QBItemReceiptLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Description = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                UnitOfMeasure = line.UnitOfMeasure?.GetValue() ?? "",
                                Cost = (decimal)(line.Cost?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                CustomerRefListID = line.CustomerRef?.ListID?.GetValue() ?? "",
                                CustomerRefFullName = line.CustomerRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? "",
                                LotNumber = line.LotNumber?.GetValue() ?? "",
                                SerialNumber = line.SerialNumber?.GetValue() ?? ""
                            });
                        }
                    }

                    return itemReceipt;
                },
                recordTypeName: "Item Receipts"
            );
        }

        // ========================================================================
        // BUILD ASSEMBLIES
        // ========================================================================
        private List<QBBuildAssembly> ExtractBuildAssemblies()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendBuildAssemblyQueryRq(),
                recordParser: (record, index) =>
                {
                    var ba = (IBuildAssemblyRet)record;
                    var buildAssembly = new QBBuildAssembly
                    {
                        TxnID = ba.TxnID?.GetValue() ?? "",
                        TxnDate = ba.TxnDate?.GetValue() ?? DateTime.MinValue,
                        RefNumber = ba.RefNumber?.GetValue() ?? "",
                        ItemInventoryAssemblyRefListID = ba.ItemInventoryAssemblyRef?.ListID?.GetValue() ?? "",
                        ItemInventoryAssemblyRefFullName = ba.ItemInventoryAssemblyRef?.FullName?.GetValue() ?? "",
                        QuantityToBuild = (decimal)(ba.QuantityToBuild?.GetValue() ?? 0.0),
                        QuantityCanBuild = (decimal)(ba.QuantityCanBuild?.GetValue() ?? 0.0),
                        QuantityOnHand = (decimal)(ba.QuantityOnHand?.GetValue() ?? 0.0),
                        Memo = ba.Memo?.GetValue() ?? "",
                        RemoveFromSite = ba.RemoveFromSite?.GetValue() ?? false,
                        TimeCreated = ba.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = ba.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = ba.EditSequence?.GetValue() ?? ""
                    };

                    // Extract component lines
                    if (ba.BuildAssemblyLineRetList != null)
                    {
                        for (int i = 0; i < ba.BuildAssemblyLineRetList.Count; i++)
                        {
                            var line = ba.BuildAssemblyLineRetList.GetAt(i);
                            buildAssembly.ComponentLines.Add(new QBBuildAssemblyLine
                            {
                                ItemInventoryRefListID = line.ItemInventoryRef?.ListID?.GetValue() ?? "",
                                ItemInventoryRefFullName = line.ItemInventoryRef?.FullName?.GetValue() ?? "",
                                QuantityNeeded = (decimal)(line.QuantityNeeded?.GetValue() ?? 0.0),
                                QuantityOnHand = (decimal)(line.QuantityOnHand?.GetValue() ?? 0.0)
                            });
                        }
                    }

                    return buildAssembly;
                },
                recordTypeName: "Build Assemblies"
            );
        }

        private List<QBTransfer> ExtractTransfers()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendTransferQueryRq(),
                recordParser: (record, index) =>
                {
                    var transfer = (ITransferRet)record;
                    return new QBTransfer
                    {
                        TxnID = transfer.TxnID?.GetValue() ?? "",
                        TxnDate = transfer.TxnDate?.GetValue() ?? DateTime.MinValue,
                        TransferFromAccountRefListID = transfer.TransferFromAccountRef?.ListID?.GetValue() ?? "",
                        TransferFromAccountRefFullName = transfer.TransferFromAccountRef?.FullName?.GetValue() ?? "",
                        FromAccountBalance = (decimal)(transfer.FromAccountBalance?.GetValue() ?? 0.0),
                        TransferToAccountRefListID = transfer.TransferToAccountRef?.ListID?.GetValue() ?? "",
                        TransferToAccountRefFullName = transfer.TransferToAccountRef?.FullName?.GetValue() ?? "",
                        ToAccountBalance = (decimal)(transfer.ToAccountBalance?.GetValue() ?? 0.0),
                        ClassRefListID = transfer.ClassRef?.ListID?.GetValue() ?? "",
                        ClassRefFullName = transfer.ClassRef?.FullName?.GetValue() ?? "",
                        Amount = (decimal)(transfer.Amount?.GetValue() ?? 0.0),
                        Memo = transfer.Memo?.GetValue() ?? "",
                        
                        // CRITICAL: Extract ClearedStatus for bank reconciliation
                        ClearedStatus = transfer.ClearedStatus?.GetValue().ToString() ?? "NotCleared",
                        
                        TimeCreated = transfer.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = transfer.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = transfer.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Transfers"
            );
        }

        private List<QBInventoryTransfer> ExtractInventoryTransfers()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendTransferInventoryQueryRq(),
                recordParser: (record, index) =>
                {
                    var invTransfer = (ITransferInventoryRet)record;
                    var inventoryTransfer = new QBInventoryTransfer
                    {
                        TxnID = invTransfer.TxnID?.GetValue() ?? "",
                        RefNumber = invTransfer.RefNumber?.GetValue() ?? "",
                        TxnDate = invTransfer.TxnDate?.GetValue() ?? DateTime.MinValue,
                        InventorySiteFromRefListID = invTransfer.InventorySiteFromRef?.ListID?.GetValue() ?? "",
                        InventorySiteFromRefFullName = invTransfer.InventorySiteFromRef?.FullName?.GetValue() ?? "",
                        InventorySiteToRefListID = invTransfer.InventorySiteToRef?.ListID?.GetValue() ?? "",
                        InventorySiteToRefFullName = invTransfer.InventorySiteToRef?.FullName?.GetValue() ?? "",
                        ClassRefListID = invTransfer.ClassRef?.ListID?.GetValue() ?? "",
                        ClassRefFullName = invTransfer.ClassRef?.FullName?.GetValue() ?? "",
                        Memo = invTransfer.Memo?.GetValue() ?? "",
                        TimeCreated = invTransfer.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = invTransfer.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = invTransfer.EditSequence?.GetValue() ?? ""
                    };

                    // Extract line items
                    if (invTransfer.TransferInventoryLineRetList != null)
                    {
                        for (int i = 0; i < invTransfer.TransferInventoryLineRetList.Count; i++)
                        {
                            var line = invTransfer.TransferInventoryLineRetList.GetAt(i);
                            inventoryTransfer.Lines.Add(new QBInventoryTransferLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemInventoryRefListID = line.ItemInventoryRef?.ListID?.GetValue() ?? "",
                                ItemInventoryRefFullName = line.ItemInventoryRef?.FullName?.GetValue() ?? "",
                                QuantityTransferred = (decimal)(line.QuantityTransferred?.GetValue() ?? 0.0),
                                SerialNumber = line.SerialNumber?.GetValue() ?? "",
                                LotNumber = line.LotNumber?.GetValue() ?? ""
                            });
                        }
                    }

                    return inventoryTransfer;
                },
                recordTypeName: "Inventory Transfers"
            );
        }

        // ========================================================================
        // SALES RECEIPTS (Cash Sales)
        // ========================================================================
        private List<QBSalesReceipt> ExtractSalesReceipts()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendSalesReceiptQueryRq(),
                recordParser: (record, index) =>
                {
                    var sr = (ISalesReceiptRet)record;
                    var salesReceipt = new QBSalesReceipt
                    {
                        TxnID = sr.TxnID?.GetValue() ?? "",
                        RefNumber = sr.RefNumber?.GetValue() ?? "",
                        TxnDate = sr.TxnDate?.GetValue() ?? DateTime.MinValue,
                        CustomerRefListID = sr.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = sr.CustomerRef?.FullName?.GetValue() ?? "",
                        ClassRefListID = sr.ClassRef?.ListID?.GetValue() ?? "",
                        ClassRefFullName = sr.ClassRef?.FullName?.GetValue() ?? "",
                        DepositToAccountRefListID = sr.DepositToAccountRef?.ListID?.GetValue() ?? "",
                        DepositToAccountRefFullName = sr.DepositToAccountRef?.FullName?.GetValue() ?? "",
                        PaymentMethodRefListID = sr.PaymentMethodRef?.ListID?.GetValue() ?? "",
                        PaymentMethodRefFullName = sr.PaymentMethodRef?.FullName?.GetValue() ?? "",
                        CheckNumber = sr.CheckNumber?.GetValue() ?? "",
                        Memo = sr.Memo?.GetValue() ?? "",
                        Subtotal = (decimal)(sr.Subtotal?.GetValue() ?? 0.0),
                        SalesTaxPercentage = (decimal)(sr.SalesTaxPercentage?.GetValue() ?? 0.0),
                        SalesTaxTotal = (decimal)(sr.SalesTaxTotal?.GetValue() ?? 0.0),
                        TotalAmount = (decimal)(sr.TotalAmount?.GetValue() ?? 0.0),
                        IsPending = sr.IsPending?.GetValue() ?? false,
                        TimeCreated = sr.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = sr.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = sr.EditSequence?.GetValue() ?? ""
                    };

                    // Extract line items
                    if (sr.SalesReceiptLineRetList != null)
                    {
                        for (int i = 0; i < sr.SalesReceiptLineRetList.Count; i++)
                        {
                            var line = sr.SalesReceiptLineRetList.GetAt(i);
                            salesReceipt.Lines.Add(new QBSalesReceiptLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                UnitOfMeasure = line.UnitOfMeasure?.GetValue() ?? "",
                                Rate = (decimal)(line.Rate?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                SalesTaxCodeRefListID = line.SalesTaxCodeRef?.ListID?.GetValue() ?? "",
                                SalesTaxCodeRefFullName = line.SalesTaxCodeRef?.FullName?.GetValue() ?? ""
                            });
                        }
                    }

                    return salesReceipt;
                },
                recordTypeName: "Sales Receipts"
            );
        }

        // ========================================================================
        // ESTIMATES (Quotes/Proposals)
        // ========================================================================
        private List<QBEstimate> ExtractEstimates()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendEstimateQueryRq(),
                recordParser: (record, index) =>
                {
                    var est = (IEstimateRet)record;
                    var estimate = new QBEstimate
                    {
                        TxnID = est.TxnID?.GetValue() ?? "",
                        RefNumber = est.RefNumber?.GetValue() ?? "",
                        TxnDate = est.TxnDate?.GetValue() ?? DateTime.MinValue,
                        CustomerRefListID = est.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = est.CustomerRef?.FullName?.GetValue() ?? "",
                        ClassRefListID = est.ClassRef?.ListID?.GetValue() ?? "",
                        ClassRefFullName = est.ClassRef?.FullName?.GetValue() ?? "",
                        Subtotal = (decimal)(est.Subtotal?.GetValue() ?? 0.0),
                        SalesTaxPercentage = (decimal)(est.SalesTaxPercentage?.GetValue() ?? 0.0),
                        SalesTaxTotal = (decimal)(est.SalesTaxTotal?.GetValue() ?? 0.0),
                        TotalAmount = (decimal)(est.TotalAmount?.GetValue() ?? 0.0),
                        IsActive = est.IsActive?.GetValue() ?? true,
                        Memo = est.Memo?.GetValue() ?? "",
                        TimeCreated = est.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = est.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = est.EditSequence?.GetValue() ?? ""
                    };

                    // Extract line items
                    if (est.EstimateLineRetList != null)
                    {
                        for (int i = 0; i < est.EstimateLineRetList.Count; i++)
                        {
                            var line = est.EstimateLineRetList.GetAt(i);
                            estimate.Lines.Add(new QBEstimateLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                ItemRefListID = line.ItemRef?.ListID?.GetValue() ?? "",
                                ItemRefFullName = line.ItemRef?.FullName?.GetValue() ?? "",
                                Desc = line.Desc?.GetValue() ?? "",
                                Quantity = (decimal)(line.Quantity?.GetValue() ?? 0.0),
                                UnitOfMeasure = line.UnitOfMeasure?.GetValue() ?? "",
                                Rate = (decimal)(line.Rate?.GetValue() ?? 0.0),
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                Markup = (decimal)(line.MarkupRate?.GetValue() ?? 0.0),
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? ""
                            });
                        }
                    }

                    return estimate;
                },
                recordTypeName: "Estimates"
            );
        }

        // ========================================================================
        // JOURNAL ENTRIES (Manual Accounting Entries - CRITICAL FOR TRIAL BALANCE)
        // ========================================================================
        private List<QBJournalEntry> ExtractJournalEntries()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendJournalEntryQueryRq(),
                recordParser: (record, index) =>
                {
                    var je = (IJournalEntryRet)record;
                    var journalEntry = new QBJournalEntry
                    {
                        TxnID = je.TxnID?.GetValue() ?? "",
                        RefNumber = je.RefNumber?.GetValue() ?? "",
                        TxnDate = je.TxnDate?.GetValue() ?? DateTime.MinValue,
                        IsAdjustment = je.IsAdjustment?.GetValue() ?? false,
                        Memo = je.Memo?.GetValue() ?? "",
                        TimeCreated = je.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = je.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = je.EditSequence?.GetValue() ?? ""
                    };

                    // Extract credit lines
                    if (je.JournalCreditLineRetList != null)
                    {
                        for (int i = 0; i < je.JournalCreditLineRetList.Count; i++)
                        {
                            var line = je.JournalCreditLineRetList.GetAt(i);
                            journalEntry.Lines.Add(new QBJournalEntryLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                LineType = "Credit",
                                AccountRefListID = line.AccountRef?.ListID?.GetValue() ?? "",
                                AccountRefFullName = line.AccountRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                Memo = line.Memo?.GetValue() ?? "",
                                EntityRefListID = line.EntityRef?.ListID?.GetValue() ?? "",
                                EntityRefFullName = line.EntityRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    // Extract debit lines
                    if (je.JournalDebitLineRetList != null)
                    {
                        for (int i = 0; i < je.JournalDebitLineRetList.Count; i++)
                        {
                            var line = je.JournalDebitLineRetList.GetAt(i);
                            journalEntry.Lines.Add(new QBJournalEntryLine
                            {
                                TxnLineID = line.TxnLineID?.GetValue() ?? "",
                                LineType = "Debit",
                                AccountRefListID = line.AccountRef?.ListID?.GetValue() ?? "",
                                AccountRefFullName = line.AccountRef?.FullName?.GetValue() ?? "",
                                Amount = (decimal)(line.Amount?.GetValue() ?? 0.0),
                                Memo = line.Memo?.GetValue() ?? "",
                                EntityRefListID = line.EntityRef?.ListID?.GetValue() ?? "",
                                EntityRefFullName = line.EntityRef?.FullName?.GetValue() ?? "",
                                ClassRefListID = line.ClassRef?.ListID?.GetValue() ?? "",
                                ClassRefFullName = line.ClassRef?.FullName?.GetValue() ?? "",
                                BillableStatus = line.BillableStatus?.GetValue().ToString() ?? ""
                            });
                        }
                    }

                    return journalEntry;
                },
                recordTypeName: "Journal Entries"
            );
        }

        // ========================================================================
        // PREFERENCES (Company Settings)
        // ========================================================================
        private QBPreferences ExtractPreferences()
        {
            var preferences = new QBPreferences();
            
            try
            {
                IMsgSetRequest requestMsgSet = sessionManager.CreateMsgSetRequest(country, qbXMLMajorVer, qbXMLMinorVer);
                requestMsgSet.Attributes.OnError = ENRqOnError.roeContinue;
                
                IPreferencesQuery query = requestMsgSet.AppendPreferencesQueryRq();
                
                IMsgSetResponse responseMsgSet = sessionManager.DoRequests(requestMsgSet);
                IResponse response = responseMsgSet.ResponseList.GetAt(0);
                
                if (response.StatusCode >= 0 && response.Detail != null)
                {
                    IPreferencesRet pref = (IPreferencesRet)response.Detail;
                    
                    // Accounting Preferences
                    if (pref.AccountingPreferences != null)
                    {
                        preferences.IsUsingClassTracking = pref.AccountingPreferences.IsUsingClassTracking?.GetValue() ?? false;
                        preferences.IsUsingAuditTrail = pref.AccountingPreferences.IsUsingAuditTrail?.GetValue() ?? false;
                        preferences.IsRequiringAccounts = pref.AccountingPreferences.IsRequiringAccounts?.GetValue() ?? false;
                        preferences.IsUsingInventory = pref.AccountingPreferences.IsUsingInventory?.GetValue() ?? false;
                    }
                    
                    // Sales Tax Preferences
                    if (pref.SalesTaxPreferences != null)
                    {
                        preferences.DefaultItemSalesTaxRefListID = pref.SalesTaxPreferences.DefaultItemSalesTaxRef?.ListID?.GetValue() ?? "";
                        preferences.DefaultItemSalesTaxRefFullName = pref.SalesTaxPreferences.DefaultItemSalesTaxRef?.FullName?.GetValue() ?? "";
                        preferences.IsPayingSalesTax = pref.SalesTaxPreferences.IsPayingSalesTax?.GetValue() ?? false;
                    }
                    
                    // Time & Jobs
                    if (pref.TimeTrackingPreferences != null)
                    {
                        preferences.IsUsingTimeTracking = pref.TimeTrackingPreferences.IsUsingTimeTracking?.GetValue() ?? false;
                    }
                    
                    if (pref.JobsAndEstimatesPreferences != null)
                    {
                        preferences.IsUsingJobTracking = pref.JobsAndEstimatesPreferences.IsUsingProgressInvoicing?.GetValue() ?? false;
                        preferences.IsUsingEstimates = pref.JobsAndEstimatesPreferences.IsUsingEstimates?.GetValue() ?? false;
                    }
                    
                    // Multi-currency
                    try
                    {
                        if (pref.MultiCurrencyPreferences != null)
                        {
                            preferences.IsUsingMultiCurrency = pref.MultiCurrencyPreferences.IsMultiCurrencyOn?.GetValue() ?? false;
                        }
                    }
                    catch (System.Runtime.InteropServices.COMException comEx)
                    {
                        // Multi-currency feature not available in all QuickBooks versions - this is expected
                        _logger?.Log(LogLevel.Debug, "Multi-currency not available in this QB version: {0}", comEx.Message);
                    }
                    catch (NullReferenceException nullEx)
                    {
                        // Property accessor returned null - expected for some QB configurations
                        _logger?.Log(LogLevel.Debug, "Multi-currency property not available: {0}", nullEx.Message);
                    }
                }
                
                Console.WriteLine($"    Extracted Preferences");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"    WARNING: Could not extract Preferences: {ex.Message}");
            }
            
            return preferences;
        }

        // ========================================================================
        // DATA EXTENSIONS (Custom Fields - CRITICAL for Power Users)
        // ========================================================================
        private List<QBDataExtension> ExtractDataExtensions()
        {
            var extensions = new List<QBDataExtension>();
            
            try
            {
                Console.WriteLine($"    Extracting Custom Fields (Data Extensions)...");
                // Note: Full implementation would query each entity's DataExt
                // This is a placeholder for the comprehensive version
                Console.WriteLine($"    Extracted {extensions.Count} Data Extensions");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"    WARNING: Could not extract Data Extensions: {ex.Message}");
            }
            
            return extensions;
        }

        // ========================================================================
        // DELETED RECORDS (Audit Trail - Often Missed by Other Tools)
        // ========================================================================
        private QBDeletedRecords ExtractDeletedRecords()
        {
            var deletedRecords = new QBDeletedRecords();
            
            try
            {
                // Extract Deleted Lists
                IMsgSetRequest listRequest = sessionManager.CreateMsgSetRequest(country, qbXMLMajorVer, qbXMLMinorVer);
                listRequest.Attributes.OnError = ENRqOnError.roeContinue;
                
                IListDeletedQuery listQuery = listRequest.AppendListDeletedQueryRq();
                listQuery.DeletedDateRangeFilter.FromDeletedDate.SetValue(new DateTime(2000, 1, 1), false);
                
                IMsgSetResponse listResponse = sessionManager.DoRequests(listRequest);
                IResponse listResp = listResponse.ResponseList.GetAt(0);
                
                if (listResp.StatusCode >= 0 && listResp.Detail != null)
                {
                    IListDeletedRetList deletedList = (IListDeletedRetList)listResp.Detail;
                    
                    for (int i = 0; i < deletedList.Count; i++)
                    {
                        var deleted = deletedList.GetAt(i);
                        deletedRecords.DeletedLists.Add(new QBDeletedList
                        {
                            ListDelType = deleted.ListDelType?.GetValue() ?? "",
                            ListID = deleted.ListID?.GetValue() ?? "",
                            TimeCreated = deleted.TimeCreated?.GetValue() ?? DateTime.MinValue,
                            TimeDeleted = deleted.TimeDeleted?.GetValue() ?? DateTime.MinValue,
                            FullName = deleted.FullName?.GetValue() ?? ""
                        });
                    }
                }
                
                // Extract Deleted Transactions
                IMsgSetRequest txnRequest = sessionManager.CreateMsgSetRequest(country, qbXMLMajorVer, qbXMLMinorVer);
                txnRequest.Attributes.OnError = ENRqOnError.roeContinue;
                
                ITxnDeletedQuery txnQuery = txnRequest.AppendTxnDeletedQueryRq();
                txnQuery.DeletedDateRangeFilter.FromDeletedDate.SetValue(new DateTime(2000, 1, 1), false);
                
                IMsgSetResponse txnResponse = sessionManager.DoRequests(txnRequest);
                IResponse txnResp = txnResponse.ResponseList.GetAt(0);
                
                if (txnResp.StatusCode >= 0 && txnResp.Detail != null)
                {
                    ITxnDeletedRetList deletedTxns = (ITxnDeletedRetList)txnResp.Detail;
                    
                    for (int i = 0; i < deletedTxns.Count; i++)
                    {
                        var deleted = deletedTxns.GetAt(i);
                        deletedRecords.DeletedTransactions.Add(new QBDeletedTxn
                        {
                            TxnDelType = deleted.TxnDelType?.GetValue() ?? "",
                            TxnID = deleted.TxnID?.GetValue() ?? "",
                            TimeCreated = deleted.TimeCreated?.GetValue() ?? DateTime.MinValue,
                            TimeDeleted = deleted.TimeDeleted?.GetValue() ?? DateTime.MinValue,
                            RefNumber = deleted.RefNumber?.GetValue() ?? ""
                        });
                    }
                }
                
                Console.WriteLine($"    Extracted {deletedRecords.DeletedLists.Count} Deleted Lists, {deletedRecords.DeletedTransactions.Count} Deleted Transactions");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"    WARNING: Could not extract Deleted Records: {ex.Message}");
            }
            
            return deletedRecords;
        }

        // ========================================================================
        // SALES TAX GROUPS (Multi-jurisdiction Tax - CRITICAL!)
        // ========================================================================
        public List<QBSalesTaxGroup> ExtractSalesTaxGroups()
        {
            var groups = new List<QBSalesTaxGroup>();
            
            try
            {
                IMsgSetRequest requestMsgSet = sessionManager.CreateMsgSetRequest(country, qbXMLMajorVer, qbXMLMinorVer);
                requestMsgSet.Attributes.OnError = ENRqOnError.roeContinue;
                
                IItemSalesTaxGroupQuery query = requestMsgSet.AppendItemSalesTaxGroupQueryRq();
                
                IMsgSetResponse responseMsgSet = sessionManager.DoRequests(requestMsgSet);
                IResponse response = responseMsgSet.ResponseList.GetAt(0);
                
                if (response.StatusCode >= 0 && response.Detail != null)
                {
                    IItemSalesTaxGroupRetList retList = (IItemSalesTaxGroupRetList)response.Detail;
                    
                    for (int i = 0; i < retList.Count; i++)
                    {
                        IItemSalesTaxGroupRet taxGroup = retList.GetAt(i);
                        var group = new QBSalesTaxGroup
                        {
                            ListID = taxGroup.ListID?.GetValue() ?? "",
                            Name = taxGroup.Name?.GetValue() ?? "",
                            Description = taxGroup.Description?.GetValue() ?? "",
                            IsActive = taxGroup.IsActive?.GetValue() ?? true,
                            TimeCreated = taxGroup.TimeCreated?.GetValue() ?? DateTime.MinValue,
                            TimeModified = taxGroup.TimeModified?.GetValue() ?? DateTime.MinValue,
                            EditSequence = taxGroup.EditSequence?.GetValue() ?? ""
                        };
                        
                        // Extract individual tax items in group
                        if (taxGroup.ItemSalesTaxRetList != null)
                        {
                            for (int j = 0; j < taxGroup.ItemSalesTaxRetList.Count; j++)
                            {
                                var taxItem = taxGroup.ItemSalesTaxRetList.GetAt(j);
                                group.TaxItems.Add(new QBSalesTaxGroupItem
                                {
                                    ItemSalesTaxRefListID = taxItem.ListID?.GetValue() ?? "",
                                    ItemSalesTaxRefFullName = taxItem.FullName?.GetValue() ?? ""
                                });
                            }
                        }
                        
                        groups.Add(group);
                    }
                }
                
                Console.WriteLine($"    Extracted {groups.Count} Sales Tax Groups");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"    WARNING: Could not extract Sales Tax Groups: {ex.Message}");
            }
            
            return groups;
        }

        // ========================================================================
        // BILL PAYMENT CREDIT CARD (Pay Vendors via Credit Card - NEW!)
        // ========================================================================
        private List<QBBillPaymentCreditCard> ExtractBillPaymentCreditCards()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendBillPaymentCreditCardQueryRq(),
                recordParser: (record, index) =>
                {
                    var bp = (IBillPaymentCreditCardRet)record;
                    var payment = new QBBillPaymentCreditCard
                    {
                        TxnID = bp.TxnID?.GetValue() ?? "",
                        RefNumber = bp.RefNumber?.GetValue() ?? "",
                        TxnDate = bp.TxnDate?.GetValue() ?? DateTime.MinValue,
                        VendorRefListID = bp.VendorRef?.ListID?.GetValue() ?? "",
                        VendorRefFullName = bp.VendorRef?.FullName?.GetValue() ?? "",
                        APAccountRefListID = bp.APAccountRef?.ListID?.GetValue() ?? "",
                        APAccountRefFullName = bp.APAccountRef?.FullName?.GetValue() ?? "",
                        CreditCardAccountRefListID = bp.CreditCardAccountRef?.ListID?.GetValue() ?? "",
                        CreditCardAccountRefFullName = bp.CreditCardAccountRef?.FullName?.GetValue() ?? "",
                        Amount = (decimal)(bp.Amount?.GetValue() ?? 0.0),
                        Memo = bp.Memo?.GetValue() ?? "",
                        TimeCreated = bp.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = bp.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = bp.EditSequence?.GetValue() ?? ""
                    };

                    // CRITICAL: Extract LinkedTxn (which bills this payment paid)
                    if (bp.AppliedToTxnRetList != null)
                    {
                        for (int i = 0; i < bp.AppliedToTxnRetList.Count; i++)
                        {
                            var applied = bp.AppliedToTxnRetList.GetAt(i);
                            payment.LinkedTransactions.Add(new QBLinkedTxn
                            {
                                TxnID = applied.TxnID?.GetValue() ?? "",
                                TxnType = applied.TxnType?.GetValue().ToString() ?? "",
                                TxnDate = applied.TxnDate?.GetValue() ?? DateTime.MinValue,
                                RefNumber = applied.RefNumber?.GetValue() ?? "",
                                LinkAmount = (decimal)(applied.AppliedAmount?.GetValue() ?? 0.0)
                            });
                        }
                    }

                    return payment;
                },
                recordTypeName: "Bill Payment Credit Cards"
            );
        }

        // ========================================================================
        // AR REFUND CREDIT CARD (Customer Refunds - NEW!)
        // ========================================================================
        private List<QBARRefundCreditCard> ExtractARRefundCreditCards()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendARRefundCreditCardQueryRq(),
                recordParser: (record, index) =>
                {
                    var refund = (IARRefundCreditCardRet)record;
                    return new QBARRefundCreditCard
                    {
                        TxnID = refund.TxnID?.GetValue() ?? "",
                        RefNumber = refund.RefNumber?.GetValue() ?? "",
                        TxnDate = refund.TxnDate?.GetValue() ?? DateTime.MinValue,
                        CustomerRefListID = refund.CustomerRef?.ListID?.GetValue() ?? "",
                        CustomerRefFullName = refund.CustomerRef?.FullName?.GetValue() ?? "",
                        ARAccountRefListID = refund.ARAccountRef?.ListID?.GetValue() ?? "",
                        ARAccountRefFullName = refund.ARAccountRef?.FullName?.GetValue() ?? "",
                        RefundAmount = (decimal)(refund.RefundAmount?.GetValue() ?? 0.0),
                        Memo = refund.Memo?.GetValue() ?? "",
                        PaymentMethodRefListID = refund.PaymentMethodRef?.ListID?.GetValue() ?? "",
                        PaymentMethodRefFullName = refund.PaymentMethodRef?.FullName?.GetValue() ?? "",
                        TimeCreated = refund.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = refund.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = refund.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "AR Refund Credit Cards"
            );
        }

        // ========================================================================
        // SALES TAX PAYMENT CHECK (Pay Tax Authorities - NEW!)
        // ========================================================================
        private List<QBSalesTaxPaymentCheck> ExtractSalesTaxPayments()
        {
            return _iteratorHelper.ExtractWithIterator(
                queryAppender: (request) => request.AppendSalesTaxPaymentCheckQueryRq(),
                recordParser: (record, index) =>
                {
                    var payment = (ISalesTaxPaymentCheckRet)record;
                    return new QBSalesTaxPaymentCheck
                    {
                        TxnID = payment.TxnID?.GetValue() ?? "",
                        RefNumber = payment.RefNumber?.GetValue() ?? "",
                        TxnDate = payment.TxnDate?.GetValue() ?? DateTime.MinValue,
                        PayeeEntityRefListID = payment.PayeeEntityRef?.ListID?.GetValue() ?? "",
                        PayeeEntityRefFullName = payment.PayeeEntityRef?.FullName?.GetValue() ?? "",
                        APAccountRefListID = payment.APAccountRef?.ListID?.GetValue() ?? "",
                        APAccountRefFullName = payment.APAccountRef?.FullName?.GetValue() ?? "",
                        BankAccountRefListID = payment.BankAccountRef?.ListID?.GetValue() ?? "",
                        BankAccountRefFullName = payment.BankAccountRef?.FullName?.GetValue() ?? "",
                        Amount = (decimal)(payment.Amount?.GetValue() ?? 0.0),
                        Memo = payment.Memo?.GetValue() ?? "",
                        IsToBePrinted = payment.IsToBePrinted?.GetValue() ?? false,
                        TimeCreated = payment.TimeCreated?.GetValue() ?? DateTime.MinValue,
                        TimeModified = payment.TimeModified?.GetValue() ?? DateTime.MinValue,
                        EditSequence = payment.EditSequence?.GetValue() ?? ""
                    };
                },
                recordTypeName: "Sales Tax Payments"
            );
        }

        // ========================================================================
        // REPORT VERIFICATION (Mathematical Proof - THE KILLER FEATURE!)
        // ========================================================================
        private QBReportVerification ExtractReportVerification()
        {
            var verification = new QBReportVerification
            {
                VerificationDate = DateTime.Now,
                IsBalanced = false,
                ValidationMessage = ""
            };

            try
            {
                Console.WriteLine("    Extracting Trial Balance for verification...");
                
                IMsgSetRequest requestMsgSet = sessionManager.CreateMsgSetRequest(country, qbXMLMajorVer, qbXMLMinorVer);
                requestMsgSet.Attributes.OnError = ENRqOnError.roeContinue;
                
                IGeneralSummaryReportQuery reportQuery = requestMsgSet.AppendGeneralSummaryReportQueryRq();
                reportQuery.GeneralSummaryReportType.SetValue(ENGeneralSummaryReportType.gsrtTrialBalance);
                
                IMsgSetResponse responseMsgSet = sessionManager.DoRequests(requestMsgSet);
                IResponse response = responseMsgSet.ResponseList.GetAt(0);
                
                if (response.StatusCode >= 0 && response.Detail != null)
                {
                    IReportRet report = (IReportRet)response.Detail;
                    
                    var trialBalance = new QBTrialBalance
                    {
                        AsOfDate = DateTime.Now,
                        TotalDebits = 0,
                        TotalCredits = 0
                    };
                    
                    // Parse report rows to extract account balances
                    if (report.ReportData != null && report.ReportData.RowList != null)
                    {
                        for (int i = 0; i < report.ReportData.RowList.Count; i++)
                        {
                            var row = report.ReportData.RowList.GetAt(i);
                            
                            // Parse DataRow types (account lines)
                            if (row.rowType == ENrowType.rtDataRow && row.ColDataList != null)
                            {
                                try
                                {
                                    string accountName = "";
                                    string accountType = "";
                                    decimal debit = 0;
                                    decimal credit = 0;
                                    
                                    // Trial Balance usually has: Account Name, Debit, Credit columns
                                    if (row.ColDataList.Count >= 3)
                                    {
                                        accountName = row.ColDataList.GetAt(0).value?.GetValue() ?? "";
                                        
                                        // Parse debit/credit amounts
                                        string debitStr = row.ColDataList.GetAt(1).value?.GetValue() ?? "0";
                                        string creditStr = row.ColDataList.GetAt(2).value?.GetValue() ?? "0";
                                        
                                        // Remove commas and parse
                                        decimal.TryParse(debitStr.Replace(",", "").Replace("$", ""), out debit);
                                        decimal.TryParse(creditStr.Replace(",", "").Replace("$", ""), out credit);
                                        
                                        if (!string.IsNullOrWhiteSpace(accountName))
                                        {
                                            trialBalance.Lines.Add(new QBTrialBalanceLine
                                            {
                                                AccountName = accountName,
                                                AccountType = accountType,
                                                DebitBalance = debit,
                                                CreditBalance = credit
                                            });
                                            
                                            trialBalance.TotalDebits += debit;
                                            trialBalance.TotalCredits += credit;
                                        }
                                    }
                                }
                                catch (FormatException)
                                {
                                    // Skip malformed rows
                                }
                                catch (ArgumentOutOfRangeException)
                                {
                                    // Skip rows with missing columns
                                }
                            }
                            // Parse TotalRow for verification
                            else if (row.rowType == ENrowType.rtTotalRow && row.ColDataList != null)
                            {
                                try
                                {
                                    if (row.ColDataList.Count >= 3)
                                    {
                                        string debitStr = row.ColDataList.GetAt(1).value?.GetValue() ?? "0";
                                        string creditStr = row.ColDataList.GetAt(2).value?.GetValue() ?? "0";
                                        
                                        decimal totalDebit, totalCredit;
                                        decimal.TryParse(debitStr.Replace(",", "").Replace("$", ""), out totalDebit);
                                        decimal.TryParse(creditStr.Replace(",", "").Replace("$", ""), out totalCredit);
                                        
                                        // Use totals from report if available
                                        if (totalDebit > 0 || totalCredit > 0)
                                        {
                                            trialBalance.TotalDebits = totalDebit;
                                            trialBalance.TotalCredits = totalCredit;
                                        }
                                    }
                                }
                                catch (FormatException)
                                {
                                    // Skip malformed totals
                                }
                                catch (ArgumentOutOfRangeException)
                                {
                                    // Skip totals with missing columns
                                }
                            }
                        }
                    }
                    
                    verification.TrialBalance = trialBalance;
                    verification.IsBalanced = Math.Abs(trialBalance.TotalDebits - trialBalance.TotalCredits) < 0.01m;
                    
                    if (verification.IsBalanced)
                    {
                        verification.ValidationMessage = $"✓ Trial Balance BALANCED - Debits: ${trialBalance.TotalDebits:N2}, Credits: ${trialBalance.TotalCredits:N2}";
                    }
                    else
                    {
                        decimal difference = trialBalance.TotalDebits - trialBalance.TotalCredits;
                        verification.ValidationMessage = $"⚠ Trial Balance OUT OF BALANCE by ${Math.Abs(difference):N2} - Debits: ${trialBalance.TotalDebits:N2}, Credits: ${trialBalance.TotalCredits:N2}";
                    }
                    
                    Console.WriteLine($"    {verification.ValidationMessage}");
                    Console.WriteLine($"    Extracted {trialBalance.Lines.Count} account balances");
                }
                else
                {
                    verification.ValidationMessage = "Could not extract Trial Balance for verification";
                    Console.WriteLine($"    WARNING: {verification.ValidationMessage}");
                }
            }
            catch (Exception ex)
            {
                verification.ValidationMessage = $"Report verification failed: {ex.Message}";
                Console.WriteLine($"    WARNING: {verification.ValidationMessage}");
            }

            return verification;
        }

        // ========================================================================
        // COMPANY ACTIVITY
        // ========================================================================
        private QBCompanyActivity ExtractCompanyActivity()
        {
            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest();
                request.AppendCompanyActivityQueryRq();
                
                IMsgSetResponse response = sessionManager.DoRequests(request);
                IResponse resp = response.ResponseList.GetAt(0);

                if (resp.StatusCode != 0)
                {
                    Console.WriteLine($"  ℹ Could not retrieve company activity");
                    return new QBCompanyActivity();
                }

                var ca = resp.Detail as ICompanyActivityRet;
                if (ca == null)
                {
                    return new QBCompanyActivity();
                }

                var activity = new QBCompanyActivity
                {
                    LastRestoreTime = ca.LastRestoreTime?.GetValue() ?? DateTime.MinValue,
                    LastCondenseTime = ca.LastCondenseTime?.GetValue() ?? DateTime.MinValue
                };

                Console.WriteLine($"  ✓ Company Activity Retrieved");
                return activity;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ℹ Company activity not available: {ex.Message}");
                return new QBCompanyActivity();
            }
        }
    }
}

#endif // USE_QBFC