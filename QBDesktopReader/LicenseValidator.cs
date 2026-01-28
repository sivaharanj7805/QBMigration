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
    /// Session Validator - Validates Session IDs for ForensicBridge migrations
    ///
    /// The Session ID (format: FB-YYYYMMDDHHMMSS-XXXXXXXX) is the license.
    /// Users receive a Session ID when they create a project on the dashboard.
    ///
    /// Features:
    /// - Server-side session validation
    /// - Hardware fingerprint binding (prevents sharing)
    /// - Offline caching with encrypted storage
    /// - Device activation tracking
    /// </summary>
    public static class LicenseValidator
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
        private static readonly string SESSION_ID_PATH = Path.Combine(APP_DATA_PATH, "session.id");

        static LicenseValidator()
        {
            // Default to production URL, override via environment variable
            var envUrl = Environment.GetEnvironmentVariable("FORENSICBRIDGE_API_URL");
            SESSION_API_URL = envUrl ?? "https://api.forensicbridge.ca/api/session";

            // SECURITY: Validate that the URL uses HTTPS
            if (!SESSION_API_URL.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            {
                Logger.Warn("Session", "API URL does not use HTTPS. Enforcing HTTPS protocol.");
                SESSION_API_URL = SESSION_API_URL.Replace("http://", "https://");
            }

            // Ensure directory exists
            Directory.CreateDirectory(APP_DATA_PATH);
        }

        /// <summary>
        /// Validate session ID before allowing extraction to run.
        /// Session ID format: FB-YYYYMMDDHHMMSS-XXXXXXXX
        /// </summary>
        /// <param name="sessionId">Optional session ID. If null, reads from stored session.</param>
        /// <returns>LicenseResult with validation status</returns>
        public static async Task<LicenseResult> ValidateAsync(string? sessionId = null)
        {
            // Load session ID if not provided
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                sessionId = LoadStoredSessionId();
            }

            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return LicenseResult.Invalid("No Session ID found. Please enter your Session ID from the ForensicBridge dashboard.");
            }

            // Validate session ID format
            if (!IsValidSessionIdFormat(sessionId))
            {
                return LicenseResult.Invalid("Invalid Session ID format. Session IDs start with 'FB-' (e.g., FB-20260128170624-AXO52A38)");
            }

            var fingerprint = HardwareFingerprint.Generate();

            // Try cached validation first (for offline mode)
            var cachedResult = TryValidateFromCache(sessionId, fingerprint);
            if (cachedResult != null && cachedResult.Valid)
            {
                Logger.Info("Session", "Using cached validation (offline mode)");
                return cachedResult;
            }

            // Validate with server
            try
            {
                var result = await ValidateWithServerAsync(sessionId, fingerprint);

                if (result.Valid)
                {
                    // Cache the result for offline use
                    CacheSessionResult(result, sessionId, fingerprint);
                    // Store the session ID
                    SaveSessionId(sessionId);
                }

                return result;
            }
            catch (HttpRequestException ex)
            {
                Logger.Warn("Session", $"Network error: {ex.Message}");

                // If network fails, try to use cache
                if (cachedResult != null)
                {
                    Logger.Info("Session", "Network unavailable, using cached validation");
                    return cachedResult;
                }

                return LicenseResult.Invalid("Unable to validate Session ID. Please check your internet connection.");
            }
            catch (Exception ex)
            {
                Logger.Error("Session", $"Validation error: {ex.Message}");
                return LicenseResult.Invalid($"Session validation failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Activate a session on this device.
        /// Must be called after validation succeeds for new devices.
        /// </summary>
        public static async Task<LicenseResult> ActivateAsync(string sessionId)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return LicenseResult.Invalid("Session ID is required");
            }

            if (!IsValidSessionIdFormat(sessionId))
            {
                return LicenseResult.Invalid("Invalid Session ID format. Session IDs start with 'FB-' (e.g., FB-20260128170624-AXO52A38)");
            }

            var fingerprint = HardwareFingerprint.Generate();
            var deviceName = Environment.MachineName;

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
                        // Save session ID
                        SaveSessionId(sessionId);

                        // Now validate to get full details
                        return await ValidateAsync(sessionId);
                    }
                }

                // Parse error
                var errorResponse = JsonSerializer.Deserialize<ErrorResponse>(responseBody);
                return LicenseResult.Invalid(errorResponse?.error ?? "Activation failed");
            }
            catch (Exception ex)
            {
                return LicenseResult.Invalid($"Activation failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Start an extraction - validates and reserves a migration credit.
        /// Returns an extraction token to use when completing.
        /// </summary>
        public static async Task<ExtractionStartResult> StartExtractionAsync(string? sessionId = null, string? companyName = null)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                sessionId = LoadStoredSessionId();
            }

            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return new ExtractionStartResult { Success = false, Error = "No Session ID found" };
            }

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

                var errorResponse = JsonSerializer.Deserialize<ErrorResponse>(responseBody);
                return new ExtractionStartResult
                {
                    Success = false,
                    Error = errorResponse?.error ?? "Failed to start extraction",
                    PurchaseRequired = responseBody.Contains("purchase_required")
                };
            }
            catch (Exception ex)
            {
                return new ExtractionStartResult { Success = false, Error = ex.Message };
            }
        }

        /// <summary>
        /// Complete an extraction - consumes the migration credit.
        /// </summary>
        public static async Task<bool> CompleteExtractionAsync(string extractionToken, int transactionCount, string? companyName = null, string? qbVersion = null)
        {
            var sessionId = LoadStoredSessionId();
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                Logger.Warn("Session", "Cannot complete extraction: No Session ID");
                return false;
            }

            var fingerprint = HardwareFingerprint.Generate();

            try
            {
                var requestBody = new
                {
                    session_id = sessionId,
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
                Logger.Error("Session", $"Error completing extraction: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// Get the currently stored Session ID
        /// </summary>
        public static string? GetStoredSessionId()
        {
            return LoadStoredSessionId();
        }

        /// <summary>
        /// Clear stored session data (for logout/reset)
        /// </summary>
        public static void ClearStoredSession()
        {
            try
            {
                if (File.Exists(SESSION_ID_PATH))
                    File.Delete(SESSION_ID_PATH);
                if (File.Exists(SESSION_CACHE_PATH))
                    File.Delete(SESSION_CACHE_PATH);
            }
            catch (Exception ex)
            {
                Logger.Warn("Session", $"Error clearing session: {ex.Message}");
            }
        }

        // ============================================================================
        // PRIVATE HELPERS
        // ============================================================================

        private static bool IsValidSessionIdFormat(string sessionId)
        {
            // Format: FB-YYYYMMDDHHMMSS-XXXXXXXX (e.g., FB-20260128170624-AXO52A38)
            if (string.IsNullOrWhiteSpace(sessionId))
                return false;

            sessionId = sessionId.Trim().ToUpperInvariant();

            // Must start with FB-
            if (!sessionId.StartsWith("FB-"))
                return false;

            // Should be approximately FB-14digits-8chars = 26 characters
            // But allow some flexibility for the random part
            if (sessionId.Length < 20 || sessionId.Length > 35)
                return false;

            return true;
        }

        private static async Task<LicenseResult> ValidateWithServerAsync(string sessionId, string fingerprint)
        {
            var requestBody = new
            {
                session_id = sessionId.Trim(),
                device_fingerprint = fingerprint,
                device_name = Environment.MachineName
            };

            var json = JsonSerializer.Serialize(requestBody);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            var response = await _httpClient.PostAsync($"{SESSION_API_URL}/validate", content);
            var responseBody = await response.Content.ReadAsStringAsync();

            if (response.IsSuccessStatusCode)
            {
                var result = JsonSerializer.Deserialize<SessionValidationResponse>(responseBody);

                if (result?.valid == true)
                {
                    return new LicenseResult
                    {
                        Valid = true,
                        SessionId = result.session_id,
                        ProjectName = result.project_name,
                        ClientName = result.client_name,
                        Tier = result.tier ?? "starter",
                        TierName = result.tier_name ?? "Starter",
                        RemainingMigrations = result.remaining_extractions,
                        TransactionLimit = result.transaction_limit,
                        IsNewDevice = result.is_new_device,
                        DevicesActive = result.devices_active,
                        HasCredits = result.has_credits,
                        PurchaseUrl = result.purchase_url
                    };
                }

                return LicenseResult.Invalid(result?.error ?? "Validation failed");
            }

            // Parse error response
            var errorResponse = JsonSerializer.Deserialize<ErrorResponse>(responseBody);
            var error = errorResponse?.error ?? $"Server error: {response.StatusCode}";

            // Check for specific error cases
            if ((int)response.StatusCode == 404)
            {
                error = "Invalid Session ID. Please check your code and try again.";
            }
            else if ((int)response.StatusCode == 403)
            {
                if (responseBody.Contains("purchase_required"))
                {
                    error = "No migration credits available. Please purchase a migration package at https://forensicbridge.ca/pricing";
                }
                else if (responseBody.Contains("max_devices_reached"))
                {
                    error = "This session is already activated on the maximum number of devices. Please contact support.";
                }
            }

            return LicenseResult.Invalid(error);
        }

        private static LicenseResult? TryValidateFromCache(string sessionId, string fingerprint)
        {
            try
            {
                if (!File.Exists(SESSION_CACHE_PATH))
                    return null;

                var encryptedData = File.ReadAllBytes(SESSION_CACHE_PATH);
                var decryptedData = ProtectedData.Unprotect(encryptedData, null, DataProtectionScope.CurrentUser);
                var json = Encoding.UTF8.GetString(decryptedData);

                var cache = JsonSerializer.Deserialize<SessionCache>(json);

                if (cache == null)
                    return null;

                // Verify session ID matches
                if (!string.Equals(cache.SessionId, sessionId, StringComparison.OrdinalIgnoreCase))
                {
                    Logger.Warn("Session", "Cached session ID mismatch");
                    return null;
                }

                // Verify fingerprint matches
                if (cache.Fingerprint != fingerprint)
                {
                    Logger.Warn("Session", "Cached fingerprint mismatch");
                    return null;
                }

                // Check if cache is expired (24 hours)
                if (cache.CachedAt < DateTime.UtcNow.AddHours(-24))
                {
                    Logger.Info("Session", "Cache expired");
                    return null;
                }

                return new LicenseResult
                {
                    Valid = true,
                    SessionId = cache.SessionId,
                    ProjectName = cache.ProjectName,
                    ClientName = cache.ClientName,
                    Tier = cache.Tier,
                    TierName = cache.TierName,
                    RemainingMigrations = cache.RemainingExtractions,
                    TransactionLimit = cache.TransactionLimit,
                    HasCredits = cache.HasCredits,
                    PurchaseUrl = cache.PurchaseUrl,
                    FromCache = true
                };
            }
            catch (Exception ex)
            {
                Logger.Warn("Session", $"Cache read error: {ex.Message}");
                return null;
            }
        }

        private static void CacheSessionResult(LicenseResult result, string sessionId, string fingerprint)
        {
            try
            {
                var cache = new SessionCache
                {
                    SessionId = sessionId,
                    Fingerprint = fingerprint,
                    ProjectName = result.ProjectName,
                    ClientName = result.ClientName,
                    Tier = result.Tier,
                    TierName = result.TierName,
                    RemainingExtractions = result.RemainingMigrations,
                    TransactionLimit = result.TransactionLimit,
                    HasCredits = result.HasCredits,
                    PurchaseUrl = result.PurchaseUrl,
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

        private static void SaveSessionId(string sessionId)
        {
            try
            {
                var data = Encoding.UTF8.GetBytes(sessionId);
                var encryptedData = ProtectedData.Protect(data, null, DataProtectionScope.CurrentUser);
                File.WriteAllBytes(SESSION_ID_PATH, encryptedData);
            }
            catch (Exception ex)
            {
                Logger.Error("Session", $"Session ID save error: {ex.Message}");
            }
        }

        private static string? LoadStoredSessionId()
        {
            try
            {
                if (!File.Exists(SESSION_ID_PATH))
                    return null;

                var encryptedData = File.ReadAllBytes(SESSION_ID_PATH);
                var decryptedData = ProtectedData.Unprotect(encryptedData, null, DataProtectionScope.CurrentUser);
                return Encoding.UTF8.GetString(decryptedData);
            }
            catch (Exception ex)
            {
                Logger.Warn("Session", $"Session ID load error: {ex.Message}");
                return null;
            }
        }

        // ============================================================================
        // RESPONSE MODELS
        // ============================================================================

        private class SessionValidationResponse
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
            public bool has_credits { get; set; }
            public string? purchase_url { get; set; }
            public string? error { get; set; }
        }

        private class ActivationResponse
        {
            public bool success { get; set; }
            public string? message { get; set; }
            public int? activation_id { get; set; }
            public int? extractions_used { get; set; }
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
        }

        private class SessionCache
        {
            public string SessionId { get; set; } = "";
            public string Fingerprint { get; set; } = "";
            public string? ProjectName { get; set; }
            public string? ClientName { get; set; }
            public string Tier { get; set; } = "starter";
            public string TierName { get; set; } = "Starter";
            public int RemainingExtractions { get; set; }
            public int TransactionLimit { get; set; }
            public bool HasCredits { get; set; } = true;
            public string? PurchaseUrl { get; set; }
            public DateTime CachedAt { get; set; }
        }
    }

    /// <summary>
    /// Result of session/license validation
    /// </summary>
    public class LicenseResult
    {
        public bool Valid { get; set; }
        public string? SessionId { get; set; }
        public string? ProjectName { get; set; }
        public string? ClientName { get; set; }
        public string Tier { get; set; } = "starter";
        public string TierName { get; set; } = "Starter";
        public int RemainingMigrations { get; set; }
        public int TransactionLimit { get; set; }
        public bool IsUnlimited { get; set; }
        public bool IsNewDevice { get; set; }
        public int DevicesActive { get; set; }
        public string? ExpiresAt { get; set; }
        public string? Token { get; set; }
        public string? Error { get; set; }
        public bool FromCache { get; set; }
        public bool HasCredits { get; set; } = true;
        public string? PurchaseUrl { get; set; }

        public static LicenseResult Invalid(string error)
        {
            return new LicenseResult
            {
                Valid = false,
                Error = error
            };
        }

        public bool HasMigrationsRemaining => IsUnlimited || RemainingMigrations > 0;

        public string GetDisplayStatus()
        {
            if (!Valid)
                return $"Invalid: {Error}";

            if (!HasCredits)
                return $"Session Valid - {ProjectName ?? "Project"} - No migration credits. Purchase at: {PurchaseUrl ?? "https://forensicbridge.ca/pricing"}";

            var status = $"{TierName}";
            if (!string.IsNullOrEmpty(ProjectName))
                status += $" - {ProjectName}";

            if (IsUnlimited)
                status += " (Unlimited)";
            else
                status += $" ({RemainingMigrations} extractions remaining)";

            return status;
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
        public bool PurchaseRequired { get; set; }
    }
}
