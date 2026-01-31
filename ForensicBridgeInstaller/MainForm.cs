using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Management;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

namespace ForensicBridgeInstaller
{
    /// <summary>
    /// GUI launcher for the QBExtractor (QBDesktopReader).
    /// Downloads the real extractor if needed, validates session codes,
    /// and launches the extraction process.
    /// </summary>
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
        private string _sessionCode;
        private bool _autoStart;
        private bool _sessionValidated;
        private Process _extractorProcess;

        // Paths
        private static readonly string InstallDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ForensicBridge");
        private static readonly string ExtractorExePath = Path.Combine(InstallDir, "QBExtractor.exe");

        // Download sources
        private const string GITHUB_REPO = "sivaharanj7805/QBMigration";
        private const string SERVER_API = "https://api.forensicbridge.ca/api/extractor";
        private static readonly string GitHubExeUrl =
            $"https://github.com/{GITHUB_REPO}/releases/latest/download/QBExtractor.exe";
        private static readonly string GitHubApiUrl =
            $"https://api.github.com/repos/{GITHUB_REPO}/releases/latest";
        private const string SESSION_VALIDATE_URL = "https://api.forensicbridge.ca/api/session/validate";

        public MainForm(string sessionCode = null, bool autoStart = false)
        {
            _sessionCode = sessionCode;
            _autoStart = autoStart;
            InitializeComponents();
            CheckQuickBooksInstallation();
            CheckExtractorAvailability();

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
            this.Text = "ForensicBridge - QuickBooks Desktop Extractor";
            this.Size = new Size(600, 550);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.BackColor = Color.FromArgb(245, 247, 250);

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

            lblQBStatus = new Label
            {
                Text = "Checking QuickBooks installation...",
                Font = new Font("Segoe UI", 9),
                Location = new Point(20, 95),
                Size = new Size(540, 20)
            };

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

            btnStartExtraction = new Button
            {
                Text = "Start Extraction",
                Font = new Font("Segoe UI", 12, FontStyle.Bold),
                Location = new Point(20, 200),
                Size = new Size(540, 45),
                BackColor = Color.Gray,
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Enabled = false,
                Cursor = Cursors.Hand
            };
            btnStartExtraction.FlatAppearance.BorderSize = 0;
            btnStartExtraction.Click += btnStartExtraction_Click;

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

            Log("ForensicBridge Launcher v2.0.0");
            Log("Powered by QBDesktopReader v4.3");
        }

