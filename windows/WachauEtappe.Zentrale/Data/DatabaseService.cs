using Microsoft.Data.Sqlite;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale.Data;

public sealed class DatabaseService
{
    public string DatabasePath { get; }
    private string ConnectionString => $"Data Source={DatabasePath}";

    public DatabaseService()
    {
        var folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WachauEtappe", "Zentrale");
        Directory.CreateDirectory(folder);
        DatabasePath = Path.Combine(folder, "wachauetappe.db");
    }

    public void Initialize()
    {
        using var connection = new SqliteConnection(ConnectionString);
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS Hosts (
          Id TEXT PRIMARY KEY, Name TEXT NOT NULL, Location TEXT, Status TEXT NOT NULL,
          Published INTEGER NOT NULL DEFAULT 0, AcceptingBookings INTEGER NOT NULL DEFAULT 0,
          DirectUrl TEXT, Email TEXT, Phone TEXT, RawJson TEXT NOT NULL, UpdatedUtc TEXT NOT NULL,
          OneNightVerified INTEGER NOT NULL DEFAULT 0,
          CashAtHostVerified INTEGER NOT NULL DEFAULT 0,
          LuggageVerified INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS Candidates (
          Id INTEGER PRIMARY KEY AUTOINCREMENT, Name TEXT NOT NULL, Location TEXT, Priority TEXT,
          Status TEXT, FitScore INTEGER, RawJson TEXT NOT NULL, UNIQUE(Name, Location)
        );
        CREATE TABLE IF NOT EXISTS Routes (Id TEXT PRIMARY KEY, Name TEXT NOT NULL, RawJson TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Coverage (Location TEXT PRIMARY KEY, Status TEXT NOT NULL, Need INTEGER NOT NULL DEFAULT 0, RawJson TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Trips (Id TEXT PRIMARY KEY, Reference TEXT NOT NULL UNIQUE, GuestName TEXT, StartDate TEXT, RouteId TEXT, Status TEXT NOT NULL, LuggageTransfer INTEGER NOT NULL DEFAULT 0, CreatedUtc TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS TripDays (Id INTEGER PRIMARY KEY AUTOINCREMENT, TripId TEXT NOT NULL, DayNumber INTEGER NOT NULL, TravelDate TEXT, FromPlace TEXT, ToPlace TEXT, DistanceKm REAL, HostId TEXT, FOREIGN KEY(TripId) REFERENCES Trips(Id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS AuditEvents (Id INTEGER PRIMARY KEY AUTOINCREMENT, CreatedUtc TEXT NOT NULL, EventType TEXT NOT NULL, EntityType TEXT, EntityId TEXT, Details TEXT);
        """;
        command.ExecuteNonQuery();
        EnsureColumn(connection, "Hosts", "OneNightVerified", "INTEGER NOT NULL DEFAULT 0");
        EnsureColumn(connection, "Hosts", "CashAtHostVerified", "INTEGER NOT NULL DEFAULT 0");
        EnsureColumn(connection, "Hosts", "LuggageVerified", "INTEGER NOT NULL DEFAULT 0");
    }

    private static void EnsureColumn(SqliteConnection connection, string table, string column, string definition)
    {
        using var check = connection.CreateCommand();
        check.CommandText = $"PRAGMA table_info({table})";
        using var reader = check.ExecuteReader();
        while (reader.Read()) if (string.Equals(reader.GetString(1), column, StringComparison.OrdinalIgnoreCase)) return;
        reader.Close();
        using var alter = connection.CreateCommand();
        alter.CommandText = $"ALTER TABLE {table} ADD COLUMN {column} {definition}";
        alter.ExecuteNonQuery();
    }

    public List<HostRecord> GetHosts(string? search = null)
    {
        var result = new List<HostRecord>();
        using var connection = new SqliteConnection(ConnectionString);
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = """
          SELECT Id,Name,COALESCE(Location,''),Status,Published,AcceptingBookings,
                 COALESCE(DirectUrl,''),COALESCE(Email,''),COALESCE(Phone,''),
                 OneNightVerified,CashAtHostVerified,LuggageVerified
          FROM Hosts
          WHERE @q='' OR Name LIKE '%'||@q||'%' OR Location LIKE '%'||@q||'%'
          ORDER BY Published DESC, Name
        """;
        command.Parameters.AddWithValue("@q", search?.Trim() ?? "");
        using var reader = command.ExecuteReader();
        while (reader.Read()) result.Add(new HostRecord {
            Id=reader.GetString(0), Name=reader.GetString(1), Location=reader.GetString(2), Status=reader.GetString(3),
            Published=reader.GetInt32(4)==1, AcceptingBookings=reader.GetInt32(5)==1, DirectUrl=reader.GetString(6),
            Email=reader.GetString(7), Phone=reader.GetString(8), OneNightVerified=reader.GetInt32(9)==1,
            CashAtHostVerified=reader.GetInt32(10)==1, LuggageVerified=reader.GetInt32(11)==1
        });
        return result;
    }

    public void SaveHost(HostRecord host)
    {
        Execute("""
          UPDATE Hosts SET Name=@name,Location=@location,Status=@status,Published=@published,
          AcceptingBookings=@accepting,DirectUrl=@url,Email=@email,Phone=@phone,
          OneNightVerified=@one,CashAtHostVerified=@cash,LuggageVerified=@luggage,UpdatedUtc=@utc
          WHERE Id=@id
        """, ("@name",host.Name),("@location",host.Location),("@status",host.Status),("@published",host.Published?1:0),
        ("@accepting",host.AcceptingBookings?1:0),("@url",host.DirectUrl),("@email",host.Email),("@phone",host.Phone),
        ("@one",host.OneNightVerified?1:0),("@cash",host.CashAtHostVerified?1:0),("@luggage",host.LuggageVerified?1:0),
        ("@utc",DateTime.UtcNow.ToString("O")),("@id",host.Id));
        Audit("host_saved", host.Id, $"{host.Name}; status={host.Status}; published={host.Published}");
    }

    public void SetHostPublication(string id, bool published)
    {
        Execute("UPDATE Hosts SET Published=@p, Status=CASE WHEN @p=1 THEN 'verified' ELSE Status END, UpdatedUtc=@utc WHERE Id=@id",
            ("@p",published?1:0),("@utc",DateTime.UtcNow.ToString("O")),("@id",id));
        Audit(published ? "host_published" : "host_unpublished", id, null);
    }

    public void Audit(string eventType, string? entityId, string? details) => Execute(
        "INSERT INTO AuditEvents(CreatedUtc,EventType,EntityType,EntityId,Details) VALUES(@utc,@event,'Host',@id,@details)",
        ("@utc",DateTime.UtcNow.ToString("O")),("@event",eventType),("@id",entityId),("@details",details));

    public void Execute(string sql, params (string Name, object? Value)[] values)
    {
        using var connection = new SqliteConnection(ConnectionString); connection.Open();
        using var command = connection.CreateCommand(); command.CommandText = sql;
        foreach (var value in values) command.Parameters.AddWithValue(value.Name, value.Value ?? DBNull.Value);
        command.ExecuteNonQuery();
    }

    public int ScalarInt(string sql)
    {
        using var connection = new SqliteConnection(ConnectionString); connection.Open();
        using var command = connection.CreateCommand(); command.CommandText = sql;
        return Convert.ToInt32(command.ExecuteScalar() ?? 0);
    }
}
