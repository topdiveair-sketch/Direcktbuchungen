using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using WachauEtappe.Zentrale.Data;

namespace WachauEtappe.Zentrale.Services;

public static class PartnerAvailabilitySyncService
{
    private const string DefaultApiBase="https://web-production-907d68.up.railway.app";
    private static readonly HttpClient Http=new(){Timeout=TimeSpan.FromSeconds(30)};
    private static readonly byte[] CredentialEntropy=Encoding.UTF8.GetBytes("WachauEtappe.Zentrale.AdminCredential.v1");
    private static readonly string CredentialFile=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"WachauEtappe","railway-admin.cred");

    public static bool HasStoredPassword => !string.IsNullOrWhiteSpace(LoadPassword());

    public static async Task<SyncResult> SyncAsync(DatabaseService db,DateTime from,DateTime to)
    {
        var password=LoadPassword();
        if(string.IsNullOrWhiteSpace(password)) return new SyncResult(false,0,"Online-Synchronisierung nicht eingerichtet. Unter Gastgeber > Online-Verwaltung zuerst Railway-ADMIN_PASSWORD speichern und testen.",true);
        if(to.Date<from.Date)(from,to)=(to,from);

        var api=(Environment.GetEnvironmentVariable("WACHAUETAPPE_API_BASE")??DefaultApiBase).TrimEnd('/');
        var url=$"{api}/api/central/partner-availability?from={from:yyyy-MM-dd}&to={to:yyyy-MM-dd}";
        using var req=new HttpRequestMessage(HttpMethod.Get,url);
        req.Headers.TryAddWithoutValidation("X-Admin-Password",password);
        try
        {
            using var resp=await Http.SendAsync(req);
            if(resp.StatusCode==System.Net.HttpStatusCode.Unauthorized)
                return new SyncResult(false,0,"Gespeicherter Admin-Zugang ist ungültig. Unter Gastgeber > Online-Verwaltung neu speichern und testen.",true);
            var json=await resp.Content.ReadAsStringAsync();
            if(!resp.IsSuccessStatusCode)
                return new SyncResult(false,0,$"Online-Synchronisierung fehlgeschlagen (HTTP {(int)resp.StatusCode}).",false);

            using var doc=JsonDocument.Parse(json);
            if(!doc.RootElement.TryGetProperty("rows",out var rows) || rows.ValueKind!=JsonValueKind.Array)
                return new SyncResult(false,0,"Online-Antwort enthält keine Verfügbarkeiten.",false);

            var totals=new Dictionary<string,int>(StringComparer.OrdinalIgnoreCase);
            var rowList=rows.EnumerateArray().Select(x=>x.Clone()).ToList();
            foreach(var hostId in rowList.Select(x=>GetString(x,"host_id")).Where(x=>!string.IsNullOrWhiteSpace(x)).Distinct(StringComparer.OrdinalIgnoreCase))
                totals[hostId]=await GetRoomsTotalAsync(api,password,hostId);

            var count=0;
            foreach(var r in rowList)
            {
                var hostId=GetString(r,"host_id");
                var stayDate=GetString(r,"stay_date");
                if(string.IsNullOrWhiteSpace(hostId)||string.IsNullOrWhiteSpace(stayDate)) continue;
                var name=GetString(r,"name");
                var location=GetString(r,"location");
                var status=GetString(r,"status");
                var roomsFree=GetInt(r,"rooms_free");
                var roomsTotal=totals.TryGetValue(hostId,out var total)&&total>0?total:Math.Max(1,roomsFree);
                var bookingBlocked=GetBool(r,"booking_blocked");
                var price=GetNullableDouble(r,"price");
                var updatedAt=GetString(r,"updated_at");
                db.UpsertOnlinePartnerAvailability(hostId,name,location,roomsTotal,stayDate,status,roomsFree,price,bookingBlocked,updatedAt);
                count++;
            }
            return new SyncResult(true,count,$"{count} Online-Verfügbarkeit(en) übernommen.",false);
        }
        catch(Exception ex)
        {
            return new SyncResult(false,0,$"Online-Synchronisierung nicht erreichbar: {ex.Message}",false);
        }
    }

    private static async Task<int> GetRoomsTotalAsync(string api,string password,string hostId)
    {
        try
        {
            using var req=new HttpRequestMessage(HttpMethod.Get,$"{api}/api/partner/admin-status?hostId={Uri.EscapeDataString(hostId)}");
            req.Headers.TryAddWithoutValidation("X-Admin-Password",password);
            using var resp=await Http.SendAsync(req);
            if(!resp.IsSuccessStatusCode) return 0;
            using var doc=JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
            var root=doc.RootElement;
            return root.TryGetProperty("roomsTotal",out var v)&&v.TryGetInt32(out var n)?Math.Max(1,n):0;
        }
        catch{return 0;}
    }

    private static string LoadPassword()
    {
        var env=Environment.GetEnvironmentVariable("WACHAUETAPPE_ADMIN_PASSWORD");
        if(!string.IsNullOrWhiteSpace(env)) return env;
        try
        {
            if(!File.Exists(CredentialFile)) return "";
            var raw=ProtectedData.Unprotect(File.ReadAllBytes(CredentialFile),CredentialEntropy,DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(raw);
        }
        catch{return "";}
    }

    private static string GetString(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.ValueKind!=JsonValueKind.Null?v.ToString():"";
    private static int GetInt(JsonElement e,string n,int fallback=0)=>e.TryGetProperty(n,out var v)&&v.TryGetInt32(out var x)?x:fallback;
    private static bool GetBool(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&(v.ValueKind==JsonValueKind.True||(v.TryGetInt32(out var x)&&x!=0));
    private static double? GetNullableDouble(JsonElement e,string n)=>e.TryGetProperty(n,out var v)&&v.ValueKind!=JsonValueKind.Null&&v.TryGetDouble(out var x)?x:null;
}

public sealed record SyncResult(bool Success,int Count,string Message,bool CredentialRequired);
