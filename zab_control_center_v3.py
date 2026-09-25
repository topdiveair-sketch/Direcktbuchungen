from __future__ import annotations

import hmac
import os
import urllib.request
from datetime import date, datetime, timedelta

from flask import Response, jsonify, request

CHANNELS = ("direct", "booking", "airbnb", "other")
ROOM_LABELS = {
    "Bachblick": "Gartenblick Zimmer",
    "Marillenzimmer": "Marillenzimmer",
    "Weinbergzimmer": "Weinbergzimmer",
    "Donauzimmer": "Donauzimmer",
}
TRANSPORT_MODES = {"", "auto", "bike", "hiker", "other"}
GENERIC_SUMMARIES = {
    "reserved", "reservation", "not available", "blocked", "busy", "unavailable",
    "booking.com", "belegt - externer kalender", "belegt - zuhause am bach",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return start, end


def _bool_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"", "none", "null", "inherit", "default", "standard"}:
        return None
    if text in {"1", "true", "yes", "on", "open", "offen", "ja"}:
        return True
    if text in {"0", "false", "no", "off", "closed", "geschlossen", "nein"}:
        return False
    raise ValueError("Ungültiger Wahrheitswert")


def _price_value(value):
    if value is None or str(value).strip() == "":
        return None
    price = round(float(str(value).replace(",", ".")), 2)
    if price < 0 or price > 50000:
        raise ValueError("Ungültiger Preis")
    return price


def _transport(value: str) -> str:
    text = (value or "").strip().lower()
    aliases = {
        "car": "auto", "pkw": "auto", "auto": "auto",
        "bicycle": "bike", "fahrrad": "bike", "rad": "bike", "bike": "bike",
        "walk": "hiker", "walking": "hiker", "wanderer": "hiker", "hiker": "hiker",
        "sonstiges": "other", "other": "other",
    }
    text = aliases.get(text, text)
    return text if text in TRANSPORT_MODES else "other"


def _parse_ical_date(value: str):
    raw = (value or "").strip().split("T", 1)[0][:8]
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except Exception:
        return None


def _parse_ical(text: str) -> list[dict]:
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = []
    for line in raw_lines:
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    events = []
    current = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if current.get("start") and current.get("end") and current["end"] > current["start"]:
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            key = key.split(";", 1)[0]
            if key == "DTSTART":
                current["start"] = _parse_ical_date(value)
            elif key == "DTEND":
                current["end"] = _parse_ical_date(value)
            elif key == "UID":
                current["uid"] = value.strip()
            elif key == "SUMMARY":
                current["summary"] = value.strip()
    return events


