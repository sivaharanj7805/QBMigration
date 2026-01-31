using System;
using System.Collections.Generic;
using System.Data;
using System.Data.Odbc;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;

namespace QBDesktopExtractor
{
    /// <summary>
    /// QuickBooks data provider using QODBC driver
    /// Works without the official QBFC SDK
    ///
    /// QODBC provides SQL access to QuickBooks data through ODBC
    /// Free for read-only operations
    /// Download: https://qodbc.com/qodbc-downloads/
    /// </summary>
    public class QODBCDataProvider : IQBDataProvider
    {
        private readonly IRedactingLogger _logger;
        private OdbcConnection _connection;
        private bool _disposed;
        private string _driverName;
        private string _companyName;
        private string _qbVersion;

        public string ProviderName => "QODBC";
        public bool IsConnected => _connection?.State == ConnectionState.Open;

        public bool IsAvailable
        {
            get
            {
                var result = CheckAvailability();
                return result.Available;
            }
        }

        public QODBCDataProvider(IRedactingLogger logger = null)
        {
            _logger = logger;
        }

        public BackendDetectionResult CheckAvailability()
        {
            return QBDataProviderFactory.CheckQODBCAvailability(_logger);
        }

        public async Task<bool> ConnectAsync(string companyFilePath = null, CancellationToken ct = default)
        {
            try
            {
                _logger?.Log(LogLevel.Info, "Connecting to QuickBooks via QODBC...");

                // Find QODBC driver
                _driverName = FindQODBCDriver();
                if (string.IsNullOrEmpty(_driverName))
                {
                    throw new InvalidOperationException(
                        "QODBC Driver not found. Please install from: https://qodbc.com/qodbc-downloads/");
                }

                _logger?.Log(LogLevel.Info, "Using driver: {0}", _driverName);

                // Build connection string
                string connectionString;
                if (!string.IsNullOrEmpty(companyFilePath))
                {
                    connectionString = $"Driver={{{_driverName}}};DFQ={companyFilePath};";
                }
                else
                {
                    // Use default (current open company file)
                    connectionString = $"Driver={{{_driverName}}};";
                }

                _connection = new OdbcConnection(connectionString);
                await Task.Run(() => _connection.Open(), ct);

                _logger?.Log(LogLevel.Info, "Connected to QuickBooks via QODBC");

                // Get company info to verify connection
                await GetCompanyInfoInternalAsync(ct);

                return true;
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Error, "Failed to connect via QODBC: {0}", ex.Message);
                throw new QBException("QODBC connection failed", ex.Message, -1, ex);
            }
        }

        public void Disconnect()
        {
            try
            {
                if (_connection != null)
                {
                    if (_connection.State != ConnectionState.Closed)
                    {
                        _connection.Close();
                    }
                    _connection.Dispose();
                    _connection = null;
                }
                _logger?.Log(LogLevel.Info, "Disconnected from QuickBooks");
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error during disconnect: {0}", ex.Message);
            }
        }

