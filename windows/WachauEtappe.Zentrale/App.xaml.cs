using System.IO;
using System.Windows;
using System.Windows.Threading;
using WachauEtappe.Zentrale.Data;
using WachauEtappe.Zentrale.Services;

namespace WachauEtappe.Zentrale;

public partial class App : Application
{
    public static DatabaseService Database { get; private set; } = null!;
    private DispatcherTimer? _liveSyncTimer;

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

        // Zuerst die WPF-Oberfläche vollständig starten. Kein Netzwerkzugriff darf
        // den UI-Thread blockieren oder den Programmstart verhindern.
        base.OnStartup(e);

        _ = InitialOnlineSyncSafeAsync();
        StartLiveSyncTimer();
    }

    private async Task InitialOnlineSyncSafeAsync()
    {
        try
        {
            // hosts.json bleibt nur Bootstrap/Fallback. Railway ist danach führend.
            await new RemoteHostSyncService(Database).SyncAsync();
            if (LiveCentralSyncService.IsConfigured)
            {
                await HostLivePushService.PushPendingAsync(Database);
                await LiveCentralSyncService.SyncAsync(Database);
            }
        }
        catch (Exception ex)
        {
            WriteStartupError(ex, "initial-online-sync");
        }
    }

    private void StartLiveSyncTimer()
    {
        _liveSyncTimer = new DispatcherTimer(DispatcherPriority.Background)
        {
            Interval = TimeSpan.FromSeconds(30)
        };
        _liveSyncTimer.Tick += async (_, _) =>
        {
            if (!LiveCentralSyncService.IsConfigured) return;
            try
            {
                // Lokale Bedieneränderungen zuerst hochladen, dann zentralen Stand
                // zurückholen. So kann ein Live-Pull keine ungesendete Änderung überschreiben.
                await HostLivePushService.PushPendingAsync(Database);
                await LiveCentralSyncService.SyncAsync(Database);
            }
            catch (Exception ex) { WriteStartupError(ex, "live-sync"); }
        };
        _liveSyncTimer.Start();
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
