namespace WachauEtappe.Zentrale.Models;

public sealed class MapHostStatus
{
    public string HostId { get; set; } = "";
    public string Name { get; set; } = "";
    public string Location { get; set; } = "";
    public string Phone { get; set; } = "";
    public int RoomsTotal { get; set; }
    public int RoomsFree { get; set; }
    public int BedsTotal { get; set; }
    public int BedsFree { get; set; }
    public string Availability { get; set; } = "unknown";
    public string DisplayStatus { get; set; } = "Unbekannt";
    public string StatusColor { get; set; } = "gray";
    public double Latitude { get; set; }
    public double Longitude { get; set; }
    public bool HasCoordinates { get; set; }
}
