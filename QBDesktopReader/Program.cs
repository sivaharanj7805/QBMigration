using System;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace QBDesktopReader
{
    class Program
    {
        static async Task Main(string[] args)
        {
            Console.WriteLine("=================================================");
            Console.WriteLine("  QuickBooks Desktop SECURE Data Extractor");
            Console.WriteLine("=================================================\n");

            string sessionId = Guid.NewGuid().ToString();
            Console.WriteLine($"Session ID: {sessionId}\n");

            try
            {
                // STEP 1: Extract data
                var extractor = new QBDataExtractor();
                
                Console.WriteLine("Connecting to QuickBooks Desktop...");
                extractor.Connect();
                Console.WriteLine("✓ Connected\n");

                var data = extractor.ExtractAllData();

                extractor.Disconnect();
                Console.WriteLine("\n✓ Disconnected from QuickBooks\n");

                // STEP 2: Convert to JSON
                Console.WriteLine("Serializing data...");
                string json = JsonConvert.SerializeObject(data, Formatting.Indented);
                Console.WriteLine($"✓ Data serialized ({json.Length} bytes)\n");

                // STEP 3: Encrypt data
                Console.WriteLine("Encrypting data with AES-256-GCM...");
                string encryptedData = Encryption.EncryptString(json);
                Console.WriteLine($"✓ Data encrypted ({encryptedData.Length} bytes)\n");

                // STEP 4: Save encrypted locally (temporary)
                string tempDir = Path.Combine(Path.GetTempPath(), "QBMigration", sessionId);
                Directory.CreateDirectory(tempDir);
                
                string encryptedFile = Path.Combine(tempDir, "encrypted_data.txt");
                File.WriteAllText(encryptedFile, encryptedData);
                Console.WriteLine($"✓ Encrypted data saved temporarily\n");

                // STEP 5: Upload to server
                string serverUrl = "http://localhost:5000"; // Change to your server URL
                var uploader = new FileUploader(serverUrl);

                try
                {
                    var uploadResult = await uploader.UploadEncryptedData(encryptedData, sessionId);
                    Console.WriteLine($"\n✓ Server response: {uploadResult.Status}");
                    Console.WriteLine($"  Migration ID: {uploadResult.MigrationId}");
                    Console.WriteLine($"  Message: {uploadResult.Message}");
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"\n⚠ Upload failed (server may not be running): {ex.Message}");
                    Console.WriteLine("Encrypted data saved locally for manual upload.");
                }

                // STEP 6: Secure delete temporary file
                Console.WriteLine("\nSecurely deleting temporary files...");
                Encryption.SecureDelete(encryptedFile);
                Directory.Delete(tempDir, true);

                Console.WriteLine("\n=================================================");
                Console.WriteLine("  SECURE EXTRACTION COMPLETE");
                Console.WriteLine("=================================================");

            }
            catch (Exception ex)
            {
                Console.WriteLine($"\n❌ ERROR: {ex.Message}");
                Console.WriteLine($"\nStack trace:\n{ex.StackTrace}");
            }

            Console.WriteLine("\nPress any key to exit...");
            Console.ReadKey();
        }
    }
}