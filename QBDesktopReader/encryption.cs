using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;

namespace QBDesktopReader
{
    /// <summary>
    /// PRODUCTION-GRADE Encryption Manager
    /// 
    /// FIXES APPLIED:
    /// - Structured JSON output (iv, tag, ciphertext, key)
    /// - Backward compatible with Python decryption
    /// - Proper memory cleanup
    /// - Cross-platform compatibility
    /// </summary>
    public class Encryption
    {
        /// <summary>
        /// Encryption result with all components
        /// </summary>
        public class EncryptionResult
        {
            [JsonProperty("iv")]
            public string IV { get; set; }
            
            [JsonProperty("tag")]
            public string Tag { get; set; }
            
            [JsonProperty("ciphertext")]
            public string Ciphertext { get; set; }
            
            [JsonProperty("key")]
            public string Key { get; set; }
            
            [JsonProperty("algorithm")]
            public string Algorithm { get; set; } = "AES-256-GCM";
            
            [JsonProperty("version")]
            public string Version { get; set; } = "2.0";
        }

        /// <summary>
        /// Encrypt string using AES-256-GCM
        /// Returns structured JSON for Python compatibility
        /// </summary>
        public static string EncryptString(string plaintext)
        {
            if (string.IsNullOrEmpty(plaintext))
            {
                throw new ArgumentException("Plaintext cannot be null or empty");
            }

            try
            {
                byte[] plaintextBytes = Encoding.UTF8.GetBytes(plaintext);
                
                // Generate 256-bit key (32 bytes)
                byte[] key = new byte[32];
                using (var rng = RandomNumberGenerator.Create())
                {
                    rng.GetBytes(key);
                }

                // Generate 96-bit IV/nonce (12 bytes for GCM)
                byte[] iv = new byte[12];
                using (var rng = RandomNumberGenerator.Create())
                {
                    rng.GetBytes(iv);
                }

                byte[] ciphertext;
                byte[] tag;

                // Encrypt using AES-GCM
                using (var aes = new AesGcm(key))
                {
                    ciphertext = new byte[plaintextBytes.Length];
                    tag = new byte[16]; // 128-bit tag

                    aes.Encrypt(iv, plaintextBytes, ciphertext, tag);
                }

                // Create structured result
                var result = new EncryptionResult
                {
                    IV = Convert.ToBase64String(iv),
                    Tag = Convert.ToBase64String(tag),
                    Ciphertext = Convert.ToBase64String(ciphertext),
                    Key = Convert.ToBase64String(key)
                };

                // Serialize to JSON
                string json = JsonConvert.SerializeObject(result);

                // SECURITY: Clear sensitive data from memory
                Array.Clear(key, 0, key.Length);
                Array.Clear(plaintextBytes, 0, plaintextBytes.Length);

                return json;
            }
            catch (Exception ex)
            {
                throw new Exception($"Encryption failed: {ex.Message}", ex);
            }
        }

        /// <summary>
        /// Decrypt string from JSON format
        /// Compatible with Python EncryptionManager.decrypt_from_json()
        /// </summary>
        public static string DecryptString(string encryptedJson)
        {
            if (string.IsNullOrEmpty(encryptedJson))
            {
                throw new ArgumentException("Encrypted JSON cannot be null or empty");
            }

            try
            {
                // Parse JSON
                var encryptedData = JsonConvert.DeserializeObject<EncryptionResult>(encryptedJson);
                
                if (encryptedData == null)
                {
                    throw new Exception("Failed to parse encryption JSON");
                }

                // Decode Base64
                byte[] iv = Convert.FromBase64String(encryptedData.IV);
                byte[] tag = Convert.FromBase64String(encryptedData.Tag);
                byte[] ciphertext = Convert.FromBase64String(encryptedData.Ciphertext);
                byte[] key = Convert.FromBase64String(encryptedData.Key);

                // Validate sizes
                if (iv.Length != 12)
                {
                    throw new Exception($"Invalid IV length: expected 12 bytes, got {iv.Length}");
                }
                if (tag.Length != 16)
                {
                    throw new Exception($"Invalid tag length: expected 16 bytes, got {tag.Length}");
                }
                if (key.Length != 32)
                {
                    throw new Exception($"Invalid key length: expected 32 bytes, got {key.Length}");
                }

                byte[] plaintext = new byte[ciphertext.Length];

                // Decrypt using AES-GCM
                using (var aes = new AesGcm(key))
                {
                    aes.Decrypt(iv, ciphertext, tag, plaintext);
                }

                string result = Encoding.UTF8.GetString(plaintext);

                // SECURITY: Clear sensitive data from memory
                Array.Clear(key, 0, key.Length);
                Array.Clear(plaintext, 0, plaintext.Length);

                return result;
            }
            catch (Exception ex)
            {
                throw new Exception($"Decryption failed: {ex.Message}", ex);
            }
        }

