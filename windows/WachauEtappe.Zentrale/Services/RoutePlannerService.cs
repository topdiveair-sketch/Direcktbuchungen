using System.Text.Json;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale.Services;

public sealed class RoutePlannerService
{
    private sealed record Segment(int Stage,string From,string To,double Km,string? FromBank,string? ToBank);

    public List<PlannedStage> Plan(TripRecord trip)
    {
        var segments=LoadSegments(trip.RouteId);
        if(segments.Count==0) throw new InvalidOperationException("Keine Routendaten gefunden.");

        var startIndex=segments.FindIndex(s=>Eq(s.From,trip.StartPlace));
        if(startIndex<0) throw new InvalidOperationException("Startort ist in der Route nicht eindeutig gefunden.");

        List<Segment> selected;
        if(Eq(trip.StartPlace,trip.EndPlace))
        {
            selected=segments.Skip(startIndex).Concat(segments.Take(startIndex)).ToList();
        }
        else
        {
            var matches=Enumerable.Range(0,segments.Count)
                .Select(offset=>(Index:(startIndex+offset)%segments.Count,Offset:offset))
                .Where(x=>Eq(segments[x.Index].To,trip.EndPlace))
                .ToList();
            if(matches.Count==0) throw new InvalidOperationException("Zielort ist in der Route nicht eindeutig gefunden.");
            var relativeEnd=matches[0];
            selected=Enumerable.Range(0,relativeEnd.Offset+1)
                .Select(offset=>segments[(startIndex+offset)%segments.Count])
                .ToList();
        }

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
            var travelDate=date.AddDays(day-1).ToString("yyyy-MM-dd");
            var requiredBank=selected[best].ToBank ?? BankForPlace(to);
            var candidates=App.Database.SearchBookableHosts(to,travelDate,trip.LuggageTransfer);
            var host=candidates.FirstOrDefault(h=>HostMatchesPlaceAndBank(h.Location,to,requiredBank));
            stages.Add(new PlannedStage{DayNumber=day,TravelDate=travelDate,FromPlace=from,ToPlace=to,DistanceKm=Math.Round(km,2),HostId=host?.HostId,HostName=host?.Name??"⚠ Kein verfügbarer freigegebener Gastgeber",CoverageGap=host is null});
            i=best+1;day++;
        }
        return stages;
    }

    private static bool HostMatchesPlaceAndBank(string hostLocation,string routePlace,string? requiredBank)
    {
        var placeMatch=Eq(hostLocation,routePlace)||hostLocation.Contains(routePlace,StringComparison.OrdinalIgnoreCase)||routePlace.Contains(hostLocation,StringComparison.OrdinalIgnoreCase);
        if(!placeMatch) return false;
        var hostBank=BankForPlace(hostLocation);
        return requiredBank is null || hostBank is null || string.Equals(hostBank,requiredBank,StringComparison.OrdinalIgnoreCase);
    }

    private static string? BankForPlace(string place)
    {
        if(place.Contains("Aggsbach Markt",StringComparison.OrdinalIgnoreCase)) return "north";
        if(place.Contains("Aggsbach Dorf",StringComparison.OrdinalIgnoreCase)) return "south";
        return null;
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
            string? GetOptional(params string[] names){foreach(var n in names)if(s.TryGetProperty(n,out var v)&&v.ValueKind==JsonValueKind.String)return v.GetString();return null;}
            double GetKm(){foreach(var n in new[]{"km","distance_km","distance"})if(s.TryGetProperty(n,out var v)&&v.TryGetDouble(out var d))return d;return 0;}
            var stage=s.TryGetProperty("stage",out var stageEl)&&stageEl.TryGetInt32(out var stageNo)?stageNo:list.Count+1;
            var from=Get("from","start","from_place");var to=Get("to","end","to_place");var km=GetKm();
            if(from!=""&&to!=""&&km>0)list.Add(new Segment(stage,from,to,km,GetOptional("from_bank"),GetOptional("to_bank")));
        }
        return list;
    }
}
