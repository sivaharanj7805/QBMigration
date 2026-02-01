using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Extraction backend type enumeration
    /// </summary>
    public enum ExtractionBackend
    {
        /// <summary>Official QBFC16 SDK via COM</summary>
        QBFC,
        /// <summary>QODBC Driver (third-party ODBC)</summary>
        QODBC,
        /// <summary>Auto-detect best available backend</summary>
        Auto
    }

    /// <summary>
    /// Result of backend detection
    /// </summary>
    public class BackendDetectionResult
    {
        public bool Available { get; set; }
        public ExtractionBackend Backend { get; set; }
        public string Version { get; set; }
        public string Message { get; set; }
        public Exception Error { get; set; }
    }

    /// <summary>
    /// Abstraction layer for QuickBooks data extraction
    /// Enables multiple backend implementations (QBFC SDK, QODBC, etc.)
    /// </summary>
    public interface IQBDataProvider : IDisposable
    {
        /// <summary>Name of this provider implementation</summary>
        string ProviderName { get; }

        /// <summary>Check if this provider is available on the current system</summary>
        bool IsAvailable { get; }

        /// <summary>Get detailed availability information</summary>
        BackendDetectionResult CheckAvailability();

        /// <summary>Connect to QuickBooks</summary>
        Task<bool> ConnectAsync(string companyFilePath = null, CancellationToken ct = default);

        /// <summary>Disconnect from QuickBooks</summary>
        void Disconnect();

        /// <summary>Check if currently connected</summary>
        bool IsConnected { get; }

        /// <summary>Get company information</summary>
        Task<QBCompanyInfo> GetCompanyInfoAsync(CancellationToken ct = default);

        /// <summary>Get QuickBooks version string</summary>
        string GetVersion();

        // === List Extraction Methods ===
        Task<List<QBAccount>> ExtractAccountsAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBCustomer>> ExtractCustomersAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBVendor>> ExtractVendorsAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBEmployee>> ExtractEmployeesAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBItem>> ExtractItemsAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBClass>> ExtractClassesAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBPaymentMethod>> ExtractPaymentMethodsAsync(CancellationToken ct = default);
        Task<List<QBTerms>> ExtractTermsAsync(CancellationToken ct = default);
        Task<List<QBSalesTaxCode>> ExtractSalesTaxCodesAsync(CancellationToken ct = default);
        Task<List<QBCustomerType>> ExtractCustomerTypesAsync(CancellationToken ct = default);
        Task<List<QBVendorType>> ExtractVendorTypesAsync(CancellationToken ct = default);
        Task<List<QBCurrency>> ExtractCurrenciesAsync(CancellationToken ct = default);

        // === Transaction Extraction Methods ===
        Task<List<QBInvoice>> ExtractInvoicesAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBBill>> ExtractBillsAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBCheck>> ExtractChecksAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBJournalEntry>> ExtractJournalEntriesAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBDeposit>> ExtractDepositsAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBCreditMemo>> ExtractCreditMemosAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBSalesReceipt>> ExtractSalesReceiptsAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBEstimate>> ExtractEstimatesAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBPurchaseOrder>> ExtractPurchaseOrdersAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
        Task<List<QBSalesOrder>> ExtractSalesOrdersAsync(DateTime? modifiedSince = null, CancellationToken ct = default);

        // === Full Extraction ===
        Task<QBExtractedData> ExtractAllDataAsync(DateTime? modifiedSince = null, CancellationToken ct = default);
    }

    /// <summary>
    /// Factory for creating QBDataProvider instances
    /// </summary>
    public static class QBDataProviderFactory
    {
        /// <summary>
        /// Detect all available backends on the system
        /// </summary>
        public static List<BackendDetectionResult> DetectAvailableBackends(IRedactingLogger logger = null)
        {
            var results = new List<BackendDetectionResult>();

            // Check QBFC SDK
            results.Add(CheckQBFCAvailability(logger));

            // Check QODBC
            results.Add(CheckQODBCAvailability(logger));

            return results;
        }

        /// <summary>
        /// Check if QBFC SDK is available
        /// </summary>
        public static BackendDetectionResult CheckQBFCAvailability(IRedactingLogger logger = null)
        {
            var result = new BackendDetectionResult
            {
                Backend = ExtractionBackend.QBFC
            };

            try
            {
                // Try to get the QBFC16 COM type
                var qbType = Type.GetTypeFromProgID("QBFC16.QBSessionManager");
                if (qbType != null)
                {
                    result.Available = true;
                    result.Version = "QBFC16";
                    result.Message = "QuickBooks Desktop SDK (QBFC16) is installed";
                    logger?.Log(LogLevel.Info, "QBFC16 SDK detected and available");
                }
                else
                {
                    result.Available = false;
                    result.Message = "QuickBooks Desktop SDK (QBFC16) is not installed";
                    logger?.Log(LogLevel.Warning, "QBFC16 SDK not detected");
                }
            }
            catch (Exception ex)
            {
                result.Available = false;
                result.Error = ex;
                result.Message = $"Error checking QBFC16: {ex.Message}";
                logger?.Log(LogLevel.Warning, "Error checking QBFC16 availability: {0}", ex.Message);
            }

            return result;
        }

        /// <summary>
        /// Check if QODBC is available
        /// </summary>
        public static BackendDetectionResult CheckQODBCAvailability(IRedactingLogger logger = null)
        {
            var result = new BackendDetectionResult
            {
                Backend = ExtractionBackend.QODBC
            };

            try
            {
                // Check for QODBC driver in registry or ODBC drivers list
                bool found = false;
                string version = null;

                // Method 1: Check ODBC drivers
                try
                {
                    using (var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                        @"SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers"))
                    {
                        if (key != null)
                        {
                            var names = key.GetValueNames();
                            foreach (var name in names)
                            {
                                if (name.Contains("QODBC") || name.Contains("QuickBooks"))
                                {
                                    found = true;
                                    version = name;
                                    break;
                                }
                            }
                        }
                    }
                }
                catch (System.Security.SecurityException secEx)
                {
                    // Registry access denied - expected in some environments, continue with other methods
                    logger?.Log(LogLevel.Debug, "Registry access denied (64-bit ODBC): {0}", secEx.Message);
                }
                catch (UnauthorizedAccessException authEx)
                {
                    // Registry access denied - expected in some environments, continue with other methods
                    logger?.Log(LogLevel.Debug, "Registry unauthorized (64-bit ODBC): {0}", authEx.Message);
                }

                // Method 2: Check 32-bit ODBC drivers (for 32-bit apps)
                if (!found)
                {
                    try
                    {
                        using (var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                            @"SOFTWARE\WOW6432Node\ODBC\ODBCINST.INI\ODBC Drivers"))
                        {
                            if (key != null)
                            {
                                var names = key.GetValueNames();
                                foreach (var name in names)
                                {
                                    if (name.Contains("QODBC") || name.Contains("QuickBooks"))
                                    {
                                        found = true;
                                        version = name;
                                        break;
                                    }
                                }
                            }
                        }
                    }
                    catch (System.Security.SecurityException secEx)
                    {
                        // Registry access denied - expected in some environments
                        logger?.Log(LogLevel.Debug, "Registry access denied (32-bit ODBC): {0}", secEx.Message);
                    }
                    catch (UnauthorizedAccessException authEx)
                    {
                        // Registry access denied - expected in some environments
                        logger?.Log(LogLevel.Debug, "Registry unauthorized (32-bit ODBC): {0}", authEx.Message);
                    }
                }

                if (found)
                {
                    result.Available = true;
                    result.Version = version;
                    result.Message = $"QODBC Driver detected: {version}";
                    logger?.Log(LogLevel.Info, "QODBC driver detected: {0}", version);
                }
                else
                {
                    result.Available = false;
                    result.Message = "QODBC Driver is not installed";
                    logger?.Log(LogLevel.Warning, "QODBC driver not detected");
                }
            }
            catch (Exception ex)
            {
                result.Available = false;
                result.Error = ex;
                result.Message = $"Error checking QODBC: {ex.Message}";
                logger?.Log(LogLevel.Warning, "Error checking QODBC availability: {0}", ex.Message);
            }

            return result;
        }

        /// <summary>
        /// Create a data provider with the specified backend
        /// </summary>
        public static IQBDataProvider CreateProvider(
            ExtractionBackend backend,
            IRedactingLogger logger = null,
            double? maxQBXMLVersion = null)
        {
            switch (backend)
            {
#if USE_QBFC
                case ExtractionBackend.QBFC:
                    return new QBFCDataProvider(logger, maxQBXMLVersion);
#endif

                case ExtractionBackend.QODBC:
                    return new QODBCDataProvider(logger);

                case ExtractionBackend.Auto:
                default:
                    return CreateBestAvailableProvider(logger, maxQBXMLVersion);
            }
        }

        /// <summary>
        /// Create the best available provider based on system detection
        /// Priority: QODBC (primary), QBFC (if available)
        /// </summary>
        public static IQBDataProvider CreateBestAvailableProvider(
            IRedactingLogger logger = null,
            double? maxQBXMLVersion = null)
        {
            logger?.Log(LogLevel.Info, "Auto-detecting best available QuickBooks backend...");

#if USE_QBFC
            // Try QBFC first if compiled with SDK support
            var qbfcResult = CheckQBFCAvailability(logger);
            if (qbfcResult.Available)
            {
                logger?.Log(LogLevel.Info, "Using QBFC backend (SDK detected)");
                return new QBFCDataProvider(logger, maxQBXMLVersion);
            }
#endif

            // Try QODBC (primary backend)
            var qodbcResult = CheckQODBCAvailability(logger);
            if (qodbcResult.Available)
            {
                logger?.Log(LogLevel.Info, "Using QODBC backend");
                return new QODBCDataProvider(logger);
            }

            // No backend available - throw helpful error
            throw new QBBackendNotFoundException(
                "No QuickBooks extraction backend found.\n\n" +
                "Please install QODBC Driver:\n\n" +
                "  1. Go to: https://qodbc.com/qodbc-downloads/\n" +
                "  2. Download 'QODBC Desktop Read-Only Driver' (FREE)\n" +
                "  3. Run installer as Administrator\n" +
                "  4. Restart your computer\n" +
                "  5. Run this application again\n\n" +
                "Note: The Intuit QBFC SDK is no longer available for download.\n" +
                "QODBC is the recommended solution and works with all QB Desktop versions.\n\n" +
                "After installation, ensure QuickBooks Desktop is running with your company file open.");
        }
    }

    /// <summary>
    /// Exception thrown when no QuickBooks backend is available
    /// </summary>
    public class QBBackendNotFoundException : Exception
    {
        public QBBackendNotFoundException(string message) : base(message) { }
    }
}
