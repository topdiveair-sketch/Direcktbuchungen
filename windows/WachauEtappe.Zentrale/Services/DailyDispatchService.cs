using System.Globalization;

namespace WachauEtappe.Zentrale.Services;

public sealed record GuestDayPosition(string Reference,string Guest,string Date,string From,string To,string Host,string Status,string PositionText);
public sealed record LuggageRouteStop(int Sequence,string Action,long TransferId,string Reference,string Guest,string Place,string Host,string Phone,string FromHost,string ToHost,double DistanceFromPreviousKm,string Status);
public sealed record LuggageRoutePlan(IReadOnlyList<LuggageRouteStop> Stops,double EstimatedKm,string StartEnd);

public static class DailyDispatchService
{
    private const double AggsbachMarktLat=48.2947;
    private const double AggsbachMarktLon=15.4046;

    public static List<GuestDayPosition> GetGuestPositions(string day)
    {
        var rows=App.Database.QueryRows("""
SELECT t.Reference,COALESCE(t.GuestName,'') AS Guest,d.TravelDate,
       COALESCE(d.FromPlace,'') AS FromPlace,COALESCE(d.ToPlace,'') AS ToPlace,
       COALESCE(h.Name,'') AS HostName,COALESCE(d.BookingStatus,'open') AS BookingStatus
FROM TripDays d
JOIN Trips t ON t.Id=d.TripId
LEFT JOIN Hosts h ON h.Id=d.HostId
WHERE d.TravelDate=@day AND t.Status NOT IN ('cancelled','completed')
ORDER BY t.Reference,d.DayNumber
""",("@day",day));
        return rows.Select(r=>
        {
            var guest=S(r,"Guest");var from=S(r,"FromPlace");var to=S(r,"ToPlace");var host=S(r,"HostName");var status=S(r,"BookingStatus");
            var position=string.IsNullOrWhiteSpace(host)?$"Etappe {from} → {to}":$"Etappe {from} → {to} · Unterkunft: {host}";
            return new GuestDayPosition(S(r,"Reference"),guest,day,from,to,host,status,position);
        }).ToList();
    }

    public static LuggageRoutePlan BuildLuggageRoute(string day)
    {
        var rows=App.Database.QueryRows("""
SELECT l.Id,t.Reference,COALESCE(t.GuestName,'') AS Guest,l.PickupHostId,l.DropoffHostId,
       COALESCE(h1.Name,'') AS PickupName,COALESCE(h1.Location,'') AS PickupLocation,COALESCE(h1.Phone,'') AS PickupPhone,
       COALESCE(h2.Name,'') AS DropName,COALESCE(h2.Location,'') AS DropLocation,COALESCE(h2.Phone,'') AS DropPhone,
       COALESCE(l.Status,'requested') AS Status
FROM LuggageTransfers l
JOIN Trips t ON t.Id=l.TripId
LEFT JOIN Hosts h1 ON h1.Id=l.PickupHostId
LEFT JOIN Hosts h2 ON h2.Id=l.DropoffHostId
WHERE l.TransferDate=@day AND l.Status NOT IN ('delivered','cancelled') AND t.Status NOT IN ('cancelled','completed')
ORDER BY t.Reference,l.Id
""",("@day",day));

        var transfers=rows.Select(r=>new Transfer(
            Convert.ToInt64(r["Id"]??0),S(r,"Reference"),S(r,"Guest"),S(r,"PickupHostId"),S(r,"DropoffHostId"),
            S(r,"PickupName"),S(r,"PickupLocation"),S(r,"PickupPhone"),S(r,"DropName"),S(r,"DropLocation"),S(r,"DropPhone"),S(r,"Status"))).ToList();

        var pendingPickups=new HashSet<long>(transfers.Select(x=>x.Id));
        var picked=new HashSet<long>();
        var done=new HashSet<long>();
        var result=new List<LuggageRouteStop>();
        var current=(lat:AggsbachMarktLat,lon:AggsbachMarktLon);
        var km=0.0;
        var seq=1;

        while(done.Count<transfers.Count)
        {
            var options=new List<ActionPoint>();
            foreach(var transfer in transfers)
            {
                if(done.Contains(transfer.Id))continue;
                if(pendingPickups.Contains(transfer.Id))
                {
                    var c=Resolve(transfer.PickupLocation);
                    if(c.ok)options.Add(new ActionPoint(transfer,true,c.lat,c.lon));
                }
                else if(picked.Contains(transfer.Id))
                {
                    var c=Resolve(transfer.DropLocation);
                    if(c.ok)options.Add(new ActionPoint(transfer,false,c.lat,c.lon));
                }
            }
            if(options.Count==0)break;
            var next=options.OrderBy(x=>Haversine(current.lat,current.lon,x.Lat,x.Lon)).First();
            var leg=Haversine(current.lat,current.lon,next.Lat,next.Lon);km+=leg;current=(next.Lat,next.Lon);
            var currentTransfer=next.Transfer;
            if(next.IsPickup){pendingPickups.Remove(currentTransfer.Id);picked.Add(currentTransfer.Id);}else{picked.Remove(currentTransfer.Id);done.Add(currentTransfer.Id);}
            result.Add(new LuggageRouteStop(seq++,next.IsPickup?"ABHOLEN":"ZUSTELLEN",currentTransfer.Id,currentTransfer.Reference,currentTransfer.Guest,
                next.IsPickup?currentTransfer.PickupLocation:currentTransfer.DropLocation,next.IsPickup?currentTransfer.PickupName:currentTransfer.DropName,next.IsPickup?currentTransfer.PickupPhone:currentTransfer.DropPhone,
                currentTransfer.PickupName,currentTransfer.DropName,Math.Round(leg,1),currentTransfer.Status));
        }
        var home=Haversine(current.lat,current.lon,AggsbachMarktLat,AggsbachMarktLon);if(result.Count>0)km+=home;
        return new LuggageRoutePlan(result,Math.Round(km,1),"Aggsbach Markt → Tour → Aggsbach Markt");
    }

