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
        private bool _isProcessing;
        private CancellationTokenSource? _cts;

        public event EventHandler<MigrationJob>? JobStarted;
        public event EventHandler<MigrationJob>? JobCompleted;
        public event EventHandler<MigrationJob>? JobFailed;
        public event EventHandler? QueueCompleted;
        public event EventHandler<string>? LogMessage;

        public int QueuedCount => _jobQueue.Count;
        public int CompletedCount => _completedJobs.Count(j => j.Status == JobStatus.Completed);
        public int FailedCount => _completedJobs.Count(j => j.Status == JobStatus.Failed);
        public bool IsProcessing => _isProcessing;
        public MigrationJob? CurrentJob { get; private set; }

        public ReadOnlyCollection<MigrationJob> CompletedJobs => _completedJobs.AsReadOnly();

        public BulkMigrationManager()
        {
            _parser = new LogParser();
            _runner = new ExtractorRunner(_parser);
        }

        /// <summary>
        /// Add a company file to the migration queue.
        /// </summary>
        public MigrationJob EnqueueFile(string filePath)
        {
            var job = new MigrationJob
            {
                Id = Guid.NewGuid().ToString("N").Substring(0, 8).ToUpper(),
                FilePath = filePath,
                FileName = Path.GetFileName(filePath),
                Status = JobStatus.Queued,
                QueuedAt = DateTime.Now
            };

            lock (_lock)
            {
                _jobQueue.Enqueue(job);
            }

            LogMessage?.Invoke(this, $"[QUEUE] Added: {job.FileName} (ID: {job.Id})");
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
        /// </summary>
        public async Task StartProcessingAsync(int maxConcurrent = 1)
        {
            if (_isProcessing)
            {
                LogMessage?.Invoke(this, "[WARN] Queue is already processing.");
                return;
            }

            _isProcessing = true;
            _cts = new CancellationTokenSource();

            LogMessage?.Invoke(this, $"[START] Beginning queue processing. {_jobQueue.Count} jobs queued.");

            try
            {
                while (_jobQueue.Count > 0 && !_cts.Token.IsCancellationRequested)
                {
                    MigrationJob job;
                    lock (_lock)
                    {
                        if (_jobQueue.Count == 0) break;
                        job = _jobQueue.Dequeue();
                    }

                    await ProcessJobAsync(job);
                }

                LogMessage?.Invoke(this, $"[COMPLETE] Queue finished. Success: {CompletedCount}, Failed: {FailedCount}");
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
        /// </summary>
        public void StopProcessing()
        {
            _cts?.Cancel();
            LogMessage?.Invoke(this, "[STOP] Queue processing stopped.");
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
            LogMessage?.Invoke(this, "[CLEAR] Queue cleared.");
        }

        private async Task ProcessJobAsync(MigrationJob job)
        {
            CurrentJob = job;
            job.Status = JobStatus.InProgress;
            job.StartedAt = DateTime.Now;

            LogMessage?.Invoke(this, $"[PROCESSING] Starting: {job.FileName}");
            JobStarted?.Invoke(this, job);

            try
            {
                // Run the actual extraction
                await _runner.RunExtractionAsync(job.FilePath);

                job.Status = JobStatus.Completed;
                job.CompletedAt = DateTime.Now;
                LogMessage?.Invoke(this, $"[SUCCESS] Completed: {job.FileName} in {job.Duration?.TotalMinutes:F1} minutes");
                JobCompleted?.Invoke(this, job);
            }
            catch (Exception ex)
            {
                job.Status = JobStatus.Failed;
                job.CompletedAt = DateTime.Now;
                job.ErrorMessage = ex.Message;
                LogMessage?.Invoke(this, $"[FAILED] {job.FileName}: {ex.Message}");
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
        /// Generate a summary report of all jobs.
        /// </summary>
        public string GenerateSummaryReport()
        {
            var report = new System.Text.StringBuilder();
            report.AppendLine("BULK MIGRATION SUMMARY");
            report.AppendLine("=".PadRight(50, '='));
            report.AppendLine($"Total Jobs: {_completedJobs.Count}");
            report.AppendLine($"Completed: {CompletedCount}");
            report.AppendLine($"Failed: {FailedCount}");
            report.AppendLine();
            report.AppendLine("DETAILS:");
            report.AppendLine("-".PadRight(50, '-'));

            foreach (var job in _completedJobs)
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
