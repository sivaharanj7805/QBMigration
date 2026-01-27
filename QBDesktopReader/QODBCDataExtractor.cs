using System;
using System.Collections.Generic;
using System.Data;
using System.Data.Odbc;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace QBDesktopExtractor
{
    /// <summary>
    /// QuickBooks data extractor using QODBC driver
    /// Does NOT require QuickBooks SDK installation
    /// Requires: QODBC Driver (free for read operations)
    /// Download: https://qodbc.com/qodbc-downloads/
    /// </summary>
    public class QODBCDataExtractor : IDataExtractor
    {
        private readonly IRedactingLogger _logger;
        private OdbcConnection _connection;
        private bool _disposed = false;
        private DateTime? _incrementalFromDate = null;
        private string _qbVersion = "QuickBooks (QODBC)";
        private QBCompanyInfo _companyInfo;

        public string BackendName => "QODBC";
        public bool IsAvailable => DataExtractorFactory.IsQODBCAvailable();
        public ExtractionRunSummary RunSummary { get; private set; }
        public bool ContinueOnEntityError { get; set; } = true;

        // QODBC connection string patterns
        private static readonly string[] ConnectionStringPatterns = new[]
        {
            "DSN=QuickBooks Data;",
            "Driver={QODBC Driver for QuickBooks};",
            "Driver={QODBC Driver for QuickBooks Online Edition};",
            "Driver={QRemote for QuickBooks};",
        };

        public QODBCDataExtractor(IRedactingLogger logger = null)
        {
            _logger = logger;
        }

        public void Connect(string companyFilePath = null)
        {
            if (_connection != null && _connection.State == ConnectionState.Open)
            {
                _logger?.Log(LogLevel.Warning, "Already connected to QuickBooks via QODBC");
                return;
            }

            _logger?.Log(LogLevel.Info, "Connecting to QuickBooks via QODBC...");

            // Try different connection string patterns
            Exception lastException = null;
            foreach (var pattern in ConnectionStringPatterns)
            {
                try
                {
                    string connString = pattern;
                    if (!string.IsNullOrEmpty(companyFilePath))
                    {
                        connString += $"DFQ={companyFilePath};";
                    }

                    _connection = new OdbcConnection(connString);
                    _connection.Open();

                    _logger?.Log(LogLevel.Info, "Connected via: {0}", pattern);

                    // Load company info on successful connection
                    LoadCompanyInfo();
                    return;
                }
                catch (Exception ex)
                {
                    lastException = ex;
                    _logger?.Log(LogLevel.Debug, "Connection failed with pattern '{0}': {1}",
                        pattern, ex.Message);
                }
            }

            throw new InvalidOperationException(
                "Could not connect to QuickBooks via QODBC.\n\n" +
                "Ensure:\n" +
                "1. QODBC driver is installed (https://qodbc.com/qodbc-downloads/)\n" +
                "2. QuickBooks Desktop is running and logged into a company file\n" +
                "3. QODBC is configured (run QODBC Setup utility)\n\n" +
                $"Last error: {lastException?.Message}");
        }

        public void Disconnect()
        {
            if (_connection != null)
            {
                try
                {
                    if (_connection.State == ConnectionState.Open)
                    {
                        _connection.Close();
                    }
                    _connection.Dispose();
                    _connection = null;
                    _logger?.Log(LogLevel.Info, "Disconnected from QuickBooks");
                }
                catch (Exception ex)
                {
                    _logger?.Log(LogLevel.Warning, "Error during disconnect: {0}", ex.Message);
                }
            }
        }

        private void LoadCompanyInfo()
        {
            try
            {
                using (var cmd = new OdbcCommand("SELECT * FROM Company", _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    if (reader.Read())
                    {
                        _companyInfo = new QBCompanyInfo
                        {
                            CompanyName = GetString(reader, "CompanyName"),
                            LegalCompanyName = GetString(reader, "LegalCompanyName"),
                            Address = GetString(reader, "CompanyAddress_Addr1"),
                            City = GetString(reader, "CompanyAddress_City"),
                            State = GetString(reader, "CompanyAddress_State"),
                            PostalCode = GetString(reader, "CompanyAddress_PostalCode"),
                            Country = GetString(reader, "CompanyAddress_Country"),
                            Phone = GetString(reader, "Phone"),
                            Fax = GetString(reader, "Fax"),
                            Email = GetString(reader, "Email"),
                            CompanyFilePath = "[REDACTED]",
                            FiscalYearStartMonth = GetString(reader, "FirstMonthFiscalYear")
                        };

                        _logger?.Log(LogLevel.Info, "Company: {0}", _companyInfo.CompanyName);
                    }
                }

                // Get QB version from QODBC
                try
                {
                    using (var cmd = new OdbcCommand("sp_version", _connection))
                    using (var reader = cmd.ExecuteReader())
                    {
                        if (reader.Read())
                        {
                            _qbVersion = $"QuickBooks {GetString(reader, 0)} (QODBC)";
                        }
                    }
                }
                catch
                {
                    _qbVersion = "QuickBooks Desktop (QODBC)";
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Could not load company info: {0}", ex.Message);
                _companyInfo = new QBCompanyInfo { CompanyName = "Unknown Company" };
            }
        }

        public QBCompanyInfo GetCompanyInfo()
        {
            return _companyInfo ?? new QBCompanyInfo { CompanyName = "Not Connected" };
        }

        public string GetQBVersion()
        {
            return _qbVersion;
        }

        public void SetIncrementalSyncDate(DateTime fromDate)
        {
            _incrementalFromDate = fromDate;
            _logger?.Log(LogLevel.Info, "INCREMENTAL SYNC MODE: Extracting only records modified since {0:yyyy-MM-dd}", fromDate);
        }

        #region Extraction Methods

        public QBExtractedData ExtractAllData()
        {
            EnsureConnected();

            _logger?.Log(LogLevel.Info, "Starting QuickBooks data extraction via QODBC");

            RunSummary = new ExtractionRunSummary
            {
                SessionId = Guid.NewGuid().ToString(),
                StartedAt = DateTime.UtcNow,
                IsIncremental = _incrementalFromDate.HasValue,
                IncrementalFromDate = _incrementalFromDate
            };

            var data = new QBExtractedData
            {
                ExtractedAt = DateTime.Now,
                SessionID = RunSummary.SessionId,
                Company = _companyInfo,
                QBVersion = _qbVersion
            };

            // Extract all entities
            data.Accounts = SafeExtract("Accounts", ExtractAccounts);
            data.Customers = SafeExtract("Customers", ExtractCustomers);
            data.Vendors = SafeExtract("Vendors", ExtractVendors);
            data.Employees = SafeExtract("Employees", ExtractEmployees);
            data.Items = SafeExtract("Items", ExtractItems);
            data.Classes = SafeExtract("Classes", ExtractClasses);
            data.Invoices = SafeExtract("Invoices", ExtractInvoices);
            data.Bills = SafeExtract("Bills", ExtractBills);
            data.Checks = SafeExtract("Checks", ExtractChecks);
            data.JournalEntries = SafeExtract("JournalEntries", ExtractJournalEntries);
            data.Deposits = SafeExtract("Deposits", ExtractDeposits);
            data.CreditMemos = SafeExtract("CreditMemos", ExtractCreditMemos);
            data.SalesReceipts = SafeExtract("SalesReceipts", ExtractSalesReceipts);
            data.Estimates = SafeExtract("Estimates", ExtractEstimates);
            data.PurchaseOrders = SafeExtract("PurchaseOrders", ExtractPurchaseOrders);
            data.PaymentMethods = SafeExtract("PaymentMethods", ExtractPaymentMethods);
            data.Terms = SafeExtract("Terms", ExtractTerms);

            RunSummary.CompletedAt = DateTime.UtcNow;

            _logger?.Log(LogLevel.Info, "QODBC extraction complete: {0} entities, {1} records",
                RunSummary.TotalEntitiesSucceeded, RunSummary.TotalRecordsExtracted);

            return data;
        }

        public async Task<RunManifest> ExtractAllDataToNDJSONAsync(
            string outputDirectory,
            string sessionId,
            string configHash = null,
            CancellationToken ct = default)
        {
            EnsureConnected();

            var startTime = DateTime.UtcNow;
            _logger?.Log(LogLevel.Info, "Starting NDJSON extraction via QODBC to: {0}", outputDirectory);

            RunSummary = new ExtractionRunSummary
            {
                SessionId = sessionId,
                StartedAt = startTime,
                IsIncremental = _incrementalFromDate.HasValue,
                IncrementalFromDate = _incrementalFromDate,
                ConfigHash = configHash
            };

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
                writer.Manifest.QBVersion = _qbVersion;
                writer.Manifest.CompanyFingerprint = ComputeCompanyFingerprint(_companyInfo);
                writer.Manifest.ConfigHash = configHash;
                writer.Manifest.IsIncremental = _incrementalFromDate.HasValue;
                writer.Manifest.IncrementalFromDate = _incrementalFromDate;

                // Extract all entities
                await ExtractToNDJSONAsync("Accounts", ExtractAccounts, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Customers", ExtractCustomers, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Vendors", ExtractVendors, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Employees", ExtractEmployees, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Items", ExtractItems, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Classes", ExtractClasses, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Invoices", ExtractInvoices, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Bills", ExtractBills, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Checks", ExtractChecks, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("JournalEntries", ExtractJournalEntries, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Deposits", ExtractDeposits, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("CreditMemos", ExtractCreditMemos, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("SalesReceipts", ExtractSalesReceipts, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Estimates", ExtractEstimates, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("PurchaseOrders", ExtractPurchaseOrders, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("PaymentMethods", ExtractPaymentMethods, writer, checkpoint, checkpointState, ct);
                await ExtractToNDJSONAsync("Terms", ExtractTerms, writer, checkpoint, checkpointState, ct);

                // Write errors
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

                await writer.FinalizeAsync(metrics, ct);

                RunSummary.CompletedAt = DateTime.UtcNow;
                checkpoint.Clear();

                _logger?.Log(LogLevel.Info, "QODBC NDJSON extraction complete: {0} entities, {1} records",
                    RunSummary.TotalEntitiesSucceeded, RunSummary.TotalRecordsExtracted);

                return writer.Manifest;
            }
            finally
            {
                writer?.Dispose();
            }
        }

        private async Task ExtractToNDJSONAsync<T>(
            string entityName,
            Func<List<T>> extractor,
            NDJSONWriter writer,
            ExtractionCheckpoint checkpoint,
            CheckpointState checkpointState,
            CancellationToken ct) where T : class
        {
            if (checkpoint.IsEntityComplete(checkpointState, entityName))
            {
                _logger?.Log(LogLevel.Info, "Skipping {0} - already extracted", entityName);
                RunSummary.EntityResults.Add(new EntityExtractionResult
                {
                    EntityName = entityName,
                    Skipped = true
                });
                return;
            }

            var records = SafeExtract(entityName, extractor);

            if (records.Count > 0)
            {
                await writer.WriteEntityBatchAsync(entityName.ToLowerInvariant(), records, ct);
            }

            checkpointState.CompletedEntities.Add(entityName);
            checkpointState.TotalRecordsExtracted += records.Count;
            checkpoint.SaveAfterEntity(checkpointState);
        }

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

                _logger?.Log(LogLevel.Info, "Extracted {0}: {1} records in {2:F1}s",
                    entityName, result.RecordCount, sw.Elapsed.TotalSeconds);

                return records ?? new List<T>();
            }
            catch (Exception ex)
            {
                sw.Stop();

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

        #endregion

        #region Entity Extractors

        private List<QBAccount> ExtractAccounts()
        {
            var accounts = new List<QBAccount>();
            string sql = "SELECT * FROM Account";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            using (var cmd = new OdbcCommand(sql, _connection))
            using (var reader = cmd.ExecuteReader())
            {
                while (reader.Read())
                {
                    accounts.Add(new QBAccount
                    {
                        ListID = GetString(reader, "ListID") ?? "",
                        Name = GetString(reader, "Name"),
                        FullName = GetString(reader, "FullName"),
                        AccountType = GetString(reader, "AccountType"),
                        AccountNumber = GetString(reader, "AccountNumber"),
                        Desc = GetString(reader, "Desc"),
                        Balance = GetDecimal(reader, "Balance"),
                        TotalBalance = GetDecimal(reader, "TotalBalance"),
                        IsActive = GetBool(reader, "IsActive"),
                        ParentRefListID = GetString(reader, "ParentRef_ListID"),
                        ParentRefFullName = GetString(reader, "ParentRef_FullName"),
                        CurrencyRefListID = GetString(reader, "CurrencyRef_ListID"),
                        TimeCreated = GetDateTime(reader, "TimeCreated"),
                        TimeModified = GetDateTime(reader, "TimeModified")
                    });
                }
            }

            return accounts;
        }

        private List<QBCustomer> ExtractCustomers()
        {
            var customers = new List<QBCustomer>();
            string sql = "SELECT * FROM Customer";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            using (var cmd = new OdbcCommand(sql, _connection))
            using (var reader = cmd.ExecuteReader())
            {
                while (reader.Read())
                {
                    customers.Add(new QBCustomer
                    {
                        ListID = GetString(reader, "ListID") ?? "",
                        Name = GetString(reader, "Name"),
                        FullName = GetString(reader, "FullName"),
                        CompanyName = GetString(reader, "CompanyName"),
                        FirstName = GetString(reader, "FirstName"),
                        LastName = GetString(reader, "LastName"),
                        Phone = GetString(reader, "Phone"),
                        Email = GetString(reader, "Email"),
                        Balance = GetDecimal(reader, "Balance"),
                        TotalBalance = GetDecimal(reader, "TotalBalance"),
                        IsActive = GetBool(reader, "IsActive"),
                        BillAddressAddr1 = GetString(reader, "BillAddress_Addr1"),
                        BillAddressCity = GetString(reader, "BillAddress_City"),
                        BillAddressState = GetString(reader, "BillAddress_State"),
                        BillAddressPostalCode = GetString(reader, "BillAddress_PostalCode"),
                        ShipAddressAddr1 = GetString(reader, "ShipAddress_Addr1"),
                        ShipAddressCity = GetString(reader, "ShipAddress_City"),
                        ShipAddressState = GetString(reader, "ShipAddress_State"),
                        ShipAddressPostalCode = GetString(reader, "ShipAddress_PostalCode"),
                        TimeCreated = GetDateTime(reader, "TimeCreated"),
                        TimeModified = GetDateTime(reader, "TimeModified")
                    });
                }
            }

            return customers;
        }

        private List<QBVendor> ExtractVendors()
        {
            var vendors = new List<QBVendor>();
            string sql = "SELECT * FROM Vendor";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            using (var cmd = new OdbcCommand(sql, _connection))
            using (var reader = cmd.ExecuteReader())
            {
                while (reader.Read())
                {
                    vendors.Add(new QBVendor
                    {
                        ListID = GetString(reader, "ListID"),
                        Name = GetString(reader, "Name"),
                        CompanyName = GetString(reader, "CompanyName"),
                        Phone = GetString(reader, "Phone"),
                        Email = GetString(reader, "Email"),
                        Balance = GetDecimal(reader, "Balance"),
                        IsActive = GetBool(reader, "IsActive"),
                        VendorAddressAddr1 = GetString(reader, "VendorAddress_Addr1"),
                        VendorAddressCity = GetString(reader, "VendorAddress_City"),
                        VendorAddressState = GetString(reader, "VendorAddress_State"),
                        VendorAddressPostalCode = GetString(reader, "VendorAddress_PostalCode"),
                        TimeCreated = GetDateTime(reader, "TimeCreated"),
                        TimeModified = GetDateTime(reader, "TimeModified")
                    });
                }
            }

            return vendors;
        }

        private List<QBEmployee> ExtractEmployees()
        {
            var employees = new List<QBEmployee>();
            string sql = "SELECT * FROM Employee";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            using (var cmd = new OdbcCommand(sql, _connection))
            using (var reader = cmd.ExecuteReader())
            {
                while (reader.Read())
                {
                    employees.Add(new QBEmployee
                    {
                        ListID = GetString(reader, "ListID"),
                        Name = GetString(reader, "Name"),
                        FirstName = GetString(reader, "FirstName"),
                        LastName = GetString(reader, "LastName"),
                        Phone = GetString(reader, "Phone"),
                        Email = GetString(reader, "Email"),
                        IsActive = GetBool(reader, "IsActive"),
                        TimeCreated = GetDateTime(reader, "TimeCreated"),
                        TimeModified = GetDateTime(reader, "TimeModified")
                    });
                }
            }

            return employees;
        }

        private List<QBItem> ExtractItems()
        {
            var items = new List<QBItem>();

            // Items can be in multiple tables in QODBC
            var queries = new[]
            {
                "SELECT *, 'Service' as Type FROM ItemService",
                "SELECT *, 'Inventory' as Type FROM ItemInventory",
                "SELECT *, 'NonInventory' as Type FROM ItemNonInventory",
                "SELECT *, 'OtherCharge' as Type FROM ItemOtherCharge",
                "SELECT *, 'Discount' as Type FROM ItemDiscount",
                "SELECT *, 'Payment' as Type FROM ItemPayment",
                "SELECT *, 'SalesTax' as Type FROM ItemSalesTax",
                "SELECT *, 'Group' as Type FROM ItemGroup"
            };

            foreach (var sql in queries)
            {
                try
                {
                    using (var cmd = new OdbcCommand(sql, _connection))
                    using (var reader = cmd.ExecuteReader())
                    {
                        while (reader.Read())
                        {
                            items.Add(new QBItem
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                FullName = GetString(reader, "FullName"),
                                Type = GetString(reader, "Type"),
                                SalesDescription = GetString(reader, "SalesDesc") ?? GetString(reader, "Desc"),
                                SalesPrice = GetDecimal(reader, "SalesPrice") ?? GetDecimal(reader, "Price"),
                                PurchaseCost = GetDecimal(reader, "PurchaseCost") ?? GetDecimal(reader, "Cost"),
                                IsActive = GetBool(reader, "IsActive"),
                                TimeCreated = GetDateTime(reader, "TimeCreated"),
                                TimeModified = GetDateTime(reader, "TimeModified")
                            });
                        }
                    }
                }
                catch
                {
                    // Table might not exist - that's OK
                }
            }

            return items;
        }

        private List<QBClass> ExtractClasses()
        {
            var classes = new List<QBClass>();
            string sql = "SELECT * FROM Class";

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        classes.Add(new QBClass
                        {
                            ListID = GetString(reader, "ListID"),
                            Name = GetString(reader, "Name"),
                            FullName = GetString(reader, "FullName"),
                            IsActive = GetBool(reader, "IsActive"),
                            ParentRefListID = GetString(reader, "ParentRef_ListID"),
                            TimeCreated = GetDateTime(reader, "TimeCreated"),
                            TimeModified = GetDateTime(reader, "TimeModified")
                        });
                    }
                }
            }
            catch
            {
                // Classes might not be enabled
            }

            return classes;
        }

        private List<QBInvoice> ExtractInvoices()
        {
            var invoices = new List<QBInvoice>();
            string sql = "SELECT * FROM Invoice";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            using (var cmd = new OdbcCommand(sql, _connection))
            using (var reader = cmd.ExecuteReader())
            {
                while (reader.Read())
                {
                    var invoice = new QBInvoice
                    {
                        TxnID = GetString(reader, "TxnID"),
                        RefNumber = GetString(reader, "RefNumber"),
                        TxnDate = GetDateTime(reader, "TxnDate"),
                        DueDate = GetDateTime(reader, "DueDate"),
                        CustomerRef_ListID = GetString(reader, "CustomerRef_ListID"),
                        CustomerRef_FullName = GetString(reader, "CustomerRef_FullName"),
                        Subtotal = GetDecimal(reader, "Subtotal"),
                        SalesTaxTotal = GetDecimal(reader, "SalesTaxTotal"),
                        TotalAmount = GetDecimal(reader, "TotalAmount") ?? GetDecimal(reader, "BalanceRemaining"),
                        BalanceRemaining = GetDecimal(reader, "BalanceRemaining"),
                        IsPaid = GetBool(reader, "IsPaid"),
                        Memo = GetString(reader, "Memo"),
                        TimeCreated = GetDateTime(reader, "TimeCreated"),
                        TimeModified = GetDateTime(reader, "TimeModified")
                    };

                    // Load line items
                    invoice.LineItems = ExtractInvoiceLines(invoice.TxnID);

                    invoices.Add(invoice);
                }
            }

            return invoices;
        }

        private List<QBInvoiceLine> ExtractInvoiceLines(string txnId)
        {
            var lines = new List<QBInvoiceLine>();

            try
            {
                string sql = $"SELECT * FROM InvoiceLine WHERE TxnID = '{txnId}'";

                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        lines.Add(new QBInvoiceLine
                        {
                            TxnLineID = GetString(reader, "TxnLineID"),
                            ItemRef_ListID = GetString(reader, "ItemRef_ListID"),
                            ItemRef_FullName = GetString(reader, "ItemRef_FullName"),
                            Description = GetString(reader, "Desc"),
                            Quantity = GetDecimal(reader, "Quantity"),
                            Rate = GetDecimal(reader, "Rate"),
                            Amount = GetDecimal(reader, "Amount")
                        });
                    }
                }
            }
            catch
            {
                // Line items might not be accessible
            }

            return lines;
        }

        private List<QBBill> ExtractBills()
        {
            var bills = new List<QBBill>();
            string sql = "SELECT * FROM Bill";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            using (var cmd = new OdbcCommand(sql, _connection))
            using (var reader = cmd.ExecuteReader())
            {
                while (reader.Read())
                {
                    bills.Add(new QBBill
                    {
                        TxnID = GetString(reader, "TxnID"),
                        RefNumber = GetString(reader, "RefNumber"),
                        TxnDate = GetDateTime(reader, "TxnDate"),
                        DueDate = GetDateTime(reader, "DueDate"),
                        VendorRef_ListID = GetString(reader, "VendorRef_ListID"),
                        VendorRef_FullName = GetString(reader, "VendorRef_FullName"),
                        AmountDue = GetDecimal(reader, "AmountDue"),
                        IsPaid = GetBool(reader, "IsPaid"),
                        Memo = GetString(reader, "Memo"),
                        TimeCreated = GetDateTime(reader, "TimeCreated"),
                        TimeModified = GetDateTime(reader, "TimeModified")
                    });
                }
            }

            return bills;
        }

        private List<QBCheck> ExtractChecks()
        {
            var checks = new List<QBCheck>();
            string sql = "SELECT * FROM Check_";  // Note: 'Check' is reserved word

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        checks.Add(new QBCheck
                        {
                            TxnID = GetString(reader, "TxnID"),
                            RefNumber = GetString(reader, "RefNumber"),
                            TxnDate = GetDateTime(reader, "TxnDate"),
                            PayeeEntityRef_ListID = GetString(reader, "PayeeEntityRef_ListID"),
                            PayeeEntityRef_FullName = GetString(reader, "PayeeEntityRef_FullName"),
                            AccountRef_ListID = GetString(reader, "AccountRef_ListID"),
                            AccountRef_FullName = GetString(reader, "AccountRef_FullName"),
                            Amount = GetDecimal(reader, "Amount"),
                            Memo = GetString(reader, "Memo"),
                            TimeCreated = GetDateTime(reader, "TimeCreated"),
                            TimeModified = GetDateTime(reader, "TimeModified")
                        });
                    }
                }
            }
            catch
            {
                // Try alternate table name
                try
                {
                    using (var cmd = new OdbcCommand("SELECT * FROM Checks", _connection))
                    using (var reader = cmd.ExecuteReader())
                    {
                        while (reader.Read())
                        {
                            checks.Add(new QBCheck
                            {
                                TxnID = GetString(reader, "TxnID"),
                                RefNumber = GetString(reader, "RefNumber"),
                                TxnDate = GetDateTime(reader, "TxnDate"),
                                Amount = GetDecimal(reader, "Amount"),
                                TimeCreated = GetDateTime(reader, "TimeCreated"),
                                TimeModified = GetDateTime(reader, "TimeModified")
                            });
                        }
                    }
                }
                catch { }
            }

            return checks;
        }

        private List<QBJournalEntry> ExtractJournalEntries()
        {
            var entries = new List<QBJournalEntry>();
            string sql = "SELECT * FROM JournalEntry";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        entries.Add(new QBJournalEntry
                        {
                            TxnID = GetString(reader, "TxnID"),
                            RefNumber = GetString(reader, "RefNumber"),
                            TxnDate = GetDateTime(reader, "TxnDate"),
                            Memo = GetString(reader, "Memo"),
                            TimeCreated = GetDateTime(reader, "TimeCreated"),
                            TimeModified = GetDateTime(reader, "TimeModified")
                        });
                    }
                }
            }
            catch { }

            return entries;
        }

        private List<QBDeposit> ExtractDeposits()
        {
            var deposits = new List<QBDeposit>();
            string sql = "SELECT * FROM Deposit";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        deposits.Add(new QBDeposit
                        {
                            TxnID = GetString(reader, "TxnID"),
                            TxnDate = GetDateTime(reader, "TxnDate"),
                            DepositToAccountRef_ListID = GetString(reader, "DepositToAccountRef_ListID"),
                            DepositToAccountRef_FullName = GetString(reader, "DepositToAccountRef_FullName"),
                            DepositTotal = GetDecimal(reader, "DepositTotal"),
                            Memo = GetString(reader, "Memo"),
                            TimeCreated = GetDateTime(reader, "TimeCreated"),
                            TimeModified = GetDateTime(reader, "TimeModified")
                        });
                    }
                }
            }
            catch { }

            return deposits;
        }

        private List<QBCreditMemo> ExtractCreditMemos()
        {
            var memos = new List<QBCreditMemo>();
            string sql = "SELECT * FROM CreditMemo";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        memos.Add(new QBCreditMemo
                        {
                            TxnID = GetString(reader, "TxnID"),
                            RefNumber = GetString(reader, "RefNumber"),
                            TxnDate = GetDateTime(reader, "TxnDate"),
                            CustomerRef_ListID = GetString(reader, "CustomerRef_ListID"),
                            CustomerRef_FullName = GetString(reader, "CustomerRef_FullName"),
                            TotalAmount = GetDecimal(reader, "TotalAmount"),
                            CreditRemaining = GetDecimal(reader, "CreditRemaining"),
                            Memo = GetString(reader, "Memo"),
                            TimeCreated = GetDateTime(reader, "TimeCreated"),
                            TimeModified = GetDateTime(reader, "TimeModified")
                        });
                    }
                }
            }
            catch { }

            return memos;
        }

        private List<QBSalesReceipt> ExtractSalesReceipts()
        {
            var receipts = new List<QBSalesReceipt>();
            string sql = "SELECT * FROM SalesReceipt";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        receipts.Add(new QBSalesReceipt
                        {
                            TxnID = GetString(reader, "TxnID"),
                            RefNumber = GetString(reader, "RefNumber"),
                            TxnDate = GetDateTime(reader, "TxnDate"),
                            CustomerRef_ListID = GetString(reader, "CustomerRef_ListID"),
                            CustomerRef_FullName = GetString(reader, "CustomerRef_FullName"),
                            Subtotal = GetDecimal(reader, "Subtotal"),
                            SalesTaxTotal = GetDecimal(reader, "SalesTaxTotal"),
                            TotalAmount = GetDecimal(reader, "TotalAmount"),
                            Memo = GetString(reader, "Memo"),
                            TimeCreated = GetDateTime(reader, "TimeCreated"),
                            TimeModified = GetDateTime(reader, "TimeModified")
                        });
                    }
                }
            }
            catch { }

            return receipts;
        }

        private List<QBEstimate> ExtractEstimates()
        {
            var estimates = new List<QBEstimate>();
            string sql = "SELECT * FROM Estimate";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        estimates.Add(new QBEstimate
                        {
                            TxnID = GetString(reader, "TxnID"),
                            RefNumber = GetString(reader, "RefNumber"),
                            TxnDate = GetDateTime(reader, "TxnDate"),
                            CustomerRef_ListID = GetString(reader, "CustomerRef_ListID"),
                            CustomerRef_FullName = GetString(reader, "CustomerRef_FullName"),
                            Subtotal = GetDecimal(reader, "Subtotal"),
                            TotalAmount = GetDecimal(reader, "TotalAmount"),
                            Memo = GetString(reader, "Memo"),
                            TimeCreated = GetDateTime(reader, "TimeCreated"),
                            TimeModified = GetDateTime(reader, "TimeModified")
                        });
                    }
                }
            }
            catch { }

            return estimates;
        }

        private List<QBPurchaseOrder> ExtractPurchaseOrders()
        {
            var orders = new List<QBPurchaseOrder>();
            string sql = "SELECT * FROM PurchaseOrder";

            if (_incrementalFromDate.HasValue)
            {
                sql += $" WHERE TimeModified >= '{_incrementalFromDate:yyyy-MM-dd}'";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        orders.Add(new QBPurchaseOrder
                        {
                            TxnID = GetString(reader, "TxnID"),
                            RefNumber = GetString(reader, "RefNumber"),
                            TxnDate = GetDateTime(reader, "TxnDate"),
                            VendorRef_ListID = GetString(reader, "VendorRef_ListID"),
                            VendorRef_FullName = GetString(reader, "VendorRef_FullName"),
                            TotalAmount = GetDecimal(reader, "TotalAmount"),
                            IsManuallyClosed = GetBool(reader, "IsManuallyClosed"),
                            Memo = GetString(reader, "Memo"),
                            TimeCreated = GetDateTime(reader, "TimeCreated"),
                            TimeModified = GetDateTime(reader, "TimeModified")
                        });
                    }
                }
            }
            catch { }

            return orders;
        }

        private List<QBPaymentMethod> ExtractPaymentMethods()
        {
            var methods = new List<QBPaymentMethod>();
            string sql = "SELECT * FROM PaymentMethod";

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        methods.Add(new QBPaymentMethod
                        {
                            ListID = GetString(reader, "ListID"),
                            Name = GetString(reader, "Name"),
                            IsActive = GetBool(reader, "IsActive"),
                            PaymentMethodType = GetString(reader, "PaymentMethodType"),
                            TimeCreated = GetDateTime(reader, "TimeCreated"),
                            TimeModified = GetDateTime(reader, "TimeModified")
                        });
                    }
                }
            }
            catch { }

            return methods;
        }

        private List<QBTerms> ExtractTerms()
        {
            var terms = new List<QBTerms>();
            string sql = "SELECT * FROM Terms";

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        terms.Add(new QBTerms
                        {
                            ListID = GetString(reader, "ListID"),
                            Name = GetString(reader, "Name"),
                            IsActive = GetBool(reader, "IsActive"),
                            DueDays = GetInt(reader, "StdDueDays"),
                            DiscountDays = GetInt(reader, "StdDiscountDays"),
                            DiscountPct = GetDecimal(reader, "DiscountPct")
                        });
                    }
                }
            }
            catch { }

            return terms;
        }

        #endregion

        #region Helper Methods

        private void EnsureConnected()
        {
            if (_connection == null || _connection.State != ConnectionState.Open)
            {
                throw new InvalidOperationException("Not connected to QuickBooks. Call Connect() first.");
            }
        }

        private string GetString(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal))
                    return null;
                return reader.GetString(ordinal)?.Trim();
            }
            catch
            {
                return null;
            }
        }

        private string GetString(OdbcDataReader reader, int ordinal)
        {
            try
            {
                if (reader.IsDBNull(ordinal))
                    return null;
                return reader.GetString(ordinal)?.Trim();
            }
            catch
            {
                return null;
            }
        }

        private decimal? GetDecimal(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal))
                    return null;
                return reader.GetDecimal(ordinal);
            }
            catch
            {
                return null;
            }
        }

        private DateTime? GetDateTime(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal))
                    return null;
                return reader.GetDateTime(ordinal);
            }
            catch
            {
                return null;
            }
        }

        private bool? GetBool(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal))
                    return null;
                return reader.GetBoolean(ordinal);
            }
            catch
            {
                return null;
            }
        }

        private int? GetInt(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal))
                    return null;
                return reader.GetInt32(ordinal);
            }
            catch
            {
                return null;
            }
        }

        private string ComputeCompanyFingerprint(QBCompanyInfo company)
        {
            if (company == null) return "unknown";

            using (var sha = System.Security.Cryptography.SHA256.Create())
            {
                var data = System.Text.Encoding.UTF8.GetBytes(
                    $"{company.CompanyName}|{company.LegalCompanyName}|{company.FiscalYearStartMonth}");
                var hash = sha.ComputeHash(data);
                return Convert.ToBase64String(hash).Substring(0, 16);
            }
        }

        #endregion

        public void Dispose()
        {
            if (!_disposed)
            {
                _disposed = true;
                Disconnect();
            }
        }
    }
}
