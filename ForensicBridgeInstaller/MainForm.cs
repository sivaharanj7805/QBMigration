using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Management;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

namespace ForensicBridgeInstaller
{
    public partial class MainForm : Form
    {
        private TextBox txtSessionCode;
        private Button btnConnect;
        private Button btnStartExtraction;
        private Label lblStatus;
        private ProgressBar progressBar;
        private RichTextBox txtLog;
        private Label lblQBStatus;
        private Panel panelHeader;

        private bool _isQuickBooksInstalled;
        private bool _isQBFCInstalled;
        private string? _sessionCode;
        private bool _autoStart;
        private bool _sessionValidated;
        private string? _deviceFingerprint;
        private readonly DataUploader _uploader;

        public MainForm(string? sessionCode = null, bool autoStart = false)
        {
            _sessionCode = sessionCode;
            _autoStart = autoStart;
            _uploader = new DataUploader(logCallback: msg => Log(msg));

            InitializeComponents();
            CheckQuickBooksInstallation();
            _deviceFingerprint = GetDeviceFingerprint();

            if (!string.IsNullOrEmpty(_sessionCode))
            {
                txtSessionCode.Text = _sessionCode;
            }

            if (_autoStart && !string.IsNullOrEmpty(_sessionCode))
            {
                this.Load += (s, e) => btnConnect_Click(null, null);
            }
        }

