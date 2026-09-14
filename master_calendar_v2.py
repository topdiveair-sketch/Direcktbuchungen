from __future__ import annotations

import hmac
import os
import secrets
from datetime import date, datetime, timedelta

from flask import Response, flash, jsonify, redirect, render_template, request, url_for

try:
    from pricing_2027 import nightly_direct_rate
except Exception:  # pragma: no cover - local fallback only
    nightly_direct_rate = None

CHANNELS = ("direct", "booking")
MASTER_MODE_VALUES = {"hybrid", "master"}
COUNTRY_CODE_MAP = {
    "österreich": "AT", "austria": "AT", "at": "AT",
    "deutschland": "DE", "germany": "DE", "de": "DE",
    "schweiz": "CH", "switzerland": "CH", "ch": "CH",
    "frankreich": "FR", "france": "FR", "fr": "FR",
    "italien": "IT", "italy": "IT", "it": "IT",
    "niederlande": "NL", "netherlands": "NL", "holland": "NL", "nl": "NL",
    "belgien": "BE", "belgium": "BE", "be": "BE",
    "tschechien": "CZ", "czechia": "CZ", "czech republic": "CZ", "cz": "CZ",
    "slowakei": "SK", "slovakia": "SK", "sk": "SK",
    "ungarn": "HU", "hungary": "HU", "hu": "HU",
    "polen": "PL", "poland": "PL", "pl": "PL",
    "spanien": "ES", "spain": "ES", "es": "ES",
    "portugal": "PT", "pt": "PT",
    "großbritannien": "GB", "vereinigtes königreich": "GB", "united kingdom": "GB", "uk": "GB", "gb": "GB",
    "usa": "US", "united states": "US", "vereinigte staaten": "US", "us": "US",
    "kanada": "CA", "canada": "CA", "ca": "CA",
    "australien": "AU", "australia": "AU", "au": "AU",
    "schweden": "SE", "sweden": "SE", "se": "SE",
    "norwegen": "NO", "norway": "NO", "no": "NO",
    "dänemark": "DK", "denmark": "DK", "dk": "DK",
    "finnland": "FI", "finland": "FI", "fi": "FI",
    "irland": "IE", "ireland": "IE", "ie": "IE",
    "luxemburg": "LU", "luxembourg": "LU", "lu": "LU",
    "slowenien": "SI", "slovenia": "SI", "si": "SI",
    "kroatien": "HR", "croatia": "HR", "hr": "HR",
    "rumänien": "RO", "romania": "RO", "ro": "RO",
    "bulgarien": "BG", "bulgaria": "BG", "bg": "BG",
    "griechenland": "GR", "greece": "GR", "gr": "GR",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start < b_end and b_start < a_end


def _ical_escape(value: str) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _country_flag(country: str) -> str:
    raw = (country or "").strip()
    if not raw:
        return ""
    code = COUNTRY_CODE_MAP.get(raw.casefold(), "")
    if not code and len(raw) == 2 and raw.isalpha():
        code = raw.upper()
    if len(code) == 2 and code.isalpha():
        return "".join(chr(127397 + ord(char)) for char in code.upper())
    return "🌍"


def _country_label(country: str) -> str:
    raw = (country or "").strip()
    if not raw:
        return ""
    flag = _country_flag(raw)
    return f"{flag} {raw}".strip()


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return first, next_month


def _calendar_grid_bounds(first: date, next_month: date) -> tuple[date, date]:
    grid_start = first - timedelta(days=first.weekday())
    last = next_month - timedelta(days=1)
    grid_end = last + timedelta(days=(6 - last.weekday()) + 1)
    return grid_start, grid_end


def init_master_calendar(app, db, require_admin, rooms):
    """Install the ZAB master calendar, channel controls and internal guest view."""

    mode = os.environ.get("ZAB_MASTER_CALENDAR_MODE", "hybrid").strip().lower()
    if mode not in MASTER_MODE_VALUES:
        mode = "hybrid"

    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS zab_calendar_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zab_channel_controls (
                room TEXT NOT NULL,
                channel TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(room, channel)
            );

            CREATE TABLE IF NOT EXISTS zab_master_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT 'Manuell gesperrt',
                source TEXT NOT NULL DEFAULT 'zab_os',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_zab_master_blocks_room_dates
                ON zab_master_blocks(room, start_date, end_date);

            CREATE TABLE IF NOT EXISTS zab_channel_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT NOT NULL,
                channel TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT 'Kanal gesperrt',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_zab_channel_blocks_room_channel_dates
                ON zab_channel_blocks(room, channel, start_date, end_date);

            CREATE TABLE IF NOT EXISTS zab_channel_day_settings (
                room TEXT NOT NULL,
                day TEXT NOT NULL,
                channel TEXT NOT NULL,
                enabled_override INTEGER,
                price REAL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(room, day, channel)
            );
            CREATE INDEX IF NOT EXISTS ix_zab_channel_day_settings_room_day
                ON zab_channel_day_settings(room, day);

            CREATE TABLE IF NOT EXISTS zab_external_guest_meta (
                room TEXT NOT NULL,
                source TEXT NOT NULL,
                uid TEXT NOT NULL DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                guest_name TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                guests INTEGER,
                booking_reference TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(room, source, uid, start_date, end_date)
            );
            """
        )
        now = _now()
        for room in rooms:
            for channel in CHANNELS:
                conn.execute(
                    """INSERT OR IGNORE INTO zab_channel_controls
                       (room, channel, enabled, updated_at) VALUES (?, ?, 1, ?)""",
                    (room, channel, now),
                )
        token_row = conn.execute(
            "SELECT value FROM zab_calendar_meta WHERE key='feed_token'"
        ).fetchone()
        if not token_row:
            conn.execute(
                "INSERT INTO zab_calendar_meta(key, value) VALUES('feed_token', ?)",
                (secrets.token_urlsafe(32),),
            )

    def _channel_enabled(conn, room: str, channel: str) -> bool:
        row = conn.execute(
            "SELECT enabled FROM zab_channel_controls WHERE room=? AND channel=?",
            (room, channel),
        ).fetchone()
        return True if row is None else bool(row["enabled"])

    def _day_setting(conn, room: str, channel: str, day: date):
        return conn.execute(
            """SELECT enabled_override, price FROM zab_channel_day_settings
               WHERE room=? AND channel=? AND day=?""",
            (room, channel, day.isoformat()),
        ).fetchone()

    def _channel_open_for_day(conn, room: str, channel: str, day: date) -> bool:
        setting = _day_setting(conn, room, channel, day)
        if setting is not None and setting["enabled_override"] is not None:
            return bool(setting["enabled_override"])
        if not _channel_enabled(conn, room, channel):
            return False
        blocked = conn.execute(
            """SELECT 1 FROM zab_channel_blocks
               WHERE room=? AND channel=? AND start_date<=? AND end_date>?
               LIMIT 1""",
            (room, channel, day.isoformat(), day.isoformat()),
        ).fetchone()
        return not bool(blocked)

    def _base_direct_price(room: str, day: date) -> float | None:
        if room == "Bachblick" and nightly_direct_rate is not None:
            try:
                rate = nightly_direct_rate(day)
            except Exception:
                rate = None
            if rate is not None:
                return float(rate)
        try:
            return float(rooms[room].get("price"))
        except Exception:
            return None

    def channel_price_for_day(room: str, channel: str, day: date, fallback=None):
        if room not in rooms or channel not in CHANNELS:
            return fallback
        with db() as conn:
            row = _day_setting(conn, room, channel, day)
        if row is not None and row["price"] is not None:
            return float(row["price"])
        return fallback

    def room_available_master(conn, room: str, arrival: date, departure: date, channel: str = "direct"):
        if room not in rooms:
            return False, "Unbekanntes Zimmer."
        if channel not in CHANNELS:
            return False, "Unbekannter Verkaufskanal."
        if departure <= arrival:
            return False, "Die Abreise muss nach der Anreise liegen."

        local = conn.execute(
            """SELECT arrival, departure FROM bookings
               WHERE room=? AND status IN ('pending','confirmed')""",
            (room,),
        ).fetchall()
        for row in local:
            if _overlaps(arrival, departure, _parse_date(row["arrival"]), _parse_date(row["departure"])):
                return False, "Das Zimmer ist durch eine Direktbuchung belegt."

        external = conn.execute(
            "SELECT start_date, end_date, source FROM external_blocks WHERE room=?",
            (room,),
        ).fetchall()
        for row in external:
            if _overlaps(arrival, departure, _parse_date(row["start_date"]), _parse_date(row["end_date"])):
                if row["source"] == "booking_ical":
                    return False, "Das Zimmer ist über Booking.com/iCal belegt."
                return False, "Das Zimmer ist durch einen externen Kalender belegt."

        master_blocks = conn.execute(
            "SELECT start_date, end_date FROM zab_master_blocks WHERE room=?",
            (room,),
        ).fetchall()
        for row in master_blocks:
            if _overlaps(arrival, departure, _parse_date(row["start_date"]), _parse_date(row["end_date"])):
                return False, "Das Zimmer ist im Zuhause-am-Bach-OS gesperrt."

        current = arrival
        while current < departure:
            if not _channel_open_for_day(conn, room, channel, current):
                label = "Direktbuchung" if channel == "direct" else "Booking.com"
                return False, f"{label} ist am {current.strftime('%d.%m.%Y')} geschlossen."
            current += timedelta(days=1)

        return True, "Das Zimmer ist verfügbar."

    def direct_overlay_states(room: str, first: date, next_month: date) -> dict[str, str]:
        result: dict[str, str] = {}
        if room not in rooms:
            return result
        with db() as conn:
            master_blocks = conn.execute(
                "SELECT start_date, end_date FROM zab_master_blocks WHERE room=?",
                (room,),
            ).fetchall()
            current = first
            while current < next_month:
                if not _channel_open_for_day(conn, room, "direct", current):
                    result[current.isoformat()] = "closed"
                current += timedelta(days=1)
        for row in master_blocks:
            start, end = _parse_date(row["start_date"]), _parse_date(row["end_date"])
            current = max(first, start)
            while current < min(next_month, end):
                result[current.isoformat()] = "blocked"
                current += timedelta(days=1)
        return result

    def _feed_token() -> str:
        with db() as conn:
            row = conn.execute(
                "SELECT value FROM zab_calendar_meta WHERE key='feed_token'"
            ).fetchone()
        return row["value"] if row else ""

    def _closed_intervals(conn, room: str, channel: str, start: date, end: date):
        intervals = []
        open_start = None
        current = start
        while current < end:
            closed = not _channel_open_for_day(conn, room, channel, current)
            if closed and open_start is None:
                open_start = current
            elif not closed and open_start is not None:
                intervals.append((open_start, current))
                open_start = None
            current += timedelta(days=1)
        if open_start is not None:
            intervals.append((open_start, end))
        return intervals

    def ical_text(room: str, channel: str) -> str:
        if room not in rooms:
            raise KeyError(room)
        if channel not in CHANNELS:
            raise KeyError(channel)

        release_expired = app.extensions.get("zab_release_expired_holds")
        if release_expired:
            try:
                release_expired()
            except Exception:
                pass

        horizon_start = date.today()
        horizon_end = horizon_start + timedelta(days=730)
        with db() as conn:
            local = conn.execute(
                """SELECT id, uid, arrival, departure FROM bookings
                   WHERE room=? AND status IN ('pending','confirmed')
                   ORDER BY arrival""",
                (room,),
            ).fetchall()
            master_blocks = conn.execute(
                """SELECT id, start_date, end_date, reason FROM zab_master_blocks
                   WHERE room=? ORDER BY start_date""",
                (room,),
            ).fetchall()
            if channel == "booking":
                external = conn.execute(
                    """SELECT id, start_date, end_date, source, uid FROM external_blocks
                       WHERE room=? AND source!='booking_ical' ORDER BY start_date""",
                    (room,),
                ).fetchall()
            else:
                external = conn.execute(
                    """SELECT id, start_date, end_date, source, uid FROM external_blocks
                       WHERE room=? ORDER BY start_date""",
                    (room,),
                ).fetchall()
            closed_intervals = _closed_intervals(conn, room, channel, horizon_start, horizon_end)

        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Zuhause am Bach//Master Calendar//DE",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:ZAB {room} {channel}",
        ]

        def add_event(uid: str, start: str, end: str, summary: str):
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{_ical_escape(uid)}",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART;VALUE=DATE:{_parse_date(start).strftime('%Y%m%d')}",
                    f"DTEND;VALUE=DATE:{_parse_date(end).strftime('%Y%m%d')}",
                    f"SUMMARY:{_ical_escape(summary)}",
                    "TRANSP:OPAQUE",
                    "END:VEVENT",
                ]
            )

        for row in local:
            add_event(
                row["uid"] or f"zab-booking-{row['id']}@zuhause-am-bach",
                row["arrival"], row["departure"], "Belegt - Zuhause am Bach",
            )
        for row in master_blocks:
            add_event(
                f"zab-master-block-{row['id']}@zuhause-am-bach",
                row["start_date"], row["end_date"], "Gesperrt - Zuhause am Bach OS",
            )
        for row in external:
            uid = row["uid"] or f"zab-external-{row['source']}-{row['id']}@zuhause-am-bach"
            add_event(uid, row["start_date"], row["end_date"], "Belegt - externer Kalender")
        for index, (start, end) in enumerate(closed_intervals, start=1):
            add_event(
                f"zab-{channel}-closed-{room}-{index}-{start.isoformat()}@zuhause-am-bach",
                start.isoformat(), end.isoformat(), f"Gesperrt - {channel}",
            )

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    def _external_meta_key(row):
        return (
            row["room"], row["source"], row["uid"] or "",
            row["start_date"], row["end_date"],
        )

    def _build_calendar_month(year: int, month: int):
        first, next_month = _month_bounds(year, month)
        grid_start, grid_end = _calendar_grid_bounds(first, next_month)
        with db() as conn:
            direct_rows = conn.execute(
                """SELECT b.id,b.room,b.arrival,b.departure,b.first_name,b.last_name,b.email,
                          b.adults,b.total,b.status,COALESCE(g.country,'') AS country
                   FROM bookings b
                   LEFT JOIN guest_profiles g ON lower(g.email)=lower(b.email)
                   WHERE b.status IN ('pending','confirmed')
                     AND b.arrival<? AND b.departure>?
                   ORDER BY b.arrival,b.room""",
                (grid_end.isoformat(), grid_start.isoformat()),
            ).fetchall()
            external_rows = conn.execute(
                """SELECT id,room,start_date,end_date,source,uid,summary
                   FROM external_blocks
                   WHERE start_date<? AND end_date>?
                   ORDER BY start_date,room""",
                (grid_end.isoformat(), grid_start.isoformat()),
            ).fetchall()
            meta_rows = conn.execute(
                "SELECT * FROM zab_external_guest_meta"
            ).fetchall()
            master_rows = conn.execute(
                """SELECT room,start_date,end_date,reason FROM zab_master_blocks
                   WHERE start_date<? AND end_date>?""",
                (grid_end.isoformat(), grid_start.isoformat()),
            ).fetchall()

        meta = {
            (r["room"], r["source"], r["uid"] or "", r["start_date"], r["end_date"]): dict(r)
            for r in meta_rows
        }
        by_room = {}
        for room in rooms:
            days = []
            current = grid_start
            while current < grid_end:
                occupancy = []
                for row in direct_rows:
                    if row["room"] != room:
                        continue
                    if _parse_date(row["arrival"]) <= current < _parse_date(row["departure"]):
                        country = row["country"] or ""
                        occupancy.append({
                            "kind": "direct",
                            "label": "Direkt",
                            "booking_id": row["id"],
                            "arrival": row["arrival"],
                            "departure": row["departure"],
                            "is_arrival": current.isoformat() == row["arrival"],
                            "guest_name": f"{row['first_name']} {row['last_name']}".strip(),
                            "country": country,
                            "country_label": _country_label(country),
                            "guests": int(row["adults"] or 0),
                            "total": float(row["total"] or 0),
                            "email": row["email"] or "",
                            "status": row["status"],
                        })
                for row in external_rows:
                    if row["room"] != room:
                        continue
                    if _parse_date(row["start_date"]) <= current < _parse_date(row["end_date"]):
                        info = meta.get(_external_meta_key(row), {})
                        country = info.get("country", "") or ""
                        occupancy.append({
                            "kind": "booking" if row["source"] == "booking_ical" else "external",
                            "label": "Booking.com" if row["source"] == "booking_ical" else "Extern",
                            "external_id": row["id"],
                            "room": row["room"],
                            "source": row["source"],
                            "uid": row["uid"] or "",
                            "arrival": row["start_date"],
                            "departure": row["end_date"],
                            "is_arrival": current.isoformat() == row["start_date"],
                            "guest_name": info.get("guest_name", "") or "",
                            "country": country,
                            "country_label": _country_label(country),
                            "guests": info.get("guests"),
                            "booking_reference": info.get("booking_reference", "") or "",
                        })
                master_reason = ""
                for row in master_rows:
                    if row["room"] == room and _parse_date(row["start_date"]) <= current < _parse_date(row["end_date"]):
                        master_reason = row["reason"] or "OS-Sperre"
                        break
                with db() as conn:
                    direct_open = _channel_open_for_day(conn, room, "direct", current)
                    booking_open = _channel_open_for_day(conn, room, "booking", current)
                    direct_setting = _day_setting(conn, room, "direct", current)
                    booking_setting = _day_setting(conn, room, "booking", current)
                base_direct = _base_direct_price(room, current)
                direct_price = (
                    float(direct_setting["price"])
                    if direct_setting is not None and direct_setting["price"] is not None
                    else base_direct
                )
                booking_price = (
                    float(booking_setting["price"])
                    if booking_setting is not None and booking_setting["price"] is not None
                    else None
                )
                days.append({
                    "date": current.isoformat(),
                    "day": current.day,
                    "in_month": current.month == month,
                    "today": current == date.today(),
                    "occupancy": occupancy,
                    "master_reason": master_reason,
                    "direct_open": direct_open,
                    "booking_open": booking_open,
                    "direct_price": direct_price,
                    "booking_price": booking_price,
                    "direct_price_override": direct_setting is not None and direct_setting["price"] is not None,
                    "booking_price_override": booking_setting is not None and booking_setting["price"] is not None,
                })
                current += timedelta(days=1)
            by_room[room] = days
        return by_room, grid_start, grid_end

    @app.get("/calendar/channel/<channel>/<room>.ics")
    def master_calendar_feed(channel: str, room: str):
        if room not in rooms or channel not in CHANNELS:
            return "Kalender nicht gefunden", 404
        expected = _feed_token()
        provided = request.args.get("token", "")
        if not expected or not provided or not hmac.compare_digest(expected, provided):
            return "Nicht autorisiert", 403
        response = Response(ical_text(room, channel), mimetype="text/calendar")
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Content-Disposition"] = f'inline; filename="zab-{channel}-{room}.ics"'
        return response

    @app.get("/os/calendar")
    def master_calendar_dashboard():
        if not require_admin():
            return redirect(url_for("admin_login"))
        today = date.today()
        try:
            year = int(request.args.get("year", today.year))
            month = int(request.args.get("month", today.month))
            if not 1 <= month <= 12:
                raise ValueError
        except (TypeError, ValueError):
            year, month = today.year, today.month

        first, next_month = _month_bounds(year, month)
        prev_month_date = first - timedelta(days=1)
        next_month_date = next_month
        calendar_rooms, _, _ = _build_calendar_month(year, month)

        with db() as conn:
            controls = {
                (row["room"], row["channel"]): dict(row)
                for row in conn.execute(
                    "SELECT * FROM zab_channel_controls ORDER BY room, channel"
                )
            }
            master_blocks = conn.execute(
                "SELECT * FROM zab_master_blocks ORDER BY start_date, room"
            ).fetchall()
            channel_blocks = conn.execute(
                "SELECT * FROM zab_channel_blocks ORDER BY start_date, room, channel"
            ).fetchall()
            imports = conn.execute(
                "SELECT room, import_url, last_sync, last_result FROM ical_settings ORDER BY room"
            ).fetchall()
            external_counts = {
                row["room"]: int(row["n"])
                for row in conn.execute(
                    "SELECT room, COUNT(*) AS n FROM external_blocks GROUP BY room"
                )
            }

        token = _feed_token()
        base = request.url_root.rstrip("/")
        feeds = {
            room: {
                channel: f"{base}/calendar/channel/{channel}/{room}.ics?token={token}"
                for channel in CHANNELS
            }
            for room in rooms
        }

        edit_room = request.args.get("room", "")
        edit_day_raw = request.args.get("edit", "")
        selected = None
        if edit_room in rooms:
            for cell in calendar_rooms.get(edit_room, []):
                if cell["date"] == edit_day_raw:
                    selected = cell
                    break

        return render_template(
            "master_calendar.html",
            rooms=rooms,
            channels=CHANNELS,
            controls=controls,
            master_blocks=master_blocks,
            channel_blocks=channel_blocks,
            imports=imports,
            external_counts=external_counts,
            feeds=feeds,
            mode=mode,
            authoritative=mode == "master",
            today=today.isoformat(),
            calendar_rooms=calendar_rooms,
            year=year,
            month=month,
            month_label=first.strftime("%m/%Y"),
            prev_year=prev_month_date.year,
            prev_month=prev_month_date.month,
            next_year=next_month_date.year,
            next_month=next_month_date.month,
            edit_room=edit_room,
            edit_day=edit_day_raw,
            selected=selected,
        )

    @app.post("/os/calendar/day")
    def master_calendar_day_update():
        if not require_admin():
            return redirect(url_for("admin_login"))
        room = request.form.get("room", "")
        if room not in rooms:
            return "Ungültiges Zimmer", 400
        try:
            start = _parse_date(request.form.get("start_date", ""))
            end = _parse_date(request.form.get("end_date", ""))
        except ValueError:
            flash("Bitte gültige Datumswerte eingeben.", "error")
            return redirect(url_for("master_calendar_dashboard"))
        if end < start or (end - start).days > 730:
            flash("Der Zeitraum ist ungültig oder zu lang.", "error")
            return redirect(url_for("master_calendar_dashboard"))

        status_values = {"keep", "open", "closed", "reset"}
        direct_status = request.form.get("direct_status", "keep")
        booking_status = request.form.get("booking_status", "keep")
        if direct_status not in status_values or booking_status not in status_values:
            return "Ungültiger Status", 400

        def parsed_price(field: str):
            raw = (request.form.get(field, "") or "").strip().replace(",", ".")
            if not raw:
                return None, False
            try:
                value = float(raw)
            except ValueError:
                raise ValueError("Preis muss eine Zahl sein.")
            if value < 0 or value > 10000:
                raise ValueError("Preis außerhalb des zulässigen Bereichs.")
            return round(value, 2), True

        try:
            direct_price, direct_price_changed = parsed_price("direct_price")
            booking_price, booking_price_changed = parsed_price("booking_price")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("master_calendar_dashboard"))

        clear_direct = request.form.get("clear_direct_price") == "1"
        clear_booking = request.form.get("clear_booking_price") == "1"
        now = _now()
        with db() as conn:
            current = start
            while current <= end:
                for channel, status, price, changed, clear in (
                    ("direct", direct_status, direct_price, direct_price_changed, clear_direct),
                    ("booking", booking_status, booking_price, booking_price_changed, clear_booking),
                ):
                    row = conn.execute(
                        """SELECT enabled_override,price FROM zab_channel_day_settings
                           WHERE room=? AND day=? AND channel=?""",
                        (room, current.isoformat(), channel),
                    ).fetchone()
                    enabled_override = row["enabled_override"] if row else None
                    stored_price = row["price"] if row else None
                    if status == "open":
                        enabled_override = 1
                    elif status == "closed":
                        enabled_override = 0
                    elif status == "reset":
                        enabled_override = None
                    if clear:
                        stored_price = None
                    elif changed:
                        stored_price = price
                    if enabled_override is None and stored_price is None:
                        conn.execute(
                            "DELETE FROM zab_channel_day_settings WHERE room=? AND day=? AND channel=?",
                            (room, current.isoformat(), channel),
                        )
                    else:
                        conn.execute(
                            """INSERT INTO zab_channel_day_settings
                               (room,day,channel,enabled_override,price,updated_at)
                               VALUES(?,?,?,?,?,?)
                               ON CONFLICT(room,day,channel) DO UPDATE SET
                                 enabled_override=excluded.enabled_override,
                                 price=excluded.price,
                                 updated_at=excluded.updated_at""",
                            (room, current.isoformat(), channel, enabled_override, stored_price, now),
                        )
                current += timedelta(days=1)
        flash(f"Kalendereinstellungen für {room} gespeichert.", "success")
        return redirect(url_for(
            "master_calendar_dashboard",
            year=start.year, month=start.month, room=room, edit=start.isoformat()
        ) + "#day-editor")

    @app.post("/os/calendar/direct-country")
    def master_calendar_direct_country_update():
        if not require_admin():
            return redirect(url_for("admin_login"))
        booking_id = request.form.get("booking_id", type=int)
        country = (request.form.get("country", "") or "").strip()[:120]
        with db() as conn:
            booking = conn.execute(
                "SELECT id,email,first_name,last_name,phone,room,departure FROM bookings WHERE id=?",
                (booking_id,),
            ).fetchone()
            if not booking:
                return "Buchung nicht gefunden", 404
            now = _now()
            conn.execute(
                """INSERT INTO guest_profiles
                   (email,first_name,last_name,phone,country,preferred_room,stays,total_revenue,last_stay,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,0,0,?,?,?)
                   ON CONFLICT(email) DO UPDATE SET
                     country=excluded.country,
                     first_name=CASE WHEN guest_profiles.first_name='' THEN excluded.first_name ELSE guest_profiles.first_name END,
                     last_name=CASE WHEN guest_profiles.last_name='' THEN excluded.last_name ELSE guest_profiles.last_name END,
                     phone=CASE WHEN guest_profiles.phone='' THEN excluded.phone ELSE guest_profiles.phone END,
                     updated_at=excluded.updated_at""",
                (
                    booking["email"], booking["first_name"], booking["last_name"], booking["phone"],
                    country, booking["room"], booking["departure"], now, now,
                ),
            )
        return redirect(request.form.get("return_to") or url_for("master_calendar_dashboard"))

    @app.post("/os/calendar/external-guest")
    def master_calendar_external_guest_update():
        if not require_admin():
            return redirect(url_for("admin_login"))
        room = request.form.get("room", "")
        source = (request.form.get("source", "") or "")[:80]
        uid = (request.form.get("uid", "") or "")[:500]
        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")
        if room not in rooms:
            return "Ungültiges Zimmer", 400
        try:
            start = _parse_date(start_date)
            end = _parse_date(end_date)
        except ValueError:
            return "Ungültige Datumswerte", 400
        if end <= start:
            return "Ungültiger Zeitraum", 400
        guest_name = (request.form.get("guest_name", "") or "").strip()[:200]
        country = (request.form.get("country", "") or "").strip()[:120]
        booking_reference = (request.form.get("booking_reference", "") or "").strip()[:160]
        raw_guests = (request.form.get("guests", "") or "").strip()
        guests = None
        if raw_guests:
            try:
                guests = max(1, min(30, int(raw_guests)))
            except ValueError:
                return "Ungültige Gästezahl", 400
        with db() as conn:
            conn.execute(
                """INSERT INTO zab_external_guest_meta
                   (room,source,uid,start_date,end_date,guest_name,country,guests,booking_reference,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(room,source,uid,start_date,end_date) DO UPDATE SET
                     guest_name=excluded.guest_name,
                     country=excluded.country,
                     guests=excluded.guests,
                     booking_reference=excluded.booking_reference,
                     updated_at=excluded.updated_at""",
                (
                    room, source, uid, start.isoformat(), end.isoformat(), guest_name,
                    country, guests, booking_reference, _now(),
                ),
            )
        return redirect(request.form.get("return_to") or url_for("master_calendar_dashboard"))

    @app.post("/os/calendar/channel")
    def master_calendar_channel_update():
        if not require_admin():
            return redirect(url_for("admin_login"))
        room = request.form.get("room", "")
        channel = request.form.get("channel", "")
        enabled = request.form.get("enabled", "1") == "1"
        if room not in rooms or channel not in CHANNELS:
            return "Ungültiger Kanal", 400
        with db() as conn:
            conn.execute(
                """INSERT INTO zab_channel_controls(room, channel, enabled, updated_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(room,channel) DO UPDATE SET
                     enabled=excluded.enabled, updated_at=excluded.updated_at""",
                (room, channel, 1 if enabled else 0, _now()),
            )
        flash(f"{room}: {channel} {'geöffnet' if enabled else 'geschlossen'}.", "success")
        return redirect(request.form.get("return_to") or url_for("master_calendar_dashboard"))

    @app.post("/os/calendar/block")
    def master_calendar_add_block():
        if not require_admin():
            return redirect(url_for("admin_login"))
        room = request.form.get("room", "")
        channel = request.form.get("channel", "all")
        reason = (request.form.get("reason", "") or "Manuell gesperrt").strip()[:240]
        start_raw = request.form.get("start_date", "")
        end_raw = request.form.get("end_date", "")
        if room not in rooms or channel not in (*CHANNELS, "all"):
            return "Ungültige Sperre", 400
        try:
            start = _parse_date(start_raw)
            end = _parse_date(end_raw)
        except ValueError:
            flash("Bitte gültige Datumswerte eingeben.", "error")
            return redirect(url_for("master_calendar_dashboard"))
        if end <= start:
            flash("Das Enddatum muss nach dem Startdatum liegen.", "error")
            return redirect(url_for("master_calendar_dashboard"))
        with db() as conn:
            if channel == "all":
                conn.execute(
                    """INSERT INTO zab_master_blocks
                       (room,start_date,end_date,reason,source,created_at)
                       VALUES(?,?,?,?, 'zab_os', ?)""",
                    (room, start.isoformat(), end.isoformat(), reason, _now()),
                )
            else:
                conn.execute(
                    """INSERT INTO zab_channel_blocks
                       (room,channel,start_date,end_date,reason,created_at)
                       VALUES(?,?,?,?,?,?)""",
                    (room, channel, start.isoformat(), end.isoformat(), reason, _now()),
                )
        flash("Kalendersperre angelegt.", "success")
        return redirect(url_for("master_calendar_dashboard"))

    @app.post("/os/calendar/block/<kind>/<int:block_id>/delete")
    def master_calendar_delete_block(kind: str, block_id: int):
        if not require_admin():
            return redirect(url_for("admin_login"))
        table = {"master": "zab_master_blocks", "channel": "zab_channel_blocks"}.get(kind)
        if not table:
            return "Ungültige Sperre", 400
        with db() as conn:
            conn.execute(f"DELETE FROM {table} WHERE id=?", (block_id,))
        flash("Kalendersperre entfernt.", "success")
        return redirect(url_for("master_calendar_dashboard"))

    @app.post("/os/calendar/sync")
    def master_calendar_sync_imports():
        if not require_admin():
            return redirect(url_for("admin_login"))
        sync = app.extensions.get("zab_sync_room")
        if not sync:
            flash("Booking/iCal-Synchronisierung ist nicht verfügbar.", "error")
            return redirect(url_for("master_calendar_dashboard"))
        messages = []
        for room in rooms:
            count, message = sync(room)
            messages.append(f"{room}: {count} ({message})")
        flash(" · ".join(messages), "success")
        return redirect(url_for("master_calendar_dashboard"))

    @app.get("/health/master-calendar")
    def master_calendar_health():
        with db() as conn:
            blocks = conn.execute("SELECT COUNT(*) AS n FROM zab_master_blocks").fetchone()["n"]
            channel_blocks = conn.execute("SELECT COUNT(*) AS n FROM zab_channel_blocks").fetchone()["n"]
            day_settings = conn.execute("SELECT COUNT(*) AS n FROM zab_channel_day_settings").fetchone()["n"]
            guest_meta = conn.execute("SELECT COUNT(*) AS n FROM zab_external_guest_meta").fetchone()["n"]
            disabled = conn.execute(
                "SELECT COUNT(*) AS n FROM zab_channel_controls WHERE enabled=0"
            ).fetchone()["n"]
        return jsonify(
            ok=True,
            mode=mode,
            authoritative=mode == "master",
            master_blocks=int(blocks or 0),
            channel_blocks=int(channel_blocks or 0),
            day_settings=int(day_settings or 0),
            enriched_external_guests=int(guest_meta or 0),
            disabled_channels=int(disabled or 0),
        )

    app.extensions["zab_master_room_available"] = room_available_master
    app.extensions["zab_master_direct_states"] = direct_overlay_states
    app.extensions["zab_master_calendar_ical_text"] = ical_text
    app.extensions["zab_channel_price_for_day"] = channel_price_for_day
    app.extensions["zab_master_calendar_mode"] = mode
    app.extensions["zab_master_calendar_authoritative"] = mode == "master"
    app.extensions["zab_master_calendar_initialized"] = True
