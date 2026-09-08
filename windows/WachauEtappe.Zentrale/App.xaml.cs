using System.Windows;
using WachauEtappe.Zentrale.Data;

namespace WachauEtappe.Zentrale;

public partial class App : Application
{
    public static DatabaseService Database { get; private set; } = null!;

    protected override void OnStartup(StartupEventArgs e)
    {
        Database = new DatabaseService();
        Database.Initialize();
        try{Database.AutoBackup();}catch{}
        new SeedImporter(Database).ImportAll();
        Database.EnsureBookingTables();
        base.OnStartup(e);
    }
}
