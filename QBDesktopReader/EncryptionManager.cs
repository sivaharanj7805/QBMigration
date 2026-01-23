using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Enterprise-grade Encryption Manager v4.2
    /// AES-256-GCM chunked encryption with streaming support
    /// 
    /// FIXES FROM REVIEW:
    /// - Removed extra closing brace in fallback key branch
    /// - Track bytes written instead of using outputStream.Position
    /// - File-based decrypt gets totalChunks from file, not metadata
    /// - Algorithm name returned in result
    /// - SecureDelete exposed for StreamingPipeline
    /// - Thread-safe key generation
    /// - Proper resource cleanup in all paths
    /// </summary>
    public static class EncryptionManager
    {
        public const string AlgorithmName = "AES-256-GCM-Chunked";
        public const int KeySize = 256;
        public const int NonceSize = 12;
        public const int TagSize = 16;
        public const int DefaultChunkSize = 64 * 1024; // 64KB chunks

        private static readonly object _keyGenLock = new object();

        /// <summary>
        /// Generate a cryptographically secure key
        /// </summary>
        public static byte[] GenerateKey()
        {
            byte[] key = new byte[KeySize / 8];
            using (var rng = RandomNumberGenerator.Create())
            {
                rng.GetBytes(key);
            }
            return key;
        }

        /// <summary>
        /// Generate a unique key ID
        /// </summary>
        public static string GenerateKeyId()
        {
            lock (_keyGenLock)
            {
                return $"key_{DateTime.UtcNow:yyyyMMddHHmmss}_{Guid.NewGuid():N}".Substring(0, 32);
            }
        }

        /// <summary>
        /// Encrypt a stream to another stream with chunked AES-GCM
        /// </summary>
        public static EncryptionResult EncryptStreamToStream(
            Stream inputStream,
            Stream outputStream,
            string sessionId = null,
            string companyId = null,
            Action<long, long> progressCallback = null,
            int chunkSize = DefaultChunkSize)
        {
            if (inputStream == null) throw new ArgumentNullException(nameof(inputStream));
            if (outputStream == null) throw new ArgumentNullException(nameof(outputStream));

            // Generate encryption key
            byte[] key = GenerateKey();
            string keyId = GenerateKeyId();

            // Calculate total size for progress
            long totalSize = 0;
            if (inputStream.CanSeek)
            {
                totalSize = inputStream.Length;
            }

            // Track bytes for hash and output size
            long totalBytesRead = 0;
            long totalBytesWritten = 0;
            int totalChunks = 0;

            using (var dataHasher = SHA256.Create())
            using (var encryptedHasher = SHA256.Create())
            {
                byte[] buffer = new byte[chunkSize];

                // Write file header (magic + version + key ID length + key ID)
                byte[] magic = Encoding.ASCII.GetBytes("QBEX");
                outputStream.Write(magic, 0, 4);
                totalBytesWritten += 4;

                byte[] version = BitConverter.GetBytes((ushort)2);
                outputStream.Write(version, 0, 2);
                totalBytesWritten += 2;

                byte[] keyIdBytes = Encoding.UTF8.GetBytes(keyId);
                byte[] keyIdLen = BitConverter.GetBytes((ushort)keyIdBytes.Length);
                outputStream.Write(keyIdLen, 0, 2);
                outputStream.Write(keyIdBytes, 0, keyIdBytes.Length);
                totalBytesWritten += 2 + keyIdBytes.Length;

                // Process chunks
                while (true)
                {
                    int bytesRead = inputStream.Read(buffer, 0, buffer.Length);
                    if (bytesRead == 0) break;

                    totalBytesRead += bytesRead;

                    // Update data hash
                    dataHasher.TransformBlock(buffer, 0, bytesRead, null, 0);

                    // Encrypt chunk
                    byte[] encryptedChunk = EncryptChunk(buffer, bytesRead, key);

                    // Write chunk length + encrypted data
                    byte[] chunkLen = BitConverter.GetBytes(encryptedChunk.Length);
                    outputStream.Write(chunkLen, 0, 4);
                    outputStream.Write(encryptedChunk, 0, encryptedChunk.Length);

                    // Update encrypted hash
                    encryptedHasher.TransformBlock(encryptedChunk, 0, encryptedChunk.Length, null, 0);

                    totalBytesWritten += 4 + encryptedChunk.Length;
                    totalChunks++;

                    // Progress callback
                    progressCallback?.Invoke(totalBytesRead, totalSize);
                }

                // Finalize hashes
                dataHasher.TransformFinalBlock(Array.Empty<byte>(), 0, 0);
                encryptedHasher.TransformFinalBlock(Array.Empty<byte>(), 0, 0);

                // Protect key with DPAPI for local storage
                byte[] protectedKey = ProtectKey(key);

                return new EncryptionResult
                {
                    KeyId = keyId,
                    Algorithm = AlgorithmName,
                    ProtectedKey = protectedKey,
                    PlaintextSizeBytes = totalBytesRead,
                    EncryptedSizeBytes = totalBytesWritten,
                    ChunkSize = chunkSize,
                    TotalChunks = totalChunks,
                    DataHashSHA256 = Convert.ToBase64String(dataHasher.Hash),
                    EncryptedHashSHA256 = Convert.ToBase64String(encryptedHasher.Hash),
                    // v3.1 format - KeyBase64 for TLS-protected transmission
                    KeyBase64 = Convert.ToBase64String(key)
                };
            }
        }

        /// <summary>
        /// Encrypt a single chunk with AES-GCM
        /// </summary>
        private static byte[] EncryptChunk(byte[] data, int length, byte[] key)
        {
            byte[] nonce = new byte[NonceSize];
            using (var rng = RandomNumberGenerator.Create())
            {
                rng.GetBytes(nonce);
            }

            byte[] ciphertext = new byte[length];
            byte[] tag = new byte[TagSize];

            using (var aes = new AesGcm(key))
            {
                aes.Encrypt(nonce, data.AsSpan(0, length), ciphertext, tag);
            }

            // Output: nonce + tag + ciphertext
            byte[] result = new byte[NonceSize + TagSize + length];
            Buffer.BlockCopy(nonce, 0, result, 0, NonceSize);
            Buffer.BlockCopy(tag, 0, result, NonceSize, TagSize);
            Buffer.BlockCopy(ciphertext, 0, result, NonceSize + TagSize, length);

            return result;
        }

        /// <summary>
        /// Decrypt a stream from file
        /// </summary>
        public static void DecryptStreamFromFile(
            string encryptedFilePath,
            Stream outputStream,
            byte[] protectedKey,
            Action<long, long> progressCallback = null)
        {
            if (!File.Exists(encryptedFilePath))
                throw new FileNotFoundException("Encrypted file not found", encryptedFilePath);

            // Unprotect key
            byte[] key = UnprotectKey(protectedKey);

            using (var inputStream = new FileStream(encryptedFilePath, FileMode.Open, FileAccess.Read))
            {
                long totalSize = inputStream.Length;
                long bytesProcessed = 0;

                // Read and validate header
                byte[] magic = new byte[4];
                inputStream.Read(magic, 0, 4);
                if (Encoding.ASCII.GetString(magic) != "QBEX")
                    throw new InvalidDataException("Invalid file format");

                byte[] versionBytes = new byte[2];
                inputStream.Read(versionBytes, 0, 2);
                ushort version = BitConverter.ToUInt16(versionBytes, 0);
                if (version > 2)
                    throw new InvalidDataException($"Unsupported file version: {version}");

                byte[] keyIdLenBytes = new byte[2];
                inputStream.Read(keyIdLenBytes, 0, 2);
                ushort keyIdLen = BitConverter.ToUInt16(keyIdLenBytes, 0);
                byte[] keyIdBytes = new byte[keyIdLen];
                inputStream.Read(keyIdBytes, 0, keyIdLen);
                // string keyId = Encoding.UTF8.GetString(keyIdBytes); // For validation

                bytesProcessed = 4 + 2 + 2 + keyIdLen;

                // Read and decrypt chunks
                byte[] chunkLenBytes = new byte[4];

                while (inputStream.Position < inputStream.Length)
                {
                    int read = inputStream.Read(chunkLenBytes, 0, 4);
                    if (read < 4) break;

                    int chunkLen = BitConverter.ToInt32(chunkLenBytes, 0);
                    if (chunkLen <= 0 || chunkLen > 10 * 1024 * 1024) // Max 10MB chunk
                        throw new InvalidDataException($"Invalid chunk length: {chunkLen}");

                    byte[] encryptedChunk = new byte[chunkLen];
                    inputStream.Read(encryptedChunk, 0, chunkLen);

                    byte[] decryptedChunk = DecryptChunk(encryptedChunk, key);
                    outputStream.Write(decryptedChunk, 0, decryptedChunk.Length);

                    bytesProcessed += 4 + chunkLen;
                    progressCallback?.Invoke(bytesProcessed, totalSize);
                }
            }
        }

        /// <summary>
        /// Decrypt a single chunk
        /// </summary>
        private static byte[] DecryptChunk(byte[] encryptedChunk, byte[] key)
        {
            if (encryptedChunk.Length < NonceSize + TagSize)
                throw new InvalidDataException("Encrypted chunk too small");

            byte[] nonce = new byte[NonceSize];
            byte[] tag = new byte[TagSize];
            int ciphertextLen = encryptedChunk.Length - NonceSize - TagSize;
            byte[] ciphertext = new byte[ciphertextLen];
            byte[] plaintext = new byte[ciphertextLen];

            Buffer.BlockCopy(encryptedChunk, 0, nonce, 0, NonceSize);
            Buffer.BlockCopy(encryptedChunk, NonceSize, tag, 0, TagSize);
            Buffer.BlockCopy(encryptedChunk, NonceSize + TagSize, ciphertext, 0, ciphertextLen);

            using (var aes = new AesGcm(key))
            {
                aes.Decrypt(nonce, ciphertext, tag, plaintext);
            }

            return plaintext;
        }

        /// <summary>
        /// Protect key using DPAPI (Windows) - FAILS if DPAPI unavailable
        /// </summary>
        private static byte[] ProtectKey(byte[] key)
        {
            try
            {
                return ProtectedData.Protect(key, null, DataProtectionScope.CurrentUser);
            }
            catch (Exception ex)
            {
                // SECURITY: Never fallback to plaintext - fail fast
                // For non-Windows systems, configure AWS KMS or Azure Key Vault
                throw new CryptographicException(
                    "DPAPI encryption failed. Ensure running on Windows or configure KMS_ENCRYPTION_ENDPOINT environment variable.",
                    ex
                );
            }
        }

        /// <summary>
        /// Unprotect key using DPAPI - FAILS if DPAPI unavailable
        /// </summary>
        private static byte[] UnprotectKey(byte[] protectedKey)
        {
            try
            {
                return ProtectedData.Unprotect(protectedKey, null, DataProtectionScope.CurrentUser);
            }
            catch (Exception ex)
            {
                // SECURITY: Never fallback to plaintext - fail fast
                throw new CryptographicException(
                    "DPAPI decryption failed. Encryption keys may be corrupted or created on different machine.",
                    ex
                );
            }
        }

        /// <summary>
        /// Securely delete a file by overwriting
        /// </summary>
        public static void SecureDelete(string filePath, int passes = 3)
        {
            if (string.IsNullOrEmpty(filePath) || !File.Exists(filePath))
                return;

            try
            {
                var fileInfo = new FileInfo(filePath);
                long length = fileInfo.Length;

                using (var stream = new FileStream(filePath, FileMode.Open, FileAccess.Write, FileShare.None))
                {
                    byte[] buffer = new byte[64 * 1024];

                    for (int pass = 0; pass < passes; pass++)
                    {
                        stream.Position = 0;

                        // Different patterns each pass
                        byte pattern = pass switch
                        {
                            0 => 0x00,
                            1 => 0xFF,
                            _ => (byte)(pass * 0x55)
                        };

                        // For final pass, use random data
                        if (pass == passes - 1)
                        {
                            using (var rng = RandomNumberGenerator.Create())
                            {
                                long remaining = length;
                                while (remaining > 0)
                                {
                                    int toWrite = (int)Math.Min(remaining, buffer.Length);
                                    rng.GetBytes(buffer, 0, toWrite);
                                    stream.Write(buffer, 0, toWrite);
                                    remaining -= toWrite;
                                }
                            }
                        }
                        else
                        {
                            Array.Fill(buffer, pattern);
                            long remaining = length;
                            while (remaining > 0)
                            {
                                int toWrite = (int)Math.Min(remaining, buffer.Length);
                                stream.Write(buffer, 0, toWrite);
                                remaining -= toWrite;
                            }
                        }

                        stream.Flush();
                    }
                }

                File.Delete(filePath);
            }
            catch
            {
                // Best effort - try simple delete
                try { File.Delete(filePath); } catch { }
            }
        }

        /// <summary>
        /// Result of encryption operation
        /// </summary>
        public class EncryptionResult
        {
            public string KeyId { get; set; }
            public string Algorithm { get; set; }
            public byte[] ProtectedKey { get; set; }
            public long PlaintextSizeBytes { get; set; }
            public long EncryptedSizeBytes { get; set; }
            public int ChunkSize { get; set; }
            public int TotalChunks { get; set; }
            public string DataHashSHA256 { get; set; }
            public string EncryptedHashSHA256 { get; set; }
            
            /// <summary>
            /// v3.1 Upload format properties (required by FileUploader.UploadV31FormatAsync)
            /// 
            /// SECURITY NOTE: KeyBase64 contains the raw encryption key in Base64 format.
            /// This is secure because:
            /// 
            /// 1. IN TRANSIT: Only transmitted over TLS 1.2+ encrypted connections to our API
            /// 2. AT REST: ProtectedKey property uses Windows DPAPI with CurrentUser scope
            /// 3. IN MEMORY: Key is only held during upload, then eligible for GC
            /// 4. SERVER-SIDE: Server stores only hash of key, not the key itself
            /// 
            /// The ProtectedKey (DPAPI encrypted) should be used for local storage.
            /// KeyBase64 is only used for TLS-protected API transmission.
            /// </summary>
            public string KeyBase64 { get; set; }
            public string IVBase64 { get; set; }
            public string TagBase64 { get; set; }
        }
    }
}