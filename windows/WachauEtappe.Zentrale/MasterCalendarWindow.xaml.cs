using System.Collections.ObjectModel;
using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Services;

namespace WachauEtappe.Zentrale;

public partial class MasterCalendarWindow : Window
{
    private readonly ObservableCollection<CalendarDayRow> _rows = new();
    private DateTime _month = new(DateTime.Today.Year, DateTime.Today.Month, 1);
    private ZabCalendarSnapshot? _snapshot;
    private ZabOccupancy? _selectedOccupancy;
    private bool _loading;

    public MasterCalendarWindow()
    {
        InitializeComponent();
        CalendarGrid.ItemsSource = _rows;
        TransportBox.SelectedIndex = 0;
        Loaded += async (_, _) => await LoadMonthAsync();
    }

    private string SelectedRoomKey => RoomBox.SelectedItem is ZabRoomOption room ? room.Key : "Bachblick";

    private async Task LoadMonthAsync()
    {
        if (_loading) return;
        _loading = true;
        try
        {
            StatusText.Text = "Master-Kalender wird geladen …";
            MonthText.Text = _month.ToString("MMMM yyyy", CultureInfo.GetCultureInfo("de-AT"));
            var result = await ZabMasterCalendarService.LoadMonthAsync(_month.Year, _month.Month);
            if (!result.Ok || result.Snapshot is null)
            {
                StatusText.Text = "⚠ " + result.Message;
                return;
            }
            _snapshot = result.Snapshot;
            var previous = SelectedRoomKey;
            RoomBox.ItemsSource = _snapshot.Rooms;
            var selected = _snapshot.Rooms.FirstOrDefault(r => r.Key.Equals(previous, StringComparison.OrdinalIgnoreCase))
                           ?? _snapshot.Rooms.FirstOrDefault(r => r.Key == "Bachblick")
                           ?? _snapshot.Rooms.FirstOrDefault();
            if (selected is not null) RoomBox.SelectedItem = selected;
            ConnectivityText.Text = _snapshot.BookingConnectivityConfigured
                ? "Booking.com: ✓ Connectivity bereit"
                : "Booking.com: ⚠ Connectivity noch nicht vollständig eingerichtet";
            ConnectivityText.Foreground = _snapshot.BookingConnectivityConfigured
                ? System.Windows.Media.Brushes.DarkGreen
                : System.Windows.Media.Brushes.DarkOrange;
            PayPalModeText.Text = _snapshot.PayPalMasterIndependent
                ? "PayPal: ✓ OS-Master unabhängig"
                : "PayPal: Hybrid-Sicherheitsmodus";
            BuildRows();
            LoadImportUrlForSelection();
            StatusText.Text = result.Message;
        }
        finally
        {
            _loading = false;
        }
    }

    private void BuildRows()
    {
        _rows.Clear();
        _selectedOccupancy = null;
        GuestSelectionText.Text = "Bitte einen belegten Kalendertag auswählen.";
        if (_snapshot is null || !_snapshot.Days.TryGetValue(SelectedRoomKey, out var roomDays)) return;

        foreach (var pair in roomDays.OrderBy(x => x.Key))
        {
            if (!DateTime.TryParseExact(pair.Key, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var day)) continue;
            var occupancies = _snapshot.Occupancy
                .Where(o => o.Room.Equals(SelectedRoomKey, StringComparison.OrdinalIgnoreCase)
                            && DateTime.TryParse(o.Arrival, out var a)
                            && DateTime.TryParse(o.Departure, out var d)
                            && a.Date <= day.Date && day.Date < d.Date)
                .ToList();
            var occ = occupancies.FirstOrDefault();
            var state = pair.Value;
            _rows.Add(new CalendarDayRow
            {
                Date = day,
                DateLabel = day.ToString("dd.MM.yyyy"),
                State = state,
                Occupancy = occ,
                OccupancyLabel = occupancies.Count == 0 ? "frei" : occupancies.Count == 1 ? OccupancyKindLabel(occ!.Kind) : $"{occupancies.Count} Belegungen",
                GuestName = occ?.GuestName ?? "",
                Country = occ?.Country ?? "",
                GuestsLabel = occ is { Guests: > 0 } ? occ.Guests.ToString(CultureInfo.InvariantCulture) : "",
                BreakfastLabel = occ?.Breakfast is true ? "Ja" : occ?.Breakfast is false ? "Nein" : "—",
                TransportLabel = TransportLabel(occ?.TransportMode ?? ""),
                DirectLabel = ChannelLabel(state, "direct"),
                BookingLabel = ChannelLabel(state, "booking"),
                BookingSyncLabel = state.BookingSync is null ? "—" : $"{state.BookingSync.Status}: {state.BookingSync.Message}".Trim(),
                AirbnbLabel = ChannelLabel(state, "airbnb"),
                OtherLabel = ChannelLabel(state, "other"),
            });
        }
    }

