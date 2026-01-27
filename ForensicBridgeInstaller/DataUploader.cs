using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace ForensicBridgeInstaller
{
    /// <summary>
    /// Uploads encrypted QuickBooks data to the ForensicBridge server.
    /// Supports both v3.1 format (primary) and original format (fallback).
    /// </summary>
    public class DataUploader
    {
        private const string DEFAULT_SERVER_URL = "https://api.forensicbridge.ca";
        private readonly string _serverUrl;
        private readonly Action<string> _logCallback;

        public DataUploader(string serverUrl = null, Action<string> logCallback = null)
        {
            _serverUrl = (serverUrl ?? DEFAULT_SERVER_URL).TrimEnd('/');
            _logCallback = logCallback ?? (msg => { });
        }

        /// <summary>
        /// Upload encrypted extraction data to the server using v3.1 format
        /// </summary>
        public async Task<UploadResult> UploadAsync(
            string sessionCode,
            ExtractionResult extraction,
            EncryptionResult encryption,
            string deviceFingerprint)
        {
            var result = new UploadResult();

            try
            {
                _logCallback("Preparing upload payload...");

                var dataHash = DataEncryptor.ComputeHash(extraction.JsonData);

                var payload = new
                {
                    session_id = sessionCode,
                    encryption = new
                    {
                        encrypted_data = encryption.EncryptedDataBase64,
                        key = encryption.KeyBase64,
                        iv = encryption.IvBase64,
                        tag = encryption.TagBase64,
                        algorithm = encryption.Algorithm,
                        version = "3.1"
                    },
                    metadata = new
                    {
                        extractor_version = "2.0.0",
                        extraction_timestamp = extraction.ExtractedAt.ToString("o"),
                        device_fingerprint = deviceFingerprint,
                        total_records = extraction.TotalRecords,
                        entity_counts = extraction.EntityCounts,
                        data_hash = dataHash,
                        original_size_bytes = encryption.OriginalSizeBytes,
                        encrypted_size_bytes = encryption.EncryptedSizeBytes
                    },
                    company_info = new
                    {
                        company_name = extraction.CompanyName,
                        qb_version = extraction.QBVersion
                    }
                };

                var jsonPayload = JsonConvert.SerializeObject(payload);
                var payloadSizeMB = jsonPayload.Length / (1024.0 * 1024.0);

                _logCallback($"Upload payload: {payloadSizeMB:F2} MB");

                if (payloadSizeMB > 50)
                {
                    result.Error = "Data too large (>50MB). Please contact support.";
                    return result;
                }

                using (var client = new HttpClient())
                {
                    client.Timeout = TimeSpan.FromMinutes(5);
                    client.DefaultRequestHeaders.Add("User-Agent", "ForensicBridge/2.0");
                    client.DefaultRequestHeaders.Add("X-Session-Code", sessionCode);

                    var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

                    _logCallback("Uploading to server...");
                    var response = await client.PostAsync($"{_serverUrl}/api/upload", content);

                    var responseBody = await response.Content.ReadAsStringAsync();

                    if (response.IsSuccessStatusCode)
                    {
                        try
                        {
                            dynamic responseJson = JsonConvert.DeserializeObject(responseBody);
                            result.Success = true;
                            result.MigrationId = responseJson?.migration_id?.ToString();
                            result.Message = responseJson?.message?.ToString() ?? "Upload successful";
                        }
                        catch
                        {
                            result.Success = true;
                            result.Message = "Upload successful";
                        }

                        _logCallback("Upload completed successfully!");
                    }
                    else
                    {
                        var statusCode = (int)response.StatusCode;
                        _logCallback($"Server returned status {statusCode}");

                        try
                        {
                            dynamic errorJson = JsonConvert.DeserializeObject(responseBody);
                            result.Error = errorJson?.error?.ToString() ?? $"Server error (HTTP {statusCode})";
                        }
                        catch
                        {
                            result.Error = $"Server error (HTTP {statusCode})";
                        }

                        // If authentication required, give specific guidance
                        if (statusCode == 401)
                        {
                            result.Error = "Session authentication failed. Please re-validate your session code.";
                        }
                        else if (statusCode == 413)
                        {
                            result.Error = "Data too large for upload. Please contact support.";
                        }
                    }
                }
            }
            catch (TaskCanceledException)
            {
                result.Error = "Upload timed out. Please check your internet connection and try again.";
                _logCallback("Upload timed out.");
            }
            catch (HttpRequestException ex)
            {
                result.Error = $"Network error: {ex.Message}";
                _logCallback($"Network error: {ex.Message}");
            }
            catch (Exception ex)
            {
                result.Error = $"Upload failed: {ex.Message}";
                _logCallback($"Upload error: {ex.Message}");
            }

            return result;
        }

        /// <summary>
        /// Validate a session code with the server
        /// </summary>
        public async Task<SessionValidationResult> ValidateSessionAsync(
            string sessionCode, string deviceFingerprint)
        {
            var result = new SessionValidationResult();

            try
            {
                using (var client = new HttpClient())
                {
                    client.Timeout = TimeSpan.FromSeconds(30);
                    client.DefaultRequestHeaders.Add("User-Agent", "ForensicBridge/2.0");

                    var payload = JsonConvert.SerializeObject(new
                    {
                        session_code = sessionCode,
                        device_fingerprint = deviceFingerprint
                    });

                    var content = new StringContent(payload, Encoding.UTF8, "application/json");
                    var response = await client.PostAsync(
                        $"{_serverUrl}/api/session/validate", content);

                    if (response.IsSuccessStatusCode)
                    {
                        var body = await response.Content.ReadAsStringAsync();
                        dynamic json = JsonConvert.DeserializeObject(body);
                        result.Valid = json?.valid == true;
                        result.Message = json?.message?.ToString();
                    }
                    else
                    {
                        result.Valid = false;
                        result.Error = $"Validation failed (HTTP {(int)response.StatusCode})";
                    }
                }
            }
            catch (Exception ex)
            {
                result.Valid = false;
                result.Error = $"Could not reach server: {ex.Message}";
                result.ServerUnreachable = true;
            }

            return result;
        }
    }

    public class UploadResult
    {
        public bool Success { get; set; }
        public string Message { get; set; }
        public string MigrationId { get; set; }
        public string Error { get; set; }
    }

    public class SessionValidationResult
    {
        public bool Valid { get; set; }
        public string Message { get; set; }
        public string Error { get; set; }
        public bool ServerUnreachable { get; set; }
    }
}
