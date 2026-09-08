namespace WachauEtappe.Zentrale.Data;

public sealed partial class DatabaseService
{
    public void UpdateLuggageTransfer(long id,string provider,string status,string note)
    {
        Execute("UPDATE LuggageTransfers SET Provider=@p,Status=@s,Note=@n WHERE Id=@id",("@p",provider),("@s",status),("@n",note),("@id",id));
        Audit("luggage_transfer_updated","LuggageTransfer",id.ToString(),$"{provider}; {status}");
    }
}
