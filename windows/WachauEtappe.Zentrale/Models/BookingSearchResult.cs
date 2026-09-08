namespace WachauEtappe.Zentrale.Models;

public sealed class BookingSearchResult
{
    public string HostId { get; set; } = "";
    public string Name { get; set; } = "";
    public string Location { get; set; } = "";
    public string Availability { get; set; } = "unknown";
    public double? Price { get; set; }
    public bool OneNight { get; set; }
    public bool CashAtHost { get; set; }
    public bool Luggage { get; set; }
    public string DirectUrl { get; set; } = "";
    public string Email { get; set; } = "";
    public string Phone { get; set; } = "";
}
