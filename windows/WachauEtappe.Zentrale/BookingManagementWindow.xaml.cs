using System.Windows;

namespace WachauEtappe.Zentrale;

public partial class BookingManagementWindow : Window
{
    public BookingManagementWindow(){InitializeComponent();Loaded+=(_,_)=>Refresh();}

    private void Refresh()=>BookingsGrid.ItemsSource=App.Database.GetBookings();

    private string? SelectedId()
    {
        if(BookingsGrid.SelectedItem is Dictionary<string,object?> row && row.TryGetValue("Id",out var id)) return id?.ToString();
        MessageBox.Show("Bitte zuerst eine Buchung auswählen.","WachauEtappe");
        return null;
    }

    private void SetStatus(string status)
    {
        var id=SelectedId(); if(string.IsNullOrWhiteSpace(id)) return;
        App.Database.SetBookingStatus(id,status); Refresh();
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

    private void Confirm_Click(object sender,RoutedEventArgs e)=>SetStatus("confirmed");
    private void Decline_Click(object sender,RoutedEventArgs e)=>SetStatus("declined");
    private void Cancel_Click(object sender,RoutedEventArgs e)=>SetStatus("cancelled");
    private void Refresh_Click(object sender,RoutedEventArgs e)=>Refresh();
}
