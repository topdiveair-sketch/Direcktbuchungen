using System.Windows;
using WachauEtappe.Zentrale.Data;
using WachauEtappe.Zentrale.Services;

namespace WachauEtappe.Zentrale;

public partial class App : Application
{
    public static DatabaseService Database { get; private set; } = null!;

    protected override void OnStartup(StartupEventArgs e)
    {
        Database = new DatabaseService();
        Database.Initialize();
        try { Database.AutoBackup(); } catch { }

        var seedImporter = new SeedImporter(Database);
        seedImporter.ImportAll();

        try
        {
            new RemoteHostSyncService(Database).SyncAsync().GetAwaiter().GetResult();
        }
        catch
        {
            // Offline oder temporär nicht erreichbar: lokaler Datenbestand bleibt nutzbar.
        }

        Database.EnsureBookingTables();
        Database.EnsureBillingTables();
        base.OnStartup(e);
    }
}
