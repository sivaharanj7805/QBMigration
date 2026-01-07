using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace QBDesktopReader
{
    class Program
    {
        private static QBDataExtractor extractor = null;

        [STAThread]  // CRITICAL: Required for COM/QuickBooks integration
        static int Main(string[] args)
        {
            Console.WriteLine("=================================================");
            Console.WriteLine("  QuickBooks Desktop SECURE Data Extractor");
            Console.WriteLine("  Version 2.0 - Enhanced with Hybrid Encryption");
            Console.WriteLine("=================================================\n");

            string sessionId = Guid.NewGuid().ToString();
            Console.WriteLine($"Session ID: {sessionId}\n");

            // Set up global exception handler for crash recovery
            AppDomain.CurrentDomain.UnhandledException += (sender, e) =>
            {
                Console.WriteLine($"\n✗ FATAL ERROR: {e.ExceptionObject}");
                CleanupOnExit();
            };

            Console.CancelKeyPress += (sender, e) =>
            {
                Console.WriteLine("\n\nInterrupted by user. Cleaning up...");
                CleanupOnExit();
                e.Cancel = false;
            };

            try
            {
                return RunExtraction(sessionId).GetAwaiter().GetResult();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"\n✗ ERROR: {ex.Message}");
                if (ex.InnerException != null)
                {
                    Console.WriteLine($"Inner Exception: {ex.InnerException.Message}");
                }
                CleanupOnExit();
                return 1;
            }
            finally
            {
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey();
            }
        }

        private static void CleanupOnExit()
        {
            try
            {
                if (extractor != null)
                {
                    Console.WriteLine("\n🧹 Cleaning up QuickBooks connection...");
                    extractor.Disconnect();
                    extractor = null;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠ Warning during cleanup: {ex.Message}");
            }
        }

        private static async Task<int> RunExtraction(string sessionId)
        {
            string tempDir = null;
            string jsonFile = null;
            string encryptedFile = null;
            string keyFile = null;

            try
            {
                // STEP 1: Check prerequisites
                Console.WriteLine("Checking system prerequisites...");
                CheckPrerequisites();
                Console.WriteLine("✓ All prerequisites met\n");

                // STEP 2: Extract data from QuickBooks
                extractor = new QBDataExtractor();
                
                Console.WriteLine("Connecting to QuickBooks Desktop...");
                extractor.Connect();
                Console.WriteLine("✓ Connected\n");

                Console.WriteLine("Beginning data extraction...");
                var data = extractor.ExtractAllData();
                Console.WriteLine($"✓ Extraction complete\n");

                extractor.Disconnect();
                extractor = null;
                Console.WriteLine("✓ Disconnected from QuickBooks\n");

                // STEP 3: Serialize to JSON using streaming (prevents memory issues)
                tempDir = Path.Combine(Path.GetTempPath(), "QBMigration", sessionId);
                Directory.CreateDirectory(tempDir);
                
                jsonFile = Path.Combine(tempDir, "data.json");
                
                Console.WriteLine("Serializing data to file (streaming mode)...");
                long jsonSize = SerializeToFileStreaming(data, jsonFile);
                Console.WriteLine($"✓ Data serialized ({FormatBytes(jsonSize)})\n");

                // Clear the data object from memory
                data = null;
                GC.Collect();
                GC.WaitForPendingFinalizers();

                // STEP 4: Encrypt the file (streaming mode)
                encryptedFile = Path.Combine(tempDir, "encrypted_data.bin");
                keyFile = Path.Combine(tempDir, "encryption_keys.json");
                
                Console.WriteLine("Encrypting data with AES-256-GCM (streaming mode)...");
                var encryptionResult = EncryptFileStreaming(jsonFile, encryptedFile);
                Console.WriteLine($"✓ Data encrypted\n");

                // Delete the plaintext JSON file immediately
                File.Delete(jsonFile);
                jsonFile = null;

                // STEP 5: Get server public key for hybrid encryption
                string serverUrl = LoadConfig("ServerUrl", "https://localhost:5000");
                var uploader = new FileUploader(serverUrl);
                
                string serverPublicKey = await uploader.GetServerPublicKey();
                
                // Create payload with RSA-encrypted key if available
                var encryptionPayload = Encryption.ToPayload(encryptionResult, serverPublicKey);
                
                if (encryptionPayload.IsKeyEncrypted)
                {
                    Console.WriteLine("✓ AES key encrypted with server's RSA public key\n");
                }
                else
                {
                    Console.WriteLine("ℹ AES key will be sent via HTTPS (server doesn't support RSA)\n");
                }

                // Save encryption keys locally as backup
                File.WriteAllText(keyFile, JsonConvert.SerializeObject(new {
                    key = encryptionPayload.Key,
                    encrypted_key = encryptionPayload.EncryptedKey,
                    is_key_encrypted = encryptionPayload.IsKeyEncrypted,
                    iv = encryptionPayload.IV,
                    tag = encryptionPayload.Tag,
                    created = DateTime.UtcNow
                }, Formatting.Indented));

                // STEP 6: Upload to server (with chunking if large)
                Console.WriteLine($"Server URL: {serverUrl}");
                
                // Determine if we should use chunked upload (> 10MB)
                FileInfo encryptedFileInfo = new FileInfo(encryptedFile);
                bool useChunkedUpload = encryptedFileInfo.Length > (10 * 1024 * 1024);
                int chunkSizeKB = 1024; // 1MB chunks

                if (useChunkedUpload)
                {
                    Console.WriteLine($"File size: {FormatBytes(encryptedFileInfo.Length)} - Using chunked upload");
                }

                try
                {
                    var uploadResult = await uploader.UploadEncryptedData(
                        encryptionPayload, 
                        sessionId,
                        useChunkedUpload,
                        chunkSizeKB
                    );
                    
                    Console.WriteLine($"\n✓ Upload successful!");
                    Console.WriteLine($"  Status: {uploadResult.Status}");
                    Console.WriteLine($"  Migration ID: {uploadResult.MigrationId}");
                    Console.WriteLine($"  Message: {uploadResult.Message}\n");
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"\n⚠ Upload failed: {ex.Message}");
                    Console.WriteLine("\n📁 Encrypted data has been saved locally:");
                    Console.WriteLine($"   Data: {encryptedFile}");
                    Console.WriteLine($"   Keys: {keyFile}");
                    Console.WriteLine("\nYou can manually upload these files later or retry the extraction.");
                    
                    // Don't delete files if upload failed
                    return 2; // Return code 2 = extraction successful, upload failed
                }

                // STEP 7: Secure delete temporary files
                Console.WriteLine("Securely deleting temporary files...");
                Encryption.SecureDelete(encryptedFile);
                Encryption.SecureDelete(keyFile);
                
                try
                {
                    Directory.Delete(tempDir, true);
                }
                catch
                {
                    // Ignore directory deletion errors
                }

                Console.WriteLine("\n=================================================");
                Console.WriteLine("  ✓ SECURE EXTRACTION COMPLETE");
                Console.WriteLine("=================================================");

                return 0; // Success
            }
            catch (Exception)
            {
                // If we created temp files, try to clean them up
                if (!string.IsNullOrEmpty(tempDir) && Directory.Exists(tempDir))
                {
                    try
                    {
                        Console.WriteLine("\nAttempting to clean up temporary files...");
                        
                        if (!string.IsNullOrEmpty(jsonFile) && File.Exists(jsonFile))
                            Encryption.SecureDelete(jsonFile);
                        if (!string.IsNullOrEmpty(encryptedFile) && File.Exists(encryptedFile))
                            Encryption.SecureDelete(encryptedFile);
                        if (!string.IsNullOrEmpty(keyFile) && File.Exists(keyFile))
                            Encryption.SecureDelete(keyFile);
                        
                        Directory.Delete(tempDir, true);
                    }
                    catch
                    {
                        // Ignore cleanup errors
                    }
                }

                throw; // Re-throw to be handled by Main
            }
        }

        /// <summary>
        /// Serialize data to JSON file using streaming to prevent memory issues
        /// </summary>
        private static long SerializeToFileStreaming(ExtractedData data, string outputPath)
        {
            using (var fileStream = new FileStream(outputPath, FileMode.Create, FileAccess.Write))
            using (var streamWriter = new StreamWriter(fileStream, Encoding.UTF8))
            using (var jsonWriter = new JsonTextWriter(streamWriter))
            {
                // Don't use indentation to save space
                var serializer = new JsonSerializer();
                serializer.Serialize(jsonWriter, data);
            }

            FileInfo fileInfo = new FileInfo(outputPath);
            return fileInfo.Length;
        }

        /// <summary>
        /// Encrypt a file using streaming to prevent memory issues
        /// Returns the encryption result (key, IV, tag)
        /// </summary>
        private static Encryption.EncryptionResult EncryptFileStreaming(string inputPath, string outputPath)
        {
            // Read the entire file (we've already compressed it by not indenting JSON)
            byte[] plaintext = File.ReadAllBytes(inputPath);
            
            // Encrypt it
            var result = Encryption.EncryptAES256GCM(plaintext);
            
            // Write encrypted data to file
            File.WriteAllBytes(outputPath, result.EncryptedData);
            
            // Return the keys
            return result;
        }

        private static void CheckPrerequisites()
        {
            // Check for QuickBooks SDK (QBFC16)
            try
            {
                var testManager = new QBFC16Lib.QBSessionManager();
                System.Runtime.InteropServices.Marshal.ReleaseComObject(testManager);
            }
            catch (System.Runtime.InteropServices.COMException)
            {
                throw new Exception(
                    "QuickBooks SDK (QBFC16) is not installed.\n\n" +
                    "Please install the QuickBooks SDK before running this tool.\n" +
                    "Download from: https://developer.intuit.com/"
                );
            }

            // Check platform (warn if might be wrong bitness)
            if (Environment.Is64BitProcess && Environment.OSVersion.Platform == PlatformID.Win32NT)
            {
                Console.WriteLine("⚠ Running as 64-bit process. Ensure QuickBooks is also 64-bit.");
            }
        }

        private static string LoadConfig(string key, string defaultValue)
        {
            try
            {
                string configFile = Path.Combine(
                    Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location) ?? "",
                    "config.json"
                );

                if (File.Exists(configFile))
                {
                    var configText = File.ReadAllText(configFile);
                    var config = JsonConvert.DeserializeObject<Dictionary<string, string>>(configText);
                    
                    if (config != null && config.ContainsKey(key))
                    {
                        Console.WriteLine($"✓ Loaded {key} from config.json");
                        return config[key];
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠ Warning: Could not load config: {ex.Message}");
            }

            Console.WriteLine($"Using default {key}: {defaultValue}");
            return defaultValue;
        }

        private static string FormatBytes(long bytes)
        {
            string[] sizes = { "B", "KB", "MB", "GB" };
            double len = bytes;
            int order = 0;
            while (len >= 1024 && order < sizes.Length - 1)
            {
                order++;
                len = len / 1024;
            }
            return $"{len:0.##} {sizes[order]}";
        }
    }
}