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
    /// License Validator - Production-grade license validation for ForensicBridge
    /// 
    /// Features:
    /// - Server-side license validation
    /// - Hardware fingerprint binding
    /// - Offline caching with JWT tokens
    /// - Secure encrypted storage via DPAPI
    /// </summary>
    public static class LicenseValidator
    {
        // API Configuration
        private static readonly string LICENSE_API_URL;
        private static readonly HttpClient _httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
        
        // Cache paths
        private static readonly string APP_DATA_PATH = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ForensicBridge"
        );
        private static readonly string LICENSE_CACHE_PATH = Path.Combine(APP_DATA_PATH, "license.cache");
        private static readonly string LICENSE_KEY_PATH = Path.Combine(APP_DATA_PATH, "license.key");
        
        static LicenseValidator()
        {
            // Default to production URL, override via environment variable
            var envUrl = Environment.GetEnvironmentVariable("FORENSICBRIDGE_API_URL"); 
            LICENSE_API_URL = envUrl ?? "https://api.forensicbridge.ca/api/license";
            
            // SECURITY: Validate that the license URL uses HTTPS
            if (!LICENSE_API_URL.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            {
                Logger.Warn("License", "License API URL does not use HTTPS. Enforcing HTTPS protocol.");
                LICENSE_API_URL = LICENSE_API_URL.Replace("http://", "https://");
            }
            
            // Ensure directory exists
            Directory.CreateDirectory(APP_DATA_PATH);
        }
        
        /// <summary>
        /// Validate license key before allowing application to run
        /// </summary>
        /// <param name="licenseKey">Optional license key. If null, reads from stored key.</param>
        /// <returns>LicenseResult with validation status</returns>
        public static async Task<LicenseResult> ValidateAsync(string? licenseKey = null)
        {
            // Load license key if not provided
            if (string.IsNullOrWhiteSpace(licenseKey))
            {
                licenseKey = LoadStoredLicenseKey();
            }
            
            if (string.IsNullOrWhiteSpace(licenseKey))
            {
                return LicenseResult.Invalid("No license key found. Please purchase a license at https://forensicbridge.ca");
            }
            
            var fingerprint = HardwareFingerprint.Generate();
            
            // Try cached validation first (for offline mode)
            var cachedResult = TryValidateFromCache(fingerprint);
            if (cachedResult != null && cachedResult.Valid)
            {
                Logger.Info("License", "Using cached validation (offline mode)");
                return cachedResult;
            }
            
            // Validate with server
            try
            {
                var result = await ValidateWithServerAsync(licenseKey, fingerprint);
                
                if (result.Valid)
                {
                    // Cache the result for offline use
                    CacheLicenseResult(result, fingerprint);
                    // Store the license key
                    SaveLicenseKey(licenseKey);
                }
                
                return result;
            }
            catch (HttpRequestException ex)
            {
                Logger.Warn("License", $"Network error: {ex.Message}");
                
                // If network fails, try to use cache
                if (cachedResult != null)
                {
                    Logger.Info("License", "Network unavailable, using cached validation");
                    return cachedResult;
                }
                
                return LicenseResult.Invalid("Unable to validate license. Please check your internet connection.");
            }
            catch (Exception ex)
            {
                Logger.Error("License", $"Validation error: {ex.Message}");
                return LicenseResult.Invalid($"License validation failed: {ex.Message}");
            }
        }
        
        /// <summary>
        /// Activate a new license key on this machine
        /// </summary>
        public static async Task<LicenseResult> ActivateAsync(string licenseKey)
        {
            if (string.IsNullOrWhiteSpace(licenseKey))
            {
                return LicenseResult.Invalid("License key is required");
            }
            
            var fingerprint = HardwareFingerprint.Generate();
            
            try
            {
                var requestBody = new
                {
                    license_key = licenseKey.Trim(),
                    hardware_fingerprint = fingerprint
                };
                
                var json = JsonSerializer.Serialize(requestBody);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                
                var response = await _httpClient.PostAsync($"{LICENSE_API_URL}/activate", content);
                var responseBody = await response.Content.ReadAsStringAsync();
                
                if (response.IsSuccessStatusCode)
                {
                    var result = JsonSerializer.Deserialize<ActivationResponse>(responseBody);
                    
                    if (result?.success == true)
                    {
                        // Save license key
                        SaveLicenseKey(licenseKey);
                        
                        // Cache result
                        var licenseResult = new LicenseResult
                        {
                            Valid = true,
                            Tier = result.tier ?? "starter",
                            RemainingMigrations = result.migrations_remaining,
                            Token = result.token
                        };
                        CacheLicenseResult(licenseResult, fingerprint);
                        
                        return licenseResult;
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
        /// Report that a migration was used (decrements server-side count)
        /// </summary>
        public static async Task<bool> UseMigrationAsync(string migrationId)
        {
            var licenseKey = LoadStoredLicenseKey();
            if (string.IsNullOrWhiteSpace(licenseKey))
            {
                Logger.Warn("License", "Cannot report migration usage: No license key");
                return false;
            }
            
            var fingerprint = HardwareFingerprint.Generate();
            
            try
            {
                var requestBody = new
                {
                    license_key = licenseKey,
                    hardware_fingerprint = fingerprint,
                    migration_id = migrationId
                };
                
                var json = JsonSerializer.Serialize(requestBody);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                
                var response = await _httpClient.PostAsync($"{LICENSE_API_URL}/use-migration", content);
                
                if (response.IsSuccessStatusCode)
                {
                    Logger.Info("License", "Migration usage reported successfully");
                    return true;
                }
                
                Logger.Warn("License", $"Failed to report migration usage: {response.StatusCode}");
                return false;
            }
            catch (Exception ex)
            {
                Logger.Error("License", $"Error reporting migration usage: {ex.Message}");
                return false;
            }
        }
        
        /// <summary>
        /// Get current license usage/remaining migrations
        /// </summary>
        public static async Task<int> GetRemainingMigrationsAsync()
        {
            var result = await ValidateAsync();
            return result.Valid ? result.RemainingMigrations : 0;
        }
        
        // ============================================================================
        // PRIVATE HELPERS
        // ============================================================================
        
        private static async Task<LicenseResult> ValidateWithServerAsync(string licenseKey, string fingerprint)
        {
            var requestBody = new
            {
                license_key = licenseKey.Trim(),
                hardware_fingerprint = fingerprint
            };
            
            var json = JsonSerializer.Serialize(requestBody);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            
            var response = await _httpClient.PostAsync($"{LICENSE_API_URL}/validate", content);
            var responseBody = await response.Content.ReadAsStringAsync();
            
            if (response.IsSuccessStatusCode)
            {
                var result = JsonSerializer.Deserialize<ValidationResponse>(responseBody);
                
                if (result?.valid == true)
                {
                    return new LicenseResult
                    {
                        Valid = true,
                        Tier = result.tier ?? "starter",
                        TierName = result.tier_name ?? "Starter",
                        RemainingMigrations = result.migrations_remaining,
                        IsUnlimited = result.is_unlimited,
                        ExpiresAt = result.expires_at,
                        Token = result.token
                    };
                }
                
                return LicenseResult.Invalid(result?.error ?? "Validation failed");
            }
            
            // Parse error response
            var errorResponse = JsonSerializer.Deserialize<ErrorResponse>(responseBody);
            return LicenseResult.Invalid(errorResponse?.error ?? $"Server error: {response.StatusCode}");
        }
        
        private static LicenseResult? TryValidateFromCache(string fingerprint)
        {
            try
            {
                if (!File.Exists(LICENSE_CACHE_PATH))
                    return null;
                
                var encryptedData = File.ReadAllBytes(LICENSE_CACHE_PATH);
                var decryptedData = ProtectedData.Unprotect(encryptedData, null, DataProtectionScope.CurrentUser);
                var json = Encoding.UTF8.GetString(decryptedData);
                
                var cache = JsonSerializer.Deserialize<LicenseCache>(json);
                
                if (cache == null)
                    return null;
                
                // Verify fingerprint matches
                if (cache.Fingerprint != fingerprint)
                {
                    Logger.Warn("License", "Cached fingerprint mismatch");
                    return null;
                }
                
                // Check if cache is expired (24 hours)
                if (cache.CachedAt < DateTime.UtcNow.AddHours(-24))
                {
                    Logger.Info("License", "Cache expired");
                    return null;
                }
                
                return new LicenseResult
                {
                    Valid = true,
                    Tier = cache.Tier,
                    TierName = cache.TierName,
                    RemainingMigrations = cache.RemainingMigrations,
                    IsUnlimited = cache.IsUnlimited,
                    FromCache = true
                };
            }
            catch (Exception ex)
            {
                Logger.Warn("License", $"Cache read error: {ex.Message}");
                return null;
            }
        }
        
        private static void CacheLicenseResult(LicenseResult result, string fingerprint)
        {
            try
            {
                var cache = new LicenseCache
                {
                    Fingerprint = fingerprint,
                    Tier = result.Tier,
                    TierName = result.TierName,
                    RemainingMigrations = result.RemainingMigrations,
                    IsUnlimited = result.IsUnlimited,
                    Token = result.Token,
                    CachedAt = DateTime.UtcNow
                };
                
                var json = JsonSerializer.Serialize(cache);
                var data = Encoding.UTF8.GetBytes(json);
                var encryptedData = ProtectedData.Protect(data, null, DataProtectionScope.CurrentUser);
                
                File.WriteAllBytes(LICENSE_CACHE_PATH, encryptedData);
            }
            catch (Exception ex)
            {
                Logger.Warn("License", $"Cache write error: {ex.Message}");
            }
        }
        
        private static void SaveLicenseKey(string licenseKey)
        {
            try
            {
                var data = Encoding.UTF8.GetBytes(licenseKey);
                var encryptedData = ProtectedData.Protect(data, null, DataProtectionScope.CurrentUser);
                File.WriteAllBytes(LICENSE_KEY_PATH, encryptedData);
            }
            catch (Exception ex)
            {
                Logger.Error("License", $"Key save error: {ex.Message}");
            }
        }
        
        private static string? LoadStoredLicenseKey()
        {
            try
            {
                if (!File.Exists(LICENSE_KEY_PATH))
                    return null;
                
                var encryptedData = File.ReadAllBytes(LICENSE_KEY_PATH);
                var decryptedData = ProtectedData.Unprotect(encryptedData, null, DataProtectionScope.CurrentUser);
                return Encoding.UTF8.GetString(decryptedData);
            }
            catch (Exception ex)
            {
                Logger.Warn("License", $"Key load error: {ex.Message}");
                return null;
            }
        }
        
        // ============================================================================
        // RESPONSE MODELS
        // ============================================================================
        
        private class ValidationResponse
        {
            public bool valid { get; set; }
            public string? tier { get; set; }
            public string? tier_name { get; set; }
            public int migrations_remaining { get; set; }
            public bool is_unlimited { get; set; }
            public string? expires_at { get; set; }
            public string? token { get; set; }
            public string? error { get; set; }
        }
        
        private class ActivationResponse
        {
            public bool success { get; set; }
            public string? message { get; set; }
            public string? tier { get; set; }
            public int migrations_remaining { get; set; }
            public string? token { get; set; }
        }
        
        private class ErrorResponse
        {
            public string? error { get; set; }
        }
        
        private class LicenseCache
        {
            public string Fingerprint { get; set; } = "";
            public string Tier { get; set; } = "starter";
            public string TierName { get; set; } = "Starter";
            public int RemainingMigrations { get; set; }
            public bool IsUnlimited { get; set; }
            public string? Token { get; set; }
            public DateTime CachedAt { get; set; }
        }
    }
    
    /// <summary>
    /// Result of license validation
    /// </summary>
    public class LicenseResult
    {
        public bool Valid { get; set; }
        public string Tier { get; set; } = "starter";
        public string TierName { get; set; } = "Starter";
        public int RemainingMigrations { get; set; }
        public bool IsUnlimited { get; set; }
        public string? ExpiresAt { get; set; }
        public string? Token { get; set; }
        public string? Error { get; set; }
        public bool FromCache { get; set; }
        
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
            
            if (IsUnlimited)
                return $"{TierName} License (Unlimited Migrations)";
            
            return $"{TierName} License ({RemainingMigrations} migrations remaining)";
        }
    }
}
