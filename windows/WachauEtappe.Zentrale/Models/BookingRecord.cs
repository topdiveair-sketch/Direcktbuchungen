namespace WachauEtappe.Zentrale.Models;

public sealed class BookingRecord
{
    public string Id { get; set; } = "";
    public string Reference { get; set; } = "";
    public string HostId { get; set; } = "";
    public string StayDate { get; set; } = "";
    public int Guests { get; set; } = 1;
    public string GuestName { get; set; } = "";
    public string GuestEmail { get; set; } = "";
    public string GuestPhone { get; set; } = "";
    public string Status { get; set; } = "requested";
    public double? Price { get; set; }
    public string Note { get; set; } = "";
    public string? TripId { get; set; }
    public long? TripDayId { get; set; }
}
