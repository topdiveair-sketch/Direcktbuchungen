using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Services;

namespace WachauEtappe.Zentrale;

public partial class WachauOperationsWindow : Window
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(20) };

    public WachauOperationsWindow()
    {
        InitializeComponent();
        Loaded += async (_, _) => await RefreshAsync();
    }

    private int SelectedDays()
    {
        var text=(DaysBox.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "30 Tage";
        return text.StartsWith("7 ") ? 7 : text.StartsWith("90 ") ? 90 : 30;
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async Task RefreshAsync()
    {
        var password=LiveCentralSyncService.ReadAdminPassword();
        if(string.IsNullOrWhiteSpace(password))
        {
            StatusText.Text="Railway-Adminzugang ist noch nicht eingerichtet. Bitte unter Gastgeber > Online-Verwaltung einmalig speichern und testen.";
            MessageBox.Show(StatusText.Text,"WachauEtappe Live Operations",MessageBoxButton.OK,MessageBoxImage.Information);
            return;
        }

        StatusText.Text="Live-Daten werden geladen …";
        try
        {
            using var req=new HttpRequestMessage(HttpMethod.Get,$"{LiveCentralSyncService.ApiBase}/api/central/wachauetappe-operations?days={SelectedDays()}");
            req.Headers.TryAddWithoutValidation("X-Admin-Password",password);
            using var resp=await Http.SendAsync(req);
            var json=await resp.Content.ReadAsStringAsync();

            if(resp.StatusCode==HttpStatusCode.Unauthorized)
            {
                StatusText.Text="Gespeicherter Railway-Adminzugang ist ungültig.";
                return;
            }
            if(!resp.IsSuccessStatusCode)
            {
                StatusText.Text=$"Online-Zentrale antwortet mit HTTP {(int)resp.StatusCode}.";
                return;
            }

            using var doc=JsonDocument.Parse(json);
            var root=doc.RootElement;
            PartnerLeadsValue.Text=Int(root,"partnerLeads").ToString();
            OpenValue.Text=Int(root,"requested").ToString();
            ConfirmedValue.Text=Int(root,"confirmed").ToString();
            BookingValue.Text=$"{Double(root,"confirmedValue"):0.00} €";
            CommissionValue.Text=$"{Double(root,"estimatedCommission"):0.00} €";

            var trips=new List<Dictionary<string,object?>>();
            if(root.TryGetProperty("trips",out var tripsNode)&&tripsNode.ValueKind==JsonValueKind.Array)
                foreach(var x in tripsNode.EnumerateArray())
                    trips.Add(new Dictionary<string,object?>
                    {
                        ["Reise"]=Str(x,"trip_reference"),
                        ["Von"]=Str(x,"start_date"),
                        ["Bis"]=Str(x,"end_date"),
                        ["Nächte"]=Int(x,"nights"),
                        ["Bestätigt"]=Int(x,"confirmed"),
                        ["Offen"]=Int(x,"requested"),
                        ["Absagen"]=Int(x,"declined"),
                        ["Status"]=TranslateStatus(Str(x,"status")),
                        ["Wert"]=($"{Double(x,"value"):0.00} €")
                    });
            TripsGrid.ItemsSource=trips;
            TripSummaryText.Text=$"{trips.Count} Reisevorgänge · Bestätigungsquote {NullableDouble(root,"requestConfirmationPct")?.ToString("0.0") ?? "—"} %";

            var replacements=new List<Dictionary<string,object?>>();
            if(root.TryGetProperty("replacementNeeds",out var repl)&&repl.ValueKind==JsonValueKind.Array)
                foreach(var x in repl.EnumerateArray())
                    replacements.Add(new Dictionary<string,object?>
                    {
                        ["Reise"]=Str(x,"trip_reference"),
                        ["Nacht"]=Str(x,"stay_date"),
                        ["Ort"]=Str(x,"location"),
                        ["Absage von"]=Str(x,"declined_host"),
                        ["Freie Alternativen"]=Int(x,"alternatives")
                    });
            ReplacementGrid.ItemsSource=replacements;

            var funnel=new List<Dictionary<string,object?>>();
            if(root.TryGetProperty("funnel",out var fn)&&fn.ValueKind==JsonValueKind.Object)
                foreach(var p in fn.EnumerateObject())
                    funnel.Add(new Dictionary<string,object?> { ["Schritt"]=TranslateEvent(p.Name), ["Anzahl"]=p.Value.TryGetInt32(out var n)?n:0 });
            FunnelGrid.ItemsSource=funnel;

            StatusText.Text=$"✓ Live verbunden · Zeitraum {SelectedDays()} Tage · Provisionssatz {Double(root,"commissionPct"):0.0} % · {replacements.Count} Ersatzfall/-fälle.";
        }
        catch(Exception ex)
        {
            StatusText.Text=$"Live Operations nicht erreichbar: {ex.Message}";
        }
    }

    private static string TranslateStatus(string value)=>value switch
    {
        "confirmed"=>"bestätigt",
        "needs_alternative"=>"Ersatz erforderlich",
        "pending"=>"Bestätigungen laufen",
        _=>value
    };

    private static string TranslateEvent(string value)=>value switch
    {
        "planner_view"=>"Planer geöffnet",
        "trip_planned"=>"Reise geplant",
        "host_selected"=>"Gastgeber gewählt",
        "trip_request_started"=>"Anfrage begonnen",
        "trip_request_submitted"=>"Anfrage gesendet",
        "my_trip_opened"=>"Meine Reise geöffnet",
        _=>value
    };

    private static string Str(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.ValueKind!=JsonValueKind.Null?v.ToString():"";
    private static int Int(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.TryGetInt32(out var x)?x:0;
    private static double Double(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.TryGetDouble(out var x)?x:0;
    private static double? NullableDouble(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.ValueKind!=JsonValueKind.Null&&v.TryGetDouble(out var x)?x:null;
}
