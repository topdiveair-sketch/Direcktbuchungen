using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;

public partial class WanderMapWindow : Window
{
    private List<MapHostStatus> _hosts = new();

    private static readonly (string Name,double Lat,double Lon)[] NorthRoute =
    {
        ("Krems",48.4108,15.6021),("Dürnstein",48.3951,15.5195),("Weißenkirchen",48.3975,15.4695),
        ("Spitz",48.3657,15.4145),("Mühldorf",48.3745,15.3479),("Maria Laach",48.3049,15.3474),
        ("Aggsbach Markt",48.2947,15.4046),("Emmersdorf",48.2417,15.3376),("Melk",48.2274,15.3319)
    };

    private static readonly (string Name,double Lat,double Lon)[] SouthRoute =
    {
        ("Melk",48.2274,15.3319),("Aggsbach Dorf",48.2956,15.4879),("Hofarnsdorf",48.3605,15.4324),
        ("Rossatz",48.3965,15.5083),("Unterbergern",48.3654,15.5837),("Mautern",48.3939,15.5782),
        ("Krems",48.4108,15.6021)
    };

    private const double MinLat=48.205;
    private const double MaxLat=48.430;
    private const double MinLon=15.300;
    private const double MaxLon=15.625;
    private const double CanvasW=920;
    private const double CanvasH=650;
    private const double Pad=38;

    public WanderMapWindow()
    {
        InitializeComponent();
        StayDatePicker.SelectedDate = DateTime.Today;
        Loaded += (_,_) => RefreshMap();
    }

