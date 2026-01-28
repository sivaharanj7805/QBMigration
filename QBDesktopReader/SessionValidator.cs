using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Session Validator - Validates session codes before allowing extraction
    ///
    /// Security Features:
    /// - Server-side session validation
    /// - Device fingerprint binding
    /// - Extraction limit enforcement
    /// - Fraud prevention via rate limiting
    /// </summary>
    public static class SessionValidator
    {
        // API Configuration
        private static readonly string SESSION_API_URL;
        private static readonly HttpClient _httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };

        // Cache paths
        private static readonly string APP_DATA_PATH = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ForensicBridge"
        );
        private static readonly string SESSION_CACHE_PATH = Path.Combine(APP_DATA_PATH, "session.cache");

        static SessionValidator()
        {
            // Default to production URL, override via environment variable
            var envUrl = Environment.GetEnvironmentVariable("FORENSICBRIDGE_API_URL");
            SESSION_API_URL = envUrl ?? "https://api.forensicbridge.ca/api/session";

            // SECURITY: Validate that the API URL uses HTTPS
            if (!SESSION_API_URL.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            {
                Logger.Warn("Session", "Session API URL does not use HTTPS. Enforcing HTTPS protocol.");
                SESSION_API_URL = SESSION_API_URL.Replace("http://", "https://");
            }

            // Ensure directory exists
            Directory.CreateDirectory(APP_DATA_PATH);
        }

        /// <summary>
        /// Validate a session code before allowing extraction
        /// </summary>
        /// <param name="sessionId">The session code (e.g., FB-20260127123456-ABCD1234)</param>
        /// <returns>SessionResult with validation status</returns>
        public static async Task<SessionResult> ValidateAsync(string sessionId)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return SessionResult.Invalid("Session code is required. Please enter the code from your ForensicBridge dashboard.");
            }

            // Validate session ID format
            if (!IsValidSessionFormat(sessionId))
            {
                return SessionResult.Invalid(
                    "Invalid session code format. " +
                    "Session codes should look like: FB-20260127123456-ABCD1234"
                );
            }

            var fingerprint = HardwareFingerprint.Generate();
            var deviceName = GetDeviceName();

            try
            {
                var requestBody = new
                {
                    session_id = sessionId.Trim(),
                    device_fingerprint = fingerprint,
                    device_name = deviceName
                };

                var json = JsonSerializer.Serialize(requestBody);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var response = await _httpClient.PostAsync($"{SESSION_API_URL}/validate", content);
                var responseBody = await response.Content.ReadAsStringAsync();

                if (response.IsSuccessStatusCode)
                {
                    var result = JsonSerializer.Deserialize<ValidationResponse>(responseBody);

                    if (result?.valid == true)
                    {
                        return new SessionResult
                        {
                            Valid = true,
                            SessionId = result.session_id,
                            ProjectName = result.project_name,
                            ClientName = result.client_name,
                            Tier = result.tier ?? "starter",
                            TierName = result.tier_name ?? "Starter",
                            TransactionLimit = result.transaction_limit,
                            RemainingExtractions = result.remaining_extractions,
                            IsNewDevice = result.is_new_device,
                            DevicesActive = result.devices_active
                        };
                    }

                    return SessionResult.Invalid(result?.error ?? "Validation failed");
                }

                // Handle specific error codes
                if (response.StatusCode == System.Net.HttpStatusCode.NotFound)
                {
                    return SessionResult.Invalid(
                        "Session code not found. Please check your code and try again.\n" +
                        "You can find your session code in the ForensicBridge dashboard."
                    );
                }

                if (response.StatusCode == System.Net.HttpStatusCode.Forbidden)
                {
                    var errorResponse = JsonSerializer.Deserialize<ErrorResponse>(responseBody);

                    if (errorResponse?.max_devices_reached == true)
                    {
                        return SessionResult.Invalid(
                            $"This session is already activated on {errorResponse.devices_active} devices.\n" +
                            "Please contact support to deactivate old devices, or create a new project."
                        );
                    }

                    if (errorResponse?.purchase_required == true)
                    {
                        return SessionResult.Invalid(
                            "No migration credits available.\n" +
                            "Please purchase a migration package at: https://forensicbridge.ca/pricing"
                        );
                    }

                    return SessionResult.Invalid(errorResponse?.error ?? "Access denied");
                }

                if (response.StatusCode == (System.Net.HttpStatusCode)429)
                {
                    return SessionResult.Invalid(
                        "Too many validation attempts. Please wait a few minutes and try again."
                    );
                }

                // Parse generic error
                var genericError = JsonSerializer.Deserialize<ErrorResponse>(responseBody);
                return SessionResult.Invalid(genericError?.error ?? $"Server error: {response.StatusCode}");
            }
            catch (HttpRequestException ex)
            {
                Logger.Warn("Session", $"Network error: {ex.Message}");
                return SessionResult.Invalid(
                    "Unable to validate session code. Please check your internet connection.\n" +
                    "If the problem persists, contact support."
                );
            }
            catch (Exception ex)
            {
                Logger.Error("Session", $"Validation error: {ex.Message}");
                return SessionResult.Invalid($"Session validation failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Activate a session on this device
        /// Must be called after ValidateAsync confirms the session is valid
        /// </summary>
        public static async Task<SessionResult> ActivateAsync(string sessionId)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return SessionResult.Invalid("Session code is required");
            }

            var fingerprint = HardwareFingerprint.Generate();
            var deviceName = GetDeviceName();

            try
            {
                var requestBody = new
                {
                    session_id = sessionId.Trim(),
                    device_fingerprint = fingerprint,
                    device_name = deviceName
                };

                var json = JsonSerializer.Serialize(requestBody);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var response = await _httpClient.PostAsync($"{SESSION_API_URL}/activate", content);
                var responseBody = await response.Content.ReadAsStringAsync();

                if (response.IsSuccessStatusCode)
                {
                    var result = JsonSerializer.Deserialize<ActivationResponse>(responseBody);

                    if (result?.success == true)
                    {
                        Logger.Info("Session", $"Device activated: {result.message}");

                        // Cache the session
                        CacheSession(sessionId, fingerprint);

                        return new SessionResult
                        {
                            Valid = true,
                            SessionId = sessionId,
                            ActivationId = result.activation_id,
                            DeviceNumber = result.device_number,
                            MaxDevices = result.max_devices
                        };
                    }
                }

                var errorResponse = JsonSerializer.Deserialize<ErrorResponse>(responseBody);
                return SessionResult.Invalid(errorResponse?.error ?? "Activation failed");
            }
            catch (Exception ex)
            {
                Logger.Error("Session", $"Activation error: {ex.Message}");
                return SessionResult.Invalid($"Device activation failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Start an extraction - must be called before beginning data extraction
        /// Returns an extraction token that must be passed to CompleteExtractionAsync
        /// </summary>
        public static async Task<ExtractionStartResult> StartExtractionAsync(string sessionId, string? companyName = null)
        {
            var fingerprint = HardwareFingerprint.Generate();

            try
            {
                var requestBody = new
                {
                    session_id = sessionId.Trim(),
                    device_fingerprint = fingerprint,
                    company_name = companyName ?? ""
                };

                var json = JsonSerializer.Serialize(requestBody);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var response = await _httpClient.PostAsync($"{SESSION_API_URL}/start-extraction", content);
                var responseBody = await response.Content.ReadAsStringAsync();

                if (response.IsSuccessStatusCode)
                {
                    var result = JsonSerializer.Deserialize<StartExtractionResponse>(responseBody);

                    if (result?.success == true)
                    {
                        return new ExtractionStartResult
                        {
                            Success = true,
                            ExtractionToken = result.extraction_token,
                            ExtractionNumber = result.extraction_number,
                            RemainingExtractions = result.remaining_extractions,
                            CreditTier = result.credit_tier
                        };
                    }
                }

                // Handle limit reached
                if (response.StatusCode == System.Net.HttpStatusCode.Forbidden)
                {
                    var errorResponse = JsonSerializer.Deserialize<ErrorResponse>(responseBody);

                    if (errorResponse?.limit_reached == true)
                    {
                        return new ExtractionStartResult
                        {
                            Success = false,
                            Error = "Maximum extractions reached for this session.\n" +
                                    "Please create a new project in the ForensicBridge dashboard."
                        };
                    }

                    if (errorResponse?.purchase_required == true)
                    {
                        return new ExtractionStartResult
                        {
                            Success = false,
                            Error = "No migration credits available.\n" +
                                    "Please purchase at: https://forensicbridge.ca/pricing"
                        };
                    }

                    return new ExtractionStartResult
                    {
                        Success = false,
                        Error = errorResponse?.error ?? "Access denied"
                    };
                }

                var genericError = JsonSerializer.Deserialize<ErrorResponse>(responseBody);
                return new ExtractionStartResult
                {
                    Success = false,
                    Error = genericError?.error ?? "Failed to start extraction"
                };
            }
            catch (Exception ex)
            {
                Logger.Error("Session", $"Start extraction error: {ex.Message}");
                return new ExtractionStartResult
                {
                    Success = false,
                    Error = $"Failed to start extraction: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// Complete an extraction - consumes a migration credit
        /// </summary>
        public static async Task<bool> CompleteExtractionAsync(
            string sessionId,
            string extractionToken,
            int transactionCount,
            string? companyName = null,
            string? qbVersion = null)
        {
            var fingerprint = HardwareFingerprint.Generate();

            try
            {
                var requestBody = new
                {
                    session_id = sessionId.Trim(),
                    device_fingerprint = fingerprint,
                    extraction_token = extractionToken,
                    transaction_count = transactionCount,
                    company_name = companyName ?? "",
                    qb_version = qbVersion ?? ""
                };

                var json = JsonSerializer.Serialize(requestBody);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var response = await _httpClient.PostAsync($"{SESSION_API_URL}/complete-extraction", content);

                if (response.IsSuccessStatusCode)
                {
                    Logger.Info("Session", "Extraction completed and credit consumed");
                    return true;
                }

                Logger.Warn("Session", $"Failed to complete extraction: {response.StatusCode}");
                return false;
            }
            catch (Exception ex)
            {
                Logger.Error("Session", $"Complete extraction error: {ex.Message}");
                return false;
            }
        }

        // ============================================================================
        // HELPER METHODS
        // ============================================================================

        private static bool IsValidSessionFormat(string sessionId)
        {
            // Session IDs look like: FB-20260127123456-ABCD1234
            if (string.IsNullOrWhiteSpace(sessionId))
                return false;

            sessionId = sessionId.Trim().ToUpper();

            // Must start with FB-
            if (!sessionId.StartsWith("FB-"))
                return false;

            // Must have two dashes
            var parts = sessionId.Split('-');
            if (parts.Length != 3)
                return false;

            // Middle part should be timestamp (14 digits)
            if (parts[1].Length != 14 || !long.TryParse(parts[1], out _))
                return false;

            // Last part should be 8 alphanumeric characters
            if (parts[2].Length != 8)
                return false;

            return true;
        }

        private static string GetDeviceName()
        {
            try
            {
                return Environment.MachineName;
            }
            catch
            {
                return "Unknown Device";
            }
        }

        private static void CacheSession(string sessionId, string fingerprint)
        {
            try
            {
                var cache = new SessionCache
                {
                    SessionId = sessionId,
                    Fingerprint = fingerprint,
                    CachedAt = DateTime.UtcNow
                };

                var json = JsonSerializer.Serialize(cache);
                var data = Encoding.UTF8.GetBytes(json);
                var encryptedData = ProtectedData.Protect(data, null, DataProtectionScope.CurrentUser);

                File.WriteAllBytes(SESSION_CACHE_PATH, encryptedData);
            }
            catch (Exception ex)
            {
                Logger.Warn("Session", $"Cache write error: {ex.Message}");
            }
        }

        public static string? GetCachedSessionId()
        {
            try
            {
                if (!File.Exists(SESSION_CACHE_PATH))
                    return null;

                var encryptedData = File.ReadAllBytes(SESSION_CACHE_PATH);
                var decryptedData = ProtectedData.Unprotect(encryptedData, null, DataProtectionScope.CurrentUser);
                var json = Encoding.UTF8.GetString(decryptedData);

                var cache = JsonSerializer.Deserialize<SessionCache>(json);

                // Verify fingerprint matches current device
                var currentFingerprint = HardwareFingerprint.Generate();
                if (cache?.Fingerprint != currentFingerprint)
                    return null;

                // Check if cache is too old (7 days)
                if (cache.CachedAt < DateTime.UtcNow.AddDays(-7))
                    return null;

                return cache.SessionId;
            }
            catch
            {
                return null;
            }
        }

        // ============================================================================
        // RESPONSE MODELS
        // ============================================================================

        private class ValidationResponse
        {
            public bool valid { get; set; }
            public string? session_id { get; set; }
            public string? project_name { get; set; }
            public string? client_name { get; set; }
            public string? tier { get; set; }
            public string? tier_name { get; set; }
            public int transaction_limit { get; set; }
            public int remaining_extractions { get; set; }
            public bool is_new_device { get; set; }
            public int devices_active { get; set; }
            public string? error { get; set; }
        }

        private class ActivationResponse
        {
            public bool success { get; set; }
            public string? message { get; set; }
            public int activation_id { get; set; }
            public int device_number { get; set; }
            public int max_devices { get; set; }
        }

        private class StartExtractionResponse
        {
            public bool success { get; set; }
            public string? extraction_token { get; set; }
            public int extraction_number { get; set; }
            public int remaining_extractions { get; set; }
            public string? credit_tier { get; set; }
        }

        private class ErrorResponse
        {
            public string? error { get; set; }
            public bool max_devices_reached { get; set; }
            public int devices_active { get; set; }
            public bool purchase_required { get; set; }
            public bool limit_reached { get; set; }
        }

        private class SessionCache
        {
            public string SessionId { get; set; } = "";
            public string Fingerprint { get; set; } = "";
            public DateTime CachedAt { get; set; }
        }
    }

    /// <summary>
    /// Result of session validation
    /// </summary>
    public class SessionResult
    {
        public bool Valid { get; set; }
        public string? SessionId { get; set; }
        public string? ProjectName { get; set; }
        public string? ClientName { get; set; }
        public string Tier { get; set; } = "starter";
        public string TierName { get; set; } = "Starter";
        public int TransactionLimit { get; set; }
        public int RemainingExtractions { get; set; }
        public bool IsNewDevice { get; set; }
        public int DevicesActive { get; set; }
        public int ActivationId { get; set; }
        public int DeviceNumber { get; set; }
        public int MaxDevices { get; set; }
        public string? Error { get; set; }

        public static SessionResult Invalid(string error)
        {
            return new SessionResult
            {
                Valid = false,
                Error = error
            };
        }

        public string GetDisplayStatus()
        {
            if (!Valid)
                return $"Invalid: {Error}";

            return $"Session: {SessionId}\n" +
                   $"Project: {ProjectName}\n" +
                   $"Client: {ClientName}\n" +
                   $"Tier: {TierName}\n" +
                   $"Remaining Extractions: {RemainingExtractions}";
        }
    }

    /// <summary>
    /// Result of starting an extraction
    /// </summary>
    public class ExtractionStartResult
    {
        public bool Success { get; set; }
        public string? ExtractionToken { get; set; }
        public int ExtractionNumber { get; set; }
        public int RemainingExtractions { get; set; }
        public string? CreditTier { get; set; }
        public string? Error { get; set; }
    }
}
