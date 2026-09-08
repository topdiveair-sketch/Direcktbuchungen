namespace WachauEtappe.Zentrale.Models;

public sealed class CandidateRecord
{
    public long Id { get; set; }
    public string Name { get; set; } = "";
    public string Location { get; set; } = "";
    public string Priority { get; set; } = "normal";
    public string Status { get; set; } = "research";
    public int FitScore { get; set; }
    public string Email { get; set; } = "";
    public string Phone { get; set; } = "";
    public string Url { get; set; } = "";
    public string Notes { get; set; } = "";
    public string LastContactUtc { get; set; } = "";
}
