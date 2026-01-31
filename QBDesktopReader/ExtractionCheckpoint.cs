using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Manages extraction checkpoints for resumability
    /// Allows resuming from last successful entity if extraction fails
    /// </summary>
    public class ExtractionCheckpoint
    {
        private readonly string _checkpointPath;
        private readonly IRedactingLogger _logger;

        public ExtractionCheckpoint(string outputDirectory, IRedactingLogger logger = null)
        {
            _checkpointPath = Path.Combine(outputDirectory, ".extraction_checkpoint.json");
            _logger = logger;
        }

        /// <summary>
        /// Save checkpoint after completing an entity
        /// </summary>
        public void SaveAfterEntity(CheckpointState state)
        {
            try
            {
                state.LastUpdated = DateTime.UtcNow;
                string json = JsonConvert.SerializeObject(state, Formatting.Indented);
                File.WriteAllText(_checkpointPath, json);
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Failed to save checkpoint: {0}", ex.Message);
            }
        }

        /// <summary>
        /// Load checkpoint if exists and matches session
        /// </summary>
        public CheckpointState Load(string sessionId)
        {
            if (!File.Exists(_checkpointPath))
                return null;

            try
            {
                string json = File.ReadAllText(_checkpointPath);
                var state = JsonConvert.DeserializeObject<CheckpointState>(json);

                // Only use if same session
                if (state?.SessionId == sessionId)
                {
                    _logger?.Log(LogLevel.Info, "Resuming from checkpoint: {0} entities completed", 
                        state.CompletedEntities.Count);
                    return state;
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Failed to load checkpoint: {0}", ex.Message);
            }

            return null;
        }

        /// <summary>
        /// Clear checkpoint after successful completion
        /// </summary>
        public void Clear()
        {
            try
            {
                if (File.Exists(_checkpointPath))
                    File.Delete(_checkpointPath);
            }
            catch (Exception ex)
            {
                // Log but don't fail - checkpoint cleanup is not critical
                _logger?.Log(LogLevel.Debug, "Failed to clear checkpoint: {0}", ex.Message);
            }
        }

        /// <summary>
        /// Check if entity was already extracted in this session
        /// </summary>
        public bool IsEntityComplete(CheckpointState state, string entityName)
        {
            return state?.CompletedEntities?.Contains(entityName) ?? false;
        }
    }

    /// <summary>
    /// State of an extraction checkpoint
    /// </summary>
    public class CheckpointState
    {
        [JsonProperty("sessionId")]
        public string SessionId { get; set; }

        [JsonProperty("startedAt")]
        public DateTime StartedAt { get; set; }

        [JsonProperty("lastUpdated")]
        public DateTime LastUpdated { get; set; }

        [JsonProperty("isIncremental")]
        public bool IsIncremental { get; set; }

        [JsonProperty("incrementalFromDate")]
        public DateTime? IncrementalFromDate { get; set; }

        [JsonProperty("completedEntities")]
        public System.Collections.Generic.List<string> CompletedEntities { get; set; } 
            = new System.Collections.Generic.List<string>();

        [JsonProperty("totalRecordsExtracted")]
        public int TotalRecordsExtracted { get; set; }

        [JsonProperty("currentPhase")]
        public string CurrentPhase { get; set; }
    }

    /// <summary>
    /// Tracks last successful sync for incremental extraction
    /// </summary>
    public class SyncMarker
    {
        private readonly string _markerPath;
        private readonly IRedactingLogger _logger;

        public SyncMarker(string dataDirectory, string companyId, IRedactingLogger logger = null)
        {
            // Create safe filename from company ID
            string safeCompanyId = ComputeHash(companyId ?? "default");
            _markerPath = Path.Combine(dataDirectory, $".sync_marker_{safeCompanyId}.json");
            _logger = logger;
        }

        /// <summary>
        /// Save sync marker after successful extraction
        /// </summary>
        public void Save(SyncMarkerState state)
        {
            try
            {
                string json = JsonConvert.SerializeObject(state, Formatting.Indented);
                File.WriteAllText(_markerPath, json);
                _logger?.Log(LogLevel.Info, "Sync marker saved: last sync at {0:yyyy-MM-dd HH:mm:ss} UTC", 
                    state.LastSyncTime);
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Failed to save sync marker: {0}", ex.Message);
            }
        }

        /// <summary>
        /// Load last sync marker
        /// </summary>
        public SyncMarkerState Load()
        {
            if (!File.Exists(_markerPath))
            {
                _logger?.Log(LogLevel.Info, "No sync marker found - will perform full extraction");
                return null;
            }

            try
            {
                string json = File.ReadAllText(_markerPath);
                var state = JsonConvert.DeserializeObject<SyncMarkerState>(json);
                _logger?.Log(LogLevel.Info, "Loaded sync marker: last sync at {0:yyyy-MM-dd HH:mm:ss} UTC",
                    state.LastSyncTime);
                return state;
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Failed to load sync marker: {0}", ex.Message);
                return null;
            }
        }

        /// <summary>
        /// Get the date to use for incremental sync
        /// </summary>
        public DateTime? GetIncrementalFromDate()
        {
            var state = Load();
            return state?.LastSyncTime;
        }

        private static string ComputeHash(string input)
        {
            using (var sha = SHA256.Create())
            {
                var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(input));
                return BitConverter.ToString(bytes).Replace("-", "").Substring(0, 16).ToLowerInvariant();
            }
        }
    }

    /// <summary>
    /// State of a sync marker
    /// </summary>
    public class SyncMarkerState
    {
        [JsonProperty("lastSyncTime")]
        public DateTime LastSyncTime { get; set; }

        [JsonProperty("lastSyncTimeLocal")]
        public DateTime LastSyncTimeLocal { get; set; }

        [JsonProperty("sessionId")]
        public string SessionId { get; set; }

        [JsonProperty("recordsExtracted")]
        public int RecordsExtracted { get; set; }

        [JsonProperty("companyFingerprint")]
        public string CompanyFingerprint { get; set; }

        [JsonProperty("qbVersion")]
        public string QBVersion { get; set; }

        [JsonProperty("extractorVersion")]
        public string ExtractorVersion { get; set; } = "4.3";
    }

    /// <summary>
    /// Support bundle generator for troubleshooting
    /// </summary>
    public class SupportBundle
    {
        private readonly IRedactingLogger _logger;
        private readonly LogRedactor _redactor;

        public SupportBundle(IRedactingLogger logger = null)
        {
            _logger = logger;
            _redactor = new LogRedactor(new RedactionConfig { Enabled = true });
        }

        /// <summary>
        /// Generate a support bundle ZIP (redacted)
        /// </summary>
        public string Generate(string outputDirectory, RunManifest manifest, ExtractionRunSummary runSummary)
        {
            string bundlePath = Path.Combine(outputDirectory, $"support_bundle_{DateTime.UtcNow:yyyyMMdd_HHmmss}.txt");

            try
            {
                var sb = new StringBuilder();
                sb.AppendLine("=== QB EXTRACTOR SUPPORT BUNDLE ===");
                sb.AppendLine($"Generated: {DateTime.UtcNow:yyyy-MM-dd HH:mm:ss} UTC");
                sb.AppendLine();

                // Run info (redacted)
                sb.AppendLine("--- RUN INFO ---");
                sb.AppendLine($"Session ID: {manifest?.RunId ?? "N/A"}");
                sb.AppendLine($"Started: {manifest?.StartedAt:yyyy-MM-dd HH:mm:ss} UTC");
                sb.AppendLine($"Completed: {manifest?.CompletedAt:yyyy-MM-dd HH:mm:ss} UTC");
                sb.AppendLine($"Duration: {manifest?.DurationSeconds:F1}s");
                sb.AppendLine($"Schema Version: {manifest?.SchemaVersion}");
                sb.AppendLine();

                // Entity summary
                sb.AppendLine("--- ENTITY SUMMARY ---");
                if (manifest?.Entities != null)
                {
                    foreach (var entity in manifest.Entities)
                    {
                        sb.AppendLine($"{entity.EntityName}: {entity.RecordCount} records, {entity.Errors} errors");
                    }
                }
                sb.AppendLine();

                // Errors (redacted)
                sb.AppendLine("--- ERRORS ---");
                if (runSummary?.Errors != null)
                {
                    foreach (var error in runSummary.Errors)
                    {
                        sb.AppendLine(_redactor.Redact(error));
                    }
                }
                sb.AppendLine();

                // Warnings
                sb.AppendLine("--- WARNINGS ---");
                if (runSummary?.Warnings != null)
                {
                    foreach (var warning in runSummary.Warnings)
                    {
                        sb.AppendLine(_redactor.Redact(warning));
                    }
                }

                File.WriteAllText(bundlePath, sb.ToString());
                _logger?.Log(LogLevel.Info, "Support bundle generated: {0}", Path.GetFileName(bundlePath));

                return bundlePath;
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Error, "Failed to generate support bundle: {0}", ex.Message);
                return null;
            }
        }
    }
}
