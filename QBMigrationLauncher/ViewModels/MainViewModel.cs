using System;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Input;
using System.Windows.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using QBMigrationLauncher.Services;

namespace QBMigrationLauncher.ViewModels
{
    public partial class MainViewModel : ObservableObject
    {
        private readonly ExtractorRunner _runner;
        private readonly LogParser _parser;
        private readonly HealthCheckService _healthCheck;
        private readonly CertificateGenerator _certificateGenerator;
        private readonly VarianceReportService _varianceReportService;
        private readonly string _outputDirectory;

        [ObservableProperty]
        private string _connectionStatusText = "Searching for QuickBooks...";

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
        private string _currentStatusMessage = "Ready to start.";

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
                
                // Generate HTML report
                var reportPath = _certificateGenerator.GenerateHealthCheckReport(result, SelectedFile ?? "Unknown");
                
                LogOutput += $"[INFO] Health Check Complete: {result.GetSummary()}\n";
                LogOutput += $"[INFO] Report saved to: {reportPath}\n";
                
                CurrentStatusMessage = result.GetSummary();
                
                // Open the report in browser
                Process.Start(new ProcessStartInfo(reportPath) { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                LogOutput += $"[ERROR] Health check failed: {ex.Message}\n";
                CurrentStatusMessage = "Health check failed";
            }
        }

        [RelayCommand]
        private async Task StartMigration()
        {
            if (IsMigrating) return;

            // ============================================================================
            // LICENSE VALIDATION - Required before any migration
            // ============================================================================
            LogOutput = "[INFO] Validating license...\n";
            CurrentStatusMessage = "Validating license...";
            
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

            string migrationId = Guid.NewGuid().ToString("N").Substring(0, 12).ToUpper();

            try
            {
                await _runner.RunExtractionAsync(SelectedFile);
                
                CurrentStatusMessage = "Migration Complete! Generating certificate...";
                
                // Generate Migration Certificate
                var certData = new MigrationCertificateData
                {
                    CompanyName = SelectedFile ?? "Unknown",
                    MigrationId = Guid.NewGuid().ToString("N").Substring(0, 12).ToUpper(),
                    MigrationDate = DateTime.Now,
                    SourceFileName = SelectedFile ?? "Unknown",
                    RealmId = "PENDING_VERIFICATION",
                    SourceHash = "SHA256_HASH_PLACEHOLDER",
                    TrialBalanceDesktop = 0,
                    TrialBalanceOnline = 0,
                    CustomerCount = 0,
                    VendorCount = 0,
                    InvoiceCount = 0,
                    BillCount = 0,
                    AuthorizedBy = Environment.UserName
                };
                
                var certPath = _certificateGenerator.GenerateMigrationCertificate(certData);
                LogOutput += $"\n[INFO] Migration Certificate saved to: {certPath}\n";
                
                // Open certificate in browser
                Process.Start(new ProcessStartInfo(certPath) { UseShellExecute = true });
                
                CurrentStatusMessage = "Migration Complete!";
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
            App.Current.Dispatcher.Invoke(() =>
            {
                ProgressPercentage = e.Percentage;
                CurrentStatusMessage = e.StatusMessage;
            });
        }

        private void OnLogReceived(object? sender, string log)
        {
            App.Current.Dispatcher.Invoke(() =>
            {
                LogOutput += log + Environment.NewLine;
            });
        }
    }
}
