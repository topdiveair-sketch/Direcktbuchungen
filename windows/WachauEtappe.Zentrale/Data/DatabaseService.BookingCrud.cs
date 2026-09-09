using Microsoft.Data.Sqlite;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale.Data;

public sealed partial class DatabaseService
{
    public BookingRecord? GetBooking(string id)
    {
        EnsureBookingTables();
        using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();
        q.CommandText="SELECT Id,Reference,HostId,StayDate,Guests,COALESCE(GuestName,''),COALESCE(GuestEmail,''),COALESCE(GuestPhone,''),Status,Price,COALESCE(Note,''),TripId,TripDayId FROM Bookings WHERE Id=@id";
        q.Parameters.AddWithValue("@id",id);using var r=q.ExecuteReader();if(!r.Read())return null;
        return new BookingRecord{Id=r.GetString(0),Reference=r.GetString(1),HostId=r.GetString(2),StayDate=r.GetString(3),Guests=r.GetInt32(4),GuestName=r.GetString(5),GuestEmail=r.GetString(6),GuestPhone=r.GetString(7),Status=r.GetString(8),Price=r.IsDBNull(9)?null:r.GetDouble(9),Note=r.GetString(10),TripId=r.IsDBNull(11)?null:r.GetString(11),TripDayId=r.IsDBNull(12)?null:r.GetInt64(12)};
    }

    private void EnsureBookingCapacityForEdit(string bookingId,string hostId,string stayDate,string status)
    {
        if(status is not ("requested" or "confirmed")) return;
        using var c=new SqliteConnection(ConnectionString);c.Open();using var q=c.CreateCommand();
        q.CommandText="SELECT (SELECT COUNT(*) FROM Bookings b WHERE b.Id<>@id AND b.HostId=@h AND b.StayDate=@d AND b.Status IN ('requested','confirmed')) < COALESCE((SELECT Units FROM HostCapacity WHERE HostId=@h),1)";
        q.Parameters.AddWithValue("@id",bookingId);q.Parameters.AddWithValue("@h",hostId);q.Parameters.AddWithValue("@d",stayDate);
        if(Convert.ToInt32(q.ExecuteScalar()??0)!=1) throw new InvalidOperationException("Für diesen Gastgeber ist an diesem Datum kein freies Kontingent mehr vorhanden.");
    }

    public void UpdateBooking(string id,string hostId,string stayDate,int guests,string guestName,string guestEmail,string guestPhone,double? price,string status,string note)
    {
        EnsureBookingTables();
        var existing=GetBooking(id)??throw new InvalidOperationException("Buchung wurde nicht gefunden.");
        EnsureBookingCapacityForEdit(id,hostId,stayDate,status);
        Execute("UPDATE Bookings SET HostId=@h,StayDate=@d,Guests=@g,GuestName=@n,GuestEmail=@e,GuestPhone=@p,Price=@price,Status=@s,Note=@note,UpdatedUtc=@u WHERE Id=@id",
            ("@h",hostId),("@d",stayDate),("@g",Math.Max(1,guests)),("@n",guestName),("@e",guestEmail),("@p",guestPhone),("@price",price),("@s",status),("@note",note),("@u",DateTime.UtcNow.ToString("O")),("@id",id));
        if(existing.TripDayId is not null)
            Execute("UPDATE TripDays SET HostId=@h,TravelDate=@d,BookingStatus=@s WHERE Id=@day",("@h",hostId),("@d",stayDate),("@s",status),("@day",existing.TripDayId));
        if(!string.IsNullOrWhiteSpace(existing.TripId)) RecalculateTripStatus(existing.TripId);
        Audit("booking_updated","Booking",id,$"{existing.Reference}; host={hostId}; date={stayDate}; status={status}");
    }

    public void DeleteBooking(string id)
    {
        EnsureBookingTables();
        var existing=GetBooking(id)??throw new InvalidOperationException("Buchung wurde nicht gefunden.");
        Execute("DELETE FROM Bookings WHERE Id=@id",("@id",id));
        if(existing.TripDayId is not null)
            Execute("UPDATE TripDays SET BookingStatus='open' WHERE Id=@day",("@day",existing.TripDayId));
        if(!string.IsNullOrWhiteSpace(existing.TripId)) RecalculateTripStatus(existing.TripId);
        Audit("booking_deleted","Booking",id,$"{existing.Reference}; {existing.GuestName}; {existing.StayDate}");
    }
}
