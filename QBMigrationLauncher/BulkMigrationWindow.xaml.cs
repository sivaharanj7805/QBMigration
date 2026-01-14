using System.Windows;

namespace QBMigrationLauncher
{
    public partial class BulkMigrationWindow : Window
    {
        public BulkMigrationWindow()
        {
            InitializeComponent();
            DataContext = new ViewModels.BulkMigrationViewModel();
        }
    }
}
