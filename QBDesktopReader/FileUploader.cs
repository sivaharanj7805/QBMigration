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

        public FileUploader(string serverUrl)
        {
            this.serverUrl = serverUrl;
            this.httpClient = new HttpClient();
            this.httpClient.Timeout = TimeSpan.FromMinutes(10);
        }

        /// <summary>
        /// Upload encrypted data to server
        /// </summary>
        public async Task<UploadResponse> UploadEncryptedData(string encryptedData, string sessionId)
        {
            try
            {
                Console.WriteLine("Uploading encrypted data to server...");

                var payload = new
                {
                    session_id = sessionId,
                    encrypted_data = encryptedData,
                    timestamp = DateTime.UtcNow.ToString("o")
                };

                string jsonPayload = JsonConvert.SerializeObject(payload);
                var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

                var response = await httpClient.PostAsync($"{serverUrl}/api/upload", content);
                response.EnsureSuccessStatusCode();

                string responseBody = await response.Content.ReadAsStringAsync();
                var result = JsonConvert.DeserializeObject<UploadResponse>(responseBody);

                Console.WriteLine($"✓ Upload complete. Migration ID: {result.MigrationId}");

                return result;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"❌ Upload failed: {ex.Message}");
                throw;
            }
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