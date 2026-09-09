using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;
using WachauEtappe.Zentrale.Models;
using IOPath = System.IO.Path;

namespace WachauEtappe.Zentrale;

public partial class WanderMapWindow : Window
{
    private List<MapHostStatus> _hosts = new();
    private List<List<GeoPoint>>? _osmRoute;
    private bool _osmRouteIsExact;

    private const long WelterbesteigRelationId = 1309244;
    private const int Zoom = 11;
    private const double MinLat = 48.195;
    private const double MaxLat = 48.440;
    private const double MinLon = 15.285;
    private const double MaxLon = 15.635;
    private const double CanvasW = 920;
    private const double CanvasH = 650;
    private const double Pad = 18;

    private double _worldMinX;
    private double _worldMinY;
    private double _scale;
    private double _offsetX;
    private double _offsetY;

    private static readonly HttpClient Http = CreateHttpClient();

    private static readonly (string Name, double Lat, double Lon)[] StagePlaces =
    {
        ("Krems",48.4108,15.6021),("Dürnstein",48.3951,15.5195),("Weißenkirchen",48.3975,15.4695),
        ("Spitz",48.3657,15.4145),("Mühldorf",48.3745,15.3479),("Maria Laach",48.3049,15.3474),
        ("Aggsbach Markt",48.2947,15.4046),("Emmersdorf",48.2417,15.3376),("Melk",48.2274,15.3319),
        ("Aggsbach Dorf",48.2956,15.4879),("Hofarnsdorf",48.3605,15.4324),("Rossatz",48.3965,15.5083),
        ("Unterbergern",48.3654,15.5837),("Mautern",48.3939,15.5782)
    };

    private static readonly GeoPoint[] FallbackRoute =
    {
        new(48.4108,15.6021),new(48.3951,15.5195),new(48.3975,15.4695),new(48.3657,15.4145),
        new(48.3745,15.3479),new(48.3049,15.3474),new(48.2947,15.4046),new(48.2417,15.3376),
        new(48.2274,15.3319),new(48.2956,15.4879),new(48.3605,15.4324),new(48.3965,15.5083),
        new(48.3654,15.5837),new(48.3939,15.5782),new(48.4108,15.6021)
    };

    public WanderMapWindow()
    {
        InitializeComponent();
        StayDatePicker.SelectedDate = DateTime.Today;
        ConfigureProjection();
        Loaded += async (_, _) => await RefreshMapAsync();
    }

    private static HttpClient CreateHttpClient()
    {
        var h = new HttpClient { Timeout = TimeSpan.FromSeconds(25) };
        h.DefaultRequestHeaders.UserAgent.ParseAdd("WachauEtappe-Zentrale/1.0 (contact: topdiveair@gmail.com)");
        return h;
    }

    private async void StayDatePicker_SelectedDateChanged(object sender, SelectionChangedEventArgs e)
    {
        if (IsLoaded) await RefreshMapAsync();
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e) => await RefreshMapAsync(forceRouteReload: true);

    private async Task RefreshMapAsync(bool forceRouteReload = false)
    {
        var date = (StayDatePicker.SelectedDate ?? DateTime.Today).Date.ToString("yyyy-MM-dd");
        _hosts = App.Database.GetMapHostStatuses(date);
        HostGrid.ItemsSource = null;
        HostGrid.ItemsSource = _hosts;
        var green = _hosts.Count(x => x.StatusColor == "green");
        var orange = _hosts.Count(x => x.StatusColor == "orange");
        var red = _hosts.Count(x => x.StatusColor == "red");
        var gray = _hosts.Count(x => x.StatusColor == "gray");
        SummaryText.Text = $"{date} · {green} frei · {orange} wenig frei · {red} besetzt · {gray} nicht gemeldet";
        SelectedHostPanel.Visibility = Visibility.Collapsed;

        MapStatusText.Text = "OpenStreetMap und Welterbesteig werden geladen …";
        MapCanvas.Children.Clear();

        await DrawOpenStreetMapTilesAsync();
        await EnsureOsmRouteAsync(forceRouteReload);
        DrawOsmRoute();
        DrawStagePlaces();
        foreach (var h in _hosts.Where(x => x.HasCoordinates)) DrawHost(h);

        MapStatusText.Text = _osmRouteIsExact
            ? $"OpenStreetMap · Welterbesteig Relation {WelterbesteigRelationId} · genauer OSM-Wegverlauf geladen"
            : "OpenStreetMap-Weg derzeit nicht abrufbar · vereinfachte Ersatzlinie wird angezeigt";
    }

