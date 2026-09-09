using System.Globalization;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;
public partial class OperationsWindow:Window
{
 public OperationsWindow(){InitializeComponent();Loaded+=(_,_)=>LoadAll();}
 private void LoadAll(){HostBox.ItemsSource=App.Database.GetHosts().Where(h=>h.Published).ToList();StayDate.SelectedDate=DateTime.Today;EndDate.SelectedDate=DateTime.Today;AvailabilityBox.SelectedIndex=0;LuggageStatusBox.SelectedIndex=0;RefreshTables();}
 private void RefreshTables(){AvailabilityGrid.ItemsSource=App.Database.QueryRows("SELECT a.StayDate,h.Name AS Gastgeber,a.Status,a.Price,a.Note FROM Availability a LEFT JOIN Hosts h ON h.Id=a.HostId ORDER BY a.StayDate,h.Name");LuggageGrid.ItemsSource=App.Database.QueryRows("SELECT l.Id,t.Reference,d.DayNumber,d.TravelDate,h1.Name AS Abholung,h2.Name AS Ziel,l.Status,l.Provider,l.Note FROM LuggageTransfers l JOIN Trips t ON t.Id=l.TripId LEFT JOIN TripDays d ON d.Id=l.TripDayId LEFT JOIN Hosts h1 ON h1.Id=l.PickupHostId LEFT JOIN Hosts h2 ON h2.Id=l.DropoffHostId ORDER BY d.TravelDate,t.Reference");PriorityGrid.ItemsSource=App.Database.GetCoveragePriorities().Select(x=>new{Ort=x.Location,FehlendeGastgeber=x.Need,Kandidaten=x.CandidateCount,Prioritaet=x.Need>=2?"HOCH":"NORMAL"}).ToList();}
 private void SaveAvailability_Click(object sender,RoutedEventArgs e){if(HostBox.SelectedItem is not HostRecord h||StayDate.SelectedDate is not DateTime from)return;var to=EndDate.SelectedDate??from;var status=(AvailabilityBox.SelectedItem as ComboBoxItem)?.Content?.ToString()??"unknown";double? price=double.TryParse(PriceBox.Text.Replace(',','.'),NumberStyles.Any,CultureInfo.InvariantCulture,out var p)?p:null;var count=App.Database.SetAvailabilityRange(h.Id,from,to,status,price);AvailabilityStatusText.Text=$"✓ {count} Tag(e) für {h.Name} gespeichert.";RefreshTables();}
 private async void LoadOnlinePartners_Click(object sender,RoutedEventArgs e)
 {
  var baseUrl=PartnerApiBox.Text.Trim().TrimEnd('/');var password=PartnerAdminPassword.Password;
  if(string.IsNullOrWhiteSpace(baseUrl)||string.IsNullOrWhiteSpace(password)){PartnerOnlineStatus.Text="Bitte API und Admin-Passwort eingeben.";return;}
  try
  {
   PartnerOnlineStatus.Text="Partnerdaten werden geladen …";
   using var http=new HttpClient{Timeout=TimeSpan.FromSeconds(20)};
   using var req=new HttpRequestMessage(HttpMethod.Get,$"{baseUrl}/api/central/partner-availability");
   req.Headers.Add("X-Admin-Password",password);
   using var res=await http.SendAsync(req);
   var raw=await res.Content.ReadAsStringAsync();
   if(!res.IsSuccessStatusCode)throw new InvalidOperationException($"Serverfehler {(int)res.StatusCode}: {raw}");
   using var doc=JsonDocument.Parse(raw);var rows=new List<object>();
   if(doc.RootElement.TryGetProperty("rows",out var arr))foreach(var r in arr.EnumerateArray())rows.Add(new{
    Gastgeber=r.GetProperty("name").GetString(),Ort=r.GetProperty("location").GetString(),Datum=r.GetProperty("stay_date").GetString(),Status=r.GetProperty("status").GetString(),FreieZimmer=r.GetProperty("rooms_free").GetInt32(),Preis=r.TryGetProperty("price",out var pe)&&pe.ValueKind!=JsonValueKind.Null?pe.GetDouble():0,Fruehstueck=r.GetProperty("breakfast_mode").GetString(),FruehstueckAufpreis=r.GetProperty("breakfast_price").GetDouble(),Gepaeck=r.GetProperty("luggage_available").GetInt32()==1?"ja":"nein",Aktualisiert=r.GetProperty("updated_at").GetString()});
   PartnerOnlineGrid.ItemsSource=rows;PartnerOnlineStatus.Text=$"✓ {rows.Count} Partner-Verfügbarkeit(en) geladen.";
  }
  catch(Exception ex){PartnerOnlineStatus.Text=$"Fehler: {ex.Message}";}
 }
 private void RebuildLuggage_Click(object sender,RoutedEventArgs e){foreach(var t in App.Database.GetTrips().Where(x=>x.LuggageTransfer&&x.Status!="cancelled"&&x.Status!="completed"))App.Database.RebuildLuggageChain(t.Id);RefreshTables();MessageBox.Show("Gepäckketten wurden neu berechnet.");}
 private void LuggageGrid_SelectionChanged(object sender,SelectionChangedEventArgs e){if(LuggageGrid.SelectedItem is not Dictionary<string,object?> row)return;ProviderBox.Text=Convert.ToString(row.GetValueOrDefault("Provider"))??"";LuggageNoteBox.Text=Convert.ToString(row.GetValueOrDefault("Note"))??"";var status=Convert.ToString(row.GetValueOrDefault("Status"))??"requested";foreach(var item in LuggageStatusBox.Items.OfType<ComboBoxItem>())if(string.Equals(item.Content?.ToString(),status,StringComparison.OrdinalIgnoreCase)){LuggageStatusBox.SelectedItem=item;break;}}
 private void SaveLuggage_Click(object sender,RoutedEventArgs e){if(LuggageGrid.SelectedItem is not Dictionary<string,object?> row||row.GetValueOrDefault("Id") is null)return;var id=Convert.ToInt64(row["Id"]);var status=(LuggageStatusBox.SelectedItem as ComboBoxItem)?.Content?.ToString()??"requested";App.Database.UpdateLuggageTransfer(id,ProviderBox.Text.Trim(),status,LuggageNoteBox.Text.Trim());LuggageStatusText.Text="✓ Gepäcktransport gespeichert.";RefreshTables();}
}
