using Microsoft.Data.Sqlite;

namespace WachauEtappe.Zentrale.Data;

public sealed partial class DatabaseService
{
    public void EnsureBillingTables()
    {
        Execute("CREATE TABLE IF NOT EXISTS BillingSettings(Key TEXT PRIMARY KEY,Value TEXT NOT NULL)");
        Execute("CREATE TABLE IF NOT EXISTS PartnerInvoices(Id TEXT PRIMARY KEY,InvoiceNo TEXT NOT NULL UNIQUE,HostId TEXT NOT NULL,PeriodFrom TEXT NOT NULL,PeriodTo TEXT NOT NULL,NetAmount REAL NOT NULL,VatRate REAL NOT NULL,VatAmount REAL NOT NULL,GrossAmount REAL NOT NULL,Status TEXT NOT NULL DEFAULT 'open',CreatedUtc TEXT NOT NULL,DueDate TEXT NOT NULL,PaidUtc TEXT)");
        Execute("CREATE TABLE IF NOT EXISTS PartnerInvoiceItems(Id INTEGER PRIMARY KEY AUTOINCREMENT,InvoiceId TEXT NOT NULL,BookingId TEXT NOT NULL UNIQUE,Reference TEXT NOT NULL,StayDate TEXT NOT NULL,AmountNet REAL NOT NULL,FOREIGN KEY(InvoiceId) REFERENCES PartnerInvoices(Id) ON DELETE CASCADE)");
        Execute("INSERT OR IGNORE INTO BillingSettings(Key,Value) VALUES('booking_fee_net','9.00')");
        Execute("INSERT OR IGNORE INTO BillingSettings(Key,Value) VALUES('vat_rate','20.00')");
        Execute("INSERT OR IGNORE INTO BillingSettings(Key,Value) VALUES('payment_days','14')");
        Execute("INSERT OR IGNORE INTO BillingSettings(Key,Value) VALUES('invoice_prefix','WE-R')");
        Execute("INSERT OR IGNORE INTO BillingSettings(Key,Value) VALUES('seller_name','WachauEtappe')");
        Execute("INSERT OR IGNORE INTO BillingSettings(Key,Value) VALUES('seller_address','')");
        Execute("INSERT OR IGNORE INTO BillingSettings(Key,Value) VALUES('seller_vat_id','')");
        Execute("INSERT OR IGNORE INTO BillingSettings(Key,Value) VALUES('seller_iban','')");
    }

    public Dictionary<string,string> GetBillingSettings()
    {
        EnsureBillingTables();
        var x=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
        using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();q.CommandText="SELECT Key,Value FROM BillingSettings";using var r=q.ExecuteReader();while(r.Read())x[r.GetString(0)]=r.GetString(1);return x;
    }

    public void SaveBillingSettings(double bookingFeeNet,double vatRate,int paymentDays,string sellerName,string sellerAddress,string sellerVatId,string sellerIban)
    {
        EnsureBillingTables();
        var values=new Dictionary<string,string>{{"booking_fee_net",bookingFeeNet.ToString("0.00",System.Globalization.CultureInfo.InvariantCulture)},{"vat_rate",vatRate.ToString("0.00",System.Globalization.CultureInfo.InvariantCulture)},{"payment_days",Math.Max(1,paymentDays).ToString()},{"seller_name",sellerName.Trim()},{"seller_address",sellerAddress.Trim()},{"seller_vat_id",sellerVatId.Trim()},{"seller_iban",sellerIban.Trim()}};
        foreach(var p in values)Execute("INSERT INTO BillingSettings(Key,Value) VALUES(@k,@v) ON CONFLICT(Key) DO UPDATE SET Value=@v",("@k",p.Key),("@v",p.Value));
        Audit("billing_settings","System","billing",$"fee={bookingFeeNet:0.00}; vat={vatRate:0.##}");
    }