    private void StayDatePicker_SelectedDateChanged(object sender,SelectionChangedEventArgs e)
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
        SelectedHostPanel.Visibility=Visibility.Collapsed;
        DrawMap();
    }

    private static Point Project(double lat,double lon)
    {
        var x=Pad+(lon-MinLon)/(MaxLon-MinLon)*(CanvasW-2*Pad);
        var y=Pad+(MaxLat-lat)/(MaxLat-MinLat)*(CanvasH-2*Pad);
        return new Point(x,y);
    }

    private void DrawMap()
    {
        MapCanvas.Children.Clear();

        AddLabel("WachauEtappe · Welterbesteig",22,610,14,FontWeights.Bold,Brushes.DarkSlateGray);
        DrawDanube();
        DrawRoute(NorthRoute,new SolidColorBrush(Color.FromRgb(23,61,50)),"Nordufer");
        DrawRoute(SouthRoute,new SolidColorBrush(Color.FromRgb(49,93,122)),"Südufer");

        foreach(var h in _hosts.Where(x=>x.HasCoordinates)) DrawHost(h);
    }

    private void DrawDanube()
    {
        var river=new[]
        {
            Project(48.229,15.319),Project(48.250,15.353),Project(48.282,15.404),Project(48.335,15.438),
            Project(48.378,15.486),Project(48.398,15.540),Project(48.402,15.610)
        };
        var poly=new Polyline{Stroke=new SolidColorBrush(Color.FromRgb(164,205,226)),StrokeThickness=15,Opacity=.72,StrokeLineJoin=PenLineJoin.Round};
        foreach(var p in river) poly.Points.Add(p);
        MapCanvas.Children.Add(poly);
        AddLabel("Donau",455,350,13,FontWeights.SemiBold,new SolidColorBrush(Color.FromRgb(70,125,160)));
    }

    private void DrawRoute((string Name,double Lat,double Lon)[] route,Brush brush,string side)
    {
        var line=new Polyline{Stroke=brush,StrokeThickness=4,Opacity=.92,StrokeLineJoin=PenLineJoin.Round};
        foreach(var p in route) line.Points.Add(Project(p.Lat,p.Lon));
        MapCanvas.Children.Add(line);

        for(var i=0;i<route.Length;i++)
        {
            var r=route[i];var p=Project(r.Lat,r.Lon);
            var dot=new Ellipse{Width=9,Height=9,Fill=Brushes.White,Stroke=brush,StrokeThickness=2,ToolTip=$"{side}: {r.Name}"};
            Canvas.SetLeft(dot,p.X-4.5);Canvas.SetTop(dot,p.Y-4.5);MapCanvas.Children.Add(dot);
            var offsetY=i%2==0?-24:10;
            AddLabel(r.Name,p.X+7,p.Y+offsetY,11,FontWeights.SemiBold,brush);
        }
    }

    private void DrawHost(MapHostStatus h)
    {
        var p=Project(h.Latitude,h.Longitude);
        var brush=StatusBrush(h.StatusColor);
        var marker=new Ellipse
        {
            Width=20,Height=20,Fill=brush,Stroke=Brushes.White,StrokeThickness=3,
            Cursor=Cursors.Hand,Tag=h,
            ToolTip=$"{h.Name}\n{h.Location}\nZimmer {h.RoomsFree}/{h.RoomsTotal} frei · Betten {h.BedsFree}/{h.BedsTotal} frei\n{h.Phone}"
        };
        marker.MouseLeftButtonDown+=HostMarker_Click;
        Canvas.SetLeft(marker,p.X-10);Canvas.SetTop(marker,p.Y-10);MapCanvas.Children.Add(marker);

        var label=new Border{Background=new SolidColorBrush(Color.FromArgb(225,255,255,255)),CornerRadius=new CornerRadius(4),Padding=new Thickness(4,2,4,2),IsHitTestVisible=false};
        label.Child=new TextBlock{Text=h.Name,FontSize=10,FontWeight=FontWeights.SemiBold,Foreground=new SolidColorBrush(Color.FromRgb(31,45,39))};
        Canvas.SetLeft(label,p.X+10);Canvas.SetTop(label,p.Y-17);MapCanvas.Children.Add(label);
    }

    private static Brush StatusBrush(string color)=>color switch
    {
        "green"=>new SolidColorBrush(Color.FromRgb(36,138,61)),
        "orange"=>new SolidColorBrush(Color.FromRgb(214,134,22)),
        "red"=>new SolidColorBrush(Color.FromRgb(201,48,48)),
        _=>new SolidColorBrush(Color.FromRgb(122,133,128))
    };

    private void HostMarker_Click(object sender,MouseButtonEventArgs e)
    {
        if(sender is Ellipse {Tag:MapHostStatus h}) SelectHost(h);
        e.Handled=true;
    }

    private void MapCanvas_MouseLeftButtonDown(object sender,MouseButtonEventArgs e)
    {
        if(e.OriginalSource==MapCanvas) SelectedHostPanel.Visibility=Visibility.Collapsed;
    }

    private void HostGrid_SelectionChanged(object sender,SelectionChangedEventArgs e)
    {
        if(HostGrid.SelectedItem is MapHostStatus h) SelectHost(h,false);
    }

    private void SelectHost(MapHostStatus h,bool selectGrid=true)
    {
        if(selectGrid)
        {
            HostGrid.SelectedItem=h;
            HostGrid.ScrollIntoView(h);
        }
        SelectedHostText.Text=$"{h.Name} · {h.Location}\nTelefon: {(string.IsNullOrWhiteSpace(h.Phone)?"–":h.Phone)}\nZimmer: {h.RoomsFree}/{h.RoomsTotal} frei · Betten: {h.BedsFree}/{h.BedsTotal} frei\nStatus: {h.DisplayStatus}";
        SelectedHostPanel.Visibility=Visibility.Visible;
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

    private void AddLabel(string text,double x,double y,double fontSize,FontWeight weight,Brush brush)
    {
        var t=new TextBlock{Text=text,FontSize=fontSize,FontWeight=weight,Foreground=brush,IsHitTestVisible=false};
        Canvas.SetLeft(t,x);Canvas.SetTop(t,y);MapCanvas.Children.Add(t);
    }
}
