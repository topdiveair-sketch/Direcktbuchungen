using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;
public partial class OperationsWindow:Window
{
 public OperationsWindow(){InitializeComponent();Loaded+=(_,_)=>LoadAll();}
 private void LoadAll(){HostBox.ItemsSource=App.Database.GetHosts().Where(h=>h.Published).ToList();StayDate.SelectedDate=DateTime.Today;AvailabilityBox.SelectedIndex=0;RefreshTables();}
 private void RefreshTables(){AvailabilityGrid.ItemsSource=App.Database.QueryRows("SELECT a.StayDate,h.Name AS Gastgeber,a.Status,a.Price,a.Note FROM Availability a LEFT JOIN Hosts h ON h.Id=a.HostId ORDER BY a.StayDate,h.Name");LuggageGrid.ItemsSource=App.Database.QueryRows("SELECT t.Reference,d.DayNumber,d.TravelDate,h1.Name AS Abholung,h2.Name AS Ziel,l.Status,l.Provider FROM LuggageTransfers l JOIN Trips t ON t.Id=l.TripId LEFT JOIN TripDays d ON d.Id=l.TripDayId LEFT JOIN Hosts h1 ON h1.Id=l.PickupHostId LEFT JOIN Hosts h2 ON h2.Id=l.DropoffHostId ORDER BY d.TravelDate,t.Reference");PriorityGrid.ItemsSource=App.Database.GetCoveragePriorities().Select(x=>new{Ort=x.Location,FehlendeGastgeber=x.Need,Kandidaten=x.CandidateCount,Prioritaet=x.Need>=2?"HOCH":"NORMAL"}).ToList();}
 private void SaveAvailability_Click(object sender,RoutedEventArgs e){if(HostBox.SelectedItem is not HostRecord h||StayDate.SelectedDate is not DateTime d)return;var status=(AvailabilityBox.SelectedItem as ComboBoxItem)?.Content?.ToString()??"unknown";double? price=double.TryParse(PriceBox.Text.Replace(',','.'),NumberStyles.Any,CultureInfo.InvariantCulture,out var p)?p:null;App.Database.SetAvailability(h.Id,d.ToString("yyyy-MM-dd"),status,price);RefreshTables();}
 private void RebuildLuggage_Click(object sender,RoutedEventArgs e){foreach(var t in App.Database.GetTrips().Where(x=>x.LuggageTransfer&&x.Status!="cancelled"&&x.Status!="completed"))App.Database.RebuildLuggageChain(t.Id);RefreshTables();MessageBox.Show("Gepäckketten wurden neu berechnet.");}
}
