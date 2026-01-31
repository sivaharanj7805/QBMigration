using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
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
                        // Validate session code - must be non-empty, reasonable length, not start with dash
                        if (!string.IsNullOrEmpty(value) && value.Length <= 50 && !value.StartsWith("-"))
                        {
                            sessionCode = value;
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
                LogToFile($"Argument parsing error: {ex.Message}");
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
            // Always log to file first
            LogToFile($"FATAL ERROR: {ex}");

            try
            {
                MessageBox.Show(
                    $"An unexpected error occurred:\n\n{ex.Message}\n\n" +
                    "The application will now close.\n\n" +
                    "If this problem persists, please contact support@forensicbridge.ca\n\n" +
                    $"Error log: {LogFilePath}",
                    "ForensicBridge Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            catch (Exception msgEx)
            {
                // MessageBox failed - try to at least log this
                LogToFile($"Failed to show error dialog: {msgEx.Message}");
            }
        }

        /// <summary>
        /// Log message to file for debugging when UI is unavailable
        /// </summary>
        private static void LogToFile(string message)
        {
            try
            {
                var logDir = Path.GetDirectoryName(LogFilePath);
                if (!string.IsNullOrEmpty(logDir))
                {
                    Directory.CreateDirectory(logDir);
                }

                var timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
                var logEntry = $"[{timestamp}] {message}{Environment.NewLine}";

                // Append to log file, creating if necessary
                File.AppendAllText(LogFilePath, logEntry);
            }
            catch
            {
                // Can't log - nothing more we can do
                Debug.WriteLine($"Failed to write to log file: {message}");
            }
        }
    }
}
