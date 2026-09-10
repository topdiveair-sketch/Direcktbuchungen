using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Services;

namespace WachauEtappe.Zentrale;

public partial class MainWindow : Window
{
    public MainWindow(){InitializeComponent();Loaded+=(_,_)=>RefreshDashboard();}
    private void RefreshDashboard(){var db=App.Database;db.EnsureBookingTables();db.EnsureBillingTables();db.EnsureMapTables();OpenTripsValue.Text=db.ScalarInt("SELECT COUNT(*) FROM Trips WHERE Status NOT IN ('completed','cancelled')").ToString();VerifiedHostsValue.Text=db.ScalarInt("SELECT COUNT(*) FROM Hosts WHERE Status='verified' AND Published=1").ToString();CandidatesValue.Text=db.ScalarInt("SELECT COUNT(*) FROM Candidates").ToString();CoverageGapsValue.Text=db.ScalarInt("SELECT COUNT(*) FROM Coverage WHERE Status='gap'").ToString();DatabaseStatus.Text=$"● Lokal bereit · {Path.GetFileName(db.DatabasePath)}";}

    private async Task SyncLiveStateAsync()
    {
        DatabaseStatus.Text="● WachauEtappe Live-Daten werden synchronisiert …";
        if(LiveCentralSyncService.IsConfigured)
            await HostLivePushService.PushPendingAsync(App.Database);
        var result=await LiveCentralSyncService.SyncAsync(App.Database,DateTime.Today.AddDays(-14),DateTime.Today.AddDays(365));
        DatabaseStatus.Text=result.Success
            ?$"● Live · {result.Hosts} Gastgeber · {result.Bookings} Buchungen · {result.Availability} Verfügbarkeiten"
            :"● Offline-Cache aktiv · Live-Sync nicht abgeschlossen";
        if(!result.Success && result.CredentialRequired)
            MessageBox.Show(result.Message,"WachauEtappe Live-Synchronisierung",MessageBoxButton.OK,MessageBoxImage.Information);
        else if(!result.Success)
            MessageBox.Show(result.Message,"WachauEtappe Live-Synchronisierung",MessageBoxButton.OK,MessageBoxImage.Warning);
    }

    private async void Navigate_Click(object sender,RoutedEventArgs e)
    {
        if(sender is not Button button||button.Tag is not string page)return;
        PageTitle.Text=page;
        if(page is "Wanderkarte" or "Verfügbarkeit" or "Unterkunft" or "Routenplaner" or "Buchungen" or "Gastgeber")
            await SyncLiveStateAsync();
        if(page=="Wanderkarte"){new WanderMapWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="Unterkunft"){new BookingWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="Buchungen"){new BookingManagementWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="Abrechnung"){new BillingWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="Gastgeber"){new HostManagementWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="Reisen"||page=="Routenplaner"){new TripManagementWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="Verfügbarkeit"||page=="Gepäck"){new OperationsWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="Kandidaten"){new CandidateManagementWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="Stornos"){new CancellationWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="System"){new SystemWindow{Owner=this}.ShowDialog();RefreshDashboard();return;}
        if(page=="Dashboard")RefreshDashboard();
    }
}
