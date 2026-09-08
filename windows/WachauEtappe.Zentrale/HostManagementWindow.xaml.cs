using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;

public partial class HostManagementWindow : Window
{
    private HostRecord? selected;
    public HostManagementWindow(){ InitializeComponent(); Loaded += (_,_) => LoadHosts(); }
    private void LoadHosts(){ HostList.ItemsSource = App.Database.GetHosts(SearchBox.Text); }
    private void SearchBox_TextChanged(object sender, TextChangedEventArgs e){ if(IsLoaded) LoadHosts(); }
    private void HostList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        selected = HostList.SelectedItem as HostRecord; if(selected is null) return;
        HostIdText.Text = $"ID: {selected.Id} · Status: {selected.Status}"; NameBox.Text=selected.Name; LocationBox.Text=selected.Location;
        EmailBox.Text=selected.Email; PhoneBox.Text=selected.Phone; UrlBox.Text=selected.DirectUrl;
        OneNightCheck.IsChecked=selected.OneNightVerified; CashCheck.IsChecked=selected.CashAtHostVerified; LuggageCheck.IsChecked=selected.LuggageVerified; AcceptingCheck.IsChecked=selected.AcceptingBookings;
        StatusText.Text = selected.Published ? "✓ Öffentlich freigegeben" : "Noch nicht öffentlich freigegeben";
    }
    private void ApplyForm(){ if(selected is null) return; selected.Name=NameBox.Text.Trim(); selected.Location=LocationBox.Text.Trim(); selected.Email=EmailBox.Text.Trim(); selected.Phone=PhoneBox.Text.Trim(); selected.DirectUrl=UrlBox.Text.Trim(); selected.OneNightVerified=OneNightCheck.IsChecked==true; selected.CashAtHostVerified=CashCheck.IsChecked==true; selected.LuggageVerified=LuggageCheck.IsChecked==true; selected.AcceptingBookings=AcceptingCheck.IsChecked==true; }
    private void Save_Click(object sender, RoutedEventArgs e){ if(selected is null) return; ApplyForm(); App.Database.SaveHost(selected); StatusText.Text="✓ Änderungen lokal gespeichert und protokolliert."; LoadHosts(); }
    private void Publish_Click(object sender, RoutedEventArgs e)
    {
        if(selected is null) return; ApplyForm();
        if(!selected.OneNightVerified || !selected.CashAtHostVerified || !selected.LuggageVerified){ MessageBox.Show("Freigabe nicht möglich. 1-Nacht-Aufenthalt, Barzahlung und Gepäcktransport müssen bestätigt sein.","WachauEtappe Pflichtprüfung",MessageBoxButton.OK,MessageBoxImage.Warning); return; }
        selected.Status="verified"; selected.Published=true; App.Database.SaveHost(selected); StatusText.Text="✓ Gastgeber geprüft und öffentlich freigegeben."; LoadHosts();
    }
    private void Unpublish_Click(object sender, RoutedEventArgs e){ if(selected is null) return; ApplyForm(); selected.Published=false; App.Database.SaveHost(selected); StatusText.Text="Gastgeber wurde gesperrt und ist nicht öffentlich freigegeben."; LoadHosts(); }
}
