using Microsoft.Data.Sqlite;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale.Data;

public sealed partial class DatabaseService
{
    public void EnsureMapTables()
    {
        EnsureBookingTables();
        using var c=new SqliteConnection(ConnectionString); c.Open();
        EnsureColumn(c,"HostCapacity","Beds","INTEGER NOT NULL DEFAULT 2");
        EnsureColumn(c,"Availability","RoomsFree","INTEGER");
        EnsureColumn(c,"Availability","Source","TEXT");
        EnsureColumn(c,"Availability","UpdatedUtc","TEXT");
    }

    public int GetHostBeds(string hostId)
    {
        EnsureMapTables();
        using var c=new SqliteConnection(ConnectionString); c.Open(); using var q=c.CreateCommand();
        q.CommandText="SELECT COALESCE((SELECT Beds FROM HostCapacity WHERE HostId=@h),COALESCE((SELECT Units FROM HostCapacity WHERE HostId=@h),1)*2)";
        q.Parameters.AddWithValue("@h",hostId);
        return Math.Max(1,Convert.ToInt32(q.ExecuteScalar()??2));
    }

    public void SetHostCapacityAndBeds(string hostId,int rooms,int beds)
    {
        EnsureMapTables();
        rooms=Math.Max(1,rooms); beds=Math.Max(1,beds);
        Execute("INSERT INTO HostCapacity(HostId,Units,Beds,UpdatedUtc) VALUES(@h,@r,@b,@t) ON CONFLICT(HostId) DO UPDATE SET Units=@r,Beds=@b,UpdatedUtc=@t",
            ("@h",hostId),("@r",rooms),("@b",beds),("@t",DateTime.UtcNow.ToString("O")));
        Audit("host_capacity","Host",hostId,$"rooms={rooms}; beds={beds}");
    }

    public void UpsertOnlinePartnerAvailability(string hostId,string name,string location,int roomsTotal,string stayDate,string status,int roomsFree,double? price,bool bookingBlocked,string updatedAt)
    {
        EnsureMapTables();
        roomsTotal=Math.Max(1,roomsTotal);
        roomsFree=Math.Max(0,Math.Min(roomsTotal,roomsFree));
        status=(status??"unknown").Trim().ToLowerInvariant();
        if(bookingBlocked || status is "full" or "closed" or "blocked") { status="full"; roomsFree=0; }

        using var c=new SqliteConnection(ConnectionString); c.Open(); using var tx=c.BeginTransaction();
        using(var h=c.CreateCommand())
        {
            h.Transaction=tx;
            h.CommandText="""
INSERT INTO Hosts(Id,Name,Location,Status,Published,AcceptingBookings,DirectUrl,Email,Phone,RawJson,UpdatedUtc,OneNightVerified,CashAtHostVerified,LuggageVerified)
VALUES(@id,@n,@l,'verified',1,1,'','','','{}',@u,1,1,0)
ON CONFLICT(Id) DO UPDATE SET Name=@n,Location=@l,Published=1,AcceptingBookings=1,UpdatedUtc=@u
""";
            h.Parameters.AddWithValue("@id",hostId);h.Parameters.AddWithValue("@n",name);h.Parameters.AddWithValue("@l",location);h.Parameters.AddWithValue("@u",DateTime.UtcNow.ToString("O"));h.ExecuteNonQuery();
        }
        using(var cap=c.CreateCommand())
        {
            cap.Transaction=tx;
            cap.CommandText="INSERT INTO HostCapacity(HostId,Units,Beds,UpdatedUtc) VALUES(@h,@r,@b,@u) ON CONFLICT(HostId) DO UPDATE SET Units=@r,UpdatedUtc=@u";
            cap.Parameters.AddWithValue("@h",hostId);cap.Parameters.AddWithValue("@r",roomsTotal);cap.Parameters.AddWithValue("@b",Math.Max(2,roomsTotal*2));cap.Parameters.AddWithValue("@u",DateTime.UtcNow.ToString("O"));cap.ExecuteNonQuery();
        }
        using(var a=c.CreateCommand())
        {
            a.Transaction=tx;
            a.CommandText="""
INSERT INTO Availability(HostId,StayDate,Status,Price,Note,RoomsFree,Source,UpdatedUtc)
VALUES(@h,@d,@s,@p,@n,@r,'partner-online',@u)
ON CONFLICT(HostId,StayDate) DO UPDATE SET Status=@s,Price=@p,Note=@n,RoomsFree=@r,Source='partner-online',UpdatedUtc=@u
""";
            a.Parameters.AddWithValue("@h",hostId);a.Parameters.AddWithValue("@d",stayDate);a.Parameters.AddWithValue("@s",status);a.Parameters.AddWithValue("@p",(object?)price??DBNull.Value);a.Parameters.AddWithValue("@n",bookingBlocked?"Booking.com Kalender: belegt":"Partnerportal synchronisiert");a.Parameters.AddWithValue("@r",roomsFree);a.Parameters.AddWithValue("@u",string.IsNullOrWhiteSpace(updatedAt)?DateTime.UtcNow.ToString("O"):updatedAt);a.ExecuteNonQuery();
        }
        tx.Commit();
    }

