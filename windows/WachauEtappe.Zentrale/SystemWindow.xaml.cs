using Microsoft.Win32;
using System.Windows;

namespace WachauEtappe.Zentrale;

public partial class SystemWindow : Window
{
    public SystemWindow(){InitializeComponent();Loaded+=(_,_)=>{DbPathText.Text=App.Database.DatabasePath;RefreshAudit();};}

    private void Backup_Click(object sender,RoutedEventArgs e)
    {
        var dlg=new SaveFileDialog{Filter="WachauEtappe Backup (*.db)|*.db",FileName=$"wachauetappe-backup-{DateTime.Now:yyyyMMdd-HHmm}.db"};
        if(dlg.ShowDialog()==true){App.Database.BackupTo(dlg.FileName);StatusText.Text="✓ Backup erstellt.";RefreshAudit();}
    }

    private void Restore_Click(object sender,RoutedEventArgs e)
    {
        var dlg=new OpenFileDialog{Filter="WachauEtappe Backup (*.db)|*.db"};
        if(dlg.ShowDialog()!=true)return;
        if(MessageBox.Show("Die aktuelle Datenbank wird vor der Wiederherstellung automatisch gesichert. Fortfahren?","WachauEtappe",MessageBoxButton.YesNo,MessageBoxImage.Warning)!=MessageBoxResult.Yes)return;
        App.Database.RestoreFrom(dlg.FileName);StatusText.Text="✓ Backup wiederhergestellt. Bitte WachauEtappe Zentrale neu starten.";
    }

    private void Export(string fileName,string sql)
    {
        var dlg=new SaveFileDialog{Filter="CSV (*.csv)|*.csv",FileName=fileName};
        if(dlg.ShowDialog()==true){App.Database.ExportCsv(sql,dlg.FileName);StatusText.Text="✓ CSV exportiert.";RefreshAudit();}
    }

    private void RefreshAudit()=>AuditGrid.ItemsSource=App.Database.QueryRows("SELECT CreatedUtc AS Zeit,EventType AS Ereignis,EntityType AS Bereich,EntityId AS ID,Details FROM AuditEvents ORDER BY Id DESC LIMIT 250");
    private void RefreshAudit_Click(object sender,RoutedEventArgs e)=>RefreshAudit();
    private void ExportBookings_Click(object sender,RoutedEventArgs e){App.Database.EnsureBookingTables();Export("wachauetappe-buchungen.csv","SELECT b.Reference,h.Name AS Gastgeber,b.StayDate AS Datum,b.Guests AS Personen,b.GuestName AS Gast,b.GuestEmail AS Email,b.GuestPhone AS Telefon,b.Status,b.Price AS Preis,b.PaymentMethod AS Zahlung FROM Bookings b JOIN Hosts h ON h.Id=b.HostId ORDER BY b.StayDate");}
    private void ExportHosts_Click(object sender,RoutedEventArgs e)=>Export("wachauetappe-gastgeber.csv","SELECT Name,Location AS Ort,Status,Published AS Freigegeben,AcceptingBookings AS Buchungen,Email,Phone,DirectUrl FROM Hosts ORDER BY Location,Name");
    private void ExportTrips_Click(object sender,RoutedEventArgs e)=>Export("wachauetappe-reisen.csv","SELECT Reference,GuestName AS Gast,GuestEmail AS Email,Guests AS Personen,StartDate,StartPlace,EndPlace,DailyTargetKm,LuggageTransfer,Status FROM Trips ORDER BY StartDate");
}
