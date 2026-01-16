using System;
using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Direct S3 uploader using pre-signed URLs
    /// Enables streaming upload directly to AWS S3 without going through the server
    /// </summary>
    public class S3DirectUploader : IDisposable
    {
        private readonly HttpClient _httpClient;
        private readonly string _serverUrl;
        private readonly string _authToken;
        private readonly IRedactingLogger _logger;
        private const int CHUNK_SIZE = 5 * 1024 * 1024; // 5MB for multipart
        private bool _disposed;

        public S3DirectUploader(string serverUrl, string authToken, IRedactingLogger logger = null)
        {
            _serverUrl = serverUrl?.TrimEnd('/') ?? throw new ArgumentNullException(nameof(serverUrl));
            _authToken = authToken;
            _logger = logger;
            
            _httpClient = new HttpClient
            {
                Timeout = TimeSpan.FromMinutes(30)
            };
            
            if (!string.IsNullOrEmpty(authToken))
            {
                _httpClient.DefaultRequestHeaders.Add("Authorization", $"Bearer {authToken}");
            }
        }

        /// <summary>
        /// Upload a file directly to S3 using pre-signed URL
        /// </summary>
        public async Task<UploadResult> UploadAsync(
            string filePath,
            string sessionId,
            IProgress<UploadProgress> progress = null,
            CancellationToken cancellationToken = default)
        {
            var fileInfo = new FileInfo(filePath);
            if (!fileInfo.Exists)
            {
                throw new FileNotFoundException("File not found", filePath);
            }

            // Calculate hash
            string fileHash = await CalculateHashAsync(filePath, cancellationToken);
            _logger?.Log(LogLevel.Info, "File hash: {0}", fileHash.Substring(0, 16) + "...");

            // Use multipart for files > 100MB
            if (fileInfo.Length > 100 * 1024 * 1024)
            {
                return await UploadMultipartAsync(filePath, sessionId, fileHash, progress, cancellationToken);
            }

            // Get pre-signed URL from server
            var presignedResponse = await GetPresignedUrlAsync(sessionId, fileInfo.Name, fileInfo.Length, fileHash);
            
            if (presignedResponse == null)
            {
                return new UploadResult { Success = false, ErrorMessage = "Failed to get pre-signed URL" };
            }

            string uploadUrl = presignedResponse["upload_url"]?.ToString();
            string migrationId = presignedResponse["migration_id"]?.ToString();

            // Upload directly to S3
            progress?.Report(new UploadProgress { Phase = "Uploading", PercentComplete = 0 });

            using (var fileStream = new FileStream(filePath, FileMode.Open, FileAccess.Read))
            {
                var content = new StreamContent(fileStream);
                content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream");

                var uploadRequest = new HttpRequestMessage(HttpMethod.Put, uploadUrl)
                {
                    Content = content
                };

                var response = await _httpClient.SendAsync(uploadRequest, cancellationToken);

                if (!response.IsSuccessStatusCode)
                {
                    string error = await response.Content.ReadAsStringAsync();
                    return new UploadResult 
                    { 
                        Success = false, 
                        ErrorMessage = $"S3 upload failed: {response.StatusCode} - {error}" 
                    };
                }
            }

            progress?.Report(new UploadProgress { Phase = "Completing", PercentComplete = 95 });

            // Notify server that upload is complete
            await CompleteUploadAsync(migrationId, fileHash);

            progress?.Report(new UploadProgress { Phase = "Complete", PercentComplete = 100 });

            return new UploadResult
            {
                Success = true,
                MigrationId = migrationId,
                Status = "uploaded"
            };
        }

        /// <summary>
        /// Upload large file using multipart upload
        /// </summary>
        private async Task<UploadResult> UploadMultipartAsync(
            string filePath,
            string sessionId,
            string fileHash,
            IProgress<UploadProgress> progress,
            CancellationToken cancellationToken)
        {
            var fileInfo = new FileInfo(filePath);
            
            // Initialize multipart upload
            var initResponse = await InitMultipartUploadAsync(sessionId, fileInfo.Name, fileInfo.Length);
            string uploadId = initResponse["upload_id"]?.ToString();
            string migrationId = initResponse["migration_id"]?.ToString();
            string s3Key = initResponse["s3_key"]?.ToString();

            var parts = new JArray();
            int partNumber = 1;
            long totalBytes = fileInfo.Length;
            long uploadedBytes = 0;

            using (var fileStream = new FileStream(filePath, FileMode.Open, FileAccess.Read))
            {
                byte[] buffer = new byte[CHUNK_SIZE];
                int bytesRead;

                while ((bytesRead = await fileStream.ReadAsync(buffer, 0, buffer.Length, cancellationToken)) > 0)
                {
                    // Get part upload URL
                    var partUrlResponse = await GetPartUploadUrlAsync(uploadId, partNumber, s3Key);
                    string partUrl = partUrlResponse["upload_url"]?.ToString();

                    // Upload part
                    using (var partContent = new ByteArrayContent(buffer, 0, bytesRead))
                    {
                        var partRequest = new HttpRequestMessage(HttpMethod.Put, partUrl)
                        {
                            Content = partContent
                        };

                        var partResponse = await _httpClient.SendAsync(partRequest, cancellationToken);

                        if (!partResponse.IsSuccessStatusCode)
                        {
                            throw new Exception($"Part {partNumber} upload failed");
                        }

                        // Get ETag from response
                        string etag = partResponse.Headers.ETag?.Tag ?? $"\"{partNumber}\"";
                        parts.Add(new JObject
                        {
                            ["PartNumber"] = partNumber,
                            ["ETag"] = etag.Trim('"')
                        });
                    }

                    uploadedBytes += bytesRead;
                    int percentComplete = (int)((uploadedBytes * 100) / totalBytes);
                    progress?.Report(new UploadProgress 
                    { 
                        Phase = "Uploading", 
                        PercentComplete = percentComplete,
                        BytesUploaded = uploadedBytes,
                        TotalBytes = totalBytes
                    });

                    partNumber++;
                }
            }

            // Complete multipart upload
            await CompleteMultipartUploadAsync(uploadId, s3Key, parts, migrationId);

            progress?.Report(new UploadProgress { Phase = "Complete", PercentComplete = 100 });

            return new UploadResult
            {
                Success = true,
                MigrationId = migrationId,
                Status = "uploaded"
            };
        }

        private async Task<JObject> GetPresignedUrlAsync(string sessionId, string fileName, long fileSize, string hash)
        {
            var request = new JObject
            {
                ["session_id"] = sessionId,
                ["file_name"] = fileName,
                ["file_size"] = fileSize,
                ["sha256_hash"] = hash,
                ["content_type"] = "application/octet-stream"
            };

            var response = await _httpClient.PostAsync(
                $"{_serverUrl}/api/upload/presigned-url",
                new StringContent(request.ToString(), Encoding.UTF8, "application/json"));

            var content = await response.Content.ReadAsStringAsync();
            return JObject.Parse(content);
        }

        private async Task<JObject> InitMultipartUploadAsync(string sessionId, string fileName, long fileSize)
        {
            var request = new JObject
            {
                ["session_id"] = sessionId,
                ["file_name"] = fileName,
                ["file_size"] = fileSize
            };

            var response = await _httpClient.PostAsync(
                $"{_serverUrl}/api/upload/multipart/init",
                new StringContent(request.ToString(), Encoding.UTF8, "application/json"));

            var content = await response.Content.ReadAsStringAsync();
            return JObject.Parse(content);
        }

        private async Task<JObject> GetPartUploadUrlAsync(string uploadId, int partNumber, string s3Key)
        {
            var request = new JObject
            {
                ["upload_id"] = uploadId,
                ["part_number"] = partNumber,
                ["s3_key"] = s3Key
            };

            var response = await _httpClient.PostAsync(
                $"{_serverUrl}/api/upload/multipart/part-url",
                new StringContent(request.ToString(), Encoding.UTF8, "application/json"));

            var content = await response.Content.ReadAsStringAsync();
            return JObject.Parse(content);
        }

        private async Task CompleteMultipartUploadAsync(string uploadId, string s3Key, JArray parts, string migrationId)
        {
            var request = new JObject
            {
                ["upload_id"] = uploadId,
                ["s3_key"] = s3Key,
                ["parts"] = parts,
                ["migration_id"] = migrationId
            };

            await _httpClient.PostAsync(
                $"{_serverUrl}/api/upload/multipart/complete",
                new StringContent(request.ToString(), Encoding.UTF8, "application/json"));
        }

        private async Task CompleteUploadAsync(string migrationId, string hash)
        {
            var request = new JObject
            {
                ["migration_id"] = migrationId,
                ["sha256_hash"] = hash
            };

            await _httpClient.PostAsync(
                $"{_serverUrl}/api/upload/complete",
                new StringContent(request.ToString(), Encoding.UTF8, "application/json"));
        }

        private static async Task<string> CalculateHashAsync(string filePath, CancellationToken cancellationToken)
        {
            using (var sha256 = SHA256.Create())
            using (var stream = new FileStream(filePath, FileMode.Open, FileAccess.Read, FileShare.Read, 8192, true))
            {
                var hash = await Task.Run(() => sha256.ComputeHash(stream), cancellationToken);
                return BitConverter.ToString(hash).Replace("-", "").ToLowerInvariant();
            }
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            _httpClient?.Dispose();
        }
    }

    public class UploadProgress
    {
        public string Phase { get; set; }
        public int PercentComplete { get; set; }
        public long BytesUploaded { get; set; }
        public long TotalBytes { get; set; }
    }
}
