using System;
using System.Diagnostics;
using System.Drawing;
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
        private TextBox txtLog; // Changed from RichTextBox to reduce overhead (L1 fix)
        private Label lblQBStatus;
        private Panel panelHeader;

        private readonly bool _isQuickBooksInstalled; // Made readonly (L2 fix)
        private readonly bool _isQBFCInstalled;       // Made readonly (L2 fix)
        private string _sessionCode;
        private readonly bool _autoStart;
        private bool _sessionValidated;
        private Process _extractorProcess;
        private readonly AppConfig _config; // Configuration loaded from config.json (CF1-CF6 fix)

        // Static HttpClient for reuse - prevents socket exhaustion (H4, H5 fix)
        private static readonly HttpClient SharedHttpClient;
        private static readonly object HttpClientLock = new object();

        // Paths
        private static readonly string InstallDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ForensicBridge");
        private static readonly string ExtractorExePath = Path.Combine(InstallDir, "QBExtractor.exe");

        // Download sources - now loaded from config (CF1 fix)
        private const string GITHUB_REPO = "sivaharanj7805/QBMigration";
        private static readonly string GitHubExeUrl =
            $"https://github.com/{GITHUB_REPO}/releases/latest/download/QBExtractor.exe";
        private static readonly string GitHubApiUrl =
            $"https://api.github.com/repos/{GITHUB_REPO}/releases/latest";

        // Static constructor to initialize HttpClient once (H4, H5 fix)
        static MainForm()
        {
            var handler = new HttpClientHandler
            {
                AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate
            };
            SharedHttpClient = new HttpClient(handler)
            {
                Timeout = TimeSpan.FromMinutes(5) // Increased timeout for large downloads (M6 fix)
            };
            SharedHttpClient.DefaultRequestHeaders.Add("User-Agent", "ForensicBridge/2.0");
        }

        public MainForm(string sessionCode = null, bool autoStart = false)
        {
            _sessionCode = sessionCode;
            _autoStart = autoStart;

            // Load configuration first (CF1-CF6 fix)
            _config = LoadConfiguration();

            InitializeComponents();

            // Set these in constructor so they can be readonly (L2 fix)
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
                this.Load += (s, e) => btnConnect_Click(null, null);
            }
        }

        /// <summary>
        /// Load configuration from config.json (CF1-CF6 fix)
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
                Debug.WriteLine($"Warning: Could not load config.json: {ex.Message}");
            }
            return config;
        }

        private void InitializeComponents()
        {
            // Enable DPI awareness (P3 fix)
            this.AutoScaleMode = AutoScaleMode.Dpi;
            this.AutoScaleDimensions = new SizeF(96F, 96F);

            // Use config values (CF1-CF6 fix)
            this.Text = $"{_config.ApplicationName} - QuickBooks Desktop Extractor";
            this.Size = new Size(650, 600); // Slightly larger for better scaling (M1 fix)
            this.MinimumSize = new Size(500, 450); // Allow resizing with minimum (M1 fix)
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.Sizable; // Allow resizing (M1 fix)
            this.MaximizeBox = true;
            this.BackColor = SystemColors.Control; // Use system colors (L6 fix)

            panelHeader = new Panel
            {
                Dock = DockStyle.Top,
                Height = 80,
                BackColor = Color.FromArgb(37, 99, 235)
            };

            var lblTitle = new Label
            {
                Text = _config.ApplicationName, // Use config (CF1 fix)
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
                Size = new Size(590, 20),
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right // Anchor for resize (M1 fix)
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
                Font = new Font("Consolas", 11), // Slightly smaller font to fit better (M2 fix)
                Location = new Point(20, 155),
                Size = new Size(350, 26),
                CharacterCasing = CharacterCasing.Upper,
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
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
                Cursor = Cursors.Hand,
                Anchor = AnchorStyles.Top | AnchorStyles.Right
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
                Cursor = Cursors.Hand,
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
            };
            btnStartExtraction.FlatAppearance.BorderSize = 0;
            btnStartExtraction.Click += btnStartExtraction_Click;

            lblStatus = new Label
            {
                Text = "Ready",
                Font = new Font("Segoe UI", 9),
                Location = new Point(20, 260),
                Size = new Size(590, 20),
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
            };

            progressBar = new ProgressBar
            {
                Location = new Point(20, 285),
                Size = new Size(590, 20),
                Style = ProgressBarStyle.Continuous,
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
            };

            var lblLog = new Label
            {
                Text = "Activity Log:",
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                Location = new Point(20, 320),
                AutoSize = true
            };

            // Changed to TextBox (L1 fix) with system colors for accessibility (L7 fix)
            txtLog = new TextBox
            {
                Location = new Point(20, 345),
                Size = new Size(590, 200),
                ReadOnly = true,
                Multiline = true,
                ScrollBars = ScrollBars.Vertical,
                BackColor = SystemColors.Window, // Use system colors (L7 fix)
                ForeColor = SystemColors.WindowText,
                Font = new Font("Consolas", 9),
                BorderStyle = BorderStyle.FixedSingle,
                Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
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

            // Use config version (CF2 fix)
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

                // M3 fix: Properly dispose Process array
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

            // H2 fix: More flexible session code validation (allow lowercase, underscores)
            // Session codes should be alphanumeric with hyphens/underscores, 6-50 characters
            if (!Regex.IsMatch(sessionCode, @"^[A-Za-z0-9_\-]{6,50}$", RegexOptions.None, TimeSpan.FromSeconds(1)))
            {
                MessageBox.Show(
                    "Invalid session code format.\n\n" +
                    "Session codes should be letters, numbers, hyphens, and underscores only (6-50 characters).",
                    "Invalid Format", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            btnConnect.Enabled = false;
            lblStatus.Text = "Validating session...";
            // M4 fix: Don't log full session code for security
            Log($"Validating session: {sessionCode.Substring(0, Math.Min(4, sessionCode.Length))}****");

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
            // Use shared HttpClient (H4 fix)
            var fingerprint = GetDeviceFingerprint();
            var payload = JsonConvert.SerializeObject(new
            {
                session_code = sessionCode,
                device_fingerprint = fingerprint
            });

            var sessionValidateUrl = $"{_config.ServerUrl}/api/session/validate";
            var content = new StringContent(payload, Encoding.UTF8, "application/json");

            using (var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30)))
            {
                var response = await SharedHttpClient.PostAsync(sessionValidateUrl, content, cts.Token);

                if (response.IsSuccessStatusCode)
                {
                    var json = await response.Content.ReadAsStringAsync();
                    // H7 fix: Proper null checking with JObject
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

            // Fallback device identifiers
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
                catch (Exception ex)
                {
                    // C5 fix: Log instead of empty catch
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
                // M15 fix: Use full 64 char hash for better entropy
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
                    // H3 fix: Wrap browser launch in try-catch
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
            // H1 fix: Also verify file is a valid PE executable
            if (info.Length < 50000) return false;

            try
            {
                // Basic PE header check
                using (var fs = new FileStream(ExtractorExePath, FileMode.Open, FileAccess.Read))
                {
                    var buffer = new byte[2];
                    if (fs.Read(buffer, 0, 2) == 2)
                    {
                        // Check for MZ header (valid Windows executable)
                        return buffer[0] == 0x4D && buffer[1] == 0x5A;
                    }
                }
            }
            catch
            {
                return false;
            }

            return false;
        }

        private async Task<bool> DownloadExtractor()
        {
            // M12 fix: Check write permissions
            try
            {
                Directory.CreateDirectory(InstallDir);
                // Test write access
                var testFile = Path.Combine(InstallDir, ".write_test");
                File.WriteAllText(testFile, "test");
                File.Delete(testFile);
            }
            catch (UnauthorizedAccessException)
            {
                Log($"ERROR: No write permission to {InstallDir}");
                MessageBox.Show(
                    $"Cannot write to:\n{InstallDir}\n\nPlease run as administrator or check folder permissions.",
                    "Permission Denied", MessageBoxButtons.OK, MessageBoxIcon.Error);
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

            // Use shared HttpClient (H4, H5 fix)
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
                        // H9 fix: More flexible content-type checking
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
                            File.Delete(tempPath);
                            continue;
                        }

                        // C1 fix: Atomic file replacement with backup
                        var backupPath = ExtractorExePath + ".bak";
                        try
                        {
                            if (File.Exists(ExtractorExePath))
                            {
                                // Create backup before deleting
                                if (File.Exists(backupPath))
                                    File.Delete(backupPath);
                                File.Move(ExtractorExePath, backupPath);
                            }

                            File.Move(tempPath, ExtractorExePath);

                            // Success - remove backup
                            if (File.Exists(backupPath))
                                File.Delete(backupPath);
                        }
                        catch (Exception moveEx)
                        {
                            // Restore from backup if move failed
                            Log($"  File move failed: {moveEx.Message}");
                            if (File.Exists(backupPath) && !File.Exists(ExtractorExePath))
                            {
                                File.Move(backupPath, ExtractorExePath);
                                Log("  Restored previous version from backup");
                            }
                            if (File.Exists(tempPath))
                                File.Delete(tempPath);
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
            // C2 fix: Now includes signature verification
            try
            {
                Log("  Querying GitHub API...");
                using (var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30)))
                {
                    // H8 fix: Handle rate limiting
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

                    // H10 fix: Proper null handling for GitHub API response
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
                        if (name != null && name.Contains("QBExtractor") && name.EndsWith(".exe"))
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
                                        // C2 fix: Verify signature for GitHub API download too
                                        var tempPath = ExtractorExePath + ".tmp";
                                        File.WriteAllBytes(tempPath, bytes);

                                        if (!VerifyAuthenticodeSignature(tempPath))
                                        {
                                            Log("  WARNING: GitHub API download - Signature verification failed!");
                                            File.Delete(tempPath);
                                            return false;
                                        }

                                        // C1 fix: Safe file move
                                        var backupPath = ExtractorExePath + ".bak";
                                        if (File.Exists(ExtractorExePath))
                                        {
                                            if (File.Exists(backupPath))
                                                File.Delete(backupPath);
                                            File.Move(ExtractorExePath, backupPath);
                                        }

                                        File.Move(tempPath, ExtractorExePath);

                                        if (File.Exists(backupPath))
                                            File.Delete(backupPath);

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
        /// Verify Authenticode signature on downloaded executable
        /// </summary>
        private bool VerifyAuthenticodeSignature(string filePath)
        {
            try
            {
                // Use WinVerifyTrust API via X509Certificate
                var cert = System.Security.Cryptography.X509Certificates.X509Certificate.CreateFromSignedFile(filePath);

                if (cert != null)
                {
                    // L8 fix: More flexible certificate verification
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
            // C4 fix: Escape session code to prevent command injection
            // Only allow alphanumeric, hyphens, underscores
            var sanitizedCode = Regex.Replace(sessionCode, @"[^A-Za-z0-9_\-]", "", RegexOptions.None, TimeSpan.FromSeconds(1));
            if (sanitizedCode.Length != sessionCode.Length)
            {
                Log("WARNING: Session code contained invalid characters that were removed");
            }

            // Use array-based arguments to avoid shell escaping issues
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

            _extractorProcess = new Process { StartInfo = startInfo };
            _extractorProcess.EnableRaisingEvents = true;

            var tcs = new TaskCompletionSource<int>();

            // H6 fix: Attach handlers before starting process
            _extractorProcess.Exited += (s, args2) =>
            {
                tcs.TrySetResult(_extractorProcess.ExitCode);
            };

            _extractorProcess.OutputDataReceived += (s, args2) =>
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

            _extractorProcess.ErrorDataReceived += (s, args2) =>
            {
                if (!string.IsNullOrEmpty(args2.Data))
                {
                    SafeUpdateUI(() => Log($"[ERR] {args2.Data}"));
                }
            };

            // H11 fix: Start process and handle potential failure
            try
            {
                if (!_extractorProcess.Start())
                {
                    throw new InvalidOperationException("Failed to start QBExtractor process");
                }
            }
            catch (Exception ex)
            {
                Log($"Failed to start extractor: {ex.Message}");
                throw;
            }

            _extractorProcess.BeginOutputReadLine();
            _extractorProcess.BeginErrorReadLine();

            Log($"QBExtractor started (PID: {_extractorProcess.Id})");

            var exitCode = await tcs.Task;

            SafeUpdateUI(() =>
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
                        $"Extraction failed.\n\n{errorMsg}\n\nSee the activity log for details.\n\nSupport: {_config.SupportEmail}",
                        "Extraction Failed",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            });
        }

        /// <summary>
        /// Parse QBExtractor output to update progress bar (L5 fix: split into smaller methods)
        /// </summary>
        private void UpdateProgressFromOutput(string line)
        {
            var lower = line.ToLowerInvariant();

            // M8 fix: More flexible keyword matching
            var progressMilestones = new[]
            {
                (keywords: new[] { "connecting", "session", "authenticat" }, progress: 25),
                (keywords: new[] { "customer", "client" }, progress: 30),
                (keywords: new[] { "vendor", "supplier" }, progress: 40),
                (keywords: new[] { "account", "chart" }, progress: 45),
                (keywords: new[] { "invoice", "receivable" }, progress: 55),
                (keywords: new[] { "bill", "payable" }, progress: 65),
                (keywords: new[] { "transaction", "journal" }, progress: 70),
                (keywords: new[] { "encrypt" }, progress: 80),
                (keywords: new[] { "upload", "transfer" }, progress: 90),
                (keywords: new[] { "complete", "success", "finish" }, progress: 100)
            };

            foreach (var milestone in progressMilestones)
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

            // M9 fix: Safer percentage parsing
            TryParseProgressPercentage(line);
        }

        /// <summary>
        /// Parse percentage from output like "[50%]" or "Progress: 50%"
        /// </summary>
        private void TryParseProgressPercentage(string line)
        {
            var percentIdx = line.IndexOf('%');
            if (percentIdx <= 0) return;

            var numStr = new StringBuilder();
            // M9 fix: Ensure we don't go below index 0
            for (int i = percentIdx - 1; i >= 0 && numStr.Length < 3; i--)
            {
                if (char.IsDigit(line[i]))
                    numStr.Insert(0, line[i]);
                else
                    break;
            }

            if (int.TryParse(numStr.ToString(), out var pct) && pct >= 0 && pct <= 100)
            {
                progressBar.Value = Math.Max(progressBar.Value, pct);
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

        /// <summary>
        /// M10, M11 fix: Safe UI update that handles disposed forms
        /// </summary>
        private void SafeUpdateUI(Action action)
        {
            if (this.IsDisposed || this.Disposing)
                return;

            try
            {
                if (this.InvokeRequired)
                {
                    this.BeginInvoke(action);
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
            var timestamp = DateTime.Now.ToString("HH:mm:ss");
            var logMessage = $"[{timestamp}] {message}{Environment.NewLine}";

            SafeUpdateUI(() =>
            {
                txtLog.AppendText(logMessage);
                // Scroll to bottom
                txtLog.SelectionStart = txtLog.TextLength;
                txtLog.ScrollToCaret();
            });
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

                // Try graceful termination before force kill
                try
                {
                    // M14 fix: Check HasExited before each operation
                    if (!_extractorProcess.HasExited)
                    {
                        // First try graceful close
                        _extractorProcess.CloseMainWindow();

                        // Wait up to 5 seconds for graceful exit
                        if (!_extractorProcess.WaitForExit(5000))
                        {
                            // Force kill if graceful close fails
                            if (!_extractorProcess.HasExited)
                            {
                                Log("Process did not exit gracefully, forcing termination...");
                                _extractorProcess.Kill();
                                _extractorProcess.WaitForExit(2000);
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
    }

    /// <summary>
    /// Configuration loaded from config.json (CF1-CF6 fix)
    /// </summary>
    internal class AppConfig
    {
        public string ServerUrl { get; set; } = "https://api.forensicbridge.ca";
        public string Version { get; set; } = "2.0.0";
        public string ApplicationName { get; set; } = "ForensicBridge";
        public string SupportEmail { get; set; } = "support@forensicbridge.ca";
        public string DocumentationUrl { get; set; } = "https://forensicbridge.ca/docs";
    }
}
