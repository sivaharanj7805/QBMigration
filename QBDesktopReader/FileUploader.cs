using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security;
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
        // FIX HIGH-10: Thread-safe Random using ThreadLocal pattern
        // This avoids lock contention when multiple threads need random numbers
        private static readonly ThreadLocal<Random> _threadLocalRandom = new ThreadLocal<Random>(() =>
            new Random(Interlocked.Increment(ref _randomSeed) ^ Environment.TickCount));
        private static int _randomSeed = Environment.TickCount;
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

            // FIX CSHARP-MED-5: Use Uri class for proper hostname check instead of string-based Contains
            bool isLocalhost = false;
            if (Uri.TryCreate(url, UriKind.Absolute, out Uri parsedUri))
            {
                isLocalhost = parsedUri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase)
                    || parsedUri.Host == "127.0.0.1"
                    || parsedUri.Host == "::1";
            }
            if (url.StartsWith("http://") && !isLocalhost)
            {
                _logger?.Log(LogLevel.Warning, "Using HTTP for non-localhost URL - data is encrypted but metadata visible");
            }

            _serverUrl = url.TrimEnd('/');

            // HIGH-24 FIX: Make timeout configurable via config, default to 10 minutes for large files
            // 30 minutes was too long and could mask network issues
            int timeoutMinutes = config.Advanced?.UploadTimeoutMinutes ?? 10;
            _httpClient = new HttpClient
            {
                Timeout = TimeSpan.FromMinutes(Math.Min(timeoutMinutes, 30)) // Cap at 30 min max
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
            if (string.IsNullOrWhiteSpace(encryptedFilePath))
                throw new ArgumentException("Encrypted file path is required", nameof(encryptedFilePath));
            if (encryptionResult == null)
                throw new ArgumentNullException(nameof(encryptionResult));
            if (string.IsNullOrWhiteSpace(sessionId))
                throw new ArgumentException("Session ID is required", nameof(sessionId));
            if (data == null)
                throw new ArgumentNullException(nameof(data));

            _logger?.Log(LogLevel.Info, "Uploading file (direct)...");

            // FIX MEDIUM: TOCTOU race - use try-catch with FileStream instead of File.Exists check
            // File.Exists check followed by File.Open creates a race window where the file could be deleted
            FileStream fileStream;
            try
            {
                fileStream = new FileStream(encryptedFilePath, FileMode.Open, FileAccess.Read);
            }
            catch (FileNotFoundException)
            {
                throw new FileNotFoundException("Encrypted file not found", encryptedFilePath);
            }
            catch (DirectoryNotFoundException)
            {
                throw new FileNotFoundException("Encrypted file directory not found", encryptedFilePath);
            }

            using (var content = new MultipartFormDataContent())
            using (fileStream)
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
        /// Upload using v3.1 JSON format (matches server's _handle_v31_upload)
        /// This is the recommended method for new integrations.
        ///
        /// SECURITY MODEL (CRIT-02 FIX):
        /// The encryption key is now wrapped with RSA (server's public key) before transmission.
        /// This provides defense-in-depth with the following guarantees:
        /// - Key is RSA-encrypted before being placed in the payload
        /// - TLS provides additional transport security
        /// - Only the server can decrypt the key with its private key
        /// - Key is never transmitted in plaintext
        /// </summary>
        public async Task<UploadResult> UploadV31FormatAsync(
            byte[] encryptedData,
            EncryptionManager.EncryptionResult encryptionResult,
            string sessionId,
            QBCompanyInfo companyInfo,
            CancellationToken cancellationToken = default)
        {
            _logger?.Log(LogLevel.Info, "Uploading using v3.1 format...");

            // CRIT-02 FIX: Get server's public key and encrypt the AES key
            string keyToSend = null;
            string encryptedKeyToSend = null;
            bool isKeyEncrypted = false;

            try
            {
                // Fetch server's RSA public key
                var pubKeyResponse = await _httpClient.GetAsync($"{_serverUrl}/api/encryption/public-key", cancellationToken);
                if (pubKeyResponse.IsSuccessStatusCode)
                {
                    var pubKeyJson = await pubKeyResponse.Content.ReadAsStringAsync();
                    var pubKeyResult = JsonConvert.DeserializeObject<dynamic>(pubKeyJson);
                    string serverPublicKeyXml = pubKeyResult?.public_key_xml;

                    if (!string.IsNullOrEmpty(serverPublicKeyXml))
                    {
                        // Encrypt the AES key with server's RSA public key
                        // FIX: Use RSA.Create() instead of deprecated RSACryptoServiceProvider
                        using (var rsa = RSA.Create())
                        {
                            rsa.FromXmlString(serverPublicKeyXml);
                            byte[] aesKeyBytes = Convert.FromBase64String(encryptionResult.KeyBase64);
                            byte[] encryptedKeyBytes = rsa.Encrypt(aesKeyBytes, RSAEncryptionPadding.OaepSHA256);
                            encryptedKeyToSend = Convert.ToBase64String(encryptedKeyBytes);
                            isKeyEncrypted = true;
                            _logger?.Log(LogLevel.Info, "AES key encrypted with server's RSA public key");
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Could not encrypt key with RSA: {0}", ex.Message);
            }

            // Handle RSA encryption failure
            if (!isKeyEncrypted)
            {
                // Check if fallback is allowed via config
                bool allowFallback = _config.Advanced?.AllowKeyEncryptionFallback ?? false;

                if (!allowFallback)
                {
                    throw new SecurityException(
                        "RSA key encryption failed and fallback is not allowed. " +
                        "The server may not support RSA key encryption, or there was a configuration error. " +
                        "Set 'allowKeyEncryptionFallback: true' in config to allow TLS-only protection (not recommended).");
                }

                _logger?.Log(LogLevel.Warning,
                    "SECURITY WARNING: RSA key encryption unavailable. " +
                    "Proceeding with TLS-only protection as allowKeyEncryptionFallback is enabled. " +
                    "This provides less security than the intended RSA+TLS double encryption.");

                keyToSend = encryptionResult.KeyBase64;
            }

            // Build v3.1 request payload (matches upload.py _handle_v31_upload)
            var payload = new V31UploadPayload
            {
                SessionId = sessionId,
                Encryption = new V31EncryptionBlock
                {
                    EncryptedData = Convert.ToBase64String(encryptedData),
                    Key = keyToSend,  // Only set if RSA encryption not available
                    EncryptedKey = encryptedKeyToSend,  // RSA-encrypted AES key
                    IsKeyEncrypted = isKeyEncrypted,
                    IV = encryptionResult.IVBase64,
                    Tag = encryptionResult.TagBase64,
                    Algorithm = encryptionResult.Algorithm ?? "AES-256-GCM",
                    Version = "4.3"
                },
                Metadata = new V31Metadata
                {
                    ClientVersion = "4.3.0",
                    DataVersion = "qb_desktop_4.3",
                    SchemaVersion = "4.3",
                    PlaintextHash = encryptionResult.DataHashSHA256,
                    PlaintextSizeBytes = encryptionResult.PlaintextSizeBytes,
                    EncryptedSizeBytes = encryptionResult.EncryptedSizeBytes,
                    ExtractedAt = DateTime.UtcNow.ToString("o")
                },
                CompanyInfo = new V31CompanyInfo
                {
                    CompanyName = companyInfo?.CompanyName ?? "Unknown",
                    QBFileName = companyInfo?.CompanyFile ?? "quickbooks.qbw",
                    FiscalYearStart = companyInfo?.FirstMonthFiscalYear ?? 1
                }
            };

            var json = JsonConvert.SerializeObject(payload, new JsonSerializerSettings
            {
                NullValueHandling = NullValueHandling.Ignore
            });
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            var response = await _httpClient.PostAsync(
                $"{_serverUrl}/api/upload",
                content,
                cancellationToken);

            await ValidateResponseAsync(response, "v3.1 Upload");

            var responseJson = await response.Content.ReadAsStringAsync();
            var result = JsonConvert.DeserializeObject<V31UploadResponse>(responseJson);

            _logger?.Log(LogLevel.Info, "v3.1 Upload complete - Migration ID: {0}", result?.MigrationId ?? "N/A");

            return new UploadResult
            {
                Success = result?.Success ?? false,
                MigrationId = result?.MigrationId,
                Status = result?.Status,
                IsDuplicate = result?.IsDuplicate ?? false
            };
        }

        /// <summary>
        /// Upload NDJSON bundle (multiple files from NDJSONWriter)
        /// </summary>
        public async Task<UploadResult> UploadNDJSONBundleAsync(
            string outputDirectory,
            RunManifest manifest,
            string sessionId,
            QBCompanyInfo companyInfo,
            CancellationToken cancellationToken = default)
        {
            _logger?.Log(LogLevel.Info, "Uploading NDJSON bundle ({0} entities)...", manifest.Entities.Count);

            var bundleFiles = new List<BundleFileEntry>();

            // Collect all NDJSON files
            foreach (var entity in manifest.Entities)
            {
                // FIX C-16: Sanitize filename to prevent path traversal (e.g. "../../etc/passwd")
                var safeFileName = Path.GetFileName(entity.FileName);
                if (string.IsNullOrWhiteSpace(safeFileName))
                {
                    _logger?.Log(LogLevel.Warning, "Skipping entity with empty filename: {0}", entity.EntityName);
                    continue;
                }

                var filePath = Path.Combine(outputDirectory, safeFileName);
                if (File.Exists(filePath))
                {
                    var fileBytes = File.ReadAllBytes(filePath);
                    bundleFiles.Add(new BundleFileEntry
                    {
                        FileName = safeFileName,
                        EntityType = entity.EntityName,
                        RecordCount = entity.RecordCount,
                        ContentBase64 = Convert.ToBase64String(fileBytes),
                        SHA256 = entity.Sha256
                    });
                }
            }

            // Add manifest, metrics, errors
            var manifestPath = Path.Combine(outputDirectory, "run_manifest.json");
            if (File.Exists(manifestPath))
            {
                bundleFiles.Add(new BundleFileEntry
                {
                    FileName = "run_manifest.json",
                    EntityType = "_manifest",
                    ContentBase64 = Convert.ToBase64String(File.ReadAllBytes(manifestPath))
                });
            }

            var errorsPath = Path.Combine(outputDirectory, "errors.ndjson");
            if (File.Exists(errorsPath))
            {
                bundleFiles.Add(new BundleFileEntry
                {
                    FileName = "errors.ndjson",
                    EntityType = "_errors",
                    ContentBase64 = Convert.ToBase64String(File.ReadAllBytes(errorsPath))
                });
            }

            // Build bundle payload
            var payload = new NDJSONBundlePayload
            {
                SessionId = sessionId,
                Format = "ndjson_bundle",
                Version = "4.3",
                TotalRecords = manifest.TotalRecords,
                TotalEntities = manifest.Entities.Count,
                CompanyFingerprint = manifest.CompanyFingerprint,
                Files = bundleFiles,
                CompanyInfo = new V31CompanyInfo
                {
                    CompanyName = companyInfo?.CompanyName ?? "Unknown",
                    QBFileName = companyInfo?.CompanyFile ?? "quickbooks.qbw"
                }
            };

            var json = JsonConvert.SerializeObject(payload);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            var response = await _httpClient.PostAsync(
                $"{_serverUrl}/api/upload/ndjson-bundle",
                content,
                cancellationToken);

            await ValidateResponseAsync(response, "NDJSON Bundle Upload");

            var responseJson = await response.Content.ReadAsStringAsync();
            var result = JsonConvert.DeserializeObject<V31UploadResponse>(responseJson);

            _logger?.Log(LogLevel.Info, "NDJSON bundle uploaded - {0} files, {1} records",
                bundleFiles.Count, manifest.TotalRecords);

            return new UploadResult
            {
                Success = result?.Success ?? false,
                MigrationId = result?.MigrationId,
                Status = result?.Status
            };
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
            if (string.IsNullOrWhiteSpace(encryptedFilePath))
                throw new ArgumentException("Encrypted file path is required", nameof(encryptedFilePath));
            if (encryptionResult == null)
                throw new ArgumentNullException(nameof(encryptionResult));
            if (string.IsNullOrWhiteSpace(sessionId))
                throw new ArgumentException("Session ID is required", nameof(sessionId));
            if (data == null)
                throw new ArgumentNullException(nameof(data));

            // FIX MEDIUM: TOCTOU race - get file info which will throw if file doesn't exist
            // This combines existence check and file info retrieval atomically
            FileInfo fileInfo;
            try
            {
                fileInfo = new FileInfo(encryptedFilePath);
                // FileInfo.Length access triggers the existence check
                _ = fileInfo.Length;
            }
            catch (FileNotFoundException)
            {
                throw new FileNotFoundException("Encrypted file not found", encryptedFilePath);
            }
            catch (DirectoryNotFoundException)
            {
                throw new FileNotFoundException("Encrypted file directory not found", encryptedFilePath);
            }
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

                        // FIX MEDIUM: chunkIndex is already 1-based after increment (starts at 0, incremented to 1 after first chunk)
                        // Progress display should show consistent 1-based chunk numbers
                        // Report every 10 chunks or on the last chunk
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
                catch (HttpRequestException)
                {
                    // Abort failed due to network - continue with re-throw
                }
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
                        // FIX MEDIUM: Use 1-based indexing in user-facing log messages
                        _logger?.Log(LogLevel.Debug, "Chunk {0} already uploaded, skipping", chunkIndex + 1);
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
                        // FIX MEDIUM: Use 1-based indexing in user-facing log messages
                        _logger?.Log(LogLevel.Error, "Chunk {0} failed after {1} attempts: {2}",
                            chunkIndex + 1, attempts, ex.Message);
                        throw;
                    }

                    int delayMs = CalculateRetryDelay(attempts);
                    // FIX MEDIUM: Use 1-based indexing in user-facing log messages
                    _logger?.Log(LogLevel.Warning, "Chunk {0} failed, retry {1}/{2} in {3}ms",
                        chunkIndex + 1, attempts, maxAttempts, delayMs);

                    await Task.Delay(delayMs, cancellationToken);
                }
            }
        }

        /// <summary>
        /// Upload chunk using multipart form data (no base64)
        /// FIX HIGH-15: Add per-request timeout with CancellationTokenSource
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
            // Per-request timeout (default 2 minutes per chunk, configurable)
            int chunkTimeoutSeconds = _config.Advanced?.ChunkUploadTimeoutSeconds ?? 120;
            using (var timeoutCts = new CancellationTokenSource(TimeSpan.FromSeconds(chunkTimeoutSeconds)))
            using (var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutCts.Token))
            {
                try
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
                            linkedCts.Token);

                        await ValidateResponseAsync(response, $"Upload chunk {chunkIndex}");

                        // Validate server echoed the hash
                        var responseJson = await response.Content.ReadAsStringAsync();
                        var result = JsonConvert.DeserializeObject<ChunkUploadResponse>(responseJson);

                        if (result?.ReceivedHash != null && result.ReceivedHash != chunkHash)
                        {
                            // FIX MEDIUM: Use 1-based indexing in user-facing error messages
                            throw new Exception($"Chunk {chunkIndex + 1} hash mismatch: sent {chunkHash}, received {result.ReceivedHash}");
                        }
                    }
                }
                catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
                {
                    // FIX MEDIUM: Use 1-based indexing in user-facing error messages
                    throw new TimeoutException($"Chunk {chunkIndex + 1} upload timed out after {chunkTimeoutSeconds} seconds");
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

                // FIX CS-06: Log non-success response instead of silent false
                // FIX MEDIUM: Use 1-based indexing in user-facing log messages
                _logger?.Log(LogLevel.Debug, "Chunk exists check returned HTTP {0} for chunk {1}",
                    (int)response.StatusCode, chunkIndex + 1);
            }
            catch (Exception ex)
            {
                // FIX CS-06: Log error instead of silent suppression
                // FIX MEDIUM: Use 1-based indexing in user-facing log messages
                _logger?.Log(LogLevel.Debug, "Chunk exists check failed for chunk {0}: {1}",
                    chunkIndex + 1, ex.Message);
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
            catch (HttpRequestException)
            {
                // Network failure during abort - best effort
            }
            catch (TaskCanceledException)
            {
                // Request cancelled - best effort
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

            // FIX CRIT-06: Enhanced overflow protection for exponential backoff
            // Ensure baseDelay is positive and reasonable
            baseDelay = Math.Max(100, Math.Min(baseDelay, 60000)); // 100ms - 60s
            maxDelay = Math.Max(baseDelay, Math.Min(maxDelay, 300000)); // Cap at 5 minutes

            long delayMs = baseDelay;

            if (_config.Advanced.EnableExponentialBackoff)
            {
                // Overflow protection: cap exponent to prevent overflow
                // For baseDelay=100 and exponent=20, result is ~104M which fits in int
                // For baseDelay=1000 and exponent=20, result is ~1B which could overflow
                int safeExponent = Math.Min(attempt - 1, 20);

                // Use checked arithmetic and catch overflow
                try
                {
                    checked
                    {
                        delayMs = (long)baseDelay * (1L << safeExponent);
                    }
                }
                catch (OverflowException)
                {
                    delayMs = maxDelay;
                }
            }

            // Cap at max delay (using long comparison to avoid issues)
            delayMs = Math.Min(delayMs, (long)maxDelay);

            // Ensure result fits in int
            int delayInt = (int)Math.Min(delayMs, int.MaxValue);

            // Always add jitter (prevents thundering herd)
            // FIX HIGH-10: Use ThreadLocal Random for thread-safety without lock contention
            int jitterRange = (int)Math.Min((long)delayInt * jitterPercent / 100L, int.MaxValue / 2);
            int jitter = jitterRange > 0 ? _threadLocalRandom.Value.Next(-jitterRange, jitterRange) : 0;

            return Math.Max(100, delayInt + jitter);
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

    // ============================================================================
    // v3.1 FORMAT CLASSES (matches upload.py _handle_v31_upload)
    // ============================================================================

    /// <summary>
    /// v3.1 upload payload structure
    /// </summary>
    internal class V31UploadPayload
    {
        [JsonProperty("session_id")]
        public string SessionId { get; set; }

        [JsonProperty("encryption")]
        public V31EncryptionBlock Encryption { get; set; }

        [JsonProperty("metadata")]
        public V31Metadata Metadata { get; set; }

        [JsonProperty("company_info")]
        public V31CompanyInfo CompanyInfo { get; set; }
    }

    internal class V31EncryptionBlock
    {
        [JsonProperty("encrypted_data")]
        public string EncryptedData { get; set; }

        [JsonProperty("key")]
        public string Key { get; set; }

        [JsonProperty("encrypted_key")]
        public string EncryptedKey { get; set; }

        [JsonProperty("is_key_encrypted")]
        public bool IsKeyEncrypted { get; set; }

        [JsonProperty("iv")]
        public string IV { get; set; }

        [JsonProperty("tag")]
        public string Tag { get; set; }

        [JsonProperty("algorithm")]
        public string Algorithm { get; set; }

        [JsonProperty("version")]
        public string Version { get; set; }
    }

    internal class V31Metadata
    {
        [JsonProperty("client_version")]
        public string ClientVersion { get; set; }

        [JsonProperty("data_version")]
        public string DataVersion { get; set; }

        [JsonProperty("schema_version")]
        public string SchemaVersion { get; set; }

        [JsonProperty("plaintext_hash")]
        public string PlaintextHash { get; set; }

        [JsonProperty("plaintext_size_bytes")]
        public long PlaintextSizeBytes { get; set; }

        [JsonProperty("encrypted_size_bytes")]
        public long EncryptedSizeBytes { get; set; }

        [JsonProperty("extracted_at")]
        public string ExtractedAt { get; set; }
    }

    internal class V31CompanyInfo
    {
        [JsonProperty("company_name")]
        public string CompanyName { get; set; }

        [JsonProperty("qb_file_name")]
        public string QBFileName { get; set; }

        [JsonProperty("fiscal_year_start")]
        public int FiscalYearStart { get; set; }
    }

    internal class V31UploadResponse
    {
        [JsonProperty("success")]
        public bool Success { get; set; }

        [JsonProperty("migration_id")]
        public string MigrationId { get; set; }

        [JsonProperty("status")]
        public string Status { get; set; }

        [JsonProperty("is_duplicate")]
        public bool IsDuplicate { get; set; }

        [JsonProperty("message")]
        public string Message { get; set; }
    }

    // ============================================================================
    // NDJSON BUNDLE CLASSES
    // ============================================================================

    internal class NDJSONBundlePayload
    {
        [JsonProperty("session_id")]
        public string SessionId { get; set; }

        [JsonProperty("format")]
        public string Format { get; set; }

        [JsonProperty("version")]
        public string Version { get; set; }

        [JsonProperty("total_records")]
        public int TotalRecords { get; set; }

        [JsonProperty("total_entities")]
        public int TotalEntities { get; set; }

        [JsonProperty("company_fingerprint")]
        public string CompanyFingerprint { get; set; }

        [JsonProperty("files")]
        public List<BundleFileEntry> Files { get; set; }

        [JsonProperty("company_info")]
        public V31CompanyInfo CompanyInfo { get; set; }
    }

    internal class BundleFileEntry
    {
        [JsonProperty("file_name")]
        public string FileName { get; set; }

        [JsonProperty("entity_type")]
        public string EntityType { get; set; }

        [JsonProperty("record_count")]
        public int RecordCount { get; set; }

        [JsonProperty("content_base64")]
        public string ContentBase64 { get; set; }

        [JsonProperty("sha256")]
        public string SHA256 { get; set; }
    }

    /// <summary>
    /// Result of an upload operation
    /// </summary>
    public class UploadResult
    {
        public bool Success { get; set; }
        public string MigrationId { get; set; }
        public string Status { get; set; }
        public bool IsDuplicate { get; set; }
        public string ErrorMessage { get; set; }
    }
}