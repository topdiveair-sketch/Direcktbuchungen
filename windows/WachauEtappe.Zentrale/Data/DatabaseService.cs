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
        using var connection = new SqliteConnection(ConnectionString); connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS Hosts (Id TEXT PRIMARY KEY, Name TEXT NOT NULL, Location TEXT, Status TEXT NOT NULL, Published INTEGER NOT NULL DEFAULT 0, AcceptingBookings INTEGER NOT NULL DEFAULT 0, DirectUrl TEXT, Email TEXT, Phone TEXT, RawJson TEXT NOT NULL, UpdatedUtc TEXT NOT NULL, OneNightVerified INTEGER NOT NULL DEFAULT 0, CashAtHostVerified INTEGER NOT NULL DEFAULT 0, LuggageVerified INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Candidates (Id INTEGER PRIMARY KEY AUTOINCREMENT, Name TEXT NOT NULL, Location TEXT, Priority TEXT, Status TEXT, FitScore INTEGER, RawJson TEXT NOT NULL, UNIQUE(Name, Location));
        CREATE TABLE IF NOT EXISTS Routes (Id TEXT PRIMARY KEY, Name TEXT NOT NULL, RawJson TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Coverage (Location TEXT PRIMARY KEY, Status TEXT NOT NULL, Need INTEGER NOT NULL DEFAULT 0, RawJson TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Trips (Id TEXT PRIMARY KEY, Reference TEXT NOT NULL UNIQUE, GuestName TEXT, GuestEmail TEXT, GuestPhone TEXT, Guests INTEGER NOT NULL DEFAULT 1, DailyTargetKm REAL NOT NULL DEFAULT 18, StartDate TEXT, RouteId TEXT, Status TEXT NOT NULL, LuggageTransfer INTEGER NOT NULL DEFAULT 0, CreatedUtc TEXT NOT NULL, UpdatedUtc TEXT);
        CREATE TABLE IF NOT EXISTS TripDays (Id INTEGER PRIMARY KEY AUTOINCREMENT, TripId TEXT NOT NULL, DayNumber INTEGER NOT NULL, TravelDate TEXT, FromPlace TEXT, ToPlace TEXT, DistanceKm REAL, HostId TEXT, BookingStatus TEXT NOT NULL DEFAULT 'open', LuggageStatus TEXT NOT NULL DEFAULT 'none', FOREIGN KEY(TripId) REFERENCES Trips(Id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS Availability (Id INTEGER PRIMARY KEY AUTOINCREMENT, HostId TEXT NOT NULL, StayDate TEXT NOT NULL, Status TEXT NOT NULL DEFAULT 'unknown', Price REAL, Note TEXT, UNIQUE(HostId,StayDate));
        CREATE TABLE IF NOT EXISTS Cancellations (Id INTEGER PRIMARY KEY AUTOINCREMENT, TripId TEXT NOT NULL, TripDayId INTEGER, RequestedUtc TEXT NOT NULL, Status TEXT NOT NULL DEFAULT 'requested', FeePercent INTEGER NOT NULL DEFAULT 0, FeeAmount REAL, Resold INTEGER NOT NULL DEFAULT 0, Note TEXT);
        CREATE TABLE IF NOT EXISTS LuggageTransfers (Id INTEGER PRIMARY KEY AUTOINCREMENT, TripId TEXT NOT NULL, TripDayId INTEGER, PickupHostId TEXT, DropoffHostId TEXT, TransferDate TEXT, Status TEXT NOT NULL DEFAULT 'requested', Provider TEXT, Note TEXT);
        CREATE TABLE IF NOT EXISTS AuditEvents (Id INTEGER PRIMARY KEY AUTOINCREMENT, CreatedUtc TEXT NOT NULL, EventType TEXT NOT NULL, EntityType TEXT, EntityId TEXT, Details TEXT);
        """;
        command.ExecuteNonQuery();
        EnsureColumn(connection,"Hosts","OneNightVerified","INTEGER NOT NULL DEFAULT 0"); EnsureColumn(connection,"Hosts","CashAtHostVerified","INTEGER NOT NULL DEFAULT 0"); EnsureColumn(connection,"Hosts","LuggageVerified","INTEGER NOT NULL DEFAULT 0");
        EnsureColumn(connection,"Trips","GuestEmail","TEXT"); EnsureColumn(connection,"Trips","GuestPhone","TEXT"); EnsureColumn(connection,"Trips","Guests","INTEGER NOT NULL DEFAULT 1"); EnsureColumn(connection,"Trips","DailyTargetKm","REAL NOT NULL DEFAULT 18"); EnsureColumn(connection,"Trips","UpdatedUtc","TEXT");
        EnsureColumn(connection,"TripDays","BookingStatus","TEXT NOT NULL DEFAULT 'open'"); EnsureColumn(connection,"TripDays","LuggageStatus","TEXT NOT NULL DEFAULT 'none'");
    }

    private static void EnsureColumn(SqliteConnection connection,string table,string column,string definition){using var check=connection.CreateCommand();check.CommandText=$"PRAGMA table_info({table})";using var reader=check.ExecuteReader();while(reader.Read())if(string.Equals(reader.GetString(1),column,StringComparison.OrdinalIgnoreCase))return;reader.Close();using var alter=connection.CreateCommand();alter.CommandText=$"ALTER TABLE {table} ADD COLUMN {column} {definition}";alter.ExecuteNonQuery();}

    public List<HostRecord> GetHosts(string? search=null){var result=new List<HostRecord>();using var c=new SqliteConnection(ConnectionString);c.Open();using var cmd=c.CreateCommand();cmd.CommandText="SELECT Id,Name,COALESCE(Location,''),Status,Published,AcceptingBookings,COALESCE(DirectUrl,''),COALESCE(Email,''),COALESCE(Phone,''),OneNightVerified,CashAtHostVerified,LuggageVerified FROM Hosts WHERE @q='' OR Name LIKE '%'||@q||'%' OR Location LIKE '%'||@q||'%' ORDER BY Published DESC,Name";cmd.Parameters.AddWithValue("@q",search?.Trim()??"");using var r=cmd.ExecuteReader();while(r.Read())result.Add(new HostRecord{Id=r.GetString(0),Name=r.GetString(1),Location=r.GetString(2),Status=r.GetString(3),Published=r.GetInt32(4)==1,AcceptingBookings=r.GetInt32(5)==1,DirectUrl=r.GetString(6),Email=r.GetString(7),Phone=r.GetString(8),OneNightVerified=r.GetInt32(9)==1,CashAtHostVerified=r.GetInt32(10)==1,LuggageVerified=r.GetInt32(11)==1});return result;}
    public void SaveHost(HostRecord h){Execute("UPDATE Hosts SET Name=@n,Location=@l,Status=@s,Published=@p,AcceptingBookings=@a,DirectUrl=@u,Email=@e,Phone=@ph,OneNightVerified=@o,CashAtHostVerified=@c,LuggageVerified=@g,UpdatedUtc=@utc WHERE Id=@id",("@n",h.Name),("@l",h.Location),("@s",h.Status),("@p",h.Published?1:0),("@a",h.AcceptingBookings?1:0),("@u",h.DirectUrl),("@e",h.Email),("@ph",h.Phone),("@o",h.OneNightVerified?1:0),("@c",h.CashAtHostVerified?1:0),("@g",h.LuggageVerified?1:0),("@utc",DateTime.UtcNow.ToString("O")),("@id",h.Id));Audit("host_saved","Host",h.Id,$"{h.Name}; status={h.Status}; published={h.Published}");}
    public void SetHostPublication(string id,bool p){Execute("UPDATE Hosts SET Published=@p,Status=CASE WHEN @p=1 THEN 'verified' ELSE Status END,UpdatedUtc=@u WHERE Id=@id",("@p",p?1:0),("@u",DateTime.UtcNow.ToString("O")),("@id",id));Audit(p?"host_published":"host_unpublished","Host",id,null);}

    public List<TripRecord> GetTrips(){var x=new List<TripRecord>();using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();q.CommandText="SELECT Id,Reference,COALESCE(GuestName,''),COALESCE(GuestEmail,''),COALESCE(GuestPhone,''),COALESCE(StartDate,''),COALESCE(RouteId,''),Status,LuggageTransfer,Guests,DailyTargetKm FROM Trips ORDER BY StartDate,CreatedUtc DESC";using var r=q.ExecuteReader();while(r.Read())x.Add(new TripRecord{Id=r.GetString(0),Reference=r.GetString(1),GuestName=r.GetString(2),GuestEmail=r.GetString(3),GuestPhone=r.GetString(4),StartDate=r.GetString(5),RouteId=r.GetString(6),Status=r.GetString(7),LuggageTransfer=r.GetInt32(8)==1,Guests=r.GetInt32(9),DailyTargetKm=r.GetDouble(10)});return x;}
    public void SaveTrip(TripRecord t){if(string.IsNullOrWhiteSpace(t.Reference))t.Reference=$"WE-{DateTime.Now:yyyyMMdd}-{Guid.NewGuid().ToString("N")[..5].ToUpperInvariant()}";Execute("INSERT INTO Trips(Id,Reference,GuestName,GuestEmail,GuestPhone,Guests,DailyTargetKm,StartDate,RouteId,Status,LuggageTransfer,CreatedUtc,UpdatedUtc) VALUES(@id,@r,@n,@e,@p,@g,@km,@d,@route,@s,@l,@u,@u) ON CONFLICT(Id) DO UPDATE SET GuestName=@n,GuestEmail=@e,GuestPhone=@p,Guests=@g,DailyTargetKm=@km,StartDate=@d,RouteId=@route,Status=@s,LuggageTransfer=@l,UpdatedUtc=@u",("@id",t.Id),("@r",t.Reference),("@n",t.GuestName),("@e",t.GuestEmail),("@p",t.GuestPhone),("@g",t.Guests),("@km",t.DailyTargetKm),("@d",t.StartDate),("@route",t.RouteId),("@s",t.Status),("@l",t.LuggageTransfer?1:0),("@u",DateTime.UtcNow.ToString("O")));Audit("trip_saved","Trip",t.Id,t.Reference);}
    public List<TripDayRecord> GetTripDays(string tripId){var x=new List<TripDayRecord>();using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();q.CommandText="SELECT d.Id,d.TripId,d.DayNumber,COALESCE(d.TravelDate,''),COALESCE(d.FromPlace,''),COALESCE(d.ToPlace,''),COALESCE(d.DistanceKm,0),COALESCE(d.HostId,''),COALESCE(h.Name,''),d.BookingStatus,d.LuggageStatus FROM TripDays d LEFT JOIN Hosts h ON h.Id=d.HostId WHERE d.TripId=@id ORDER BY d.DayNumber";q.Parameters.AddWithValue("@id",tripId);using var r=q.ExecuteReader();while(r.Read())x.Add(new TripDayRecord{Id=r.GetInt64(0),TripId=r.GetString(1),DayNumber=r.GetInt32(2),TravelDate=r.GetString(3),FromPlace=r.GetString(4),ToPlace=r.GetString(5),DistanceKm=r.GetDouble(6),HostId=r.GetString(7),HostName=r.GetString(8),BookingStatus=r.GetString(9),LuggageStatus=r.GetString(10)});return x;}
    public void AddTripDay(string tripId,int day,string date,string from,string to,double km,string? hostId,bool luggage){Execute("INSERT INTO TripDays(TripId,DayNumber,TravelDate,FromPlace,ToPlace,DistanceKm,HostId,BookingStatus,LuggageStatus) VALUES(@t,@d,@date,@f,@to,@km,@h,'open',@l)",("@t",tripId),("@d",day),("@date",date),("@f",from),("@to",to),("@km",km),("@h",hostId),("@l",luggage?"requested":"none"));Audit("trip_day_added","Trip",tripId,$"Tag {day}: {from} - {to}");}
    public void SetTripDayStatus(long id,string bookingStatus,string luggageStatus){Execute("UPDATE TripDays SET BookingStatus=@b,LuggageStatus=@l WHERE Id=@id",("@b",bookingStatus),("@l",luggageStatus),("@id",id));Audit("trip_day_status","TripDay",id.ToString(),$"booking={bookingStatus}; luggage={luggageStatus}");}
    public void RequestCancellation(string tripId,long? dayId,int feePercent,string note){Execute("INSERT INTO Cancellations(TripId,TripDayId,RequestedUtc,FeePercent,Note) VALUES(@t,@d,@u,@f,@n)",("@t",tripId),("@d",dayId),("@u",DateTime.UtcNow.ToString("O")),("@f",feePercent),("@n",note));Audit("cancellation_requested","Trip",tripId,$"fee={feePercent}%");}

    public void Audit(string eventType,string entityType,string? entityId,string? details)=>Execute("INSERT INTO AuditEvents(CreatedUtc,EventType,EntityType,EntityId,Details) VALUES(@u,@e,@t,@id,@d)",("@u",DateTime.UtcNow.ToString("O")),("@e",eventType),("@t",entityType),("@id",entityId),("@d",details));
    public void Execute(string sql,params (string Name,object? Value)[] values){using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();q.CommandText=sql;foreach(var v in values)q.Parameters.AddWithValue(v.Name,v.Value??DBNull.Value);q.ExecuteNonQuery();}
    public int ScalarInt(string sql){using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();q.CommandText=sql;return Convert.ToInt32(q.ExecuteScalar()??0);}
}
