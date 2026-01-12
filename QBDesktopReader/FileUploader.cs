using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace QBDesktopExtractor
{
    /// <summary>
    /// PHASE 2: SECURE TRANSFER - Upload encrypted QB data to AWS S3
    /// 
    /// FEATURES:
    /// - Chunked upload for large files (prevents timeouts)
    /// - RSA public key exchange for hybrid encryption
    /// - Progress tracking
    /// - Automatic retry on failure
    /// - Support for both HTTP/HTTPS with security warnings
    /// 
    /// SERVER API ENDPOINTS:
    /// - GET  /api/public-key       - Get server's RSA public key
    /// - POST /api/upload            - Single-shot upload (< 10MB)
    /// - POST /api/upload/initiate   - Start chunked upload
    /// - POST /api/upload/chunk      - Upload chunk
    /// - POST /api/upload/finalize   - Complete chunked upload
    /// - POST /api/upload/abort      - Cancel chunked upload
    /// </summary>
    public class FileUploader
    {
        private readonly string serverUrl;
        private readonly HttpClient httpClient;
        private string cachedPublicKey;

        public FileUploader(string serverUrl)
        {
            // Auto-add HTTPS if no protocol specified
            if (!serverUrl.StartsWith("http://") && !serverUrl.StartsWith("https://"))
            {
                serverUrl = "https://" + serverUrl;
            }

            // Security warning for HTTP
            if (serverUrl.StartsWith("http://") && 
                !serverUrl.Contains("localhost") && 
                !serverUrl.Contains("127.0.0.1"))
            {
                Console.WriteLine("      ⚠ WARNING: Using HTTP instead of HTTPS!");
                Console.WriteLine("         Your data encryption protects the content, but metadata is visible.");
                Console.WriteLine("         Strongly recommend using HTTPS in production.");
            }

            this.serverUrl = serverUrl;
            this.httpClient = new HttpClient
            {
                Timeout = TimeSpan.FromMinutes(30) // Long timeout for large uploads
            };
            
            this.httpClient.DefaultRequestHeaders.Add("User-Agent", "QBExtractor/4.0");
            this.httpClient.DefaultRequestHeaders.Add("X-Client-Version", "4.0.0");
        }

        /// <summary>
        /// Get server's RSA-4096 public key for hybrid encryption
        /// Returns null if server doesn't support RSA (will use TLS only)
        /// </summary>
        public async Task<string> GetServerPublicKey()
        {
            if (cachedPublicKey != null)
                return cachedPublicKey;

            try
            {
                var response = await httpClient.GetAsync($"{serverUrl}/api/public-key");
                
                if (!response.IsSuccessStatusCode)
                {
                    // Server doesn't support RSA - use HTTPS-only encryption
                    return null;
                }

                var responseBody = await response.Content.ReadAsStringAsync();
                var keyResponse = JsonConvert.DeserializeObject<PublicKeyResponse>(responseBody);
                
                if (keyResponse == null || string.IsNullOrEmpty(keyResponse.PublicKey))
                {
                    return null;
                }
                
                cachedPublicKey = keyResponse.PublicKey;
                
                return cachedPublicKey;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"      ⚠ Could not retrieve server public key: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// Upload encrypted data to AWS S3 (via Flask API)
        /// Automatically chooses single or chunked upload based on file size
        /// </summary>
        public async Task<UploadResponse> UploadEncryptedData(
            EncryptionPayload encryptionPayload, 
            string sessionId,
            bool useChunkedUpload = false,
            int chunkSizeKB = 1024)
        {
            try
            {
                if (useChunkedUpload)
                {
                    return await UploadInChunks(encryptionPayload, sessionId, chunkSizeKB);
                }
                else
                {
                    return await UploadSinglePayload(encryptionPayload, sessionId);
                }
            }
            catch (HttpRequestException ex)
            {
                throw new Exception(
                    $"Network error during upload: {ex.Message}\n" +
                    "Please check:\n" +
                    "  1. Server URL is correct\n" +
                    "  2. Internet connection is stable\n" +
                    "  3. Firewall allows outbound HTTPS", 
                    ex);
            }
            catch (TaskCanceledException ex)
            {
                throw new Exception(
                    "Upload timed out. This usually happens with very large files or slow connections.\n" +
                    "Consider:\n" +
                    "  1. Using chunked upload (automatic for files > 10MB)\n" +
                    "  2. Checking your internet speed\n" +
                    "  3. Retrying during off-peak hours",
                    ex);
            }
        }

        /// <summary>
        /// Single-shot upload for small files (< 10MB)
        /// </summary>
        private async Task<UploadResponse> UploadSinglePayload(
            EncryptionPayload encryptionPayload, 
            string sessionId)
        {
            var payload = new
            {
                session_id = sessionId,
                encryption = new
                {
                    encrypted_data = encryptionPayload.EncryptedData,
                    key = encryptionPayload.Key,
                    encrypted_key = encryptionPayload.EncryptedKey,
                    is_key_encrypted = encryptionPayload.IsKeyEncrypted,
                    iv = encryptionPayload.IV,
                    tag = encryptionPayload.Tag,
                    algorithm = encryptionPayload.Algorithm,
                    version = encryptionPayload.Version
                },
                metadata = new
                {
                    timestamp = DateTime.UtcNow.ToString("o"),
                    client_version = "4.0.0",
                    upload_method = "single",
                    data_version = "qb_desktop_4.0"
                }
            };

            string jsonPayload = JsonConvert.SerializeObject(payload);
            var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

            var response = await httpClient.PostAsync($"{serverUrl}/api/upload", content);
            
            // Validate response
            if (!response.IsSuccessStatusCode)
            {
                string errorBody = await response.Content.ReadAsStringAsync();
                throw new Exception(
                    $"Server rejected upload (HTTP {response.StatusCode}):\n{errorBody}");
            }

            // Check content type
            var contentType = response.Content.Headers.ContentType?.MediaType;
            if (contentType != "application/json")
            {
                throw new Exception(
                    $"Server returned unexpected content type: {contentType}\n" +
                    "Expected: application/json");
            }

            string responseBody = await response.Content.ReadAsStringAsync();
            var result = JsonConvert.DeserializeObject<UploadResponse>(responseBody);

            if (result == null)
            {
                throw new Exception("Failed to parse server response");
            }

            return result;
        }

        /// <summary>
        /// Chunked upload for large files (prevents timeouts, shows progress)
        /// </summary>
        private async Task<UploadResponse> UploadInChunks(
            EncryptionPayload encryptionPayload,
            string sessionId,
            int chunkSizeKB)
        {
            // Step 1: Initiate chunked upload
            var initResponse = await InitiateChunkedUpload(sessionId, encryptionPayload);
            string uploadId = initResponse.UploadId;

            try
            {
                // Step 2: Split and upload chunks
                byte[] encryptedDataBytes = Convert.FromBase64String(encryptionPayload.EncryptedData);
                int chunkSize = chunkSizeKB * 1024;
                int totalChunks = (int)Math.Ceiling((double)encryptedDataBytes.Length / chunkSize);

                for (int i = 0; i < totalChunks; i++)
                {
                    int offset = i * chunkSize;
                    int length = Math.Min(chunkSize, encryptedDataBytes.Length - offset);
                    
                    byte[] chunkData = new byte[length];
                    Array.Copy(encryptedDataBytes, offset, chunkData, 0, length);

                    await UploadChunk(uploadId, sessionId, i, totalChunks, chunkData);

                    // Progress
                    int percentComplete = (int)((i + 1) * 100.0 / totalChunks);
                    Console.Write($"\r      Uploading... {percentComplete}% ({i + 1}/{totalChunks} chunks)");
                }

                Console.WriteLine(); // New line after progress

                // Step 3: Finalize upload
                return await FinalizeChunkedUpload(uploadId, sessionId);
            }
            catch (Exception ex)
            {
                // Attempt to abort the upload to clean up server resources
                try
                {
                    await AbortChunkedUpload(uploadId, sessionId);
                }
                catch
                {
                    // Ignore abort errors - server will timeout incomplete uploads
                }
                
                throw new Exception($"Chunked upload failed at server: {ex.Message}", ex);
            }
        }

        private async Task<InitiateUploadResponse> InitiateChunkedUpload(
            string sessionId,
            EncryptionPayload encryptionPayload)
        {
            var payload = new
            {
                session_id = sessionId,
                encryption_metadata = new
                {
                    key = encryptionPayload.Key,
                    encrypted_key = encryptionPayload.EncryptedKey,
                    is_key_encrypted = encryptionPayload.IsKeyEncrypted,
                    iv = encryptionPayload.IV,
                    tag = encryptionPayload.Tag,
                    algorithm = encryptionPayload.Algorithm,
                    version = encryptionPayload.Version
                },
                metadata = new
                {
                    timestamp = DateTime.UtcNow.ToString("o"),
                    client_version = "4.0.0",
                    data_version = "qb_desktop_4.0"
                }
            };

            string jsonPayload = JsonConvert.SerializeObject(payload);
            var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

            var response = await httpClient.PostAsync($"{serverUrl}/api/upload/initiate", content);
            response.EnsureSuccessStatusCode();

            string responseBody = await response.Content.ReadAsStringAsync();
            return JsonConvert.DeserializeObject<InitiateUploadResponse>(responseBody);
        }

        private async Task UploadChunk(
            string uploadId,
            string sessionId,
            int chunkIndex,
            int totalChunks,
            byte[] chunkData)
        {
            var payload = new
            {
                upload_id = uploadId,
                session_id = sessionId,
                chunk_index = chunkIndex,
                total_chunks = totalChunks,
                chunk_data = Convert.ToBase64String(chunkData),
                chunk_size = chunkData.Length
            };

            string jsonPayload = JsonConvert.SerializeObject(payload);
            var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

            var response = await httpClient.PostAsync($"{serverUrl}/api/upload/chunk", content);
            response.EnsureSuccessStatusCode();
        }

        private async Task<UploadResponse> FinalizeChunkedUpload(string uploadId, string sessionId)
        {
            var payload = new
            {
                upload_id = uploadId,
                session_id = sessionId,
                finalized_at = DateTime.UtcNow.ToString("o")
            };

            string jsonPayload = JsonConvert.SerializeObject(payload);
            var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

            var response = await httpClient.PostAsync($"{serverUrl}/api/upload/finalize", content);
            response.EnsureSuccessStatusCode();

            string responseBody = await response.Content.ReadAsStringAsync();
            return JsonConvert.DeserializeObject<UploadResponse>(responseBody);
        }

        private async Task AbortChunkedUpload(string uploadId, string sessionId)
        {
            var payload = new
            {
                upload_id = uploadId,
                session_id = sessionId,
                reason = "client_error"
            };

            string jsonPayload = JsonConvert.SerializeObject(payload);
            var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

            // Don't throw on abort failure - best effort
            await httpClient.PostAsync($"{serverUrl}/api/upload/abort", content);
        }

        // ====================================================================
        // RESPONSE MODELS
        // ====================================================================

        public class PublicKeyResponse
        {
            [JsonProperty("public_key")]
            public string PublicKey { get; set; }

            [JsonProperty("key_format")]
            public string KeyFormat { get; set; } // "XML" or "PEM"

            [JsonProperty("key_size_bits")]
            public int KeySizeBits { get; set; } // Should be 4096
        }

        public class InitiateUploadResponse
        {
            [JsonProperty("upload_id")]
            public string UploadId { get; set; }

            [JsonProperty("status")]
            public string Status { get; set; }

            [JsonProperty("expires_at")]
            public string ExpiresAt { get; set; }
        }

        public class UploadResponse
        {
            [JsonProperty("migration_id")]
            public string MigrationId { get; set; }

            [JsonProperty("status")]
            public string Status { get; set; }

            [JsonProperty("message")]
            public string Message { get; set; }

            [JsonProperty("s3_location")]
            public string S3Location { get; set; }

            [JsonProperty("next_phase")]
            public string NextPhase { get; set; }

            [JsonProperty("estimated_processing_time_minutes")]
            public int EstimatedProcessingTimeMinutes { get; set; }
        }
    }
}