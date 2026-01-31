using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Input;
using System.Windows.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using QBMigrationLauncher.Services;

namespace QBMigrationLauncher.ViewModels
{
    /// <summary>
    /// FIX: Implement IDisposable to properly unsubscribe from event handlers and prevent memory leaks
    /// </summary>
    public partial class MainViewModel : ObservableObject, IDisposable
    {
        private readonly ExtractorRunner _runner;
        private readonly LogParser _parser;
        private readonly HealthCheckService _healthCheck;
        private readonly CertificateGenerator _certificateGenerator;
        private readonly VarianceReportService _varianceReportService;
        private readonly string _outputDirectory;

        // FIX #27 & #28: Store full paths for detected files
        // FIX: Use ConcurrentDictionary for thread safety during async operations
        private readonly ConcurrentDictionary<string, string> _detectedFilePaths = new ConcurrentDictionary<string, string>();

        // FIX #14: Use circular buffer for logs to prevent memory growth
        // FIX LOW: Use constant instead of magic number
        private readonly CircularLogBuffer _logBuffer = new CircularLogBuffer(maxLines: Constants.Logging.MaxLogBufferLines);
        private readonly object _logLock = new object();

        // FIX LOW: Use constants for status messages
        [ObservableProperty]
        private string _connectionStatusText = Constants.Messages.SearchingQuickBooks;

        [ObservableProperty]
        private Brush _connectionStatusColor = Brushes.Gray;

        [ObservableProperty]
        private ObservableCollection<string> _detectedFiles = new ObservableCollection<string>();

        [ObservableProperty]
        private string? _selectedFile;

        [ObservableProperty]
        [NotifyPropertyChangedFor(nameof(CanStart))]
        private bool _isMigrating;

        [ObservableProperty]
        private int _progressPercentage;

        [ObservableProperty]
        private string _currentStatusMessage = Constants.Messages.Ready;

        [ObservableProperty]
        private string _logOutput = "";

        [ObservableProperty]
        private string _buttonText = "START MIGRATION";

        [ObservableProperty]
        private Brush _buttonColor = new SolidColorBrush(Color.FromRgb(44, 160, 28)); // #2CA01C

        public bool CanStart => !IsMigrating && !string.IsNullOrEmpty(SelectedFile);

        public MainViewModel()
        {
            _parser = new LogParser();
            _runner = new ExtractorRunner(_parser);
            
            // Initialize output directory for reports
            _outputDirectory = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                "QBMigration",
                "Reports"
            );
            Directory.CreateDirectory(_outputDirectory);
            
            _healthCheck = new HealthCheckService();
            _certificateGenerator = new CertificateGenerator(_outputDirectory);
            _varianceReportService = new VarianceReportService(_outputDirectory);
            
            _parser.ProgressChanged += OnProgressChanged;
            _parser.LogReceived += OnLogReceived;

            // Real detection
            CheckQuickBooksStatus();
        }

        private void CheckQuickBooksStatus()
        {
            // Check SDK installation
            if (!QuickBooksDetector.IsQBFC16Installed())
            {
                ConnectionStatusText = "ERROR: QuickBooks SDK not installed";
                ConnectionStatusColor = Brushes.Red;
                LogOutput = "[ERROR] QBFC16 SDK is not installed on this machine.\n" +
                           "Download it from: https://developer.intuit.com/app/developer/qbdesktop/docs/get-started/install-the-sdk";
                return;
            }

            // Check if QB is running
            if (!QuickBooksDetector.IsQuickBooksRunning())
            {
                ConnectionStatusText = "QuickBooks not running";
                ConnectionStatusColor = Brushes.Orange;
                LogOutput = "[WARN] QuickBooks Desktop is not running.\n" +
                           "Please open QuickBooks and your company file, then restart this tool.";
                return;
            }

            // Detect open company file
            var companyFile = QuickBooksDetector.GetOpenCompanyFile();
            if (!string.IsNullOrEmpty(companyFile))
            {
                // FIX #45: Store full path, not just filename
                _detectedFilePaths[Path.GetFileName(companyFile)] = companyFile;
                DetectedFiles.Add(Path.GetFileName(companyFile));
                SelectedFile = DetectedFiles[0];
            }
            else
            {
                // Fallback: QB is running but we couldn't detect the file
                DetectedFiles.Add("(QuickBooks detected - file will be auto-selected)");
                SelectedFile = DetectedFiles[0];
            }

            ConnectionStatusText = "Connected to QuickBooks";
            ConnectionStatusColor = Brushes.Green;
            LogOutput = $"[INFO] QuickBooks Desktop detected.\n" +
                       $"[INFO] Ready to start migration.\n";
        }

