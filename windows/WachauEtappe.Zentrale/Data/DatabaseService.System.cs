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