    private void ConfigureProjection()
    {
        var nw = WorldPixel(MaxLat, MinLon, Zoom);
        var se = WorldPixel(MinLat, MaxLon, Zoom);
        _worldMinX = nw.X;
        _worldMinY = nw.Y;
        var worldWidth = se.X - nw.X;
        var worldHeight = se.Y - nw.Y;
        _scale = Math.Min((CanvasW - 2 * Pad) / worldWidth, (CanvasH - 2 * Pad) / worldHeight);
        _offsetX = (CanvasW - worldWidth * _scale) / 2.0;
        _offsetY = (CanvasH - worldHeight * _scale) / 2.0;
    }

    private static Point WorldPixel(double lat, double lon, int zoom)
    {
        var size = 256.0 * Math.Pow(2, zoom);
        var x = (lon + 180.0) / 360.0 * size;
        var rad = lat * Math.PI / 180.0;
        var y = (1.0 - Math.Log(Math.Tan(rad) + 1.0 / Math.Cos(rad)) / Math.PI) / 2.0 * size;
        return new Point(x, y);
    }

    private Point Project(double lat, double lon)
    {
        var p = WorldPixel(lat, lon, Zoom);
        return new Point(_offsetX + (p.X - _worldMinX) * _scale, _offsetY + (p.Y - _worldMinY) * _scale);
    }

    private async Task DrawOpenStreetMapTilesAsync()
    {
        var nw = WorldPixel(MaxLat, MinLon, Zoom);
        var se = WorldPixel(MinLat, MaxLon, Zoom);
        var x0 = (int)Math.Floor(nw.X / 256.0);
        var x1 = (int)Math.Floor(se.X / 256.0);
        var y0 = (int)Math.Floor(nw.Y / 256.0);
        var y1 = (int)Math.Floor(se.Y / 256.0);

        for (var y = y0; y <= y1; y++)
        {
            for (var x = x0; x <= x1; x++)
            {
                var source = await GetTileAsync(x, y, Zoom);
                if (source is null) continue;
                var topLeft = new Point(_offsetX + (x * 256.0 - _worldMinX) * _scale, _offsetY + (y * 256.0 - _worldMinY) * _scale);
                var image = new Image
                {
                    Source = source,
                    Width = 256 * _scale + 0.5,
                    Height = 256 * _scale + 0.5,
                    Stretch = Stretch.Fill,
                    IsHitTestVisible = false
                };
                Canvas.SetLeft(image, topLeft.X);
                Canvas.SetTop(image, topLeft.Y);
                Panel.SetZIndex(image, 0);
                MapCanvas.Children.Add(image);
            }
        }
    }

    private static async Task<BitmapImage?> GetTileAsync(int x, int y, int z)
    {
        try
        {
            var folder = IOPath.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WachauEtappe", "MapCache", z.ToString(), x.ToString());
            Directory.CreateDirectory(folder);
            var path = IOPath.Combine(folder, $"{y}.png");
            byte[] bytes;
            if (File.Exists(path) && DateTime.UtcNow - File.GetLastWriteTimeUtc(path) < TimeSpan.FromDays(30))
            {
                bytes = await File.ReadAllBytesAsync(path);
            }
            else
            {
                bytes = await Http.GetByteArrayAsync($"https://tile.openstreetmap.org/{z}/{x}/{y}.png");
                await File.WriteAllBytesAsync(path, bytes);
            }

            using var ms = new MemoryStream(bytes);
            var bitmap = new BitmapImage();
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.StreamSource = ms;
            bitmap.EndInit();
            bitmap.Freeze();
            return bitmap;
        }
        catch
        {
            return null;
        }
    }