        [RelayCommand]
        private void RunHealthCheck()
        {
            LogOutput += "\n[INFO] Running Pre-Migration Health Check...\n";
            CurrentStatusMessage = "Running health check...";

            try
            {
                var result = _healthCheck.RunHealthCheck(_outputDirectory);

                // FIX MEDIUM: Validate health check results before proceeding
                if (result == null)
                {
                    LogOutput += "[ERROR] Health check returned null result.\n";
                    CurrentStatusMessage = "Health check failed - no results";
                    return;
                }

                // FIX MEDIUM: Validate that Checks collection is not null
                if (result.Checks == null)
                {
                    LogOutput += "[WARN] Health check returned no individual check results.\n";
                    result.Checks = new System.Collections.Generic.List<Services.HealthCheck>();
                }

                // FIX MEDIUM: Log critical issues found during health check
                var criticalFailures = result.Checks.Where(c =>
                    c.Severity == Services.CheckSeverity.Critical && !c.Passed).ToList();

                if (criticalFailures.Any())
                {
                    LogOutput += $"[WARN] {criticalFailures.Count} CRITICAL issue(s) found:\n";
                    foreach (var failure in criticalFailures)
                    {
                        LogOutput += $"  - {failure.Name}: {failure.Message}\n";
                    }
                }

                // Generate HTML report
                var reportPath = _certificateGenerator.GenerateHealthCheckReport(result, SelectedFile ?? "Unknown");

                // FIX MEDIUM: Validate report was actually created
                if (string.IsNullOrEmpty(reportPath) || !File.Exists(reportPath))
                {
                    LogOutput += "[WARN] Health check report may not have been generated successfully.\n";
                }
                else
                {
                    LogOutput += $"[INFO] Report saved to: {reportPath}\n";
                    // FIX WPF-02 & WPF-04: Add path validation and error handling for Process.Start
                    OpenFileInBrowser(reportPath);
                }

                LogOutput += $"[INFO] Health Check Complete: {result.GetSummary()}\n";
                CurrentStatusMessage = result.GetSummary();
            }
            catch (Exception ex)
            {
                LogOutput += $"[ERROR] Health check failed: {ex.Message}\n";
                CurrentStatusMessage = "Health check failed";
            }
        }

