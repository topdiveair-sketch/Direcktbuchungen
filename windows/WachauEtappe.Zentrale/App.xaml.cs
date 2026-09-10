using System.IO;
using System.Windows;
using WachauEtappe.Zentrale.Data;
using WachauEtappe.Zentrale.Services;

namespace WachauEtappe.Zentrale;

public partial class App : Application
{
    public static DatabaseService Database { get; private set; } = null!;

    protected override void OnStartup(StartupEventArgs e)
    {
        try
        {
            Database = new DatabaseService();
            Database.Initialize();
            try { Database.AutoBackup(); } catch { }

            var seedImporter = new SeedImporter(Database);
            seedImporter.ImportAll();

            Database.EnsureBookingTables();
            Database.EnsureBillingTables();
        }
        catch (Exception ex)
        {
            WriteStartupError(ex);
            MessageBox.Show(
                "WachauEtappe konnte die lokale Datenbank nicht initialisieren.\n\n" +
                "Fehlerdetails wurden unter %LOCALAPPDATA%\\WachauEtappe\\startup-error.log gespeichert.",
                "WachauEtappe – Startfehler",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
            Shutdown(-1);
            return;
        }

        // Zuerst die WPF-Oberfläche vollständig starten. Die Online-Synchronisierung
        // darf den UI-Thread niemals blockieren oder den Programmstart verhindern.
        base.OnStartup(e);

        _ = SyncRemoteHostsSafeAsync();
    }

    private async Task SyncRemoteHostsSafeAsync()
    {
        try
        {
            await new RemoteHostSyncService(Database).SyncAsync();
        }
        catch (Exception ex)
        {
            // Remote-Sync ist Komfortfunktion: lokal muss die Zentrale immer weiterlaufen.
            WriteStartupError(ex, "remote-host-sync");
        }
    }

    private static void WriteStartupError(Exception ex, string area = "startup")
    {
        try
        {
            var dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "WachauEtappe");
            Directory.CreateDirectory(dir);
            var path = Path.Combine(dir, "startup-error.log");
            File.AppendAllText(
                path,
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {area}: {ex}\r\n\r\n");
        }
        catch
        {
            // Logging darf niemals selbst den Start verhindern.
        }
    }
}