    private async Task EnsureOsmRouteAsync(bool forceReload)
    {
        if (_osmRoute is not null && !forceReload) return;
        var cacheFolder = IOPath.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WachauEtappe", "MapCache");
        Directory.CreateDirectory(cacheFolder);
        var cachePath = IOPath.Combine(cacheFolder, $"welterbesteig-relation-{WelterbesteigRelationId}.json");

        try
        {
            var query = $"[out:json][timeout:25];relation({WelterbesteigRelationId});way(r);out geom;";
            var url = "https://overpass-api.de/api/interpreter?data=" + Uri.EscapeDataString(query);
            var json = await Http.GetStringAsync(url);
            var segments = ParseOverpassGeometry(json);
            if (segments.Count > 0 && segments.Sum(s => s.Count) > 100)
            {
                _osmRoute = segments;
                _osmRouteIsExact = true;
                await File.WriteAllTextAsync(cachePath, JsonSerializer.Serialize(segments));
                return;
            }
        }
        catch
        {
        }

        try
        {
            if (File.Exists(cachePath))
            {
                var cached = JsonSerializer.Deserialize<List<List<GeoPoint>>>(await File.ReadAllTextAsync(cachePath));
                if (cached is { Count: > 0 } && cached.Sum(s => s.Count) > 100)
                {
                    _osmRoute = cached;
                    _osmRouteIsExact = true;
                    return;
                }
            }
        }
        catch
        {
        }

        _osmRoute = new List<List<GeoPoint>> { FallbackRoute.ToList() };
        _osmRouteIsExact = false;
    }

    private static List<List<GeoPoint>> ParseOverpassGeometry(string json)
    {
        var result = new List<List<GeoPoint>>();
        using var doc = JsonDocument.Parse(json);
        if (!doc.RootElement.TryGetProperty("elements", out var elements)) return result;
        foreach (var el in elements.EnumerateArray())
        {
            if (!el.TryGetProperty("type", out var type) || type.GetString() != "way") continue;
            if (!el.TryGetProperty("geometry", out var geometry) || geometry.ValueKind != JsonValueKind.Array) continue;
            var segment = new List<GeoPoint>();
            foreach (var p in geometry.EnumerateArray())
            {
                if (p.TryGetProperty("lat", out var lat) && p.TryGetProperty("lon", out var lon))
                    segment.Add(new GeoPoint(lat.GetDouble(), lon.GetDouble()));
            }
            if (segment.Count > 1) result.Add(segment);
        }
        return result;
    }

    private void DrawOsmRoute()
    {
        if (_osmRoute is null) return;
        foreach (var segment in _osmRoute)
        {
            var halo = new Polyline
            {
                Stroke = Brushes.White,
                StrokeThickness = 7,
                Opacity = 0.92,
                StrokeLineJoin = PenLineJoin.Round,
                IsHitTestVisible = false
            };
            var line = new Polyline
            {
                Stroke = new SolidColorBrush(Color.FromRgb(198, 40, 40)),
                StrokeThickness = 3.5,
                Opacity = 0.96,
                StrokeLineJoin = PenLineJoin.Round,
                IsHitTestVisible = false
            };
            foreach (var point in segment)
            {
                var p = Project(point.Lat, point.Lon);
                halo.Points.Add(p);
                line.Points.Add(p);
            }
            Panel.SetZIndex(halo, 10);
            Panel.SetZIndex(line, 11);
            MapCanvas.Children.Add(halo);
            MapCanvas.Children.Add(line);
        }
    }

    private void DrawStagePlaces()
    {
        foreach (var stage in StagePlaces)
        {
            var p = Project(stage.Lat, stage.Lon);
            var dot = new Ellipse
            {
                Width = 7,
                Height = 7,
                Fill = Brushes.White,
                Stroke = new SolidColorBrush(Color.FromRgb(23, 61, 50)),
                StrokeThickness = 2,
                ToolTip = stage.Name
            };
            Canvas.SetLeft(dot, p.X - 3.5);
            Canvas.SetTop(dot, p.Y - 3.5);
            Panel.SetZIndex(dot, 20);
            MapCanvas.Children.Add(dot);

            var label = new Border
            {
                Background = new SolidColorBrush(Color.FromArgb(220, 255, 255, 255)),
                CornerRadius = new CornerRadius(3),
                Padding = new Thickness(3, 1, 3, 1),
                IsHitTestVisible = false,
                Child = new TextBlock { Text = stage.Name, FontSize = 9.5, FontWeight = FontWeights.SemiBold, Foreground = new SolidColorBrush(Color.FromRgb(23, 61, 50)) }
            };
            Canvas.SetLeft(label, p.X + 5);
            Canvas.SetTop(label, p.Y - 15);
            Panel.SetZIndex(label, 21);
            MapCanvas.Children.Add(label);
        }
    }

