namespace WachauEtappe.Zentrale.Models;

public sealed class TripRecord
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Reference { get; set; } = "";
    public string GuestName { get; set; } = "";
    public string GuestEmail { get; set; } = "";
    public string GuestPhone { get; set; } = "";
    public string StartDate { get; set; } = "";
    public string RouteId { get; set; } = "welterbesteig-wachau";
    public string Status { get; set; } = "draft";
    public bool LuggageTransfer { get; set; }
    public int Guests { get; set; } = 1;
    public double DailyTargetKm { get; set; } = 18;
}

public sealed class TripDayRecord
{
    public long Id { get; set; }
    public string TripId { get; set; } = "";
    public int DayNumber { get; set; }
    public string TravelDate { get; set; } = "";
    public string FromPlace { get; set; } = "";
    public string ToPlace { get; set; } = "";
    public double DistanceKm { get; set; }
    public string HostId { get; set; } = "";
    public string HostName { get; set; } = "";
    public string BookingStatus { get; set; } = "open";
    public string LuggageStatus { get; set; } = "none";
}
