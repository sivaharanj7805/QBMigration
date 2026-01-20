using System;
using System.Windows;
using QBDesktopExtractor;

namespace QBMigrationLauncher
{
    /// <summary>
    /// Application entry point - Shows LoginWindow first for authentication
    /// </summary>
    public partial class App : Application
    {
        /// <summary>
        /// Current user session (set after successful login)
        /// </summary>
        public static SessionData? CurrentSession { get; set; }
        
        /// <summary>
        /// Current license status (set after validation)
        /// </summary>
        public static LicenseResult? LicenseResult { get; set; }
        
        /// <summary>
        /// Application startup - Show login window first
        /// </summary>
        protected override void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);
            
            // Show login window as the first window
            var loginWindow = new LoginWindow();
            loginWindow.Show();
        }
        
        /// <summary>
        /// Check if user is authenticated
        /// </summary>
        public static bool IsAuthenticated => CurrentSession != null && !string.IsNullOrEmpty(CurrentSession.Token);
        
        /// <summary>
        /// Check if license is valid
        /// </summary>
        public static bool HasValidLicense => LicenseResult != null && LicenseResult.Valid && LicenseResult.HasMigrationsRemaining;
        
        /// <summary>
        /// Get remaining migrations
        /// </summary>
        public static int RemainingMigrations => LicenseResult?.RemainingMigrations ?? 0;
        
        /// <summary>
        /// Logout and return to login window
        /// </summary>
        public static void Logout()
        {
            CurrentSession = null;
            LicenseResult = null;
            
            // Delete session file
            try
            {
                var sessionPath = System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "ForensicBridge", "session.dat"
                );
                if (System.IO.File.Exists(sessionPath))
                    System.IO.File.Delete(sessionPath);
            }
            catch { }
            
            // Close all windows and show login
            foreach (Window window in Current.Windows)
            {
                if (!(window is LoginWindow))
                    window.Close();
            }
            
            var loginWindow = new LoginWindow();
            loginWindow.Show();
        }
    }
}
