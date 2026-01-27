using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Backend type for data extraction
    /// </summary>
    public enum ExtractorBackend
    {
        /// <summary>Auto-detect best available backend</summary>
        Auto,
        /// <summary>QuickBooks SDK (QBFC16) - requires SDK installation</summary>
        SDK,
        /// <summary>QODBC driver - requires QODBC installation</summary>
        QODBC
    }

    /// <summary>
    /// Abstraction for QuickBooks data extraction
    /// Enables multiple backends (SDK, QODBC) with same interface
    /// </summary>
    public interface IDataExtractor : IDisposable
    {
        /// <summary>
        /// Name of this extractor backend
        /// </summary>
        string BackendName { get; }

        /// <summary>
        /// Whether this backend is available on the current system
        /// </summary>
        bool IsAvailable { get; }

        /// <summary>
        /// Connect to QuickBooks
        /// </summary>
        void Connect(string companyFilePath = null);

        /// <summary>
        /// Disconnect from QuickBooks
        /// </summary>
        void Disconnect();

        /// <summary>
        /// Get company information
        /// </summary>
        QBCompanyInfo GetCompanyInfo();

        /// <summary>
        /// Get QuickBooks version string
        /// </summary>
        string GetQBVersion();

        /// <summary>
        /// Set incremental sync date - only extract records modified since this date
        /// </summary>
        void SetIncrementalSyncDate(DateTime fromDate);

        /// <summary>
        /// Extract all data to a single structure
        /// </summary>
        QBExtractedData ExtractAllData();

        /// <summary>
        /// Extract all data to NDJSON files with checkpointing
        /// </summary>
        Task<RunManifest> ExtractAllDataToNDJSONAsync(
            string outputDirectory,
            string sessionId,
            string configHash = null,
            CancellationToken ct = default);

        /// <summary>
        /// Get extraction run summary
        /// </summary>
        ExtractionRunSummary RunSummary { get; }

        /// <summary>
        /// Whether to continue extraction if an entity fails
        /// </summary>
        bool ContinueOnEntityError { get; set; }
    }

    /// <summary>
    /// Factory for creating appropriate data extractor based on available backends
    /// </summary>
    public static class DataExtractorFactory
    {
        /// <summary>
        /// Detect which backends are available on the current system
        /// </summary>
        public static List<ExtractorBackend> GetAvailableBackends()
        {
            var available = new List<ExtractorBackend>();

            // Check SDK availability
            if (IsSDKAvailable())
            {
                available.Add(ExtractorBackend.SDK);
            }

            // Check QODBC availability
            if (IsQODBCAvailable())
            {
                available.Add(ExtractorBackend.QODBC);
            }

            return available;
        }

        /// <summary>
        /// Check if QuickBooks SDK (QBFC16) is installed
        /// </summary>
        public static bool IsSDKAvailable()
        {
            try
            {
                var qbType = Type.GetTypeFromProgID("QBFC16.QBSessionManager");
                return qbType != null;
            }
            catch
            {
                return false;
            }
        }

        /// <summary>
        /// Check if QODBC driver is installed
        /// </summary>
        public static bool IsQODBCAvailable()
        {
            try
            {
                // Check for QODBC driver registration in ODBC
                using (var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                    @"SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers"))
                {
                    if (key != null)
                    {
                        var drivers = key.GetValueNames();
                        foreach (var driver in drivers)
                        {
                            if (driver.Contains("QODBC") || driver.Contains("QuickBooks"))
                            {
                                return true;
                            }
                        }
                    }
                }

                // Also check 32-bit registry on 64-bit systems
                using (var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                    @"SOFTWARE\WOW6432Node\ODBC\ODBCINST.INI\ODBC Drivers"))
                {
                    if (key != null)
                    {
                        var drivers = key.GetValueNames();
                        foreach (var driver in drivers)
                        {
                            if (driver.Contains("QODBC") || driver.Contains("QuickBooks"))
                            {
                                return true;
                            }
                        }
                    }
                }

                return false;
            }
            catch
            {
                return false;
            }
        }

        /// <summary>
        /// Create an appropriate data extractor
        /// </summary>
        public static IDataExtractor Create(
            ExtractorBackend preferredBackend,
            IRedactingLogger logger = null)
        {
            var available = GetAvailableBackends();

            if (available.Count == 0)
            {
                throw new InvalidOperationException(
                    "No QuickBooks extraction backend available.\n\n" +
                    "You need ONE of the following:\n" +
                    "1. QuickBooks SDK (QBFC16) - Download from Intuit Developer Portal\n" +
                    "2. QODBC Driver - Download from https://qodbc.com/qodbc-downloads/\n\n" +
                    "QODBC is recommended for most users (free for read operations).");
            }

            ExtractorBackend backendToUse;

            if (preferredBackend == ExtractorBackend.Auto)
            {
                // Prefer SDK if available (more reliable), otherwise QODBC
                backendToUse = available.Contains(ExtractorBackend.SDK)
                    ? ExtractorBackend.SDK
                    : available[0];
            }
            else
            {
                if (!available.Contains(preferredBackend))
                {
                    throw new InvalidOperationException(
                        $"Requested backend '{preferredBackend}' is not available.\n" +
                        $"Available backends: {string.Join(", ", available)}");
                }
                backendToUse = preferredBackend;
            }

            logger?.Log(LogLevel.Info, "Using extraction backend: {0}", backendToUse);

            switch (backendToUse)
            {
                case ExtractorBackend.SDK:
#if USE_SDK
                    return new SDKDataExtractor(logger);
#else
                    throw new InvalidOperationException(
                        "SDK backend was requested but this build was compiled without SDK support.\n" +
                        "Use a build with SDK support or switch to QODBC backend.");
#endif

                case ExtractorBackend.QODBC:
                    return new QODBCDataExtractor(logger);

                default:
                    throw new ArgumentException($"Unknown backend: {backendToUse}");
            }
        }

        /// <summary>
        /// Print diagnostic information about available backends
        /// </summary>
        public static void PrintDiagnostics(IRedactingLogger logger = null)
        {
            var log = logger ?? new RedactingConsoleLogger(new RedactionConfig(), LogLevel.Info);

            log.Log(LogLevel.Info, "=== QuickBooks Backend Diagnostics ===");

            // SDK Check
            bool sdkAvailable = IsSDKAvailable();
            log.Log(sdkAvailable ? LogLevel.Info : LogLevel.Warning,
                "QuickBooks SDK (QBFC16): {0}", sdkAvailable ? "AVAILABLE" : "NOT FOUND");

            // QODBC Check
            bool qodbcAvailable = IsQODBCAvailable();
            log.Log(qodbcAvailable ? LogLevel.Info : LogLevel.Warning,
                "QODBC Driver: {0}", qodbcAvailable ? "AVAILABLE" : "NOT FOUND");

            // Recommendations
            if (!sdkAvailable && !qodbcAvailable)
            {
                log.Log(LogLevel.Error, "No backend available! Install one of the following:");
                log.Log(LogLevel.Error, "  1. QODBC (recommended): https://qodbc.com/qodbc-downloads/");
                log.Log(LogLevel.Error, "  2. QuickBooks SDK: https://developer.intuit.com/");
            }
            else
            {
                log.Log(LogLevel.Info, "Recommended backend: {0}",
                    sdkAvailable ? "SDK (most reliable)" : "QODBC");
            }

            log.Log(LogLevel.Info, "======================================");
        }
    }
}
