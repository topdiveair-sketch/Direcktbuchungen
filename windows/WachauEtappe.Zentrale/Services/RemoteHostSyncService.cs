using System.Net.Http;
using WachauEtappe.Zentrale.Data;

namespace WachauEtappe.Zentrale.Services;

public sealed class RemoteHostSyncService(DatabaseService db)
{
    private const string HostsUrl = "https://raw.githubusercontent.com/topdiveair-sketch/Direcktbuchungen/main/plattform/hosts.json";
    private static readonly HttpClient Http = new()
    {
        Timeout = TimeSpan.FromSeconds(8)
    };

    public async Task<bool> SyncAsync()
    {
        try
        {
            var json = await Http.GetStringAsync(HostsUrl);
            if (string.IsNullOrWhiteSpace(json)) return false;

            new SeedImporter(db).ImportHostsJson(json);
            db.Execute(
                "INSERT INTO AuditEvents(CreatedUtc,EventType,EntityType,Details) VALUES($time,'remote_host_sync','system','Gastgeber aus GitHub hosts.json synchronisiert')",
                ("$time", DateTime.UtcNow.ToString("O")));
            return true;
        }
        catch (Exception ex)
        {
            try
            {
                db.Execute(
                    "INSERT INTO AuditEvents(CreatedUtc,EventType,EntityType,Details) VALUES($time,'remote_host_sync_failed','system',$details)",
                    ("$time", DateTime.UtcNow.ToString("O")),
                    ("$details", $"GitHub-Synchronisierung fehlgeschlagen: {ex.Message}"));
            }
            catch
            {
                // Die Anwendung darf bei fehlendem Internet oder Audit-Fehlern trotzdem starten.
            }
            return false;
        }
    }
}
