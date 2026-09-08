using System.Windows;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;

public partial class BookingWindow : Window
{
    public BookingWindow()
    {
        InitializeComponent();
        DateBox.SelectedDate=DateTime.Today.AddDays(1);
    }

    private void Search_Click(object sender,RoutedEventArgs e)
    {
        var date=(DateBox.SelectedDate??DateTime.Today).ToString("yyyy-MM-dd");
        ResultsGrid.ItemsSource=App.Database.SearchBookableHosts(LocationBox.Text,date,LuggageBox.IsChecked==true);
    }

    private void CreateBooking_Click(object sender,RoutedEventArgs e)
    {
        if(ResultsGrid.SelectedItem is not BookingSearchResult host)
        {
            MessageBox.Show("Bitte zuerst einen Gastgeber auswählen.","WachauEtappe");
            return;
        }
        if(string.IsNullOrWhiteSpace(GuestNameBox.Text))
        {
            MessageBox.Show("Bitte den Namen des Gastes eingeben.","WachauEtappe");
            return;
        }
        var date=(DateBox.SelectedDate??DateTime.Today).ToString("yyyy-MM-dd");
        _=int.TryParse(GuestsBox.Text,out var guests); if(guests<1) guests=1;
        var reference=App.Database.CreateBooking(host.HostId,date,guests,GuestNameBox.Text.Trim(),GuestEmailBox.Text.Trim(),GuestPhoneBox.Text.Trim(),host.Price,"Unterkunftssuche WachauEtappe Zentrale");
        MessageBox.Show($"Reservierung {reference} wurde als Anfrage angelegt.\nZahlung: direkt beim Gastgeber.","WachauEtappe");
        Search_Click(sender,e);
    }
}
