using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;

public partial class TripManagementWindow : Window
{
    private TripRecord? selected;
    public TripManagementWindow(){InitializeComponent();Loaded+=(_,_)=>LoadTrips();}
    private void LoadTrips(){TripList.ItemsSource=App.Database.GetTrips();}
    private void NewTrip_Click(object sender,RoutedEventArgs e){selected=new TripRecord();ReferenceText.Text="Neue Reise · Referenz wird beim Speichern erzeugt";GuestBox.Text=EmailBox.Text=PhoneBox.Text="";StartDatePicker.SelectedDate=DateTime.Today;DailyKmBox.Text="18";GuestsBox.Text="1";LuggageCheck.IsChecked=false;DaysGrid.ItemsSource=null;}
    private void TripList_SelectionChanged(object sender,SelectionChangedEventArgs e){selected=TripList.SelectedItem as TripRecord;if(selected is null)return;ReferenceText.Text=selected.Reference;GuestBox.Text=selected.GuestName;EmailBox.Text=selected.GuestEmail;PhoneBox.Text=selected.GuestPhone;if(DateTime.TryParse(selected.StartDate,out var d))StartDatePicker.SelectedDate=d;DailyKmBox.Text=selected.DailyTargetKm.ToString(CultureInfo.InvariantCulture);GuestsBox.Text=selected.Guests.ToString();LuggageCheck.IsChecked=selected.LuggageTransfer;RefreshDays();}
    private void Apply(){if(selected is null)return;selected.GuestName=GuestBox.Text.Trim();selected.GuestEmail=EmailBox.Text.Trim();selected.GuestPhone=PhoneBox.Text.Trim();selected.StartDate=StartDatePicker.SelectedDate?.ToString("yyyy-MM-dd")??"";if(double.TryParse(DailyKmBox.Text.Replace(',','.'),NumberStyles.Any,CultureInfo.InvariantCulture,out var km))selected.DailyTargetKm=km;if(int.TryParse(GuestsBox.Text,out var g))selected.Guests=Math.Max(1,g);selected.LuggageTransfer=LuggageCheck.IsChecked==true;}
    private void SaveTrip_Click(object sender,RoutedEventArgs e){if(selected is null)NewTrip_Click(sender,e);Apply();if(selected is null)return;App.Database.SaveTrip(selected);ReferenceText.Text=selected.Reference;StatusText.Text="✓ Reise gespeichert und protokolliert.";LoadTrips();}
    private void RefreshDays(){if(selected is null)return;DaysGrid.ItemsSource=App.Database.GetTripDays(selected.Id);}
    private void AddDay_Click(object sender,RoutedEventArgs e){if(selected is null){MessageBox.Show("Bitte zuerst eine Reise anlegen.");return;}Apply();App.Database.SaveTrip(selected);var days=App.Database.GetTripDays(selected.Id);var n=days.Count+1;var date=(StartDatePicker.SelectedDate??DateTime.Today).AddDays(n-1).ToString("yyyy-MM-dd");App.Database.AddTripDay(selected.Id,n,date,days.LastOrDefault()?.ToPlace??"Start","Übernachtungsort",selected.DailyTargetKm,null,selected.LuggageTransfer);RefreshDays();StatusText.Text="Etappe angelegt. Ziel, Distanz und Gastgeber werden im nächsten Planungsschritt konkret zugeordnet.";}
    private TripDayRecord? CurrentDay()=>DaysGrid.SelectedItem as TripDayRecord;
    private void ConfirmDay_Click(object sender,RoutedEventArgs e){var d=CurrentDay();if(d is null)return;App.Database.SetTripDayStatus(d.Id,"confirmed",d.LuggageStatus);RefreshDays();StatusText.Text="✓ Übernachtung für diese Etappe bestätigt.";}
    private void ConfirmLuggage_Click(object sender,RoutedEventArgs e){var d=CurrentDay();if(d is null)return;App.Database.SetTripDayStatus(d.Id,d.BookingStatus,"confirmed");RefreshDays();StatusText.Text="✓ Gepäckübergabe bestätigt.";}
    private void Cancel_Click(object sender,RoutedEventArgs e){if(selected is null)return;var d=CurrentDay();App.Database.RequestCancellation(selected.Id,d?.Id,0,"Gebühr noch manuell zu prüfen; keine automatische Abbuchung.");StatusText.Text="Storno erfasst. Gebühr bleibt bis zur Prüfung offen; es wird nichts automatisch eingezogen.";}
}
