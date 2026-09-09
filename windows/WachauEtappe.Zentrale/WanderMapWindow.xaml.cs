using System.Text.Json;
using System.Windows;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;

public partial class WanderMapWindow : Window
{
    private List<MapHostStatus> _hosts = new();

    public WanderMapWindow()
    {
        InitializeComponent();
        StayDatePicker.SelectedDate = DateTime.Today;
        Loaded += async (_,_) =>
        {
            try { await MapView.EnsureCoreWebView2Async(); }
            catch(Exception ex)
            {
                MessageBox.Show($"Kartenmodul konnte nicht gestartet werden: {ex.Message}","WachauEtappe Wanderkarte",MessageBoxButton.OK,MessageBoxImage.Warning);
            }
            RefreshMap();
        };
    }

    private void StayDatePicker_SelectedDateChanged(object sender,System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if(IsLoaded) RefreshMap();
    }

    private void Refresh_Click(object sender,RoutedEventArgs e) => RefreshMap();

    private void RefreshMap()
    {
        var date=(StayDatePicker.SelectedDate??DateTime.Today).Date.ToString("yyyy-MM-dd");
        _hosts=App.Database.GetMapHostStatuses(date);
        HostGrid.ItemsSource=null;
        HostGrid.ItemsSource=_hosts;
        var green=_hosts.Count(x=>x.StatusColor=="green");
        var orange=_hosts.Count(x=>x.StatusColor=="orange");
        var red=_hosts.Count(x=>x.StatusColor=="red");
        var gray=_hosts.Count(x=>x.StatusColor=="gray");
        SummaryText.Text=$"{date} · {green} frei · {orange} wenig frei · {red} besetzt · {gray} nicht gemeldet";
        if(MapView.CoreWebView2 is not null) MapView.NavigateToString(BuildHtml(_hosts,date));
    }

    private void CopyPhone_Click(object sender,RoutedEventArgs e)
    {
        if(HostGrid.SelectedItem is not MapHostStatus h || string.IsNullOrWhiteSpace(h.Phone))
        {
            MessageBox.Show("Bitte zuerst einen Gastgeber mit Telefonnummer auswählen.");
            return;
        }
        Clipboard.SetText(h.Phone);
        MessageBox.Show($"Telefonnummer von {h.Name} kopiert: {h.Phone}","WachauEtappe",MessageBoxButton.OK,MessageBoxImage.Information);
    }

    private static string BuildHtml(List<MapHostStatus> hosts,string date)
    {
        var mapHosts=hosts.Where(h=>h.HasCoordinates).Select(h=>new
        {
            h.Name,h.Location,h.Phone,h.RoomsTotal,h.RoomsFree,h.BedsTotal,h.BedsFree,
            status=h.DisplayStatus,color=h.StatusColor,lat=h.Latitude,lon=h.Longitude
        }).ToList();
        var json=JsonSerializer.Serialize(mapHosts).Replace("</","<\\/");
        var routeJson=JsonSerializer.Serialize(new[]
        {
            new {name="Krems",lat=48.4108,lon=15.6021},
            new {name="Dürnstein",lat=48.3951,lon=15.5195},
            new {name="Weißenkirchen",lat=48.3975,lon=15.4695},
            new {name="Spitz",lat=48.3657,lon=15.4145},
            new {name="Mühldorf",lat=48.3745,lon=15.3479},
            new {name="Maria Laach",lat=48.3049,lon=15.3474},
            new {name="Aggsbach Markt",lat=48.2947,lon=15.4046},
            new {name="Emmersdorf",lat=48.2417,lon=15.3376},
            new {name="Melk",lat=48.2274,lon=15.3319},
            new {name="Aggsbach Dorf",lat=48.2956,lon=15.4879},
            new {name="Hofarnsdorf",lat=48.3605,lon=15.4324},
            new {name="Rossatz",lat=48.3965,lon=15.5083},
            new {name="Unterbergern",lat=48.3654,lon=15.5837},
            new {name="Mautern",lat=48.3939,lon=15.5782},
            new {name="Krems",lat=48.4108,lon=15.6021}
        });
        return $$"""
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>html,body,#map{height:100%;margin:0}body{font-family:Segoe UI,Arial,sans-serif}.leaflet-popup-content{line-height:1.45}.host-title{font-weight:700;font-size:15px;color:#173D32}.pill{display:inline-block;padding:2px 7px;border-radius:999px;color:#fff;font-size:11px;margin-top:4px}</style></head>
<body><div id="map"></div><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const hosts={{json}}; const route={{routeJson}};
const map=L.map('map',{zoomControl:true}).setView([48.34,15.47],11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);
const routeLine=L.polyline(route.map(p=>[p.lat,p.lon]),{color:'#173D32',weight:4,opacity:.85}).addTo(map);
route.forEach((p,i)=>L.circleMarker([p.lat,p.lon],{radius:4,color:'#173D32',fillColor:'#F4F1E8',fillOpacity:1,weight:2}).addTo(map).bindTooltip(p.name,{direction:'top'}));
const colors={green:'#248A3D',orange:'#D68616',red:'#C93030',gray:'#7A8580'};
hosts.forEach(h=>{
 const c=colors[h.color]||colors.gray;
 const marker=L.circleMarker([h.lat,h.lon],{radius:10,color:'#fff',weight:2,fillColor:c,fillOpacity:.95}).addTo(map);
 const phone=h.Phone?`<br><b>Tel.:</b> ${h.Phone}`:'';
 marker.bindPopup(`<div class="host-title">${h.Name}</div>${h.Location}<br><span class="pill" style="background:${c}">${h.status}</span><br><b>Zimmer:</b> ${h.RoomsFree}/${h.RoomsTotal} frei<br><b>Betten:</b> ${h.BedsFree}/${h.BedsTotal} frei${phone}<br><small>{{date}}</small>`);
 marker.bindTooltip(`${h.Name} · ${h.RoomsFree} Zi. frei`,{direction:'top'});
});
if(routeLine.getBounds().isValid()) map.fitBounds(routeLine.getBounds().pad(.08));
</script></body></html>
""";
    }
}
