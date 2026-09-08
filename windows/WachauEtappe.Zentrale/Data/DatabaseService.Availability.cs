namespace WachauEtappe.Zentrale.Data;

public sealed partial class DatabaseService
{
    public int SetAvailabilityRange(string hostId,DateTime from,DateTime to,string status,double? price=null,string? note=null)
    {
        if(to.Date<from.Date)(from,to)=(to,from);
        var count=0;
        for(var d=from.Date;d<=to.Date;d=d.AddDays(1))
        {
            SetAvailability(hostId,d.ToString("yyyy-MM-dd"),status,price,note);
            count++;
        }
        Audit("availability_range","Host",hostId,$"{from:yyyy-MM-dd}..{to:yyyy-MM-dd}; {status}; days={count}");
        return count;
    }
}
