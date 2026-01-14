using System.Windows;
using QBMigrationLauncher.ViewModels;

namespace QBMigrationLauncher
{
    public partial class MainWindow : Window
    {
        public MainWindow()
        {
            InitializeComponent();
            DataContext = new MainViewModel();
        }
    }
}