    public (int invoices,int bookings,double gross) GeneratePartnerInvoices(string periodFrom,string periodTo)
    {
        EnsureBillingTables();
        var settings=GetBillingSettings();
        var fee=double.Parse(settings["booking_fee_net"],System.Globalization.CultureInfo.InvariantCulture);
        var vat=double.Parse(settings["vat_rate"],System.Globalization.CultureInfo.InvariantCulture);
        var days=int.Parse(settings["payment_days"]);
        var prefix=settings["invoice_prefix"];
        var candidates=new List<(string BookingId,string Reference,string HostId,string StayDate)>();
        using(var c=new SqliteConnection(ConnectionString))
        {
            c.Open();using var q=c.CreateCommand();
            q.CommandText="SELECT b.Id,b.Reference,b.HostId,b.StayDate FROM Bookings b WHERE b.Status='confirmed' AND b.StayDate BETWEEN @f AND @t AND NOT EXISTS(SELECT 1 FROM PartnerInvoiceItems i WHERE i.BookingId=b.Id) ORDER BY b.HostId,b.StayDate,b.Reference";
            q.Parameters.AddWithValue("@f",periodFrom);q.Parameters.AddWithValue("@t",periodTo);using var r=q.ExecuteReader();while(r.Read())candidates.Add((r.GetString(0),r.GetString(1),r.GetString(2),r.GetString(3)));
        }
        var invoiceCount=0;var bookingCount=0;double grossTotal=0;
        foreach(var group in candidates.GroupBy(x=>x.HostId))
        {
            var invoiceId=Guid.NewGuid().ToString("N");
            var invoiceNo=$"{prefix}-{DateTime.Now:yyyyMMdd}-{Guid.NewGuid().ToString("N")[..4].ToUpperInvariant()}";
            var net=Math.Round(group.Count()*fee,2,MidpointRounding.AwayFromZero);
            var vatAmount=Math.Round(net*vat/100d,2,MidpointRounding.AwayFromZero);
            var gross=Math.Round(net+vatAmount,2,MidpointRounding.AwayFromZero);
            var due=DateTime.Today.AddDays(days).ToString("yyyy-MM-dd");
            Execute("INSERT INTO PartnerInvoices(Id,InvoiceNo,HostId,PeriodFrom,PeriodTo,NetAmount,VatRate,VatAmount,GrossAmount,Status,CreatedUtc,DueDate) VALUES(@id,@n,@h,@f,@t,@net,@vr,@va,@g,'open',@u,@d)",("@id",invoiceId),("@n",invoiceNo),("@h",group.Key),("@f",periodFrom),("@t",periodTo),("@net",net),("@vr",vat),("@va",vatAmount),("@g",gross),("@u",DateTime.UtcNow.ToString("O")),("@d",due));
            foreach(var b in group){Execute("INSERT INTO PartnerInvoiceItems(InvoiceId,BookingId,Reference,StayDate,AmountNet) VALUES(@i,@b,@r,@d,@a)",("@i",invoiceId),("@b",b.BookingId),("@r",b.Reference),("@d",b.StayDate),("@a",fee));bookingCount++;}
            invoiceCount++;grossTotal+=gross;Audit("partner_invoice_created","Host",group.Key,$"{invoiceNo}; bookings={group.Count()}; gross={gross:0.00}");
        }
        return(invoiceCount,bookingCount,grossTotal);
    }

    public List<Dictionary<string,object?>> GetPartnerInvoices()
    {
        EnsureBillingTables();var rows=new List<Dictionary<string,object?>>();using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();q.CommandText="SELECT i.Id,i.InvoiceNo,h.Name AS Host,COALESCE(h.Email,''),i.PeriodFrom,i.PeriodTo,i.NetAmount,i.VatRate,i.VatAmount,i.GrossAmount,i.Status,i.DueDate,COUNT(x.Id) AS Bookings FROM PartnerInvoices i JOIN Hosts h ON h.Id=i.HostId LEFT JOIN PartnerInvoiceItems x ON x.InvoiceId=i.Id GROUP BY i.Id ORDER BY i.CreatedUtc DESC";using var r=q.ExecuteReader();while(r.Read())rows.Add(new Dictionary<string,object?>{{"Id",r.GetString(0)},{"Rechnung",r.GetString(1)},{"Gastgeber",r.GetString(2)},{"E-Mail",r.GetString(3)},{"Zeitraum",$"{r.GetString(4)} – {r.GetString(5)}"},{"Buchungen",r.GetInt32(12)},{"Netto",r.GetDouble(6)},{"USt %",r.GetDouble(7)},{"USt",r.GetDouble(8)},{"Brutto",r.GetDouble(9)},{"Status",r.GetString(10)},{"Fällig",r.GetString(11)}});return rows;
    }

    public Dictionary<string,object?>? GetPartnerInvoice(string invoiceId)
    {
        EnsureBillingTables();using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();q.CommandText="SELECT i.Id,i.InvoiceNo,i.HostId,h.Name,COALESCE(h.Email,''),COALESCE(h.Location,''),i.PeriodFrom,i.PeriodTo,i.NetAmount,i.VatRate,i.VatAmount,i.GrossAmount,i.Status,i.DueDate FROM PartnerInvoices i JOIN Hosts h ON h.Id=i.HostId WHERE i.Id=@id";q.Parameters.AddWithValue("@id",invoiceId);using var r=q.ExecuteReader();if(!r.Read())return null;return new Dictionary<string,object?>{{"Id",r.GetString(0)},{"InvoiceNo",r.GetString(1)},{"HostId",r.GetString(2)},{"HostName",r.GetString(3)},{"HostEmail",r.GetString(4)},{"HostLocation",r.GetString(5)},{"PeriodFrom",r.GetString(6)},{"PeriodTo",r.GetString(7)},{"Net",r.GetDouble(8)},{"VatRate",r.GetDouble(9)},{"Vat",r.GetDouble(10)},{"Gross",r.GetDouble(11)},{"Status",r.GetString(12)},{"DueDate",r.GetString(13)}};
    }

    public List<Dictionary<string,object?>> GetPartnerInvoiceItems(string invoiceId)
    {
        EnsureBillingTables();var rows=new List<Dictionary<string,object?>>();using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();q.CommandText="SELECT Reference,StayDate,AmountNet FROM PartnerInvoiceItems WHERE InvoiceId=@id ORDER BY StayDate,Reference";q.Parameters.AddWithValue("@id",invoiceId);using var r=q.ExecuteReader();while(r.Read())rows.Add(new Dictionary<string,object?>{{"Reference",r.GetString(0)},{"StayDate",r.GetString(1)},{"AmountNet",r.GetDouble(2)}});return rows;
    }

    public void MarkPartnerInvoicePaid(string invoiceId,bool paid)
    {
        EnsureBillingTables();Execute("UPDATE PartnerInvoices SET Status=@s,PaidUtc=@p WHERE Id=@id",("@s",paid?"paid":"open"),("@p",paid?DateTime.UtcNow.ToString("O"):null),("@id",invoiceId));Audit("partner_invoice_status","PartnerInvoice",invoiceId,paid?"paid":"open");
    }
}
