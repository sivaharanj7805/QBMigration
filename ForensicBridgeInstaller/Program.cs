using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

namespace ForensicBridgeInstaller
{
    static class Program
    {
        // DPI awareness for high-DPI displays
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        // Log file for fatal errors (when UI can't be shown)
        private static readonly string LogFilePath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ForensicBridge",
            "error.log");

        // Thread-safe lock object for log file operations
        private static readonly object LogLock = new object();

        // Session code validation pattern: alphanumeric with dashes, 6-50 characters
        private static readonly Regex SessionCodePattern = new Regex(
            @"^[A-Za-z0-9][A-Za-z0-9\-]{4,48}[A-Za-z0-9]$",
            RegexOptions.Compiled);

        /// <summary>
        /// The main entry point for the application.
        /// </summary>
        [STAThread]
        static void Main(string[] args)
        {
            // Enable DPI awareness before any UI is created
            if (Environment.OSVersion.Version.Major >= 6)
            {
                SetProcessDPIAware();
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            // Add global exception handling
            Application.ThreadException += OnThreadException;
            AppDomain.CurrentDomain.UnhandledException += OnUnhandledException;
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);

            // Parse command line arguments with validation
            string sessionCode = null;
            bool autoStart = false;

            try
            {
                for (int i = 0; i < args.Length; i++)
                {
                    var arg = args[i];

                    if ((arg == "--session" || arg == "-s") && i + 1 < args.Length)
                    {
                        var value = args[i + 1];
                        // Strong session code validation
                        if (ValidateSessionCode(value))
                        {
                            sessionCode = value;
                        }
                        else
                        {
                            LogToFile($"Invalid session code format provided (redacted for security)");
                        }
                        i++;
                    }
                    else if (arg == "--auto")
                    {
                        autoStart = true;
                    }
                    else if (arg == "--help" || arg == "-h" || arg == "/?")
                    {
                        ShowUsage();
                        return;
                    }
                }
            }
            catch (Exception ex)
            {
                // Argument parsing failed - continue with defaults
                LogToFile($"Argument parsing error: {SanitizeErrorMessage(ex.Message)}");
            }

            try
            {
                Application.Run(new MainForm(sessionCode, autoStart));
            }
            catch (Exception ex)
            {
                ShowFatalError(ex);
            }
        }

