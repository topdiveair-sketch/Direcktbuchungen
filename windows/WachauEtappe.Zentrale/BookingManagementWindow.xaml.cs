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

    private void Confirm_Click(object sender,RoutedEventArgs e)=>SetStatus("confirmed");
    private void Decline_Click(object sender,RoutedEventArgs e)=>SetStatus("declined");
    private void Cancel_Click(object sender,RoutedEventArgs e)=>SetStatus("cancelled");
    private void Refresh_Click(object sender,RoutedEventArgs e)=>Refresh();
}
