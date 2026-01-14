using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Enterprise-grade File Uploader v4.2
    /// 
    /// FIXES FROM REVIEW:
    /// - NO RAW KEYS in payloads (keyId only)
    /// - Multipart upload (no base64 inflation)
    /// - Single upload implementation (removed legacy)
    /// - Thread-safe random (Random.Shared or lock)
    /// - Jitter always applied, with max delay cap
    /// - Cancellation token threaded through all calls
    /// - HttpClient lifecycle managed (IDisposable)
    /// - Server response validation (hash echo)
    /// - Structured logging with redaction
    /// - Consistent endpoint naming
    /// </summary>
    public class FileUploader : IDisposable
    {
        private readonly string _serverUrl;
        private readonly HttpClient _httpClient;
        private readonly ExtractionConfig _config;
        private readonly IRedactingLogger _logger;
        private readonly object _randomLock = new object();
        private readonly Random _random = new Random();
        private bool _disposed;

        public FileUploader(ExtractionConfig config, IRedactingLogger logger = null)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger;
            
            string url = config.ServerUrl;
            if (!url.StartsWith("http://") && !url.StartsWith("https://"))
            {
                url = "https://" + url;
            }

            bool isLocalhost = url.Contains("localhost") || url.Contains("127.0.0.1");
            if (url.StartsWith("http://") && !isLocalhost)
            {
                _logger?.Log(LogLevel.Warning, "Using HTTP for non-localhost URL - data is encrypted but metadata visible");
            }

            _serverUrl = url.TrimEnd('/');
            _httpClient = new HttpClient
            {
                Timeout = TimeSpan.FromMinutes(30)
            };
            
            _httpClient.DefaultRequestHeaders.Add("User-Agent", "QBExtractor/4.2");
            _httpClient.DefaultRequestHeaders.Add("X-Client-Version", "4.2.0");
        }

        /// <summary>
        /// Upload file for small files (under threshold) using multipart
        /// </summary>
        public async Task UploadFileAsync(
            string encryptedFilePath,
            EncryptionManager.EncryptionResult encryptionResult,
            string sessionId,
            QBExtractedData data,
            CancellationToken cancellationToken = default)
        {
            _logger?.Log(LogLevel.Info, "Uploading file (direct)...");

            using (var content = new MultipartFormDataContent())
            using (var fileStream = new FileStream(encryptedFilePath, FileMode.Open, FileAccess.Read))
            {
                // Add file as binary (no base64)
                var fileContent = new StreamContent(fileStream);
                fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
                content.Add(fileContent, "file", "encrypted_data.bin");

                // Add metadata (NO raw keys - keyId only)
                var metadata = new UploadMetadata
                {
                    SessionId = sessionId,
                    KeyId = encryptionResult.KeyId,
                    Algorithm = encryptionResult.Algorithm,
                    DataHashSHA256 = encryptionResult.DataHashSHA256,
                    EncryptedHashSHA256 = encryptionResult.EncryptedHashSHA256,
                    PlaintextSizeBytes = encryptionResult.PlaintextSizeBytes,
                    EncryptedSizeBytes = encryptionResult.EncryptedSizeBytes,
                    ChunkSize = encryptionResult.ChunkSize,
                    TotalChunks = encryptionResult.TotalChunks,
                    SchemaVersion = data.SchemaVersion,
                    IsIncremental = data.IsIncrementalSync
                };

                var metadataJson = JsonConvert.SerializeObject(metadata);
                content.Add(new StringContent(metadataJson, Encoding.UTF8, "application/json"), "metadata");

                var response = await _httpClient.PostAsync(
                    $"{_serverUrl}/api/upload",
                    content,
                    cancellationToken);

                await ValidateResponseAsync(response, "Upload");
            }

            _logger?.Log(LogLevel.Info, "Upload complete");
        }

        /// <summary>
        /// Upload file using chunked streaming with retry and resume
        /// </summary>
        public async Task UploadFileChunkedAsync(
            string encryptedFilePath,
            EncryptionManager.EncryptionResult encryptionResult,
            string sessionId,
            QBExtractedData data,
            CancellationToken cancellationToken = default)
        {
            var fileInfo = new FileInfo(encryptedFilePath);
            long fileSize = fileInfo.Length;
            int chunkSize = _config.Advanced.ChunkSizeKB * 1024;
            int totalChunks = (int)Math.Ceiling((double)fileSize / chunkSize);

            // Initialize upload session (server returns uploadId)
            string uploadId = await InitiateUploadAsync(sessionId, encryptionResult, totalChunks, cancellationToken);

            _logger?.Log(LogLevel.Info, "Uploading {0} chunks ({1}KB each)", totalChunks, _config.Advanced.ChunkSizeKB);

            try
            {
                using (var fileStream = new FileStream(encryptedFilePath, FileMode.Open, FileAccess.Read, FileShare.Read, chunkSize))
                {
                    byte[] buffer = new byte[chunkSize];
                    int chunkIndex = 0;

                    while (true)
                    {
                        cancellationToken.ThrowIfCancellationRequested();

                        int bytesRead = await fileStream.ReadAsync(buffer, 0, buffer.Length, cancellationToken);
                        if (bytesRead == 0) break;

                        await UploadChunkWithRetryAsync(
                            uploadId,
                            chunkIndex,
                            buffer,
                            bytesRead,
                            totalChunks,
                            cancellationToken);

                        chunkIndex++;

                        if (chunkIndex % 10 == 0 || chunkIndex == totalChunks)
                        {
                            double percent = (double)chunkIndex / totalChunks * 100.0;
                            _logger?.Log(LogLevel.Info, "Progress: {0}/{1} chunks ({2:F1}%)",
                                chunkIndex, totalChunks, percent);
                        }
                    }
                }

                // Commit upload
                _logger?.Log(LogLevel.Info, "Committing upload...");
                await CommitUploadAsync(uploadId, encryptionResult, sessionId, data, cancellationToken);
            }
            catch (Exception)
            {
                // Try to abort on failure
                try
                {
                    await AbortUploadAsync(uploadId, cancellationToken);
                }
                catch { }
                throw;
            }
        }

        /// <summary>
        /// Initiate chunked upload session
        /// </summary>
        private async Task<string> InitiateUploadAsync(
            string sessionId,
            EncryptionManager.EncryptionResult encryptionResult,
            int totalChunks,
            CancellationToken cancellationToken)
        {
            var payload = new
            {
                session_id = sessionId,
                total_chunks = totalChunks,
                key_id = encryptionResult.KeyId,
                algorithm = encryptionResult.Algorithm,
                encrypted_hash = encryptionResult.EncryptedHashSHA256
            };

            var json = JsonConvert.SerializeObject(payload);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            var response = await _httpClient.PostAsync(
                $"{_serverUrl}/api/upload/initiate",
                content,
                cancellationToken);

            await ValidateResponseAsync(response, "Initiate upload");

            var responseJson = await response.Content.ReadAsStringAsync();
            var result = JsonConvert.DeserializeObject<InitiateUploadResponse>(responseJson);

            return result?.UploadId ?? throw new Exception("Server did not return upload ID");
        }

        /// <summary>
        /// Upload single chunk with retry logic
        /// </summary>
        private async Task UploadChunkWithRetryAsync(
            string uploadId,
            int chunkIndex,
            byte[] data,
            int dataLength,
            int totalChunks,
            CancellationToken cancellationToken)
        {
            int attempts = 0;
            int maxAttempts = _config.Advanced.RetryAttempts;

            while (attempts <= maxAttempts)
            {
                try
                {
                    cancellationToken.ThrowIfCancellationRequested();

                    // Check if server already has chunk (resume support)
                    if (await ServerHasChunkAsync(uploadId, chunkIndex, cancellationToken))
                    {
                        _logger?.Log(LogLevel.Debug, "Chunk {0} already uploaded, skipping", chunkIndex);
                        return;
                    }

                    // Compute chunk hash
                    string chunkHash = ComputeChunkHash(data, dataLength);

                    // Upload chunk using multipart (no base64)
                    await UploadChunkMultipartAsync(uploadId, chunkIndex, data, dataLength, chunkHash, totalChunks, cancellationToken);
                    
                    return;
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception ex)
                {
                    attempts++;

                    if (attempts > maxAttempts)
                    {
                        _logger?.Log(LogLevel.Error, "Chunk {0} failed after {1} attempts: {2}",
                            chunkIndex, attempts, ex.Message);
                        throw;
                    }

                    int delayMs = CalculateRetryDelay(attempts);
                    _logger?.Log(LogLevel.Warning, "Chunk {0} failed, retry {1}/{2} in {3}ms",
                        chunkIndex, attempts, maxAttempts, delayMs);

                    await Task.Delay(delayMs, cancellationToken);
                }
            }
        }

        /// <summary>
        /// Upload chunk using multipart form data (no base64)
        /// </summary>
        private async Task UploadChunkMultipartAsync(
            string uploadId,
            int chunkIndex,
            byte[] data,
            int dataLength,
            string chunkHash,
            int totalChunks,
            CancellationToken cancellationToken)
        {
            using (var content = new MultipartFormDataContent())
            {
                // Add chunk data as binary
                var chunkData = new byte[dataLength];
                Buffer.BlockCopy(data, 0, chunkData, 0, dataLength);

                var chunkContent = new ByteArrayContent(chunkData);
                chunkContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
                content.Add(chunkContent, "chunk", $"chunk_{chunkIndex}.bin");

                // Add metadata
                content.Add(new StringContent(uploadId), "upload_id");
                content.Add(new StringContent(chunkIndex.ToString()), "chunk_index");
                content.Add(new StringContent(totalChunks.ToString()), "total_chunks");
                content.Add(new StringContent(chunkHash), "chunk_hash");

                var response = await _httpClient.PostAsync(
                    $"{_serverUrl}/api/upload/chunk",
                    content,
                    cancellationToken);

                await ValidateResponseAsync(response, $"Upload chunk {chunkIndex}");

                // Validate server echoed the hash
                var responseJson = await response.Content.ReadAsStringAsync();
                var result = JsonConvert.DeserializeObject<ChunkUploadResponse>(responseJson);

                if (result?.ReceivedHash != null && result.ReceivedHash != chunkHash)
                {
                    throw new Exception($"Chunk {chunkIndex} hash mismatch: sent {chunkHash}, received {result.ReceivedHash}");
                }
            }
        }

        /// <summary>
        /// Check if server already has a chunk
        /// </summary>
        private async Task<bool> ServerHasChunkAsync(
            string uploadId,
            int chunkIndex,
            CancellationToken cancellationToken)
        {
            try
            {
                var url = $"{_serverUrl}/api/upload/chunk/exists?uploadId={uploadId}&chunkIndex={chunkIndex}";
                var response = await _httpClient.GetAsync(url, cancellationToken);

                if (response.IsSuccessStatusCode)
                {
                    var json = await response.Content.ReadAsStringAsync();
                    var result = JsonConvert.DeserializeObject<ChunkExistsResponse>(json);
                    return result?.Exists ?? false;
                }
            }
            catch
            {
                // If check fails, assume chunk doesn't exist
            }

            return false;
        }

        /// <summary>
        /// Commit the upload
        /// </summary>
        private async Task CommitUploadAsync(
            string uploadId,
            EncryptionManager.EncryptionResult encryptionResult,
            string sessionId,
            QBExtractedData data,
            CancellationToken cancellationToken)
        {
            // NO raw keys - keyId only
            var payload = new
            {
                upload_id = uploadId,
                session_id = sessionId,
                key_id = encryptionResult.KeyId,
                encryption_metadata = new
                {
                    algorithm = encryptionResult.Algorithm,
                    data_hash_sha256 = encryptionResult.DataHashSHA256,
                    encrypted_hash_sha256 = encryptionResult.EncryptedHashSHA256,
                    chunk_size = encryptionResult.ChunkSize,
                    total_chunks = encryptionResult.TotalChunks,
                    plaintext_size_bytes = encryptionResult.PlaintextSizeBytes,
                    encrypted_size_bytes = encryptionResult.EncryptedSizeBytes
                },
                metadata = new
                {
                    schema_version = data.SchemaVersion,
                    extraction_version = data.ExtractionVersion,
                    is_incremental = data.IsIncrementalSync,
                    incremental_from_date = data.IncrementalFromDate,
                    qb_version = data.QBVersion,
                    extracted_at = data.ExtractedAt
                }
            };

            var json = JsonConvert.SerializeObject(payload);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            var response = await _httpClient.PostAsync(
                $"{_serverUrl}/api/upload/commit",
                content,
                cancellationToken);

            await ValidateResponseAsync(response, "Commit upload");
        }

        /// <summary>
        /// Abort an upload session
        /// </summary>
        private async Task AbortUploadAsync(string uploadId, CancellationToken cancellationToken)
        {
            try
            {
                var payload = new { upload_id = uploadId, reason = "client_error" };
                var json = JsonConvert.SerializeObject(payload);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                await _httpClient.PostAsync($"{_serverUrl}/api/upload/abort", content, cancellationToken);
            }
            catch
            {
                // Best effort
            }
        }

        /// <summary>
        /// Validate HTTP response
        /// </summary>
        private async Task ValidateResponseAsync(HttpResponseMessage response, string operation)
        {
            if (!response.IsSuccessStatusCode)
            {
                string errorBody = await response.Content.ReadAsStringAsync();
                throw new Exception($"{operation} failed (HTTP {(int)response.StatusCode}): {errorBody}");
            }
        }

        /// <summary>
        /// Compute SHA256 hash of chunk
        /// </summary>
        private string ComputeChunkHash(byte[] data, int length)
        {
            using (var sha256 = SHA256.Create())
            {
                byte[] hash = sha256.ComputeHash(data, 0, length);
                return Convert.ToBase64String(hash);
            }
        }

        /// <summary>
        /// Calculate retry delay with exponential backoff and jitter
        /// </summary>
        private int CalculateRetryDelay(int attempt)
        {
            int baseDelay = _config.Advanced.RetryDelayMs;
            int maxDelay = _config.Advanced.RetryMaxDelayMs;
            int jitterPercent = _config.Advanced.RetryJitterPercent;

            int delayMs = baseDelay;

            if (_config.Advanced.EnableExponentialBackoff)
            {
                delayMs = baseDelay * (int)Math.Pow(2, attempt - 1);
            }

            // Cap at max delay
            delayMs = Math.Min(delayMs, maxDelay);

            // Always add jitter (prevents thundering herd)
            int jitterRange = (int)(delayMs * jitterPercent / 100.0);
            int jitter;
            lock (_randomLock)
            {
                jitter = _random.Next(-jitterRange, jitterRange);
            }

            return Math.Max(100, delayMs + jitter);
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                _httpClient?.Dispose();
                _disposed = true;
            }
        }

        // Response models
        private class InitiateUploadResponse
        {
            [JsonProperty("upload_id")]
            public string UploadId { get; set; }

            [JsonProperty("expires_at")]
            public string ExpiresAt { get; set; }
        }

        private class ChunkUploadResponse
        {
            [JsonProperty("received_hash")]
            public string ReceivedHash { get; set; }

            [JsonProperty("stored")]
            public bool Stored { get; set; }
        }

        private class ChunkExistsResponse
        {
            [JsonProperty("exists")]
            public bool Exists { get; set; }

            [JsonProperty("chunk_hash")]
            public string ChunkHash { get; set; }
        }
    }

    /// <summary>
    /// Upload metadata (no raw keys)
    /// </summary>
    internal class UploadMetadata
    {
        [JsonProperty("session_id")]
        public string SessionId { get; set; }

        [JsonProperty("key_id")]
        public string KeyId { get; set; }

        [JsonProperty("algorithm")]
        public string Algorithm { get; set; }

        [JsonProperty("data_hash_sha256")]
        public string DataHashSHA256 { get; set; }

        [JsonProperty("encrypted_hash_sha256")]
        public string EncryptedHashSHA256 { get; set; }

        [JsonProperty("plaintext_size_bytes")]
        public long PlaintextSizeBytes { get; set; }

        [JsonProperty("encrypted_size_bytes")]
        public long EncryptedSizeBytes { get; set; }

        [JsonProperty("chunk_size")]
        public int ChunkSize { get; set; }

        [JsonProperty("total_chunks")]
        public int TotalChunks { get; set; }

        [JsonProperty("schema_version")]
        public string SchemaVersion { get; set; }

        [JsonProperty("is_incremental")]
        public bool IsIncremental { get; set; }
    }

    /// <summary>
    /// Legacy payload class for backwards compatibility
    /// </summary>
    public class EncryptionPayload
    {
        public string EncryptedData { get; set; }
        public string Key { get; set; }
        public string EncryptedKey { get; set; }
        public bool IsKeyEncrypted { get; set; }
        public string IV { get; set; }
        public string Tag { get; set; }
        public string Algorithm { get; set; }
        public string Version { get; set; }
    }
}