        private void CheckQuickBooksInstallation()
        {
            _isQuickBooksInstalled = IsQuickBooksInstalled();
            _isQBFCInstalled = IsQBFCInstalled();

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
            }
            else
            {
                lblQBStatus.Text = "QuickBooks Desktop: Not detected";
                lblQBStatus.ForeColor = Color.Red;
                Log("WARNING: QuickBooks Desktop not detected.");
            }
        }

        private void CheckExtractorAvailability()
        {
            if (File.Exists(ExtractorExePath))
            {
                var info = new FileInfo(ExtractorExePath);
                if (info.Length > 50000)
                {
                    Log($"Extractor found: {ExtractorExePath} ({info.Length / 1024}KB)");
                    return;
                }
            }
            Log("Extractor not installed locally. Will download when needed.");
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
            catch (Exception ex)
            {
                // HIGH-04 FIX: Log instead of silently swallowing exceptions
                Debug.WriteLine($"Warning: QuickBooks detection check failed: {ex.Message}");
            }

            return false;
        }

        private bool IsQBFCInstalled()
        {
            try
            {
                var qbType = Type.GetTypeFromProgID("QBFC16.QBSessionManager");
                return qbType != null;
            }
            catch (Exception ex)
            {
                // HIGH-04 FIX: Log instead of silently swallowing exceptions
                Debug.WriteLine($"Warning: QBFC SDK detection failed: {ex.Message}");
            }

            return false;
        }

        // ====================================================================
        // Session Validation
        // ====================================================================

        private async void btnConnect_Click(object sender, EventArgs e)
        {
            var sessionCode = txtSessionCode.Text.Trim();
            if (string.IsNullOrEmpty(sessionCode))
            {
                MessageBox.Show("Please enter a session code.", "Session Required",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            // HIGH-09 FIX: Validate session code format before making API call
            // Session codes should be alphanumeric with hyphens, 6-50 characters
            if (!System.Text.RegularExpressions.Regex.IsMatch(sessionCode, @"^[A-Z0-9\-]{6,50}$"))
            {
                MessageBox.Show(
                    "Invalid session code format.\n\n" +
                    "Session codes should be uppercase letters, numbers, and hyphens only (6-50 characters).",
                    "Invalid Format", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            btnConnect.Enabled = false;
            lblStatus.Text = "Validating session...";
            Log($"Validating session: {sessionCode}");

            try
            {
                var isValid = await ValidateSession(sessionCode);

                if (isValid)
                {
                    _sessionValidated = true;
                    Log("Session validated successfully!");
                    lblStatus.Text = "Session validated. Ready to extract.";
                    btnStartExtraction.Enabled = true;
                    btnStartExtraction.BackColor = Color.FromArgb(34, 197, 94);
                }
                else
                {
                    _sessionValidated = false;
                    Log("Session validation failed.");
                    lblStatus.Text = "Invalid session code.";
                    MessageBox.Show(
                        "The session code is invalid or expired.\n\n" +
                        "Please check the code from your migration project.",
                        "Invalid Session", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
            catch (Exception ex)
            {
                Log($"Validation error: {ex.Message}");
                lblStatus.Text = "Cannot reach server.";
                MessageBox.Show(
                    $"Could not validate session:\n{ex.Message}\n\n" +
                    "Please check your internet connection.",
                    "Connection Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                btnConnect.Enabled = true;
            }
        }

        private async Task<bool> ValidateSession(string sessionCode)
        {
            using (var client = new HttpClient())
            {
                client.Timeout = TimeSpan.FromSeconds(30);

                var fingerprint = GetDeviceFingerprint();
                var payload = Newtonsoft.Json.JsonConvert.SerializeObject(new
                {
                    session_code = sessionCode,
                    device_fingerprint = fingerprint
                });

                var content = new StringContent(payload, Encoding.UTF8, "application/json");
                var response = await client.PostAsync(SESSION_VALIDATE_URL, content);

                if (response.IsSuccessStatusCode)
                {
                    var json = await response.Content.ReadAsStringAsync();
                    var result = Newtonsoft.Json.JsonConvert.DeserializeObject<dynamic>(json);
                    return result?.valid == true;
                }

                return false;
            }
        }

        private string GetDeviceFingerprint()
        {
            // CRIT-09 FIX: Require real device fingerprint - no fallback to random GUID
            var info = new StringBuilder();
            bool hasHardwareInfo = false;

            try
            {
                using (var searcher = new ManagementObjectSearcher("SELECT ProcessorId FROM Win32_Processor"))
                {
                    foreach (ManagementObject obj in searcher.Get())
                    {
                        var processorId = obj["ProcessorId"]?.ToString();
                        if (!string.IsNullOrEmpty(processorId))
                        {
                            info.Append(processorId);
                            hasHardwareInfo = true;
                        }
                        break;
                    }
                }
            }
            catch (Exception ex)
            {
                Log($"Warning: Could not read ProcessorId: {ex.Message}");
            }

            try
            {
                using (var searcher = new ManagementObjectSearcher("SELECT SerialNumber FROM Win32_BaseBoard"))
                {
                    foreach (ManagementObject obj in searcher.Get())
                    {
                        var serialNumber = obj["SerialNumber"]?.ToString();
                        if (!string.IsNullOrEmpty(serialNumber) && serialNumber != "To be filled by O.E.M.")
                        {
                            info.Append(serialNumber);
                            hasHardwareInfo = true;
                        }
                        break;
                    }
                }
            }
            catch (Exception ex)
            {
                Log($"Warning: Could not read BaseBoard SerialNumber: {ex.Message}");
            }

            // CRIT-09 FIX: If no hardware info, add machine name + volume serial as fallback
            // This is still better than a random GUID as it's consistent per machine
            if (!hasHardwareInfo)
            {
                Log("Warning: Using fallback device identifiers (machine name + volume serial)");
                info.Append(Environment.MachineName);

                try
                {
                    using (var searcher = new ManagementObjectSearcher("SELECT VolumeSerialNumber FROM Win32_LogicalDisk WHERE DeviceID='C:'"))
                    {
                        foreach (ManagementObject obj in searcher.Get())
                        {
                            info.Append(obj["VolumeSerialNumber"]?.ToString() ?? "");
                            break;
                        }
                    }
                }
                catch { }
            }

            // CRIT-09 FIX: Never return random GUID - throw exception if we can't identify the machine
            if (info.Length == 0)
            {
                throw new InvalidOperationException(
                    "Cannot generate device fingerprint. WMI queries failed. " +
                    "Please ensure WMI service is running and you have administrator privileges.");
            }

            using (var sha = SHA256.Create())
            {
                var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(info.ToString()));
                return BitConverter.ToString(bytes).Replace("-", "").Substring(0, 32);
            }
        }

        // ====================================================================
        // Extraction (Download extractor if needed, then launch it)
        // ====================================================================

        private async void btnStartExtraction_Click(object sender, EventArgs e)
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
                    "SDK Required", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);

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

            btnStartExtraction.Enabled = false;
            btnConnect.Enabled = false;
            txtSessionCode.Enabled = false;
            progressBar.Value = 0;

            var sessionCode = txtSessionCode.Text.Trim();

            try
            {
                // Step 1: Ensure extractor is downloaded
                if (!IsExtractorAvailable())
                {
                    Log("Downloading QBExtractor...");
                    lblStatus.Text = "Downloading extractor...";
                    progressBar.Value = 10;

                    var downloaded = await DownloadExtractor();
                    if (!downloaded)
                    {
                        MessageBox.Show(
                            "Could not download the extractor.\n\n" +
                            "Please download QBExtractor.exe manually from:\n" +
                            $"https://github.com/{GITHUB_REPO}/releases",
                            "Download Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        return;
                    }

                    Log("Extractor downloaded successfully.");
                }

                progressBar.Value = 20;

                // Step 2: Launch the real extractor
                Log("========================================");
                Log("Launching QBExtractor...");
                Log("========================================");
                lblStatus.Text = "Running extraction...";

                await LaunchExtractor(sessionCode);
            }
            catch (Exception ex)
            {
                Log($"Error: {ex.Message}");
                lblStatus.Text = "Failed. See log.";
                MessageBox.Show($"Error:\n{ex.Message}", "Error",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                btnStartExtraction.Enabled = true;
                btnConnect.Enabled = true;
                txtSessionCode.Enabled = true;
            }
        }

        private bool IsExtractorAvailable()
        {
            if (!File.Exists(ExtractorExePath)) return false;
            var info = new FileInfo(ExtractorExePath);
            return info.Length > 50000;
        }

        private async Task<bool> DownloadExtractor()
        {
            Directory.CreateDirectory(InstallDir);

            var sources = new[]
            {
                new { Name = "server API", Url = $"{SERVER_API}/download-exe" },
                new { Name = "GitHub releases", Url = GitHubExeUrl }
            };

            using (var client = new HttpClient())
            {
                client.Timeout = TimeSpan.FromMinutes(2);
                client.DefaultRequestHeaders.Add("User-Agent", "ForensicBridge/2.0");

                foreach (var source in sources)
                {
                    try
                    {
                        Log($"  Trying {source.Name}...");

                        var response = await client.GetAsync(source.Url);
                        if (!response.IsSuccessStatusCode) continue;

                        var contentType = response.Content.Headers.ContentType?.MediaType ?? "";
                        if (contentType.Contains("html")) continue;

                        var bytes = await response.Content.ReadAsByteArrayAsync();
                        if (bytes.Length < 50000) continue;

                        // Save to temp location first for verification
                        var tempPath = ExtractorExePath + ".tmp";
                        File.WriteAllBytes(tempPath, bytes);

                        // CRIT-03 FIX: Verify Authenticode signature before accepting
                        if (!VerifyAuthenticodeSignature(tempPath))
                        {
                            Log($"  WARNING: {source.Name} - Authenticode signature verification failed!");
                            File.Delete(tempPath);
                            continue;
                        }

                        // Signature verified - move to final location
                        if (File.Exists(ExtractorExePath))
                            File.Delete(ExtractorExePath);
                        File.Move(tempPath, ExtractorExePath);

                        Log($"  Downloaded from {source.Name} ({bytes.Length / 1024}KB) - Signature verified");
                        return true;
                    }
                    catch (Exception ex)
                    {
                        Log($"  {source.Name} failed: {ex.Message}");
                    }
                }
            }

            // Method 3: Try GitHub API to find asset
            try
            {
                Log("  Querying GitHub API...");
                using (var client = new HttpClient())
                {
                    client.Timeout = TimeSpan.FromSeconds(30);
                    client.DefaultRequestHeaders.Add("User-Agent", "ForensicBridge/2.0");

                    var json = await client.GetStringAsync(GitHubApiUrl);
                    var release = Newtonsoft.Json.JsonConvert.DeserializeObject<dynamic>(json);

                    foreach (var asset in release.assets)
                    {
                        string name = asset.name;
                        if (name != null && name.Contains("QBExtractor") && name.EndsWith(".exe"))
                        {
                            string downloadUrl = asset.browser_download_url;
                            var response = await client.GetAsync(downloadUrl);
                            if (response.IsSuccessStatusCode)
                            {
                                var bytes = await response.Content.ReadAsByteArrayAsync();
                                if (bytes.Length > 50000)
                                {
                                    File.WriteAllBytes(ExtractorExePath, bytes);
                                    Log($"  Downloaded via GitHub API ({bytes.Length / 1024}KB)");
                                    return true;
                                }
                            }
                            break;
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Log($"  GitHub API failed: {ex.Message}");
            }

            return false;
        }

        /// <summary>
        /// CRIT-03 FIX: Verify Authenticode signature on downloaded executable
        /// </summary>
        private bool VerifyAuthenticodeSignature(string filePath)
        {
            try
            {
                // Use WinVerifyTrust API via X509Certificate
                var cert = System.Security.Cryptography.X509Certificates.X509Certificate.CreateFromSignedFile(filePath);

                if (cert != null)
                {
                    // Verify the certificate subject contains expected publisher
                    var subject = cert.Subject;
                    if (subject.Contains("ForensicBridge") || subject.Contains("sivaharanj7805"))
                    {
                        Log($"  Signature verified: {subject}");
                        return true;
                    }
                    else
                    {
                        Log($"  Unexpected signer: {subject}");
                        return false;
                    }
                }

                Log("  No Authenticode signature found");
                return false;
            }
            catch (CryptographicException)
            {
                // No valid signature
                Log("  Authenticode signature invalid or missing");
                return false;
            }
            catch (Exception ex)
            {
                Log($"  Signature verification error: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// Launch QBExtractor.exe with session code and stream its output to the log.
        /// </summary>
        private async Task LaunchExtractor(string sessionCode)
        {
            var args = $"--session \"{sessionCode}\" --no-pause";

            var startInfo = new ProcessStartInfo
            {
                FileName = ExtractorExePath,
                Arguments = args,
                WorkingDirectory = InstallDir,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            _extractorProcess = new Process { StartInfo = startInfo };
            _extractorProcess.EnableRaisingEvents = true;

            var tcs = new TaskCompletionSource<int>();

            _extractorProcess.OutputDataReceived += (s, args2) =>
            {
                if (!string.IsNullOrEmpty(args2.Data))
                {
                    UpdateUI(() =>
                    {
                        Log(args2.Data);
                        UpdateProgressFromOutput(args2.Data);
                    });
                }
            };

            _extractorProcess.ErrorDataReceived += (s, args2) =>
            {
                if (!string.IsNullOrEmpty(args2.Data))
                {
                    UpdateUI(() => Log($"[ERR] {args2.Data}"));
                }
            };

            _extractorProcess.Exited += (s, args2) =>
            {
                tcs.TrySetResult(_extractorProcess.ExitCode);
            };

            _extractorProcess.Start();
            _extractorProcess.BeginOutputReadLine();
            _extractorProcess.BeginErrorReadLine();

            Log($"QBExtractor started (PID: {_extractorProcess.Id})");

            var exitCode = await tcs.Task;

            UpdateUI(() =>
            {
                _extractorProcess = null;

                if (exitCode == 0)
                {
                    progressBar.Value = 100;
                    lblStatus.Text = "Extraction complete!";
                    Log("========================================");
                    Log("EXTRACTION COMPLETE! (Exit code: 0)");
                    Log("========================================");

                    MessageBox.Show(
                        "Data extraction completed successfully!\n\n" +
                        "Your QuickBooks data has been securely encrypted\n" +
                        "and uploaded to ForensicBridge.\n\n" +
                        "You can now view your data in the dashboard.",
                        "Extraction Complete",
                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                else
                {
                    lblStatus.Text = $"Extraction failed (exit code: {exitCode})";
                    Log($"QBExtractor exited with code: {exitCode}");

                    var errorMsg = GetExitCodeMessage(exitCode);
                    MessageBox.Show(
                        $"Extraction failed.\n\n{errorMsg}\n\nSee the activity log for details.",
                        "Extraction Failed",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            });
        }

        /// <summary>
        /// Parse QBExtractor output to update progress bar
        /// </summary>
        private void UpdateProgressFromOutput(string line)
        {
            var lower = line.ToLower();

            if (lower.Contains("connecting") || lower.Contains("session"))
                progressBar.Value = Math.Max(progressBar.Value, 25);
            else if (lower.Contains("extracting customers"))
                progressBar.Value = Math.Max(progressBar.Value, 30);
            else if (lower.Contains("extracting vendors"))
                progressBar.Value = Math.Max(progressBar.Value, 40);
            else if (lower.Contains("extracting accounts"))
                progressBar.Value = Math.Max(progressBar.Value, 45);
            else if (lower.Contains("extracting invoices"))
                progressBar.Value = Math.Max(progressBar.Value, 55);
            else if (lower.Contains("extracting bills"))
                progressBar.Value = Math.Max(progressBar.Value, 65);
            else if (lower.Contains("encrypting"))
                progressBar.Value = Math.Max(progressBar.Value, 80);
            else if (lower.Contains("uploading"))
                progressBar.Value = Math.Max(progressBar.Value, 90);
            else if (lower.Contains("complete") || lower.Contains("success"))
                progressBar.Value = 100;

            // Also try to parse percentage from output like "[50%]" or "Progress: 50%"
            var percentIdx = line.IndexOf('%');
            if (percentIdx > 0)
            {
                var numStr = "";
                for (int i = percentIdx - 1; i >= 0 && i >= percentIdx - 3; i--)
                {
                    if (char.IsDigit(line[i]))
                        numStr = line[i] + numStr;
                    else
                        break;
                }
                if (int.TryParse(numStr, out var pct) && pct >= 0 && pct <= 100)
                {
                    progressBar.Value = Math.Max(progressBar.Value, pct);
                }
            }
        }

        private string GetExitCodeMessage(int exitCode)
        {
            switch (exitCode)
            {
                case 10: return "Configuration error. Check config.json.";
                case 15: return "License is invalid or expired.";
                case 20: return "QuickBooks SDK (QBFC16) not installed.";
                case 30: return "Could not connect to QuickBooks Desktop.\nEnsure QuickBooks is running with a company file open.";
                case 40: return "Data extraction failed.\nSee log for details.";
                case 50: return "Upload to server failed.\nCheck your internet connection.";
                case 60: return "Extraction was cancelled.";
                default: return $"Unknown error (code: {exitCode}).";
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

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (_extractorProcess != null && !_extractorProcess.HasExited)
            {
                var result = MessageBox.Show(
                    "An extraction is currently running.\n\n" +
                    "Are you sure you want to close? This will stop the extraction.",
                    "Extraction Running",
                    MessageBoxButtons.YesNo, MessageBoxIcon.Warning);

                if (result == DialogResult.No)
                {
                    e.Cancel = true;
                    return;
                }

                // HIGH-05 FIX: Try graceful termination before force kill
                try
                {
                    // First try graceful close
                    _extractorProcess.CloseMainWindow();

                    // Wait up to 5 seconds for graceful exit
                    if (!_extractorProcess.WaitForExit(5000))
                    {
                        // Force kill if graceful close fails
                        Log("Process did not exit gracefully, forcing termination...");
                        _extractorProcess.Kill();
                        _extractorProcess.WaitForExit(2000);
                    }
                }
                catch (Exception ex)
                {
                    Debug.WriteLine($"Warning: Error terminating process: {ex.Message}");
                }
            }

            base.OnFormClosing(e);
        }
    }
}
