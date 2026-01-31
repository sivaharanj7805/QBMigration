using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;

namespace QBDesktopExtractor
{
    /// <summary>
    /// NDJSON (Newline Delimited JSON) writer for streaming per-entity output
    /// Produces warehouse/ETL-friendly output files
    /// </summary>
    public class NDJSONWriter : IDisposable
    {
        private readonly string _outputDirectory;
        private readonly IRedactingLogger _logger;
        private readonly Dictionary<string, EntityFileInfo> _entityFiles;
        private readonly JsonSerializerSettings _jsonSettings;
        private bool _disposed;

        public RunManifest Manifest { get; private set; }

        public NDJSONWriter(string outputDirectory, string sessionId, IRedactingLogger logger = null)
        {
            _outputDirectory = outputDirectory ?? throw new ArgumentNullException(nameof(outputDirectory));
            _logger = logger;
            _entityFiles = new Dictionary<string, EntityFileInfo>();

            // Create output directory
            if (!Directory.Exists(_outputDirectory))
            {
                Directory.CreateDirectory(_outputDirectory);
            }

            // Initialize manifest
            Manifest = new RunManifest
            {
                RunId = sessionId,
                StartedAt = DateTime.UtcNow,
                SchemaVersion = "4.3",
                ExtractorVersion = "4.3"
            };

            // JSON settings for consistent output
            _jsonSettings = new JsonSerializerSettings
            {
                ContractResolver = new CamelCasePropertyNamesContractResolver(),
                NullValueHandling = NullValueHandling.Ignore,
                Formatting = Formatting.None,
                DateFormatString = "yyyy-MM-ddTHH:mm:ssZ"
            };
        }

        /// <summary>
        /// Write a batch of records for an entity type
        /// Note: Content hash is computed at finalization, not per-batch
        /// </summary>
        public async Task WriteEntityBatchAsync<T>(string entityName, IEnumerable<T> records, CancellationToken ct = default)
        {
            if (string.IsNullOrEmpty(entityName))
                throw new ArgumentNullException(nameof(entityName));

            var fileInfo = GetOrCreateEntityFile(entityName);
            int count = 0;

            foreach (var record in records)
            {
                ct.ThrowIfCancellationRequested();

                string json = JsonConvert.SerializeObject(record, _jsonSettings);
                byte[] bytes = Encoding.UTF8.GetBytes(json + "\n");

                await fileInfo.Stream.WriteAsync(bytes, 0, bytes.Length, ct);

                fileInfo.RecordCount++;
                fileInfo.BytesWritten += bytes.Length;
                count++;
            }

            _logger?.Log(LogLevel.Debug, "Wrote {0} {1} records", count, entityName);
        }

        /// <summary>
        /// Write a single record
        /// </summary>
        public async Task WriteRecordAsync<T>(string entityName, T record, CancellationToken ct = default)
        {
            var fileInfo = GetOrCreateEntityFile(entityName);

            string json = JsonConvert.SerializeObject(record, _jsonSettings);
            byte[] bytes = Encoding.UTF8.GetBytes(json + "\n");

            await fileInfo.Stream.WriteAsync(bytes, 0, bytes.Length, ct);
            fileInfo.RecordCount++;
            fileInfo.BytesWritten += bytes.Length;
        }

        /// <summary>
        /// Write a structured error
        /// </summary>
        public async Task WriteErrorAsync(ExtractionError error, CancellationToken ct = default)
        {
            await WriteRecordAsync("errors", error, ct);
            Manifest.TotalErrors++;
        }

        /// <summary>
        /// Finalize all files and generate manifest
        /// </summary>
        public async Task FinalizeAsync(RunMetrics metrics, CancellationToken ct = default)
        {
            // Close all entity files and compute final hashes
            foreach (var kvp in _entityFiles)
            {
                var info = kvp.Value;
                await info.Stream.FlushAsync(ct);
                info.Stream.Close();

                // Compute file hash
                using (var fs = File.OpenRead(info.FilePath))
                using (var hasher = SHA256.Create())
                {
                    var hash = hasher.ComputeHash(fs);
                    info.FileHash = Convert.ToBase64String(hash);
                }

                Manifest.Entities.Add(new EntityManifestEntry
                {
                    EntityName = kvp.Key,
                    FileName = Path.GetFileName(info.FilePath),
                    RecordCount = info.RecordCount,
                    FileSizeBytes = info.BytesWritten,
                    Sha256 = info.FileHash,
                    Warnings = info.Warnings,
                    Errors = info.Errors
                });

                Manifest.TotalRecords += info.RecordCount;
            }

            Manifest.CompletedAt = DateTime.UtcNow;
            Manifest.DurationSeconds = (Manifest.CompletedAt.Value - Manifest.StartedAt).TotalSeconds;

            // Write metrics.json
            string metricsPath = Path.Combine(_outputDirectory, "metrics.json");
            string metricsJson = JsonConvert.SerializeObject(metrics, Formatting.Indented, _jsonSettings);
            File.WriteAllText(metricsPath, metricsJson);

            // Write run_manifest.json
            string manifestPath = Path.Combine(_outputDirectory, "run_manifest.json");
            string manifestJson = JsonConvert.SerializeObject(Manifest, Formatting.Indented, _jsonSettings);
            File.WriteAllText(manifestPath, manifestJson);

            _logger?.Log(LogLevel.Info, "NDJSON output complete: {0} entities, {1} total records",
                Manifest.Entities.Count, Manifest.TotalRecords);
        }

