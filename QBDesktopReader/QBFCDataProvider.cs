using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace QBDesktopExtractor
{
    /// <summary>
    /// QuickBooks data provider using the official QBFC16 SDK
    /// Wraps the existing QBSessionManager and QBDataExtractor for maximum reliability
    ///
    /// This is the preferred backend when the SDK is available as it provides:
    /// - Direct COM access to QuickBooks
    /// - Full transaction linking and relationships
    /// - Better error messages from QuickBooks
    /// - Support for all entity types including custom fields
    /// </summary>
    public class QBFCDataProvider : IQBDataProvider
    {
        private readonly IRedactingLogger _logger;
        private readonly double? _maxQBXMLVersion;
        private QBSessionManager _sessionManager;
        private QBDataExtractor _extractor;
        private QBCompanyInfo _cachedCompanyInfo;
        private bool _disposed;

        public string ProviderName => "QBFC (Official SDK)";
        public bool IsConnected => _sessionManager?.IsSessionOpen ?? false;

        public bool IsAvailable
        {
            get
            {
                var result = CheckAvailability();
                return result.Available;
            }
        }

        public QBFCDataProvider(IRedactingLogger logger = null, double? maxQBXMLVersion = null)
        {
            _logger = logger;
            _maxQBXMLVersion = maxQBXMLVersion;
        }

        public BackendDetectionResult CheckAvailability()
        {
            return QBDataProviderFactory.CheckQBFCAvailability(_logger);
        }

        public async Task<bool> ConnectAsync(string companyFilePath = null, CancellationToken ct = default)
        {
            try
            {
                _logger?.Log(LogLevel.Info, "Connecting to QuickBooks via QBFC SDK...");

                // Create session manager
                _sessionManager = new QBSessionManager(_maxQBXMLVersion, _logger);

                // Begin session on STA thread
                await Task.Run(() =>
                {
                    _sessionManager.BeginSession(
                        companyFilePath ?? "",
                        QBFC16Lib.ENOpenMode.omDontCare);
                }, ct);

                // Get and cache company info
                _cachedCompanyInfo = _sessionManager.GetCompanyInfo();

                _logger?.Log(LogLevel.Info, "Connected to QuickBooks via QBFC");
                _logger?.Log(LogLevel.Info, "Company: {0}", _cachedCompanyInfo.CompanyName);
                _logger?.Log(LogLevel.Info, "QB Version: {0}", _sessionManager.GetQBVersion());

                // Create extractor
                _extractor = new QBDataExtractor(_sessionManager, _logger);

                return true;
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Error, "Failed to connect via QBFC: {0}", ex.Message);
                Disconnect();
                throw new QBException("QBFC connection failed", ex.Message, -1, ex);
            }
        }

        public void Disconnect()
        {
            try
            {
                if (_sessionManager != null)
                {
                    _sessionManager.EndSession();
                    _sessionManager.CloseConnection();
                    _sessionManager.Dispose();
                    _sessionManager = null;
                }
                _extractor = null;
                _cachedCompanyInfo = null;
                _logger?.Log(LogLevel.Info, "Disconnected from QuickBooks");
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Error during disconnect: {0}", ex.Message);
            }
        }

        public Task<QBCompanyInfo> GetCompanyInfoAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            return Task.FromResult(_cachedCompanyInfo ?? _sessionManager.GetCompanyInfo());
        }

        public string GetVersion()
        {
            return _sessionManager?.GetQBVersion() ?? "QBFC";
        }

        #region List Extraction Methods

        public async Task<List<QBAccount>> ExtractAccountsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractAccounts(), ct);
        }

        public async Task<List<QBCustomer>> ExtractCustomersAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractCustomers(), ct);
        }

        public async Task<List<QBVendor>> ExtractVendorsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractVendors(), ct);
        }

        public async Task<List<QBEmployee>> ExtractEmployeesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractEmployees(), ct);
        }

        public async Task<List<QBItem>> ExtractItemsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractItems(), ct);
        }

        public async Task<List<QBClass>> ExtractClassesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractClasses(), ct);
        }

        public async Task<List<QBPaymentMethod>> ExtractPaymentMethodsAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            return await Task.Run(() => _extractor.ExtractPaymentMethods(), ct);
        }

        public async Task<List<QBTerms>> ExtractTermsAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            return await Task.Run(() => _extractor.ExtractTerms(), ct);
        }

        public async Task<List<QBSalesTaxCode>> ExtractSalesTaxCodesAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            return await Task.Run(() => _extractor.ExtractSalesTaxCodes(), ct);
        }

        public async Task<List<QBCustomerType>> ExtractCustomerTypesAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            return await Task.Run(() => _extractor.ExtractCustomerTypes(), ct);
        }

        public async Task<List<QBVendorType>> ExtractVendorTypesAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            return await Task.Run(() => _extractor.ExtractVendorTypes(), ct);
        }

        public async Task<List<QBCurrency>> ExtractCurrenciesAsync(CancellationToken ct = default)
        {
            EnsureConnected();
            return await Task.Run(() => _extractor.ExtractCurrencies(), ct);
        }

        #endregion

        #region Transaction Extraction Methods

        public async Task<List<QBInvoice>> ExtractInvoicesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractInvoices(), ct);
        }

        public async Task<List<QBBill>> ExtractBillsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractBills(), ct);
        }

        public async Task<List<QBCheck>> ExtractChecksAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractChecks(), ct);
        }

        public async Task<List<QBJournalEntry>> ExtractJournalEntriesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractJournalEntries(), ct);
        }

        public async Task<List<QBDeposit>> ExtractDepositsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractDeposits(), ct);
        }

        public async Task<List<QBCreditMemo>> ExtractCreditMemosAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractCreditMemos(), ct);
        }

        public async Task<List<QBSalesReceipt>> ExtractSalesReceiptsAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractSalesReceipts(), ct);
        }

        public async Task<List<QBEstimate>> ExtractEstimatesAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractEstimates(), ct);
        }

        public async Task<List<QBPurchaseOrder>> ExtractPurchaseOrdersAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractPurchaseOrders(), ct);
        }

        public async Task<List<QBSalesOrder>> ExtractSalesOrdersAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();
            ConfigureIncremental(modifiedSince);
            return await Task.Run(() => _extractor.ExtractSalesOrders(), ct);
        }

        #endregion

        #region Full Extraction

        /// <summary>
        /// Extract all data using the proven QBDataExtractor
        /// This provides the most complete and reliable extraction
        /// </summary>
        public async Task<QBExtractedData> ExtractAllDataAsync(DateTime? modifiedSince = null, CancellationToken ct = default)
        {
            EnsureConnected();

            _logger?.Log(LogLevel.Info, "Starting full extraction via QBFC SDK...");

            // Configure incremental sync
            if (modifiedSince.HasValue)
            {
                _extractor.SetIncrementalSyncDate(modifiedSince.Value);
            }

            // Use the existing proven ExtractAllData method
            var data = await Task.Run(() => _extractor.ExtractAllData(), ct);

            _logger?.Log(LogLevel.Info, "QBFC extraction complete");
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
            if (_extractor == null)
            {
                throw new InvalidOperationException("Extractor not initialized.");
            }
        }

        private void ConfigureIncremental(DateTime? modifiedSince)
        {
            if (modifiedSince.HasValue)
            {
                _extractor.SetIncrementalSyncDate(modifiedSince.Value);
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