    public List<MapHostStatus> GetMapHostStatuses(string stayDate)
    {
        EnsureMapTables();
        var result=new List<MapHostStatus>();
        using var c=new SqliteConnection(ConnectionString); c.Open(); using var q=c.CreateCommand();
        q.CommandText="""
SELECT h.Id,h.Name,COALESCE(h.Location,''),COALESCE(h.Phone,''),
       COALESCE(cap.Units,1),COALESCE(cap.Beds,COALESCE(cap.Units,1)*2),
       COALESCE(a.Status,'unknown'),a.RoomsFree,COALESCE(a.Source,''),
       (SELECT COUNT(*) FROM Bookings b WHERE b.HostId=h.Id AND b.StayDate=@d AND b.Status IN ('requested','confirmed')) AS UsedRooms,
       COALESCE((SELECT SUM(b.Guests) FROM Bookings b WHERE b.HostId=h.Id AND b.StayDate=@d AND b.Status IN ('requested','confirmed')),0) AS UsedBeds
FROM Hosts h
LEFT JOIN HostCapacity cap ON cap.HostId=h.Id
LEFT JOIN Availability a ON a.HostId=h.Id AND a.StayDate=@d
WHERE h.Published=1
ORDER BY h.Location,h.Name
""";
        q.Parameters.AddWithValue("@d",stayDate);
        using var r=q.ExecuteReader();
        while(r.Read())
        {
            var rooms=Math.Max(1,r.GetInt32(4)); var beds=Math.Max(1,r.GetInt32(5));
            var availability=r.GetString(6).Trim().ToLowerInvariant();
            var reportedRooms=r.IsDBNull(7)?(int?)null:Math.Max(0,r.GetInt32(7));
            var source=r.GetString(8);
            var usedRooms=Math.Max(0,r.GetInt32(9)); var usedBeds=Math.Max(0,r.GetInt32(10));
            var freeRooms=reportedRooms.HasValue && source=="partner-online" ? Math.Min(rooms,reportedRooms.Value) : Math.Max(0,rooms-usedRooms);
            var freeBeds=Math.Max(0,beds-usedBeds);
            if(reportedRooms.HasValue && source=="partner-online" && rooms>0)
            {
                var bedsPerRoom=Math.Max(1,(int)Math.Ceiling((double)beds/rooms));
                freeBeds=Math.Min(beds,freeRooms*bedsPerRoom);
            }
            if(availability is "blocked" or "full" or "closed"){freeRooms=0;freeBeds=0;}
            var color="gray"; var label="Nicht gemeldet";
            if(availability is "blocked" or "full" or "closed" || freeRooms==0 || freeBeds==0){color="red";label="Besetzt";}
            else if(availability is "available" or "free")
            {
                color=(freeRooms==1 || freeBeds<=2)?"orange":"green";
                label=color=="orange"?"Wenig frei":"Frei";
            }
            else if(usedRooms>0)
            {
                color=(freeRooms==1 || freeBeds<=2)?"orange":"green";
                label=color=="orange"?"Wenig frei":"Frei";
            }
            var location=r.GetString(2); var coord=ResolveLocationCoordinate(location);
            result.Add(new MapHostStatus{HostId=r.GetString(0),Name=r.GetString(1),Location=location,Phone=r.GetString(3),RoomsTotal=rooms,RoomsFree=freeRooms,BedsTotal=beds,BedsFree=freeBeds,Availability=availability,DisplayStatus=label,StatusColor=color,Latitude=coord.lat,Longitude=coord.lon,HasCoordinates=coord.ok});
        }
        return result;
    }

    private static (double lat,double lon,bool ok) ResolveLocationCoordinate(string location)
    {
        var x=(location??"").ToLowerInvariant();
        if(x.Contains("aggsbach markt")) return (48.2947,15.4046,true);
        if(x.Contains("aggsbach dorf")) return (48.2956,15.4879,true);
        if(x.Contains("krems")) return (48.4108,15.6021,true);
        if(x.Contains("dürnstein")||x.Contains("duernstein")||x.Contains("unterloiben")) return (48.3951,15.5195,true);
        if(x.Contains("weißenkirchen")||x.Contains("weissenkirchen")) return (48.3975,15.4695,true);
        if(x.Contains("wösendorf")||x.Contains("woesendorf")) return (48.3839,15.4509,true);
        if(x.Contains("st. michael")||x.Contains("sankt michael")) return (48.3800,15.4381,true);
        if(x.Contains("spitz")) return (48.3657,15.4145,true);
        if(x.Contains("mühldorf")||x.Contains("muehldorf")) return (48.3745,15.3479,true);
        if(x.Contains("maria laach")) return (48.3049,15.3474,true);
        if(x.Contains("maria langegg")) return (48.3152,15.5439,true);
        if(x.Contains("emmersdorf")) return (48.2417,15.3376,true);
        if(x.Contains("melk")) return (48.2274,15.3319,true);
        if(x.Contains("hofarnsdorf")) return (48.3605,15.4324,true);
        if(x.Contains("oberarnsdorf")) return (48.3561,15.4214,true);
        if(x.Contains("bacharnsdorf")) return (48.3537,15.4078,true);
        if(x.Contains("rossatz")) return (48.3965,15.5083,true);
        if(x.Contains("unterbergern")) return (48.3654,15.5837,true);
        if(x.Contains("mautern")) return (48.3939,15.5782,true);
        return (0,0,false);
    }
}
