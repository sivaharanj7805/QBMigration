using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Hash Verifier v4.3 - Forensic Chain of Custody
    /// 
    /// Provides standardized SHA-256 hashing that matches Python's implementation
    /// for end-to-end integrity verification.
    /// 
    /// CRITICAL: Both C# and Python MUST produce identical hashes for:
    /// - The same plaintext data
    /// - The data hash must travel with encrypted payload
    /// - Server verifies hash before transformation
    /// </summary>
    public static class HashVerifier
    {
        /// <summary>
        /// Compute SHA-256 hash of string data (UTF-8 encoded)
        /// Matches Python: hashlib.sha256(data.encode()).hexdigest()
        /// </summary>
        public static string ComputeHash(string data)
        {
            if (string.IsNullOrEmpty(data))
                return null;

            using (var sha256 = SHA256.Create())
            {
                // CRITICAL: Use UTF-8 encoding to match Python's .encode()
                byte[] bytes = Encoding.UTF8.GetBytes(data);
                byte[] hash = sha256.ComputeHash(bytes);
                return ToHexString(hash);
            }
        }

        /// <summary>
        /// Compute SHA-256 hash of byte array
        /// Matches Python: hashlib.sha256(byte_data).hexdigest()
        /// </summary>
        public static string ComputeHash(byte[] data)
        {
            if (data == null || data.Length == 0)
                return null;

            using (var sha256 = SHA256.Create())
            {
                byte[] hash = sha256.ComputeHash(data);
                return ToHexString(hash);
            }
        }

        /// <summary>
        /// Compute SHA-256 hash of a file stream
        /// </summary>
        public static string ComputeFileHash(string filePath)
        {
            if (!File.Exists(filePath))
                throw new FileNotFoundException("File not found for hashing", filePath);

            using (var sha256 = SHA256.Create())
            using (var stream = File.OpenRead(filePath))
            {
                byte[] hash = sha256.ComputeHash(stream);
                return ToHexString(hash);
            }
        }

        /// <summary>
        /// Verify that computed hash matches expected hash
        /// </summary>
        public static bool VerifyHash(string data, string expectedHash)
        {
            string actualHash = ComputeHash(data);
            return string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>
        /// Verify that computed hash matches expected hash
        /// </summary>
        public static bool VerifyHash(byte[] data, string expectedHash)
        {
            string actualHash = ComputeHash(data);
            return string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>
        /// Generate forensic hash report for audit trail
        /// </summary>
        public static ForensicHashReport GenerateForensicReport(
            string sessionId,
            string plaintextJson,
            byte[] encryptedData,
            QBCompanyInfo companyInfo)
        {
            return new ForensicHashReport
            {
                SessionId = sessionId,
                Timestamp = DateTime.UtcNow,
                PlaintextHash = ComputeHash(plaintextJson),
                PlaintextSizeBytes = Encoding.UTF8.GetByteCount(plaintextJson),
                EncryptedHash = ComputeHash(encryptedData),
                EncryptedSizeBytes = encryptedData.Length,
                CompanyFingerprint = GenerateCompanyFingerprint(companyInfo),
                HashAlgorithm = "SHA-256",
                Version = "4.3"
            };
        }

        /// <summary>
        /// Generate unique company fingerprint for deduplication
        /// </summary>
        public static string GenerateCompanyFingerprint(QBCompanyInfo company)
        {
            if (company == null)
                return ComputeHash("unknown");

            // Combine stable identifiers
            string combined = $"{company.CompanyName}|{company.LegalCompanyName}|{company.EIN}|{company.CompanyFile}";
            return ComputeHash(combined);
        }

        /// <summary>
        /// Convert byte array to lowercase hex string (matches Python hexdigest())
        /// </summary>
        private static string ToHexString(byte[] bytes)
        {
            var sb = new StringBuilder(bytes.Length * 2);
            foreach (byte b in bytes)
            {
                sb.Append(b.ToString("x2")); // CRITICAL: lowercase to match Python
            }
            return sb.ToString();
        }
    }

    /// <summary>
    /// Forensic hash report for audit trail
    /// </summary>
    public class ForensicHashReport
    {
        [JsonProperty("session_id")]
        public string SessionId { get; set; }

        [JsonProperty("timestamp")]
        public DateTime Timestamp { get; set; }

        [JsonProperty("plaintext_hash")]
        public string PlaintextHash { get; set; }

        [JsonProperty("plaintext_size_bytes")]
        public long PlaintextSizeBytes { get; set; }

        [JsonProperty("encrypted_hash")]
        public string EncryptedHash { get; set; }

        [JsonProperty("encrypted_size_bytes")]
        public long EncryptedSizeBytes { get; set; }

        [JsonProperty("company_fingerprint")]
        public string CompanyFingerprint { get; set; }

        [JsonProperty("hash_algorithm")]
        public string HashAlgorithm { get; set; }

        [JsonProperty("version")]
        public string Version { get; set; }

        /// <summary>
        /// Serialize to JSON for storage/transmission
        /// </summary>
        public string ToJson()
        {
            return JsonConvert.SerializeObject(this, Formatting.Indented);
        }
    }
}
