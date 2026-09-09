using System.Globalization;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Models;
using WachauEtappe.Zentrale.Services;

namespace WachauEtappe.Zentrale;
public partial class OperationsWindow:Window
{
 private const decimal LuggagePricePerPiece=25m;
 private const decimal MinimumDailyLuggageRevenue=125m;
 private const string LuggageReadyBy="08:00";

 public OperationsWindow(){InitializeComponent();Loaded+=(_,_)=>LoadAll();}
 private void LoadAll(){HostBox.ItemsSource=App.Database.GetHosts().Where(h=>h.Published).ToList();StayDate.SelectedDate=DateTime.Today;EndDate.SelectedDate=DateTime.Today;DispatchDate.SelectedDate=DateTime.Today;AvailabilityBox.SelectedIndex=0;LuggageStatusBox.SelectedIndex=0;RefreshTables();RefreshDispatch();}
 private void RefreshTables(){AvailabilityGrid.ItemsSource=App.Database.QueryRows("SELECT a.StayDate,h.Name AS Gastgeber,a.Status,a.Price,a.Note FROM Availability a LEFT JOIN Hosts h ON h.Id=a.HostId ORDER BY a.StayDate,h.Name");LuggageGrid.ItemsSource=App.Database.QueryRows("SELECT l.Id,t.Reference,d.DayNumber,d.TravelDate,h1.Name AS Abholung,h2.Name AS Ziel,l.Status,l.Provider,l.Note FROM LuggageTransfers l JOIN Trips t ON t.Id=l.TripId LEFT JOIN TripDays d ON d.Id=l.TripDayId LEFT JOIN Hosts h1 ON h1.Id=l.PickupHostId LEFT JOIN Hosts h2 ON h2.Id=l.DropoffHostId ORDER BY d.TravelDate,t.Reference");PriorityGrid.ItemsSource=App.Database.GetCoveragePriorities().Select(x=>new{Ort=x.Location,FehlendeGastgeber=x.Need,Kandidaten=x.CandidateCount,Prioritaet=x.Need>=2?"HOCH":"NORMAL"}).ToList();RefreshPartnerNetwork();}
 private void RefreshPartnerNetwork()
 {
  var hosts=App.Database.GetHosts();
  var candidates=App.Database.GetCandidates();
  var points=new[]{
   new{Ort="Krems",Suchbegriffe=new[]{"krems"}},
   new{Ort="Dürnstein / Unterloiben",Suchbegriffe=new[]{"dürnstein","duernstein","unterloiben"}},
   new{Ort="Weißenkirchen / Wösendorf",Suchbegriffe=new[]{"weißenkirchen","weissenkirchen","wösendorf","woesendorf"}},
   new{Ort="Spitz",Suchbegriffe=new[]{"spitz"}},
   new{Ort="Mühldorf",Suchbegriffe=new[]{"mühldorf","muehldorf"}},
   new{Ort="Maria Laach",Suchbegriffe=new[]{"maria laach"}},
   new{Ort="Aggsbach Markt",Suchbegriffe=new[]{"aggsbach markt"}},
   new{Ort="Melk",Suchbegriffe=new[]{"melk"}},
   new{Ort="Aggsbach Dorf",Suchbegriffe=new[]{"aggsbach dorf"}},
   new{Ort="Arnsdorf / Hofarnsdorf",Suchbegriffe=new[]{"arnsdorf","hofarnsdorf","oberarnsdorf","bacharnsdorf"}},
   new{Ort="Rossatz",Suchbegriffe=new[]{"rossatz"}},
   new{Ort="Unterbergern / Mautern",Suchbegriffe=new[]{"unterbergern","mautern"}}
  };
  const int ziel=2;
  var rows=points.Select(p=>
  {
   bool Match(string location)=>p.Suchbegriffe.Any(s=>(location??"").Contains(s,StringComparison.OrdinalIgnoreCase));
   var active=hosts.Count(h=>h.Published&&h.AcceptingBookings&&h.OneNightVerified&&h.CashAtHostVerified&&Match(h.Location));
   var cand=candidates.Count(c=>Match(c.Location)&&!string.Equals(c.Status,"rejected",StringComparison.OrdinalIgnoreCase));
   var fehlt=Math.Max(0,ziel-active);
   var prioritaet=fehlt>=2?"KRITISCH":fehlt==1?"HOCH":"OK";
   return new{Ort=p.Ort,ZielPartner=ziel,AktivePartner=active,Fehlend=fehlt,Kandidaten=cand,Prioritaet=prioritaet};
  }).ToList();
  PartnerNetworkGrid.ItemsSource=rows;
  var covered=rows.Count(r=>r.Fehlend==0);
  var totalMissing=rows.Sum(r=>r.Fehlend);
  PartnerNetworkSummary.Text=$"{covered}/{rows.Count} strategische Punkte vollständig abgedeckt · noch {totalMissing} verlässliche Partner bis zum Zielnetz (2 je Punkt).";
 }
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
 private void RebuildLuggage_Click(object sender,RoutedEventArgs e){foreach(var t in App.Database.GetTrips().Where(x=>x.LuggageTransfer&&x.Status!="cancelled"&&x.Status!="completed"))App.Database.RebuildLuggageChain(t.Id);RefreshTables();RefreshDispatch();MessageBox.Show("Gepäckketten wurden neu berechnet.");}
 private void LuggageGrid_SelectionChanged(object sender,SelectionChangedEventArgs e){if(LuggageGrid.SelectedItem is not Dictionary<string,object?> row)return;ProviderBox.Text=Convert.ToString(row.GetValueOrDefault("Provider"))??"";LuggageNoteBox.Text=Convert.ToString(row.GetValueOrDefault("Note"))??"";var status=Convert.ToString(row.GetValueOrDefault("Status"))??"requested";foreach(var item in LuggageStatusBox.Items.OfType<ComboBoxItem>())if(string.Equals(item.Content?.ToString(),status,StringComparison.OrdinalIgnoreCase)){LuggageStatusBox.SelectedItem=item;break;}}
 private void SaveLuggage_Click(object sender,RoutedEventArgs e){if(LuggageGrid.SelectedItem is not Dictionary<string,object?> row||row.GetValueOrDefault("Id") is null)return;var id=Convert.ToInt64(row["Id"]);var status=(LuggageStatusBox.SelectedItem as ComboBoxItem)?.Content?.ToString()??"requested";App.Database.UpdateLuggageTransfer(id,ProviderBox.Text.Trim(),status,LuggageNoteBox.Text.Trim());LuggageStatusText.Text="✓ Gepäcktransport gespeichert.";RefreshTables();RefreshDispatch();}
 private void DispatchDate_SelectedDateChanged(object sender,SelectionChangedEventArgs e){if(IsLoaded)RefreshDispatch();}
 private void OptimizeDispatch_Click(object sender,RoutedEventArgs e){foreach(var t in App.Database.GetTrips().Where(x=>x.LuggageTransfer&&x.Status!="cancelled"&&x.Status!="completed"))App.Database.RebuildLuggageChain(t.Id);RefreshTables();RefreshDispatch();}
 private void RefreshDispatch()
 {
  var day=(DispatchDate.SelectedDate??DateTime.Today).ToString("yyyy-MM-dd");
  var guests=DailyDispatchService.GetGuestPositions(day);GuestPositionGrid.ItemsSource=guests;
  var plan=DailyDispatchService.BuildLuggageRoute(day);OptimizedLuggageGrid.ItemsSource=plan.Stops;
  var pieces=plan.Stops.Select(x=>x.TransferId).Distinct().Count();
  var revenue=pieces*LuggagePricePerPiece;
  var economics=revenue>=MinimumDailyLuggageRevenue
      ? $"✓ Mindestumsatz erreicht ({revenue:0} €)"
      : $"⚠ unter internem Tagesziel ({revenue:0} € von {MinimumDailyLuggageRevenue:0} €)";
  DispatchSummary.Text=$"{day} · Bereitstellung bis {LuggageReadyBy} Uhr · {guests.Count} gebuchte Gast-Etappe(n) · {pieces} Gepäckstück(e) à {LuggagePricePerPiece:0} € · {plan.Stops.Count} Stopp(s) · {economics} · geschätzte direkte Fahrstrecke ca. {plan.EstimatedKm:0.0} km · {plan.StartEnd}";
 }
}
