using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Services;

namespace WachauEtappe.Zentrale;

public partial class WachauOperationsWindow : Window
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(20) };
    private string _password = "";

    public WachauOperationsWindow()
    {
        InitializeComponent();
        PartnerDate.SelectedDate=DateTime.Today;
        Loaded += async (_, _) => await RefreshAsync();
    }

    private int SelectedDays()
    {
        var text=(DaysBox.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "30 Tage";
        return text.StartsWith("7 ") ? 7 : text.StartsWith("90 ") ? 90 : 30;
    }

    private HttpRequestMessage AdminRequest(HttpMethod method,string path,object? payload=null)
    {
        var req=new HttpRequestMessage(method,$"{LiveCentralSyncService.ApiBase}{path}");
        req.Headers.TryAddWithoutValidation("X-Admin-Password",_password);
        if(payload is not null)req.Content=new StringContent(JsonSerializer.Serialize(payload),Encoding.UTF8,"application/json");
        return req;
    }

    private async Task<JsonDocument?> SendAsync(HttpMethod method,string path,object? payload=null)
    {
        using var req=AdminRequest(method,path,payload);
        using var resp=await Http.SendAsync(req);
        var json=await resp.Content.ReadAsStringAsync();
        if(resp.StatusCode==HttpStatusCode.Unauthorized)throw new InvalidOperationException("Gespeicherter Railway-Adminzugang ist ungültig.");
        if(!resp.IsSuccessStatusCode)throw new InvalidOperationException($"Online-Zentrale antwortet mit HTTP {(int)resp.StatusCode}: {json}");
        return JsonDocument.Parse(json);
    }

    private async void Refresh_Click(object sender,RoutedEventArgs e)=>await RefreshAsync();
    private async void PartnerDate_SelectedDateChanged(object sender,SelectionChangedEventArgs e){if(IsLoaded)await LoadPartnersAsync();}

    private async Task RefreshAsync()
    {
        _password=LiveCentralSyncService.ReadAdminPassword();
        if(string.IsNullOrWhiteSpace(_password))
        {
            StatusText.Text="Railway-Adminzugang ist noch nicht eingerichtet. Bitte unter Gastgeber > Online-Verwaltung einmalig speichern und testen.";
            MessageBox.Show(StatusText.Text,"WachauEtappe Live Operations",MessageBoxButton.OK,MessageBoxImage.Information);
            return;
        }

        StatusText.Text="Live-Daten werden geladen …";
        try
        {
            await LoadSummaryAsync();
            await Task.WhenAll(LoadBookingsAsync(),LoadPartnersAsync(),LoadLeadsAsync());
            StatusText.Text=$"✓ Live verbunden · {DateTime.Now:dd.MM.yyyy HH:mm} · API {LiveCentralSyncService.ApiBase}";
        }
        catch(Exception ex){StatusText.Text=$"Live Operations nicht erreichbar: {ex.Message}";}
    }

    private async Task LoadSummaryAsync()
    {
        using var doc=await SendAsync(HttpMethod.Get,$"/api/central/wachauetappe-operations?days={SelectedDays()}");
        if(doc is null)return;var root=doc.RootElement;
        var replacements=new List<Dictionary<string,object?>>();
        if(root.TryGetProperty("replacementNeeds",out var repl)&&repl.ValueKind==JsonValueKind.Array)
            foreach(var x in repl.EnumerateArray())replacements.Add(new Dictionary<string,object?>
            {
                ["Reise"]=Str(x,"trip_reference"),["Nacht"]=Str(x,"stay_date"),["Ort"]=Str(x,"location"),
                ["Absage von"]=Str(x,"declined_host"),["Freie Alternativen"]=Int(x,"alternatives")
            });
        ReplacementGrid.ItemsSource=replacements;

        var due=Int(root,"dueRequests");var newLeads=Int(root,"newPartnerLeads");var todayStays=Int(root,"todayConfirmedStays");
        DueValue.Text=due.ToString();ReplacementValue.Text=replacements.Count.ToString();PartnerLeadsValue.Text=newLeads.ToString();TodayStaysValue.Text=todayStays.ToString();
        BookingValue.Text=$"{Double(root,"confirmedValue"):0.00} €";CommissionValue.Text=$"{Double(root,"estimatedCommission"):0.00} €";
        TodaySummaryText.Text=due==0&&replacements.Count==0&&newLeads==0
            ? $"✓ Keine kritischen offenen Aufgaben. {todayStays} bestätigte Übernachtung(en) heute."
            : $"Heute bearbeiten: {due} Anfrage(n) länger als 12h offen · {replacements.Count} Ersatzfall/-fälle · {newLeads} neue Partner-Lead(s) · {todayStays} bestätigte Übernachtung(en) heute.";
        TodayGrid.ItemsSource=new[]
        {
            new Dictionary<string,object?>{{"Priorität",due>0?"HOCH":"OK"},{"Aufgabe","Unbeantwortete Gästeanfragen"},{"Anzahl",due},{"Aktion","Im Tab Gästeanfragen bearbeiten"}},
            new Dictionary<string,object?>{{"Priorität",replacements.Count>0?"HOCH":"OK"},{"Aufgabe","Ersatzunterkünfte erforderlich"},{"Anzahl",replacements.Count},{"Aktion","Im Tab Ersatzunterkünfte prüfen"}},
            new Dictionary<string,object?>{{"Priorität",newLeads>0?"MITTEL":"OK"},{"Aufgabe","Neue Partner-Leads"},{"Anzahl",newLeads},{"Aktion","Kontakt aufnehmen und Status setzen"}},
            new Dictionary<string,object?>{{"Priorität","INFO"},{"Aufgabe","Bestätigte Aufenthalte heute"},{"Anzahl",todayStays},{"Aktion","Operativen Ablauf prüfen"}}
        };

        var trips=new List<Dictionary<string,object?>>();
        if(root.TryGetProperty("trips",out var tripsNode)&&tripsNode.ValueKind==JsonValueKind.Array)
            foreach(var x in tripsNode.EnumerateArray())trips.Add(new Dictionary<string,object?>
            {
                ["Reise"]=Str(x,"trip_reference"),["Zeitraum"]=$"{Str(x,"start_date")} – {Str(x,"end_date")}",
                ["Fortschritt"]=$"{Int(x,"confirmed")}/{Int(x,"nights")} bestätigt",["Offen"]=Int(x,"requested"),
                ["Absagen"]=Int(x,"declined"),["Status"]=TranslateStatus(Str(x,"status")),["Wert"]=$"{Double(x,"value"):0.00} €"
            });
        TripsGrid.ItemsSource=trips;
        TripSummaryText.Text=$"{trips.Count} Reisevorgänge · Bestätigungsquote {NullableDouble(root,"requestConfirmationPct")?.ToString("0.0") ?? "—"} %";

        var funnel=new List<Dictionary<string,object?>>();
        if(root.TryGetProperty("funnel",out var fn)&&fn.ValueKind==JsonValueKind.Object)
            foreach(var p in fn.EnumerateObject())funnel.Add(new Dictionary<string,object?>{{"Schritt",TranslateEvent(p.Name)},{"Anzahl",p.Value.TryGetInt32(out var n)?n:0}});
        FunnelGrid.ItemsSource=funnel;
    }

    private async Task LoadBookingsAsync()
    {
        using var doc=await SendAsync(HttpMethod.Get,"/api/central/wachauetappe-bookings");
        if(doc is null)return;var items=new List<Dictionary<string,object?>>();
        foreach(var x in doc.RootElement.GetProperty("items").EnumerateArray())items.Add(new Dictionary<string,object?>
        {
            ["Referenz"]=Str(x,"reference"),["Reise"]=Str(x,"trip_reference"),["Datum"]=Str(x,"stay_date"),["Gast"]=Str(x,"guest_name"),
            ["Personen"]=Int(x,"guests"),["Gastgeber"]=Str(x,"host_name"),["Ort"]=Str(x,"location"),["Status"]=TranslateBookingStatus(Str(x,"status")),
            ["Alter h"]=Int(x,"age_hours"),["Fällig"]=Bool(x,"reminder_due")?"JA":"",["Preis"]=x.TryGetProperty("price",out var p)&&p.ValueKind!=JsonValueKind.Null?$"{p.GetDouble():0.00} €":"—",
            ["Nachricht"]=Str(x,"note")
        });
        BookingsGrid.ItemsSource=items;
        var open=items.Count(x=>Equals(x["Status"],"offen"));var due=items.Count(x=>Equals(x["Fällig"],"JA"));
        BookingSummaryText.Text=$"{open} offen · {due} Antwort(en) fällig";
    }

    private async Task LoadPartnersAsync()
    {
        if(string.IsNullOrWhiteSpace(_password))return;
        var day=(PartnerDate.SelectedDate??DateTime.Today).ToString("yyyy-MM-dd");
        using var doc=await SendAsync(HttpMethod.Get,$"/api/central/wachauetappe-partners?date={day}");
        if(doc is null)return;var items=new List<Dictionary<string,object?>>();
        foreach(var x in doc.RootElement.GetProperty("items").EnumerateArray())items.Add(new Dictionary<string,object?>
        {
            ["ID"]=Str(x,"host_id"),["Gastgeber"]=Str(x,"name"),["Ort"]=Str(x,"location"),["Aktiv"]=Int(x,"active")>0?"Ja":"Nein",
            ["Zimmer gesamt"]=Int(x,"rooms_total"),["Status"]=Str(x,"status"),["Frei"]=Int(x,"rooms_free"),
            ["Booking blockiert"]=Int(x,"booking_blocked")>0?"Ja":"Nein",["Preis"]=x.TryGetProperty("price",out var p)&&p.ValueKind!=JsonValueKind.Null?$"{p.GetDouble():0.00} €":"—",
            ["Frühstück"]=Str(x,"breakfast_mode"),["Gepäck"]=Int(x,"luggage_available")>0?"Ja":"Nein"
        });
        PartnersGrid.ItemsSource=items;
        var free=items.Sum(x=>Convert.ToInt32(x["Frei"]??0));PartnerSummaryText.Text=$"{items.Count} Partner · {free} freie Zimmer am {day}";
    }

    private async Task LoadLeadsAsync()
    {
        using var doc=await SendAsync(HttpMethod.Get,"/api/central/wachauetappe-leads");
        if(doc is null)return;var items=new List<Dictionary<string,object?>>();
        foreach(var x in doc.RootElement.GetProperty("items").EnumerateArray())items.Add(new Dictionary<string,object?>
        {
            ["ID"]=Int(x,"id"),["Betrieb"]=Str(x,"business_name"),["Kontakt"]=Str(x,"contact_name"),["Ort"]=Str(x,"location"),["E-Mail"]=Str(x,"email"),
            ["Telefon"]=Str(x,"phone"),["Zimmer"]=Str(x,"rooms"),["Quelle"]=Str(x,"source"),["Status"]=Str(x,"status"),["Eingang"]=Str(x,"created_at"),["Nachricht"]=Str(x,"message")
        });
        LeadsGrid.ItemsSource=items;LeadSummaryText.Text=$"{items.Count} Leads · {items.Count(x=>Equals(x["Status"],"new"))} neu";
    }

    private async void ConfirmBooking_Click(object sender,RoutedEventArgs e)=>await UpdateSelectedBookingAsync("confirmed");
    private async void DeclineBooking_Click(object sender,RoutedEventArgs e)=>await UpdateSelectedBookingAsync("declined");

    private async Task UpdateSelectedBookingAsync(string status)
    {
        if(BookingsGrid.SelectedItem is not Dictionary<string,object?> row||row.GetValueOrDefault("Referenz") is not string reference||string.IsNullOrWhiteSpace(reference))
        {MessageBox.Show("Bitte zuerst eine Gästeanfrage auswählen.");return;}
        var verb=status=="confirmed"?"bestätigen":"ablehnen";
        if(MessageBox.Show($"Anfrage {reference} wirklich {verb}?","WachauEtappe",MessageBoxButton.YesNo,MessageBoxImage.Question)!=MessageBoxResult.Yes)return;
        try{using var _=await SendAsync(HttpMethod.Patch,$"/api/central/wachauetappe-bookings/{Uri.EscapeDataString(reference)}",new{status});await RefreshAsync();}
        catch(Exception ex){MessageBox.Show(ex.Message,"Aktion fehlgeschlagen",MessageBoxButton.OK,MessageBoxImage.Warning);}
    }

    private async void SaveLeadStatus_Click(object sender,RoutedEventArgs e)
    {
        if(LeadsGrid.SelectedItem is not Dictionary<string,object?> row){MessageBox.Show("Bitte zuerst einen Partner-Lead auswählen.");return;}
        var id=Convert.ToInt32(row["ID"]);var status=(LeadStatusBox.SelectedItem as ComboBoxItem)?.Content?.ToString()??"contacted";
        try{using var _=await SendAsync(HttpMethod.Patch,$"/api/central/wachauetappe-leads/{id}",new{status});await LoadLeadsAsync();await LoadSummaryAsync();}
        catch(Exception ex){MessageBox.Show(ex.Message,"Lead-Status",MessageBoxButton.OK,MessageBoxImage.Warning);}
    }

    private static string TranslateStatus(string value)=>value switch{"confirmed"=>"bestätigt","needs_alternative"=>"Ersatz erforderlich","pending"=>"Bestätigungen laufen",_=>value};
    private static string TranslateBookingStatus(string value)=>value switch{"confirmed"=>"bestätigt","declined"=>"abgelehnt","requested"=>"offen",_=>value};
    private static string TranslateEvent(string value)=>value switch{"planner_view"=>"Planer geöffnet","trip_planned"=>"Reise geplant","host_selected"=>"Gastgeber gewählt","trip_request_started"=>"Anfrage begonnen","trip_request_submitted"=>"Anfrage gesendet","my_trip_opened"=>"Meine Reise geöffnet",_=>value};
    private static string Str(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.ValueKind!=JsonValueKind.Null?v.ToString():"";
    private static int Int(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.TryGetInt32(out var x)?x:0;
    private static bool Bool(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.ValueKind==JsonValueKind.True;
    private static double Double(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.TryGetDouble(out var x)?x:0;
    private static double? NullableDouble(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.ValueKind!=JsonValueKind.Null&&v.TryGetDouble(out var x)?x:null;
}
