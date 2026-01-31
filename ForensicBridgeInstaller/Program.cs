using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace ForensicBridgeInstaller
{
    static class Program
    {
        // P3 fix: DPI awareness for high-DPI displays
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        /// <summary>
        /// The main entry point for the application.
        /// </summary>
        [STAThread]
        static void Main(string[] args)
        {
            // P3 fix: Enable DPI awareness before any UI is created
            if (Environment.OSVersion.Version.Major >= 6)
            {
                SetProcessDPIAware();
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            // P2 fix: Add global exception handling
            Application.ThreadException += OnThreadException;
            AppDomain.CurrentDomain.UnhandledException += OnUnhandledException;
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);

            // Parse command line arguments with validation (P1 fix)
            string sessionCode = null;
            bool autoStart = false;

            try
            {
                for (int i = 0; i < args.Length; i++)
                {
                    if ((args[i] == "--session" || args[i] == "-s") && i + 1 < args.Length)
                    {
                        var value = args[i + 1];
                        // P1 fix: Validate session code length and content
                        if (value.Length > 0 && value.Length <= 50 && !value.StartsWith("-"))
                        {
                            sessionCode = value;
                        }
                        i++;
                    }
                    else if (args[i] == "--auto")
                    {
                        autoStart = true;
                    }
                }
            }
            catch (Exception ex)
            {
                // Argument parsing failed - continue with defaults
                System.Diagnostics.Debug.WriteLine($"Argument parsing error: {ex.Message}");
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
        }

        private static void ShowFatalError(Exception ex)
        {
            try
            {
                MessageBox.Show(
                    $"An unexpected error occurred:\n\n{ex.Message}\n\n" +
                    "The application will now close.\n\n" +
                    "If this problem persists, please contact support@forensicbridge.ca",
                    "ForensicBridge Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);

                // Log to debug output
                System.Diagnostics.Debug.WriteLine($"FATAL ERROR: {ex}");
            }
            catch
            {
                // Last resort - can't even show message box
            }
        }
    }
}
