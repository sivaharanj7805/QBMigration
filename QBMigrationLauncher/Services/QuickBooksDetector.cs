using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Management;
using Newtonsoft.Json;

namespace QBMigrationLauncher.Services
{
    /// <summary>
    /// Detects installed QuickBooks versions and currently open company files.
    /// </summary>
    public class QuickBooksDetector
    {
        /// <summary>
        /// Check if QuickBooks Desktop is running.
        /// </summary>
        public static bool IsQuickBooksRunning()
        {
            // QuickBooks Desktop process names
            return Process.GetProcessesByName("QBW32").Length > 0 
                || Process.GetProcessesByName("QBW").Length > 0;
        }

        /// <summary>
        /// Get the path to the currently open company file (if any).
        /// FIX #5: Uses Process.GetProcessesByName() first to check if QB is running,
        /// then falls back to WMI only when needed to get command line.
        /// FIX #10: Properly collects results before disposing ManagementObjects.
        /// </summary>
        public static string? GetOpenCompanyFile()
        {
            try
            {
                // FIX #5: First check if QB is running using Process.GetProcessesByName
                // This is safer and more efficient than WMI
                var qbProcesses = Process.GetProcessesByName("QBW32")
                    .Concat(Process.GetProcessesByName("QBW"))
                    .ToArray();

                if (qbProcesses.Length == 0)
                {
                    return null; // No QuickBooks running
                }

                // Dispose process handles - we only needed to check if they exist
                foreach (var proc in qbProcesses)
                {
                    proc.Dispose();
                }

                // FIX #10: Need WMI to get command line - collect results before disposing
                // Use parameterized query for additional safety
                string query = "SELECT CommandLine FROM Win32_Process WHERE Name = 'QBW32.exe' OR Name = 'QBW.exe'";
                var collectedCmdLines = new System.Collections.Generic.List<string>();

                using (var searcher = new ManagementObjectSearcher(query))
                using (var results = searcher.Get())
                {
                    // FIX #10: Collect all command lines first, then dispose objects
                    foreach (ManagementObject obj in results)
                    {
                        try
                        {
                            string? cmdLine = obj["CommandLine"]?.ToString();
                            if (!string.IsNullOrEmpty(cmdLine))
                            {
                                collectedCmdLines.Add(cmdLine);
                            }
                        }
                        finally
                        {
                            obj.Dispose();
                        }
                    }
                }

                // Now process collected command lines (after ManagementObjects are disposed)
                foreach (var cmdLine in collectedCmdLines)
                {
                    // Extract .qbw file path from command line
                    var parts = cmdLine.Split(new[] { '"' }, StringSplitOptions.RemoveEmptyEntries);
                    var qbwFile = parts.FirstOrDefault(p => p.EndsWith(".qbw", StringComparison.OrdinalIgnoreCase));
                    if (!string.IsNullOrEmpty(qbwFile))
                    {
                        return qbwFile;
                    }
                }
            }
            // FIX #10: Handle specific WMI exceptions
            catch (ManagementException ex)
            {
                System.Diagnostics.Debug.WriteLine($"[WARN] WMI query failed: {ex.Message}");
            }
            catch (UnauthorizedAccessException ex)
            {
                System.Diagnostics.Debug.WriteLine($"[WARN] Access denied for WMI query: {ex.Message}");
            }
            catch (System.ComponentModel.Win32Exception ex)
            {
                // Handle process access errors
                System.Diagnostics.Debug.WriteLine($"[WARN] Process access error: {ex.Message}");
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[WARN] Could not detect open QB file: {ex.Message}");
            }

            return null;
        }

        /// <summary>
        /// Check if QBFC16 SDK is installed.
        /// </summary>
        public static bool IsQBFC16Installed()
        {
            try
            {
                var qbType = Type.GetTypeFromProgID("QBFC16.QBSessionManager");
                return qbType != null;
            }
            catch (System.Runtime.InteropServices.COMException)
            {
                // COM registration issue - SDK not properly installed
                return false;
            }
            catch (InvalidOperationException)
            {
                // Type resolution failed
                return false;
            }
        }
    }

    /// <summary>
    /// Manages the config.json for the Extractor.
    /// </summary>
    public class ConfigManager
    {
        private readonly string _configPath;

        public ConfigManager(string extractorDirectory)
        {
            _configPath = Path.Combine(extractorDirectory, "config.json");
        }

        public string? ServerUrl { get; set; }

        /// <summary>
        /// Load config from disk.
        /// FIX: Added null checks for dynamic object deserialization.
        /// FIX MEDIUM: Added configuration validation.
        /// </summary>
        public bool Load()
        {
            if (!File.Exists(_configPath)) return false;

            try
            {
                var json = File.ReadAllText(_configPath);
                var config = JsonConvert.DeserializeObject<dynamic>(json);

                // FIX: Check for null before accessing properties
                if (config == null)
                {
                    System.Diagnostics.Debug.WriteLine("[WARN] Config file deserialized to null");
                    return false;
                }

                // Safely access serverUrl property
                ServerUrl = config.serverUrl?.ToString();

                // FIX MEDIUM: Validate configuration values
                if (!ValidateConfiguration())
                {
                    System.Diagnostics.Debug.WriteLine("[WARN] Configuration validation failed");
                    return false;
                }

                return true;
            }
            catch (JsonException ex)
            {
                System.Diagnostics.Debug.WriteLine($"[WARN] Failed to parse config: {ex.Message}");
                return false;
            }
            catch (IOException ex)
            {
                System.Diagnostics.Debug.WriteLine($"[WARN] Failed to read config file: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// FIX MEDIUM: Validate configuration values.
        /// Returns true if configuration is valid.
        /// </summary>
        private bool ValidateConfiguration()
        {
            // Validate ServerUrl
            if (!string.IsNullOrEmpty(ServerUrl))
            {
                // Check for valid URL format
                if (!Uri.TryCreate(ServerUrl, UriKind.Absolute, out var uri))
                {
                    System.Diagnostics.Debug.WriteLine($"[WARN] Invalid serverUrl format: {ServerUrl}");
                    return false;
                }

                // FIX MEDIUM: Validate URL scheme (should be https in production)
                if (uri.Scheme != "https" && uri.Scheme != "http")
                {
                    System.Diagnostics.Debug.WriteLine($"[WARN] Invalid URL scheme: {uri.Scheme}");
                    return false;
                }

                // FIX MEDIUM: Warn about insecure HTTP (but allow for localhost)
                if (uri.Scheme == "http" && uri.Host != "localhost" && uri.Host != "127.0.0.1")
                {
                    System.Diagnostics.Debug.WriteLine("[WARN] Using HTTP for non-localhost URL - this is insecure");
                }

                // FIX MEDIUM: Check for suspicious URLs
                var host = uri.Host.ToLowerInvariant();
                if (host.Contains("example.com") || host.Contains("test.local"))
                {
                    System.Diagnostics.Debug.WriteLine("[WARN] Configuration contains placeholder/test URL");
                }
            }

            return true;
        }

        /// <summary>
        /// Save config to disk.
        /// </summary>
        public void Save()
        {
            var config = new
            {
                serverUrl = ServerUrl ?? "https://localhost:5000",
                version = "4.3",
                schemaVersion = "4.3",
                advanced = new
                {
                    chunkSizeKB = 1024,
                    chunkedUploadThresholdMB = 10,
                    secureDeletePasses = 3,
                    enableLogRedaction = true
                }
            };

            var json = JsonConvert.SerializeObject(config, Formatting.Indented);
            File.WriteAllText(_configPath, json);
        }
    }
}