        private static void ShowUsage()
        {
            MessageBox.Show(
                "ForensicBridge - QuickBooks Desktop Data Migration Tool\n\n" +
                "Usage: ForensicBridge.exe [options]\n\n" +
                "Options:\n" +
                "  --session <code>  Pre-fill session code\n" +
                "  -s <code>         Same as --session\n" +
                "  --auto            Auto-start validation after launch\n" +
                "  --help, -h, /?    Show this help message\n\n" +
                "Example:\n" +
                "  ForensicBridge.exe --session ABC123-XYZ --auto",
                "ForensicBridge Help",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }

        private static void OnThreadException(object sender, ThreadExceptionEventArgs e)
        {
            ShowFatalError(e.Exception);
        }

        private static void OnUnhandledException(object sender, UnhandledExceptionEventArgs e)
        {
            if (e.ExceptionObject is Exception ex)
            {
                ShowFatalError(ex);
            }
            else
            {
                // Non-Exception object thrown (rare but possible)
                ShowFatalError(new Exception($"Unknown error: {e.ExceptionObject}"));
            }
        }

        private static void ShowFatalError(Exception ex)
        {
            // Always log to file first (with full details for diagnostics)
            LogToFile($"FATAL ERROR: Type={ex.GetType().Name}, Message={ex.Message}, Source={ex.Source}");
            if (ex.InnerException != null)
            {
                LogToFile($"INNER EXCEPTION: Type={ex.InnerException.GetType().Name}, Message={ex.InnerException.Message}");
            }

            try
            {
                // Show user-friendly message (not the raw exception)
                var userMessage = GetUserFriendlyMessage(ex);

                MessageBox.Show(
                    $"An unexpected error occurred:\n\n{userMessage}\n\n" +
                    "The application will now close.\n\n" +
                    "If this problem persists, please contact support@forensicbridge.ca\n\n" +
                    $"Error log location: {Path.GetDirectoryName(LogFilePath)}",
                    "ForensicBridge Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            catch (Exception msgEx)
            {
                // MessageBox failed - try to at least log this
                LogToFile($"Failed to show error dialog: {msgEx.GetType().Name}");
            }
        }

        /// <summary>
        /// Converts technical exception messages to user-friendly messages.
        /// </summary>
        private static string GetUserFriendlyMessage(Exception ex)
        {
            // Map common exceptions to user-friendly messages
            if (ex is OutOfMemoryException)
                return "The application ran out of memory. Please close other applications and try again.";

            if (ex is FileNotFoundException || ex is DirectoryNotFoundException)
                return "A required file or folder could not be found. Please reinstall the application.";

            if (ex is UnauthorizedAccessException)
                return "Access was denied. Please run the application as administrator.";

            if (ex is System.Net.WebException || ex is System.Net.Sockets.SocketException)
                return "A network error occurred. Please check your internet connection and try again.";

            if (ex is InvalidOperationException && ex.Message.Contains("QuickBooks"))
                return "QuickBooks is not responding. Please ensure QuickBooks Desktop is running and try again.";

            if (ex is TimeoutException)
                return "The operation timed out. Please try again.";

            // For other exceptions, provide a generic but helpful message
            return "An internal error occurred. Details have been saved to the error log.";
        }

        /// <summary>
        /// Validates session code format for security.
        /// Session codes must:
        /// - Be 6-50 characters long
        /// - Start and end with alphanumeric characters
        /// - Contain only alphanumeric characters and dashes
        /// - Not contain path traversal or injection patterns
        /// </summary>
        /// <param name="sessionCode">The session code to validate</param>
        /// <returns>True if valid, false otherwise</returns>
        private static bool ValidateSessionCode(string sessionCode)
        {
            if (string.IsNullOrEmpty(sessionCode))
                return false;

            // Length check
            if (sessionCode.Length < 6 || sessionCode.Length > 50)
                return false;

            // Pattern validation
            if (!SessionCodePattern.IsMatch(sessionCode))
                return false;

            // Security: Block potential injection patterns
            var lowerCode = sessionCode.ToLower();
            string[] blockedPatterns = { "..", "/", "\\", "<", ">", "|", ":", "*", "?", "\"", "'", "script", "eval" };
            foreach (var pattern in blockedPatterns)
            {
                if (lowerCode.Contains(pattern))
                    return false;
            }

            return true;
        }

        /// <summary>
        /// Sanitizes error messages to remove sensitive data before logging.
        /// Redacts file paths, usernames, and potential secrets.
        /// </summary>
        /// <param name="message">The original error message</param>
        /// <returns>Sanitized message safe for logging</returns>
        private static string SanitizeErrorMessage(string message)
        {
            if (string.IsNullOrEmpty(message))
                return "[empty message]";

            // Redact file paths (Windows)
            message = Regex.Replace(message, @"[A-Za-z]:\\[^\s""']+", "[PATH_REDACTED]");

            // Redact usernames in paths
            message = Regex.Replace(message, @"\\Users\\[^\\]+", "\\Users\\[USER]");

            // Redact potential tokens/secrets (base64-like strings over 20 chars)
            message = Regex.Replace(message, @"[A-Za-z0-9+/]{20,}={0,2}", "[TOKEN_REDACTED]");

            // Redact email addresses
            message = Regex.Replace(message, @"[\w.-]+@[\w.-]+\.\w+", "[EMAIL_REDACTED]");

            // Limit message length to prevent log flooding
            if (message.Length > 1000)
                message = message.Substring(0, 1000) + "... [TRUNCATED]";

            return message;
        }

        /// <summary>
        /// Log message to file for debugging when UI is unavailable.
        /// Thread-safe implementation using locks.
        /// Sanitizes sensitive data before writing.
        /// </summary>
        /// <param name="message">Message to log (will be sanitized)</param>
        private static void LogToFile(string message)
        {
            // Thread-safe logging with lock
            lock (LogLock)
            {
                try
                {
                    var logDir = Path.GetDirectoryName(LogFilePath);
                    if (!string.IsNullOrEmpty(logDir))
                    {
                        Directory.CreateDirectory(logDir);
                    }

                    // Sanitize message to remove sensitive data
                    var sanitizedMessage = SanitizeErrorMessage(message);

                    var timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
                    var logEntry = $"[{timestamp}] {sanitizedMessage}{Environment.NewLine}";

                    // Append to log file, creating if necessary
                    File.AppendAllText(LogFilePath, logEntry);

                    // Rotate log file if too large (> 1MB)
                    RotateLogFileIfNeeded();
                }
                catch
                {
                    // Can't log - nothing more we can do
                    Debug.WriteLine($"Failed to write to log file");
                }
            }
        }

        /// <summary>
        /// Rotates the log file if it exceeds 1MB to prevent disk space issues.
        /// Keeps one backup file.
        /// </summary>
        private static void RotateLogFileIfNeeded()
        {
            try
            {
                if (!File.Exists(LogFilePath))
                    return;

                var fileInfo = new FileInfo(LogFilePath);
                const long maxSizeBytes = 1024 * 1024; // 1MB

                if (fileInfo.Length > maxSizeBytes)
                {
                    var backupPath = LogFilePath + ".old";
                    if (File.Exists(backupPath))
                        File.Delete(backupPath);

                    File.Move(LogFilePath, backupPath);
                }
            }
            catch
            {
                // Rotation failed - not critical
            }
        }
    }
}