def _ical_escape(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def init_zab_control_center_v3(app, db, rooms, authorize, direct_rate_fn=None):
    """Install the Windows-first ZAB OS bridge without changing legacy URLs.

    Internal room keys stay compatible with the existing system. In the control
    center Bachblick is displayed as Gartenblick Zimmer.
    """

    def _authorized() -> bool:
        try:
            return bool(authorize())
        except Exception:
            return False

    def _columns(conn, table: str) -> set[str]:
        try:
            return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
        except Exception:
            return set()

    def _ensure_column(conn, table: str, name: str, definition: str):
        if name not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS zab_booking_guest_meta (
                booking_id INTEGER PRIMARY KEY,
                country TEXT NOT NULL DEFAULT '',
                transport_mode TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zab_channel_imports (
                room TEXT NOT NULL,
                channel TEXT NOT NULL,
                import_url TEXT NOT NULL DEFAULT '',
                last_sync TEXT NOT NULL DEFAULT '',
                last_result TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(room, channel)
            );

            CREATE TABLE IF NOT EXISTS zab_booking_rate_sync (
                room TEXT NOT NULL,
                day TEXT NOT NULL,
                price REAL,
                status TEXT NOT NULL DEFAULT 'pending',
                message TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(room, day)
            );
            """
        )
        _ensure_column(conn, "zab_external_guest_meta", "breakfast", "INTEGER")
        _ensure_column(conn, "zab_external_guest_meta", "transport_mode", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "zab_external_guest_meta", "notes", "TEXT NOT NULL DEFAULT ''")
        now = _now()
        for room in rooms:
            for channel in CHANNELS:
                conn.execute(
                    """INSERT OR IGNORE INTO zab_channel_controls(room,channel,enabled,updated_at)
                       VALUES(?,?,1,?)""",
                    (room, channel, now),
                )
                if channel in {"airbnb", "other"}:
                    conn.execute(
                        """INSERT OR IGNORE INTO zab_channel_imports(room,channel,import_url,last_sync,last_result)
                           VALUES(?,?, '', '', '')""",
                        (room, channel),
                    )

    app.extensions["zab_rooms"] = rooms

    def _global_enabled(conn, room: str, channel: str) -> bool:
        row = conn.execute(
            "SELECT enabled FROM zab_channel_controls WHERE room=? AND channel=?",
            (room, channel),
        ).fetchone()
        return True if row is None else bool(row["enabled"])

    def _day_row(conn, room: str, channel: str, day: date):
        return conn.execute(
            """SELECT enabled_override,price FROM zab_channel_day_settings
               WHERE room=? AND channel=? AND day=?""",
            (room, channel, day.isoformat()),
        ).fetchone()

    def _channel_open(conn, room: str, channel: str, day: date) -> bool:
        row = _day_row(conn, room, channel, day)
        if row is not None and row["enabled_override"] is not None:
            return bool(row["enabled_override"])
        if not _global_enabled(conn, room, channel):
            return False
        block = conn.execute(
            """SELECT 1 FROM zab_channel_blocks
               WHERE room=? AND channel=? AND start_date<=? AND end_date>?
               LIMIT 1""",
            (room, channel, day.isoformat(), day.isoformat()),
        ).fetchone()
        return not bool(block)

    def _direct_price(conn, room: str, day: date):
        row = _day_row(conn, room, "direct", day)
        if row is not None and row["price"] is not None:
            return float(row["price"]), True
        if room == "Bachblick" and callable(direct_rate_fn):
            try:
                value = direct_rate_fn(day)
                if value is not None:
                    return float(value), False
            except Exception:
                pass
        try:
            return float(rooms[room].get("price")), False
        except Exception:
            return None, False

    def _channel_price(conn, room: str, channel: str, day: date):
        if channel == "direct":
            return _direct_price(conn, room, day)
        row = _day_row(conn, room, channel, day)
        if row is not None and row["price"] is not None:
            return float(row["price"]), True
        return None, False

    def _meta_for_external(conn, row):
        meta = conn.execute(
            """SELECT guest_name,country,guests,booking_reference,breakfast,transport_mode,notes
               FROM zab_external_guest_meta
               WHERE room=? AND source=? AND uid=? AND start_date=? AND end_date=?""",
            (row["room"], row["source"], row["uid"] or "", row["start_date"], row["end_date"]),
        ).fetchone()
        return dict(meta) if meta else {}

    def _occupancy(conn, start: date, end: date) -> list[dict]:
        output = []
        direct = conn.execute(
            """SELECT b.id,b.uid,b.room,b.arrival,b.departure,b.first_name,b.last_name,
                      b.adults,b.breakfast,b.status,b.email,
                      COALESCE(g.country,'') AS profile_country,
                      COALESCE(m.country,'') AS meta_country,
                      COALESCE(m.transport_mode,'') AS transport_mode,
                      COALESCE(m.notes,'') AS guest_notes
               FROM bookings b
               LEFT JOIN guest_profiles g ON lower(g.email)=lower(b.email)
               LEFT JOIN zab_booking_guest_meta m ON m.booking_id=b.id
               WHERE b.status IN ('pending','confirmed') AND b.arrival<? AND b.departure>?""",
            (end.isoformat(), start.isoformat()),
        ).fetchall()
        for row in direct:
            output.append({
                "kind": "direct",
                "booking_id": int(row["id"]),
                "uid": row["uid"] or "",
                "room": row["room"],
                "arrival": row["arrival"],
                "departure": row["departure"],
                "guest_name": f"{row['first_name']} {row['last_name']}".strip(),
                "country": row["meta_country"] or row["profile_country"] or "",
                "guests": int(row["adults"] or 0),
                "breakfast": bool(row["breakfast"]),
                "transport_mode": row["transport_mode"] or "",
                "notes": row["guest_notes"] or "",
                "source": "direct",
            })

        external = conn.execute(
            """SELECT id,room,start_date,end_date,source,uid,summary FROM external_blocks
               WHERE start_date<? AND end_date>?""",
            (end.isoformat(), start.isoformat()),
        ).fetchall()
        for row in external:
            md = _meta_for_external(conn, row)
            guest_name = str(md.get("guest_name") or "").strip()
            summary = str(row["summary"] or "").strip()
            if not guest_name and summary and summary.casefold() not in GENERIC_SUMMARIES:
                guest_name = summary
            source = str(row["source"] or "external")
            channel = "booking" if source == "booking_ical" else "airbnb" if source == "airbnb_ical" else "other"
            output.append({
                "kind": channel,
                "external_id": int(row["id"]),
                "uid": row["uid"] or "",
                "room": row["room"],
                "arrival": row["start_date"],
                "departure": row["end_date"],
                "guest_name": guest_name,
                "country": str(md.get("country") or ""),
                "guests": int(md.get("guests") or 0),
                "breakfast": None if md.get("breakfast") is None else bool(md.get("breakfast")),
                "transport_mode": str(md.get("transport_mode") or ""),
                "notes": str(md.get("notes") or ""),
                "booking_reference": str(md.get("booking_reference") or ""),
                "source": source,
            })
        return output

    def _sync_booking_rate(room: str, day: date, price):
        pusher = app.extensions.get("zab_booking_push_rate")
        if price is None:
            result = {"ok": False, "status": "no_local_price", "message": "Kein Booking-Preis gesetzt."}
        elif not callable(pusher):
            result = {"ok": False, "status": "adapter_missing", "message": "Booking.com Connectivity-Adapter fehlt."}
        else:
            try:
                result = dict(pusher(room, day, float(price)))
            except Exception as exc:
                result = {"ok": False, "status": "error", "message": str(exc)[:700]}
        with db() as conn:
            conn.execute(
                """INSERT INTO zab_booking_rate_sync(room,day,price,status,message,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(room,day) DO UPDATE SET price=excluded.price,status=excluded.status,
                     message=excluded.message,updated_at=excluded.updated_at""",
                (room, day.isoformat(), price, result.get("status", "error"), result.get("message", "")[:900], _now()),
            )
        return result

    def _set_day_values(room: str, start: date, end: date, data: dict):
        supplied = {}
        for channel in CHANNELS:
            enabled_key = f"{channel}_enabled"
            price_key = f"{channel}_price"
            if enabled_key in data:
                supplied[(channel, "enabled")] = _bool_value(data.get(enabled_key))
            if price_key in data:
                supplied[(channel, "price")] = _price_value(data.get(price_key))
        if not supplied:
            raise ValueError("no_changes")

        changed_booking_prices = []
        with db() as conn:
            current = start
            while current <= end:
                for channel in CHANNELS:
                    if not any((channel, field) in supplied for field in ("enabled", "price")):
                        continue
                    old = _day_row(conn, room, channel, current)
                    enabled = old["enabled_override"] if old else None
                    price = old["price"] if old else None
                    if (channel, "enabled") in supplied:
                        val = supplied[(channel, "enabled")]
                        enabled = None if val is None else (1 if val else 0)
                    if (channel, "price") in supplied:
                        price = supplied[(channel, "price")]
                        if channel == "booking" and price is not None:
                            changed_booking_prices.append((current, float(price)))
                    if enabled is None and price is None:
                        conn.execute(
                            "DELETE FROM zab_channel_day_settings WHERE room=? AND day=? AND channel=?",
                            (room, current.isoformat(), channel),
                        )
                    else:
                        conn.execute(
                            """INSERT INTO zab_channel_day_settings(room,day,channel,enabled_override,price,updated_at)
                               VALUES(?,?,?,?,?,?)
                               ON CONFLICT(room,day,channel) DO UPDATE SET enabled_override=excluded.enabled_override,
                                 price=excluded.price,updated_at=excluded.updated_at""",
                            (room, current.isoformat(), channel, enabled, price, _now()),
                        )
                current += timedelta(days=1)
        return changed_booking_prices

    def _calendar_snapshot(year: int, month: int):
        start, end = _month_bounds(year, month)
        with db() as conn:
            occupancy = _occupancy(conn, start, end)
            days = {room: {} for room in rooms}
            for room in rooms:
                current = start
                while current < end:
                    channels = {}
                    for channel in CHANNELS:
                        price, overridden = _channel_price(conn, room, channel, current)
                        channels[channel] = {
                            "open": _channel_open(conn, room, channel, current),
                            "price": price,
                            "price_override": overridden,
                        }
                    sync = conn.execute(
                        "SELECT status,message,updated_at FROM zab_booking_rate_sync WHERE room=? AND day=?",
                        (room, current.isoformat()),
                    ).fetchone()
                    days[room][current.isoformat()] = {
                        "channels": channels,
                        "booking_sync": dict(sync) if sync else None,
                    }
                    current += timedelta(days=1)
            controls = {
                room: {channel: _global_enabled(conn, room, channel) for channel in CHANNELS}
                for room in rooms
            }
            imports = [dict(r) for r in conn.execute("SELECT * FROM zab_channel_imports ORDER BY room,channel")]
        return {
            "ok": True,
            "year": year,
            "month": month,
            "rooms": [{"key": room, "label": ROOM_LABELS.get(room, room)} for room in rooms],
            "channels": list(CHANNELS),
            "controls": controls,
            "days": days,
            "occupancy": occupancy,
            "imports": imports,
        }

    def _closed_intervals(conn, room: str, channel: str, start: date, end: date):
        result = []
        opened = None
        current = start
        while current < end:
            closed = not _channel_open(conn, room, channel, current)
            if closed and opened is None:
                opened = current
            elif not closed and opened is not None:
                result.append((opened, current))
                opened = None
            current += timedelta(days=1)
        if opened is not None:
            result.append((opened, end))
        return result

    def _feed_token() -> str:
        with db() as conn:
            row = conn.execute("SELECT value FROM zab_calendar_meta WHERE key='feed_token'").fetchone()
        return row["value"] if row else ""

    def _ical(room: str, channel: str, public_direct: bool = False) -> str:
        horizon_start = date.today() - timedelta(days=2)
        horizon_end = horizon_start + timedelta(days=732)
        exclude_source = {"booking": "booking_ical", "airbnb": "airbnb_ical", "other": "other_ical"}.get(channel)
        with db() as conn:
            local = conn.execute(
                """SELECT id,uid,arrival,departure FROM bookings
                   WHERE room=? AND status IN ('pending','confirmed') ORDER BY arrival""",
                (room,),
            ).fetchall()
            external = conn.execute(
                "SELECT id,start_date,end_date,source,uid FROM external_blocks WHERE room=? ORDER BY start_date",
                (room,),
            ).fetchall()
            master = conn.execute(
                "SELECT id,start_date,end_date FROM zab_master_blocks WHERE room=? ORDER BY start_date",
                (room,),
            ).fetchall()
            closed = _closed_intervals(conn, room, "direct" if public_direct else channel, horizon_start, horizon_end)
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Zuhause am Bach//ZAB OS//DE", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]

        def add(uid: str, start: str, end: str, summary: str):
            lines.extend([
                "BEGIN:VEVENT", f"UID:{_ical_escape(uid)}", f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{_parse_date(start).strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{_parse_date(end).strftime('%Y%m%d')}",
                f"SUMMARY:{_ical_escape(summary)}", "TRANSP:OPAQUE", "END:VEVENT",
            ])

        for row in local:
            add(row["uid"] or f"zab-booking-{row['id']}@zab", row["arrival"], row["departure"], "Belegt - Zuhause am Bach")
        for row in external:
            if not public_direct and exclude_source and row["source"] == exclude_source:
                continue
            add(row["uid"] or f"zab-external-{row['id']}@zab", row["start_date"], row["end_date"], "Belegt - externer Kanal")
        for row in master:
            add(f"zab-master-{row['id']}@zab", row["start_date"], row["end_date"], "Gesperrt - Zuhause am Bach OS")
        for idx, (a, b) in enumerate(closed, 1):
            add(f"zab-closed-{room}-{channel}-{idx}-{a.isoformat()}@zab", a.isoformat(), b.isoformat(), "Gesperrt - Zuhause am Bach OS")
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    @app.get("/api/central/zab-calendar")
    def zab_calendar_snapshot():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        try:
            year = int(request.args.get("year", date.today().year))
            month = int(request.args.get("month", date.today().month))
            if not 1 <= month <= 12:
                raise ValueError
        except Exception:
            return jsonify(ok=False, error="invalid_month"), 400
        payload = _calendar_snapshot(year, month)
        checker = app.extensions.get("zab_booking_connectivity_status")
        payload["booking_connectivity"] = checker("Bachblick") if callable(checker) else {"configured": False}
        payload["paypal_master_independent"] = bool(app.extensions.get("zab_paypal_master_independent"))
        return jsonify(payload), 200, {"Cache-Control": "no-store"}

    @app.get("/api/central/revenue-management")
    def zab_revenue_management():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        provider = app.extensions.get("zab_revenue_management_status")
        if not callable(provider):
            return jsonify(ok=False, error="revenue_management_unavailable"), 503
        try:
            payload = dict(provider())
            payload["ok"] = True
            return jsonify(payload), 200, {"Cache-Control": "no-store"}
        except Exception as exc:
            return jsonify(ok=False, error="revenue_management_failed", message=str(exc)[:700]), 503

    @app.post("/api/central/zab-calendar/day-setting")
    def zab_calendar_day_setting():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        room = str(data.get("room") or "").strip()
        if room not in rooms:
            return jsonify(ok=False, error="unknown_room"), 400
        try:
            start = date.fromisoformat(str(data.get("start_date") or ""))
            end = date.fromisoformat(str(data.get("end_date") or data.get("start_date") or ""))
            if end < start or (end - start).days > 370:
                raise ValueError
            booking_prices = _set_day_values(room, start, end, data)
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc) or "invalid_values"), 400
        sync_results = []
        if data.get("sync_booking_price", True):
            for day_value, price in booking_prices:
                sync_results.append({"date": day_value.isoformat(), **_sync_booking_rate(room, day_value, price)})
        return jsonify(ok=True, room=room, start_date=start.isoformat(), end_date=end.isoformat(), booking_sync=sync_results), 200

    @app.post("/api/central/zab-calendar/channel")
    def zab_calendar_channel():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        room = str(data.get("room") or "")
        channel = str(data.get("channel") or "").lower()
        if room not in rooms or channel not in CHANNELS:
            return jsonify(ok=False, error="invalid_channel"), 400
        try:
            enabled = _bool_value(data.get("enabled"))
        except ValueError:
            return jsonify(ok=False, error="invalid_enabled"), 400
        if enabled is None:
            enabled = True
        with db() as conn:
            conn.execute(
                """INSERT INTO zab_channel_controls(room,channel,enabled,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(room,channel) DO UPDATE SET enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (room, channel, 1 if enabled else 0, _now()),
            )
        return jsonify(ok=True, room=room, channel=channel, enabled=bool(enabled)), 200

    @app.post("/api/central/zab-calendar/guest-meta")
    def zab_calendar_guest_meta():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        country = str(data.get("country") or "").strip()[:120]
        transport_mode = _transport(str(data.get("transport_mode") or ""))
        notes = str(data.get("notes") or "").strip()[:500]
        breakfast = _bool_value(data.get("breakfast")) if "breakfast" in data else None
        guests = None
        if "guests" in data and str(data.get("guests") or "").strip():
            try:
                guests = max(1, min(30, int(data.get("guests"))))
            except Exception:
                return jsonify(ok=False, error="invalid_guests"), 400

        booking_id = data.get("booking_id")
        if booking_id:
            try:
                booking_id = int(booking_id)
            except Exception:
                return jsonify(ok=False, error="invalid_booking_id"), 400
            with db() as conn:
                row = conn.execute("SELECT id FROM bookings WHERE id=?", (booking_id,)).fetchone()
                if not row:
                    return jsonify(ok=False, error="booking_not_found"), 404
                conn.execute(
                    """INSERT INTO zab_booking_guest_meta(booking_id,country,transport_mode,notes,updated_at)
                       VALUES(?,?,?,?,?) ON CONFLICT(booking_id) DO UPDATE SET country=excluded.country,
                       transport_mode=excluded.transport_mode,notes=excluded.notes,updated_at=excluded.updated_at""",
                    (booking_id, country, transport_mode, notes, _now()),
                )
                if breakfast is not None:
                    conn.execute("UPDATE bookings SET breakfast=? WHERE id=?", (1 if breakfast else 0, booking_id))
                if guests is not None:
                    conn.execute("UPDATE bookings SET adults=? WHERE id=?", (guests, booking_id))
            return jsonify(ok=True, kind="direct", booking_id=booking_id), 200

        room = str(data.get("room") or "")
        source = str(data.get("source") or "")[:80]
        uid = str(data.get("uid") or "")[:500]
        start_date = str(data.get("start_date") or "")
        end_date = str(data.get("end_date") or "")
        if room not in rooms or not source:
            return jsonify(ok=False, error="external_identity_missing"), 400
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
            if end <= start:
                raise ValueError
        except Exception:
            return jsonify(ok=False, error="invalid_dates"), 400
        guest_name = str(data.get("guest_name") or "").strip()[:200]
        reference = str(data.get("booking_reference") or "").strip()[:160]
        with db() as conn:
            conn.execute(
                """INSERT INTO zab_external_guest_meta
                   (room,source,uid,start_date,end_date,guest_name,country,guests,booking_reference,updated_at,breakfast,transport_mode,notes)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(room,source,uid,start_date,end_date) DO UPDATE SET guest_name=excluded.guest_name,
                     country=excluded.country,guests=excluded.guests,booking_reference=excluded.booking_reference,
                     updated_at=excluded.updated_at,breakfast=excluded.breakfast,
                     transport_mode=excluded.transport_mode,notes=excluded.notes""",
                (room, source, uid, start.isoformat(), end.isoformat(), guest_name, country, guests, reference, _now(),
                 None if breakfast is None else (1 if breakfast else 0), transport_mode, notes),
            )
        return jsonify(ok=True, kind="external"), 200

    @app.post("/api/central/zab-calendar/import-source")
    def zab_calendar_import_source():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        room = str(data.get("room") or "")
        channel = str(data.get("channel") or "").lower()
        import_url = str(data.get("import_url") or "").strip()[:2000]
        if room not in rooms or channel not in {"airbnb", "other"}:
            return jsonify(ok=False, error="invalid_channel"), 400
        if import_url and not import_url.startswith("https://"):
            return jsonify(ok=False, error="https_required"), 400
        with db() as conn:
            conn.execute(
                """INSERT INTO zab_channel_imports(room,channel,import_url,last_sync,last_result)
                   VALUES(?,?,?,'','') ON CONFLICT(room,channel) DO UPDATE SET import_url=excluded.import_url""",
                (room, channel, import_url),
            )
        return jsonify(ok=True, room=room, channel=channel, configured=bool(import_url)), 200

    @app.post("/api/central/zab-calendar/sync-channel")
    def zab_calendar_sync_channel():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        room = str(data.get("room") or "")
        channel = str(data.get("channel") or "").lower()
        if room not in rooms or channel not in {"booking", "airbnb", "other"}:
            return jsonify(ok=False, error="invalid_channel"), 400
        if channel == "booking":
            sync = app.extensions.get("zab_sync_room")
            if not callable(sync):
                return jsonify(ok=False, error="booking_sync_unavailable"), 503
            count, message = sync(room)
            return jsonify(ok=message == "Synchronisierung erfolgreich.", count=count, message=message), 200 if message == "Synchronisierung erfolgreich." else 502
        with db() as conn:
            row = conn.execute("SELECT import_url FROM zab_channel_imports WHERE room=? AND channel=?", (room, channel)).fetchone()
        url = str(row["import_url"] if row else "").strip()
        if not url:
            return jsonify(ok=False, error="import_url_missing"), 400
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Zuhause-am-Bach-OS-iCal/1.0", "Accept": "text/calendar,text/plain,*/*"})
            with urllib.request.urlopen(req, timeout=20) as response:
                text = response.read().decode("utf-8", errors="replace")
            events = _parse_ical(text)
            source = f"{channel}_ical"
            with db() as conn:
                conn.execute("DELETE FROM external_blocks WHERE room=? AND source=?", (room, source))
                for event in events:
                    conn.execute(
                        """INSERT INTO external_blocks(room,start_date,end_date,source,uid,summary,imported_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (room, event["start"].isoformat(), event["end"].isoformat(), source,
                         event.get("uid", ""), event.get("summary", channel), _now()),
                    )
                conn.execute(
                    "UPDATE zab_channel_imports SET last_sync=?,last_result=? WHERE room=? AND channel=?",
                    (_now(), f"{len(events)} Termine importiert", room, channel),
                )
            return jsonify(ok=True, count=len(events), message="Synchronisierung erfolgreich."), 200
        except Exception as exc:
            with db() as conn:
                conn.execute(
                    "UPDATE zab_channel_imports SET last_sync=?,last_result=? WHERE room=? AND channel=?",
                    (_now(), f"Fehler: {exc}"[:900], room, channel),
                )
            return jsonify(ok=False, error="sync_failed", message=str(exc)[:700]), 502

    @app.post("/api/central/zab-calendar/sync-booking-prices")
    def zab_calendar_sync_booking_prices():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        room = str(data.get("room") or "Bachblick")
        if room not in rooms:
            return jsonify(ok=False, error="unknown_room"), 400
        try:
            start = date.fromisoformat(str(data.get("start_date") or date.today().isoformat()))
            end = date.fromisoformat(str(data.get("end_date") or (start + timedelta(days=31)).isoformat()))
            if end < start or (end - start).days > 370:
                raise ValueError
        except Exception:
            return jsonify(ok=False, error="invalid_range"), 400
        with db() as conn:
            rows = conn.execute(
                """SELECT day,price FROM zab_channel_day_settings
                   WHERE room=? AND channel='booking' AND day>=? AND day<=? AND price IS NOT NULL ORDER BY day""",
                (room, start.isoformat(), end.isoformat()),
            ).fetchall()
        results = []
        for row in rows:
            result = _sync_booking_rate(room, date.fromisoformat(row["day"]), float(row["price"]))
            results.append({"date": row["day"], **result})
        return jsonify(ok=all(r.get("ok") for r in results) if results else True, attempted=len(results), results=results), 200

    @app.get("/calendar/public/<room>.ics")
    def zab_public_direct_calendar(room: str):
        if room not in rooms:
            return "Kalender nicht gefunden", 404
        response = Response(_ical(room, "direct", public_direct=True), mimetype="text/calendar")
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Content-Disposition"] = f'inline; filename="zab-public-{room}.ics"'
        return response

    @app.get("/calendar/channel-v3/<channel>/<room>.ics")
    def zab_channel_calendar(channel: str, room: str):
        if room not in rooms or channel not in CHANNELS:
            return "Kalender nicht gefunden", 404
        expected = _feed_token()
        provided = request.args.get("token", "")
        if not expected or not provided or not hmac.compare_digest(expected, provided):
            return "Nicht autorisiert", 403
        response = Response(_ical(room, channel), mimetype="text/calendar")
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/health/zab-control-center")
    def zab_control_center_health():
        checker = app.extensions.get("zab_booking_connectivity_status")
        booking_status = checker("Bachblick") if callable(checker) else {"configured": False}
        booking_ready = bool(booking_status.get("configured"))
        payload = dict(
            ok=True,
            degraded=not booking_ready,
            version=3,
            channels=list(CHANNELS),
            rooms=[{"key": room, "label": ROOM_LABELS.get(room, room)} for room in rooms],
            booking_connectivity=booking_status,
            booking_connectivity_ready=booking_ready,
            booking_connectivity_message=(
                "Booking.com Connectivity ist vollständig konfiguriert."
                if booking_ready
                else "Booking.com Connectivity ist nicht vollständig konfiguriert; Kalender-Fallbacks bleiben aktiv."
            ),
            paypal_master_independent=bool(app.extensions.get("zab_paypal_master_independent")),
        )
        return jsonify(payload), 200

    app.extensions["zab_control_center_channels"] = CHANNELS
    app.extensions["zab_control_center_snapshot"] = _calendar_snapshot
    app.extensions["zab_control_center_v3"] = True
    return _calendar_snapshot


def make_master_checkout_sync(app, db, legacy_sync):
    """Return the checkout calendar sync used by PayPal.

    In hybrid mode the legacy Booking.com iCal safety check remains unchanged.
    In master mode the OS can become authoritative without a Booking iCal call
    when Booking is globally closed, or when ZAB_MASTER_PAYPAL_INDEPENDENT=1 is
    explicitly enabled after the operator has completed the channel migration.
    """

    def sync(room: str):
        mode = str(app.extensions.get("zab_master_calendar_mode", "hybrid"))
        explicit = os.environ.get("ZAB_MASTER_PAYPAL_INDEPENDENT", "0").strip().lower() in {"1", "true", "yes", "on"}
        booking_enabled = True
        try:
            with db() as conn:
                row = conn.execute(
                    "SELECT enabled FROM zab_channel_controls WHERE room=? AND channel='booking'",
                    (room,),
                ).fetchone()
                if row is not None:
                    booking_enabled = bool(row["enabled"])
        except Exception:
            pass
        independent = mode == "master" and (explicit or not booking_enabled)
        app.extensions["zab_paypal_master_independent"] = independent
        if not independent:
            return legacy_sync(room)

        now = _now()
        with db() as conn:
            row = conn.execute("SELECT import_url FROM ical_settings WHERE room=?", (room,)).fetchone()
            current_url = str(row["import_url"] if row else "").strip()
            marker = current_url or "zab-os-master://authoritative"
            conn.execute(
                """INSERT INTO ical_settings(room,import_url,last_sync,last_result)
                   VALUES(?,?,?,?)
                   ON CONFLICT(room) DO UPDATE SET import_url=CASE WHEN ical_settings.import_url='' THEN excluded.import_url ELSE ical_settings.import_url END,
                     last_sync=excluded.last_sync,last_result=excluded.last_result""",
                (room, marker, now, "ZAB OS Master-Kalender aktiv"),
            )
        return 0, "Synchronisierung erfolgreich."

    return sync
