using System.Text.Json;

namespace WachauEtappe.Zentrale.Data;

public sealed class SeedImporter(DatabaseService db)
{
    private static string SeedPath(string file) => Path.Combine(AppContext.BaseDirectory, "Seed", file);

    public void ImportAll()
    {
        ImportHosts();
        ImportCandidates();
        ImportRoutes();
        ImportCoverage();
        db.Execute("INSERT INTO AuditEvents(CreatedUtc,EventType,EntityType,Details) VALUES($time,'seed_import','system','Platform-Stammdaten importiert')",
            ("$time", DateTime.UtcNow.ToString("O")));
    }

    private void ImportHosts()
    {
        if (!File.Exists(SeedPath("hosts.json"))) return;
        ImportHostsJson(File.ReadAllText(SeedPath("hosts.json")));
    }

    public void ImportHostsJson(string json)
    {
        using var doc = JsonDocument.Parse(json);
        if (!doc.RootElement.TryGetProperty("hosts", out var hosts) || hosts.ValueKind != JsonValueKind.Array) return;
        foreach (var h in hosts.EnumerateArray())
        {
            var id = Text(h, "id") ?? Guid.NewGuid().ToString("N");
            db.Execute("""
                INSERT INTO Hosts(Id,Name,Location,Status,Published,AcceptingBookings,DirectUrl,Email,Phone,RawJson,UpdatedUtc)
                VALUES($id,$name,$location,$status,$published,$accepting,$url,$email,$phone,$raw,$updated)
                ON CONFLICT(Id) DO UPDATE SET Name=excluded.Name,Location=excluded.Location,Status=excluded.Status,
                Published=excluded.Published,AcceptingBookings=excluded.AcceptingBookings,DirectUrl=excluded.DirectUrl,
                Email=excluded.Email,Phone=excluded.Phone,RawJson=excluded.RawJson,UpdatedUtc=excluded.UpdatedUtc
                """,
                ("$id", id), ("$name", Text(h,"name") ?? id), ("$location", Text(h,"location")),
                ("$status", Text(h,"status") ?? "research"), ("$published", Bool(h,"published") ? 1 : 0),
                ("$accepting", Bool(h,"accepting_bookings") ? 1 : 0), ("$url", Text(h,"direct_url")),
                ("$email", Text(h,"email")), ("$phone", Text(h,"phone")), ("$raw", h.GetRawText()),
                ("$updated", DateTime.UtcNow.ToString("O")));
        }
    }

    private void ImportCandidates()
    {
        if (!File.Exists(SeedPath("candidates.json"))) return;
        using var doc = JsonDocument.Parse(File.ReadAllText(SeedPath("candidates.json")));
        var root = doc.RootElement;
        JsonElement list;
        if (!(root.TryGetProperty("candidates", out list) || root.TryGetProperty("hosts", out list))) return;
        foreach (var c in list.EnumerateArray())
        {
            var name = Text(c,"name"); if (string.IsNullOrWhiteSpace(name)) continue;
            var location = Text(c,"location") ?? "";
            db.Execute("""
                INSERT INTO Candidates(Name,Location,Priority,Status,FitScore,RawJson)
                VALUES($name,$location,$priority,$status,$score,$raw)
                ON CONFLICT(Name,Location) DO UPDATE SET Priority=excluded.Priority,Status=excluded.Status,FitScore=excluded.FitScore,RawJson=excluded.RawJson
                """,
                ("$name", name), ("$location", location), ("$priority", Text(c,"priority")),
                ("$status", Text(c,"status")), ("$score", Int(c,"fit_score")), ("$raw", c.GetRawText()));
        }
    }

    private void ImportRoutes()
    {
        if (!File.Exists(SeedPath("routes.json"))) return;
        using var doc = JsonDocument.Parse(File.ReadAllText(SeedPath("routes.json")));
        var root = doc.RootElement;
        if (root.TryGetProperty("routes", out var routes) && routes.ValueKind == JsonValueKind.Array)
        {
            foreach (var r in routes.EnumerateArray()) SaveRoute(r);
        }
        else SaveRoute(root);
    }

    private void SaveRoute(JsonElement r)
    {
        var id = Text(r,"id") ?? Text(r,"route_id") ?? "welterbesteig-wachau";
        var name = Text(r,"name") ?? "Welterbesteig Wachau";
        db.Execute("INSERT INTO Routes(Id,Name,RawJson) VALUES($id,$name,$raw) ON CONFLICT(Id) DO UPDATE SET Name=excluded.Name,RawJson=excluded.RawJson",
            ("$id",id),("$name",name),("$raw",r.GetRawText()));
    }

    private void ImportCoverage()
    {
        if (!File.Exists(SeedPath("coverage.json"))) return;
        using var doc = JsonDocument.Parse(File.ReadAllText(SeedPath("coverage.json")));
        if (!doc.RootElement.TryGetProperty("locations", out var locations)) return;
        foreach (var c in locations.EnumerateArray())
        {
            var location = Text(c,"location"); if (string.IsNullOrWhiteSpace(location)) continue;
            db.Execute("INSERT INTO Coverage(Location,Status,Need,RawJson) VALUES($location,$status,$need,$raw) ON CONFLICT(Location) DO UPDATE SET Status=excluded.Status,Need=excluded.Need,RawJson=excluded.RawJson",
                ("$location",location),("$status",Text(c,"status") ?? "gap"),("$need",Int(c,"need")),("$raw",c.GetRawText()));
        }
    }

    private static string? Text(JsonElement e,string p) => e.TryGetProperty(p,out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
    private static bool Bool(JsonElement e,string p) => e.TryGetProperty(p,out var v) && v.ValueKind is JsonValueKind.True;
    private static int Int(JsonElement e,string p) => e.TryGetProperty(p,out var v) && v.TryGetInt32(out var n) ? n : 0;
}
