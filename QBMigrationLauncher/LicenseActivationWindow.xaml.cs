using System;
using System.Windows;
using System.Windows.Media;
using QBDesktopExtractor;

namespace QBMigrationLauncher
{
    /// <summary>
    /// License Activation Window - Activates license key on this machine
    /// Uses LicenseValidator from QBDesktopReader
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
            var licenseKey = LicenseKeyTextBox.Text?.Trim().ToUpperInvariant();
            
            // Validation
            if (string.IsNullOrEmpty(licenseKey))
            {
                ShowStatus("Please enter your license key.", false);
                return;
            }
            
            // Validate format (FB-XXXX-XXXX-XXXX-XXXX)
            if (!System.Text.RegularExpressions.Regex.IsMatch(licenseKey, @"^FB-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"))
            {
                ShowStatus("Invalid license key format. Expected: FB-XXXX-XXXX-XXXX-XXXX", false);
                return;
            }
            
            ShowLoading(true);
            
            try
            {
                // Activate license using LicenseValidator
                var result = await LicenseValidator.ActivateAsync(licenseKey);
                
                if (result.Valid)
                {
                    ShowStatus($"✅ License activated successfully!\n{result.GetDisplayStatus()}", true);
                    
                    // Store in App for MainWindow to use
                    App.LicenseResult = result;
                    
                    // Wait a moment to show success, then close
                    await System.Threading.Tasks.Task.Delay(1500);
                    
                    this.DialogResult = true;
                    this.Close();
                }
                else
                {
                    ShowStatus($"❌ {result.Error}", false);
                }
            }
            catch (Exception ex)
            {
                ShowStatus($"Activation failed: {ex.Message}", false);
            }
            finally
            {
                ShowLoading(false);
            }
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
