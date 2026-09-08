using System.Text;

namespace WachauEtappe.Zentrale.Data;

public sealed partial class DatabaseService
{
    public void BackupTo(string targetPath)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(targetPath)??Environment.CurrentDirectory);
        File.Copy(DatabasePath,targetPath,true);
        Audit("database_backup","System",null,targetPath);
    }

    public string AutoBackup(int retentionDays=30)
    {
        var folder=Path.Combine(Path.GetDirectoryName(DatabasePath)??Environment.CurrentDirectory,"Backups");
        Directory.CreateDirectory(folder);
        var target=Path.Combine(folder,$"wachauetappe-{DateTime.Today:yyyyMMdd}.db");
        if(!File.Exists(target)) File.Copy(DatabasePath,target,true);
        foreach(var file in Directory.EnumerateFiles(folder,"wachauetappe-*.db"))
        {
            try{if(File.GetLastWriteTimeUtc(file)<DateTime.UtcNow.AddDays(-Math.Max(7,retentionDays)))File.Delete(file);}catch{}
        }
        return target;
    }

    public void RestoreFrom(string sourcePath)
    {
        if(!File.Exists(sourcePath)) throw new FileNotFoundException("Backup-Datei nicht gefunden.",sourcePath);
        var safety=DatabasePath+".before-restore-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+".bak";
        File.Copy(DatabasePath,safety,true);
        File.Copy(sourcePath,DatabasePath,true);
    }

    public void ExportCsv(string sql,string targetPath)
    {
        var rows=QueryRows(sql);
        var sb=new StringBuilder();
        var headers=rows.Count>0?rows[0].Keys.ToList():new List<string>();
        if(headers.Count>0) sb.AppendLine(string.Join(';',headers.Select(EscapeCsv)));
        foreach(var row in rows) sb.AppendLine(string.Join(';',headers.Select(h=>EscapeCsv(Convert.ToString(row[h])??""))));
        File.WriteAllText(targetPath,sb.ToString(),new UTF8Encoding(true));
        Audit("csv_export","System",null,targetPath);
    }

    private static string EscapeCsv(string value)
    {
        if(value.Contains(';')||value.Contains('"')||value.Contains('\n')||value.Contains('\r')) return '"'+value.Replace("\"","\"\"")+'"';
        return value;
    }
}
