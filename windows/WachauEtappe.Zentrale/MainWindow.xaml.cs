using System.Windows;
using System.Windows.Controls;

namespace WachauEtappe.Zentrale;

public partial class MainWindow : Window
{
    public MainWindow(){ InitializeComponent(); Loaded += (_, _) => RefreshDashboard(); }
    private void RefreshDashboard()
    {
        var db=App.Database;
        OpenTripsValue.Text=db.ScalarInt("SELECT COUNT(*) FROM Trips WHERE Status NOT IN ('completed','cancelled')").ToString();
        VerifiedHostsValue.Text=db.ScalarInt("SELECT COUNT(*) FROM Hosts WHERE Status='verified' AND Published=1").ToString();
        CandidatesValue.Text=db.ScalarInt("SELECT COUNT(*) FROM Candidates").ToString();
        CoverageGapsValue.Text=db.ScalarInt("SELECT COUNT(*) FROM Coverage WHERE Status='gap'").ToString();
        DatabaseStatus.Text=$"● Lokal bereit · {System.IO.Path.GetFileName(db.DatabasePath)}";
    }
    private void Navigate_Click(object sender, RoutedEventArgs e)
    {
        if(sender is not Button button || button.Tag is not string page) return;
        PageTitle.Text=page;
        if(page=="Dashboard") RefreshDashboard();
        if(page=="Gastgeber") { var window=new HostManagementWindow{Owner=this}; window.ShowDialog(); RefreshDashboard(); PageTitle.Text="Dashboard"; }
    }
}