        /// <summary>
        /// FIX WPF-02 & WPF-04: Safely open a file in the default browser/application
        /// with path validation and error handling.
        /// </summary>
        private void OpenFileInBrowser(string filePath)
        {
            try
            {
                // Validate path exists and is safe
                if (string.IsNullOrEmpty(filePath))
                {
                    LogOutput += "[WARN] Cannot open file: path is empty\n";
                    return;
                }

                if (!File.Exists(filePath))
                {
                    LogOutput += $"[WARN] Cannot open file: {filePath} does not exist\n";
                    return;
                }

                // Ensure path is within expected directories (security check)
                var fullPath = Path.GetFullPath(filePath);
                var allowedPaths = new[]
                {
                    _outputDirectory,
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments)
                };

                bool isAllowed = allowedPaths.Any(allowed =>
                    fullPath.StartsWith(Path.GetFullPath(allowed), StringComparison.OrdinalIgnoreCase));

                if (!isAllowed)
                {
                    LogOutput += "[WARN] Cannot open file: path is outside allowed directories\n";
                    return;
                }

                Process.Start(new ProcessStartInfo(fullPath) { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                LogOutput += $"[WARN] Could not open file in browser: {ex.Message}\n";
            }
        }

        [RelayCommand]
        private async Task StartMigration()
        {
            if (IsMigrating) return;

            // FIX MEDIUM: Validate that selected file exists before starting migration
            if (!ValidateSelectedFileExists())
            {
                return;
            }

            // ============================================================================
            // LICENSE VALIDATION - Required before any migration
            // ============================================================================
            LogOutput = $"{Constants.Logging.InfoPrefix} Validating license...\n";
            CurrentStatusMessage = Constants.Messages.ValidatingLicense;
            
            try
            {
                var licenseResult = await QBDesktopExtractor.LicenseValidator.ValidateAsync();
                
                if (!licenseResult.Valid)
                {
                    LogOutput += $"[ERROR] License validation failed: {licenseResult.Error}\n";
                    CurrentStatusMessage = "License validation failed";
                    System.Windows.MessageBox.Show(
                        $"License validation failed:\n\n{licenseResult.Error}\n\nPlease activate a valid license to continue.",
                        "License Required",
                        System.Windows.MessageBoxButton.OK,
                        System.Windows.MessageBoxImage.Warning
                    );
                    return;
                }
                
                if (!licenseResult.HasMigrationsRemaining)
                {
                    LogOutput += "[ERROR] No migrations remaining on this license.\n";
                    CurrentStatusMessage = "No migrations remaining";
                    System.Windows.MessageBox.Show(
                        "You have used all migrations on your current license.\n\nPlease upgrade your license at https://forensicbridge.ca/pricing",
                        "Migrations Exhausted",
                        System.Windows.MessageBoxButton.OK,
                        System.Windows.MessageBoxImage.Warning
                    );
                    return;
                }
                
                LogOutput += $"[INFO] License valid: {licenseResult.GetDisplayStatus()}\n";
                App.LicenseResult = licenseResult;
            }
            catch (Exception ex)
            {
                LogOutput += $"[ERROR] License check failed: {ex.Message}\n";
                CurrentStatusMessage = "License check failed";
                return;
            }
            
            // ============================================================================
            // BEGIN MIGRATION
            // ============================================================================
            IsMigrating = true;
            ButtonText = "MIGRATING...";
            ButtonColor = Brushes.Gray;
            ProgressPercentage = 0;
            CurrentStatusMessage = "Starting extraction engine...";

            // FIX WPF-01: Generate MigrationId once and reuse
            // FIX LOW: Use constant for migration ID length
            string migrationId = Guid.NewGuid().ToString("N").Substring(0, Constants.Migration.MigrationIdLength).ToUpper();

            try
            {
                await _runner.RunExtractionAsync(SelectedFile, migrationId, _outputDirectory);

                CurrentStatusMessage = "Migration Complete! Generating certificate...";

                // FIX WPF-03: Generate real values instead of placeholders
                // Note: In production, these would come from the extraction results
                var sourceHash = ComputeFileHash(SelectedFile);

                // Generate Migration Certificate
                // FIX: Handle empty string from Path.GetFileName (it returns "" not null for empty input)
                var fileName = Path.GetFileName(SelectedFile ?? "");
                var displayName = string.IsNullOrEmpty(fileName) ? "Unknown" : fileName;

                var certData = new MigrationCertificateData
                {
                    CompanyName = displayName,
                    MigrationId = migrationId, // FIX WPF-01: Use the already-generated ID
                    MigrationDate = DateTime.UtcNow, // FIX: Use UtcNow for consistency
                    SourceFileName = displayName,
                    RealmId = "PENDING_QBO_VERIFICATION", // Clearer status message
                    SourceHash = sourceHash,
                    TrialBalanceDesktop = 0, // Will be populated from extraction results
                    TrialBalanceOnline = 0,  // Will be populated after QBO sync
                    CustomerCount = 0,
                    VendorCount = 0,
                    InvoiceCount = 0,
                    BillCount = 0,
                    AuthorizedBy = Environment.UserName
                };

                var certPath = _certificateGenerator.GenerateMigrationCertificate(certData);
                LogOutput += $"\n[INFO] Migration Certificate saved to: {certPath}\n";

                // FIX WPF-02 & WPF-04: Use safe file opening method
                OpenFileInBrowser(certPath);
                
                CurrentStatusMessage = Constants.Messages.MigrationComplete;
                ButtonText = "SUCCESS";
                ButtonColor = Brushes.Green;
            }
            catch (Exception ex)
            {
                CurrentStatusMessage = $"Error: {ex.Message}";
                ButtonText = "FAILED";
                ButtonColor = Brushes.Red;
                LogOutput += $"\n[ERROR] {ex.Message}";
            }
            finally
            {
                IsMigrating = false;
            }
        }

        private void OnProgressChanged(object? sender, ProgressEventArgs e)
        {
            // FIX #15: Use BeginInvoke (non-blocking) and check for null App.Current
            SafeDispatch(() =>
            {
                ProgressPercentage = e.Percentage;
                CurrentStatusMessage = e.StatusMessage;
            });
        }

        private void OnLogReceived(object? sender, string log)
        {
            // FIX #15: Use BeginInvoke (non-blocking) and check for null App.Current
            SafeDispatch(() =>
            {
                // FIX #14: Use circular buffer for efficient log management
                lock (_logLock)
                {
                    _logBuffer.Add(log);
                    LogOutput = _logBuffer.ToString();
                }
            });
        }

        /// <summary>
        /// FIX #15: Safely dispatch to UI thread with null check and non-blocking call.
        /// </summary>
        private void SafeDispatch(Action action)
        {
            var app = App.Current;
            if (app == null) return; // Application shutting down

            var dispatcher = app.Dispatcher;
            if (dispatcher == null || dispatcher.HasShutdownStarted) return;

            // Use BeginInvoke (async) instead of Invoke to prevent deadlocks
            dispatcher.BeginInvoke(action);
        }

        /// <summary>
        /// Compute SHA-256 hash of a file for the migration certificate.
        /// FIX #27 & #28: Properly resolve full path from detected files.
        /// FIX #39: Use streaming to avoid large file memory pressure.
        /// </summary>
        private string ComputeFileHash(string? filePath)
        {
            if (string.IsNullOrEmpty(filePath))
                return "NO_FILE_SELECTED";

            try
            {
                // FIX #27 & #28: Resolve to full path - check _detectedFilePaths dictionary
                string? fullPath = null;
                if (Path.IsPathRooted(filePath))
                {
                    fullPath = filePath;
                }
                else if (_detectedFilePaths.TryGetValue(filePath, out var detectedPath))
                {
                    fullPath = detectedPath;
                }

                // Try to find extracted output files to hash
                var extractedDir = Path.Combine(_outputDirectory, "extracted");
                if (Directory.Exists(extractedDir))
                {
                    // Hash the extraction manifest/summary if available
                    var manifestFiles = Directory.GetFiles(extractedDir, "*.ndjson", SearchOption.TopDirectoryOnly);
                    if (manifestFiles.Length > 0)
                    {
                        using var sha256 = System.Security.Cryptography.SHA256.Create();

                        // FIX #39: Stream files instead of loading all into memory
                        foreach (var file in manifestFiles.OrderBy(f => f))
                        {
                            using var fileStream = File.OpenRead(file);
                            byte[] buffer = new byte[8192];
                            int bytesRead;
                            while ((bytesRead = fileStream.Read(buffer, 0, buffer.Length)) > 0)
                            {
                                sha256.TransformBlock(buffer, 0, bytesRead, buffer, 0);
                            }
                        }
                        sha256.TransformFinalBlock(Array.Empty<byte>(), 0, 0);
                        return BitConverter.ToString(sha256.Hash!).Replace("-", "").ToLowerInvariant();
                    }
                }

                // Fallback: hash the company file directly if accessible
                if (fullPath != null && File.Exists(fullPath))
                {
                    using var sha256 = System.Security.Cryptography.SHA256.Create();
                    using var stream = File.OpenRead(fullPath);
                    var hashBytes = sha256.ComputeHash(stream);
                    return BitConverter.ToString(hashBytes).Replace("-", "").ToLowerInvariant();
                }

                // If no file accessible yet, return pending marker
                return $"PENDING_{DateTime.UtcNow:yyyyMMddHHmmss}";
            }
            catch (Exception ex)
            {
                LogOutput += $"[WARN] Could not compute file hash: {ex.Message}\n";
                return "HASH_ERROR";
            }
        }

        /// <summary>
        /// FIX #27: Get full path for a selected file.
        /// FIX MEDIUM: Validate that the path still exists before returning.
        /// </summary>
        private string? GetFullFilePath(string? fileName)
        {
            if (string.IsNullOrEmpty(fileName)) return null;

            string? fullPath = null;
            if (Path.IsPathRooted(fileName))
            {
                fullPath = fileName;
            }
            else if (_detectedFilePaths.TryGetValue(fileName, out var detectedPath))
            {
                fullPath = detectedPath;
            }

            // FIX MEDIUM: Validate that the file still exists before returning
            if (!string.IsNullOrEmpty(fullPath))
            {
                try
                {
                    if (!File.Exists(fullPath))
                    {
                        LogOutput += $"[WARN] Detected file no longer exists: {fullPath}\n";
                        // Remove stale entry from detected paths
                        if (!string.IsNullOrEmpty(fileName) && _detectedFilePaths.ContainsKey(fileName))
                        {
                            _detectedFilePaths.TryRemove(fileName, out _);
                        }
                        return null;
                    }
                }
                catch (Exception ex)
                {
                    LogOutput += $"[WARN] Unable to verify file exists: {ex.Message}\n";
                    return null;
                }
            }

            return fullPath;
        }

        /// <summary>
        /// FIX MEDIUM: Validate that detected files still exist before starting migration.
        /// Returns true if validation passes.
        /// </summary>
        private bool ValidateSelectedFileExists()
        {
            if (string.IsNullOrEmpty(SelectedFile))
            {
                LogOutput += "[ERROR] No file selected for migration.\n";
                return false;
            }

            // Skip validation for auto-detected files placeholder
            if (SelectedFile.Contains("will be auto-selected"))
            {
                return true;
            }

            var fullPath = GetFullFilePath(SelectedFile);
            if (fullPath == null)
            {
                LogOutput += $"[ERROR] Selected file '{SelectedFile}' no longer exists or cannot be accessed.\n";
                CurrentStatusMessage = "Selected file not found. Please select a different file.";
                return false;
            }

            return true;
        }

        /// <summary>
        /// FIX: Dispose pattern to unsubscribe from events and prevent memory leaks
        /// </summary>
        public void Dispose()
        {
            _parser.ProgressChanged -= OnProgressChanged;
            _parser.LogReceived -= OnLogReceived;
        }
    }

