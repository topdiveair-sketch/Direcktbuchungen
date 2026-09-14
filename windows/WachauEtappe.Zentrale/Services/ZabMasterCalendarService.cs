using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace WachauEtappe.Zentrale.Services;

public static class ZabMasterCalendarService
{
    private const string DefaultApiBase = "https://web-production-f05a4.up.railway.app";
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(30) };
    private static readonly byte[] CredentialEntropy = Encoding.UTF8.GetBytes("WachauEtappe.Zentrale.AdminCredential.v1");
    private static readonly string CredentialFile = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "WachauEtappe", "railway-admin.cred");

    public static bool IsConfigured => !string.IsNullOrWhiteSpace(ReadAdminPassword());

    public static async Task<(bool Ok, string Message, ZabCalendarSnapshot? Snapshot)> LoadMonthAsync(int year, int month)
    {
        try
        {
            using var req = Request(HttpMethod.Get, $"/api/central/zab-calendar?year={year}&month={month}");
            using var resp = await Http.SendAsync(req);
            var text = await resp.Content.ReadAsStringAsync();
            if (resp.StatusCode == HttpStatusCode.Unauthorized)
                return (false, "Railway-Admin-Zugang ist ungültig oder fehlt.", null);
            if (!resp.IsSuccessStatusCode)
                return (false, ApiError(text, $"HTTP {(int)resp.StatusCode}"), null);
            return (true, "ZAB OS Master-Kalender geladen.", ParseSnapshot(text));
        }
        catch (Exception ex)
        {
            return (false, $"Master-Kalender nicht erreichbar: {ex.Message}", null);
        }
    }

    public static async Task<ZabApiResult> SaveDaySettingsAsync(
        string room, DateTime start, DateTime end, IDictionary<string, object?> changes,
        bool syncBookingPrice = true)
    {
        var payload = new Dictionary<string, object?>(changes, StringComparer.OrdinalIgnoreCase)
        {
            ["room"] = room,
            ["start_date"] = start.ToString("yyyy-MM-dd"),
            ["end_date"] = end.ToString("yyyy-MM-dd"),
            ["sync_booking_price"] = syncBookingPrice,
        };
        return await SendJsonAsync("/api/central/zab-calendar/day-setting", payload);
    }

    public static Task<ZabApiResult> SetChannelAsync(string room, string channel, bool enabled) =>
        SendJsonAsync("/api/central/zab-calendar/channel", new { room, channel, enabled });

    public static Task<ZabApiResult> SaveGuestMetaAsync(IDictionary<string, object?> payload) =>
        SendJsonAsync("/api/central/zab-calendar/guest-meta", payload);

    public static Task<ZabApiResult> SaveImportSourceAsync(string room, string channel, string importUrl) =>
        SendJsonAsync("/api/central/zab-calendar/import-source", new { room, channel, import_url = importUrl });

    public static Task<ZabApiResult> SyncChannelAsync(string room, string channel) =>
        SendJsonAsync("/api/central/zab-calendar/sync-channel", new { room, channel });

    public static Task<ZabApiResult> SyncBookingPricesAsync(string room, DateTime start, DateTime end) =>
        SendJsonAsync("/api/central/zab-calendar/sync-booking-prices", new
        {
            room,
            start_date = start.ToString("yyyy-MM-dd"),
            end_date = end.ToString("yyyy-MM-dd"),
        });

    private static async Task<ZabApiResult> SendJsonAsync(string path, object payload)
    {
        try
        {
            using var req = Request(HttpMethod.Post, path);
            req.Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            using var resp = await Http.SendAsync(req);
            var text = await resp.Content.ReadAsStringAsync();
            if (resp.StatusCode == HttpStatusCode.Unauthorized)
                return new ZabApiResult(false, "Railway-Admin-Zugang ist ungültig oder fehlt.", text);
            if (!resp.IsSuccessStatusCode)
                return new ZabApiResult(false, ApiError(text, $"HTTP {(int)resp.StatusCode}"), text);

            var message = "Gespeichert.";
            try
            {
                using var doc = JsonDocument.Parse(text);
                var root = doc.RootElement;
                if (root.TryGetProperty("message", out var m) && !string.IsNullOrWhiteSpace(m.ToString()))
                    message = m.ToString();
                if (root.TryGetProperty("booking_sync", out var sync) && sync.ValueKind == JsonValueKind.Array)
                {
                    var parts = new List<string>();
                    foreach (var item in sync.EnumerateArray())
                    {
                        var day = S(item, "date");
                        var status = S(item, "status");
                        var detail = S(item, "message");
                        if (!string.IsNullOrWhiteSpace(day)) parts.Add($"{day}: {status} {detail}".Trim());
                    }
                    if (parts.Count > 0) message = "Booking-Preis: " + string.Join(" · ", parts);
                }
                if (root.TryGetProperty("results", out var results) && results.ValueKind == JsonValueKind.Array)
                {
                    var ok = results.EnumerateArray().Count(x => B(x, "ok"));
                    var count = results.GetArrayLength();
                    message = $"Booking-Preise: {ok}/{count} bestätigt.";
                }
            }
            catch { }
            return new ZabApiResult(true, message, text);
        }
        catch (Exception ex)
        {
            return new ZabApiResult(false, $"ZAB OS Server nicht erreichbar: {ex.Message}", "");
        }
    }

    private static HttpRequestMessage Request(HttpMethod method, string path)
    {
        var password = ReadAdminPassword();
        if (string.IsNullOrWhiteSpace(password))
            throw new InvalidOperationException("Unter Gastgeber > Online-Verwaltung zuerst Railway-ADMIN_PASSWORD speichern.");
        var req = new HttpRequestMessage(method, $"{ApiBase}{path}");
        req.Headers.TryAddWithoutValidation("X-Admin-Password", password);
        req.Headers.TryAddWithoutValidation("Accept", "application/json");
        return req;
    }

    private static string ApiBase =>
        (Environment.GetEnvironmentVariable("WACHAUETAPPE_API_BASE") ?? DefaultApiBase).TrimEnd('/');

    private static string ReadAdminPassword()
    {
        var env = Environment.GetEnvironmentVariable("WACHAUETAPPE_ADMIN_PASSWORD");
        if (!string.IsNullOrWhiteSpace(env)) return env;
        try
        {
            if (!File.Exists(CredentialFile)) return "";
            var raw = ProtectedData.Unprotect(File.ReadAllBytes(CredentialFile), CredentialEntropy, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(raw);
        }
        catch { return ""; }
    }

    private static ZabCalendarSnapshot ParseSnapshot(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        var rooms = new List<ZabRoomOption>();
        if (root.TryGetProperty("rooms", out var roomArray) && roomArray.ValueKind == JsonValueKind.Array)
        {
            foreach (var r in roomArray.EnumerateArray())
                rooms.Add(new ZabRoomOption(S(r, "key"), S(r, "label")));
        }

        var days = new Dictionary<string, Dictionary<string, ZabDayState>>(StringComparer.OrdinalIgnoreCase);
        if (root.TryGetProperty("days", out var daysRoot) && daysRoot.ValueKind == JsonValueKind.Object)
        {
            foreach (var roomProperty in daysRoot.EnumerateObject())
            {
                var roomDays = new Dictionary<string, ZabDayState>(StringComparer.OrdinalIgnoreCase);
                foreach (var dayProperty in roomProperty.Value.EnumerateObject())
                {
                    var channelStates = new Dictionary<string, ZabChannelState>(StringComparer.OrdinalIgnoreCase);
                    if (dayProperty.Value.TryGetProperty("channels", out var channels) && channels.ValueKind == JsonValueKind.Object)
                    {
                        foreach (var channel in channels.EnumerateObject())
                        {
                            channelStates[channel.Name] = new ZabChannelState(
                                B(channel.Value, "open"),
                                D(channel.Value, "price"),
                                B(channel.Value, "price_override"));
                        }
                    }
                    ZabBookingSync? bookingSync = null;
                    if (dayProperty.Value.TryGetProperty("booking_sync", out var sync) && sync.ValueKind == JsonValueKind.Object)
                        bookingSync = new ZabBookingSync(S(sync, "status"), S(sync, "message"), S(sync, "updated_at"));
                    roomDays[dayProperty.Name] = new ZabDayState(channelStates, bookingSync);
                }
                days[roomProperty.Name] = roomDays;
            }
        }

        var occupancy = new List<ZabOccupancy>();
        if (root.TryGetProperty("occupancy", out var occArray) && occArray.ValueKind == JsonValueKind.Array)
        {
            foreach (var o in occArray.EnumerateArray())
            {
                occupancy.Add(new ZabOccupancy(
                    S(o, "kind"), I(o, "booking_id"), I(o, "external_id"), S(o, "uid"), S(o, "room"),
                    S(o, "arrival"), S(o, "departure"), S(o, "guest_name"), S(o, "country"), I(o, "guests"),
                    NullableBool(o, "breakfast"), S(o, "transport_mode"), S(o, "notes"),
                    S(o, "booking_reference"), S(o, "source")));
            }
        }

        var imports = new List<ZabImportSource>();
        if (root.TryGetProperty("imports", out var importArray) && importArray.ValueKind == JsonValueKind.Array)
        {
            foreach (var x in importArray.EnumerateArray())
                imports.Add(new ZabImportSource(S(x, "room"), S(x, "channel"), S(x, "import_url"), S(x, "last_sync"), S(x, "last_result")));
        }

        var bookingConfigured = false;
        var bookingDetail = "Booking.com Connectivity nicht konfiguriert";
        if (root.TryGetProperty("booking_connectivity", out var bc) && bc.ValueKind == JsonValueKind.Object)
        {
            bookingConfigured = B(bc, "configured");
            bookingDetail = bookingConfigured ? "Booking.com Connectivity bereit" : "Booking.com Connectivity/Zimmer-Rate-Mapping fehlt";
        }
        var paypalIndependent = B(root, "paypal_master_independent");
        return new ZabCalendarSnapshot(rooms, days, occupancy, imports, bookingConfigured, bookingDetail, paypalIndependent);
    }

    private static string ApiError(string text, string fallback)
    {
        try
        {
            using var doc = JsonDocument.Parse(text);
            var root = doc.RootElement;
            var message = S(root, "message");
            if (!string.IsNullOrWhiteSpace(message)) return message;
            var error = S(root, "error");
            if (!string.IsNullOrWhiteSpace(error)) return error;
        }
        catch { }
        return fallback;
    }

    private static string S(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind != JsonValueKind.Null ? v.ToString() : "";

    private static bool B(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && (v.ValueKind == JsonValueKind.True || (v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var i) && i != 0));

    private static double? D(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind != JsonValueKind.Null && v.TryGetDouble(out var x) ? x : null;

    private static int I(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind != JsonValueKind.Null && v.TryGetInt32(out var x) ? x : 0;

    private static bool? NullableBool(JsonElement e, string name)
    {
        if (!e.TryGetProperty(name, out var v) || v.ValueKind == JsonValueKind.Null) return null;
        if (v.ValueKind == JsonValueKind.True) return true;
        if (v.ValueKind == JsonValueKind.False) return false;
        if (v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var i)) return i != 0;
        return null;
    }
}

public sealed record ZabApiResult(bool Ok, string Message, string RawJson);
public sealed record ZabRoomOption(string Key, string Label)
{
    public override string ToString() => Label;
}
public sealed record ZabChannelState(bool Open, double? Price, bool PriceOverride);
public sealed record ZabBookingSync(string Status, string Message, string UpdatedAt);
public sealed record ZabDayState(Dictionary<string, ZabChannelState> Channels, ZabBookingSync? BookingSync);
public sealed record ZabImportSource(string Room, string Channel, string ImportUrl, string LastSync, string LastResult);
public sealed record ZabOccupancy(
    string Kind, int BookingId, int ExternalId, string Uid, string Room, string Arrival, string Departure,
    string GuestName, string Country, int Guests, bool? Breakfast, string TransportMode, string Notes,
    string BookingReference, string Source);
public sealed record ZabCalendarSnapshot(
    List<ZabRoomOption> Rooms,
    Dictionary<string, Dictionary<string, ZabDayState>> Days,
    List<ZabOccupancy> Occupancy,
    List<ZabImportSource> Imports,
    bool BookingConnectivityConfigured,
    string BookingConnectivityDetail,
    bool PayPalMasterIndependent);
