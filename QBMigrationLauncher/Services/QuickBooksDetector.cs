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
        /// Uses Windows Management Instrumentation to find the command line.
        /// </summary>
        public static string? GetOpenCompanyFile()
        {
            try
            {
                // Query for QB process command line
                string query = "SELECT CommandLine FROM Win32_Process WHERE Name = 'QBW32.exe' OR Name = 'QBW.exe'";
                using var searcher = new ManagementObjectSearcher(query);

                // FIX #37: Properly dispose ManagementObject instances
                using var results = searcher.Get();
                foreach (ManagementObject obj in results)
                {
                    using (obj) // Dispose each ManagementObject
                    {
                        string? cmdLine = obj["CommandLine"]?.ToString();
                        if (!string.IsNullOrEmpty(cmdLine))
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
            catch
            {
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
        /// </summary>
        public bool Load()
        {
            if (!File.Exists(_configPath)) return false;

            try
            {
                var json = File.ReadAllText(_configPath);
                dynamic config = JsonConvert.DeserializeObject(json)!;
                ServerUrl = config.serverUrl;
                return true;
            }
            catch
            {
                return false;
            }
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
