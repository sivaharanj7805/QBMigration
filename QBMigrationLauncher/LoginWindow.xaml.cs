using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;
using System.Security.Cryptography;
using System.IO;

namespace QBMigrationLauncher
{
    /// <summary>
    /// Login Window - Authentication UI for ForensicBridge
    /// Handles user login, license activation, and session management
    /// </summary>
    public partial class LoginWindow : Window
    {
        private static readonly HttpClient _httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
        private static readonly string API_BASE_URL;
        private static readonly string SESSION_PATH;

        // FIX #31: Basic email validation pattern
        private static readonly Regex EmailPattern = new Regex(
            @"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);
        
        static LoginWindow()
        {
            API_BASE_URL = Environment.GetEnvironmentVariable("FORENSICBRIDGE_API_URL") 
                           ?? "https://api.forensicbridge.ca";
            
            var appDataPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "ForensicBridge"
            );
            Directory.CreateDirectory(appDataPath);
            SESSION_PATH = Path.Combine(appDataPath, "session.dat");
        }
        
        public LoginWindow()
        {
            InitializeComponent();

            // FIX: Use Loaded event handler for async initialization (async void is safe for event handlers)
            Loaded += LoginWindow_Loaded;
        }

        /// <summary>
        /// FIX: Proper event handler for async initialization - async void is acceptable here
        /// </summary>
        private async void LoginWindow_Loaded(object sender, RoutedEventArgs e)
        {
            // Unsubscribe to prevent multiple calls
            Loaded -= LoginWindow_Loaded;
            await TryRestoreSessionAsync();
        }

        /// <summary>
        /// Attempt to restore a saved session token
        /// FIX: Changed from async void to async Task for proper exception propagation
        /// </summary>
        private async Task TryRestoreSessionAsync()
        {
            try
            {
                if (!File.Exists(SESSION_PATH))
                    return;
                
                var encryptedData = File.ReadAllBytes(SESSION_PATH);
                var decryptedData = ProtectedData.Unprotect(encryptedData, null, DataProtectionScope.CurrentUser);
                var sessionJson = Encoding.UTF8.GetString(decryptedData);
                
                var session = JsonSerializer.Deserialize<SessionData>(sessionJson);

                if (session == null || string.IsNullOrEmpty(session.Token))
                    return;

                // CRIT-08 FIX: Check local expiry before making network call
                if (session.ExpiresAt != DateTime.MinValue && DateTime.UtcNow >= session.ExpiresAt)
                {
                    Console.WriteLine("Session token expired locally - clearing session");
                    File.Delete(SESSION_PATH);
                    return;
                }

                // Validate token with server
                ShowLoading(true);
                
                var request = new HttpRequestMessage(HttpMethod.Get, $"{API_BASE_URL}/api/auth/me");
                request.Headers.Add("Authorization", $"Bearer {session.Token}");
                
                var response = await _httpClient.SendAsync(request);
                
                if (response.IsSuccessStatusCode)
                {
                    // Token still valid, proceed to main window
                    App.CurrentSession = session;
                    OpenMainWindow();
                    return;
                }
                
                // Token expired, clear session
                File.Delete(SESSION_PATH);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Session restore error: {ex.Message}");
            }
            finally
            {
                ShowLoading(false);
            }
        }
        
        /// <summary>
        /// Handle Sign In button click
        /// </summary>
        private async void SignInButton_Click(object sender, RoutedEventArgs e)
        {
            var email = EmailTextBox.Text?.Trim();
            var password = PasswordBox.Password;
            
            // Validation
            if (string.IsNullOrEmpty(email))
            {
                ShowError("Please enter your email address.");
                return;
            }

            // FIX #31: Validate email format before API call
            if (!EmailPattern.IsMatch(email))
            {
                ShowError("Please enter a valid email address.");
                return;
            }

            if (string.IsNullOrEmpty(password))
            {
                ShowError("Please enter your password.");
                return;
            }
            
            ShowLoading(true);
            HideError();
            
            try
            {
                var loginData = new { email, password };
                var json = JsonSerializer.Serialize(loginData);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                
                var response = await _httpClient.PostAsync($"{API_BASE_URL}/api/auth/login", content);
                var responseBody = await response.Content.ReadAsStringAsync();
                
                if (response.IsSuccessStatusCode)
                {
                    var result = JsonSerializer.Deserialize<LoginResponse>(responseBody);
                    
                    if (result?.success == true && !string.IsNullOrEmpty(result.token))
                    {
                        // Save session
                        // CRIT-08 FIX: Set expiry time (default 24 hours, or from server response)
                        var session = new SessionData
                        {
                            Token = result.token,
                            Email = result.user?.email ?? email,
                            UserId = result.user?.id ?? 0,
                            FirstName = result.user?.first_name,
                            CompanyName = result.user?.company_name,
                            ExpiresAt = DateTime.UtcNow.AddHours(24)  // Default 24 hour expiry
                        };
                        
                        SaveSession(session);
                        App.CurrentSession = session;
                        
                        OpenMainWindow();
                        return;
                    }
                }
                
                // Parse error
                var errorResult = JsonSerializer.Deserialize<ErrorResponse>(responseBody);
                ShowError(errorResult?.error ?? "Login failed. Please check your credentials.");
            }
            catch (HttpRequestException)
            {
                ShowError("Unable to connect to server. Please check your internet connection.");
            }
            catch (Exception ex)
            {
                // HIGH-02 FIX: Don't expose exception details to users - log server-side only
                Console.WriteLine($"Login error (internal): {ex.Message}");
                ShowError("An unexpected error occurred. Please try again.");
            }
            finally
            {
                ShowLoading(false);
            }
        }
        
