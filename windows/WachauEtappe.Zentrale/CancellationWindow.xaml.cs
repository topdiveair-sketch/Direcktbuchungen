using System.Windows;

namespace WachauEtappe.Zentrale;

public partial class CancellationWindow : Window
{
    public CancellationWindow(){InitializeComponent();Loaded+=(_,_)=>LoadRows();}
    private void LoadRows()=>CancellationGrid.ItemsSource=App.Database.QueryRows("SELECT c.Id,c.TripId,t.Reference,COALESCE(t.GuestName,'') AS Gast,c.RequestedUtc,c.Status,c.FeePercent,c.Resold,COALESCE(c.Note,'') AS Note FROM Cancellations c LEFT JOIN Trips t ON t.Id=c.TripId ORDER BY c.RequestedUtc DESC");
    private long? SelectedId(){if(CancellationGrid.SelectedItem is IDictionary<string,object?> r&&r.TryGetValue("Id",out var v)&&v!=null)return Convert.ToInt64(v);return null;}
    private void Set(string status,bool? resold=null){var id=SelectedId();if(id is null){MessageBox.Show("Bitte zuerst ein Storno auswählen.");return;}if(resold.HasValue)App.Database.Execute("UPDATE Cancellations SET Status=@s,Resold=@r WHERE Id=@id",("@s",status),("@r",resold.Value?1:0),("@id",id.Value));else App.Database.Execute("UPDATE Cancellations SET Status=@s WHERE Id=@id",("@s",status),("@id",id.Value));App.Database.Audit("cancellation_reviewed","Cancellation",id.Value.ToString(),status);LoadRows();}
    private void Approve_Click(object sender,RoutedEventArgs e)=>Set("reviewed");
    private void Reject_Click(object sender,RoutedEventArgs e)=>Set("rejected");
    private void Resold_Click(object sender,RoutedEventArgs e)=>Set("resold",true);
    private void Refresh_Click(object sender,RoutedEventArgs e)=>LoadRows();
}