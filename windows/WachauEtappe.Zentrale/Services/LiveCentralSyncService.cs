using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using WachauEtappe.Zentrale.Data;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale.Services;

public static class LiveCentralSyncService
{
    private const string DefaultApiBase = "https://web-production-907d68.up.railway.app";
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(20) };
    private static readonly byte[] CredentialEntropy = Encoding.UTF8.GetBytes("WachauEtappe.Zentrale.AdminCredential.v1");
    private static readonly string CredentialFile = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "WachauEtappe", "railway-admin.cred");
    private static int _syncRunning;

    public static bool IsConfigured => !string.IsNullOrWhiteSpace(ReadAdminPassword());

    public static async Task<LiveSyncResult> SyncAsync(DatabaseService db, DateTime? from = null, DateTime? to = null)
    {
        if (Interlocked.Exchange(ref _syncRunning, 1) == 1)
            return new LiveSyncResult(true, 0, 0, 0, "Synchronisierung läuft bereits.", false);

        try
        {
            var password = ReadAdminPassword();
            if (string.IsNullOrWhiteSpace(password))
                return new LiveSyncResult(false, 0, 0, 0,
                    "Live-Synchronisierung noch nicht eingerichtet. Unter Gastgeber > Online-Verwaltung einmalig Railway-ADMIN_PASSWORD speichern.", true);

            var first = (from ?? DateTime.Today.AddDays(-14)).Date;
            var last = (to ?? DateTime.Today.AddDays(365)).Date;
            if (last < first) (first, last) = (last, first);
            var api = ApiBase;
            var url = $"{api}/api/central/live-state?from={first:yyyy-MM-dd}&to={last:yyyy-MM-dd}";
            using var req = new HttpRequestMessage(HttpMethod.Get, url);
            req.Headers.TryAddWithoutValidation("X-Admin-Password", password);
            using var resp = await Http.SendAsync(req);
            if (resp.StatusCode == HttpStatusCode.Unauthorized)
                return new LiveSyncResult(false, 0, 0, 0, "Gespeicherter Railway-Admin-Zugang ist ungültig.", true);
            var json = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
                return new LiveSyncResult(false, 0, 0, 0, $"Live-Zentrale antwortet mit HTTP {(int)resp.StatusCode}.", false);

            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            var hostInfo = new Dictionary<string, (string Name, string Location, int Rooms)>(StringComparer.OrdinalIgnoreCase);
            var hostCount = 0;
            if (root.TryGetProperty("hosts", out var hosts) && hosts.ValueKind == JsonValueKind.Array)
            {
                foreach (var h in hosts.EnumerateArray())
                {
                    var id = S(h, "host_id");
                    if (string.IsNullOrWhiteSpace(id)) continue;
                    var name = S(h, "name");
                    var location = S(h, "location");
                    var rooms = Math.Max(0, I(h, "effective_rooms_total", I(h, "rooms_total")));
                    var beds = Math.Max(0, I(h, "beds_total"));
                    db.Execute("""
                        INSERT INTO Hosts(Id,Name,Location,Status,Published,AcceptingBookings,DirectUrl,Email,Phone,RawJson,UpdatedUtc,OneNightVerified,CashAtHostVerified,LuggageVerified)
                        VALUES(@id,@name,@location,@status,@published,@accepting,@url,@email,@phone,@raw,@updated,@one,@cash,@luggage)
                        ON CONFLICT(Id) DO UPDATE SET Name=excluded.Name,Location=excluded.Location,Status=excluded.Status,
                          Published=excluded.Published,AcceptingBookings=excluded.AcceptingBookings,DirectUrl=excluded.DirectUrl,
                          Email=excluded.Email,Phone=excluded.Phone,RawJson=excluded.RawJson,UpdatedUtc=excluded.UpdatedUtc,
                          OneNightVerified=excluded.OneNightVerified,CashAtHostVerified=excluded.CashAtHostVerified,LuggageVerified=excluded.LuggageVerified
                        """,
                        ("@id", id), ("@name", name), ("@location", location), ("@status", S(h, "status")),
                        ("@published", B(h, "published") ? 1 : 0), ("@accepting", B(h, "accepting_bookings") ? 1 : 0),
                        ("@url", S(h, "direct_url")), ("@email", S(h, "email")), ("@phone", S(h, "phone")),
                        ("@raw", h.GetRawText()), ("@updated", S(h, "updated_at")),
                        ("@one", B(h, "one_night_verified") ? 1 : 0), ("@cash", B(h, "cash_at_host_verified") ? 1 : 0),
                        ("@luggage", B(h, "luggage_verified") ? 1 : 0));
                    if (rooms > 0)
                        db.SetHostCapacityAndBeds(id, rooms, beds > 0 ? beds : Math.Max(2, rooms * 2));
                    hostInfo[id] = (name, location, rooms);
                    hostCount++;
                }
            }

            var bookingCount = 0;
            if (root.TryGetProperty("bookings", out var bookings) && bookings.ValueKind == JsonValueKind.Array)
            {
                foreach (var b in bookings.EnumerateArray())
                {
                    var reference = S(b, "reference");
                    var hostId = S(b, "host_id");
                    if (string.IsNullOrWhiteSpace(reference) || string.IsNullOrWhiteSpace(hostId)) continue;
                    var id = $"live:{reference}";
                    db.Execute("""
                        INSERT INTO Bookings(Id,Reference,HostId,StayDate,Guests,GuestName,GuestEmail,GuestPhone,Status,Price,PaymentMethod,CreatedUtc,UpdatedUtc,Note)
                        VALUES(@id,@ref,@host,@date,@guests,@name,@email,@phone,@status,@price,@payment,@created,@updated,@note)
                        ON CONFLICT(Reference) DO UPDATE SET HostId=excluded.HostId,StayDate=excluded.StayDate,Guests=excluded.Guests,
                          GuestName=excluded.GuestName,GuestEmail=excluded.GuestEmail,GuestPhone=excluded.GuestPhone,
                          Status=excluded.Status,Price=excluded.Price,PaymentMethod=excluded.PaymentMethod,
                          UpdatedUtc=excluded.UpdatedUtc,Note=excluded.Note
                        """,
                        ("@id", id), ("@ref", reference), ("@host", hostId), ("@date", S(b, "stay_date")),
                        ("@guests", Math.Max(1, I(b, "guests", 1))), ("@name", S(b, "guest_name")),
                        ("@email", S(b, "guest_email")), ("@phone", S(b, "guest_phone")), ("@status", S(b, "status")),
                        ("@price", Dn(b, "price")), ("@payment", S(b, "payment_method")),
                        ("@created", S(b, "created_at")), ("@updated", S(b, "updated_at")), ("@note", S(b, "note")));
                    bookingCount++;
                }
            }

            var availabilityCount = 0;
            if (root.TryGetProperty("availability", out var availability) && availability.ValueKind == JsonValueKind.Array)
            {
                foreach (var a in availability.EnumerateArray())
                {
                    var hostId = S(a, "host_id");
                    var stayDate = S(a, "stay_date");
                    if (string.IsNullOrWhiteSpace(hostId) || string.IsNullOrWhiteSpace(stayDate)) continue;
                    hostInfo.TryGetValue(hostId, out var hi);
                    var roomsFree = Math.Max(0, I(a, "rooms_free"));
                    var roomsTotal = hi.Rooms > 0 ? hi.Rooms : Math.Max(1, roomsFree);
                    db.UpsertOnlinePartnerAvailability(hostId, hi.Name ?? hostId, hi.Location ?? "", roomsTotal,
                        stayDate, S(a, "status"), roomsFree, Dn(a, "price"), B(a, "booking_blocked"), S(a, "updated_at"));
                    availabilityCount++;
                }
            }

            db.Execute("INSERT INTO AuditEvents(CreatedUtc,EventType,EntityType,Details) VALUES(@t,'live_central_sync','system',@d)",
                ("@t", DateTime.UtcNow.ToString("O")),
                ("@d", $"hosts={hostCount}; bookings={bookingCount}; availability={availabilityCount}"));
            return new LiveSyncResult(true, hostCount, bookingCount, availabilityCount,
                $"Live: {hostCount} Gastgeber, {bookingCount} Buchungen, {availabilityCount} Verfügbarkeiten synchronisiert.", false);
        }
        catch (Exception ex)
        {
            return new LiveSyncResult(false, 0, 0, 0, $"Live-Synchronisierung nicht erreichbar: {ex.Message}", false);
        }
        finally
        {
            Interlocked.Exchange(ref _syncRunning, 0);
        }
    }

    public static async Task<(bool Ok, string Message)> PushHostAsync(HostRecord host, int roomsTotal, int bedsTotal)
    {
        var password = ReadAdminPassword();
        if (string.IsNullOrWhiteSpace(password)) return (false, "Admin-Zugang nicht eingerichtet.");
        var payload = new
        {
            name = host.Name, location = host.Location, status = host.Status, published = host.Published,
            acceptingBookings = host.AcceptingBookings, directUrl = host.DirectUrl, email = host.Email, phone = host.Phone,
            address = host.Address, latitude = host.Latitude, longitude = host.Longitude,
            oneNightVerified = host.OneNightVerified, cashAtHostVerified = host.CashAtHostVerified,
            luggageVerified = host.LuggageVerified, roomsTotal, bedsTotal
        };
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Put, $"{ApiBase}/api/central/hosts/{Uri.EscapeDataString(host.Id)}");
            req.Headers.TryAddWithoutValidation("X-Admin-Password", password);
            req.Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            using var resp = await Http.SendAsync(req);
            if (resp.StatusCode == HttpStatusCode.Unauthorized) return (false, "Admin-Zugang ungültig.");
            return resp.IsSuccessStatusCode ? (true, "✓ Änderung live gespeichert.") : (false, $"Live-Speichern fehlgeschlagen (HTTP {(int)resp.StatusCode}).");
        }
        catch (Exception ex) { return (false, $"Live-Speichern nicht erreichbar: {ex.Message}"); }
    }

    public static async Task<bool> PushBookingStatusAsync(string reference, string status)
    {
        if (!reference.StartsWith("WE-", StringComparison.OrdinalIgnoreCase)) return true;
        var password = ReadAdminPassword();
        if (string.IsNullOrWhiteSpace(password)) return false;
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Patch, $"{ApiBase}/api/central/bookings/{Uri.EscapeDataString(reference)}");
            req.Headers.TryAddWithoutValidation("X-Admin-Password", password);
            req.Content = new StringContent(JsonSerializer.Serialize(new { status }), Encoding.UTF8, "application/json");
            using var resp = await Http.SendAsync(req);
            return resp.IsSuccessStatusCode;
        }
        catch { return false; }
    }

    private static string ApiBase => (Environment.GetEnvironmentVariable("WACHAUETAPPE_API_BASE") ?? DefaultApiBase).TrimEnd('/');

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

    private static string S(JsonElement e, string n) => e.TryGetProperty(n, out var v) && v.ValueKind != JsonValueKind.Null ? v.ToString() : "";
    private static int I(JsonElement e, string n, int fallback = 0) => e.TryGetProperty(n, out var v) && v.TryGetInt32(out var x) ? x : fallback;
    private static bool B(JsonElement e, string n) => e.TryGetProperty(n, out var v) && (v.ValueKind == JsonValueKind.True || (v.TryGetInt32(out var x) && x != 0));
    private static double? Dn(JsonElement e, string n) => e.TryGetProperty(n, out var v) && v.ValueKind != JsonValueKind.Null && v.TryGetDouble(out var x) ? x : null;
}

public sealed record LiveSyncResult(bool Success, int Hosts, int Bookings, int Availability, string Message, bool CredentialRequired);
