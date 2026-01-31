using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Production-grade structured logging for ForensicBridge
    /// 
    /// Features:
    /// - Structured JSON logging for production environments
    /// - Console output for development with color coding
    /// - File logging with rotation support
    /// - Event Log integration for Windows services
    /// - Log levels: Debug, Info, Warn, Error, Fatal
    /// </summary>
    public static class Logger
    {
        private static readonly object _logLock = new object();
        private static readonly string _logDirectory;
        private static readonly string _logFilePath;
        private static readonly bool _isProduction;
        private static readonly bool _useEventLog;
        private const string EventLogSource = "ForensicBridge";
        private const string EventLogName = "Application";
        private const long MaxLogFileSize = 10 * 1024 * 1024; // 10MB
        
        static Logger()
        {
            _logDirectory = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "ForensicBridge",
                "Logs"
            );
            
            try
            {
                Directory.CreateDirectory(_logDirectory);
            }
            catch (IOException)
            {
                // Fallback to temp directory
                _logDirectory = Path.GetTempPath();
            }
            catch (UnauthorizedAccessException)
            {
                // Fallback to temp directory
                _logDirectory = Path.GetTempPath();
            }
            
            _logFilePath = Path.Combine(_logDirectory, $"forensicbridge_{DateTime.UtcNow:yyyyMMdd}.log");
            
            // Check if running in production (no debugger attached, release build)
            _isProduction = !Debugger.IsAttached && 
                           Environment.GetEnvironmentVariable("FORENSICBRIDGE_ENV") == "production";
            
            // Try to use Windows Event Log for services (Windows only)
            _useEventLog = false;
            try
            {
                // Only enable event logging in production
                if (_isProduction)
                {
                    if (EventLog.SourceExists(EventLogSource))
                    {
                        _useEventLog = true;
                    }
                    // Note: Don't try to create source - requires admin privileges
                }
            }
            catch (System.Security.SecurityException)
            {
                // EventLog access may fail on non-Windows or without permissions
                _useEventLog = false;
            }
            catch (InvalidOperationException)
            {
                // EventLog not available on this platform
                _useEventLog = false;
            }
        }
        
        /// <summary>
        /// Log debug message (only in development)
        /// </summary>
        public static void Debug(string component, string message, object? data = null)
        {
            if (!_isProduction)
            {
                Log(LogLevel.Debug, component, message, data);
            }
        }
        
        /// <summary>
        /// Log informational message
        /// </summary>
        public static void Info(string component, string message, object? data = null)
        {
            Log(LogLevel.Info, component, message, data);
        }
        
        /// <summary>
        /// Log warning message
        /// </summary>
        public static void Warn(string component, string message, object? data = null)
        {
            Log(LogLevel.Warn, component, message, data);
        }
        
        /// <summary>
        /// Log error message
        /// </summary>
        public static void Error(string component, string message, object? data = null, Exception? exception = null)
        {
            Log(LogLevel.Error, component, message, data, exception);
        }
        
        /// <summary>
        /// Log fatal error message
        /// </summary>
        public static void Fatal(string component, string message, object? data = null, Exception? exception = null)
        {
            Log(LogLevel.Fatal, component, message, data, exception);
        }
        
        private static void Log(LogLevel level, string component, string message, object? data = null, Exception? exception = null)
        {
            var logEntry = new LogEntry
            {
                Timestamp = DateTime.UtcNow,
                Level = level.ToString().ToUpperInvariant(),
                Component = component,
                Message = message,
                Data = data,
                Exception = exception?.ToString(),
                MachineName = Environment.MachineName,
                ProcessId = Process.GetCurrentProcess().Id
            };
            
            lock (_logLock)
            {
                try
                {
                    // Console output with color coding
                    WriteToConsole(level, component, message);
                    
                    // File logging (structured JSON)
                    WriteToFile(logEntry);
                    
                    // Windows Event Log for errors in production
                    if (_useEventLog && level >= LogLevel.Error)
                    {
                        WriteToEventLog(level, component, message, exception);
                    }
                }
                catch (Exception)
                {
                    // Swallow logging errors - never let logging crash the app
                }
            }
        }
        
        private static void WriteToConsole(LogLevel level, string component, string message)
        {
            // Only write to console in development or for warnings/errors
            if (_isProduction && level < LogLevel.Warn)
                return;
            
            var originalColor = Console.ForegroundColor;
            
            try
            {
                var prefix = level switch
                {
                    LogLevel.Debug => "[DBG]",
                    LogLevel.Info => "[INF]",
                    LogLevel.Warn => "[WRN]",
                    LogLevel.Error => "[ERR]",
                    LogLevel.Fatal => "[FTL]",
                    _ => "[LOG]"
                };
                
                Console.ForegroundColor = level switch
                {
                    LogLevel.Debug => ConsoleColor.Gray,
                    LogLevel.Info => ConsoleColor.Cyan,
                    LogLevel.Warn => ConsoleColor.Yellow,
                    LogLevel.Error => ConsoleColor.Red,
                    LogLevel.Fatal => ConsoleColor.DarkRed,
                    _ => ConsoleColor.White
                };
                
                Console.WriteLine($"{prefix} [{component}] {message}");
            }
            finally
            {
                Console.ForegroundColor = originalColor;
            }
        }
        
        private static void WriteToFile(LogEntry entry)
        {
            try
            {
                // Rotate log file if too large
                if (File.Exists(_logFilePath))
                {
                    var fileInfo = new FileInfo(_logFilePath);
                    if (fileInfo.Length > MaxLogFileSize)
                    {
                        var archivePath = Path.Combine(
                            _logDirectory,
                            $"forensicbridge_{DateTime.UtcNow:yyyyMMdd_HHmmss}.log"
                        );
                        try
                        {
                            File.Move(_logFilePath, archivePath);
                        }
                        catch (IOException)
                        {
                            // Log rotation failed - continue writing to current file
                        }
                    }
                }

                var json = JsonSerializer.Serialize(entry, new JsonSerializerOptions
                {
                    WriteIndented = false
                });

                // Use FileStream with proper sharing to allow concurrent reads
                // and to ensure atomic writes with exclusive lock
                var logLine = Encoding.UTF8.GetBytes(json + Environment.NewLine);
                using (var fs = new FileStream(
                    _logFilePath,
                    FileMode.Append,
                    FileAccess.Write,
                    FileShare.Read,    // Allow other processes to read while we write
                    bufferSize: 4096,
                    FileOptions.None))
                {
                    fs.Write(logLine, 0, logLine.Length);
                }
            }
            catch (IOException)
            {
                // Swallow file write errors - can't let logging crash the app
            }
            catch (UnauthorizedAccessException)
            {
                // No write permission - can't let logging crash the app
            }
        }
        
        private static void WriteToEventLog(LogLevel level, string component, string message, Exception? exception)
        {
            try
            {
                var entryType = level switch
                {
                    LogLevel.Warn => EventLogEntryType.Warning,
                    LogLevel.Error => EventLogEntryType.Error,
                    LogLevel.Fatal => EventLogEntryType.Error,
                    _ => EventLogEntryType.Information
                };

                var fullMessage = $"[{component}] {message}";
                if (exception != null)
                {
                    fullMessage += $"\n\nException:\n{exception}";
                }

                // Truncate to event log max size (Windows limit is 32766 chars)
                const int MaxEventLogSize = 32000;
                if (fullMessage.Length > MaxEventLogSize)
                {
                    fullMessage = fullMessage.Substring(0, MaxEventLogSize) + "...[truncated]";
                }

                EventLog.WriteEntry(EventLogSource, fullMessage, entryType);
            }
            catch (System.Security.SecurityException)
            {
                // Swallow event log errors - can't let logging crash the app
            }
            catch (InvalidOperationException)
            {
                // EventLog not available - can't let logging crash the app
            }
        }
        
        /// <summary>
        /// Get the current log file path
        /// </summary>
        public static string GetLogFilePath() => _logFilePath;
        
        /// <summary>
        /// Get the log directory path
        /// </summary>
        public static string GetLogDirectory() => _logDirectory;
        
        private enum LogLevel
        {
            Debug = 0,
            Info = 1,
            Warn = 2,
            Error = 3,
            Fatal = 4
        }
        
        private class LogEntry
        {
            public DateTime Timestamp { get; set; }
            public string Level { get; set; } = "";
            public string Component { get; set; } = "";
            public string Message { get; set; } = "";
            public object? Data { get; set; }
            public string? Exception { get; set; }
            public string MachineName { get; set; } = "";
            public int ProcessId { get; set; }
        }
    }
}