        private string FindQODBCDriver()
        {
            // Common QODBC driver names
            string[] driverNames = new[]
            {
                "QODBC Driver for QuickBooks",
                "QODBC Read-Only Driver for QuickBooks",
                "QuickBooks Data",
                "QODBC Desktop Driver for QuickBooks"
            };

            try
            {
                // Check 32-bit ODBC drivers first (for x86 apps)
                using (var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                    @"SOFTWARE\WOW6432Node\ODBC\ODBCINST.INI\ODBC Drivers"))
                {
                    if (key != null)
                    {
                        var names = key.GetValueNames();
                        foreach (var driver in driverNames)
                        {
                            if (Array.Exists(names, n => n.Contains(driver) || driver.Contains(n)))
                            {
                                return driver;
                            }
                        }
                        // Check for any QODBC-like driver
                        foreach (var name in names)
                        {
                            if (name.ToLower().Contains("qodbc") || name.ToLower().Contains("quickbooks"))
                            {
                                return name;
                            }
                        }
                    }
                }

                // Check 64-bit ODBC drivers
                using (var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                    @"SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers"))
                {
                    if (key != null)
                    {
                        var names = key.GetValueNames();
                        foreach (var driver in driverNames)
                        {
                            if (Array.Exists(names, n => n.Contains(driver) || driver.Contains(n)))
                            {
                                return driver;
                            }
                        }
                        // Check for any QODBC-like driver
                        foreach (var name in names)
                        {
                            if (name.ToLower().Contains("qodbc") || name.ToLower().Contains("quickbooks"))
                            {
                                return name;
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error searching for QODBC driver: {0}", ex.Message);
            }

            return null;
        }

        private async Task GetCompanyInfoInternalAsync(CancellationToken ct)
        {
            try
            {
                using (var cmd = new OdbcCommand("SELECT CompanyName FROM Company", _connection))
                {
                    var result = await Task.Run(() => cmd.ExecuteScalar(), ct);
                    _companyName = result?.ToString() ?? "Unknown";
                }

                // Try to get QB version
                try
                {
                    using (var cmd = new OdbcCommand("sp_version", _connection))
                    {
                        cmd.CommandType = CommandType.StoredProcedure;
                        var result = await Task.Run(() => cmd.ExecuteScalar(), ct);
                        _qbVersion = result?.ToString() ?? "Unknown";
                    }
                }
                catch (Exception ex)
                {
                    // sp_version may not be available on all QODBC versions
                    _logger?.Log(LogLevel.Debug, "Could not get QB version via sp_version: {0}", ex.Message);
                    _qbVersion = "QODBC";
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Could not get company info: {0}", ex.Message);
                _companyName = "Unknown";
                _qbVersion = "QODBC";
            }
        }

        public async Task<QBCompanyInfo> GetCompanyInfoAsync(CancellationToken ct = default)
        {
            EnsureConnected();

            var company = new QBCompanyInfo();

            try
            {
                using (var cmd = new OdbcCommand(@"
                    SELECT
                        CompanyName,
                        LegalCompanyName,
                        Address1, City, State, PostalCode, Country,
                        Phone, Fax, Email,
                        FiscalYearStartMonth
                    FROM Company", _connection))
                {
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        if (await Task.Run(() => reader.Read(), ct))
                        {
                            company.CompanyName = GetString(reader, "CompanyName");
                            company.LegalCompanyName = GetString(reader, "LegalCompanyName");
                            company.Address = GetString(reader, "Address1");
                            company.City = GetString(reader, "City");
                            company.State = GetString(reader, "State");
                            company.PostalCode = GetString(reader, "PostalCode");
                            company.Country = GetString(reader, "Country");
                            company.Phone = GetString(reader, "Phone");
                            company.Fax = GetString(reader, "Fax");
                            company.Email = GetString(reader, "Email");
                            company.FiscalYearStartMonth = GetString(reader, "FiscalYearStartMonth");
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error getting company info: {0}", ex.Message);
                company.CompanyName = _companyName ?? "Unknown";
            }

            return company;
        }

        public string GetVersion()
        {
            return _qbVersion ?? "QODBC";
        }

        #region List Extraction Methods

        public async Task<List<QBAccount>> ExtractAccountsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            var accounts = new List<QBAccount>();

            string sql = @"
                SELECT
                    ListID, Name, FullName, IsActive,
                    ParentRefListID, ParentRefFullName, Sublevel,
                    AccountType, SpecialAccountType, IsTaxAccount,
                    AccountNumber, BankNumber, Description,
                    Balance, TotalBalance,
                    SalesTaxCodeRefListID, SalesTaxCodeRefFullName,
                    TaxLineID, TaxLineName,
                    CashFlowClassification,
                    CurrencyRefListID, CurrencyRefFullName,
                    TimeCreated, TimeModified, EditSequence
                FROM Account";

            if (modifiedSince.HasValue)
            {
                sql += $" WHERE TimeModified >= {{ts '{modifiedSince.Value:yyyy-MM-dd HH:mm:ss}'}}";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                {
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            accounts.Add(new QBAccount
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                FullName = GetString(reader, "FullName"),
                                IsActive = GetBool(reader, "IsActive"),
                                ParentRefListID = GetString(reader, "ParentRefListID"),
                                ParentRefFullName = GetString(reader, "ParentRefFullName"),
                                Sublevel = GetInt(reader, "Sublevel"),
                                AccountType = GetString(reader, "AccountType"),
                                SpecialAccountType = GetString(reader, "SpecialAccountType"),
                                IsTaxAccount = GetBool(reader, "IsTaxAccount"),
                                AccountNumber = GetString(reader, "AccountNumber"),
                                BankNumber = GetString(reader, "BankNumber"),
                                Desc = GetString(reader, "Description"),
                                Balance = GetDecimal(reader, "Balance"),
                                TotalBalance = GetDecimal(reader, "TotalBalance"),
                                SalesTaxCodeRefListID = GetString(reader, "SalesTaxCodeRefListID"),
                                SalesTaxCodeRefFullName = GetString(reader, "SalesTaxCodeRefFullName"),
                                TaxLineID = GetInt(reader, "TaxLineID"),
                                TaxLineName = GetString(reader, "TaxLineName"),
                                CashFlowClassification = GetString(reader, "CashFlowClassification"),
                                CurrencyRefListID = GetString(reader, "CurrencyRefListID"),
                                CurrencyRefFullName = GetString(reader, "CurrencyRefFullName"),
                                TimeCreated = GetDateTime(reader, "TimeCreated"),
                                TimeModified = GetDateTime(reader, "TimeModified"),
                                EditSequence = GetString(reader, "EditSequence")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Error, "Error extracting accounts: {0}", ex.Message);
                throw;
            }

            _logger?.Log(LogLevel.Info, "Extracted {0} accounts via QODBC", accounts.Count);
            return accounts;
        }

        public async Task<List<QBCustomer>> ExtractCustomersAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            var customers = new List<QBCustomer>();

            string sql = @"
                SELECT
                    ListID, Name, FullName, IsActive,
                    CompanyName, Salutation, FirstName, MiddleName, LastName,
                    BillAddressAddr1, BillAddressAddr2, BillAddressAddr3, BillAddressCity,
                    BillAddressState, BillAddressPostalCode, BillAddressCountry,
                    ShipAddressAddr1, ShipAddressAddr2, ShipAddressAddr3, ShipAddressCity,
                    ShipAddressState, ShipAddressPostalCode, ShipAddressCountry,
                    Phone, AltPhone, Fax, Email, Contact,
                    CustomerTypeRefListID, CustomerTypeRefFullName,
                    TermsRefListID, TermsRefFullName,
                    SalesRepRefListID, SalesRepRefFullName,
                    Balance, TotalBalance, CreditLimit,
                    SalesTaxCodeRefListID, SalesTaxCodeRefFullName,
                    ItemSalesTaxRefListID, ItemSalesTaxRefFullName,
                    ResaleNumber, AccountNumber,
                    PreferredPaymentMethodRefListID, PreferredPaymentMethodRefFullName,
                    JobStatus, JobStartDate, JobProjectedEndDate, JobEndDate,
                    JobDesc, JobTypeRefListID, JobTypeRefFullName,
                    Notes, PriceLevelRefListID, PriceLevelRefFullName,
                    ParentRefListID, ParentRefFullName, Sublevel,
                    TimeCreated, TimeModified, EditSequence
                FROM Customer";

            if (modifiedSince.HasValue)
            {
                sql += $" WHERE TimeModified >= {{ts '{modifiedSince.Value:yyyy-MM-dd HH:mm:ss}'}}";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                {
                    cmd.CommandTimeout = 300; // 5 minutes for large datasets
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            customers.Add(ParseCustomer(reader));
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Error, "Error extracting customers: {0}", ex.Message);
                throw;
            }

            _logger?.Log(LogLevel.Info, "Extracted {0} customers via QODBC", customers.Count);
            return customers;
        }

        private QBCustomer ParseCustomer(OdbcDataReader reader)
        {
            return new QBCustomer
            {
                ListID = GetString(reader, "ListID"),
                Name = GetString(reader, "Name"),
                FullName = GetString(reader, "FullName"),
                IsActive = GetBool(reader, "IsActive"),
                CompanyName = GetString(reader, "CompanyName"),
                Salutation = GetString(reader, "Salutation"),
                FirstName = GetString(reader, "FirstName"),
                MiddleName = GetString(reader, "MiddleName"),
                LastName = GetString(reader, "LastName"),
                BillAddressAddr1 = GetString(reader, "BillAddressAddr1"),
                BillAddressAddr2 = GetString(reader, "BillAddressAddr2"),
                BillAddressAddr3 = GetString(reader, "BillAddressAddr3"),
                BillAddressCity = GetString(reader, "BillAddressCity"),
                BillAddressState = GetString(reader, "BillAddressState"),
                BillAddressPostalCode = GetString(reader, "BillAddressPostalCode"),
                BillAddressCountry = GetString(reader, "BillAddressCountry"),
                ShipAddressAddr1 = GetString(reader, "ShipAddressAddr1"),
                ShipAddressAddr2 = GetString(reader, "ShipAddressAddr2"),
                ShipAddressAddr3 = GetString(reader, "ShipAddressAddr3"),
                ShipAddressCity = GetString(reader, "ShipAddressCity"),
                ShipAddressState = GetString(reader, "ShipAddressState"),
                ShipAddressPostalCode = GetString(reader, "ShipAddressPostalCode"),
                ShipAddressCountry = GetString(reader, "ShipAddressCountry"),
                Phone = GetString(reader, "Phone"),
                AltPhone = GetString(reader, "AltPhone"),
                Fax = GetString(reader, "Fax"),
                Email = GetString(reader, "Email"),
                Contact = GetString(reader, "Contact"),
                CustomerTypeRefListID = GetString(reader, "CustomerTypeRefListID"),
                CustomerTypeRefFullName = GetString(reader, "CustomerTypeRefFullName"),
                TermsRefListID = GetString(reader, "TermsRefListID"),
                TermsRefFullName = GetString(reader, "TermsRefFullName"),
                SalesRepRefListID = GetString(reader, "SalesRepRefListID"),
                SalesRepRefFullName = GetString(reader, "SalesRepRefFullName"),
                Balance = GetDecimal(reader, "Balance"),
                TotalBalance = GetDecimal(reader, "TotalBalance"),
                CreditLimit = GetDecimal(reader, "CreditLimit"),
                SalesTaxCodeRefListID = GetString(reader, "SalesTaxCodeRefListID"),
                SalesTaxCodeRefFullName = GetString(reader, "SalesTaxCodeRefFullName"),
                ItemSalesTaxRefListID = GetString(reader, "ItemSalesTaxRefListID"),
                ItemSalesTaxRefFullName = GetString(reader, "ItemSalesTaxRefFullName"),
                ResaleNumber = GetString(reader, "ResaleNumber"),
                AccountNumber = GetString(reader, "AccountNumber"),
                PrefPaymentMethodRefListID = GetString(reader, "PreferredPaymentMethodRefListID"),
                PrefPaymentMethodRefFullName = GetString(reader, "PreferredPaymentMethodRefFullName"),
                JobStatus = GetString(reader, "JobStatus"),
                JobStartDate = GetDateTime(reader, "JobStartDate"),
                JobProjectedEndDate = GetDateTime(reader, "JobProjectedEndDate"),
                JobEndDate = GetDateTime(reader, "JobEndDate"),
                JobDesc = GetString(reader, "JobDesc"),
                JobTypeRefListID = GetString(reader, "JobTypeRefListID"),
                JobTypeRefFullName = GetString(reader, "JobTypeRefFullName"),
                Notes = GetString(reader, "Notes"),
                PriceLevelRefListID = GetString(reader, "PriceLevelRefListID"),
                PriceLevelRefFullName = GetString(reader, "PriceLevelRefFullName"),
                ParentRefListID = GetString(reader, "ParentRefListID"),
                ParentRefFullName = GetString(reader, "ParentRefFullName"),
                Sublevel = GetInt(reader, "Sublevel"),
                TimeCreated = GetDateTime(reader, "TimeCreated"),
                TimeModified = GetDateTime(reader, "TimeModified"),
                EditSequence = GetString(reader, "EditSequence")
            };
        }

        public async Task<List<QBVendor>> ExtractVendorsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            var vendors = new List<QBVendor>();

            string sql = @"
                SELECT
                    ListID, Name, FullName, IsActive,
                    CompanyName, Salutation, FirstName, MiddleName, LastName,
                    VendorAddressAddr1, VendorAddressAddr2, VendorAddressAddr3,
                    VendorAddressCity, VendorAddressState, VendorAddressPostalCode, VendorAddressCountry,
                    Phone, AltPhone, Fax, Email, Contact,
                    VendorTypeRefListID, VendorTypeRefFullName,
                    TermsRefListID, TermsRefFullName,
                    CreditLimit, VendorTaxIdent, IsVendorEligibleFor1099,
                    Balance, AccountNumber,
                    ParentRefListID, ParentRefFullName, Sublevel,
                    TimeCreated, TimeModified, EditSequence
                FROM Vendor";

            if (modifiedSince.HasValue)
            {
                sql += $" WHERE TimeModified >= {{ts '{modifiedSince.Value:yyyy-MM-dd HH:mm:ss}'}}";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                {
                    cmd.CommandTimeout = 300;
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            vendors.Add(new QBVendor
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                FullName = GetString(reader, "FullName"),
                                IsActive = GetBool(reader, "IsActive"),
                                CompanyName = GetString(reader, "CompanyName"),
                                Salutation = GetString(reader, "Salutation"),
                                FirstName = GetString(reader, "FirstName"),
                                MiddleName = GetString(reader, "MiddleName"),
                                LastName = GetString(reader, "LastName"),
                                VendorAddressAddr1 = GetString(reader, "VendorAddressAddr1"),
                                VendorAddressAddr2 = GetString(reader, "VendorAddressAddr2"),
                                VendorAddressAddr3 = GetString(reader, "VendorAddressAddr3"),
                                VendorAddressCity = GetString(reader, "VendorAddressCity"),
                                VendorAddressState = GetString(reader, "VendorAddressState"),
                                VendorAddressPostalCode = GetString(reader, "VendorAddressPostalCode"),
                                VendorAddressCountry = GetString(reader, "VendorAddressCountry"),
                                Phone = GetString(reader, "Phone"),
                                AltPhone = GetString(reader, "AltPhone"),
                                Fax = GetString(reader, "Fax"),
                                Email = GetString(reader, "Email"),
                                Contact = GetString(reader, "Contact"),
                                VendorTypeRefListID = GetString(reader, "VendorTypeRefListID"),
                                VendorTypeRefFullName = GetString(reader, "VendorTypeRefFullName"),
                                TermsRefListID = GetString(reader, "TermsRefListID"),
                                TermsRefFullName = GetString(reader, "TermsRefFullName"),
                                CreditLimit = GetDecimal(reader, "CreditLimit"),
                                VendorTaxIdent = GetString(reader, "VendorTaxIdent"),
                                IsVendorEligibleFor1099 = GetBool(reader, "IsVendorEligibleFor1099"),
                                Balance = GetDecimal(reader, "Balance"),
                                AccountNumber = GetString(reader, "AccountNumber"),
                                ParentRefListID = GetString(reader, "ParentRefListID"),
                                ParentRefFullName = GetString(reader, "ParentRefFullName"),
                                Sublevel = GetInt(reader, "Sublevel"),
                                TimeCreated = GetDateTime(reader, "TimeCreated"),
                                TimeModified = GetDateTime(reader, "TimeModified"),
                                EditSequence = GetString(reader, "EditSequence")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Error, "Error extracting vendors: {0}", ex.Message);
                throw;
            }

            _logger?.Log(LogLevel.Info, "Extracted {0} vendors via QODBC", vendors.Count);
            return vendors;
        }

        public async Task<List<QBEmployee>> ExtractEmployeesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            var employees = new List<QBEmployee>();

            string sql = @"
                SELECT
                    ListID, Name, IsActive,
                    Salutation, FirstName, MiddleName, LastName,
                    EmployeeAddressAddr1, EmployeeAddressAddr2, EmployeeAddressCity,
                    EmployeeAddressState, EmployeeAddressPostalCode, EmployeeAddressCountry,
                    Phone, AltPhone, Fax, Email,
                    EmployeeType, Gender, SSN,
                    HiredDate, ReleasedDate, BirthDate,
                    AccountNumber, Notes,
                    TimeCreated, TimeModified, EditSequence
                FROM Employee";

            if (modifiedSince.HasValue)
            {
                sql += $" WHERE TimeModified >= {{ts '{modifiedSince.Value:yyyy-MM-dd HH:mm:ss}'}}";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                {
                    cmd.CommandTimeout = 300;
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            employees.Add(new QBEmployee
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                IsActive = GetBool(reader, "IsActive"),
                                Salutation = GetString(reader, "Salutation"),
                                FirstName = GetString(reader, "FirstName"),
                                MiddleName = GetString(reader, "MiddleName"),
                                LastName = GetString(reader, "LastName"),
                                EmployeeAddressAddr1 = GetString(reader, "EmployeeAddressAddr1"),
                                EmployeeAddressAddr2 = GetString(reader, "EmployeeAddressAddr2"),
                                EmployeeAddressCity = GetString(reader, "EmployeeAddressCity"),
                                EmployeeAddressState = GetString(reader, "EmployeeAddressState"),
                                EmployeeAddressPostalCode = GetString(reader, "EmployeeAddressPostalCode"),
                                EmployeeAddressCountry = GetString(reader, "EmployeeAddressCountry"),
                                Phone = GetString(reader, "Phone"),
                                AltPhone = GetString(reader, "AltPhone"),
                                Fax = GetString(reader, "Fax"),
                                Email = GetString(reader, "Email"),
                                EmployeeType = GetString(reader, "EmployeeType"),
                                Gender = GetString(reader, "Gender"),
                                HiredDate = GetDateTime(reader, "HiredDate"),
                                ReleasedDate = GetDateTime(reader, "ReleasedDate"),
                                BirthDate = GetDateTime(reader, "BirthDate"),
                                AccountNumber = GetString(reader, "AccountNumber"),
                                Notes = GetString(reader, "Notes"),
                                TimeCreated = GetDateTime(reader, "TimeCreated"),
                                TimeModified = GetDateTime(reader, "TimeModified"),
                                EditSequence = GetString(reader, "EditSequence")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Error, "Error extracting employees: {0}", ex.Message);
                throw;
            }

            _logger?.Log(LogLevel.Info, "Extracted {0} employees via QODBC", employees.Count);
            return employees;
        }

        public async Task<List<QBItem>> ExtractItemsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            var items = new List<QBItem>();

            // QODBC uses ItemInventory, ItemService, ItemNonInventory tables
            await ExtractItemsFromTableAsync("ItemInventory", items, modifiedSince, ct);
            await ExtractItemsFromTableAsync("ItemService", items, modifiedSince, ct);
            await ExtractItemsFromTableAsync("ItemNonInventory", items, modifiedSince, ct);
            await ExtractItemsFromTableAsync("ItemOtherCharge", items, modifiedSince, ct);
            await ExtractItemsFromTableAsync("ItemDiscount", items, modifiedSince, ct);

            _logger?.Log(LogLevel.Info, "Extracted {0} items via QODBC", items.Count);
            return items;
        }

        private async Task ExtractItemsFromTableAsync(string tableName, List<QBItem> items, DateTime? modifiedSince, CancellationToken ct)
        {
            try
            {
                string sql = $@"
                    SELECT
                        ListID, Name, FullName, IsActive,
                        ParentRefListID, ParentRefFullName, Sublevel,
                        SalesDesc, SalesPrice, SalesTaxCodeRefFullName,
                        PurchaseDesc, PurchaseCost,
                        IncomeAccountRefFullName, ExpenseAccountRefFullName,
                        AssetAccountRefFullName, COGSAccountRefFullName,
                        QuantityOnHand, ReorderPoint,
                        TimeCreated, TimeModified, EditSequence
                    FROM {tableName}";

                if (modifiedSince.HasValue)
                {
                    sql += $" WHERE TimeModified >= {{ts '{modifiedSince.Value:yyyy-MM-dd HH:mm:ss}'}}";
                }

                using (var cmd = new OdbcCommand(sql, _connection))
                {
                    cmd.CommandTimeout = 300;
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            items.Add(new QBItem
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                FullName = GetString(reader, "FullName"),
                                IsActive = GetBool(reader, "IsActive"),
                                Type = tableName.Replace("Item", ""),
                                ParentRefListID = GetString(reader, "ParentRefListID"),
                                ParentRefFullName = GetString(reader, "ParentRefFullName"),
                                Sublevel = GetInt(reader, "Sublevel"),
                                SalesDescription = GetStringSafe(reader, "SalesDesc"),
                                SalesPrice = GetDecimalSafe(reader, "SalesPrice"),
                                SalesTaxCodeRefFullName = GetStringSafe(reader, "SalesTaxCodeRefFullName"),
                                PurchaseDescription = GetStringSafe(reader, "PurchaseDesc"),
                                PurchaseCost = GetDecimalSafe(reader, "PurchaseCost"),
                                IncomeAccountRefFullName = GetStringSafe(reader, "IncomeAccountRefFullName"),
                                ExpenseAccountRefFullName = GetStringSafe(reader, "ExpenseAccountRefFullName"),
                                AssetAccountRefFullName = GetStringSafe(reader, "AssetAccountRefFullName"),
                                COGSAccountRefFullName = GetStringSafe(reader, "COGSAccountRefFullName"),
                                QuantityOnHand = GetDecimalSafe(reader, "QuantityOnHand"),
                                ReorderPoint = GetDecimalSafe(reader, "ReorderPoint"),
                                TimeCreated = GetDateTime(reader, "TimeCreated"),
                                TimeModified = GetDateTime(reader, "TimeModified"),
                                EditSequence = GetString(reader, "EditSequence")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                // Table might not exist in this QB edition
                _logger?.Log(LogLevel.Debug, "Could not extract from {0}: {1}", tableName, ex.Message);
            }
        }

        public async Task<List<QBClass>> ExtractClassesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            var classes = new List<QBClass>();

            string sql = @"
                SELECT
                    ListID, Name, FullName, IsActive,
                    ParentRefListID, ParentRefFullName, Sublevel,
                    TimeCreated, TimeModified, EditSequence
                FROM Class";

            if (modifiedSince.HasValue)
            {
                sql += $" WHERE TimeModified >= {{ts '{modifiedSince.Value:yyyy-MM-dd HH:mm:ss}'}}";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                {
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            classes.Add(new QBClass
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                FullName = GetString(reader, "FullName"),
                                IsActive = GetBool(reader, "IsActive"),
                                ParentRefListID = GetString(reader, "ParentRefListID"),
                                ParentRefFullName = GetString(reader, "ParentRefFullName"),
                                Sublevel = GetInt(reader, "Sublevel"),
                                TimeCreated = GetDateTime(reader, "TimeCreated"),
                                TimeModified = GetDateTime(reader, "TimeModified"),
                                EditSequence = GetString(reader, "EditSequence")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error extracting classes: {0}", ex.Message);
            }

            _logger?.Log(LogLevel.Info, "Extracted {0} classes via QODBC", classes.Count);
            return classes;
        }

        public async Task<List<QBPaymentMethod>> ExtractPaymentMethodsAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            var methods = new List<QBPaymentMethod>();

            try
            {
                using (var cmd = new OdbcCommand("SELECT ListID, Name, IsActive, PaymentMethodType FROM PaymentMethod", _connection))
                {
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            methods.Add(new QBPaymentMethod
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                IsActive = GetBool(reader, "IsActive"),
                                PaymentMethodType = GetString(reader, "PaymentMethodType")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error extracting payment methods: {0}", ex.Message);
            }

            return methods;
        }

        public async Task<List<QBTerms>> ExtractTermsAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            var terms = new List<QBTerms>();

            try
            {
                using (var cmd = new OdbcCommand(@"
                    SELECT ListID, Name, IsActive,
                           StdDueDays, StdDiscountDays, DiscountPct
                    FROM Terms", _connection))
                {
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
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
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error extracting terms: {0}", ex.Message);
            }

            return terms;
        }

        public async Task<List<QBSalesTaxCode>> ExtractSalesTaxCodesAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            var codes = new List<QBSalesTaxCode>();

            try
            {
                using (var cmd = new OdbcCommand(@"
                    SELECT ListID, Name, IsActive, IsTaxable, Description
                    FROM SalesTaxCode", _connection))
                {
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            codes.Add(new QBSalesTaxCode
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                IsActive = GetBool(reader, "IsActive"),
                                IsTaxable = GetBool(reader, "IsTaxable"),
                                Desc = GetString(reader, "Description")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error extracting sales tax codes: {0}", ex.Message);
            }

            return codes;
        }

        public async Task<List<QBCustomerType>> ExtractCustomerTypesAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            var types = new List<QBCustomerType>();

            try
            {
                using (var cmd = new OdbcCommand("SELECT ListID, Name, FullName, IsActive FROM CustomerType", _connection))
                {
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            types.Add(new QBCustomerType
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                FullName = GetString(reader, "FullName"),
                                IsActive = GetBool(reader, "IsActive")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error extracting customer types: {0}", ex.Message);
            }

            return types;
        }

        public async Task<List<QBVendorType>> ExtractVendorTypesAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            var types = new List<QBVendorType>();

            try
            {
                using (var cmd = new OdbcCommand("SELECT ListID, Name, FullName, IsActive FROM VendorType", _connection))
                {
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            types.Add(new QBVendorType
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                FullName = GetString(reader, "FullName"),
                                IsActive = GetBool(reader, "IsActive")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error extracting vendor types: {0}", ex.Message);
            }

            return types;
        }

        public async Task<List<QBCurrency>> ExtractCurrenciesAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            var currencies = new List<QBCurrency>();

            try
            {
                using (var cmd = new OdbcCommand(@"
                    SELECT ListID, Name, IsActive, CurrencyCode,
                           ExchangeRate, IsUserDefinedCurrency
                    FROM Currency", _connection))
                {
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            currencies.Add(new QBCurrency
                            {
                                ListID = GetString(reader, "ListID"),
                                Name = GetString(reader, "Name"),
                                IsActive = GetBool(reader, "IsActive"),
                                CurrencyCode = GetString(reader, "CurrencyCode"),
                                ExchangeRate = GetDecimal(reader, "ExchangeRate"),
                                IsUserDefinedCurrency = GetBool(reader, "IsUserDefinedCurrency")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Debug, "Multi-currency not enabled or error: {0}", ex.Message);
            }

            return currencies;
        }

        #endregion

        #region Transaction Extraction Methods

        public async Task<List<QBInvoice>> ExtractInvoicesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            var invoices = new List<QBInvoice>();

            string sql = @"
                SELECT
                    TxnID, TxnNumber, RefNumber,
                    CustomerRefListID, CustomerRefFullName,
                    ClassRefListID, ClassRefFullName,
                    ARAccountRefListID, ARAccountRefFullName,
                    TemplateRefListID, TemplateRefFullName,
                    TxnDate, DueDate, ShipDate,
                    Subtotal, SalesTaxTotal, AppliedAmount, BalanceRemaining,
                    IsPending, IsFinanceCharge, IsPaid, IsToBePrinted, IsToBeEmailed,
                    PONumber, TermsRefFullName, SalesRepRefFullName,
                    ShipMethodRefFullName, FOB,
                    BillAddressAddr1, BillAddressCity, BillAddressState, BillAddressPostalCode,
                    ShipAddressAddr1, ShipAddressCity, ShipAddressState, ShipAddressPostalCode,
                    Memo, CustomerMsgRefFullName,
                    TimeCreated, TimeModified, EditSequence
                FROM Invoice";

            if (modifiedSince.HasValue)
            {
                sql += $" WHERE TimeModified >= {{ts '{modifiedSince.Value:yyyy-MM-dd HH:mm:ss}'}}";
            }

            try
            {
                using (var cmd = new OdbcCommand(sql, _connection))
                {
                    cmd.CommandTimeout = 600;
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            var invoice = new QBInvoice
                            {
                                TxnID = GetString(reader, "TxnID"),
                                TxnNumber = GetInt(reader, "TxnNumber"),
                                RefNumber = GetString(reader, "RefNumber"),
                                CustomerRefListID = GetString(reader, "CustomerRefListID"),
                                CustomerRefFullName = GetString(reader, "CustomerRefFullName"),
                                ClassRefListID = GetString(reader, "ClassRefListID"),
                                ClassRefFullName = GetString(reader, "ClassRefFullName"),
                                ARAccountRefListID = GetString(reader, "ARAccountRefListID"),
                                ARAccountRefFullName = GetString(reader, "ARAccountRefFullName"),
                                TxnDate = GetDateTime(reader, "TxnDate"),
                                DueDate = GetDateTime(reader, "DueDate"),
                                ShipDate = GetDateTime(reader, "ShipDate"),
                                Subtotal = GetDecimal(reader, "Subtotal"),
                                SalesTaxTotal = GetDecimal(reader, "SalesTaxTotal"),
                                AppliedAmount = GetDecimal(reader, "AppliedAmount"),
                                BalanceRemaining = GetDecimal(reader, "BalanceRemaining"),
                                IsPending = GetBool(reader, "IsPending"),
                                IsFinanceCharge = GetBool(reader, "IsFinanceCharge"),
                                IsPaid = GetBool(reader, "IsPaid"),
                                IsToBePrinted = GetBool(reader, "IsToBePrinted"),
                                IsToBeEmailed = GetBool(reader, "IsToBeEmailed"),
                                PONumber = GetString(reader, "PONumber"),
                                TermsRefFullName = GetString(reader, "TermsRefFullName"),
                                SalesRepRefFullName = GetString(reader, "SalesRepRefFullName"),
                                ShipMethodRefFullName = GetString(reader, "ShipMethodRefFullName"),
                                FOB = GetString(reader, "FOB"),
                                Memo = GetString(reader, "Memo"),
                                CustomerMsgRefFullName = GetString(reader, "CustomerMsgRefFullName"),
                                TimeCreated = GetDateTime(reader, "TimeCreated"),
                                TimeModified = GetDateTime(reader, "TimeModified"),
                                EditSequence = GetString(reader, "EditSequence")
                            };

                            // Get line items
                            invoice.Lines = await ExtractInvoiceLinesAsync(invoice.TxnID, ct);

                            invoices.Add(invoice);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Error, "Error extracting invoices: {0}", ex.Message);
                throw;
            }

            _logger?.Log(LogLevel.Info, "Extracted {0} invoices via QODBC", invoices.Count);
            return invoices;
        }

        private async Task<List<QBInvoiceLine>> ExtractInvoiceLinesAsync(string txnId, CancellationToken ct)
        {
            var lines = new List<QBInvoiceLine>();

            try
            {
                // SECURITY FIX: Use parameterized query to prevent SQL injection
                using (var cmd = new OdbcCommand(@"
                    SELECT
                        TxnLineID, ItemRefListID, ItemRefFullName,
                        Description, Quantity, UnitOfMeasure,
                        Rate, Amount, ClassRefFullName,
                        SalesTaxCodeRefFullName, ServiceDate
                    FROM InvoiceLine
                    WHERE InvoiceTxnID = ?", _connection))
                {
                    cmd.Parameters.AddWithValue("@txnId", txnId ?? "");

                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            lines.Add(new QBInvoiceLine
                            {
                                TxnLineID = GetString(reader, "TxnLineID"),
                                ItemRefListID = GetString(reader, "ItemRefListID"),
                                ItemRefFullName = GetString(reader, "ItemRefFullName"),
                                Description = GetString(reader, "Description"),
                                Quantity = GetDecimal(reader, "Quantity"),
                                UnitOfMeasure = GetString(reader, "UnitOfMeasure"),
                                Rate = GetDecimal(reader, "Rate"),
                                Amount = GetDecimal(reader, "Amount"),
                                ClassRefFullName = GetString(reader, "ClassRefFullName"),
                                SalesTaxCodeRefListID = GetString(reader, "SalesTaxCodeRefFullName"),
                                ServiceDate = GetDateTime(reader, "ServiceDate")
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Debug, "Error getting invoice lines: {0}", ex.Message);
            }

            return lines;
        }

        // Simplified implementations for other transactions
        public async Task<List<QBBill>> ExtractBillsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            return await ExtractSimpleTransactionAsync<QBBill>("Bill", modifiedSince, ct);
        }

        public async Task<List<QBCheck>> ExtractChecksAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            return await ExtractSimpleTransactionAsync<QBCheck>("Check", modifiedSince, ct);
        }

        public async Task<List<QBJournalEntry>> ExtractJournalEntriesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            return await ExtractSimpleTransactionAsync<QBJournalEntry>("JournalEntry", modifiedSince, ct);
        }

        public async Task<List<QBDeposit>> ExtractDepositsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            return await ExtractSimpleTransactionAsync<QBDeposit>("Deposit", modifiedSince, ct);
        }

        public async Task<List<QBCreditMemo>> ExtractCreditMemosAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            return await ExtractSimpleTransactionAsync<QBCreditMemo>("CreditMemo", modifiedSince, ct);
        }

        public async Task<List<QBSalesReceipt>> ExtractSalesReceiptsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            return await ExtractSimpleTransactionAsync<QBSalesReceipt>("SalesReceipt", modifiedSince, ct);
        }

        public async Task<List<QBEstimate>> ExtractEstimatesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            return await ExtractSimpleTransactionAsync<QBEstimate>("Estimate", modifiedSince, ct);
        }

        public async Task<List<QBPurchaseOrder>> ExtractPurchaseOrdersAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            return await ExtractSimpleTransactionAsync<QBPurchaseOrder>("PurchaseOrder", modifiedSince, ct);
        }

        public async Task<List<QBSalesOrder>> ExtractSalesOrdersAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            return await ExtractSimpleTransactionAsync<QBSalesOrder>("SalesOrder", modifiedSince, ct);
        }

        private async Task<List<T>> ExtractSimpleTransactionAsync<T>(string tableName, DateTime? modifiedSince, CancellationToken ct) where T : class, new()
        {
            var results = new List<T>();

            try
            {
                string sql = $"SELECT * FROM {tableName}";
                if (modifiedSince.HasValue)
                {
                    sql += $" WHERE TimeModified >= {{ts '{modifiedSince.Value:yyyy-MM-dd HH:mm:ss}'}}";
                }

                using (var cmd = new OdbcCommand(sql, _connection))
                {
                    cmd.CommandTimeout = 600;
                    using (var reader = await Task.Run(() => cmd.ExecuteReader(), ct))
                    {
                        var properties = typeof(T).GetProperties();
                        var columnNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

                        for (int i = 0; i < reader.FieldCount; i++)
                        {
                            columnNames.Add(reader.GetName(i));
                        }

                        while (await Task.Run(() => reader.Read(), ct))
                        {
                            var item = new T();

                            foreach (var prop in properties)
                            {
                                if (columnNames.Contains(prop.Name) && prop.CanWrite)
                                {
                                    try
                                    {
                                        var value = reader[prop.Name];
                                        if (value != DBNull.Value)
                                        {
                                            if (prop.PropertyType == typeof(string))
                                                prop.SetValue(item, value?.ToString());
                                            else if (prop.PropertyType == typeof(decimal?) || prop.PropertyType == typeof(decimal))
                                                prop.SetValue(item, Convert.ToDecimal(value));
                                            else if (prop.PropertyType == typeof(int?) || prop.PropertyType == typeof(int))
                                                prop.SetValue(item, Convert.ToInt32(value));
                                            else if (prop.PropertyType == typeof(bool?) || prop.PropertyType == typeof(bool))
                                                prop.SetValue(item, Convert.ToBoolean(value));
                                            else if (prop.PropertyType == typeof(DateTime?) || prop.PropertyType == typeof(DateTime))
                                                prop.SetValue(item, Convert.ToDateTime(value));
                                        }
                                    }
                                    catch (Exception)
                                    {
                                        // Property mapping failures are expected for schema mismatches
                                        // Individual property failures don't warrant logging each one
                                    }
                                }
                            }

                            results.Add(item);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error extracting {0}: {1}", tableName, ex.Message);
            }

            _logger?.Log(LogLevel.Info, "Extracted {0} {1} via QODBC", results.Count, tableName);
            return results;
        }

        #endregion

        #region Full Extraction

        public async Task<QBExtractedData> ExtractAllDataAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();

            _logger?.Log(LogLevel.Info, "Starting full extraction via QODBC...");

            var data = new QBExtractedData
            {
                ExtractedAt = DateTime.Now,
                SessionID = Guid.NewGuid().ToString(),
                Company = await GetCompanyInfoAsync(ct),
                QBVersion = GetVersion(),
                IsIncrementalSync = modifiedSince.HasValue,
                IncrementalFromDate = modifiedSince
            };

            // Extract lists
            data.Accounts = await ExtractAccountsAsync(modifiedSince, ct);
            data.Customers = await ExtractCustomersAsync(modifiedSince, ct);
            data.Vendors = await ExtractVendorsAsync(modifiedSince, ct);
            data.Employees = await ExtractEmployeesAsync(modifiedSince, ct);
            data.Items = await ExtractItemsAsync(modifiedSince, ct);
            data.Classes = await ExtractClassesAsync(modifiedSince, ct);
            data.PaymentMethods = await ExtractPaymentMethodsAsync(ct);
            data.Terms = await ExtractTermsAsync(ct);
            data.SalesTaxCodes = await ExtractSalesTaxCodesAsync(ct);
            data.CustomerTypes = await ExtractCustomerTypesAsync(ct);
            data.VendorTypes = await ExtractVendorTypesAsync(ct);
            data.Currencies = await ExtractCurrenciesAsync(ct);

            // Extract transactions
            data.Invoices = await ExtractInvoicesAsync(modifiedSince, ct);
            data.Bills = await ExtractBillsAsync(modifiedSince, ct);
            data.Checks = await ExtractChecksAsync(modifiedSince, ct);
            data.JournalEntries = await ExtractJournalEntriesAsync(modifiedSince, ct);
            data.Deposits = await ExtractDepositsAsync(modifiedSince, ct);
            data.CreditMemos = await ExtractCreditMemosAsync(modifiedSince, ct);
            data.SalesReceipts = await ExtractSalesReceiptsAsync(modifiedSince, ct);
            data.Estimates = await ExtractEstimatesAsync(modifiedSince, ct);
            data.PurchaseOrders = await ExtractPurchaseOrdersAsync(modifiedSince, ct);
            data.SalesOrders = await ExtractSalesOrdersAsync(modifiedSince, ct);

            _logger?.Log(LogLevel.Info, "QODBC extraction complete");
            return data;
        }

        #endregion

        #region Helper Methods

        private void EnsureConnected()
        {
            if (!IsConnected)
            {
                throw new InvalidOperationException("Not connected to QuickBooks. Call ConnectAsync first.");
            }
        }

        // NOTE: These helper methods intentionally return null on any exception.
        // This is by design - columns may not exist in all QB editions/versions,
        // and graceful degradation is preferred over failing the entire extraction.

        private string GetString(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                return reader.IsDBNull(ordinal) ? null : reader.GetString(ordinal);
            }
            catch (Exception)
            {
                return null; // Column may not exist or type mismatch
            }
        }

        private string GetStringSafe(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                return reader.IsDBNull(ordinal) ? null : reader.GetString(ordinal);
            }
            catch (Exception)
            {
                return null; // Column may not exist or type mismatch
            }
        }

        private bool? GetBool(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal)) return null;
                return reader.GetBoolean(ordinal);
            }
            catch (Exception)
            {
                return null; // Column may not exist or type mismatch
            }
        }

        private int? GetInt(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal)) return null;
                return reader.GetInt32(ordinal);
            }
            catch (Exception)
            {
                return null; // Column may not exist or type mismatch
            }
        }

        private decimal? GetDecimal(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal)) return null;
                return reader.GetDecimal(ordinal);
            }
            catch (Exception)
            {
                return null; // Column may not exist or type mismatch
            }
        }

        private decimal? GetDecimalSafe(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal)) return null;
                return reader.GetDecimal(ordinal);
            }
            catch (Exception)
            {
                return null; // Column may not exist or type mismatch
            }
        }

        private DateTime? GetDateTime(OdbcDataReader reader, string column)
        {
            try
            {
                int ordinal = reader.GetOrdinal(column);
                if (reader.IsDBNull(ordinal)) return null;
                return reader.GetDateTime(ordinal);
            }
            catch (Exception)
            {
                return null; // Column may not exist or type mismatch
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
