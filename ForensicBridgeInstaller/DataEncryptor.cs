using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace ForensicBridgeInstaller
{
    /// <summary>
    /// Encrypts extracted QuickBooks data using AES-256-GCM before upload.
    /// Compatible with the server's v3.1 upload format.
    /// </summary>
    public class DataEncryptor
    {
        /// <summary>
        /// Encrypt data using AES-256-GCM
        /// </summary>
        public static EncryptionResult Encrypt(string plainText)
        {
            if (string.IsNullOrEmpty(plainText))
                throw new ArgumentException("Data to encrypt cannot be empty");

            var plainBytes = Encoding.UTF8.GetBytes(plainText);
            return EncryptBytes(plainBytes);
        }

        /// <summary>
        /// Encrypt raw bytes using AES-256-GCM
        /// </summary>
        public static EncryptionResult EncryptBytes(byte[] plainBytes)
        {
            // Generate random 256-bit key and 96-bit IV
            var key = new byte[32]; // 256 bits
            var iv = new byte[12];  // 96 bits (standard for GCM)

            using (var rng = RandomNumberGenerator.Create())
            {
                rng.GetBytes(key);
                rng.GetBytes(iv);
            }

            // AES-GCM encryption
            var tag = new byte[16]; // 128-bit auth tag
            var cipherBytes = new byte[plainBytes.Length];

            using (var aesGcm = new AesGcm(key))
            {
                aesGcm.Encrypt(iv, plainBytes, cipherBytes, tag);
            }

            return new EncryptionResult
            {
                EncryptedDataBase64 = Convert.ToBase64String(cipherBytes),
                KeyBase64 = Convert.ToBase64String(key),
                IvBase64 = Convert.ToBase64String(iv),
                TagBase64 = Convert.ToBase64String(tag),
                Algorithm = "AES-256-GCM",
                OriginalSizeBytes = plainBytes.Length,
                EncryptedSizeBytes = cipherBytes.Length
            };
        }

        /// <summary>
        /// Compute SHA-256 hash of data for integrity verification
        /// </summary>
        public static string ComputeHash(string data)
        {
            using (var sha256 = SHA256.Create())
            {
                var bytes = Encoding.UTF8.GetBytes(data);
                var hash = sha256.ComputeHash(bytes);
                return BitConverter.ToString(hash).Replace("-", "").ToLowerInvariant();
            }
        }

        /// <summary>
        /// Compute SHA-256 hash of byte array
        /// </summary>
        public static string ComputeHash(byte[] data)
        {
            using (var sha256 = SHA256.Create())
            {
                var hash = sha256.ComputeHash(data);
                return BitConverter.ToString(hash).Replace("-", "").ToLowerInvariant();
            }
        }
    }

    /// <summary>
    /// Result of an encryption operation
    /// </summary>
    public class EncryptionResult
    {
        public string EncryptedDataBase64 { get; set; }
        public string KeyBase64 { get; set; }
        public string IvBase64 { get; set; }
        public string TagBase64 { get; set; }
        public string Algorithm { get; set; }
        public int OriginalSizeBytes { get; set; }
        public int EncryptedSizeBytes { get; set; }
    }
}
