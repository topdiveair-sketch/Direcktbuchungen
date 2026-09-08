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
        new SeedImporter(Database).ImportAll();
        base.OnStartup(e);
    }
}
