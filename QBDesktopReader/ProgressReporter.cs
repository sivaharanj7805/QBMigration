using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace QBDesktopExtractor
{
    /// <summary>
    /// WebSocket client for real-time progress reporting to dashboard
    /// </summary>
    public class ProgressReporter : IDisposable
    {
        private ClientWebSocket _webSocket;
        private readonly string _serverUrl;
        private readonly string _authToken;
        private readonly IRedactingLogger _logger;
        private CancellationTokenSource _cts;
        private bool _disposed;
        private bool _isConnected;

        public event Action<string> OnMessage;
        public event Action<Exception> OnError;
        public event Action OnConnected;
        public event Action OnDisconnected;

        public bool IsConnected => _isConnected;

        public ProgressReporter(string serverUrl, string authToken, IRedactingLogger logger = null)
        {
            _serverUrl = serverUrl?.TrimEnd('/') ?? throw new ArgumentNullException(nameof(serverUrl));
            _authToken = authToken;
            _logger = logger;
        }

        /// <summary>
        /// Connect to the WebSocket server
        /// </summary>
        public async Task ConnectAsync(CancellationToken cancellationToken = default)
        {
            if (_isConnected) return;

            _cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            _webSocket = new ClientWebSocket();

            // Convert HTTP URL to WebSocket URL
            string wsUrl = _serverUrl
                .Replace("https://", "wss://")
                .Replace("http://", "ws://");
            wsUrl = $"{wsUrl}/socket.io/?EIO=4&transport=websocket";

            try
            {
                await _webSocket.ConnectAsync(new Uri(wsUrl), _cts.Token);
                _isConnected = true;
                _logger?.Log(LogLevel.Info, "WebSocket connected");
                OnConnected?.Invoke();

                // Start receiving messages
                _ = ReceiveLoopAsync(_cts.Token);

                // Authenticate
                await AuthenticateAsync();
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Error, "WebSocket connection failed: {0}", ex.Message);
                OnError?.Invoke(ex);
                throw;
            }
        }

        /// <summary>
        /// Subscribe to migration progress updates
        /// </summary>
        public async Task SubscribeToMigrationAsync(string migrationId)
        {
            if (!_isConnected)
            {
                throw new InvalidOperationException("Not connected");
            }

            var message = new JObject
            {
                ["type"] = "subscribe_migration",
                ["migration_id"] = migrationId
            };

            await SendMessageAsync(message);
            _logger?.Log(LogLevel.Debug, "Subscribed to migration: {0}", migrationId);
        }

        /// <summary>
        /// Report extraction progress
        /// </summary>
        public async Task ReportProgressAsync(
            string migrationId,
            int progressPercent,
            string currentStep,
            string phase = "extraction")
        {
            // Also send via REST API for reliability
            try
            {
                using (var http = new System.Net.Http.HttpClient())
                {
                    if (!string.IsNullOrEmpty(_authToken))
                    {
                        http.DefaultRequestHeaders.Add("Authorization", $"Bearer {_authToken}");
                    }

                    var payload = new JObject
                    {
                        ["migration_id"] = migrationId,
                        ["progress"] = progressPercent,
                        ["step"] = currentStep,
                        ["status"] = phase
                    };

                    await http.PostAsync(
                        $"{_serverUrl}/api/ws/emit/progress",
                        new System.Net.Http.StringContent(
                            payload.ToString(),
                            Encoding.UTF8,
                            "application/json"));
                }
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "Failed to report progress via REST: {0}", ex.Message);
            }

            // Also send via WebSocket if connected
            if (_isConnected)
            {
                var message = new JObject
                {
                    ["type"] = "progress_update",
                    ["migration_id"] = migrationId,
                    ["progress"] = progressPercent,
                    ["step"] = currentStep,
                    ["phase"] = phase
                };

                try
                {
                    await SendMessageAsync(message);
                }
                catch
                {
                    // WebSocket may be closed, ignore
                }
            }
        }

        private async Task AuthenticateAsync()
        {
            var authMessage = new JObject
            {
                ["type"] = "authenticate",
                ["token"] = _authToken
            };

            await SendMessageAsync(authMessage);
        }

        private async Task SendMessageAsync(JObject message)
        {
            if (_webSocket?.State != WebSocketState.Open)
            {
                return;
            }

            string json = message.ToString(Formatting.None);
            byte[] buffer = Encoding.UTF8.GetBytes(json);

            await _webSocket.SendAsync(
                new ArraySegment<byte>(buffer),
                WebSocketMessageType.Text,
                true,
                _cts.Token);
        }

        private async Task ReceiveLoopAsync(CancellationToken cancellationToken)
        {
            var buffer = new byte[4096];

            try
            {
                while (!cancellationToken.IsCancellationRequested && 
                       _webSocket?.State == WebSocketState.Open)
                {
                    var result = await _webSocket.ReceiveAsync(
                        new ArraySegment<byte>(buffer),
                        cancellationToken);

                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        break;
                    }

                    if (result.MessageType == WebSocketMessageType.Text)
                    {
                        string message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                        OnMessage?.Invoke(message);
                    }
                }
            }
            catch (OperationCanceledException)
            {
                // Normal cancellation
            }
            catch (Exception ex)
            {
                _logger?.Log(LogLevel.Warning, "WebSocket receive error: {0}", ex.Message);
                OnError?.Invoke(ex);
            }
            finally
            {
                _isConnected = false;
                OnDisconnected?.Invoke();
            }
        }

        /// <summary>
        /// Disconnect from the WebSocket server
        /// </summary>
        public async Task DisconnectAsync()
        {
            if (!_isConnected) return;

            try
            {
                _cts?.Cancel();

                if (_webSocket?.State == WebSocketState.Open)
                {
                    await _webSocket.CloseAsync(
                        WebSocketCloseStatus.NormalClosure,
                        "Closing",
                        CancellationToken.None);
                }
            }
            catch
            {
                // Best effort
            }
            finally
            {
                _isConnected = false;
            }
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;

            _cts?.Cancel();
            _cts?.Dispose();
            _webSocket?.Dispose();
        }
    }
}
