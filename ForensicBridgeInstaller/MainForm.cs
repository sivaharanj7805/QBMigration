using System;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Management;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

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
        private TextBox txtLog;
        private Label lblQBStatus;
        private Panel panelHeader;

        private readonly bool _isQuickBooksInstalled;
        private readonly bool _isQBFCInstalled;
        private readonly string _sessionCode; // Made readonly - never reassigned
        private readonly bool _autoStart;
        private bool _sessionValidated;
        private Process _extractorProcess;
        private readonly object _processLock = new object(); // Lock for process access
        private readonly AppConfig _config;

        // Fonts - stored for proper disposal
        private Font _fontTitle;
        private Font _fontSubtitle;
        private Font _fontNormal;
        private Font _fontBold;
        private Font _fontMonospace;
        private Font _fontButton;
        private Font _fontButtonLarge;

        // Static HttpClient for reuse - prevents socket exhaustion
        private static readonly HttpClient SharedHttpClient;

        // Cached compiled regex for performance
        private static readonly Regex SessionCodeRegex = new Regex(
            @"^[A-Za-z0-9_\-]{6,50}$",
            RegexOptions.Compiled,
            TimeSpan.FromSeconds(1));
        private static readonly Regex SanitizeRegex = new Regex(
            @"[^A-Za-z0-9_\-]",
            RegexOptions.Compiled,
            TimeSpan.FromSeconds(1));

        // Progress milestones - static to avoid allocation on every call
        private static readonly (string[] keywords, int progress)[] ProgressMilestones = new[]
        {
            (new[] { "connecting", "session", "authenticat" }, 25),
            (new[] { "customer", "client" }, 30),
            (new[] { "vendor", "supplier" }, 40),
            (new[] { "account", "chart" }, 45),
            (new[] { "invoice", "receivable" }, 55),
            (new[] { "bill", "payable" }, 65),
            (new[] { "transaction", "journal" }, 70),
            (new[] { "encrypt" }, 80),
            (new[] { "upload", "transfer" }, 90),
            (new[] { "complete", "success", "finish" }, 100)
        };

        // Maximum log size in characters to prevent memory issues
        private const int MaxLogSize = 100000;

        // Paths
        private static readonly string InstallDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ForensicBridge");
        private static readonly string ExtractorExePath = Path.Combine(InstallDir, "QBExtractor.exe");

        // Download sources
        private const string GITHUB_REPO = "sivaharanj7805/QBMigration";
        private static readonly string GitHubExeUrl =
            $"https://github.com/{GITHUB_REPO}/releases/latest/download/QBExtractor.exe";
        private static readonly string GitHubApiUrl =
            $"https://api.github.com/repos/{GITHUB_REPO}/releases/latest";

        // Static constructor to initialize HttpClient once
        static MainForm()
        {
            var handler = new HttpClientHandler
            {
                AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate
            };
            SharedHttpClient = new HttpClient(handler)
            {
                Timeout = TimeSpan.FromMinutes(5)
            };
            // Only add if not already present
            if (!SharedHttpClient.DefaultRequestHeaders.Contains("User-Agent"))
            {
                SharedHttpClient.DefaultRequestHeaders.Add("User-Agent", "ForensicBridge/2.0");
            }
        }

        public MainForm(string sessionCode = null, bool autoStart = false)
        {
            _sessionCode = sessionCode;
            _autoStart = autoStart;

            // Load configuration first
            _config = LoadConfiguration();

            // Initialize fonts (for proper disposal)
            InitializeFonts();

            InitializeComponents();

            // Set these in constructor so they can be readonly
            _isQuickBooksInstalled = IsQuickBooksInstalled();
            _isQBFCInstalled = IsQBFCInstalled();

            UpdateQuickBooksStatus();
            CheckExtractorAvailability();

            if (!string.IsNullOrEmpty(_sessionCode))
            {
                txtSessionCode.Text = _sessionCode;
            }

            if (_autoStart && !string.IsNullOrEmpty(_sessionCode))
            {
                this.Load += (s, e) => btnConnect_Click(this, EventArgs.Empty);
            }
        }

        /// <summary>
        /// Initialize fonts once for reuse and proper disposal
        /// </summary>
        private void InitializeFonts()
        {
            _fontTitle = new Font("Segoe UI", 24, FontStyle.Bold);
            _fontSubtitle = new Font("Segoe UI", 10);
            _fontNormal = new Font("Segoe UI", 9);
            _fontBold = new Font("Segoe UI", 10, FontStyle.Bold);
            _fontMonospace = new Font("Consolas", 9);
            _fontButton = new Font("Segoe UI", 10);
            _fontButtonLarge = new Font("Segoe UI", 12, FontStyle.Bold);
        }

        /// <summary>
        /// Load configuration from config.json
        /// </summary>
        private AppConfig LoadConfiguration()
        {
            var config = new AppConfig();
            try
            {
                var configPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "config.json");
                if (File.Exists(configPath))
                {
                    var json = File.ReadAllText(configPath);
                    var parsed = JObject.Parse(json);

                    config.ServerUrl = parsed["serverUrl"]?.ToString() ?? config.ServerUrl;
                    config.Version = parsed["version"]?.ToString() ?? config.Version;
                    config.ApplicationName = parsed["applicationName"]?.ToString() ?? config.ApplicationName;
                    config.SupportEmail = parsed["supportEmail"]?.ToString() ?? config.SupportEmail;
                    config.DocumentationUrl = parsed["documentationUrl"]?.ToString() ?? config.DocumentationUrl;
                }
            }
            catch (Exception ex)
            {
                // Log but don't fail - use defaults
                // Note: Can't use Log() here as txtLog isn't created yet
                Debug.WriteLine($"Warning: Could not load config.json: {ex.Message}");
            }
            return config;
        }

        private void InitializeComponents()
        {
            // Enable DPI awareness
            this.AutoScaleMode = AutoScaleMode.Dpi;
            this.AutoScaleDimensions = new SizeF(96F, 96F);

            this.Text = $"{_config.ApplicationName} - QuickBooks Desktop Extractor";
            this.Size = new Size(650, 600);
            this.MinimumSize = new Size(500, 450);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.Sizable;
            this.MaximizeBox = true;
            this.BackColor = SystemColors.Control;

            // Use TableLayoutPanel for proper resizing behavior
            var mainLayout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 9,
                Padding = new Padding(0)
            };
            mainLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            mainLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 80F));  // Header
            mainLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 30F));  // QB Status
            mainLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 25F));  // Session label
            mainLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 40F));  // Session input row
            mainLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 55F));  // Start button
            mainLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 25F));  // Status
            mainLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 30F));  // Progress
            mainLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 25F));  // Log label
            mainLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));  // Log (fills remaining)

            panelHeader = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.FromArgb(37, 99, 235)
            };

            var lblTitle = new Label
            {
                Text = _config.ApplicationName,
                Font = _fontTitle,
                ForeColor = Color.White,
                AutoSize = true,
                Location = new Point(20, 12)
            };

            var lblSubtitle = new Label
            {
                Text = "QuickBooks Desktop Data Migration Tool",
                Font = _fontSubtitle,
                ForeColor = Color.FromArgb(200, 220, 255),
                AutoSize = true,
                Location = new Point(22, 50)
            };

            panelHeader.Controls.Add(lblTitle);
            panelHeader.Controls.Add(lblSubtitle);

            lblQBStatus = new Label
            {
                Text = "Checking QuickBooks installation...",
                Font = _fontNormal,
                Dock = DockStyle.Fill,
                Padding = new Padding(20, 5, 20, 0)
            };

            var lblSession = new Label
            {
                Text = "Session Code:",
                Font = _fontBold,
                Dock = DockStyle.Fill,
                Padding = new Padding(20, 5, 20, 0)
            };

            // Session input panel for proper layout
            var sessionPanel = new Panel { Dock = DockStyle.Fill };

            txtSessionCode = new TextBox
            {
                Font = new Font("Consolas", 11),
                Location = new Point(20, 2),
                Size = new Size(350, 26),
                CharacterCasing = CharacterCasing.Upper,
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
            };

            btnConnect = new Button
            {
                Text = "Validate Session",
                Font = _fontButton,
                Location = new Point(380, 0),
                Size = new Size(180, 32),
                BackColor = Color.FromArgb(37, 99, 235),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand,
                Anchor = AnchorStyles.Top | AnchorStyles.Right
            };
            btnConnect.FlatAppearance.BorderSize = 0;
            btnConnect.Click += btnConnect_Click;

            sessionPanel.Controls.Add(txtSessionCode);
            sessionPanel.Controls.Add(btnConnect);

            btnStartExtraction = new Button
            {
                Text = "Start Extraction",
                Font = _fontButtonLarge,
                Dock = DockStyle.Fill,
                Margin = new Padding(20, 5, 20, 5),
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
                Font = _fontNormal,
                Dock = DockStyle.Fill,
                Padding = new Padding(20, 5, 20, 0)
            };

            progressBar = new ProgressBar
            {
                Dock = DockStyle.Fill,
                Margin = new Padding(20, 5, 20, 5),
                Style = ProgressBarStyle.Continuous
            };

            var lblLog = new Label
            {
                Text = "Activity Log:",
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                Dock = DockStyle.Fill,
                Padding = new Padding(20, 5, 20, 0)
            };

            txtLog = new TextBox
            {
                Dock = DockStyle.Fill,
                Margin = new Padding(20, 0, 20, 10),
                ReadOnly = true,
                Multiline = true,
                ScrollBars = ScrollBars.Vertical,
                BackColor = SystemColors.Window,
                ForeColor = SystemColors.WindowText,
                Font = _fontMonospace,
                BorderStyle = BorderStyle.FixedSingle
            };

            mainLayout.Controls.Add(panelHeader, 0, 0);
            mainLayout.Controls.Add(lblQBStatus, 0, 1);
            mainLayout.Controls.Add(lblSession, 0, 2);
            mainLayout.Controls.Add(sessionPanel, 0, 3);
            mainLayout.Controls.Add(btnStartExtraction, 0, 4);
            mainLayout.Controls.Add(lblStatus, 0, 5);
            mainLayout.Controls.Add(progressBar, 0, 6);
            mainLayout.Controls.Add(lblLog, 0, 7);
            mainLayout.Controls.Add(txtLog, 0, 8);

            this.Controls.Add(mainLayout);

            Log($"{_config.ApplicationName} Launcher v{_config.Version}");
            Log("Powered by QBDesktopReader v4.3");
        }

        private void UpdateQuickBooksStatus()
        {
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

                // Properly dispose Process array
                Process[] processes = null;
                try
                {
                    processes = Process.GetProcessesByName("QBW32");
                    if (processes.Length > 0) return true;
                }
                finally
                {
                    if (processes != null)
                    {
                        foreach (var p in processes)
                        {
                            p.Dispose();
                        }
                    }
                }

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
                Log($"Warning: QuickBooks detection check failed: {ex.Message}");
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
                Log($"Warning: QBFC SDK detection failed: {ex.Message}");
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

            // Use cached compiled regex for validation
            if (!SessionCodeRegex.IsMatch(sessionCode))
            {
                MessageBox.Show(
                    "Invalid session code format.\n\n" +
                    "Session codes should be letters, numbers, hyphens, and underscores only (6-50 characters).",
                    "Invalid Format", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            btnConnect.Enabled = false;
            lblStatus.Text = "Validating session...";
            // Don't log full session code for security
            var maskedCode = sessionCode.Length > 4
                ? sessionCode.Substring(0, 4) + new string('*', sessionCode.Length - 4)
                : new string('*', sessionCode.Length);
            Log($"Validating session: {maskedCode}");

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
                    $"Please check your internet connection.\n\nSupport: {_config.SupportEmail}",
                    "Connection Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                btnConnect.Enabled = true;
            }
        }

        private async Task<bool> ValidateSession(string sessionCode)
        {
            var fingerprint = GetDeviceFingerprint();
            var payload = JsonConvert.SerializeObject(new
            {
                session_code = sessionCode,
                device_fingerprint = fingerprint
            });

            var sessionValidateUrl = $"{_config.ServerUrl}/api/session/validate";

            // Properly dispose StringContent
            using (var content = new StringContent(payload, Encoding.UTF8, "application/json"))
            using (var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30)))
            {
                var response = await SharedHttpClient.PostAsync(sessionValidateUrl, content, cts.Token);

                if (response.IsSuccessStatusCode)
                {
                    var json = await response.Content.ReadAsStringAsync();
                    try
                    {
                        var result = JObject.Parse(json);
                        return result["valid"]?.Value<bool>() == true;
                    }
                    catch (JsonException)
                    {
                        Log("Warning: Invalid JSON response from server");
                        return false;
                    }
                }

                return false;
            }
        }

        private string GetDeviceFingerprint()
        {
            var info = new StringBuilder();
            bool hasHardwareInfo = false;

            try
            {
                using (var searcher = new ManagementObjectSearcher("SELECT ProcessorId FROM Win32_Processor"))
                using (var collection = searcher.Get())
                {
                    foreach (ManagementObject obj in collection)
                    {
                        using (obj) // Properly dispose ManagementObject
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
            }
            catch (Exception ex)
            {
                Log($"Warning: Could not read ProcessorId: {ex.Message}");
            }

            try
            {
                using (var searcher = new ManagementObjectSearcher("SELECT SerialNumber FROM Win32_BaseBoard"))
                using (var collection = searcher.Get())
                {
                    foreach (ManagementObject obj in collection)
                    {
                        using (obj)
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
            }
            catch (Exception ex)
            {
                Log($"Warning: Could not read BaseBoard SerialNumber: {ex.Message}");
            }

            // Fallback device identifiers
            if (!hasHardwareInfo)
            {
                Log("Warning: Using fallback device identifiers (machine name + volume serial)");
                info.Append(Environment.MachineName);

                try
                {
                    using (var searcher = new ManagementObjectSearcher("SELECT VolumeSerialNumber FROM Win32_LogicalDisk WHERE DeviceID='C:'"))
                    using (var collection = searcher.Get())
                    {
                        foreach (ManagementObject obj in collection)
                        {
                            using (obj)
                            {
                                info.Append(obj["VolumeSerialNumber"]?.ToString() ?? "");
                                break;
                            }
                        }
                    }
                }
                catch (Exception ex)
                {
                    Log($"Warning: Could not read VolumeSerialNumber: {ex.Message}");
                }
            }

            // Throw if we can't identify the machine
            if (info.Length == 0)
            {
                throw new InvalidOperationException(
                    "Cannot generate device fingerprint. WMI queries failed. " +
                    "Please ensure WMI service is running and you have administrator privileges.");
            }

            using (var sha = SHA256.Create())
            {
                var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(info.ToString()));
                return BitConverter.ToString(bytes).Replace("-", "");
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
                    try
                    {
                        Process.Start(new ProcessStartInfo
                        {
                            FileName = _config.DocumentationUrl ?? "https://developer.intuit.com/app/developer/qbdesktop/docs/get-started",
                            UseShellExecute = true
                        });
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show(
                            $"Could not open browser. Please visit:\n{_config.DocumentationUrl}\n\nError: {ex.Message}",
                            "Browser Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    }
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
            if (info.Length < 50000) return false;

            try
            {
                // Basic PE header check with specific exception handling
                using (var fs = new FileStream(ExtractorExePath, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    var buffer = new byte[2];
                    if (fs.Read(buffer, 0, 2) == 2)
                    {
                        // Check for MZ header (valid Windows executable)
                        return buffer[0] == 0x4D && buffer[1] == 0x5A;
                    }
                }
            }
            catch (IOException ex)
            {
                Log($"Warning: Could not verify extractor file (may be in use): {ex.Message}");
                // File exists but is locked - assume it's valid
                return true;
            }
            catch (UnauthorizedAccessException ex)
            {
                Log($"Warning: Access denied to extractor file: {ex.Message}");
                return true;
            }
            catch (Exception)
            {
                return false;
            }

            return false;
        }

        private async Task<bool> DownloadExtractor()
        {
            // Check write permissions
            try
            {
                Directory.CreateDirectory(InstallDir);
                var testFile = Path.Combine(InstallDir, ".write_test");
                File.WriteAllText(testFile, "test");
                File.Delete(testFile);
            }
            catch (UnauthorizedAccessException)
            {
                Log($"ERROR: No write permission to {InstallDir}");
                SafeUpdateUI(() => MessageBox.Show(
                    $"Cannot write to:\n{InstallDir}\n\nPlease run as administrator or check folder permissions.",
                    "Permission Denied", MessageBoxButtons.OK, MessageBoxIcon.Error));
                return false;
            }
            catch (Exception ex)
            {
                Log($"ERROR: Cannot create install directory: {ex.Message}");
                return false;
            }

            var serverApiUrl = $"{_config.ServerUrl}/api/extractor/download-exe";

            var sources = new[]
            {
                new { Name = "server API", Url = serverApiUrl },
                new { Name = "GitHub releases", Url = GitHubExeUrl }
            };

            foreach (var source in sources)
            {
                try
                {
                    Log($"  Trying {source.Name}...");

                    using (var cts = new CancellationTokenSource(TimeSpan.FromMinutes(5)))
                    {
                        var response = await SharedHttpClient.GetAsync(source.Url, cts.Token);
                        if (!response.IsSuccessStatusCode) continue;

                        var contentType = response.Content.Headers.ContentType?.MediaType ?? "";
                        if (contentType.Contains("text/html") || contentType.Contains("application/json"))
                        {
                            Log($"  {source.Name} returned non-binary content type: {contentType}");
                            continue;
                        }

                        var bytes = await response.Content.ReadAsByteArrayAsync();
                        if (bytes.Length < 50000) continue;

                        // Save to temp location first for verification
                        var tempPath = ExtractorExePath + ".tmp";
                        File.WriteAllBytes(tempPath, bytes);

                        // Verify Authenticode signature before accepting
                        if (!VerifyAuthenticodeSignature(tempPath))
                        {
                            Log($"  WARNING: {source.Name} - Authenticode signature verification failed!");
                            SafeDeleteFile(tempPath);
                            continue;
                        }

                        // Safe file replacement with backup
                        if (!SafeReplaceFile(tempPath, ExtractorExePath))
                        {
                            continue;
                        }

                        Log($"  Downloaded from {source.Name} ({bytes.Length / 1024}KB) - Signature verified");
                        return true;
                    }
                }
                catch (OperationCanceledException)
                {
                    Log($"  {source.Name} timed out");
                }
                catch (Exception ex)
                {
                    Log($"  {source.Name} failed: {ex.Message}");
                }
            }

            // Method 3: Try GitHub API to find asset
            try
            {
                Log("  Querying GitHub API...");
                using (var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30)))
                {
                    var apiResponse = await SharedHttpClient.GetAsync(GitHubApiUrl, cts.Token);

                    if (apiResponse.StatusCode == HttpStatusCode.Forbidden ||
                        apiResponse.StatusCode == HttpStatusCode.TooManyRequests)
                    {
                        Log("  GitHub API rate limited. Try again later.");
                        return false;
                    }

                    if (!apiResponse.IsSuccessStatusCode)
                    {
                        Log($"  GitHub API returned: {apiResponse.StatusCode}");
                        return false;
                    }

                    var json = await apiResponse.Content.ReadAsStringAsync();

                    JObject release;
                    try
                    {
                        release = JObject.Parse(json);
                    }
                    catch (JsonException)
                    {
                        Log("  GitHub API returned invalid JSON");
                        return false;
                    }

                    var assets = release["assets"] as JArray;
                    if (assets == null || assets.Count == 0)
                    {
                        Log("  No release assets found");
                        return false;
                    }

                    foreach (var asset in assets)
                    {
                        var name = asset["name"]?.ToString();
                        // Case-insensitive comparison
                        if (name != null &&
                            name.IndexOf("QBExtractor", StringComparison.OrdinalIgnoreCase) >= 0 &&
                            name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
                        {
                            var downloadUrl = asset["browser_download_url"]?.ToString();
                            if (string.IsNullOrEmpty(downloadUrl))
                            {
                                Log("  Asset has no download URL");
                                continue;
                            }

                            using (var dlCts = new CancellationTokenSource(TimeSpan.FromMinutes(5)))
                            {
                                var response = await SharedHttpClient.GetAsync(downloadUrl, dlCts.Token);
                                if (response.IsSuccessStatusCode)
                                {
                                    var bytes = await response.Content.ReadAsByteArrayAsync();
                                    if (bytes.Length > 50000)
                                    {
                                        var tempPath = ExtractorExePath + ".tmp";
                                        File.WriteAllBytes(tempPath, bytes);

                                        if (!VerifyAuthenticodeSignature(tempPath))
                                        {
                                            Log("  WARNING: GitHub API download - Signature verification failed!");
                                            SafeDeleteFile(tempPath);
                                            return false;
                                        }

                                        if (!SafeReplaceFile(tempPath, ExtractorExePath))
                                        {
                                            return false;
                                        }

                                        Log($"  Downloaded via GitHub API ({bytes.Length / 1024}KB) - Signature verified");
                                        return true;
                                    }
                                }
                            }
                            break;
                        }
                    }
                }
            }
            catch (OperationCanceledException)
            {
                Log("  GitHub API timed out");
            }
            catch (Exception ex)
            {
                Log($"  GitHub API failed: {ex.Message}");
            }

            return false;
        }

        /// <summary>
        /// Safely replace a file with atomic backup/restore logic
        /// </summary>
        private bool SafeReplaceFile(string sourcePath, string destPath)
        {
            var backupPath = destPath + ".bak";
            try
            {
                if (File.Exists(destPath))
                {
                    SafeDeleteFile(backupPath);
                    File.Move(destPath, backupPath);
                }

                File.Move(sourcePath, destPath);

                SafeDeleteFile(backupPath);
                return true;
            }
            catch (Exception ex)
            {
                Log($"  File move failed: {ex.Message}");
                // Restore from backup if move failed
                if (File.Exists(backupPath) && !File.Exists(destPath))
                {
                    try
                    {
                        File.Move(backupPath, destPath);
                        Log("  Restored previous version from backup");
                    }
                    catch (Exception restoreEx)
                    {
                        Log($"  Failed to restore backup: {restoreEx.Message}");
                    }
                }
                SafeDeleteFile(sourcePath);
                return false;
            }
        }

        /// <summary>
        /// Safely delete a file, ignoring errors
        /// </summary>
        private void SafeDeleteFile(string path)
        {
            try
            {
                if (File.Exists(path))
                    File.Delete(path);
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"Warning: Could not delete {path}: {ex.Message}");
            }
        }

        /// <summary>
        /// Verify Authenticode signature on downloaded executable
        /// </summary>
        private bool VerifyAuthenticodeSignature(string filePath)
        {
            try
            {
                var cert = System.Security.Cryptography.X509Certificates.X509Certificate.CreateFromSignedFile(filePath);

                if (cert != null)
                {
                    var subject = cert.Subject;
                    var validSubjects = new[] { "ForensicBridge", "sivaharanj7805", "Forensic Bridge" };

                    foreach (var validSubject in validSubjects)
                    {
                        if (subject.IndexOf(validSubject, StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            Log($"  Signature verified: {subject}");
                            return true;
                        }
                    }

                    Log($"  Unexpected signer: {subject}");
                    return false;
                }

                Log("  No Authenticode signature found");
                return false;
            }
            catch (CryptographicException)
            {
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
            // Use cached compiled regex for sanitization
            var sanitizedCode = SanitizeRegex.Replace(sessionCode, "");
            if (sanitizedCode.Length != sessionCode.Length)
            {
                Log("WARNING: Session code contained invalid characters that were removed");
            }

            var args = $"--session {sanitizedCode} --no-pause";

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

            var tcs = new TaskCompletionSource<int>();
            Process process;

            lock (_processLock)
            {
                process = new Process { StartInfo = startInfo };
                process.EnableRaisingEvents = true;
                _extractorProcess = process;
            }

            // Attach handlers before starting process
            process.Exited += (s, args2) =>
            {
                int exitCode;
                try
                {
                    exitCode = process.ExitCode;
                }
                catch (InvalidOperationException)
                {
                    exitCode = -1;
                }
                tcs.TrySetResult(exitCode);
            };

            process.OutputDataReceived += (s, args2) =>
            {
                if (!string.IsNullOrEmpty(args2.Data))
                {
                    SafeUpdateUI(() =>
                    {
                        Log(args2.Data);
                        UpdateProgressFromOutput(args2.Data);
                    });
                }
            };

            process.ErrorDataReceived += (s, args2) =>
            {
                if (!string.IsNullOrEmpty(args2.Data))
                {
                    SafeUpdateUI(() => Log($"[ERR] {args2.Data}"));
                }
            };

            try
            {
                if (!process.Start())
                {
                    throw new InvalidOperationException("Failed to start QBExtractor process");
                }
            }
            catch (Exception ex)
            {
                Log($"Failed to start extractor: {ex.Message}");
                lock (_processLock)
                {
                    _extractorProcess = null;
                }
                throw;
            }

            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            Log($"QBExtractor started (PID: {process.Id})");

            var exitCode = await tcs.Task;

            lock (_processLock)
            {
                _extractorProcess = null;
            }

            SafeUpdateUI(() =>
            {
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
                        $"Extraction failed.\n\n{errorMsg}\n\nSee the activity log for details.\n\nSupport: {_config.SupportEmail}",
                        "Extraction Failed",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            });

            // Dispose process after use
            process.Dispose();
        }

        /// <summary>
        /// Parse QBExtractor output to update progress bar
        /// </summary>
        private void UpdateProgressFromOutput(string line)
        {
            var lower = line.ToLowerInvariant();

            // Use static milestones to avoid allocation
            foreach (var milestone in ProgressMilestones)
            {
                foreach (var keyword in milestone.keywords)
                {
                    if (lower.Contains(keyword))
                    {
                        progressBar.Value = Math.Max(progressBar.Value, milestone.progress);
                        return;
                    }
                }
            }

            TryParseProgressPercentage(line);
        }

        /// <summary>
        /// Parse percentage from output like "[50%]" or "Progress: 50%"
        /// </summary>
        private void TryParseProgressPercentage(string line)
        {
            var percentIdx = line.IndexOf('%');
            if (percentIdx <= 0) return;

            // Simple string building for max 3 digits
            int startIdx = percentIdx - 1;
            int digitCount = 0;

            while (startIdx >= 0 && digitCount < 3 && char.IsDigit(line[startIdx]))
            {
                startIdx--;
                digitCount++;
            }

            if (digitCount > 0)
            {
                var numStr = line.Substring(startIdx + 1, digitCount);
                if (int.TryParse(numStr, NumberStyles.None, CultureInfo.InvariantCulture, out var pct) && pct >= 0 && pct <= 100)
                {
                    progressBar.Value = Math.Max(progressBar.Value, pct);
                }
            }
        }

        private static string GetExitCodeMessage(int exitCode)
        {
            switch (exitCode)
            {
                case -1: return "Process terminated unexpectedly.";
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

        /// <summary>
        /// Safe UI update that handles disposed forms
        /// </summary>
        private void SafeUpdateUI(Action action)
        {
            if (this.IsDisposed || this.Disposing)
                return;

            try
            {
                if (this.InvokeRequired)
                {
                    // Use Invoke for synchronous update to prevent ordering issues
                    this.Invoke(action);
                }
                else
                {
                    action();
                }
            }
            catch (ObjectDisposedException)
            {
                // Form was disposed during invoke - ignore
            }
            catch (InvalidOperationException)
            {
                // Handle wasn't created yet or form is closing - ignore
            }
        }

        private void Log(string message)
        {
            // Use invariant culture for timestamp
            var timestamp = DateTime.Now.ToString("HH:mm:ss", CultureInfo.InvariantCulture);
            var logMessage = $"[{timestamp}] {message}{Environment.NewLine}";

            SafeUpdateUI(() =>
            {
                // Truncate log if it gets too large to prevent memory issues
                if (txtLog.TextLength > MaxLogSize)
                {
                    var truncateAmount = MaxLogSize / 4;
                    txtLog.Text = "... (log truncated) ..." + Environment.NewLine +
                                  txtLog.Text.Substring(truncateAmount);
                }

                txtLog.AppendText(logMessage);
                txtLog.SelectionStart = txtLog.TextLength;
                txtLog.ScrollToCaret();
            });
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            Process processToKill = null;

            lock (_processLock)
            {
                if (_extractorProcess != null)
                {
                    try
                    {
                        if (!_extractorProcess.HasExited)
                        {
                            processToKill = _extractorProcess;
                        }
                    }
                    catch (InvalidOperationException)
                    {
                        // Process already disposed
                    }
                }
            }

            if (processToKill != null)
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

                try
                {
                    if (!processToKill.HasExited)
                    {
                        processToKill.CloseMainWindow();

                        if (!processToKill.WaitForExit(5000))
                        {
                            if (!processToKill.HasExited)
                            {
                                Log("Process did not exit gracefully, forcing termination...");
                                processToKill.Kill();
                                processToKill.WaitForExit(2000);
                            }
                        }
                    }
                }
                catch (InvalidOperationException)
                {
                    // Process already exited - ignore
                }
                catch (Exception ex)
                {
                    Debug.WriteLine($"Warning: Error terminating process: {ex.Message}");
                }
            }

            base.OnFormClosing(e);
        }

        /// <summary>
        /// Clean up fonts and other resources
        /// </summary>
        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                _fontTitle?.Dispose();
                _fontSubtitle?.Dispose();
                _fontNormal?.Dispose();
                _fontBold?.Dispose();
                _fontMonospace?.Dispose();
                _fontButton?.Dispose();
                _fontButtonLarge?.Dispose();
            }
            base.Dispose(disposing);
        }
    }

    /// <summary>
    /// Configuration loaded from config.json
    /// </summary>
    internal sealed class AppConfig
    {
        public string ServerUrl { get; set; } = "https://api.forensicbridge.ca";
        public string Version { get; set; } = "2.0.0";
        public string ApplicationName { get; set; } = "ForensicBridge";
        public string SupportEmail { get; set; } = "support@forensicbridge.ca";
        public string DocumentationUrl { get; set; } = "https://forensicbridge.ca/docs";
    }
}
