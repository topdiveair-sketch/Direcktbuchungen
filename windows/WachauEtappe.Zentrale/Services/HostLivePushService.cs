using WachauEtappe.Zentrale.Data;

namespace WachauEtappe.Zentrale.Services;

public static class HostLivePushService
{
    public static async Task<int> PushPendingAsync(DatabaseService db)
    {
        if (!LiveCentralSyncService.IsConfigured) return 0;
        var rows = db.QueryRows("""
            SELECT h.Id,
                   COALESCE((SELECT MAX(a.CreatedUtc) FROM AuditEvents a WHERE a.EventType='host_saved' AND a.EntityId=h.Id),'') AS LocalEdit,
                   COALESCE((SELECT MAX(a.CreatedUtc) FROM AuditEvents a WHERE a.EventType='host_live_push' AND a.EntityId=h.Id),'') AS LastPush
            FROM Hosts h
            WHERE EXISTS(SELECT 1 FROM AuditEvents a WHERE a.EventType='host_saved' AND a.EntityId=h.Id)
            """);
        var pushed = 0;
        foreach (var row in rows)
        {
            var id = Convert.ToString(row.GetValueOrDefault("Id")) ?? "";
            var edit = Convert.ToString(row.GetValueOrDefault("LocalEdit")) ?? "";
            var lastPush = Convert.ToString(row.GetValueOrDefault("LastPush")) ?? "";
            if (string.IsNullOrWhiteSpace(id) || string.CompareOrdinal(edit, lastPush) <= 0) continue;
            var host = db.GetHosts().FirstOrDefault(x => string.Equals(x.Id, id, StringComparison.OrdinalIgnoreCase));
            if (host is null) continue;
            var result = await LiveCentralSyncService.PushHostAsync(host, db.GetHostCapacity(id), db.GetHostBeds(id));
            if (!result.Ok) continue;
            db.Execute("INSERT INTO AuditEvents(CreatedUtc,EventType,EntityType,EntityId,Details) VALUES(@t,'host_live_push','Host',@id,@d)",
                ("@t", DateTime.UtcNow.ToString("O")), ("@id", id), ("@d", result.Message));
            pushed++;
        }
        return pushed;
    }
}
