#if USE_QBFC

using System;
using System.Linq;
using System.Threading;
using QBFC16Lib;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Interface for QuickBooks Session Manager - enables unit testing with mocks
    /// </summary>
    public interface IQBSessionManager : IDisposable
    {
        void BeginSession(string qbFilePath, ENOpenMode openMode);
        void EndSession();
        void CloseConnection();
        IMsgSetRequest CreateMsgSetRequest();
        IMsgSetRequest CreateMsgSetRequest(string country, short majorVersion, short minorVersion);
        IMsgSetResponse DoRequests(IMsgSetRequest requestMsgSet);
        QBRequestResult DoRequestsWithResult(IMsgSetRequest requestMsgSet);
        CompanyInfo GetCompanyInfo();
        string GetQBVersion();
        double GetQBXMLVersion();
        QBCapabilities GetCapabilities();
        DiagnosticsSnapshot GetDiagnosticsSnapshot(bool includePII = false);
        bool IsSessionOpen { get; }
        bool IsDisposed { get; }
    }

    /// <summary>
    /// Result wrapper for QBFC requests with full status information
    /// </summary>
    public class QBRequestResult
    {
        public bool Success { get; set; }
        public int StatusCode { get; set; }
        public string StatusMessage { get; set; }
        public string StatusSeverity { get; set; }
        public IMsgSetResponse Response { get; set; }
        public string OperationContext { get; set; }
        public Exception Exception { get; set; }
    }

    /// <summary>
    /// QuickBooks capabilities detection result
    /// </summary>
    public class QBCapabilities
    {
        public bool SupportsMultiCurrency { get; set; }
        public bool SupportsInventory { get; set; }
        public bool SupportsPayroll { get; set; }
        public bool SupportsSalesOrders { get; set; }
        public bool SupportsEstimates { get; set; }
        public string Edition { get; set; }  // Pro, Premier, Enterprise
        public double QBXMLVersion { get; set; }
        public string Country { get; set; }
    }

    /// <summary>
    /// Telemetry-safe diagnostics snapshot
    /// </summary>
    public class DiagnosticsSnapshot
    {
        public string SessionId { get; set; }
        public bool IsConnected { get; set; }
        public bool IsSessionOpen { get; set; }
        public double QBXMLVersion { get; set; }
        public string Country { get; set; }
        public DateTime? SessionStartTime { get; set; }
        public string CompanyNameHash { get; set; }  // Never raw company name
        public string CompanyFilePath { get; set; }  // Only if includePII=true
    }

    /// <summary>
    /// Thread-safe QuickBooks Session Manager with STA Thread Affinity
    /// 
    /// CRITICAL: This manages the COM connection to QuickBooks Desktop
    /// COM objects are NOT thread-safe - all QBFC calls MUST execute on a dedicated STA thread
    /// 
    /// v4.3 FIXES:
    /// - STA thread affinity guaranteed via dedicated STA thread
    /// - ObjectDisposedException thrown after Dispose()
    /// - IQBSessionManager interface for unit testing
    /// - Configurable country code (not hardcoded "US")
    /// - Version validation in CreateMsgSetRequest
    /// - Full status codes in DoRequestsWithResult
    /// - Capability detection without exceptions
    /// - Telemetry-safe diagnostics
    /// </summary>
    public class QBSessionManager : IQBSessionManager
    {
        private QBFC16Lib.QBSessionManager _qbfcSessionManager;
        private string _companyFilePath;
        private bool _isConnected = false;
        private bool _isSessionOpen = false;
        private bool _disposed = false;
        private readonly object _lockObject = new object();
        private double _qbxmlVersion = 13.0;
        private readonly string _sessionId;
        private DateTime? _sessionStartTime;
        private readonly IRedactingLogger _logger;
        
        // Configurable settings
        private readonly string _country;
        private readonly double? _maxQBXMLVersion;
        
        // STA Thread for COM operations
        private Thread _staThread;
        private readonly AutoResetEvent _workAvailable = new AutoResetEvent(false);
        private readonly AutoResetEvent _workComplete = new AutoResetEvent(false);
        private Action _pendingWork;
        private Exception _pendingException;
        private bool _staThreadRunning = true;

        public bool IsSessionOpen 
        { 
            get 
            { 
                ThrowIfDisposed();
                lock (_lockObject) return _isSessionOpen; 
            } 
        }

        public bool IsDisposed => _disposed;

        /// <summary>
        /// Create a new QBSessionManager with default settings
        /// </summary>
        public QBSessionManager() : this(null, null, "US") { }

        /// <summary>
        /// Create a new QBSessionManager with optional version limit and logger
        /// </summary>
        public QBSessionManager(double? maxQBXMLVersion, IRedactingLogger logger, string country = "US")
        {
            _maxQBXMLVersion = maxQBXMLVersion;
            _logger = logger;
            _country = country ?? "US";
            _sessionId = Guid.NewGuid().ToString("N").Substring(0, 8);
            
            // Start dedicated STA thread for all COM operations
            StartSTAThread();
            
            // Create the QBFC COM object on the STA thread
            ExecuteOnSTAThread(() =>
            {
                _qbfcSessionManager = new QBFC16Lib.QBSessionManager();
            });
        }

        /// <summary>
        /// Start the dedicated STA thread for COM operations
        /// </summary>
        private void StartSTAThread()
        {
            _staThread = new Thread(STAThreadProc)
            {
                Name = $"QBFC-STA-{_sessionId}",
                IsBackground = true
            };
            _staThread.SetApartmentState(ApartmentState.STA);
            _staThread.Start();
        }

        /// <summary>
        /// STA thread main loop - processes work items sequentially
        /// </summary>
        private void STAThreadProc()
        {
            while (_staThreadRunning)
            {
                _workAvailable.WaitOne();
                
                if (!_staThreadRunning) break;
                
                try
                {
                    _pendingWork?.Invoke();
                    _pendingException = null;
                }
                catch (Exception ex)
                {
                    _pendingException = ex;
                }
                finally
                {
                    _workComplete.Set();
                }
            }
        }

        /// <summary>
        /// Execute an action on the STA thread and wait for completion
        /// </summary>
        private void ExecuteOnSTAThread(Action action)
        {
            if (Thread.CurrentThread == _staThread)
            {
                // Already on STA thread, execute directly
                action();
                return;
            }

            lock (_lockObject)
            {
                _pendingWork = action;
                _workAvailable.Set();
                _workComplete.WaitOne();
                
                if (_pendingException != null)
                {
                    throw _pendingException;
                }
            }
        }

        /// <summary>
        /// Execute a function on the STA thread and return result
        /// </summary>
        private T ExecuteOnSTAThread<T>(Func<T> func)
        {
            T result = default;
            ExecuteOnSTAThread(() => { result = func(); });
            return result;
        }

        /// <summary>
        /// Throw ObjectDisposedException if disposed
        /// </summary>
        private void ThrowIfDisposed()
        {
            if (_disposed)
            {
                throw new ObjectDisposedException(nameof(QBSessionManager), 
                    "Cannot access a disposed QBSessionManager");
            }
        }

        /// <summary>
        /// Begin a session with QuickBooks (idempotent)
        /// </summary>
        public void BeginSession(string qbFilePath, ENOpenMode openMode)
        {
            ThrowIfDisposed();
            
            ExecuteOnSTAThread(() =>
            {
                // Idempotent: repeated calls are safe
                if (_isSessionOpen)
                {
                    _logger?.Log(LogLevel.Warning, "Session already open - skipping BeginSession");
                    return;
                }

                try
                {
                    if (!_isConnected)
                    {
                        _qbfcSessionManager.OpenConnection2("", 
                            "QuickBooks Desktop Extractor v4.3", 
                            ENConnectionType.ctLocalQBD);
                        _isConnected = true;
                    }

                    _qbfcSessionManager.BeginSession(qbFilePath, openMode);
                    _isSessionOpen = true;
                    _sessionStartTime = DateTime.UtcNow;
                    _companyFilePath = qbFilePath;
                    
                    // Cache QBXML version after session is open
                    _qbxmlVersion = GetQBXMLVersionSafe();
                    
                    _logger?.Log(LogLevel.Info, "QuickBooks session opened. QBXML version: {0}", _qbxmlVersion);
                }
                catch (Exception ex)
                {
                    CleanupConnectionInternal();
                    throw new QBException("Failed to begin QuickBooks session", ex.Message, -1, ex);
                }
            });
        }

        /// <summary>
        /// End the current session (idempotent)
        /// </summary>
        public void EndSession()
        {
            ThrowIfDisposed();
            
            ExecuteOnSTAThread(() =>
            {
                try
                {
                    if (_isSessionOpen)
                    {
                        _qbfcSessionManager.EndSession();
                        _isSessionOpen = false;
                        _logger?.Log(LogLevel.Info, "QuickBooks session ended");
                    }
                }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"Warning: Error ending session: {ex.Message}");
                    _isSessionOpen = false;
                }
            });
        }

        /// <summary>
        /// Close the connection (idempotent)
        /// </summary>
        public void CloseConnection()
        {
            ThrowIfDisposed();
            
            ExecuteOnSTAThread(CleanupConnectionInternal);
        }

        private void CleanupConnectionInternal()
        {
            try
            {
                if (_isSessionOpen)
                {
                    try { _qbfcSessionManager.EndSession(); } catch (System.Runtime.InteropServices.COMException) { /* Expected during cleanup */ }
                    _isSessionOpen = false;
                }

                if (_isConnected)
                {
                    try { _qbfcSessionManager.CloseConnection(); } catch (System.Runtime.InteropServices.COMException) { /* Expected during cleanup */ }
                    _isConnected = false;
                }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Warning during cleanup: {ex.Message}");
            }
        }

        /// <summary>
        /// Create a new message set request with default version
        /// </summary>
        public IMsgSetRequest CreateMsgSetRequest()
        {
            ThrowIfDisposed();
            return CreateMsgSetRequest(_country, (short)_qbxmlVersion, 0);
        }

        /// <summary>
        /// Create a new message set request with explicit version
        /// Validates version combinations before creating request
        /// </summary>
        public IMsgSetRequest CreateMsgSetRequest(string country, short majorVersion, short minorVersion)
        {
            ThrowIfDisposed();
            
            // Validate inputs
            if (string.IsNullOrEmpty(country))
                throw new ArgumentNullException(nameof(country));
            
            if (majorVersion < 1 || majorVersion > 16)
                throw new ArgumentOutOfRangeException(nameof(majorVersion), 
                    $"QBXML major version must be 1-16, got {majorVersion}");

            if (minorVersion < 0)
                throw new ArgumentOutOfRangeException(nameof(minorVersion),
                    $"QBXML minor version cannot be negative, got {minorVersion}");

            // Validate against max version if configured
            double requestedVersion = majorVersion + (minorVersion / 10.0);
            if (_maxQBXMLVersion.HasValue && requestedVersion > _maxQBXMLVersion.Value)
            {
                throw new ArgumentException(
                    $"Requested version {requestedVersion} exceeds configured max {_maxQBXMLVersion.Value}");
            }

            return ExecuteOnSTAThread(() =>
            {
                if (!_isSessionOpen)
                {
                    throw new InvalidOperationException("No active QuickBooks session");
                }

                return _qbfcSessionManager.CreateMsgSetRequest(country, majorVersion, minorVersion);
            });
        }

        /// <summary>
        /// Execute a message set request (legacy - throws on error)
        /// </summary>
        public IMsgSetResponse DoRequests(IMsgSetRequest requestMsgSet)
        {
            var result = DoRequestsWithResult(requestMsgSet);
            if (result.Exception != null)
            {
                throw result.Exception;
            }
            return result.Response;
        }

        /// <summary>
        /// Execute a message set request with full status information
        /// Never swallows QBFC exceptions - returns structured result
        /// </summary>
        public QBRequestResult DoRequestsWithResult(IMsgSetRequest requestMsgSet)
        {
            ThrowIfDisposed();
            
            if (requestMsgSet == null)
                throw new ArgumentNullException(nameof(requestMsgSet));

            return ExecuteOnSTAThread(() =>
            {
                if (!_isSessionOpen)
                {
                    return new QBRequestResult
                    {
                        Success = false,
                        StatusCode = -1,
                        StatusMessage = "No active QuickBooks session",
                        OperationContext = "DoRequests"
                    };
                }

                try
                {
                    var response = _qbfcSessionManager.DoRequests(requestMsgSet);
                    
                    // Check first response for status
                    if (response.ResponseList?.Count > 0)
                    {
                        var firstResp = response.ResponseList.GetAt(0);
                        return new QBRequestResult
                        {
                            Success = firstResp.StatusCode == 0,
                            StatusCode = firstResp.StatusCode,
                            StatusMessage = firstResp.StatusMessage,
                            StatusSeverity = firstResp.StatusSeverity,
                            Response = response,
                            OperationContext = "DoRequests"
                        };
                    }
                    
                    return new QBRequestResult
                    {
                        Success = true,
                        StatusCode = 0,
                        Response = response,
                        OperationContext = "DoRequests"
                    };
                }
                catch (Exception ex)
                {
                    return new QBRequestResult
                    {
                        Success = false,
                        StatusCode = -1,
                        StatusMessage = ex.Message,
                        OperationContext = "DoRequests",
                        Exception = new QBException("QuickBooks request failed", ex.Message, -1, ex)
                    };
                }
            });
        }

        /// <summary>
        /// Get company information with file path redacted by default
        /// </summary>
        public CompanyInfo GetCompanyInfo()
        {
            ThrowIfDisposed();
            
            return ExecuteOnSTAThread(() =>
            {
                var requestMsgSet = _qbfcSessionManager.CreateMsgSetRequest(_country, (short)_qbxmlVersion, 0);
                requestMsgSet.AppendCompanyQueryRq();

                var responseMsgSet = _qbfcSessionManager.DoRequests(requestMsgSet);
                var response = responseMsgSet.ResponseList.GetAt(0);

                if (response.StatusCode != 0)
                {
                    throw new QBException("Company query failed", response.StatusMessage, response.StatusCode);
                }

                var companyRet = response.Detail as ICompanyRet;
                
                return new CompanyInfo
                {
                    CompanyName = companyRet?.CompanyName?.GetValue() ?? "Unknown",
                    LegalCompanyName = companyRet?.LegalCompanyName?.GetValue() ?? "",
                    Address = companyRet?.Address?.Addr1?.GetValue() ?? "",
                    City = companyRet?.Address?.City?.GetValue() ?? "",
                    State = companyRet?.Address?.State?.GetValue() ?? "",
                    PostalCode = companyRet?.Address?.PostalCode?.GetValue() ?? "",
                    Country = companyRet?.Address?.Country?.GetValue() ?? "",
                    Phone = companyRet?.Phone?.GetValue() ?? "",
                    Fax = companyRet?.Fax?.GetValue() ?? "",
                    Email = companyRet?.Email?.GetValue() ?? "",
                    // Redact file path by default
                    CompanyFilePath = "[REDACTED]"
                };
            });
        }

        /// <summary>
        /// Get QuickBooks version string
        /// </summary>
        public string GetQBVersion()
        {
            ThrowIfDisposed();
            return $"QuickBooks QBXML {_qbxmlVersion}";
        }

        /// <summary>
        /// Get cached QBXML version
        /// </summary>
        public double GetQBXMLVersion()
        {
            ThrowIfDisposed();
            return _qbxmlVersion;
        }

        /// <summary>
        /// Safely get QBXML version - parse all and select MAX
        /// </summary>
        private double GetQBXMLVersionSafe()
        {
            try
            {
                if (!_isSessionOpen)
                    return 13.0;

                string[] versions = _qbfcSessionManager.QBXMLVersionsForSession as string[];
                if (versions == null || versions.Length == 0)
                    return 13.0;

                double maxVersion = 13.0;
                foreach (string versionStr in versions)
                {
                    if (double.TryParse(versionStr, System.Globalization.NumberStyles.Float, 
                        System.Globalization.CultureInfo.InvariantCulture, out double parsedVersion))
                    {
                        // Respect max version limit if configured
                        if (_maxQBXMLVersion.HasValue && parsedVersion > _maxQBXMLVersion.Value)
                            continue;
                            
                        if (parsedVersion > maxVersion)
                        {
                            maxVersion = parsedVersion;
                        }
                    }
                }

                _logger?.Log(LogLevel.Debug, "Selected QBXML version: {0}", maxVersion);
                return maxVersion;
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Could not determine QBXML version: {0}", ex.Message);
                return 13.0;
            }
        }

        /// <summary>
        /// Detect QuickBooks capabilities without exception-driven flow
        /// </summary>
        public QBCapabilities GetCapabilities()
        {
            ThrowIfDisposed();
            
            return ExecuteOnSTAThread(() =>
            {
                var caps = new QBCapabilities
                {
                    QBXMLVersion = _qbxmlVersion,
                    Country = _country
                };

                try
                {
                    // Query preferences to detect edition and features
                    var requestMsgSet = _qbfcSessionManager.CreateMsgSetRequest(_country, (short)_qbxmlVersion, 0);
                    requestMsgSet.AppendHostQueryRq();

                    var responseMsgSet = _qbfcSessionManager.DoRequests(requestMsgSet);
                    var response = responseMsgSet.ResponseList.GetAt(0);

                    if (response.StatusCode == 0 && response.Detail is IHostRet hostRet)
                    {
                        // Get edition from product name
                        string productName = hostRet.ProductName?.GetValue() ?? "";
                        if (productName.Contains("Enterprise"))
                            caps.Edition = "Enterprise";
                        else if (productName.Contains("Premier"))
                            caps.Edition = "Premier";
                        else
                            caps.Edition = "Pro";

                        // Check supported versions for feature hints
                        var supportedVersions = hostRet.SupportedQBXMLVersionList;
                        if (supportedVersions != null)
                        {
                            caps.SupportsMultiCurrency = _qbxmlVersion >= 8.0;
                            caps.SupportsInventory = true;
                            caps.SupportsPayroll = _qbxmlVersion >= 5.0;
                            caps.SupportsSalesOrders = caps.Edition != "Pro";
                            caps.SupportsEstimates = true;
                        }
                    }
                }
                catch (Exception ex)
                {
                    _logger?.Log(LogLevel.Warning, "Capability detection failed: {0}", ex.Message);
                }

                return caps;
            });
        }

        /// <summary>
        /// Get telemetry-safe diagnostics snapshot
        /// Never includes secrets/PII unless explicitly requested
        /// </summary>
        public DiagnosticsSnapshot GetDiagnosticsSnapshot(bool includePII = false)
        {
            ThrowIfDisposed();
            
            var snapshot = new DiagnosticsSnapshot
            {
                SessionId = _sessionId,
                IsConnected = _isConnected,
                IsSessionOpen = _isSessionOpen,
                QBXMLVersion = _qbxmlVersion,
                Country = _country,
                SessionStartTime = _sessionStartTime
            };

            if (includePII)
            {
                snapshot.CompanyFilePath = _companyFilePath;
            }

            // Always hash company name, never include raw
            try
            {
                var companyInfo = GetCompanyInfo();
                using (var sha256 = System.Security.Cryptography.SHA256.Create())
                {
                    var hash = sha256.ComputeHash(
                        System.Text.Encoding.UTF8.GetBytes(companyInfo.CompanyName ?? ""));
                    snapshot.CompanyNameHash = Convert.ToBase64String(hash).Substring(0, 16);
                }
            }
            catch
            {
                snapshot.CompanyNameHash = "unavailable";
            }

            return snapshot;
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;

            try
            {
                ExecuteOnSTAThread(() =>
                {
                    CleanupConnectionInternal();
                    
                    if (_qbfcSessionManager != null)
                    {
                        System.Runtime.InteropServices.Marshal.ReleaseComObject(_qbfcSessionManager);
                        _qbfcSessionManager = null;
                    }
                });
            }
            finally
            {
                // Stop STA thread with proper timeout handling
                _staThreadRunning = false;
                _workAvailable.Set();

                if (_staThread != null && _staThread.IsAlive)
                {
                    // Wait up to 5 seconds for graceful shutdown
                    bool terminated = _staThread.Join(5000);

                    if (!terminated)
                    {
                        _logger?.Log(LogLevel.Warning,
                            "STA thread did not terminate gracefully within 5 seconds. " +
                            "QuickBooks resources may not be fully released.");

                        // Don't forcibly abort - just log and continue
                        // The thread will eventually terminate or the process will exit
                    }
                }

                _workAvailable?.Dispose();
                _workComplete?.Dispose();
            }
        }
    }

}

#endif // USE_QBFC
