using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
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
    /// Downloads the real extractor zip (exe + DLLs + config) if needed,
    /// validates session codes, and launches the extraction process.
    /// </summary>
    public partial class MainForm : Form
    {
        private TextBox txtSessionCode;
        private TextBox txtLicenseKey;
        private Button btnConnect;
        private Button btnStartExtraction;
        private Label lblStatus;
        private ProgressBar progressBar;
        private RichTextBox txtLog;
        private Label lblQBStatus;
        private Panel panelHeader;
        private Label lblLicenseStatus;

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
        private static readonly string ExtractorZipPath = Path.Combine(InstallDir, "QBExtractor.zip");
        private static readonly string LicenseKeyPath = Path.Combine(InstallDir, "license.key");

        // Download sources — zip file containing exe + DLLs + config
        private const string GITHUB_REPO = "sivaharanj7805/QBMigration";
        private const string SERVER_API = "https://api.forensicbridge.ca/api/extractor";
        private static readonly string GitHubZipUrl =
            $"https://github.com/{GITHUB_REPO}/releases/latest/download/QBExtractor.zip";
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
            CheckLicenseKeyStored();

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
            this.Size = new Size(600, 620);
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

            // License key section
            var lblLicense = new Label
            {
                Text = "License Key:",
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                Location = new Point(20, 125),
                AutoSize = true
            };

            txtLicenseKey = new TextBox
            {
                Font = new Font("Consolas", 11),
                Location = new Point(20, 148),
                Size = new Size(350, 28),
                UseSystemPasswordChar = true
            };

            lblLicenseStatus = new Label
            {
                Text = "",
                Font = new Font("Segoe UI", 8),
                ForeColor = Color.Gray,
                Location = new Point(380, 152),
                Size = new Size(180, 20)
            };

            // Session code section
            var lblSession = new Label
            {
                Text = "Session Code:",
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                Location = new Point(20, 185),
                AutoSize = true
            };

            txtSessionCode = new TextBox
            {
                Font = new Font("Consolas", 12),
                Location = new Point(20, 210),
                Size = new Size(350, 30),
                CharacterCasing = CharacterCasing.Upper
            };

            btnConnect = new Button
            {
                Text = "Validate Session",
                Font = new Font("Segoe UI", 10),
                Location = new Point(380, 208),
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
                Location = new Point(20, 255),
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
                Location = new Point(20, 315),
                Size = new Size(540, 20)
            };

            progressBar = new ProgressBar
            {
                Location = new Point(20, 340),
                Size = new Size(540, 20),
                Style = ProgressBarStyle.Continuous
            };

            var lblLog = new Label
            {
                Text = "Activity Log:",
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                Location = new Point(20, 375),
                AutoSize = true
            };

            txtLog = new RichTextBox
            {
                Location = new Point(20, 398),
                Size = new Size(540, 165),
                ReadOnly = true,
                BackColor = Color.FromArgb(30, 30, 30),
                ForeColor = Color.FromArgb(200, 200, 200),
                Font = new Font("Consolas", 9),
                BorderStyle = BorderStyle.None
            };

            this.Controls.Add(panelHeader);
            this.Controls.Add(lblQBStatus);
            this.Controls.Add(lblLicense);
            this.Controls.Add(txtLicenseKey);
            this.Controls.Add(lblLicenseStatus);
            this.Controls.Add(lblSession);
            this.Controls.Add(txtSessionCode);
            this.Controls.Add(btnConnect);
            this.Controls.Add(btnStartExtraction);
            this.Controls.Add(lblStatus);
            this.Controls.Add(progressBar);
            this.Controls.Add(lblLog);
            this.Controls.Add(txtLog);

            Log("ForensicBridge Launcher v2.1.0");
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

        private void CheckLicenseKeyStored()
        {
            if (File.Exists(LicenseKeyPath))
            {
                lblLicenseStatus.Text = "(stored from previous run)";
                lblLicenseStatus.ForeColor = Color.Green;
                txtLicenseKey.Text = "********";
                txtLicenseKey.Enabled = false;
                Log("License key found (cached from previous activation).");
            }
            else
            {
                lblLicenseStatus.Text = "(required on first run)";
                lblLicenseStatus.ForeColor = Color.Orange;
                Log("No stored license key. Enter your license key above.");
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

        private bool IsQBFCInstalled()
        {
            try
            {
                var qbType = Type.GetTypeFromProgID("QBFC16.QBSessionManager");
                return qbType != null;
            }
            catch { }

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

                // Use session_id to match the extractor's SessionValidator field name
                var payload = Newtonsoft.Json.JsonConvert.SerializeObject(new
                {
                    session_id = sessionCode,
                    device_fingerprint = fingerprint,
                    device_name = Environment.MachineName
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

            // Check license key on first run
            if (!File.Exists(LicenseKeyPath) && txtLicenseKey.Enabled)
            {
                var licenseKey = txtLicenseKey.Text.Trim();
                if (string.IsNullOrEmpty(licenseKey))
                {
                    MessageBox.Show(
                        "A license key is required for first-time use.\n\n" +
                        "Enter your license key in the field above.\n" +
                        "Purchase a license at: https://forensicbridge.ca",
                        "License Required", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
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
            txtLicenseKey.Enabled = false;
            progressBar.Value = 0;

            var sessionCode = txtSessionCode.Text.Trim();

            try
            {
                // Step 1: Ensure extractor is downloaded and extracted
                if (!IsExtractorAvailable())
                {
                    Log("Downloading QBExtractor package...");
                    lblStatus.Text = "Downloading extractor...";
                    progressBar.Value = 5;

                    var downloaded = await DownloadExtractor();
                    if (!downloaded)
                    {
                        MessageBox.Show(
                            "Could not download the extractor.\n\n" +
                            "Please download QBExtractor.zip manually from:\n" +
                            $"https://github.com/{GITHUB_REPO}/releases",
                            "Download Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        return;
                    }

                    Log("Extractor package downloaded and extracted.");
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
                // Re-enable license key only if not stored
                if (!File.Exists(LicenseKeyPath))
                {
                    txtLicenseKey.Enabled = true;
                }
            }
        }

        private bool IsExtractorAvailable()
        {
            if (!File.Exists(ExtractorExePath)) return false;
            var info = new FileInfo(ExtractorExePath);
            return info.Length > 50000;
        }

        /// <summary>
        /// Download QBExtractor.zip (contains exe + DLLs + config) and extract to InstallDir.
        /// net48 cannot produce single-file executables, so the extractor needs
        /// its dependency DLLs and config.json alongside it.
        /// </summary>
        private async Task<bool> DownloadExtractor()
        {
            Directory.CreateDirectory(InstallDir);

            var sources = new[]
            {
                new { Name = "server API", Url = $"{SERVER_API}/download-zip" },
                new { Name = "GitHub releases", Url = GitHubZipUrl }
            };

            using (var client = new HttpClient())
            {
                client.Timeout = TimeSpan.FromMinutes(3);
                client.DefaultRequestHeaders.Add("User-Agent", "ForensicBridge/2.1");

                foreach (var source in sources)
                {
                    try
                    {
                        Log($"  Trying {source.Name}...");

                        var response = await client.GetAsync(source.Url);
                        if (!response.IsSuccessStatusCode) continue;

                        var contentType = response.Content.Headers.ContentType?.MediaType ?? "";
                        // Reject HTML responses (GitHub login pages, etc.)
                        if (contentType.Contains("html")) continue;

                        var bytes = await response.Content.ReadAsByteArrayAsync();
                        // A real zip with exe + DLLs + config should be at least 100KB
                        if (bytes.Length < 100000) continue;

                        File.WriteAllBytes(ExtractorZipPath, bytes);
                        Log($"  Downloaded from {source.Name} ({bytes.Length / 1024}KB)");

                        // Extract zip to install directory
                        return ExtractZipToInstallDir();
                    }
                    catch (Exception ex)
                    {
                        Log($"  {source.Name} failed: {ex.Message}");
                    }
                }
            }

            // Method 3: Try GitHub API to find zip asset
            try
            {
                Log("  Querying GitHub API...");
                using (var client = new HttpClient())
                {
                    client.Timeout = TimeSpan.FromSeconds(30);
                    client.DefaultRequestHeaders.Add("User-Agent", "ForensicBridge/2.1");

                    var json = await client.GetStringAsync(GitHubApiUrl);
                    var release = Newtonsoft.Json.JsonConvert.DeserializeObject<dynamic>(json);

                    foreach (var asset in release.assets)
                    {
                        string name = asset.name;
                        if (name != null && name.Contains("QBExtractor") && name.EndsWith(".zip"))
                        {
                            string downloadUrl = asset.browser_download_url;
                            var response = await client.GetAsync(downloadUrl);
                            if (response.IsSuccessStatusCode)
                            {
                                var bytes = await response.Content.ReadAsByteArrayAsync();
                                if (bytes.Length > 100000)
                                {
                                    File.WriteAllBytes(ExtractorZipPath, bytes);
                                    Log($"  Downloaded via GitHub API ({bytes.Length / 1024}KB)");
                                    return ExtractZipToInstallDir();
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
        /// Extract QBExtractor.zip to InstallDir.
        /// net48 ZipFile.ExtractToDirectory has no overwrite parameter,
        /// so we extract to a temp dir first, then copy files over.
        /// </summary>
        private bool ExtractZipToInstallDir()
        {
            try
            {
                if (!File.Exists(ExtractorZipPath))
                {
                    Log("  ERROR: Zip file not found after download.");
                    return false;
                }

                Log("  Extracting package...");

                // Extract to a temporary directory first (net48 ZipFile has no overwrite option)
                var tempExtractDir = Path.Combine(Path.GetTempPath(),
                    "ForensicBridge_extract_" + Guid.NewGuid().ToString("N").Substring(0, 8));
                if (Directory.Exists(tempExtractDir))
                    Directory.Delete(tempExtractDir, true);

                ZipFile.ExtractToDirectory(ExtractorZipPath, tempExtractDir);

                // Find where QBExtractor.exe landed (could be root or a subdirectory)
                string sourceDir = tempExtractDir;
                if (!File.Exists(Path.Combine(sourceDir, "QBExtractor.exe")))
                {
                    // Check subdirectories (zip may have a root folder)
                    foreach (var subDir in Directory.GetDirectories(tempExtractDir))
                    {
                        if (File.Exists(Path.Combine(subDir, "QBExtractor.exe")))
                        {
                            sourceDir = subDir;
                            break;
                        }
                    }
                }

                if (!File.Exists(Path.Combine(sourceDir, "QBExtractor.exe")))
                {
                    Log("  ERROR: QBExtractor.exe not found in zip contents.");
                    try { Directory.Delete(tempExtractDir, true); } catch { }
                    return false;
                }

                // Copy all files from source to install dir, overwriting existing
                foreach (var file in Directory.GetFiles(sourceDir))
                {
                    var destFile = Path.Combine(InstallDir, Path.GetFileName(file));
                    if (File.Exists(destFile)) File.Delete(destFile);
                    File.Move(file, destFile);
                }

                // Copy subdirectories too (if any runtime folders exist)
                foreach (var dir in Directory.GetDirectories(sourceDir))
                {
                    var destDir = Path.Combine(InstallDir, Path.GetFileName(dir));
                    if (Directory.Exists(destDir)) Directory.Delete(destDir, true);
                    Directory.Move(dir, destDir);
                }

                // Clean up temp directory and zip
                try { Directory.Delete(tempExtractDir, true); } catch { }
                try { File.Delete(ExtractorZipPath); } catch { }

                // Verify
                if (File.Exists(ExtractorExePath))
                {
                    var info = new FileInfo(ExtractorExePath);
                    Log($"  Extracted QBExtractor.exe ({info.Length / 1024}KB)");

                    // Verify config.json was included
                    var configPath = Path.Combine(InstallDir, "config.json");
                    if (File.Exists(configPath))
                    {
                        Log("  config.json: present");
                    }
                    else
                    {
                        Log("  WARNING: config.json not found in package.");
                    }

                    return true;
                }

                Log("  ERROR: QBExtractor.exe not found after extraction.");
                return false;
            }
            catch (Exception ex)
            {
                Log($"  Extraction failed: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// Launch QBExtractor.exe with session code and license key, stream its output to the log.
        /// </summary>
        private async Task LaunchExtractor(string sessionCode)
        {
            // Build command line arguments
            var argsBuilder = new StringBuilder();
            argsBuilder.Append($"--session \"{sessionCode}\" --no-pause");

            // Pass license key if the user entered one (first run)
            if (txtLicenseKey.Enabled && !string.IsNullOrEmpty(txtLicenseKey.Text.Trim())
                && txtLicenseKey.Text.Trim() != "********")
            {
                argsBuilder.Append($" --license \"{txtLicenseKey.Text.Trim()}\"");
            }

            var args = argsBuilder.ToString();

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

                    // After successful extraction, license key is now cached by the extractor
                    CheckLicenseKeyStored();

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

            if (lower.Contains("validating license") || lower.Contains("validating session"))
                progressBar.Value = Math.Max(progressBar.Value, 22);
            else if (lower.Contains("session validated") || lower.Contains("license validated"))
                progressBar.Value = Math.Max(progressBar.Value, 25);
            else if (lower.Contains("connecting") || lower.Contains("connected to quickbooks"))
                progressBar.Value = Math.Max(progressBar.Value, 28);
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
            else if (lower.Contains("extraction complete"))
                progressBar.Value = Math.Max(progressBar.Value, 75);
            else if (lower.Contains("encrypting") || lower.Contains("streaming upload"))
                progressBar.Value = Math.Max(progressBar.Value, 80);
            else if (lower.Contains("uploading") || lower.Contains("pipeline"))
                progressBar.Value = Math.Max(progressBar.Value, 90);
            else if (lower.Contains("success") && lower.Contains("all data"))
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
                case 10: return "Configuration error. The config.json may be missing or invalid.";
                case 15: return "License key is missing, invalid, or expired.\nEnter a valid license key and try again.";
                case 20: return "QuickBooks SDK (QBFC16) not installed.\nDownload from: https://developer.intuit.com/app/developer/qbdesktop/docs/get-started";
                case 30: return "Could not connect to QuickBooks Desktop.\nEnsure QuickBooks is running with a company file open.";
                case 40: return "Data extraction failed.\nSee log for details.";
                case 50: return "Upload to server failed.\nCheck your internet connection.";
                case 60: return "Extraction was cancelled.";
                case 99: return "An unexpected error occurred. See log for details.";
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

                try { _extractorProcess.Kill(); } catch { }
            }

            base.OnFormClosing(e);
        }
    }
}
