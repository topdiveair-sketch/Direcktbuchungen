namespace WachauEtappe.Zentrale.Models;

public sealed class HostRecord
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Location { get; set; } = "";
    public string Address { get; set; } = "";
    public double? Latitude { get; set; }
    public double? Longitude { get; set; }
    public string Status { get; set; } = "research";
    public bool Published { get; set; }
    public bool AcceptingBookings { get; set; }
    public string DirectUrl { get; set; } = "";
    public string Email { get; set; } = "";
    public string Phone { get; set; } = "";
    public bool OneNightVerified { get; set; }
    public bool CashAtHostVerified { get; set; }
    public bool LuggageVerified { get; set; }
}
