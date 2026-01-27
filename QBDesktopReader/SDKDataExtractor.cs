#if USE_SDK
using System;
using System.Threading;
using System.Threading.Tasks;
using QBFC16Lib;

namespace QBDesktopExtractor
{
    /// <summary>
    /// SDK-based data extractor wrapper
    /// Wraps existing QBSessionManager and QBDataExtractor with IDataExtractor interface
    /// Requires: QuickBooks Desktop SDK (QBFC16)
    /// </summary>
    public class SDKDataExtractor : IDataExtractor
    {
        private readonly IRedactingLogger _logger;
        private QBSessionManager _sessionManager;
        private QBDataExtractor _extractor;
        private bool _disposed = false;
        private DateTime? _incrementalFromDate = null;
        private QBCompanyInfo _companyInfo;

        public string BackendName => "SDK (QBFC16)";
        public bool IsAvailable => DataExtractorFactory.IsSDKAvailable();
        public ExtractionRunSummary RunSummary => _extractor?.RunSummary;

        public bool ContinueOnEntityError
        {
            get => _extractor?.ContinueOnEntityError ?? true;
            set
            {
                if (_extractor != null)
                    _extractor.ContinueOnEntityError = value;
            }
        }

        public SDKDataExtractor(IRedactingLogger logger = null)
        {
            _logger = logger;
        }

        public void Connect(string companyFilePath = null)
        {
            if (_sessionManager != null)
            {
                _logger?.Log(LogLevel.Warning, "Already connected to QuickBooks via SDK");
                return;
            }

            _logger?.Log(LogLevel.Info, "Connecting to QuickBooks via SDK (QBFC16)...");

            try
            {
                _sessionManager = new QBSessionManager(null, _logger);
                _sessionManager.BeginSession(companyFilePath ?? "", ENOpenMode.omDontCare);

                var companyInfo = _sessionManager.GetCompanyInfo();
                _companyInfo = new QBCompanyInfo
                {
                    CompanyName = companyInfo.CompanyName,
                    LegalCompanyName = companyInfo.LegalCompanyName,
                    Address = companyInfo.Address,
                    City = companyInfo.City,
                    State = companyInfo.State,
                    PostalCode = companyInfo.PostalCode,
                    Country = companyInfo.Country,
                    Phone = companyInfo.Phone,
                    Fax = companyInfo.Fax,
                    Email = companyInfo.Email,
                    CompanyFilePath = "[REDACTED]"
                };

                _extractor = new QBDataExtractor(_sessionManager, _logger);

                _logger?.Log(LogLevel.Info, "Connected to: {0}", _companyInfo.CompanyName);
                _logger?.Log(LogLevel.Info, "QB Version: {0}", _sessionManager.GetQBVersion());
            }
            catch (Exception ex)
            {
                _sessionManager?.Dispose();
                _sessionManager = null;
                throw new InvalidOperationException(
                    "Could not connect to QuickBooks via SDK.\n\n" +
                    "Ensure:\n" +
                    "1. QuickBooks Desktop is running and logged into a company file\n" +
                    "2. Approve the connection request when prompted in QuickBooks\n" +
                    "3. QuickBooks SDK (QBFC16) is properly installed\n\n" +
                    $"Error: {ex.Message}", ex);
            }
        }

        public void Disconnect()
        {
            if (_sessionManager != null)
            {
                try
                {
                    _sessionManager.EndSession();
                    _sessionManager.CloseConnection();
                    _sessionManager.Dispose();
                    _sessionManager = null;
                    _extractor = null;
                    _logger?.Log(LogLevel.Info, "Disconnected from QuickBooks");
                }
                catch (Exception ex)
                {
                    _logger?.Log(LogLevel.Warning, "Error during disconnect: {0}", ex.Message);
                }
            }
        }

        public QBCompanyInfo GetCompanyInfo()
        {
            return _companyInfo ?? new QBCompanyInfo { CompanyName = "Not Connected" };
        }

        public string GetQBVersion()
        {
            return _sessionManager?.GetQBVersion() ?? "Unknown";
        }

        public void SetIncrementalSyncDate(DateTime fromDate)
        {
            _incrementalFromDate = fromDate;
            _extractor?.SetIncrementalSyncDate(fromDate);
            _logger?.Log(LogLevel.Info, "INCREMENTAL SYNC MODE: Extracting only records modified since {0:yyyy-MM-dd}", fromDate);
        }

        public QBExtractedData ExtractAllData()
        {
            EnsureConnected();

            if (_incrementalFromDate.HasValue && _extractor != null)
            {
                _extractor.SetIncrementalSyncDate(_incrementalFromDate.Value);
            }

            return _extractor.ExtractAllData();
        }

        public Task<RunManifest> ExtractAllDataToNDJSONAsync(
            string outputDirectory,
            string sessionId,
            string configHash = null,
            CancellationToken ct = default)
        {
            EnsureConnected();

            if (_incrementalFromDate.HasValue && _extractor != null)
            {
                _extractor.SetIncrementalSyncDate(_incrementalFromDate.Value);
            }

            return _extractor.ExtractAllDataToNDJSONAsync(outputDirectory, sessionId, configHash, ct);
        }

        private void EnsureConnected()
        {
            if (_sessionManager == null || !_sessionManager.IsSessionOpen)
            {
                throw new InvalidOperationException("Not connected to QuickBooks. Call Connect() first.");
            }
        }

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
#endif
