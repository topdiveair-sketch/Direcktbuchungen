using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;

public partial class BookingEditWindow : Window
{
    private readonly string? bookingId;
    public BookingEditWindow(string? id=null)
    {
        InitializeComponent();
        bookingId=id;
        Loaded+=(_,_)=>LoadForm();
    }

    private void LoadForm()
    {
        var hosts=App.Database.GetHosts().Where(h=>h.Published&&h.AcceptingBookings).OrderBy(h=>h.Location).ThenBy(h=>h.Name).ToList();
        HostBox.ItemsSource=hosts;
        StatusBox.SelectedIndex=0;
        StayDateBox.SelectedDate=DateTime.Today.AddDays(1);
        if(string.IsNullOrWhiteSpace(bookingId)){TitleText.Text="Neue Buchung";ReferenceText.Text="Referenz wird beim Speichern erzeugt";return;}
        var b=App.Database.GetBooking(bookingId);
        if(b is null){MessageBox.Show("Buchung wurde nicht gefunden.");Close();return;}
        TitleText.Text="Buchung bearbeiten";ReferenceText.Text=$"Referenz: {b.Reference}";
        HostBox.SelectedItem=hosts.FirstOrDefault(h=>h.Id==b.HostId);
        if(DateTime.TryParse(b.StayDate,out var date))StayDateBox.SelectedDate=date;
        GuestsBox.Text=b.Guests.ToString(CultureInfo.InvariantCulture);PriceBox.Text=b.Price?.ToString("0.00",CultureInfo.InvariantCulture)??"";
        GuestNameBox.Text=b.GuestName;EmailBox.Text=b.GuestEmail;PhoneBox.Text=b.GuestPhone;NoteBox.Text=b.Note;
        foreach(var item in StatusBox.Items.OfType<ComboBoxItem>())if(string.Equals(item.Content?.ToString(),b.Status,StringComparison.OrdinalIgnoreCase)){StatusBox.SelectedItem=item;break;}
    }

    private void Save_Click(object sender,RoutedEventArgs e)
    {
        if(HostBox.SelectedItem is not HostRecord host){MessageBox.Show("Bitte Gastgeber auswählen.");return;}
        if(StayDateBox.SelectedDate is not DateTime date){MessageBox.Show("Bitte Datum auswählen.");return;}
        if(string.IsNullOrWhiteSpace(GuestNameBox.Text)){MessageBox.Show("Bitte Gastnamen eingeben.");return;}
        if(!int.TryParse(GuestsBox.Text,out var guests)||guests<1){MessageBox.Show("Personenzahl ist ungültig.");return;}
        double? price=null;if(!string.IsNullOrWhiteSpace(PriceBox.Text)){if(!double.TryParse(PriceBox.Text.Replace(',','.'),NumberStyles.Any,CultureInfo.InvariantCulture,out var p)||p<0){MessageBox.Show("Preis ist ungültig.");return;}price=p;}
        var status=(StatusBox.SelectedItem as ComboBoxItem)?.Content?.ToString()??"requested";
        try
        {
            if(string.IsNullOrWhiteSpace(bookingId))
                App.Database.CreateBooking(host.Id,date.ToString("yyyy-MM-dd"),guests,GuestNameBox.Text.Trim(),EmailBox.Text.Trim(),PhoneBox.Text.Trim(),price,NoteBox.Text.Trim());
            else
                App.Database.UpdateBooking(bookingId,host.Id,date.ToString("yyyy-MM-dd"),guests,GuestNameBox.Text.Trim(),EmailBox.Text.Trim(),PhoneBox.Text.Trim(),price,status,NoteBox.Text.Trim());
            DialogResult=true;Close();
        }
        catch(Exception ex){MessageBox.Show(ex.Message,"Buchung",MessageBoxButton.OK,MessageBoxImage.Warning);}
    }

    private void Cancel_Click(object sender,RoutedEventArgs e){DialogResult=false;Close();}
}
