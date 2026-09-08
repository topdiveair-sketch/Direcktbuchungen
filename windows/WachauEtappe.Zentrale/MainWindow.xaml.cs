using System.Windows;
using System.Windows.Controls;

namespace WachauEtappe.Zentrale;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
    }

    private void Navigate_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button button && button.Tag is string page)
        {
            PageTitle.Text = page;
        }
    }
}
