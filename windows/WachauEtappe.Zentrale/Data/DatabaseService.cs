using Microsoft.Data.Sqlite;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale.Data;

public sealed partial class DatabaseService
{
    public List<Dictionary<string,object?>> QueryRows(string sql,params (string Name,object? Value)[] parameters)
    {
        var rows=new List<Dictionary<string,object?>>();
        using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();q.CommandText=sql;
        foreach(var p in parameters)q.Parameters.AddWithValue(p.Name,p.Value??DBNull.Value);
        using var r=q.ExecuteReader();
        while(r.Read()){var row=new Dictionary<string,object?>();for(int i=0;i<r.FieldCount;i++)row[r.GetName(i)]=r.IsDBNull(i)?null:r.GetValue(i);rows.Add(row);}return rows;
    }
}