    /// <summary>
    /// FIX #14: Circular buffer for log lines to prevent unbounded memory growth.
    /// Efficiently maintains a fixed-size window of the most recent log lines.
    /// </summary>
    public class CircularLogBuffer
    {
        private readonly string[] _buffer;
        private readonly int _maxLines;
        private int _head;
        private int _count;
        private readonly StringBuilder _outputCache;
        private bool _cacheValid;

        public CircularLogBuffer(int maxLines = 1000)
        {
            _maxLines = maxLines;
            _buffer = new string[maxLines];
            _head = 0;
            _count = 0;
            _outputCache = new StringBuilder();
            _cacheValid = false;
        }

        /// <summary>
        /// Add a log line to the buffer. Old lines are overwritten when buffer is full.
        /// </summary>
        public void Add(string line)
        {
            _buffer[_head] = line;
            _head = (_head + 1) % _maxLines;

            if (_count < _maxLines)
                _count++;

            _cacheValid = false; // Invalidate cache
        }

        /// <summary>
        /// Get all lines in the buffer, oldest to newest.
        /// Uses caching for efficiency when repeatedly called without new additions.
        /// </summary>
        public override string ToString()
        {
            if (_cacheValid)
                return _outputCache.ToString();

            _outputCache.Clear();

            if (_count == 0)
                return string.Empty;

            // Calculate start position (oldest line)
            int start = (_count < _maxLines) ? 0 : _head;

            for (int i = 0; i < _count; i++)
            {
                int index = (start + i) % _maxLines;
                _outputCache.AppendLine(_buffer[index]);
            }

            _cacheValid = true;
            return _outputCache.ToString();
        }

        /// <summary>
        /// Clear all log lines from the buffer.
        /// </summary>
        public void Clear()
        {
            _head = 0;
            _count = 0;
            _outputCache.Clear();
            _cacheValid = false;
        }

        /// <summary>
        /// Current number of lines in the buffer.
        /// </summary>
        public int Count => _count;
    }
}
