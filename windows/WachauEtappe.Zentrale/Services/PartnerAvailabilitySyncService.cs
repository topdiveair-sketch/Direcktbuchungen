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

    public static bool HasStoredPassword => !string.IsNullOrWhiteSpace(LoadPassword());

    public static async Task<SyncResult> SyncAsync(DatabaseService db,DateTime from,DateTime to,string? password=null)
    {
        password=string.IsNullOrWhiteSpace(password)?LoadPassword():password;
        if(string.IsNullOrWhiteSpace(password)) return new SyncResult(false,0,"Zentrale-Online-Passwort fehlt.",true);
        if(to.Date<from.Date)(from,to)=(to,from);

        var api=(Environment.GetEnvironmentVariable("WACHAUETAPPE_API_BASE")??DefaultApiBase).TrimEnd('/');
        var url=$"{api}/api/central/partner-availability?from={from:yyyy-MM-dd}&to={to:yyyy-MM-dd}";
        using var req=new HttpRequestMessage(HttpMethod.Get,url);
        req.Headers.TryAddWithoutValidation("X-Admin-Password",password);
        try
        {
            using var resp=await Http.SendAsync(req);
            if(resp.StatusCode==System.Net.HttpStatusCode.Unauthorized)
                return new SyncResult(false,0,"Zentrale-Online-Passwort ist nicht korrekt.",true);
            var json=await resp.Content.ReadAsStringAsync();
            if(!resp.IsSuccessStatusCode)
                return new SyncResult(false,0,$"Online-Synchronisierung fehlgeschlagen (HTTP {(int)resp.StatusCode}).",false);

            using var doc=JsonDocument.Parse(json);
            if(!doc.RootElement.TryGetProperty("rows",out var rows) || rows.ValueKind!=JsonValueKind.Array)
                return new SyncResult(false,0,"Online-Antwort enthält keine Verfügbarkeiten.",false);

            var count=0;
            foreach(var r in rows.EnumerateArray())
            {
                var hostId=GetString(r,"host_id");
                var stayDate=GetString(r,"stay_date");
                if(string.IsNullOrWhiteSpace(hostId)||string.IsNullOrWhiteSpace(stayDate)) continue;
                var name=GetString(r,"name");
                var location=GetString(r,"location");
                var status=GetString(r,"status");
                var roomsFree=GetInt(r,"rooms_free");
                var roomsTotal=Math.Max(1,GetInt(r,"rooms_total",roomsFree>0?roomsFree:1));
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

    public static void SavePassword(string password)
    {
        var folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"WachauEtappe","Zentrale");
        Directory.CreateDirectory(folder);
        var path=Path.Combine(folder,"central-online.cred");
        if(string.IsNullOrWhiteSpace(password)){if(File.Exists(path))File.Delete(path);return;}
        var raw=Encoding.UTF8.GetBytes(password);
        var enc=ProtectedData.Protect(raw,null,DataProtectionScope.CurrentUser);
        File.WriteAllBytes(path,enc);
    }

    public static string LoadPassword()
    {
        var env=Environment.GetEnvironmentVariable("WACHAUETAPPE_ADMIN_PASSWORD");
        if(!string.IsNullOrWhiteSpace(env)) return env;
        try
        {
            var path=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"WachauEtappe","Zentrale","central-online.cred");
            if(!File.Exists(path)) return "";
            var raw=ProtectedData.Unprotect(File.ReadAllBytes(path),null,DataProtectionScope.CurrentUser);
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
