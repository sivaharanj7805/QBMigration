using System;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Win32;
using QBMigrationLauncher.Services;

namespace QBMigrationLauncher.ViewModels
{
    public partial class BulkMigrationViewModel : ObservableObject
    {
        private readonly BulkMigrationManager _manager;

        [ObservableProperty]
        private ObservableCollection<JobViewModel> _allJobs = new ObservableCollection<JobViewModel>();

        [ObservableProperty]
        private int _queuedCount;

        [ObservableProperty]
        private int _completedCount;

        [ObservableProperty]
        private int _failedCount;

        [ObservableProperty]
        private bool _isProcessing;

        [ObservableProperty]
        private string _currentJobName = "";

        [ObservableProperty]
        private string _logOutput = "";

        public BulkMigrationViewModel()
        {
            _manager = new BulkMigrationManager();

            // FIX #15 & #46: Use BeginInvoke (non-blocking) and check for null App.Current
            _manager.LogMessage += (s, msg) =>
            {
                SafeDispatch(() => LogOutput += msg + Environment.NewLine);
            };

            _manager.JobStarted += (s, job) =>
            {
                SafeDispatch(() =>
                {
                    CurrentJobName = job.FileName;
                    UpdateJobInList(job);
                    UpdateCounts();
                });
            };

            _manager.JobCompleted += (s, job) =>
            {
                SafeDispatch(() =>
                {
                    UpdateJobInList(job);
                    UpdateCounts();
                });
            };

            _manager.JobFailed += (s, job) =>
            {
                SafeDispatch(() =>
                {
                    UpdateJobInList(job);
                    UpdateCounts();
                });
            };

            _manager.QueueCompleted += (s, e) =>
            {
                SafeDispatch(() =>
                {
                    IsProcessing = false;
                    CurrentJobName = "";
                    LogOutput += Environment.NewLine + _manager.GenerateSummaryReport();
                });
            };
        }

        /// <summary>
        /// FIX #15 & #46: Safely dispatch to UI thread with null check and non-blocking call.
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

        [RelayCommand]
        private void AddFiles()
        {
            var dialog = new OpenFileDialog
            {
                Multiselect = true,
                Filter = "QuickBooks Files (*.qbw)|*.qbw|All Files (*.*)|*.*",
                Title = "Select QuickBooks Company Files"
            };

            if (dialog.ShowDialog() == true)
            {
                foreach (var file in dialog.FileNames)
                {
                    try
                    {
                        // FIX #33: EnqueueFile now validates file exists
                        var job = _manager.EnqueueFile(file);
                        AllJobs.Add(new JobViewModel(job));
                    }
                    catch (FileNotFoundException ex)
                    {
                        LogOutput += $"[ERROR] File not found: {ex.FileName}\n";
                    }
                    catch (ArgumentException ex)
                    {
                        LogOutput += $"[ERROR] Invalid file: {ex.Message}\n";
                    }
                }
                UpdateCounts();
            }
        }

        [RelayCommand]
        private async Task StartQueue()
        {
            if (IsProcessing) return;

            IsProcessing = true;
            await _manager.StartProcessingAsync();
        }

        [RelayCommand]
        private void StopQueue()
        {
            _manager.StopProcessing();
            IsProcessing = false;
        }

        [RelayCommand]
        private void ClearQueue()
        {
            // FIX #29: Use ClearAll to also clear completed jobs history
            _manager.ClearAll();
            AllJobs.Clear();
            UpdateCounts();
        }

        private void UpdateJobInList(MigrationJob job)
        {
            var vm = AllJobs.FirstOrDefault(j => j.Id == job.Id);
            if (vm != null)
            {
                vm.UpdateFromJob(job);
            }
        }

        private void UpdateCounts()
        {
            QueuedCount = _manager.QueuedCount;
            CompletedCount = _manager.CompletedCount;
            FailedCount = _manager.FailedCount;
        }
    }

    public partial class JobViewModel : ObservableObject
    {
        [ObservableProperty]
        private string _id = "";

        [ObservableProperty]
        private string _fileName = "";

        [ObservableProperty]
        private JobStatus _status;

        [ObservableProperty]
        private DateTime _queuedAt;

        [ObservableProperty]
        private string? _errorMessage;

        [ObservableProperty]
        private string _durationText = "";

        public string StatusIcon => Status switch
        {
            JobStatus.Queued => "⏳",
            JobStatus.InProgress => "🔄",
            JobStatus.Completed => "✅",
            JobStatus.Failed => "❌",
            _ => "❓"
        };

        public JobViewModel(MigrationJob job)
        {
            UpdateFromJob(job);
        }

        public void UpdateFromJob(MigrationJob job)
        {
            Id = job.Id;
            FileName = job.FileName;
            Status = job.Status;
            QueuedAt = job.QueuedAt;
            ErrorMessage = job.ErrorMessage;
            DurationText = job.Duration.HasValue ? $"{job.Duration.Value.TotalMinutes:F1} min" : "-";
            OnPropertyChanged(nameof(StatusIcon));
        }
    }
}
