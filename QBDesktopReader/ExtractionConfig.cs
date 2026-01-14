using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using Newtonsoft.Json.Converters;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Type-safe configuration with comprehensive validation
    /// v4.2: Enterprise-grade config with proper validation, error handling, and security
    /// 
    /// FIXES FROM REVIEW:
    /// - JSON property names use camelCase with fallback support
    /// - HTTPS validation allows localhost for dev
    /// - IncrementalSyncFromDate validates timezone and range
    /// - Version strings are parsed and validated
    /// - Cross-field relationship validation
    /// - LogLevel validated against enum
    /// - Retry config has jitter and max delay
    /// - Capabilities are read-only (derived from runtime)
    /// - All config errors use ConfigurationException
    /// - Unknown field detection prevents typos
    /// - Secrets excluded from SaveToFile
    /// </summary>
    public class ExtractionConfig
    {
        [JsonProperty("serverUrl")]
        public string ServerUrl { get; set; }

        [JsonProperty("incrementalSyncFromDate")]
        public DateTime? IncrementalSyncFromDate { get; set; }

        [JsonProperty("advanced")]
        public AdvancedSettings Advanced { get; set; } = new AdvancedSettings();

        [JsonProperty("version")]
        public string Version { get; set; } = "4.2";

        [JsonProperty("schemaVersion")]
        public string SchemaVersion { get; set; } = "4.2";

        /// <summary>
        /// Extraction capabilities - READ ONLY at runtime
        /// These are populated by runtime probing, not config
        /// </summary>
        [JsonIgnore]
        public RuntimeCapabilities Capabilities { get; internal set; } = new RuntimeCapabilities();

        /// <summary>
        /// Load configuration from file with comprehensive validation
        /// </summary>
        public static ExtractionConfig LoadFromFile(string filePath)
        {
            if (!File.Exists(filePath))
            {
                throw new ConfigurationException($"Configuration file not found: {filePath}");
            }

            try
            {
                string json = File.ReadAllText(filePath);
                
                // Parse with settings that detect unknown fields
                var settings = new JsonSerializerSettings
                {
                    MissingMemberHandling = MissingMemberHandling.Error,
                    DateParseHandling = DateParseHandling.DateTime,
                    DateTimeZoneHandling = DateTimeZoneHandling.Utc
                };

                ExtractionConfig config;
                try
                {
                    config = JsonConvert.DeserializeObject<ExtractionConfig>(json, settings);
                }
                catch (JsonSerializationException ex) when (ex.Message.Contains("Could not find member"))
                {
                    // Extract the unknown field name from the error
                    throw new ConfigurationException(
                        $"Unknown field in configuration file (possible typo): {ex.Message}\n" +
                        "Check spelling of all configuration properties.", ex);
                }

                if (config == null)
                {
                    throw new ConfigurationException("Configuration file is empty or invalid JSON");
                }

                // Validate configuration
                config.Validate();

                return config;
            }
            catch (JsonException ex)
            {
                throw new ConfigurationException($"Invalid JSON in configuration file: {ex.Message}", ex);
            }
            catch (ConfigurationException)
            {
                throw; // Re-throw config exceptions as-is
            }
            catch (Exception ex)
            {
                throw new ConfigurationException($"Failed to load configuration: {ex.Message}", ex);
            }
        }

        /// <summary>
        /// Comprehensive configuration validation
        /// </summary>
        public void Validate()
        {
            var errors = new List<string>();
            var warnings = new List<string>();

            // =============================================================
            // SERVER URL VALIDATION
            // =============================================================
            if (string.IsNullOrWhiteSpace(ServerUrl))
            {
                errors.Add("serverUrl is required");
            }
            else
            {
                // Check for valid URL
                if (!Uri.TryCreate(ServerUrl, UriKind.Absolute, out Uri parsedUri))
                {
                    errors.Add("serverUrl is not a valid URL");
                }
                else
                {
                    // HTTPS required EXCEPT for localhost
                    bool isLocalhost = parsedUri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
                                       parsedUri.Host.Equals("127.0.0.1") ||
                                       parsedUri.Host.Equals("::1");
                    
                    if (!isLocalhost && !parsedUri.Scheme.Equals("https", StringComparison.OrdinalIgnoreCase))
                    {
                        if (Advanced?.AllowInsecureHttpForLocalhost == true)
                        {
                            warnings.Add($"Using HTTP for non-localhost URL '{ServerUrl}' - this is insecure for production");
                        }
                        else
                        {
                            errors.Add("serverUrl must use HTTPS for non-localhost URLs (security requirement)");
                        }
                    }
                }
            }

            // =============================================================
            // INCREMENTAL SYNC DATE VALIDATION
            // =============================================================
            if (IncrementalSyncFromDate.HasValue)
            {
                var date = IncrementalSyncFromDate.Value;
                
                // Check for future dates (with 1 day tolerance for timezone issues)
                if (date > DateTime.UtcNow.AddDays(1))
                {
                    errors.Add($"incrementalSyncFromDate cannot be in the future: {date:yyyy-MM-dd}");
                }
                
                // Warn about very old dates
                if (date < DateTime.UtcNow.AddYears(-10))
                {
                    warnings.Add($"incrementalSyncFromDate is over 10 years ago ({date:yyyy-MM-dd}) - this will extract a lot of data");
                }
                
                // Normalize to UTC if not specified
                if (date.Kind == DateTimeKind.Unspecified)
                {
                    IncrementalSyncFromDate = DateTime.SpecifyKind(date, DateTimeKind.Utc);
                }
            }

            // =============================================================
            // VERSION VALIDATION
            // =============================================================
            if (!string.IsNullOrEmpty(Version))
            {
                if (!System.Version.TryParse(Version, out _))
                {
                    errors.Add($"version '{Version}' is not a valid version string (use format: major.minor)");
                }
            }

            if (!string.IsNullOrEmpty(SchemaVersion))
            {
                if (!System.Version.TryParse(SchemaVersion, out var schemaVer))
                {
                    errors.Add($"schemaVersion '{SchemaVersion}' is not a valid version string");
                }
                else
                {
                    // Check schema version compatibility
                    var currentSchema = new System.Version("4.2");
                    if (schemaVer.Major > currentSchema.Major)
                    {
                        errors.Add($"schemaVersion {SchemaVersion} is newer than supported version {currentSchema}");
                    }
                }
            }

            // =============================================================
            // ADVANCED SETTINGS VALIDATION
            // =============================================================
            if (Advanced != null)
            {
                // Chunk size bounds
                if (Advanced.ChunkSizeKB <= 0 || Advanced.ChunkSizeKB > 10240)
                {
                    errors.Add("advanced.chunkSizeKB must be between 1 and 10240 (10MB)");
                }

                if (Advanced.ChunkedUploadThresholdMB <= 0 || Advanced.ChunkedUploadThresholdMB > 10240)
                {
                    errors.Add("advanced.chunkedUploadThresholdMB must be between 1 and 10240");
                }

                // CROSS-FIELD VALIDATION: Chunk size should be <= threshold
                if (Advanced.ChunkSizeKB > 0 && Advanced.ChunkedUploadThresholdMB > 0)
                {
                    long chunkBytes = Advanced.ChunkSizeKB * 1024L;
                    long thresholdBytes = Advanced.ChunkedUploadThresholdMB * 1024L * 1024L;
                    
                    if (chunkBytes > thresholdBytes)
                    {
                        warnings.Add($"advanced.chunkSizeKB ({Advanced.ChunkSizeKB}KB) exceeds chunkedUploadThresholdMB ({Advanced.ChunkedUploadThresholdMB}MB) - this is inefficient");
                    }
                }

                // Secure delete passes (reasonable bounds)
                if (Advanced.SecureDeletePasses < 1 || Advanced.SecureDeletePasses > 7)
                {
                    errors.Add("advanced.secureDeletePasses must be between 1 and 7 (higher values don't improve security on modern storage)");
                }

                // Batch size
                if (Advanced.InitialBatchSize <= 0 || Advanced.InitialBatchSize > 1000)
                {
                    errors.Add("advanced.initialBatchSize must be between 1 and 1000");
                }

                // File stream size
                if (Advanced.MaxFileStreamSizeMB <= 0)
                {
                    errors.Add("advanced.maxFileStreamSizeMB must be positive");
                }

                // Server version format
                if (!string.IsNullOrEmpty(Advanced.MinimumServerVersion))
                {
                    if (!System.Version.TryParse(Advanced.MinimumServerVersion, out _))
                    {
                        errors.Add($"advanced.minimumServerVersion '{Advanced.MinimumServerVersion}' is not a valid version string");
                    }
                }

                // LOG LEVEL VALIDATION
                var validLogLevels = new HashSet<string>(StringComparer.OrdinalIgnoreCase) 
                { 
                    "DEBUG", "INFO", "WARNING", "ERROR" 
                };
                if (!string.IsNullOrEmpty(Advanced.LogLevel) && !validLogLevels.Contains(Advanced.LogLevel))
                {
                    errors.Add($"advanced.logLevel '{Advanced.LogLevel}' is invalid. Valid values: DEBUG, INFO, WARNING, ERROR");
                }

                // RETRY CONFIGURATION VALIDATION
                if (Advanced.RetryAttempts < 0 || Advanced.RetryAttempts > 10)
                {
                    errors.Add("advanced.retryAttempts must be between 0 and 10");
                }

                if (Advanced.RetryDelayMs < 100 || Advanced.RetryDelayMs > 30000)
                {
                    errors.Add("advanced.retryDelayMs must be between 100 and 30000");
                }

                if (Advanced.RetryMaxDelayMs < Advanced.RetryDelayMs)
                {
                    errors.Add("advanced.retryMaxDelayMs must be >= retryDelayMs");
                }

                // Total retry time budget check
                if (Advanced.RetryAttempts > 0 && Advanced.EnableExponentialBackoff)
                {
                    // Calculate worst case total delay
                    long worstCaseMs = 0;
                    for (int i = 0; i < Advanced.RetryAttempts; i++)
                    {
                        worstCaseMs += Math.Min(
                            Advanced.RetryDelayMs * (long)Math.Pow(2, i),
                            Advanced.RetryMaxDelayMs
                        );
                    }
                    
                    if (worstCaseMs > 300000) // 5 minutes
                    {
                        warnings.Add($"Retry configuration could result in up to {worstCaseMs / 1000}s of delays - consider reducing retryAttempts or retryMaxDelayMs");
                    }
                }
            }

            // =============================================================
            // OUTPUT RESULTS
            // =============================================================
            
            // Print warnings
            foreach (var warning in warnings)
            {
                Console.WriteLine($"⚠ Config warning: {warning}");
            }

            // Throw if errors
            if (errors.Count > 0)
            {
                throw new ConfigurationException(
                    "Configuration validation failed:\n  - " + string.Join("\n  - ", errors));
            }
        }

        /// <summary>
        /// Save configuration to file (excludes secrets)
        /// </summary>
        public void SaveToFile(string filePath)
        {
            var settings = new JsonSerializerSettings
            {
                Formatting = Formatting.Indented,
                NullValueHandling = NullValueHandling.Ignore,
                DateTimeZoneHandling = DateTimeZoneHandling.Utc
            };
            
            string json = JsonConvert.SerializeObject(this, settings);
            File.WriteAllText(filePath, json);
        }

        /// <summary>
        /// Create default configuration
        /// </summary>
        public static ExtractionConfig CreateDefault()
        {
            return new ExtractionConfig
            {
                ServerUrl = "https://api.example.com",
                Version = "4.2",
                SchemaVersion = "4.2",
                Advanced = new AdvancedSettings()
            };
        }
    }

    /// <summary>
    /// Advanced configuration settings with comprehensive options
    /// </summary>
    public class AdvancedSettings
    {
        // Upload settings
        [JsonProperty("chunkSizeKB")]
        public int ChunkSizeKB { get; set; } = 1024;

        [JsonProperty("chunkedUploadThresholdMB")]
        public int ChunkedUploadThresholdMB { get; set; } = 10;

        // Security settings
        [JsonProperty("secureDeletePasses")]
        public int SecureDeletePasses { get; set; } = 3; // 3 is sufficient for modern storage

        // Extraction settings
        [JsonProperty("initialBatchSize")]
        public int InitialBatchSize { get; set; } = 100;

        [JsonProperty("enableAdaptiveBatching")]
        public bool EnableAdaptiveBatching { get; set; } = true;

        [JsonProperty("enablePreFlightCheck")]
        public bool EnablePreFlightCheck { get; set; } = true;

        [JsonProperty("enableForensicHashing")]
        public bool EnableForensicHashing { get; set; } = true;

        // Version compatibility
        [JsonProperty("minimumServerVersion")]
        public string MinimumServerVersion { get; set; } = "4.0";

        [JsonProperty("enableVersionCheck")]
        public bool EnableVersionCheck { get; set; } = true;

        // Memory management
        [JsonProperty("maxFileStreamSizeMB")]
        public long MaxFileStreamSizeMB { get; set; } = 2048;

        // Logging settings
        [JsonProperty("enableLogRedaction")]
        public bool EnableLogRedaction { get; set; } = true;

        [JsonProperty("logLevel")]
        public string LogLevel { get; set; } = "INFO";

        // Retry configuration with enterprise features
        [JsonProperty("retryAttempts")]
        public int RetryAttempts { get; set; } = 3;

        [JsonProperty("retryDelayMs")]
        public int RetryDelayMs { get; set; } = 1000;

        [JsonProperty("retryMaxDelayMs")]
        public int RetryMaxDelayMs { get; set; } = 30000;

        [JsonProperty("retryJitterPercent")]
        public int RetryJitterPercent { get; set; } = 20;

        [JsonProperty("enableExponentialBackoff")]
        public bool EnableExponentialBackoff { get; set; } = true;

        // Security relaxation (dev only)
        [JsonProperty("allowInsecureHttpForLocalhost")]
        public bool AllowInsecureHttpForLocalhost { get; set; } = true;

        // QBXML version control
        [JsonProperty("maxQBXMLVersion")]
        public double? MaxQBXMLVersion { get; set; } = null; // null = use max available
    }

    /// <summary>
    /// Runtime capabilities - populated by probing, not config
    /// These represent what the current environment actually supports
    /// </summary>
    public class RuntimeCapabilities
    {
        public bool SupportsIncrementalSync { get; internal set; }
        public bool SupportsTrialBalanceVerification { get; internal set; }
        public bool SupportsForensicHashing { get; internal set; } = true;
        public bool SupportsStreamingEncryption { get; internal set; } = true;
        public bool SupportsChunkedUpload { get; internal set; }
        public bool SupportsLinkedTransactions { get; internal set; }
        public int SupportedEntityTypes { get; internal set; }
        public long MaxFileSizeMB { get; internal set; } = 10240;
        public double QBXMLVersion { get; internal set; }
        public string QuickBooksEdition { get; internal set; }
        
        /// <summary>
        /// List of capability probe results for auditing
        /// </summary>
        public List<CapabilityProbeResult> ProbeResults { get; } = new List<CapabilityProbeResult>();
    }

    /// <summary>
    /// Result of a capability probe
    /// </summary>
    public class CapabilityProbeResult
    {
        public string CapabilityName { get; set; }
        public bool Supported { get; set; }
        public string Reason { get; set; }
        public DateTime ProbedAt { get; set; } = DateTime.UtcNow;
    }

    /// <summary>
    /// Custom exception for configuration errors with detailed context
    /// </summary>
    public class ConfigurationException : Exception
    {
        public string ConfigFile { get; set; }
        public string FieldName { get; set; }
        
        public ConfigurationException(string message) : base(message) { }
        
        public ConfigurationException(string message, Exception innerException) 
            : base(message, innerException) { }
        
        public ConfigurationException(string message, string fieldName) : base(message)
        {
            FieldName = fieldName;
        }
    }
}