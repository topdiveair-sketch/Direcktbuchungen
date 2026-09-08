using Microsoft.Data.Sqlite;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale.Data;

public sealed partial class DatabaseService
{
    public void EnsureCandidateColumns()
    {
        using var c=new SqliteConnection(ConnectionString);c.Open();
        EnsureColumn(c,"Candidates","Email","TEXT");
        EnsureColumn(c,"Candidates","Phone","TEXT");
        EnsureColumn(c,"Candidates","Url","TEXT");
        EnsureColumn(c,"Candidates","Notes","TEXT");
        EnsureColumn(c,"Candidates","LastContactUtc","TEXT");
    }

    public List<CandidateRecord> GetCandidates(string? search=null)
    {
        EnsureCandidateColumns();
        var list=new List<CandidateRecord>();using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();
        q.CommandText="SELECT Id,Name,COALESCE(Location,''),COALESCE(Priority,'normal'),COALESCE(Status,'research'),COALESCE(FitScore,0),COALESCE(Email,''),COALESCE(Phone,''),COALESCE(Url,''),COALESCE(Notes,''),COALESCE(LastContactUtc,'') FROM Candidates WHERE @q='' OR Name LIKE '%'||@q||'%' OR Location LIKE '%'||@q||'%' ORDER BY CASE lower(COALESCE(Priority,'')) WHEN 'hoch' THEN 0 WHEN 'high' THEN 0 ELSE 1 END,FitScore DESC,Location,Name";
        q.Parameters.AddWithValue("@q",search?.Trim()??"");using var r=q.ExecuteReader();
        while(r.Read())list.Add(new CandidateRecord{Id=r.GetInt64(0),Name=r.GetString(1),Location=r.GetString(2),Priority=r.GetString(3),Status=r.GetString(4),FitScore=r.GetInt32(5),Email=r.GetString(6),Phone=r.GetString(7),Url=r.GetString(8),Notes=r.GetString(9),LastContactUtc=r.GetString(10)});
        return list;
    }

    public void SaveCandidate(CandidateRecord x)
    {
        EnsureCandidateColumns();
        Execute("UPDATE Candidates SET Name=@n,Location=@l,Priority=@p,Status=@s,FitScore=@f,Email=@e,Phone=@ph,Url=@u,Notes=@note,LastContactUtc=@lc WHERE Id=@id",("@n",x.Name),("@l",x.Location),("@p",x.Priority),("@s",x.Status),("@f",x.FitScore),("@e",x.Email),("@ph",x.Phone),("@u",x.Url),("@note",x.Notes),("@lc",x.LastContactUtc),("@id",x.Id));
        Audit("candidate_saved","Candidate",x.Id.ToString(),x.Name);
    }

    public void MarkCandidateContacted(long id)
    {
        EnsureCandidateColumns();
        Execute("UPDATE Candidates SET Status='contacted',LastContactUtc=@u WHERE Id=@id",("@u",DateTime.UtcNow.ToString("O")),("@id",id));
        Audit("candidate_contacted","Candidate",id.ToString(),null);
    }
}