    private static string S(Dictionary<string,object?> row,string key)=>Convert.ToString(row.GetValueOrDefault(key),CultureInfo.InvariantCulture)??"";
    private sealed record Transfer(long Id,string Reference,string Guest,string PickupHostId,string DropoffHostId,string PickupName,string PickupLocation,string PickupPhone,string DropName,string DropLocation,string DropPhone,string Status);
    private sealed record ActionPoint(Transfer Transfer,bool IsPickup,double Lat,double Lon);

    private static (double lat,double lon,bool ok) Resolve(string location)
    {
        var x=(location??"").ToLowerInvariant();
        if(x.Contains("aggsbach markt"))return (48.2947,15.4046,true);
        if(x.Contains("aggsbach dorf"))return (48.2956,15.4879,true);
        if(x.Contains("krems"))return (48.4108,15.6021,true);
        if(x.Contains("dürnstein")||x.Contains("duernstein")||x.Contains("unterloiben"))return (48.3951,15.5195,true);
        if(x.Contains("weißenkirchen")||x.Contains("weissenkirchen"))return (48.3975,15.4695,true);
        if(x.Contains("wösendorf")||x.Contains("woesendorf"))return (48.3839,15.4509,true);
        if(x.Contains("st. michael")||x.Contains("sankt michael"))return (48.3800,15.4381,true);
        if(x.Contains("spitz"))return (48.3657,15.4145,true);
        if(x.Contains("mühldorf")||x.Contains("muehldorf"))return (48.3745,15.3479,true);
        if(x.Contains("maria laach"))return (48.3049,15.3474,true);
        if(x.Contains("maria langegg"))return (48.3152,15.5439,true);
        if(x.Contains("emmersdorf"))return (48.2417,15.3376,true);
        if(x.Contains("melk"))return (48.2274,15.3319,true);
        if(x.Contains("hofarnsdorf"))return (48.3605,15.4324,true);
        if(x.Contains("oberarnsdorf"))return (48.3561,15.4214,true);
        if(x.Contains("bacharnsdorf"))return (48.3537,15.4078,true);
        if(x.Contains("rossatz"))return (48.3965,15.5083,true);
        if(x.Contains("unterbergern"))return (48.3654,15.5837,true);
        if(x.Contains("mautern"))return (48.3939,15.5782,true);
        return (0,0,false);
    }

    private static double Haversine(double lat1,double lon1,double lat2,double lon2)
    {
        const double r=6371.0;var dLat=(lat2-lat1)*Math.PI/180.0;var dLon=(lon2-lon1)*Math.PI/180.0;
        var a=Math.Sin(dLat/2)*Math.Sin(dLat/2)+Math.Cos(lat1*Math.PI/180.0)*Math.Cos(lat2*Math.PI/180.0)*Math.Sin(dLon/2)*Math.Sin(dLon/2);
        return 2*r*Math.Atan2(Math.Sqrt(a),Math.Sqrt(1-a));
    }
}
