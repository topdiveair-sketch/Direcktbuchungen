using System.Windows;
using WachauEtappe.Zentrale.Services;

namespace WachauEtappe.Zentrale;

public partial class BookingManagementWindow : Window
{
    public BookingManagementWindow(){InitializeComponent();Loaded+=async (_,_)=>{await SyncAndRefreshAsync();};}

    private void Refresh()=>BookingsGrid.ItemsSource=App.Database.GetBookings();

    private async Task SyncAndRefreshAsync()
    {
        if(LiveCentralSyncService.IsConfigured) await LiveCentralSyncService.SyncAsync(App.Database);
        Refresh();
    }

    private string? SelectedId()
    {
        if(BookingsGrid.SelectedItem is Dictionary<string,object?> row && row.TryGetValue("Id",out var id)) return id?.ToString();
        MessageBox.Show("Bitte zuerst eine Buchung auswählen.","WachauEtappe");
        return null;
    }

    private async Task SetStatusAsync(string status)
    {
        var id=SelectedId(); if(string.IsNullOrWhiteSpace(id)) return;
        var booking=App.Database.GetBooking(id); if(booking is null)return;
        App.Database.SetBookingStatus(id,status);
        Refresh();
        if(booking.Reference.StartsWith("WE-",StringComparison.OrdinalIgnoreCase))
        {
            var ok=await LiveCentralSyncService.PushBookingStatusAsync(booking.Reference,status);
            if(!ok)
                MessageBox.Show("Status wurde lokal gespeichert, konnte aber noch nicht an die Live-Zentrale übertragen werden. Der nächste Live-Abgleich bleibt möglich.","WachauEtappe Live",MessageBoxButton.OK,MessageBoxImage.Warning);
            else
                await SyncAndRefreshAsync();
        }
    }

    private void New_Click(object sender,RoutedEventArgs e)
    {
        var w=new BookingEditWindow{Owner=this};
        if(w.ShowDialog()==true)Refresh();
    }

    private void Edit_Click(object sender,RoutedEventArgs e)
    {
        var id=SelectedId();if(string.IsNullOrWhiteSpace(id))return;
        var w=new BookingEditWindow(id){Owner=this};
        if(w.ShowDialog()==true)Refresh();
    }

    private void Delete_Click(object sender,RoutedEventArgs e)
    {
        var id=SelectedId();if(string.IsNullOrWhiteSpace(id))return;
        var booking=App.Database.GetBooking(id);if(booking is null)return;
        var text=booking.Status=="confirmed"
            ?$"Die Buchung {booking.Reference} ist BESTÄTIGT. Wirklich endgültig löschen?\n\nDer Vorgang bleibt im Audit-Protokoll erhalten."
            :$"Buchung {booking.Reference} wirklich löschen?\n\nDer Vorgang bleibt im Audit-Protokoll erhalten.";
        if(MessageBox.Show(text,"Buchung löschen",MessageBoxButton.YesNo,MessageBoxImage.Warning)!=MessageBoxResult.Yes)return;
        App.Database.DeleteBooking(id);Refresh();
    }

    private async void Confirm_Click(object sender,RoutedEventArgs e)=>await SetStatusAsync("confirmed");
    private async void Decline_Click(object sender,RoutedEventArgs e)=>await SetStatusAsync("declined");
    private async void Cancel_Click(object sender,RoutedEventArgs e)=>await SetStatusAsync("cancelled");
    private async void Refresh_Click(object sender,RoutedEventArgs e)=>await SyncAndRefreshAsync();
}