        /// <summary>
        /// Handle Activate License button click
        /// </summary>
        private void ActivateLicenseButton_Click(object sender, RoutedEventArgs e)
        {
            var licenseWindow = new LicenseActivationWindow();
            licenseWindow.Owner = this;
            
            if (licenseWindow.ShowDialog() == true)
            {
                // License activated successfully, proceed to main window
                OpenMainWindow();
            }
        }
        
        /// <summary>
        /// Handle Register link click
        /// FIX #18: Updated to use RoutedEventArgs for keyboard-accessible Hyperlink
        /// </summary>
        private void RegisterLink_Click(object sender, RoutedEventArgs e)
        {
            // Open registration in browser
            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = "https://app.forensicbridge.ca/register",
                    UseShellExecute = true
                });
            }
            catch (Exception ex)
            {
                // FIX #8: Log actual exception for debugging
                System.Diagnostics.Debug.WriteLine($"[WARN] Could not open browser: {ex.Message}");
                ShowError("Unable to open browser. Please visit https://app.forensicbridge.ca/register");
            }
        }
        
        /// <summary>
        /// Save session to encrypted file
        /// </summary>
        private void SaveSession(SessionData session)
        {
            try
            {
                var json = JsonSerializer.Serialize(session);
                var data = Encoding.UTF8.GetBytes(json);
                var encryptedData = ProtectedData.Protect(data, null, DataProtectionScope.CurrentUser);
                File.WriteAllBytes(SESSION_PATH, encryptedData);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Session save error: {ex.Message}");
            }
        }
        
        /// <summary>
        /// Open main window and close login
        /// </summary>
        private void OpenMainWindow()
        {
            var mainWindow = new MainWindow();
            mainWindow.Show();
            this.Close();
        }
        
        private void ShowLoading(bool show)
        {
            Dispatcher.Invoke(() =>
            {
                LoadingText.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
                SignInButton.IsEnabled = !show;
                EmailTextBox.IsEnabled = !show;
                PasswordBox.IsEnabled = !show;
            });
        }
        
        private void ShowError(string message)
        {
            Dispatcher.Invoke(() =>
            {
                ErrorMessage.Text = message;
                ErrorMessage.Visibility = Visibility.Visible;
            });
        }
        
        private void HideError()
        {
            Dispatcher.Invoke(() =>
            {
                ErrorMessage.Visibility = Visibility.Collapsed;
            });
        }
        
        // ========================================================================
        // DATA MODELS
        // ========================================================================
        
        private class LoginResponse
        {
            public bool success { get; set; }
            public string? token { get; set; }
            public UserData? user { get; set; }
            public string? error { get; set; }
        }
        
        private class UserData
        {
            public int id { get; set; }
            public string? email { get; set; }
            public string? first_name { get; set; }
            public string? last_name { get; set; }
            public string? company_name { get; set; }
        }
        
        private class ErrorResponse
        {
            public string? error { get; set; }
        }
    }
    
    /// <summary>
    /// Session data stored locally
    /// CRIT-08 FIX: Added ExpiresAt field for local expiry validation
    /// </summary>
    public class SessionData
    {
        public string Token { get; set; } = "";
        public string Email { get; set; } = "";
        public int UserId { get; set; }
        public string? FirstName { get; set; }
        public string? CompanyName { get; set; }
        /// <summary>
        /// CRIT-08 FIX: Token expiration timestamp for local validation
        /// </summary>
        public DateTime ExpiresAt { get; set; } = DateTime.MinValue;
    }
}
