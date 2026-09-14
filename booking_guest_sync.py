from __future__ import annotations

import os
import threading
import time
from datetime import date, datetime

from flask import jsonify, request

_sync_lock = threading.Lock()
_last_auto_sync = 0.0


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _auto_enabled() -> bool:
    return os.environ.get("BOOKING_AUTO_SYNC_GUESTS", "1").strip().lower() in {"1", "true", "yes", "on"}


def init_booking_guest_sync(app, db, authorize):
    """Enrich Booking iCal occupancy with reservation details from Connectivity.

    Availability remains privacy-safe iCal data. Full reservation details are
    written only to the private OS database and are never emitted by public or
    channel calendar feeds.
    """

    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS zab_booking_guest_pending (
                   reservation_id TEXT NOT NULL,
                   room TEXT NOT NULL,
                   room_type_id TEXT NOT NULL DEFAULT '',
                   arrival TEXT NOT NULL,
                   departure TEXT NOT NULL,
                   guest_name TEXT NOT NULL DEFAULT '',
                   country TEXT NOT NULL DEFAULT '',
                   guests INTEGER NOT NULL DEFAULT 0,
                   breakfast INTEGER,
                   roomreservation_id TEXT NOT NULL DEFAULT '',
                   meal_plan TEXT NOT NULL DEFAULT '',
                   updated_at TEXT NOT NULL,
                   PRIMARY KEY(reservation_id, room, arrival, departure)
               )"""
        )

    def _upsert_meta(conn, block, record) -> None:
        existing = conn.execute(
            """SELECT guest_name,country,guests,booking_reference,breakfast,transport_mode,notes
               FROM zab_external_guest_meta
               WHERE room=? AND source='booking_ical' AND uid=? AND start_date=? AND end_date=?""",
            (block["room"], block["uid"] or "", block["start_date"], block["end_date"]),
        ).fetchone()
        guest_name = str(record.get("guest_name") or "").strip() or (existing["guest_name"] if existing else "")
        country = str(record.get("country") or "").strip().upper() or (existing["country"] if existing else "")
        guests = int(record.get("guests") or 0) or (int(existing["guests"] or 0) if existing else 0)
        reference = str(record.get("reservation_id") or "").strip() or (existing["booking_reference"] if existing else "")
        breakfast = record.get("breakfast")
        if breakfast is None and existing:
            breakfast = existing["breakfast"]
        transport = existing["transport_mode"] if existing else ""
        notes = existing["notes"] if existing else ""
        conn.execute(
            """INSERT INTO zab_external_guest_meta
               (room,source,uid,start_date,end_date,guest_name,country,guests,booking_reference,
                updated_at,breakfast,transport_mode,notes)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(room,source,uid,start_date,end_date) DO UPDATE SET
                 guest_name=excluded.guest_name,country=excluded.country,guests=excluded.guests,
                 booking_reference=excluded.booking_reference,updated_at=excluded.updated_at,
                 breakfast=excluded.breakfast,transport_mode=excluded.transport_mode,notes=excluded.notes""",
            (
                block["room"], "booking_ical", block["uid"] or "", block["start_date"], block["end_date"],
                guest_name, country, guests, reference, _now(),
                None if breakfast is None else (1 if bool(breakfast) else 0), transport, notes,
            ),
        )

    def _find_block(conn, record):
        room = str(record.get("room") or "").strip()
        arrival = str(record.get("arrival") or "").strip()
        departure = str(record.get("departure") or "").strip()
        reservation_id = str(record.get("reservation_id") or "").strip()
        rows = conn.execute(
            """SELECT id,room,start_date,end_date,source,uid,summary
               FROM external_blocks
               WHERE room=? AND source='booking_ical' AND start_date=? AND end_date=?
               ORDER BY id""",
            (room, arrival, departure),
        ).fetchall()
        if len(rows) == 1:
            return rows[0]
        if reservation_id:
            for row in rows:
                searchable = f"{row['uid'] or ''} {row['summary'] or ''}"
                if reservation_id in searchable:
                    return row
        return None

    def _store_pending(conn, record) -> None:
        breakfast = record.get("breakfast")
        conn.execute(
            """INSERT INTO zab_booking_guest_pending
               (reservation_id,room,room_type_id,arrival,departure,guest_name,country,guests,
                breakfast,roomreservation_id,meal_plan,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(reservation_id,room,arrival,departure) DO UPDATE SET
                 room_type_id=excluded.room_type_id,guest_name=excluded.guest_name,country=excluded.country,
                 guests=excluded.guests,breakfast=excluded.breakfast,
                 roomreservation_id=excluded.roomreservation_id,meal_plan=excluded.meal_plan,
                 updated_at=excluded.updated_at""",
            (
                str(record.get("reservation_id") or ""), str(record.get("room") or ""),
                str(record.get("room_type_id") or ""), str(record.get("arrival") or ""),
                str(record.get("departure") or ""), str(record.get("guest_name") or "")[:200],
                str(record.get("country") or "")[:30], int(record.get("guests") or 0),
                None if breakfast is None else (1 if bool(breakfast) else 0),
                str(record.get("roomreservation_id") or "")[:100], str(record.get("meal_plan") or "")[:500], _now(),
            ),
        )

    def _pending_as_record(row) -> dict:
        return {
            "reservation_id": row["reservation_id"], "room": row["room"], "room_type_id": row["room_type_id"],
            "arrival": row["arrival"], "departure": row["departure"], "guest_name": row["guest_name"],
            "country": row["country"], "guests": row["guests"],
            "breakfast": None if row["breakfast"] is None else bool(row["breakfast"]),
            "roomreservation_id": row["roomreservation_id"], "meal_plan": row["meal_plan"],
        }

    def _attach_pending() -> int:
        attached = 0
        with db() as conn:
            rows = conn.execute("SELECT * FROM zab_booking_guest_pending ORDER BY arrival").fetchall()
            for row in rows:
                record = _pending_as_record(row)
                block = _find_block(conn, record)
                if not block:
                    continue
                _upsert_meta(conn, block, record)
                conn.execute(
                    "DELETE FROM zab_booking_guest_pending WHERE reservation_id=? AND room=? AND arrival=? AND departure=?",
                    (record["reservation_id"], record["room"], record["arrival"], record["departure"]),
                )
                attached += 1
        return attached

    def sync_booking_guests() -> dict:
        fetcher = app.extensions.get("zab_booking_fetch_future_reservations")
        if not callable(fetcher):
            return {"ok": False, "status": "adapter_missing", "message": "Booking.com Reservierungsadapter fehlt."}
        if not _sync_lock.acquire(blocking=False):
            return {"ok": True, "status": "already_running", "message": "Booking-Gastsynchronisierung läuft bereits."}
        try:
            attached_from_pending = _attach_pending()
            result = dict(fetcher())
            if not result.get("ok"):
                return result
            attached = attached_from_pending
            skipped = 0
            with db() as conn:
                for record in result.get("reservations", []):
                    room = str(record.get("room") or "").strip()
                    try:
                        arrival = date.fromisoformat(str(record.get("arrival") or ""))
                        departure = date.fromisoformat(str(record.get("departure") or ""))
                    except Exception:
                        skipped += 1
                        continue
                    if not room or departure <= arrival:
                        skipped += 1
                        continue
                    block = _find_block(conn, record)
                    if block:
                        _upsert_meta(conn, block, record)
                        conn.execute(
                            "DELETE FROM zab_booking_guest_pending WHERE reservation_id=? AND room=? AND arrival=? AND departure=?",
                            (str(record.get("reservation_id") or ""), room, arrival.isoformat(), departure.isoformat()),
                        )
                        attached += 1
                    else:
                        _store_pending(conn, record)
                pending_total = conn.execute("SELECT COUNT(*) AS n FROM zab_booking_guest_pending").fetchone()["n"]
            return {
                "ok": True,
                "status": "synced",
                "message": f"Booking-Gastdaten: {attached} zugeordnet, {pending_total} warten auf iCal-Zuordnung.",
                "attached": attached,
                "pending": int(pending_total),
                "skipped": skipped,
                "detail_errors": result.get("detail_errors", []),
            }
        except Exception as exc:
            return {"ok": False, "status": "error", "message": str(exc)[:900]}
        finally:
            _sync_lock.release()

    app.extensions["zab_booking_guest_sync"] = sync_booking_guests
    app.extensions["zab_booking_guest_sync_initialized"] = True

    @app.post("/api/central/zab-calendar/sync-booking-guests")
    def booking_guest_sync_route():
        if not authorize():
            return jsonify(ok=False, error="unauthorized"), 401
        result = sync_booking_guests()
        return jsonify(result), 200 if result.get("ok") else 502

    @app.before_request
    def booking_guest_auto_sync():
        global _last_auto_sync
        if request.path != "/api/central/zab-calendar" or not _auto_enabled():
            return None
        # before_request runs before the calendar endpoint performs its own
        # authorization. Never trigger a Booking.com PII fetch for an
        # unauthenticated request.
        if not authorize():
            return None
        checker = app.extensions.get("zab_booking_connectivity_status")
        try:
            configured = callable(checker) and bool(checker().get("configured"))
        except Exception:
            configured = False
        if not configured:
            return None
        now = time.monotonic()
        if now - _last_auto_sync < 600:
            _attach_pending()
            return None
        _last_auto_sync = now
        sync_booking_guests()
        return None

    @app.get("/health/booking-guest-sync")
    def booking_guest_sync_health():
        with db() as conn:
            pending = conn.execute("SELECT COUNT(*) AS n FROM zab_booking_guest_pending").fetchone()["n"]
        return jsonify(ok=True, initialized=True, auto=_auto_enabled(), pending=int(pending)), 200

    return sync_booking_guests