    private void DrawHost(MapHostStatus h)
    {
        var p = Project(h.Latitude, h.Longitude);
        var brush = StatusBrush(h.StatusColor);
        var marker = new Ellipse
        {
            Width = 20,
            Height = 20,
            Fill = brush,
            Stroke = Brushes.White,
            StrokeThickness = 3,
            Cursor = Cursors.Hand,
            Tag = h,
            ToolTip = $"{h.Name}\n{h.Location}\nZimmer {h.RoomsFree}/{h.RoomsTotal} frei · Betten {h.BedsFree}/{h.BedsTotal} frei\n{h.Phone}"
        };
        marker.MouseLeftButtonDown += HostMarker_Click;
        Canvas.SetLeft(marker, p.X - 10);
        Canvas.SetTop(marker, p.Y - 10);
        Panel.SetZIndex(marker, 30);
        MapCanvas.Children.Add(marker);

        var label = new Border
        {
            Background = new SolidColorBrush(Color.FromArgb(230, 255, 255, 255)),
            CornerRadius = new CornerRadius(4),
            Padding = new Thickness(4, 2, 4, 2),
            IsHitTestVisible = false,
            Child = new TextBlock { Text = h.Name, FontSize = 10, FontWeight = FontWeights.SemiBold, Foreground = new SolidColorBrush(Color.FromRgb(31, 45, 39)) }
        };
        Canvas.SetLeft(label, p.X + 10);
        Canvas.SetTop(label, p.Y - 17);
        Panel.SetZIndex(label, 31);
        MapCanvas.Children.Add(label);
    }

    private static Brush StatusBrush(string color) => color switch
    {
        "green" => new SolidColorBrush(Color.FromRgb(36, 138, 61)),
        "orange" => new SolidColorBrush(Color.FromRgb(214, 134, 22)),
        "red" => new SolidColorBrush(Color.FromRgb(201, 48, 48)),
        _ => new SolidColorBrush(Color.FromRgb(122, 133, 128))
    };

    private void HostMarker_Click(object sender, MouseButtonEventArgs e)
    {
        if (sender is Ellipse { Tag: MapHostStatus h }) SelectHost(h);
        e.Handled = true;
    }

    private void MapCanvas_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.OriginalSource == MapCanvas) SelectedHostPanel.Visibility = Visibility.Collapsed;
    }

    private void HostGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (HostGrid.SelectedItem is MapHostStatus h) SelectHost(h, false);
    }

    private void SelectHost(MapHostStatus h, bool selectGrid = true)
    {
        if (selectGrid)
        {
            HostGrid.SelectedItem = h;
            HostGrid.ScrollIntoView(h);
        }
        SelectedHostText.Text = $"{h.Name} · {h.Location}\nTelefon: {(string.IsNullOrWhiteSpace(h.Phone) ? "–" : h.Phone)}\nZimmer: {h.RoomsFree}/{h.RoomsTotal} frei · Betten: {h.BedsFree}/{h.BedsTotal} frei\nStatus: {h.DisplayStatus}";
        SelectedHostPanel.Visibility = Visibility.Visible;
    }

    private void CopyPhone_Click(object sender, RoutedEventArgs e)
    {
        if (HostGrid.SelectedItem is not MapHostStatus h || string.IsNullOrWhiteSpace(h.Phone))
        {
            MessageBox.Show("Bitte zuerst einen Gastgeber mit Telefonnummer auswählen.");
            return;
        }
        Clipboard.SetText(h.Phone);
        MessageBox.Show($"Telefonnummer von {h.Name} kopiert: {h.Phone}", "WachauEtappe", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    private sealed record GeoPoint(double Lat, double Lon);
}
