using Microsoft.Data.Sqlite;

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
          DirectUrl TEXT, Email TEXT, Phone TEXT, RawJson TEXT NOT NULL, UpdatedUtc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS Candidates (
          Id INTEGER PRIMARY KEY AUTOINCREMENT, Name TEXT NOT NULL, Location TEXT, Priority TEXT,
          Status TEXT, FitScore INTEGER, RawJson TEXT NOT NULL, UNIQUE(Name, Location)
        );
        CREATE TABLE IF NOT EXISTS Routes (
          Id TEXT PRIMARY KEY, Name TEXT NOT NULL, RawJson TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS Coverage (
          Location TEXT PRIMARY KEY, Status TEXT NOT NULL, Need INTEGER NOT NULL DEFAULT 0,
          RawJson TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS Trips (
          Id TEXT PRIMARY KEY, Reference TEXT NOT NULL UNIQUE, GuestName TEXT, StartDate TEXT,
          RouteId TEXT, Status TEXT NOT NULL, LuggageTransfer INTEGER NOT NULL DEFAULT 0,
          CreatedUtc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS TripDays (
          Id INTEGER PRIMARY KEY AUTOINCREMENT, TripId TEXT NOT NULL, DayNumber INTEGER NOT NULL,
          TravelDate TEXT, FromPlace TEXT, ToPlace TEXT, DistanceKm REAL, HostId TEXT,
          FOREIGN KEY(TripId) REFERENCES Trips(Id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS AuditEvents (
          Id INTEGER PRIMARY KEY AUTOINCREMENT, CreatedUtc TEXT NOT NULL, EventType TEXT NOT NULL,
          EntityType TEXT, EntityId TEXT, Details TEXT
        );
        """;
        command.ExecuteNonQuery();
    }

    public void Execute(string sql, params (string Name, object? Value)[] values)
    {
        using var connection = new SqliteConnection(ConnectionString);
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        foreach (var value in values)
            command.Parameters.AddWithValue(value.Name, value.Value ?? DBNull.Value);
        command.ExecuteNonQuery();
    }

    public int ScalarInt(string sql)
    {
        using var connection = new SqliteConnection(ConnectionString);
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToInt32(command.ExecuteScalar() ?? 0);
    }
}
