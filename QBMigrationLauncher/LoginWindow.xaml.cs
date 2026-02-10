using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
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
        // FIX #11: Configure HttpClient with connection pooling and proper lifetime
        private static readonly HttpClient _httpClient;
        private static readonly string API_BASE_URL;
        private static readonly string SESSION_PATH;

        // FIX MEDIUM: Improved email validation pattern with additional checks
        // - Must have valid local part (no consecutive dots, no leading/trailing dots)
        // - Domain must have valid TLD (2-63 characters)
        // - Overall length validation (max 254 characters per RFC 5321)
        private static readonly Regex EmailPattern = new Regex(
            @"^(?!.*\.\.)(?!\.)[a-zA-Z0-9._%+-]{1,64}(?<!\.)@[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,63}$",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        // FIX MEDIUM: UI loading timeout to prevent indefinite waiting
        // FIX LOW: Use constant from centralized location
        private static readonly TimeSpan LoadingTimeout = Constants.Timeouts.UiLoading;
        private CancellationTokenSource? _loadingTimeoutCts;

        // FIX #16: Rate limiting state
        // FIX LOW: Use constants from centralized location
        private int _failedLoginAttempts = 0;
        private DateTime _lastFailedAttempt = DateTime.MinValue;
        private static readonly int MaxFailedAttempts = Constants.Auth.MaxFailedAttempts;
        private static readonly TimeSpan LockoutDuration = Constants.Auth.LockoutDuration;
        
        static LoginWindow()
        {
            // FIX LOW: Use constant for default API URL
            API_BASE_URL = Environment.GetEnvironmentVariable("FORENSICBRIDGE_API_URL")
                           ?? Constants.Urls.DefaultApiBaseUrl;

            var appDataPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "ForensicBridge"
            );
            Directory.CreateDirectory(appDataPath);
            SESSION_PATH = Path.Combine(appDataPath, "session.dat");

            // FIX #11: Configure HttpClient with connection pooling to prevent socket exhaustion
            // Note: net48 does not have SocketsHttpHandler; use HttpClientHandler instead
            var handler = new HttpClientHandler
            {
                MaxConnectionsPerServer = 10
            };
            _httpClient = new HttpClient(handler)
            {
                Timeout = TimeSpan.FromSeconds(30)
            };
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
                    System.Diagnostics.Debug.WriteLine("[LoginWindow] Session token expired locally - clearing session");
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
                System.Diagnostics.Debug.WriteLine($"[LoginWindow] Session restore error: {ex.Message}");
            }
            finally
            {
                ShowLoading(false);
            }
        }
        
        /// <summary>
        /// Handle Sign In button click
        /// FIX #6: Clear password from memory after use
        /// FIX #7: Map server errors to generic messages
        /// FIX #16: Add client-side rate limiting
        /// </summary>
        private async void SignInButton_Click(object sender, RoutedEventArgs e)
        {
            var email = EmailTextBox.Text?.Trim();
            var password = PasswordBox.Password;

            try
            {
                // FIX #16: Check rate limiting before proceeding
                if (IsRateLimited())
                {
                    var remainingTime = LockoutDuration - (DateTime.UtcNow - _lastFailedAttempt);
                    ShowError($"Too many failed attempts. Please try again in {Math.Ceiling(remainingTime.TotalMinutes)} minutes.");
                    return;
                }

                // Validation
                if (string.IsNullOrEmpty(email))
                {
                    ShowError("Please enter your email address.");
                    return;
                }

                // FIX MEDIUM: Improved email validation with length check
                // FIX LOW: Use constant for max email length
                if (email.Length > Constants.Auth.MaxEmailLength)
                {
                    ShowError("Email address is too long (max 254 characters).");
                    return;
                }

                // FIX #31: Validate email format before API call
                if (!EmailPattern.IsMatch(email))
                {
                    ShowError("Please enter a valid email address.");
                    return;
                }

                // FIX MEDIUM: Additional validation - check for common typos in domain
                var emailDomain = email.Substring(email.LastIndexOf('@') + 1).ToLowerInvariant();
                var commonTypos = new Dictionary<string, string>
                {
                    { "gmial.com", "gmail.com" },
                    { "gmal.com", "gmail.com" },
                    { "gamil.com", "gmail.com" },
                    { "outlok.com", "outlook.com" },
                    { "hotmal.com", "hotmail.com" },
                    { "yahooo.com", "yahoo.com" }
                };
                if (commonTypos.ContainsKey(emailDomain))
                {
                    ShowError($"Did you mean {email.Replace(emailDomain, commonTypos[emailDomain])}?");
                    return;
                }

                if (string.IsNullOrEmpty(password))
                {
                    ShowError("Please enter your password.");
                    return;
                }

                ShowLoading(true);
                HideError();

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
                        // FIX #16: Reset rate limiting on successful login
                        _failedLoginAttempts = 0;

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

                // FIX #16: Increment failed attempts counter
                _failedLoginAttempts++;
                _lastFailedAttempt = DateTime.UtcNow;

                // FIX #7: Map server errors to generic messages - don't expose details
                var errorResult = JsonSerializer.Deserialize<ErrorResponse>(responseBody);
                var serverError = errorResult?.error ?? "";

                // Log the actual error for debugging (server-side only in production)
                System.Diagnostics.Debug.WriteLine($"[LoginWindow] Login failed: {serverError}");

                // FIX #7: Show generic error to user, don't leak server internals
                ShowError(MapServerErrorToUserMessage(serverError));
            }
            catch (HttpRequestException)
            {
                ShowError("Unable to connect to server. Please check your internet connection.");
            }
            catch (TaskCanceledException)
            {
                ShowError("Request timed out. Please try again.");
            }
            catch (Exception ex)
            {
                // FIX #7: Don't expose exception details to users - log internally only
                System.Diagnostics.Debug.WriteLine($"[LoginWindow] Login error (internal): {ex.Message}");
                ShowError("An unexpected error occurred. Please try again.");
            }
            finally
            {
                // FIX #6: Clear password from memory immediately after use
                PasswordBox.Clear();
                ShowLoading(false);
            }
        }

        /// <summary>
        /// FIX #16: Check if user is currently rate limited
        /// </summary>
        private bool IsRateLimited()
        {
            if (_failedLoginAttempts < MaxFailedAttempts)
                return false;

            // Check if lockout period has expired
            if (DateTime.UtcNow - _lastFailedAttempt > LockoutDuration)
            {
                // Reset rate limiting
                _failedLoginAttempts = 0;
                return false;
            }

            return true;
        }

        /// <summary>
        /// FIX #7: Map server error messages to user-friendly generic messages
        /// </summary>
        private static string MapServerErrorToUserMessage(string serverError)
        {
            // Map known error types to generic messages
            if (string.IsNullOrEmpty(serverError))
                return "Login failed. Please check your credentials.";

            var lowerError = serverError.ToLowerInvariant();

            if (lowerError.Contains("invalid") || lowerError.Contains("incorrect") ||
                lowerError.Contains("wrong") || lowerError.Contains("password") ||
                lowerError.Contains("email") || lowerError.Contains("credentials"))
            {
                return "Invalid email or password. Please try again.";
            }

            if (lowerError.Contains("locked") || lowerError.Contains("disabled") ||
                lowerError.Contains("suspended"))
            {
                return "Your account has been locked. Please contact support.";
            }

            if (lowerError.Contains("expired"))
            {
                return "Your session has expired. Please log in again.";
            }

            if (lowerError.Contains("rate") || lowerError.Contains("limit") ||
                lowerError.Contains("too many"))
            {
                return "Too many login attempts. Please wait a few minutes.";
            }

            // Default generic message
            return "Login failed. Please try again.";
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
                System.Diagnostics.Debug.WriteLine($"[LoginWindow] Session save error: {ex.Message}");
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

            // FIX MEDIUM: Add UI loading timeout to prevent indefinite waiting
            if (show)
            {
                // Cancel and dispose any existing timeout to prevent resource leak
                _loadingTimeoutCts?.Cancel();
                _loadingTimeoutCts?.Dispose();
                _loadingTimeoutCts = new CancellationTokenSource();

                // Start timeout task
                var timeoutToken = _loadingTimeoutCts.Token;
                Task.Run(async () =>
                {
                    try
                    {
                        await Task.Delay(LoadingTimeout, timeoutToken);

                        // Timeout reached - hide loading and show error
                        if (!timeoutToken.IsCancellationRequested)
                        {
                            Dispatcher.Invoke(() =>
                            {
                                ShowLoading(false);
                                ShowError("Request timed out. Please try again.");
                            });
                        }
                    }
                    catch (TaskCanceledException)
                    {
                        // Timeout was cancelled - this is expected when loading completes normally
                    }
                }, timeoutToken);
            }
            else
            {
                // Loading complete - cancel the timeout and dispose the CancellationTokenSource
                // FIX: Dispose CTS to prevent resource leak
                _loadingTimeoutCts?.Cancel();
                _loadingTimeoutCts?.Dispose();
                _loadingTimeoutCts = null;
            }
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

        /// <summary>
        /// FIX #8: Check if the session is expired locally
        /// </summary>
        public bool IsExpired => ExpiresAt != DateTime.MinValue && DateTime.UtcNow >= ExpiresAt;

        /// <summary>
        /// FIX #8: Check if the session is valid (has token and not expired)
        /// </summary>
        public bool IsValid => !string.IsNullOrEmpty(Token) && !IsExpired;
    }

    /// <summary>
    /// FIX #8: Helper class for making authenticated API calls with session expiry enforcement
    /// </summary>
    public static class AuthenticatedHttpClient
    {
        private static readonly HttpClient _client;
        private static readonly string _apiBaseUrl;

        static AuthenticatedHttpClient()
        {
            _apiBaseUrl = Environment.GetEnvironmentVariable("FORENSICBRIDGE_API_URL")
                          ?? "https://api.forensicbridge.ca";

            // Note: net48 does not have SocketsHttpHandler; use HttpClientHandler instead
            var handler = new HttpClientHandler
            {
                MaxConnectionsPerServer = 10
            };
            _client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(30) };
        }

        /// <summary>
        /// FIX #8: Check session expiry on every API call
        /// Throws SessionExpiredException if session is expired
        /// </summary>
        public static async Task<HttpResponseMessage> SendAuthenticatedAsync(
            HttpRequestMessage request,
            SessionData? session)
        {
            // FIX #8: Always check session expiry before making API call
            if (session == null || !session.IsValid)
            {
                throw new SessionExpiredException("Session is expired or invalid. Please log in again.");
            }

            // Add authorization header
            request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", session.Token);

            var response = await _client.SendAsync(request);

            // FIX #8: Check for 401 Unauthorized which indicates server-side session expiry
            if (response.StatusCode == System.Net.HttpStatusCode.Unauthorized)
            {
                throw new SessionExpiredException("Session has expired. Please log in again.");
            }

            return response;
        }

        /// <summary>
        /// FIX #8: Convenience method for GET requests
        /// </summary>
        public static async Task<HttpResponseMessage> GetAsync(string endpoint, SessionData? session)
        {
            var request = new HttpRequestMessage(HttpMethod.Get, $"{_apiBaseUrl}{endpoint}");
            return await SendAuthenticatedAsync(request, session);
        }

        /// <summary>
        /// FIX #8: Convenience method for POST requests
        /// </summary>
        public static async Task<HttpResponseMessage> PostAsync(string endpoint, HttpContent content, SessionData? session)
        {
            var request = new HttpRequestMessage(HttpMethod.Post, $"{_apiBaseUrl}{endpoint}")
            {
                Content = content
            };
            return await SendAuthenticatedAsync(request, session);
        }
    }

    /// <summary>
    /// FIX #8: Exception thrown when session is expired
    /// </summary>
    public class SessionExpiredException : Exception
    {
        public SessionExpiredException(string message) : base(message) { }
    }
}