        private void InitializeComponents()
        {
            // Form settings
            this.Text = "ForensicBridge - QuickBooks Desktop Extractor";
            this.Size = new Size(600, 550);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.BackColor = Color.FromArgb(245, 247, 250);

            // Header Panel
            panelHeader = new Panel
            {
                Dock = DockStyle.Top,
                Height = 80,
                BackColor = Color.FromArgb(37, 99, 235)
            };

            var lblTitle = new Label
            {
                Text = "ForensicBridge",
                Font = new Font("Segoe UI", 24, FontStyle.Bold),
                ForeColor = Color.White,
                AutoSize = true,
                Location = new Point(20, 12)
            };

            var lblSubtitle = new Label
            {
                Text = "QuickBooks Desktop Data Migration Tool",
                Font = new Font("Segoe UI", 10),
                ForeColor = Color.FromArgb(200, 220, 255),
                AutoSize = true,
                Location = new Point(22, 50)
            };

            panelHeader.Controls.Add(lblTitle);
            panelHeader.Controls.Add(lblSubtitle);

            // QuickBooks Status
            lblQBStatus = new Label
            {
                Text = "Checking QuickBooks installation...",
                Font = new Font("Segoe UI", 9),
                Location = new Point(20, 95),
                Size = new Size(540, 20)
            };

            // Session Code Section
            var lblSession = new Label
            {
                Text = "Session Code:",
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                Location = new Point(20, 130),
                AutoSize = true
            };

            txtSessionCode = new TextBox
            {
                Font = new Font("Consolas", 12),
                Location = new Point(20, 155),
                Size = new Size(350, 30),
                CharacterCasing = CharacterCasing.Upper
            };

            btnConnect = new Button
            {
                Text = "Validate Session",
                Font = new Font("Segoe UI", 10),
                Location = new Point(380, 153),
                Size = new Size(180, 32),
                BackColor = Color.FromArgb(37, 99, 235),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            btnConnect.FlatAppearance.BorderSize = 0;
            btnConnect.Click += btnConnect_Click;

            // Start Extraction Button
            btnStartExtraction = new Button
            {
                Text = "Start Extraction",
                Font = new Font("Segoe UI", 12, FontStyle.Bold),
                Location = new Point(20, 200),
                Size = new Size(540, 45),
                BackColor = Color.FromArgb(34, 197, 94),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Enabled = false,
                Cursor = Cursors.Hand
            };
            btnStartExtraction.FlatAppearance.BorderSize = 0;
            btnStartExtraction.Click += btnStartExtraction_Click;

            // Progress
            lblStatus = new Label
            {
                Text = "Ready",
                Font = new Font("Segoe UI", 9),
                Location = new Point(20, 260),
                Size = new Size(540, 20)
            };

            progressBar = new ProgressBar
            {
                Location = new Point(20, 285),
                Size = new Size(540, 20),
                Style = ProgressBarStyle.Continuous
            };

            // Log
            var lblLog = new Label
            {
                Text = "Activity Log:",
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                Location = new Point(20, 320),
                AutoSize = true
            };

            txtLog = new RichTextBox
            {
                Location = new Point(20, 345),
                Size = new Size(540, 150),
                ReadOnly = true,
                BackColor = Color.FromArgb(30, 30, 30),
                ForeColor = Color.FromArgb(200, 200, 200),
                Font = new Font("Consolas", 9),
                BorderStyle = BorderStyle.None
            };

            // Add controls
            this.Controls.Add(panelHeader);
            this.Controls.Add(lblQBStatus);
            this.Controls.Add(lblSession);
            this.Controls.Add(txtSessionCode);
            this.Controls.Add(btnConnect);
            this.Controls.Add(btnStartExtraction);
            this.Controls.Add(lblStatus);
            this.Controls.Add(progressBar);
            this.Controls.Add(lblLog);
            this.Controls.Add(txtLog);

            // Initial log message
            Log("ForensicBridge Extractor v2.0.0");
            Log("Ready to migrate QuickBooks Desktop data.");
        }

        private void CheckQuickBooksInstallation()
        {
            _isQuickBooksInstalled = IsQuickBooksInstalled();
            _isQBFCInstalled = QBExtractor.IsQBFCInstalled();

            if (_isQuickBooksInstalled && _isQBFCInstalled)
            {
                lblQBStatus.Text = "QuickBooks Desktop: Installed | SDK: Ready";
                lblQBStatus.ForeColor = Color.Green;
                Log("QuickBooks Desktop and SDK (QBFC16) detected.");
            }
            else if (_isQuickBooksInstalled && !_isQBFCInstalled)
            {
                lblQBStatus.Text = "QuickBooks SDK (QBFC16) not found. Required for extraction.";
                lblQBStatus.ForeColor = Color.Orange;
                Log("WARNING: QuickBooks found but SDK (QBFC16) is missing.");
                Log("The extraction requires the QuickBooks SDK.");
            }
            else
            {
                lblQBStatus.Text = "QuickBooks Desktop: Not detected";
                lblQBStatus.ForeColor = Color.Red;
                Log("WARNING: QuickBooks Desktop not detected.");
                Log("Please ensure QuickBooks Desktop is installed and running.");
            }
        }

        private bool IsQuickBooksInstalled()
        {
            try
            {
                using (var key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Intuit\QuickBooks"))
                {
                    if (key != null) return true;
                }
                using (var key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\WOW6432Node\Intuit\QuickBooks"))
                {
                    if (key != null) return true;
                }

                var processes = Process.GetProcessesByName("QBW32");
                if (processes.Length > 0) return true;

                var paths = new[]
                {
                    @"C:\Program Files (x86)\Intuit\QuickBooks",
                    @"C:\Program Files\Intuit\QuickBooks"
                };

                foreach (var path in paths)
                {
                    if (Directory.Exists(path)) return true;
                }
            }
            catch { }

            return false;
        }

        private async void btnConnect_Click(object? sender, EventArgs? e)
        {
            var sessionCode = txtSessionCode.Text.Trim();
            if (string.IsNullOrEmpty(sessionCode))
            {
                MessageBox.Show("Please enter a session code.", "Session Required",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            btnConnect.Enabled = false;
            lblStatus.Text = "Validating session...";
            Log($"Validating session: {sessionCode}");

            try
            {
                var result = await _uploader.ValidateSessionAsync(
                    sessionCode, _deviceFingerprint ?? "");

                if (result.Valid)
                {
                    _sessionValidated = true;
                    Log("Session validated successfully!");
                    lblStatus.Text = "Session validated. Ready to extract.";
                    btnStartExtraction.Enabled = true;
                    btnStartExtraction.BackColor = Color.FromArgb(34, 197, 94);
                }
                else if (result.ServerUnreachable)
                {
                    _sessionValidated = false;
                    Log($"Server unreachable: {result.Error}");
                    lblStatus.Text = "Cannot reach server. Please check your internet connection.";
                    MessageBox.Show(
                        "Cannot connect to the ForensicBridge server.\n\n" +
                        "Please check your internet connection and try again.\n\n" +
                        $"Details: {result.Error}",
                        "Connection Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                else
                {
                    _sessionValidated = false;
                    Log($"Session validation failed: {result.Error}");
                    lblStatus.Text = "Invalid session code.";
                    MessageBox.Show(
                        "The session code is invalid or expired.\n\n" +
                        "Please check the code from your migration project.",
                        "Invalid Session", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
            catch (Exception ex)
            {
                Log($"Error: {ex.Message}");
                lblStatus.Text = "Validation failed.";
                MessageBox.Show($"Could not validate session:\n{ex.Message}",
                    "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                btnConnect.Enabled = true;
            }
        }

        private string GetDeviceFingerprint()
        {
            try
            {
                var info = new StringBuilder();

                using (var searcher = new ManagementObjectSearcher("SELECT ProcessorId FROM Win32_Processor"))
                {
                    foreach (ManagementObject obj in searcher.Get())
                    {
                        info.Append(obj["ProcessorId"]?.ToString() ?? "");
                        break;
                    }
                }

                using (var searcher = new ManagementObjectSearcher("SELECT SerialNumber FROM Win32_BaseBoard"))
                {
                    foreach (ManagementObject obj in searcher.Get())
                    {
                        info.Append(obj["SerialNumber"]?.ToString() ?? "");
                        break;
                    }
                }

                using (var sha = SHA256.Create())
                {
                    var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(info.ToString()));
                    return BitConverter.ToString(bytes).Replace("-", "").Substring(0, 32);
                }
            }
            catch
            {
                return Guid.NewGuid().ToString("N");
            }
        }

        private async void btnStartExtraction_Click(object? sender, EventArgs? e)
        {
            if (!_sessionValidated)
            {
                MessageBox.Show("Please validate your session code first.",
                    "Session Required", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            if (!_isQBFCInstalled)
            {
                var result = MessageBox.Show(
                    "The QuickBooks SDK (QBFC16) is required for extraction but was not detected.\n\n" +
                    "Would you like to open the QuickBooks SDK download page?",
                    "SDK Required",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Warning);

                if (result == DialogResult.Yes)
                {
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = "https://developer.intuit.com/app/developer/qbdesktop/docs/get-started",
                        UseShellExecute = true
                    });
                }
                return;
            }

            if (!QBExtractor.IsQuickBooksRunning())
            {
                var result = MessageBox.Show(
                    "QuickBooks Desktop does not appear to be running.\n\n" +
                    "Please open QuickBooks Desktop and your company file before extraction.\n\n" +
                    "Continue anyway?",
                    "QuickBooks Not Running",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Warning);

                if (result == DialogResult.No) return;
            }

            btnStartExtraction.Enabled = false;
            btnConnect.Enabled = false;
            txtSessionCode.Enabled = false;
            progressBar.Value = 0;

            var sessionCode = txtSessionCode.Text.Trim();

            Log("========================================");
            Log("Starting QuickBooks data extraction...");
            Log("========================================");
            lblStatus.Text = "Connecting to QuickBooks...";

            try
            {
                await Task.Run(async () => await RunRealExtraction(sessionCode));
            }
            catch (Exception ex)
            {
                Log($"EXTRACTION FAILED: {ex.Message}");
                lblStatus.Text = "Extraction failed. See log for details.";
                MessageBox.Show(
                    $"Extraction failed:\n{ex.Message}\n\n" +
                    "Please ensure QuickBooks is running and try again.",
                    "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                btnStartExtraction.Enabled = true;
                btnConnect.Enabled = true;
                txtSessionCode.Enabled = true;
            }
        }

        /// <summary>
        /// Real extraction: connect to QB, extract data, encrypt, upload
        /// </summary>
        private async Task RunRealExtraction(string sessionCode)
        {
            using (var extractor = new QBExtractor(
                logCallback: msg => Log(msg),
                progressCallback: pct => UpdateUI(() => progressBar.Value = Math.Min(pct, 100))))
            {
                // Step 1: Initialize QBFC
                UpdateUI(() =>
                {
                    progressBar.Value = 5;
                    lblStatus.Text = "Initializing QuickBooks connection...";
                });

                if (!extractor.Initialize())
                {
                    throw new Exception(
                        "Could not initialize QuickBooks SDK (QBFC16). " +
                        "Please ensure the QuickBooks SDK is properly installed.");
                }

                // Step 2: Open session
                UpdateUI(() =>
                {
                    progressBar.Value = 10;
                    lblStatus.Text = "Connecting to QuickBooks Desktop...";
                });

                Log("Please authorize ForensicBridge in QuickBooks if prompted.");
                Log("Click 'Yes, Always Allow' when the QuickBooks dialog appears.");

                if (!extractor.OpenSession())
                {
                    throw new Exception(
                        "Could not connect to QuickBooks. Please ensure:\n" +
                        "1. QuickBooks Desktop is running\n" +
                        "2. A company file is open\n" +
                        "3. You authorized ForensicBridge when prompted");
                }

                UpdateUI(() => lblStatus.Text = $"Connected to: {extractor.CompanyName}");

                // Step 3: Extract data
                UpdateUI(() =>
                {
                    lblStatus.Text = "Extracting data from QuickBooks...";
                });

                var extractionResult = extractor.ExtractAll();

                if (!extractionResult.Success)
                {
                    throw new Exception(
                        $"Data extraction failed: {extractionResult.Error}");
                }

                Log($"Extracted {extractionResult.TotalRecords} total records");
                foreach (var kvp in extractionResult.EntityCounts)
                {
                    Log($"  {kvp.Key}: {kvp.Value}");
                }

                // Step 4: Encrypt data
                UpdateUI(() =>
                {
                    progressBar.Value = 85;
                    lblStatus.Text = "Encrypting data with AES-256-GCM...";
                });

                Log("Encrypting extracted data...");
                var encryptionResult = DataEncryptor.Encrypt(extractionResult.JsonData);
                var originalSizeKB = encryptionResult.OriginalSizeBytes / 1024.0;
                var encryptedSizeKB = encryptionResult.EncryptedSizeBytes / 1024.0;
                Log($"Encryption complete: {originalSizeKB:F1} KB -> {encryptedSizeKB:F1} KB");

                // Step 5: Upload to server
                UpdateUI(() =>
                {
                    progressBar.Value = 90;
                    lblStatus.Text = "Uploading encrypted data to server...";
                });

                Log("Uploading to ForensicBridge server...");
                var uploadResult = await _uploader.UploadAsync(
                    sessionCode,
                    extractionResult,
                    encryptionResult,
                    _deviceFingerprint ?? "");

                if (!uploadResult.Success)
                {
                    throw new Exception($"Upload failed: {uploadResult.Error}");
                }

                // Step 6: Success!
                UpdateUI(() =>
                {
                    progressBar.Value = 100;
                    lblStatus.Text = "Extraction and upload complete!";
                });

                Log("========================================");
                Log("EXTRACTION COMPLETE!");
                Log($"Company: {extractionResult.CompanyName}");
                Log($"Records extracted: {extractionResult.TotalRecords}");
                Log($"Migration ID: {uploadResult.MigrationId ?? "N/A"}");
                Log("Your data has been securely encrypted and uploaded.");
                Log("You can now view your data in the ForensicBridge dashboard.");
                Log("========================================");

                UpdateUI(() =>
                {
                    MessageBox.Show(
                        $"Data extraction completed successfully!\n\n" +
                        $"Company: {extractionResult.CompanyName}\n" +
                        $"Records: {extractionResult.TotalRecords}\n\n" +
                        "Your QuickBooks data has been securely encrypted\n" +
                        "and uploaded to ForensicBridge.\n\n" +
                        "You can now view your data in the dashboard.",
                        "Extraction Complete",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information);
                });
            }
        }

        private void UpdateUI(Action action)
        {
            if (this.InvokeRequired)
            {
                this.Invoke(action);
            }
            else
            {
                action();
            }
        }

        private void Log(string message)
        {
            var timestamp = DateTime.Now.ToString("HH:mm:ss");
            var logMessage = $"[{timestamp}] {message}\n";

            if (txtLog.InvokeRequired)
            {
                txtLog.Invoke(new Action(() =>
                {
                    txtLog.AppendText(logMessage);
                    txtLog.ScrollToCaret();
                }));
            }
            else
            {
                txtLog.AppendText(logMessage);
                txtLog.ScrollToCaret();
            }
        }
    }
}
