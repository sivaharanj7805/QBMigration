using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace QBDesktopReader
{
    public class FileUploader
    {
        private readonly string serverUrl;
        private readonly HttpClient httpClient;
        private string cachedPublicKey;

        public FileUploader(string serverUrl)
        {
            // Default to HTTPS if no protocol specified
            if (!serverUrl.StartsWith("http://") && !serverUrl.StartsWith("https://"))
            {
                serverUrl = "https://" + serverUrl;
            }

            // Warn if using HTTP
            if (serverUrl.StartsWith("http://") && !serverUrl.Contains("localhost") && !serverUrl.Contains("127.0.0.1"))
            {
                Console.WriteLine("⚠ WARNING: Using HTTP instead of HTTPS. Data will be transmitted unencrypted!");
            }

            this.serverUrl = serverUrl;
            this.httpClient = new HttpClient();
            this.httpClient.Timeout = TimeSpan.FromMinutes(30); // Increased for chunked uploads
            this.httpClient.DefaultRequestHeaders.Add("User-Agent", "QBDesktopReader/2.0");
        }

        /// <summary>
        /// Get server's RSA public key for hybrid encryption
        /// Returns null if server doesn't support RSA encryption
        /// </summary>
        public async Task<string> GetServerPublicKey()
        {
            if (cachedPublicKey != null)
                return cachedPublicKey;

            try
            {
                Console.WriteLine("Requesting server public key for secure key exchange...");
                
                var response = await httpClient.GetAsync($"{serverUrl}/api/public-key");
                
                if (!response.IsSuccessStatusCode)
                {
                    Console.WriteLine("⚠ Server doesn't support RSA key exchange. Using HTTPS-only encryption.");
                    return null;
                }

                var responseBody = await response.Content.ReadAsStringAsync();
                var keyResponse = JsonConvert.DeserializeObject<PublicKeyResponse>(responseBody);
                
                cachedPublicKey = keyResponse.PublicKey;
                Console.WriteLine("✓ Received server public key");
                
                return cachedPublicKey;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠ Could not retrieve server public key: {ex.Message}");
                Console.WriteLine("   Falling back to HTTPS-only encryption.");
                return null;
            }
        }

        /// <summary>
        /// Upload encrypted data with encryption keys to server
        /// Supports both single upload and chunked upload for large files
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
                Console.WriteLine($"✗ Upload failed: {ex.Message}");
                throw new Exception("Failed to upload data to server. Please check your network connection and server URL.", ex);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"✗ Upload failed: {ex.Message}");
                throw;
            }
        }

        /// <summary>
        /// Upload entire payload in a single request
        /// </summary>
        private async Task<UploadResponse> UploadSinglePayload(
            EncryptionPayload encryptionPayload, 
            string sessionId)
        {
            Console.WriteLine("Uploading encrypted data to server...");

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
                    tag = encryptionPayload.Tag
                },
                timestamp = DateTime.UtcNow.ToString("o"),
                client_version = "2.0",
                upload_method = "single"
            };

            string jsonPayload = JsonConvert.SerializeObject(payload);
            var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

            var response = await httpClient.PostAsync($"{serverUrl}/api/upload", content);
            
            // Check response content type
            var contentType = response.Content.Headers.ContentType?.MediaType;
            if (contentType != "application/json")
            {
                throw new Exception($"Server returned unexpected content type: {contentType}");
            }

            response.EnsureSuccessStatusCode();

            string responseBody = await response.Content.ReadAsStringAsync();
            var result = JsonConvert.DeserializeObject<UploadResponse>(responseBody);

            Console.WriteLine($"✓ Upload complete. Migration ID: {result.MigrationId}");

            return result;
        }

        /// <summary>
        /// Upload data in chunks for large files
        /// Prevents memory issues and allows for progress tracking
        /// </summary>
        private async Task<UploadResponse> UploadInChunks(
            EncryptionPayload encryptionPayload,
            string sessionId,
            int chunkSizeKB)
        {
            Console.WriteLine("Using chunked upload for large dataset...");

            // First, initiate the chunked upload
            var initResponse = await InitiateChunkedUpload(sessionId, encryptionPayload);
            string uploadId = initResponse.UploadId;

            try
            {
                // Split the encrypted data into chunks
                byte[] encryptedDataBytes = Convert.FromBase64String(encryptionPayload.EncryptedData);
                int chunkSize = chunkSizeKB * 1024;
                int totalChunks = (int)Math.Ceiling((double)encryptedDataBytes.Length / chunkSize);

                Console.WriteLine($"Uploading {totalChunks} chunks ({chunkSizeKB}KB each)...");

                for (int i = 0; i < totalChunks; i++)
                {
                    int offset = i * chunkSize;
                    int length = Math.Min(chunkSize, encryptedDataBytes.Length - offset);
                    
                    byte[] chunkData = new byte[length];
                    Array.Copy(encryptedDataBytes, offset, chunkData, 0, length);

                    await UploadChunk(uploadId, sessionId, i, totalChunks, chunkData);

                    // Progress indicator
                    int percentComplete = (int)((i + 1) * 100.0 / totalChunks);
                    Console.WriteLine($"  Progress: {percentComplete}% ({i + 1}/{totalChunks} chunks)");
                }

                // Finalize the upload
                Console.WriteLine("Finalizing upload...");
                return await FinalizeChunkedUpload(uploadId, sessionId);
            }
            catch (Exception ex)
            {
                // Attempt to abort the upload
                try
                {
                    await AbortChunkedUpload(uploadId, sessionId);
                }
                catch
                {
                    // Ignore abort errors
                }
                throw new Exception($"Chunked upload failed: {ex.Message}", ex);
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
                    tag = encryptionPayload.Tag
                },
                timestamp = DateTime.UtcNow.ToString("o"),
                client_version = "2.0"
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
                chunk_data = Convert.ToBase64String(chunkData)
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
                session_id = sessionId
            };

            string jsonPayload = JsonConvert.SerializeObject(payload);
            var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

            var response = await httpClient.PostAsync($"{serverUrl}/api/upload/finalize", content);
            response.EnsureSuccessStatusCode();

            string responseBody = await response.Content.ReadAsStringAsync();
            var result = JsonConvert.DeserializeObject<UploadResponse>(responseBody);

            Console.WriteLine($"✓ Upload complete. Migration ID: {result.MigrationId}");
            return result;
        }

        private async Task AbortChunkedUpload(string uploadId, string sessionId)
        {
            var payload = new
            {
                upload_id = uploadId,
                session_id = sessionId
            };

            string jsonPayload = JsonConvert.SerializeObject(payload);
            var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

            await httpClient.PostAsync($"{serverUrl}/api/upload/abort", content);
        }

        public class PublicKeyResponse
        {
            [JsonProperty("public_key")]
            public string PublicKey { get; set; }

            [JsonProperty("key_format")]
            public string KeyFormat { get; set; } // "XML" or "PEM"
        }

        public class InitiateUploadResponse
        {
            [JsonProperty("upload_id")]
            public string UploadId { get; set; }

            [JsonProperty("status")]
            public string Status { get; set; }
        }

        public class UploadResponse
        {
            [JsonProperty("migration_id")]
            public string MigrationId { get; set; }

            [JsonProperty("status")]
            public string Status { get; set; }

            [JsonProperty("message")]
            public string Message { get; set; }
        }
    }
}