        private EntityFileInfo GetOrCreateEntityFile(string entityName)
        {
            if (_entityFiles.TryGetValue(entityName, out var existing))
                return existing;

            string fileName = $"{entityName.ToLowerInvariant()}.ndjson";
            string filePath = Path.Combine(_outputDirectory, fileName);

            var info = new EntityFileInfo
            {
                EntityName = entityName,
                FilePath = filePath,
                Stream = new FileStream(filePath, FileMode.Create, FileAccess.Write, FileShare.None, 65536, true)
            };

            _entityFiles[entityName] = info;
            return info;
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;

            foreach (var kvp in _entityFiles)
            {
                try { kvp.Value.Stream?.Dispose(); }
                catch (ObjectDisposedException) { /* Already disposed - safe to ignore */ }
                catch (IOException) { /* IO errors during dispose are non-critical */ }
            }
            _entityFiles.Clear();
        }

        private class EntityFileInfo
        {
            public string EntityName { get; set; }
            public string FilePath { get; set; }
            public FileStream Stream { get; set; }
            public int RecordCount { get; set; }
            public long BytesWritten { get; set; }
            public string FileHash { get; set; }  // Computed at finalization
            public int Warnings { get; set; }
            public int Errors { get; set; }
        }
    }

    /// <summary>
    /// Run manifest containing metadata about the extraction run
    /// </summary>
    public class RunManifest
    {
        [JsonProperty("runId")]
        public string RunId { get; set; }

        [JsonProperty("startedAt")]
        public DateTime StartedAt { get; set; }

        [JsonProperty("completedAt")]
        public DateTime? CompletedAt { get; set; }

        [JsonProperty("durationSeconds")]
        public double DurationSeconds { get; set; }

        [JsonProperty("schemaVersion")]
        public string SchemaVersion { get; set; }

        [JsonProperty("extractorVersion")]
        public string ExtractorVersion { get; set; }

        [JsonProperty("qbVersion")]
        public string QBVersion { get; set; }

        [JsonProperty("companyFingerprint")]
        public string CompanyFingerprint { get; set; }

        [JsonProperty("configHash")]
        public string ConfigHash { get; set; }

        [JsonProperty("isIncremental")]
        public bool IsIncremental { get; set; }

        [JsonProperty("incrementalFromDate")]
        public DateTime? IncrementalFromDate { get; set; }

        [JsonProperty("totalRecords")]
        public int TotalRecords { get; set; }

        [JsonProperty("totalWarnings")]
        public int TotalWarnings { get; set; }

        [JsonProperty("totalErrors")]
        public int TotalErrors { get; set; }

        [JsonProperty("entities")]
        public List<EntityManifestEntry> Entities { get; set; } = new List<EntityManifestEntry>();
    }

    /// <summary>
    /// Manifest entry for a single entity type
    /// </summary>
    public class EntityManifestEntry
    {
        [JsonProperty("entityName")]
        public string EntityName { get; set; }

        [JsonProperty("fileName")]
        public string FileName { get; set; }

        [JsonProperty("recordCount")]
        public int RecordCount { get; set; }

        [JsonProperty("fileSizeBytes")]
        public long FileSizeBytes { get; set; }

        [JsonProperty("sha256")]
        public string Sha256 { get; set; }

        [JsonProperty("warnings")]
        public int Warnings { get; set; }

        [JsonProperty("errors")]
        public int Errors { get; set; }
    }

    /// <summary>
    /// Run metrics for performance analysis
    /// </summary>
    public class RunMetrics
    {
        [JsonProperty("runId")]
        public string RunId { get; set; }

        [JsonProperty("startedAt")]
        public DateTime StartedAt { get; set; }

        [JsonProperty("completedAt")]
        public DateTime CompletedAt { get; set; }

        [JsonProperty("totalDurationSeconds")]
        public double TotalDurationSeconds { get; set; }

        [JsonProperty("extractionDurationSeconds")]
        public double ExtractionDurationSeconds { get; set; }

        [JsonProperty("serializationDurationSeconds")]
        public double SerializationDurationSeconds { get; set; }

        [JsonProperty("encryptionDurationSeconds")]
        public double EncryptionDurationSeconds { get; set; }

        [JsonProperty("uploadDurationSeconds")]
        public double UploadDurationSeconds { get; set; }

        [JsonProperty("entityTimings")]
        public List<EntityTiming> EntityTimings { get; set; } = new List<EntityTiming>();

        [JsonProperty("retryCount")]
        public int RetryCount { get; set; }

        [JsonProperty("peakMemoryMB")]
        public double PeakMemoryMB { get; set; }
    }

    /// <summary>
    /// Timing for a single entity extraction
    /// </summary>
    public class EntityTiming
    {
        [JsonProperty("entityName")]
        public string EntityName { get; set; }

        [JsonProperty("durationSeconds")]
        public double DurationSeconds { get; set; }

        [JsonProperty("recordCount")]
        public int RecordCount { get; set; }

        [JsonProperty("recordsPerSecond")]
        public double RecordsPerSecond { get; set; }

        [JsonProperty("retries")]
        public int Retries { get; set; }
    }

    /// <summary>
    /// Structured extraction error for errors.ndjson
    /// </summary>
    public class ExtractionError
    {
        [JsonProperty("timestamp")]
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;

        [JsonProperty("errorCode")]
        public string ErrorCode { get; set; }

        [JsonProperty("entityType")]
        public string EntityType { get; set; }

        [JsonProperty("recordId")]
        public string RecordId { get; set; }

        [JsonProperty("message")]
        public string Message { get; set; }

        [JsonProperty("severity")]
        public string Severity { get; set; } // "warning", "error", "critical"

        [JsonProperty("isRetryable")]
        public bool IsRetryable { get; set; }

        [JsonProperty("context")]
        public Dictionary<string, string> Context { get; set; }
    }
}