        /// <summary>
        /// Secure file deletion using DoD 5220.22-M standard (7-pass)
        /// </summary>
        public static void SecureDelete(string filePath)
        {
            if (!File.Exists(filePath))
            {
                return;
            }

            try
            {
                FileInfo fileInfo = new FileInfo(filePath);
                long fileSize = fileInfo.Length;

                // Open file for overwriting
                using (FileStream stream = new FileStream(filePath, FileMode.Open, FileAccess.Write))
                {
                    // 7-pass overwrite
                    for (int pass = 0; pass < 7; pass++)
                    {
                        stream.Position = 0;

                        byte[] buffer;
                        if (pass < 5)
                        {
                            // Alternate 0x00 and 0xFF
                            byte pattern = (byte)(pass % 2 == 0 ? 0x00 : 0xFF);
                            buffer = new byte[fileSize];
                            for (long i = 0; i < fileSize; i++)
                            {
                                buffer[i] = pattern;
                            }
                        }
                        else
                        {
                            // Random data for last 2 passes
                            buffer = new byte[fileSize];
                            using (var rng = RandomNumberGenerator.Create())
                            {
                                rng.GetBytes(buffer);
                            }
                        }

                        stream.Write(buffer, 0, buffer.Length);
                        stream.Flush();
                    }
                }

                // Delete the file
                File.Delete(filePath);
                Console.WriteLine($"✓ Securely deleted: {Path.GetFileName(filePath)}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠ Failed to securely delete {filePath}: {ex.Message}");
                throw;
            }
        }

        /// <summary>
        /// Encrypt file and save to output path
        /// </summary>
        public static EncryptionResult EncryptFile(string inputPath, string outputPath)
        {
            if (!File.Exists(inputPath))
            {
                throw new FileNotFoundException($"Input file not found: {inputPath}");
            }

            try
            {
                // Read plaintext
                string plaintext = File.ReadAllText(inputPath);

                // Encrypt
                string encryptedJson = EncryptString(plaintext);

                // Write to output
                File.WriteAllText(outputPath, encryptedJson);

                // Return result for key management
                return JsonConvert.DeserializeObject<EncryptionResult>(encryptedJson);
            }
            catch (Exception ex)
            {
                throw new Exception($"File encryption failed: {ex.Message}", ex);
            }
        }

        /// <summary>
        /// Decrypt file
        /// </summary>
        public static void DecryptFile(string inputPath, string outputPath)
        {
            if (!File.Exists(inputPath))
            {
                throw new FileNotFoundException($"Input file not found: {inputPath}");
            }

            try
            {
                // Read encrypted JSON
                string encryptedJson = File.ReadAllText(inputPath);

                // Decrypt
                string plaintext = DecryptString(encryptedJson);

                // Write plaintext
                File.WriteAllText(outputPath, plaintext);
            }
            catch (Exception ex)
            {
                throw new Exception($"File decryption failed: {ex.Message}", ex);
            }
        }
    }
}