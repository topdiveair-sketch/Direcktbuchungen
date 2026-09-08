using System.Text.Json;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale.Services;

public sealed class RoutePlannerService
{
    private sealed record Segment(string From,string To,double Km);

    public List<PlannedStage> Plan(TripRecord trip)
    {
        var segments=LoadSegments(trip.RouteId);
        if(segments.Count==0) throw new InvalidOperationException("Keine Routendaten gefunden.");
        var startIndex=segments.FindIndex(s=>Eq(s.From,trip.StartPlace));
        var endIndex=segments.FindLastIndex(s=>Eq(s.To,trip.EndPlace));
        if(startIndex<0 || endIndex<startIndex) throw new InvalidOperationException("Start oder Ziel ist in der Route nicht eindeutig gefunden.");
        var selected=segments.Skip(startIndex).Take(endIndex-startIndex+1).ToList();
        var hosts=App.Database.GetHosts().Where(h=>h.Published&&h.Status=="verified"&&h.AcceptingBookings&&h.OneNightVerified&&h.CashAtHostVerified&&h.LuggageVerified).ToList();
        var stages=new List<PlannedStage>();
        var i=0; var day=1; var date=DateTime.TryParse(trip.StartDate,out var parsed)?parsed:DateTime.Today;
        while(i<selected.Count)
        {
            var from=selected[i].From; double sum=0; var best=i; var bestDiff=double.MaxValue;
            for(var j=i;j<selected.Count;j++)
            {
                sum+=selected[j].Km; var diff=Math.Abs(sum-trip.DailyTargetKm);
                if(diff<bestDiff || diff<=trip.DailyToleranceKm){best=j;bestDiff=diff;}
                if(sum>trip.DailyTargetKm+trip.DailyToleranceKm && j>i) break;
            }
            var km=selected.Skip(i).Take(best-i+1).Sum(s=>s.Km); var to=selected[best].To;
            var host=hosts.FirstOrDefault(h=>Eq(h.Location,to)||h.Location.Contains(to,StringComparison.OrdinalIgnoreCase)||to.Contains(h.Location,StringComparison.OrdinalIgnoreCase));
            stages.Add(new PlannedStage{DayNumber=day,TravelDate=date.AddDays(day-1).ToString("yyyy-MM-dd"),FromPlace=from,ToPlace=to,DistanceKm=Math.Round(km,2),HostId=host?.Id,HostName=host?.Name??"⚠ Kein freigegebener Gastgeber",CoverageGap=host is null});
            i=best+1;day++;
        }
        return stages;
    }

    private static bool Eq(string a,string b)=>string.Equals(a.Trim(),b.Trim(),StringComparison.OrdinalIgnoreCase);

    private static List<Segment> LoadSegments(string routeId)
    {
        var path=Path.Combine(AppContext.BaseDirectory,"Seed","routes.json");
        if(!File.Exists(path)) return [];
        using var doc=JsonDocument.Parse(File.ReadAllText(path));
        var root=doc.RootElement;
        JsonElement route=root;
        if(root.ValueKind==JsonValueKind.Object && root.TryGetProperty("routes",out var routes) && routes.ValueKind==JsonValueKind.Array)
            route=routes.EnumerateArray().FirstOrDefault(r=>r.TryGetProperty("id",out var id)&&id.GetString()==routeId);
        if(route.ValueKind!=JsonValueKind.Object || !route.TryGetProperty("segments",out var segs)) return [];
        var list=new List<Segment>();
        foreach(var s in segs.EnumerateArray())
        {
            string Get(params string[] names){foreach(var n in names)if(s.TryGetProperty(n,out var v))return v.GetString()??"";return "";}
            double GetKm(){foreach(var n in new[]{"km","distance_km","distance"})if(s.TryGetProperty(n,out var v)&&v.TryGetDouble(out var d))return d;return 0;}
            var from=Get("from","start","from_place");var to=Get("to","end","to_place");var km=GetKm();if(from!=""&&to!=""&&km>0)list.Add(new Segment(from,to,km));
        }
        return list;
    }
}
