using System;
using System.Windows;

namespace QBMigrationLauncher
{
    public partial class BulkMigrationWindow : Window
    {
        private readonly ViewModels.BulkMigrationViewModel _viewModel;

        public BulkMigrationWindow()
        {
            InitializeComponent();
            _viewModel = new ViewModels.BulkMigrationViewModel();
            DataContext = _viewModel;

            // FIX MEDIUM: Subscribe to Closed event to dispose ViewModel
            Closed += OnWindowClosed;
        }

        /// <summary>
        /// FIX MEDIUM: Dispose ViewModel when window is closed to prevent memory leaks.
        /// The ViewModel subscribes to events that need to be unsubscribed.
        /// </summary>
        private void OnWindowClosed(object? sender, EventArgs e)
        {
            // Unsubscribe from event to prevent memory leaks
            Closed -= OnWindowClosed;

            // Dispose the ViewModel to unsubscribe from its event handlers
            try
            {
                _viewModel?.Dispose();
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[WARN] Error disposing ViewModel: {ex.Message}");
            }
        }
    }
}
