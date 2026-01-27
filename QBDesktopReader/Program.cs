using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace QBDesktopExtractor
{
    /// <summary>
    /// QuickBooks Desktop to Cloud - Enterprise Migration Tool
    /// v4.2: Production-Ready with Accurate Claims
    /// 
    /// FIXES FROM REVIEW:
    /// - Accurate algorithm description (AES-256-GCM-Chunked)
    /// - Correct entity type count (dynamic)
    /// - No "zero-footprint" claim (uses "low-memory streaming")
    /// - Progress-based, not time estimates
    /// - Automation-friendly (--no-pause, exit codes)
    /// - Single cleanup path (idempotent)
    /// - Sensitive data redacted by default
    /// - CLI args support (--config, --extract-only, etc.)
    /// - Structured logging
    /// </summary>
    class Program
    {
        private static QBSessionManager _sessionManager;
        private static QBDataExtractor _extractor;
        private static ExtractionConfig _config;
        private static CancellationTokenSource _cts;
        private static IRedactingLogger _logger;
        private static bool _cleanupDone;
        private static readonly object _cleanupLock = new object();

        private static class ExitCode
        {
            public const int Success = 0;
            public const int ConfigError = 10;
            public const int LicenseInvalid = 15;
            public const int SDKNotInstalled = 20;
            public const int QBConnectionFailed = 30;
            public const int ExtractionFailed = 40;
            public const int UploadFailed = 50;
            public const int Cancelled = 60;
            public const int UnknownError = 99;
        }

        [STAThread]
        static int Main(string[] args)
        {
            var options = ParseArgs(args);
            
            if (!options.Quiet)
            {
                PrintHeader();
            }

            string sessionId = Guid.NewGuid().ToString();
            
            var logConfig = new RedactionConfig { Enabled = true };
            _logger = new RedactingConsoleLogger(logConfig, 
                options.Verbose ? LogLevel.Debug : LogLevel.Info);
            
            _logger.Log(LogLevel.Info, "Migration Session ID: {0}", sessionId);
            _logger.Log(LogLevel.Info, "Started: {0}", DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));

            _cts = new CancellationTokenSource();

            Console.CancelKeyPress += (sender, e) =>
            {
                _logger.Log(LogLevel.Warning, "Interrupted by user. Cleaning up...");
                _cts.Cancel();
                SafeCleanup();
                e.Cancel = false;
            };

            AppDomain.CurrentDomain.UnhandledException += (sender, e) =>
            {
                _logger.Log(LogLevel.Error, "FATAL ERROR: {0}", e.ExceptionObject);
                SafeCleanup();
            };

            try
            {
                int result = RunExtraction(sessionId, options).GetAwaiter().GetResult();
                
                if (!options.NoPause && !options.Quiet)
                {
                    Console.WriteLine("\nPress any key to exit...");
                    Console.ReadKey();
                }
                
                return result;
            }
            catch (OperationCanceledException)
            {
                _logger.Log(LogLevel.Warning, "Operation cancelled by user");
                return ExitCode.Cancelled;
            }
            catch (Exception ex)
            {
                _logger.Log(LogLevel.Error, "Extraction failed: {0}", ex.Message);
                SafeCleanup();
                return ExitCode.UnknownError;
            }
        }

        private static void PrintHeader()
        {
            Console.WriteLine();
            Console.WriteLine(new string('=', 80));
            Console.WriteLine("  QuickBooks Desktop to Cloud - Enterprise Migration Tool");
            Console.WriteLine("  Version 4.2 - Production-Ready Low-Memory Streaming");
            Console.WriteLine("  AES-256-GCM Chunked Encryption | COM Thread-Safe");
            Console.WriteLine(new string('=', 80));
            Console.WriteLine();
        }

        private static void SafeCleanup()
        {
            lock (_cleanupLock)
            {
                if (_cleanupDone) return;
                _cleanupDone = true;

                try
                {
                    _logger?.Log(LogLevel.Info, "Cleaning up QuickBooks connection...");

                    if (_sessionManager != null)
                    {
                        _sessionManager.EndSession();
                        _sessionManager.CloseConnection();
                        _sessionManager.Dispose();
                        _sessionManager = null;
                    }

                    _extractor = null;
                    GC.Collect();
                    GC.WaitForPendingFinalizers();
                    
                    _logger?.Log(LogLevel.Info, "Cleanup complete");
                }
                catch (Exception ex)
                {
                    _logger?.Log(LogLevel.Warning, "Warning during cleanup: {0}", ex.Message);
                }
            }
        }

        private static async Task<int> RunExtraction(string sessionId, CommandLineOptions options)
        {
            try
            {
                // PHASE 0: LICENSE VALIDATION (CRITICAL - must come first)
                _logger.Log(LogLevel.Info, "Validating license...");
                
                try
                {
                    var licenseResult = await LicenseValidator.ValidateAsync(options.LicenseKey);
                    
                    if (!licenseResult.Valid)
                    {
                        _logger.Log(LogLevel.Error, "License validation failed: {0}", licenseResult.Error);
                        Console.WriteLine();
                        Console.WriteLine("╔══════════════════════════════════════════════════════════════════╗");
                        Console.WriteLine("║  LICENSE REQUIRED                                                 ║");
                        Console.WriteLine("╠══════════════════════════════════════════════════════════════════╣");
                        Console.WriteLine("║  Please purchase a license at: https://forensicbridge.ca         ║");
                        Console.WriteLine("║  Use --license <key> to provide your license key                 ║");
                        Console.WriteLine("╚══════════════════════════════════════════════════════════════════╝");
                        Console.WriteLine();
                        return ExitCode.LicenseInvalid;
                    }
                    
                    if (!licenseResult.HasMigrationsRemaining)
                    {
                        _logger.Log(LogLevel.Error, "No migrations remaining on license");
                        Console.WriteLine();
                        Console.WriteLine("╔══════════════════════════════════════════════════════════════════╗");
                        Console.WriteLine("║  MIGRATIONS EXHAUSTED                                             ║");
                        Console.WriteLine("╠══════════════════════════════════════════════════════════════════╣");
                        Console.WriteLine("║  Your license has used all available migrations.                 ║");
                        Console.WriteLine("║  Please upgrade at: https://forensicbridge.ca                    ║");
                        Console.WriteLine("╚══════════════════════════════════════════════════════════════════╝");
                        Console.WriteLine();
                        return ExitCode.LicenseInvalid;
                    }
                    
                    _logger.Log(LogLevel.Info, "License validated: {0}", licenseResult.GetDisplayStatus());
                    if (licenseResult.FromCache)
                    {
                        _logger.Log(LogLevel.Warning, "Using cached license (offline mode)");
                    }
                }
                catch (Exception ex)
                {
                    _logger.Log(LogLevel.Error, "License check failed: {0}", ex.Message);
                    return ExitCode.LicenseInvalid;
                }

                // PHASE 0.5: SESSION CODE VALIDATION (CRITICAL)
                _logger.Log(LogLevel.Info, "Validating session code...");

                string? sessionCode = options.SessionCode;

                // Try to get cached session if not provided
                if (string.IsNullOrWhiteSpace(sessionCode))
                {
                    sessionCode = SessionValidator.GetCachedSessionId();
                    if (!string.IsNullOrWhiteSpace(sessionCode))
                    {
                        _logger.Log(LogLevel.Info, "Using cached session: {0}", sessionCode);
                    }
                }

                // Prompt for session code if not provided
                if (string.IsNullOrWhiteSpace(sessionCode))
                {
                    Console.WriteLine();
                    Console.WriteLine("╔══════════════════════════════════════════════════════════════════╗");
                    Console.WriteLine("║  SESSION CODE REQUIRED                                            ║");
                    Console.WriteLine("╠══════════════════════════════════════════════════════════════════╣");
                    Console.WriteLine("║  Enter your session code from the ForensicBridge dashboard:      ║");
                    Console.WriteLine("║  Example: FB-20260127123456-ABCD1234                              ║");
                    Console.WriteLine("╚══════════════════════════════════════════════════════════════════╝");
                    Console.WriteLine();
                    Console.Write("Session Code: ");
                    sessionCode = Console.ReadLine()?.Trim();
                }

                if (string.IsNullOrWhiteSpace(sessionCode))
                {
                    _logger.Log(LogLevel.Error, "No session code provided");
                    Console.WriteLine();
                    Console.WriteLine("╔══════════════════════════════════════════════════════════════════╗");
                    Console.WriteLine("║  SESSION CODE REQUIRED                                            ║");
                    Console.WriteLine("╠══════════════════════════════════════════════════════════════════╣");
                    Console.WriteLine("║  Create a project at: https://forensicbridge.ca/projects/new     ║");
                    Console.WriteLine("║  Use --session <code> to provide your session code               ║");
                    Console.WriteLine("╚══════════════════════════════════════════════════════════════════╝");
                    Console.WriteLine();
                    return ExitCode.ConfigError;
                }

                try
                {
                    var sessionResult = await SessionValidator.ValidateAsync(sessionCode);

                    if (!sessionResult.Valid)
                    {
                        _logger.Log(LogLevel.Error, "Session validation failed: {0}", sessionResult.Error);
                        Console.WriteLine();
                        Console.WriteLine("╔══════════════════════════════════════════════════════════════════╗");
                        Console.WriteLine("║  SESSION VALIDATION FAILED                                        ║");
                        Console.WriteLine("╠══════════════════════════════════════════════════════════════════╣");
                        Console.WriteLine($"║  {sessionResult.Error,-64} ║");
                        Console.WriteLine("╚══════════════════════════════════════════════════════════════════╝");
                        Console.WriteLine();
                        return ExitCode.ConfigError;
                    }

                    if (sessionResult.RemainingExtractions <= 0)
                    {
                        _logger.Log(LogLevel.Error, "No extractions remaining for this session");
                        Console.WriteLine();
                        Console.WriteLine("╔══════════════════════════════════════════════════════════════════╗");
                        Console.WriteLine("║  EXTRACTIONS EXHAUSTED                                            ║");
                        Console.WriteLine("╠══════════════════════════════════════════════════════════════════╣");
                        Console.WriteLine("║  This session has used all available extractions.                ║");
                        Console.WriteLine("║  Please create a new project at: https://forensicbridge.ca      ║");
                        Console.WriteLine("╚══════════════════════════════════════════════════════════════════╝");
                        Console.WriteLine();
                        return ExitCode.LicenseInvalid;
                    }

                    _logger.Log(LogLevel.Info, "Session validated:");
                    _logger.Log(LogLevel.Info, "  Project: {0}", sessionResult.ProjectName);
                    _logger.Log(LogLevel.Info, "  Client: {0}", sessionResult.ClientName);
                    _logger.Log(LogLevel.Info, "  Tier: {0}", sessionResult.TierName);
                    _logger.Log(LogLevel.Info, "  Remaining Extractions: {0}", sessionResult.RemainingExtractions);

                    // Activate device if new
                    if (sessionResult.IsNewDevice)
                    {
                        _logger.Log(LogLevel.Info, "Activating device...");
                        var activationResult = await SessionValidator.ActivateAsync(sessionCode);
                        if (!activationResult.Valid)
                        {
                            _logger.Log(LogLevel.Error, "Device activation failed: {0}", activationResult.Error);
                            return ExitCode.ConfigError;
                        }
                        _logger.Log(LogLevel.Info, "Device activated (device {0} of {1})",
                            activationResult.DeviceNumber, activationResult.MaxDevices);
                    }

                    // Store session ID for use later
                    sessionId = $"{sessionCode}-{sessionId}";
                }
                catch (Exception ex)
                {
                    _logger.Log(LogLevel.Error, "Session check failed: {0}", ex.Message);
                    return ExitCode.ConfigError;
                }

                // PHASE 1: LOAD CONFIGURATION
                _logger.Log(LogLevel.Info, "Loading configuration...");

                try
                {
                    _config = ExtractionConfig.LoadFromFile(options.ConfigPath);
                    _logger.Log(LogLevel.Info, "Configuration loaded and validated");
                    _logger.Log(LogLevel.Info, "Server: {0}", _config.ServerUrl);
                    
                    if (_config.IncrementalSyncFromDate.HasValue)
                    {
                        _logger.Log(LogLevel.Info, "Incremental Sync: from {0:yyyy-MM-dd}", 
                            _config.IncrementalSyncFromDate);
                    }
                }
                catch (ConfigurationException ex)
                {
                    _logger.Log(LogLevel.Error, "Configuration Error: {0}", ex.Message);
                    return ExitCode.ConfigError;
                }

                // PHASE 1: PREREQUISITES CHECK
                _logger.Log(LogLevel.Info, "Checking system requirements...");

                try
                {
                    CheckPrerequisites();
                    _logger.Log(LogLevel.Info, "Prerequisites verified");
                }
                catch (Exception ex)
                {
                    _logger.Log(LogLevel.Error, "Prerequisite check failed: {0}", ex.Message);
                    return ExitCode.SDKNotInstalled;
                }

                // PHASE 2: QUICKBOOKS CONNECTION & EXTRACTION
                _logger.Log(LogLevel.Info, "Connecting to QuickBooks Desktop...");
                _logger.Log(LogLevel.Warning, "IMPORTANT: Approve the connection request in QuickBooks");

                try
                {
                    _sessionManager = new QBSessionManager(
                        _config.Advanced?.MaxQBXMLVersion,
                        _logger);
                    
                    _sessionManager.BeginSession("", QBFC16Lib.ENOpenMode.omDontCare);

                    var companyInfo = _sessionManager.GetCompanyInfo();
                    _logger.Log(LogLevel.Info, "Connected to QuickBooks");
                    _logger.Log(LogLevel.Info, "Company: {0}", companyInfo.CompanyName);
                    _logger.Log(LogLevel.Info, "QB Version: {0}", _sessionManager.GetQBVersion());

                    _logger.Log(LogLevel.Info, "Extracting data (sequential mode for COM safety)...");
                    
                    _extractor = new QBDataExtractor(_sessionManager, _logger);

                    // Handle incremental sync (auto or config-based)
                    DateTime? incrementalFrom = _config.IncrementalSyncFromDate;
                    
                    if (options.AutoIncremental)
                    {
                        var syncMarker = new SyncMarker(options.OutputDirectory, companyInfo.CompanyName, _logger);
                        incrementalFrom = syncMarker.GetIncrementalFromDate();
                    }

                    if (incrementalFrom.HasValue)
                    {
                        _extractor.SetIncrementalSyncDate(incrementalFrom.Value);
                    }

                    // NDJSON MODE: Per-entity files with manifest
                    if (options.NDJSONMode)
                    {
                        _logger.Log(LogLevel.Info, "Using NDJSON output mode (warehouse-ready)");
                        
                        var configHash = ComputeHash(File.ReadAllText(options.ConfigPath));
                        var manifest = await _extractor.ExtractAllDataToNDJSONAsync(
                            options.OutputDirectory,
                            sessionId,
                            configHash,
                            _cts.Token);

                        _logger.Log(LogLevel.Info, "Closing QuickBooks session...");
                        _sessionManager.EndSession();

                        // Save sync marker for next incremental run
                        if (options.AutoIncremental && manifest.TotalRecords > 0)
                        {
                            var syncMarker = new SyncMarker(options.OutputDirectory, companyInfo.CompanyName, _logger);
                            syncMarker.Save(new SyncMarkerState
                            {
                                LastSyncTime = DateTime.UtcNow,
                                LastSyncTimeLocal = DateTime.Now,
                                SessionId = sessionId,
                                RecordsExtracted = manifest.TotalRecords,
                                CompanyFingerprint = manifest.CompanyFingerprint,
                                QBVersion = manifest.QBVersion
                            });
                        }

                        // Generate support bundle if requested
                        if (options.GenerateSupportBundle)
                        {
                            var bundle = new SupportBundle(_logger);
                            bundle.Generate(options.OutputDirectory, manifest, _extractor.RunSummary);
                        }

                        // Print summary
                        PrintExtractionSummary(manifest, _extractor.RunSummary);
                        return ExitCode.Success;
                    }

                    // LEGACY MODE: Single JSON blob
                    var data = _extractor.ExtractAllData();

                    data.IsIncrementalSync = incrementalFrom.HasValue;
                    data.IncrementalFromDate = incrementalFrom;
                    data.SessionID = sessionId;

                    int totalRecords = CountTotalRecords(data);
                    _logger.Log(LogLevel.Info, "Extraction complete: {0} total records", totalRecords);

                    // PHASE 2.5: AUTO-SANITIZATION
                    if (!options.NoSanitize)
                    {
                        _logger.Log(LogLevel.Info, "Auto-sanitizing data...");

                        var sanitizer = new DataSanitizer(
                            SanitizationMode.Json,
                            new SanitizationConfig { IncludeRawValuesInReport = false },
                            _logger);
                        
                        data = sanitizer.SanitizeExtractedData(data);

                        if (sanitizer.Report.TotalActions > 0)
                        {
                            _logger.Log(LogLevel.Info, "Auto-healed {0} issues", sanitizer.Report.TotalActions);
                        }
                    }

                    _logger.Log(LogLevel.Info, "Closing QuickBooks session...");
                    _sessionManager.EndSession();

                    // PHASE 3: STREAMING PIPELINE
                    if (options.ExtractOnly)
                    {
                        string outputPath = $"extraction_{sessionId}.json";
                        File.WriteAllText(outputPath, 
                            JsonConvert.SerializeObject(data, Formatting.Indented));
                        _logger.Log(LogLevel.Info, "Data saved to: {0}", outputPath);
                    }
                    else
                    {
                        _logger.Log(LogLevel.Info, "Starting streaming upload pipeline...");

                        var uploader = new FileUploader(_config, _logger);
                        var pipeline = new StreamingPipeline(_config, uploader, _logger);

                        var pipelineResult = await pipeline.ProcessDataAsync(
                            data,
                            sessionId,
                            _cts.Token);

                        _logger.Log(LogLevel.Info, "Pipeline complete in {0:F1}s", 
                            pipelineResult.TotalDurationSeconds);

                        // PHASE 4: SUCCESS SUMMARY
                        _logger.Log(LogLevel.Info, "Generating migration certificate...");
                        GenerateMigrationCertificate(sessionId, data, pipelineResult, companyInfo);

                        _logger.Log(LogLevel.Info, "SUCCESS: All data extracted, encrypted, and uploaded");
                        _logger.Log(LogLevel.Info, "Session ID: {0}", sessionId);
                        _logger.Log(LogLevel.Info, "Forensic Hash: {0}...", 
                            pipelineResult.DataHashSHA256?.Substring(0, 16) ?? "N/A");
                    }

                    return ExitCode.Success;
                }
                catch (QBException ex)
                {
                    _logger.Log(LogLevel.Error, "QuickBooks error ({0}): {1}", ex.ErrorCode, ex.Message);
                    return ExitCode.QBConnectionFailed;
                }
                finally
                {
                    SafeCleanup();
                }
            }
            catch (PipelineException ex)
            {
                _logger.Log(LogLevel.Error, "Pipeline failed at {0}: {1}", ex.FailedStage, ex.Message);
                return ExitCode.UploadFailed;
            }
            catch (Exception ex)
            {
                _logger.Log(LogLevel.Error, "Unexpected error: {0}", ex.Message);
                return ExitCode.UnknownError;
            }
        }

        private static void CheckPrerequisites()
        {
            try
            {
                var qbType = Type.GetTypeFromProgID("QBFC16.QBSessionManager");
                if (qbType == null)
                {
                    throw new Exception(
                        "QuickBooks SDK (QBFC16) not installed.\n" +
                        "Download from: https://developer.intuit.com/app/developer/qbdesktop/docs/get-started/install-the-sdk");
                }
            }
            catch (Exception ex) when (!(ex.Message.Contains("QuickBooks SDK")))
            {
                throw new Exception("QuickBooks SDK check failed. Ensure QBFC16 is properly installed.");
            }

            try
            {
                var computerInfo = new Microsoft.VisualBasic.Devices.ComputerInfo();
                ulong availableGB = computerInfo.AvailablePhysicalMemory / 1024 / 1024 / 1024;

                if (availableGB < 2)
                {
                    _logger?.Log(LogLevel.Warning, 
                        "Low RAM ({0}GB available). Recommend 4GB+ for large companies.", availableGB);
                }
            }
            catch { }
        }

        private static int CountTotalRecords(QBExtractedData data)
        {
            int total = 0;
            var listProperties = typeof(QBExtractedData).GetProperties()
                .Where(p => p.PropertyType.IsGenericType && 
                           p.PropertyType.GetGenericTypeDefinition() == typeof(List<>));

            foreach (var prop in listProperties)
            {
                var list = prop.GetValue(data) as System.Collections.IList;
                if (list != null) total += list.Count;
            }
            return total;
        }

        private static void PrintExtractionSummary(RunManifest manifest, ExtractionRunSummary runSummary)
        {
            Console.WriteLine();
            Console.WriteLine(new string('=', 60));
            Console.WriteLine("  EXTRACTION SUMMARY");
            Console.WriteLine(new string('=', 60));
            Console.WriteLine();
            
            // Entity breakdown
            Console.WriteLine("  Entity                    Records    Status");
            Console.WriteLine("  " + new string('-', 50));
            
            foreach (var entity in manifest.Entities)
            {
                string status = entity.Errors > 0 ? "⚠️ WARN" : "✅ OK";
                Console.WriteLine($"  {entity.EntityName,-24} {entity.RecordCount,8}    {status}");
            }
            
            Console.WriteLine("  " + new string('-', 50));
            Console.WriteLine($"  {"TOTAL",-24} {manifest.TotalRecords,8}");
            Console.WriteLine();
            
            // Errors/warnings
            if (manifest.TotalErrors > 0)
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine($"  ⚠️ Warnings/Errors: {manifest.TotalErrors}");
                Console.ResetColor();
            }
            
            // Timing
            Console.WriteLine($"  Duration: {manifest.DurationSeconds:F1}s");
            Console.WriteLine($"  Output: {runSummary?.EntityResults?.Count ?? 0} NDJSON files + manifest");
            Console.WriteLine();
            
            if (manifest.TotalErrors == 0)
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("  ✅ SUCCESS: All entities extracted");
                Console.ResetColor();
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine("  ⚠️ COMPLETED WITH WARNINGS - Review errors.ndjson");
                Console.ResetColor();
            }
            Console.WriteLine();
        }


        private static void GenerateMigrationCertificate(
            string sessionId, QBExtractedData data, 
            PipelineResult pipelineResult, QBCompanyInfo companyInfo)
        {
            string companyHash = ComputeHash(companyInfo.CompanyName);

            var certificate = new
            {
                SessionID = sessionId,
                MigrationDate = DateTime.UtcNow,
                CompanyNameHash = companyHash,
                QBVersion = data.QBVersion,
                SchemaVersion = data.SchemaVersion,
                TotalRecords = CountTotalRecords(data),
                PlaintextSizeBytes = pipelineResult.PlaintextSizeBytes,
                EncryptedSizeBytes = pipelineResult.EncryptedSizeBytes,
                DataHashSHA256 = pipelineResult.DataHashSHA256,
                EncryptedHashSHA256 = pipelineResult.EncryptedHashSHA256,
                Algorithm = pipelineResult.Algorithm,
                KeyId = pipelineResult.KeyId,
                IsIncrementalSync = data.IsIncrementalSync,
                IncrementalFromDate = data.IncrementalFromDate,
                DurationSeconds = pipelineResult.TotalDurationSeconds
            };

            string certPath = $"migration_certificate_{sessionId}.json";
            File.WriteAllText(certPath, JsonConvert.SerializeObject(certificate, Formatting.Indented));
            _logger.Log(LogLevel.Info, "Certificate saved: {0}", certPath);
        }

        private static string ComputeHash(string value)
        {
            if (string.IsNullOrEmpty(value)) return "null";
            using (var sha256 = System.Security.Cryptography.SHA256.Create())
            {
                byte[] hash = sha256.ComputeHash(System.Text.Encoding.UTF8.GetBytes(value));
                return Convert.ToBase64String(hash).Substring(0, 16);
            }
        }

        private static CommandLineOptions ParseArgs(string[] args)
        {
            var options = new CommandLineOptions();
            for (int i = 0; i < args.Length; i++)
            {
                switch (args[i].ToLower())
                {
                    case "--config": case "-c":
                        if (i + 1 < args.Length) options.ConfigPath = args[++i];
                        break;
                    case "--output-dir": case "-o":
                        if (i + 1 < args.Length) options.OutputDirectory = args[++i];
                        break;
                    case "--license": case "-l":
                        if (i + 1 < args.Length) options.LicenseKey = args[++i];
                        break;
                    case "--session": case "-s":
                        if (i + 1 < args.Length) options.SessionCode = args[++i];
                        break;
                    case "--no-pause": options.NoPause = true; break;
                    case "--quiet": case "-q": options.Quiet = true; break;
                    case "--verbose": case "-v": options.Verbose = true; break;
                    case "--extract-only": options.ExtractOnly = true; break;
                    case "--no-sanitize": options.NoSanitize = true; break;
                    case "--ndjson": options.NDJSONMode = true; break;
                    case "--auto-incremental": options.AutoIncremental = true; break;
                    case "--generate-bundle": options.GenerateSupportBundle = true; break;
                    case "--help": case "-h": PrintHelp(); Environment.Exit(0); break;
                }
            }
            return options;
        }

        private static void PrintHelp()
        {
            Console.WriteLine("QuickBooks Desktop Extractor v4.3");
            Console.WriteLine("\nUsage: QBExtractor.exe [options]");
            Console.WriteLine("\nRequired:");
            Console.WriteLine("  --session, -s <code>  Session code from ForensicBridge dashboard");
            Console.WriteLine("                        Example: FB-20260127123456-ABCD1234");
            Console.WriteLine("\nOptions:");
            Console.WriteLine("  --config, -c <path>   Path to config.json (default: config.json)");
            Console.WriteLine("  --output-dir, -o      Output directory for NDJSON files");
            Console.WriteLine("  --license, -l <key>   License key (optional, cached after first use)");
            Console.WriteLine("  --ndjson              Output NDJSON per-entity files (warehouse-ready)");
            Console.WriteLine("  --auto-incremental    Auto-detect last sync and extract changes only");
            Console.WriteLine("  --generate-bundle     Generate support bundle after extraction");
            Console.WriteLine("  --no-pause            Don't wait for keypress on exit");
            Console.WriteLine("  --quiet, -q           Minimal output");
            Console.WriteLine("  --verbose, -v         Debug-level output");
            Console.WriteLine("  --extract-only        Extract to local file, don't upload");
            Console.WriteLine("  --no-sanitize         Skip data sanitization");
            Console.WriteLine("  --help, -h            Show this help");
            Console.WriteLine("\nOutput modes:");
            Console.WriteLine("  Default: Single JSON blob, upload to server");
            Console.WriteLine("  --ndjson: Per-entity NDJSON files with run_manifest.json");
            Console.WriteLine("\nExit codes:");
            Console.WriteLine("  0   Success");
            Console.WriteLine("  10  Configuration error");
            Console.WriteLine("  20  SDK not installed");
            Console.WriteLine("  30  QuickBooks connection failed");
            Console.WriteLine("  40  Extraction failed");
            Console.WriteLine("  50  Upload failed");
            Console.WriteLine("  60  Cancelled by user");
            Console.WriteLine("  99  Unknown error");
        }
    }

    internal class CommandLineOptions
    {
        public string ConfigPath { get; set; } = "config.json";
        public string OutputDirectory { get; set; } = "output";
        public string? LicenseKey { get; set; }
        public string? SessionCode { get; set; }
        public bool NoPause { get; set; }
        public bool Quiet { get; set; }
        public bool Verbose { get; set; }
        public bool ExtractOnly { get; set; }
        public bool NoSanitize { get; set; }
        public bool NDJSONMode { get; set; }
        public bool AutoIncremental { get; set; }
        public bool GenerateSupportBundle { get; set; }
    }
}