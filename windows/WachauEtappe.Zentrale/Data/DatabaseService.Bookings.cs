using Microsoft.Data.Sqlite;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale.Data;

public sealed partial class DatabaseService
{
    public void EnsureBookingTables()
    {
        Execute("CREATE TABLE IF NOT EXISTS Bookings(Id TEXT PRIMARY KEY,Reference TEXT NOT NULL UNIQUE,HostId TEXT NOT NULL,StayDate TEXT NOT NULL,Guests INTEGER NOT NULL DEFAULT 1,GuestName TEXT,GuestEmail TEXT,GuestPhone TEXT,Status TEXT NOT NULL DEFAULT 'requested',Price REAL,PaymentMethod TEXT NOT NULL DEFAULT 'host',CreatedUtc TEXT NOT NULL,UpdatedUtc TEXT,Note TEXT)");
        Execute("CREATE INDEX IF NOT EXISTS IX_Bookings_HostDate ON Bookings(HostId,StayDate)");
    }

    public List<BookingSearchResult> SearchBookableHosts(string location,string stayDate,bool requireLuggage=false)
    {
        EnsureBookingTables();
        var rows=new List<BookingSearchResult>();
        using var c=new SqliteConnection(ConnectionString); c.Open();
        using var q=c.CreateCommand();
        q.CommandText="""
SELECT h.Id,h.Name,COALESCE(h.Location,''),COALESCE(a.Status,'unknown'),a.Price,
       h.OneNightVerified,h.CashAtHostVerified,h.LuggageVerified,
       COALESCE(h.DirectUrl,''),COALESCE(h.Email,''),COALESCE(h.Phone,'')
FROM Hosts h
LEFT JOIN Availability a ON a.HostId=h.Id AND a.StayDate=@date
WHERE h.Published=1 AND h.Status='verified' AND h.AcceptingBookings=1
  AND h.OneNightVerified=1 AND h.CashAtHostVerified=1
  AND (@luggage=0 OR h.LuggageVerified=1)
  AND (@location='' OR lower(COALESCE(h.Location,'')) LIKE '%'||lower(@location)||'%')
  AND COALESCE(a.Status,'unknown') <> 'blocked'
  AND NOT EXISTS(
      SELECT 1 FROM Bookings b
      WHERE b.HostId=h.Id AND b.StayDate=@date AND b.Status IN ('requested','confirmed')
  )
ORDER BY CASE COALESCE(a.Status,'unknown') WHEN 'available' THEN 0 ELSE 1 END,
         CASE WHEN a.Price IS NULL THEN 1 ELSE 0 END,a.Price,h.Name
""";
        q.Parameters.AddWithValue("@location",location?.Trim()??"");
        q.Parameters.AddWithValue("@date",stayDate);
        q.Parameters.AddWithValue("@luggage",requireLuggage?1:0);
        using var r=q.ExecuteReader();
        while(r.Read()) rows.Add(new BookingSearchResult{
            HostId=r.GetString(0),Name=r.GetString(1),Location=r.GetString(2),Availability=r.GetString(3),
            Price=r.IsDBNull(4)?null:r.GetDouble(4),OneNight=r.GetInt32(5)==1,CashAtHost=r.GetInt32(6)==1,
            Luggage=r.GetInt32(7)==1,DirectUrl=r.GetString(8),Email=r.GetString(9),Phone=r.GetString(10)});
        return rows;
    }

    public string CreateBooking(string hostId,string stayDate,int guests,string guestName,string guestEmail,string guestPhone,double? price,string note="")
    {
        EnsureBookingTables();
        var id=Guid.NewGuid().ToString("N");
        var reference=$"WB-{DateTime.Now:yyyyMMdd}-{Guid.NewGuid().ToString("N")[..5].ToUpperInvariant()}";
        Execute("INSERT INTO Bookings(Id,Reference,HostId,StayDate,Guests,GuestName,GuestEmail,GuestPhone,Status,Price,PaymentMethod,CreatedUtc,UpdatedUtc,Note) VALUES(@id,@r,@h,@d,@g,@n,@e,@p,'requested',@price,'host',@u,@u,@note)",
            ("@id",id),("@r",reference),("@h",hostId),("@d",stayDate),("@g",Math.Max(1,guests)),("@n",guestName),("@e",guestEmail),("@p",guestPhone),("@price",price),("@u",DateTime.UtcNow.ToString("O")),("@note",note));
        Audit("booking_created","Booking",id,reference);
        return reference;
    }

    public List<Dictionary<string,object?>> GetBookings()
    {
        EnsureBookingTables();
        var result=new List<Dictionary<string,object?>>();
        using var c=new SqliteConnection(ConnectionString); c.Open(); using var q=c.CreateCommand();
        q.CommandText="SELECT b.Id,b.Reference,h.Name AS Host,b.StayDate,b.Guests,COALESCE(b.GuestName,''),COALESCE(b.GuestEmail,''),b.Status,b.Price,b.PaymentMethod FROM Bookings b JOIN Hosts h ON h.Id=b.HostId ORDER BY b.StayDate,b.CreatedUtc DESC";
        using var r=q.ExecuteReader();
        while(r.Read()) result.Add(new Dictionary<string,object?>{{"Id",r.GetString(0)},{"Referenz",r.GetString(1)},{"Gastgeber",r.GetString(2)},{"Datum",r.GetString(3)},{"Personen",r.GetInt32(4)},{"Gast",r.GetString(5)},{"E-Mail",r.GetString(6)},{"Status",r.GetString(7)},{"Preis",r.IsDBNull(8)?null:r.GetDouble(8)},{"Zahlung",r.GetString(9)}});
        return result;
    }

    public void SetBookingStatus(string id,string status)
    {
        EnsureBookingTables();
        Execute("UPDATE Bookings SET Status=@s,UpdatedUtc=@u WHERE Id=@id",("@s",status),("@u",DateTime.UtcNow.ToString("O")),("@id",id));
        Audit("booking_status","Booking",id,status);
    }
}
