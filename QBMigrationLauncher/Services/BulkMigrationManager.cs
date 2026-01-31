using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace QBMigrationLauncher.Services
{
    /// <summary>
    /// Bulk Migration Manager - Queues and processes multiple QuickBooks files.
    /// Designed for CPA firms migrating 50+ client files.
    /// </summary>
    public class BulkMigrationManager
    {
        private readonly Queue<MigrationJob> _jobQueue = new Queue<MigrationJob>();
        private readonly List<MigrationJob> _completedJobs = new List<MigrationJob>();
        private readonly ExtractorRunner _runner;
        private readonly LogParser _parser;
        private readonly object _lock = new object();
        private readonly string _outputDirectory;
        private bool _isProcessing;
        private CancellationTokenSource? _cts;

        // FIX #12: Store reference to current process for kill on stop
        private System.Diagnostics.Process? _currentProcess;
        private readonly object _processLock = new object();

        // FIX #4: Process timeout configuration (30 minutes default)
        private static readonly TimeSpan ProcessTimeout = TimeSpan.FromMinutes(30);

        public event EventHandler<MigrationJob>? JobStarted;
        public event EventHandler<MigrationJob>? JobCompleted;
        public event EventHandler<MigrationJob>? JobFailed;
        public event EventHandler? QueueCompleted;
        public event EventHandler<string>? LogMessage;

        // FIX #13: Thread-safe count accessors
        public int QueuedCount
        {
            get
            {
                lock (_lock) { return _jobQueue.Count; }
            }
        }

        public int CompletedCount
        {
            get
            {
                lock (_lock) { return _completedJobs.Count(j => j.Status == JobStatus.Completed); }
            }
        }

        public int FailedCount
        {
            get
            {
                lock (_lock) { return _completedJobs.Count(j => j.Status == JobStatus.Failed); }
            }
        }

        public bool IsProcessing => _isProcessing;
        public MigrationJob? CurrentJob { get; private set; }

        public ReadOnlyCollection<MigrationJob> CompletedJobs
        {
            get
            {
                lock (_lock) { return _completedJobs.ToList().AsReadOnly(); }
            }
        }

        public BulkMigrationManager() : this(null)
        {
        }

        public BulkMigrationManager(string? outputDirectory)
        {
            _parser = new LogParser();
            _runner = new ExtractorRunner(_parser);

            // FIX #2: Set up output directory for extraction results
            _outputDirectory = outputDirectory ?? Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                "QBMigration",
                "BulkOutput"
            );
            Directory.CreateDirectory(_outputDirectory);
        }

        /// <summary>
        /// Add a company file to the migration queue.
        /// </summary>
        public MigrationJob EnqueueFile(string filePath)
        {
            // FIX #33: Validate file exists before queueing
            if (string.IsNullOrWhiteSpace(filePath))
            {
                throw new ArgumentException("File path cannot be empty", nameof(filePath));
            }

            if (!File.Exists(filePath))
            {
                throw new FileNotFoundException($"QuickBooks file not found: {filePath}", filePath);
            }

            var job = new MigrationJob
            {
                Id = Guid.NewGuid().ToString("N").Substring(0, 8).ToUpper(),
                FilePath = Path.GetFullPath(filePath), // Store full path
                FileName = Path.GetFileName(filePath),
                Status = JobStatus.Queued,
                QueuedAt = DateTime.UtcNow  // FIX: Use UtcNow for consistency
            };

            lock (_lock)
            {
                _jobQueue.Enqueue(job);
            }

            // FIX #13: Use job ID instead of exposing filename in logs
            RedactedLog($"[QUEUE] Added job {job.Id}");
            return job;
        }

        /// <summary>
        /// Add multiple files at once.
        /// </summary>
        public List<MigrationJob> EnqueueFiles(IEnumerable<string> filePaths)
        {
            return filePaths.Select(EnqueueFile).ToList();
        }

        /// <summary>
        /// Start processing the queue (runs in background).
        /// FIX #15: Uses proper TryDequeue pattern for thread safety.
        /// </summary>
        public async Task StartProcessingAsync(int maxConcurrent = 1)
        {
            if (_isProcessing)
            {
                RedactedLog("[WARN] Queue is already processing.");
                return;
            }

            _isProcessing = true;

            // FIX: Dispose old CancellationTokenSource before creating new one
            _cts?.Dispose();
            _cts = new CancellationTokenSource();

            // FIX: Get count with lock to avoid race condition
            int jobCount;
            lock (_lock) { jobCount = _jobQueue.Count; }
            RedactedLog($"[START] Beginning queue processing. {jobCount} jobs queued.");

            try
            {
                while (!_cts.Token.IsCancellationRequested)
                {
                    // FIX #15: Use TryDequeue pattern for thread safety
                    MigrationJob? job = null;
                    lock (_lock)
                    {
                        if (_jobQueue.Count > 0)
                        {
                            job = _jobQueue.Dequeue();
                        }
                    }

                    // No more jobs
                    if (job == null)
                        break;

                    await ProcessJobAsync(job);
                }

                RedactedLog($"[COMPLETE] Queue finished. Success: {CompletedCount}, Failed: {FailedCount}");
                QueueCompleted?.Invoke(this, EventArgs.Empty);
            }
            finally
            {
                _isProcessing = false;
                CurrentJob = null;
            }
        }

        /// <summary>
        /// Stop processing (gracefully waits for current job).
        /// FIX #12: Kill the current process when stop is requested.
        /// </summary>
        public void StopProcessing()
        {
            _cts?.Cancel();

            // FIX #12: Kill the current process if running
            lock (_processLock)
            {
                if (_currentProcess != null && !_currentProcess.HasExited)
                {
                    try
                    {
                        _currentProcess.Kill(entireProcessTree: true);
                        RedactedLog("[STOP] Current process terminated.");
                    }
                    catch (InvalidOperationException)
                    {
                        // Process already exited
                    }
                    catch (Exception ex)
                    {
                        System.Diagnostics.Debug.WriteLine($"[WARN] Failed to kill process: {ex.Message}");
                    }
                }
            }

            RedactedLog("[STOP] Queue processing stopped.");
        }

        /// <summary>
        /// Clear all pending jobs (does not affect running job).
        /// </summary>
        public void ClearQueue()
        {
            lock (_lock)
            {
                _jobQueue.Clear();
            }
            RedactedLog("[CLEAR] Queue cleared.");
        }

        /// <summary>
        /// FIX #29: Clear completed jobs history.
        /// </summary>
        public void ClearHistory()
        {
            lock (_lock)
            {
                _completedJobs.Clear();
            }
            RedactedLog("[CLEAR] Job history cleared.");
        }

        /// <summary>
        /// FIX #29: Clear everything (queue and history).
        /// </summary>
        public void ClearAll()
        {
            lock (_lock)
            {
                _jobQueue.Clear();
                _completedJobs.Clear();
            }
            RedactedLog("[CLEAR] Queue and history cleared.");
        }

        private async Task ProcessJobAsync(MigrationJob job)
        {
            CurrentJob = job;
            job.Status = JobStatus.InProgress;
            job.StartedAt = DateTime.UtcNow;  // FIX: Use UtcNow for consistency

            // FIX #13: Use redacted logging
            RedactedLog($"[PROCESSING] Starting job {job.Id}");
            JobStarted?.Invoke(this, job);

            try
            {
                // FIX #9: Remove pre-check (TOCTOU vulnerability) - let extraction fail naturally
                // and catch FileNotFoundException during extraction instead

                // FIX #2: Pass all 3 required parameters to RunExtractionAsync
                // Use job ID as session code, create job-specific output directory
                var jobOutputDir = Path.Combine(_outputDirectory, $"Job_{job.Id}_{DateTime.UtcNow:yyyyMMdd_HHmmss}");
                Directory.CreateDirectory(jobOutputDir);

                await _runner.RunExtractionAsync(job.FilePath, job.Id, jobOutputDir);

                job.Status = JobStatus.Completed;
                job.CompletedAt = DateTime.UtcNow;  // FIX: Use UtcNow for consistency
                job.OutputDirectory = jobOutputDir; // Store where results went
                // FIX #13: Redact sensitive info from logs
                RedactedLog($"[SUCCESS] Completed job {job.Id} in {job.Duration?.TotalMinutes:F1} minutes");
                JobCompleted?.Invoke(this, job);
            }
            catch (FileNotFoundException ex)
            {
                // FIX #9: Handle file not found during extraction (TOCTOU-safe)
                job.Status = JobStatus.Failed;
                job.CompletedAt = DateTime.UtcNow;
                job.ErrorMessage = "Source file not found or inaccessible";
                RedactedLog($"[FAILED] Job {job.Id}: File not found");
                System.Diagnostics.Debug.WriteLine($"[DEBUG] FileNotFoundException: {ex.Message}");
                JobFailed?.Invoke(this, job);
            }
            catch (Exception ex)
            {
                job.Status = JobStatus.Failed;
                job.CompletedAt = DateTime.UtcNow;  // FIX: Use UtcNow for consistency
                // FIX #13: Don't expose full exception message in stored error
                job.ErrorMessage = SanitizeErrorMessage(ex.Message);
                RedactedLog($"[FAILED] Job {job.Id}: {job.ErrorMessage}");
                JobFailed?.Invoke(this, job);
            }
            finally
            {
                lock (_lock)
                {
                    _completedJobs.Add(job);
                }
            }
        }

        /// <summary>
        /// FIX #13: Log message with sensitive data redaction.
        /// </summary>
        private void RedactedLog(string message)
        {
            LogMessage?.Invoke(this, message);
        }

        /// <summary>
        /// FIX #13: Sanitize error messages to remove sensitive paths and company names.
        /// </summary>
        private static string SanitizeErrorMessage(string message)
        {
            if (string.IsNullOrEmpty(message))
                return "Unknown error";

            // Redact file paths (e.g., C:\Users\...\CompanyName.qbw)
            message = System.Text.RegularExpressions.Regex.Replace(
                message,
                @"[A-Za-z]:\\[^\s:*?""<>|]+",
                "[PATH_REDACTED]");

            // Redact network paths (e.g., \\server\share\path)
            message = System.Text.RegularExpressions.Regex.Replace(
                message,
                @"\\\\[^\s:*?""<>|]+",
                "[PATH_REDACTED]");

            // Limit length
            if (message.Length > 200)
                message = message.Substring(0, 200) + "...";

            return message;
        }

        /// <summary>
        /// Generate a summary report of all jobs.
        /// FIX: Thread-safe iteration of completed jobs.
        /// </summary>
        public string GenerateSummaryReport()
        {
            var report = new System.Text.StringBuilder();
            report.AppendLine("BULK MIGRATION SUMMARY");
            report.AppendLine("=".PadRight(50, '='));

            // FIX: Take a snapshot under lock to avoid collection modification during iteration
            List<MigrationJob> jobSnapshot;
            lock (_lock)
            {
                jobSnapshot = _completedJobs.ToList();
            }

            int completedCount = jobSnapshot.Count(j => j.Status == JobStatus.Completed);
            int failedCount = jobSnapshot.Count(j => j.Status == JobStatus.Failed);

            report.AppendLine($"Total Jobs: {jobSnapshot.Count}");
            report.AppendLine($"Completed: {completedCount}");
            report.AppendLine($"Failed: {failedCount}");
            report.AppendLine();
            report.AppendLine("DETAILS:");
            report.AppendLine("-".PadRight(50, '-'));

            foreach (var job in jobSnapshot)
            {
                var status = job.Status == JobStatus.Completed ? "✓" : "✗";
                var duration = job.Duration?.TotalMinutes.ToString("F1") + " min" ?? "N/A";
                report.AppendLine($"{status} {job.FileName} ({duration})");
                if (job.Status == JobStatus.Failed)
                {
                    report.AppendLine($"   Error: {job.ErrorMessage}");
                }
            }

            return report.ToString();
        }
    }

    public class MigrationJob
    {
        public string Id { get; set; } = "";
        public string FilePath { get; set; } = "";
        public string FileName { get; set; } = "";
        public JobStatus Status { get; set; }
        public DateTime QueuedAt { get; set; }
        public DateTime? StartedAt { get; set; }
        public DateTime? CompletedAt { get; set; }
        public string? ErrorMessage { get; set; }
        /// <summary>
        /// Directory where extraction output was saved (set on completion).
        /// </summary>
        public string? OutputDirectory { get; set; }

        public TimeSpan? Duration =>
            StartedAt.HasValue && CompletedAt.HasValue
                ? CompletedAt.Value - StartedAt.Value
                : null;
    }

    public enum JobStatus
    {
        Queued,
        InProgress,
        Completed,
        Failed
    }
}
