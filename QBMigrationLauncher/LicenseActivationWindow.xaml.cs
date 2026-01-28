using System;
using System.Windows;
using System.Windows.Media;
using QBDesktopExtractor;

namespace QBMigrationLauncher
{
    /// <summary>
    /// Session Activation Window - Activates Session ID on this machine
    /// Uses SessionValidator from QBDesktopReader
    ///
    /// Session ID format: FB-YYYYMMDDHHMMSS-XXXXXXXX
    /// Example: FB-20260128170624-AXO52A38
    /// </summary>
    public partial class LicenseActivationWindow : Window
    {
        public LicenseActivationWindow()
        {
            InitializeComponent();
        }

        /// <summary>
        /// Handle Activate button click
        /// </summary>
        private async void ActivateButton_Click(object sender, RoutedEventArgs e)
        {
            var sessionId = LicenseKeyTextBox.Text?.Trim().ToUpperInvariant();

            // Validation
            if (string.IsNullOrEmpty(sessionId))
            {
                ShowStatus("Please enter your Session ID.", false);
                return;
            }

            // Validate format (FB-YYYYMMDDHHMMSS-XXXXXXXX)
            if (!IsValidSessionIdFormat(sessionId))
            {
                ShowStatus("Invalid Session ID format.\nExpected: FB-YYYYMMDDHHMMSS-XXXXXXXX\nExample: FB-20260128170624-AXO52A38", false);
                return;
            }

            ShowLoading(true);

            try
            {
                // First validate the session
                var validateResult = await SessionValidator.ValidateAsync(sessionId);

                if (!validateResult.Valid)
                {
                    ShowStatus($"❌ {validateResult.Error}", false);
                    return;
                }

                // If new device, activate it
                if (validateResult.IsNewDevice)
                {
                    var activateResult = await SessionValidator.ActivateAsync(sessionId);

                    if (!activateResult.Valid)
                    {
                        ShowStatus($"❌ {activateResult.Error}", false);
                        return;
                    }
                }

                // Build display status
                var status = $"✅ Session activated successfully!\n\n" +
                             $"Project: {validateResult.ProjectName}\n" +
                             $"Client: {validateResult.ClientName}\n" +
                             $"Tier: {validateResult.TierName}\n" +
                             $"Remaining Extractions: {validateResult.RemainingExtractions}";

                ShowStatus(status, true);

                // Store session result for MainWindow to use
                App.SessionResult = validateResult;

                // Wait a moment to show success, then close
                await System.Threading.Tasks.Task.Delay(1500);

                this.DialogResult = true;
                this.Close();
            }
            catch (Exception ex)
            {
                ShowStatus($"Session validation failed: {ex.Message}", false);
            }
            finally
            {
                ShowLoading(false);
            }
        }

        /// <summary>
        /// Validate Session ID format: FB-YYYYMMDDHHMMSS-XXXXXXXX
        /// </summary>
        private bool IsValidSessionIdFormat(string sessionId)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
                return false;

            sessionId = sessionId.Trim().ToUpperInvariant();

            // Must start with FB-
            if (!sessionId.StartsWith("FB-"))
                return false;

            // Split into parts
            var parts = sessionId.Split('-');
            if (parts.Length != 3)
                return false;

            // Middle part should be timestamp (14 digits)
            if (parts[1].Length != 14 || !long.TryParse(parts[1], out _))
                return false;

            // Last part should be 8 alphanumeric characters
            if (parts[2].Length != 8)
                return false;

            return true;
        }

        /// <summary>
        /// Handle Cancel button click
        /// </summary>
        private void CancelButton_Click(object sender, RoutedEventArgs e)
        {
            this.DialogResult = false;
            this.Close();
        }

        /// <summary>
        /// Handle Purchase link click
        /// </summary>
        private void PurchaseLink_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = "https://forensicbridge.ca/pricing",
                    UseShellExecute = true
                });
            }
            catch
            {
                ShowStatus("Unable to open browser. Visit https://forensicbridge.ca/pricing", false);
            }
        }

        private void ShowLoading(bool show)
        {
            Dispatcher.Invoke(() =>
            {
                LoadingText.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
                ActivateButton.IsEnabled = !show;
                LicenseKeyTextBox.IsEnabled = !show;
            });
        }

        private void ShowStatus(string message, bool success)
        {
            Dispatcher.Invoke(() =>
            {
                StatusMessage.Text = message;
                StatusMessage.Foreground = success
                    ? new SolidColorBrush(Color.FromRgb(16, 185, 129))  // Green
                    : new SolidColorBrush(Color.FromRgb(239, 68, 68)); // Red
                StatusMessage.Visibility = Visibility.Visible;
            });
        }
    }
}