    private static string ChannelLabel(ZabDayState state, string channel)
    {
        if (!state.Channels.TryGetValue(channel, out var value)) return "—";
        var status = value.Open ? "🟢" : "🔴";
        var price = value.Price.HasValue ? $" {value.Price.Value:0.00} €" : "";
        return status + price;
    }

    private static string OccupancyKindLabel(string kind) => kind.ToLowerInvariant() switch
    {
        "direct" => "Direkt gebucht",
        "booking" => "Booking.com",
        "airbnb" => "Airbnb",
        _ => "Extern belegt",
    };

    private static string TransportLabel(string mode) => mode.ToLowerInvariant() switch
    {
        "auto" => "🚗 Auto",
        "bike" => "🚲 Fahrrad",
        "hiker" => "🥾 Wanderer",
        "other" => "Sonstiges",
        _ => "—",
    };

    private async void PreviousMonth_Click(object sender, RoutedEventArgs e)
    {
        _month = _month.AddMonths(-1);
        await LoadMonthAsync();
    }

    private async void NextMonth_Click(object sender, RoutedEventArgs e)
    {
        _month = _month.AddMonths(1);
        await LoadMonthAsync();
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e) => await LoadMonthAsync();

    private void RoomBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_loading) return;
        BuildRows();
        LoadImportUrlForSelection();
    }

    private void CalendarGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (CalendarGrid.SelectedItem is not CalendarDayRow row) return;
        FromDate.SelectedDate = row.Date;
        ToDate.SelectedDate = row.Date;
        DirectStatusBox.SelectedIndex = BookingStatusBox.SelectedIndex = AirbnbStatusBox.SelectedIndex = OtherStatusBox.SelectedIndex = 0;
        DirectPriceBox.Text = PriceText(row.State, "direct");
        BookingPriceBox.Text = PriceText(row.State, "booking");
        AirbnbPriceBox.Text = PriceText(row.State, "airbnb");
        OtherPriceBox.Text = PriceText(row.State, "other");
        ShowGuest(row.Occupancy);
    }

    private static string PriceText(ZabDayState state, string channel) =>
        state.Channels.TryGetValue(channel, out var value) && value.Price.HasValue
            ? value.Price.Value.ToString("0.00", CultureInfo.GetCultureInfo("de-AT"))
            : "";

    private void ShowGuest(ZabOccupancy? occupancy)
    {
        _selectedOccupancy = occupancy;
        if (occupancy is null)
        {
            GuestSelectionText.Text = "Dieser Tag ist frei. Keine Gastdaten vorhanden.";
            GuestNameBox.Text = CountryBox.Text = GuestsBox.Text = BookingReferenceBox.Text = GuestNotesBox.Text = "";
            BreakfastBox.IsChecked = null;
            TransportBox.SelectedIndex = 0;
            GuestNameBox.IsReadOnly = false;
            return;
        }
        GuestSelectionText.Text = $"{OccupancyKindLabel(occupancy.Kind)} · {occupancy.Arrival} bis {occupancy.Departure}";
        GuestNameBox.Text = occupancy.GuestName;
        GuestNameBox.IsReadOnly = occupancy.Kind.Equals("direct", StringComparison.OrdinalIgnoreCase);
        CountryBox.Text = occupancy.Country;
        GuestsBox.Text = occupancy.Guests > 0 ? occupancy.Guests.ToString(CultureInfo.InvariantCulture) : "";
        BookingReferenceBox.Text = occupancy.BookingReference;
        GuestNotesBox.Text = occupancy.Notes;
        BreakfastBox.IsChecked = occupancy.Breakfast;
        SelectTransport(occupancy.TransportMode);
    }

    private void SelectTransport(string mode)
    {
        foreach (var item in TransportBox.Items.OfType<ComboBoxItem>())
        {
            if (string.Equals(item.Tag?.ToString() ?? "", mode ?? "", StringComparison.OrdinalIgnoreCase))
            {
                TransportBox.SelectedItem = item;
                return;
            }
        }
        TransportBox.SelectedIndex = 0;
    }

    private static void AddStatus(Dictionary<string, object?> changes, string channel, ComboBox box)
    {
        var tag = (box.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "keep";
        if (tag == "open") changes[$"{channel}_enabled"] = true;
        else if (tag == "closed") changes[$"{channel}_enabled"] = false;
        else if (tag == "reset") changes[$"{channel}_enabled"] = null;
    }

    private static bool AddPrice(Dictionary<string, object?> changes, string channel, TextBox box, out string error)
    {
        error = "";
        var text = box.Text.Trim();
        if (string.IsNullOrWhiteSpace(text)) return true;
        if (!double.TryParse(text.Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out var price) || price < 0 || price > 50000)
        {
            error = $"Ungültiger {channel}-Preis.";
            return false;
        }
        changes[$"{channel}_price"] = Math.Round(price, 2);
        return true;
    }

    private async void SaveDaySettings_Click(object sender, RoutedEventArgs e)
    {
        if (FromDate.SelectedDate is not DateTime start || ToDate.SelectedDate is not DateTime end)
        {
            StatusText.Text = "⚠ Bitte Von- und Bis-Datum wählen.";
            return;
        }
        if (end.Date < start.Date)
        {
            StatusText.Text = "⚠ Das Bis-Datum darf nicht vor dem Von-Datum liegen.";
            return;
        }
        var changes = new Dictionary<string, object?>();
        AddStatus(changes, "direct", DirectStatusBox);
        AddStatus(changes, "booking", BookingStatusBox);
        AddStatus(changes, "airbnb", AirbnbStatusBox);
        AddStatus(changes, "other", OtherStatusBox);
        foreach (var item in new[]
                 {
                     ("direct", DirectPriceBox), ("booking", BookingPriceBox),
                     ("airbnb", AirbnbPriceBox), ("other", OtherPriceBox),
                 })
        {
            if (!AddPrice(changes, item.Item1, item.Item2, out var error))
            {
                StatusText.Text = "⚠ " + error;
                return;
            }
        }
        if (changes.Count == 0)
        {
            StatusText.Text = "Keine Änderungen ausgewählt.";
            return;
        }
        StatusText.Text = "Speichere OS-Kalender und synchronisiere freigegebene Kanäle …";
        var result = await ZabMasterCalendarService.SaveDaySettingsAsync(
            SelectedRoomKey, start.Date, end.Date, changes, SyncBookingPriceBox.IsChecked == true);
        StatusText.Text = (result.Ok ? "✓ " : "⚠ ") + result.Message;
        if (result.Ok) await LoadMonthAsync();
    }

    private async void RetryBookingPrices_Click(object sender, RoutedEventArgs e)
    {
        if (FromDate.SelectedDate is not DateTime start || ToDate.SelectedDate is not DateTime end)
        {
            StatusText.Text = "⚠ Bitte Zeitraum wählen.";
            return;
        }
        StatusText.Text = "Booking.com Preise werden gesendet …";
        var result = await ZabMasterCalendarService.SyncBookingPricesAsync(SelectedRoomKey, start.Date, end.Date);
        StatusText.Text = (result.Ok ? "✓ " : "⚠ ") + result.Message;
        await LoadMonthAsync();
    }

    private async void SaveGuest_Click(object sender, RoutedEventArgs e)
    {
        if (_selectedOccupancy is null)
        {
            StatusText.Text = "⚠ Bitte zuerst einen belegten Tag auswählen.";
            return;
        }
        var payload = new Dictionary<string, object?>
        {
            ["country"] = CountryBox.Text.Trim(),
            ["breakfast"] = BreakfastBox.IsChecked,
            ["transport_mode"] = (TransportBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "",
            ["notes"] = GuestNotesBox.Text.Trim(),
        };
        if (int.TryParse(GuestsBox.Text.Trim(), out var guests) && guests > 0)
            payload["guests"] = guests;

        if (_selectedOccupancy.BookingId > 0)
        {
            payload["booking_id"] = _selectedOccupancy.BookingId;
        }
        else
        {
            payload["room"] = _selectedOccupancy.Room;
            payload["source"] = _selectedOccupancy.Source;
            payload["uid"] = _selectedOccupancy.Uid;
            payload["start_date"] = _selectedOccupancy.Arrival;
            payload["end_date"] = _selectedOccupancy.Departure;
            payload["guest_name"] = GuestNameBox.Text.Trim();
            payload["booking_reference"] = BookingReferenceBox.Text.Trim();
        }
        var result = await ZabMasterCalendarService.SaveGuestMetaAsync(payload);
        StatusText.Text = (result.Ok ? "✓ " : "⚠ ") + result.Message;
        if (result.Ok) await LoadMonthAsync();
    }

    private void LoadImportUrlForSelection()
    {
        if (_snapshot is null) return;
        var channel = (ImportChannelBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "airbnb";
        var row = _snapshot.Imports.FirstOrDefault(x => x.Room == SelectedRoomKey && x.Channel == channel);
        if (row is not null)
        {
            ImportUrlBox.Text = row.ImportUrl;
            ImportStatusText.Text = string.IsNullOrWhiteSpace(row.LastResult)
                ? "Noch nicht synchronisiert."
                : $"{row.LastSync} · {row.LastResult}";
        }
    }

    private async void SaveImport_Click(object sender, RoutedEventArgs e)
    {
        var channel = (ImportChannelBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "airbnb";
        var result = await ZabMasterCalendarService.SaveImportSourceAsync(SelectedRoomKey, channel, ImportUrlBox.Text.Trim());
        ImportStatusText.Text = (result.Ok ? "✓ " : "⚠ ") + result.Message;
        if (result.Ok) await LoadMonthAsync();
    }

    private async void SyncImport_Click(object sender, RoutedEventArgs e)
    {
        var channel = (ImportChannelBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "airbnb";
        ImportStatusText.Text = "Synchronisierung läuft …";
        var result = await ZabMasterCalendarService.SyncChannelAsync(SelectedRoomKey, channel);
        ImportStatusText.Text = (result.Ok ? "✓ " : "⚠ ") + result.Message;
        if (result.Ok) await LoadMonthAsync();
    }
}

public sealed class CalendarDayRow
{
    public DateTime Date { get; init; }
    public string DateLabel { get; init; } = "";
    public string OccupancyLabel { get; init; } = "";
    public string GuestName { get; init; } = "";
    public string Country { get; init; } = "";
    public string GuestsLabel { get; init; } = "";
    public string BreakfastLabel { get; init; } = "";
    public string TransportLabel { get; init; } = "";
    public string DirectLabel { get; init; } = "";
    public string BookingLabel { get; init; } = "";
    public string BookingSyncLabel { get; init; } = "";
    public string AirbnbLabel { get; init; } = "";
    public string OtherLabel { get; init; } = "";
    public ZabDayState State { get; init; } = new(new(), null);
    public ZabOccupancy? Occupancy { get; init; }
}
