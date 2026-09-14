from __future__ import annotations

import hmac
import os
import secrets
from datetime import date, datetime, timedelta

from flask import Response, flash, jsonify, redirect, render_template, request, url_for

CHANNELS = ("direct", "booking")
MASTER_MODE_VALUES = {"hybrid", "master"}


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


def init_master_calendar(app, db, require_admin, rooms):
    """Install the Zuhause-am-Bach master availability layer.

    Existing ``bookings`` remain the authoritative local reservations and
    ``external_blocks`` remain imported occupancy from Booking.com/iCal. This
    module adds OS-owned manual blocks, per-channel blocks and channel switches.

    ``ZAB_MASTER_CALENDAR_MODE=hybrid`` keeps Booking/iCal as a strict checkout
    safety dependency. ``master`` makes the OS authoritative; Booking sync then
    becomes an advisory import instead of a checkout dependency.
    """

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

    def room_available_master(conn, room: str, arrival: date, departure: date, channel: str = "direct"):
        if room not in rooms:
            return False, "Unbekanntes Zimmer."
        if channel not in CHANNELS:
            return False, "Unbekannter Verkaufskanal."
        if departure <= arrival:
            return False, "Die Abreise muss nach der Anreise liegen."
        if not _channel_enabled(conn, room, channel):
            label = "Direktbuchungen" if channel == "direct" else "Booking.com"
            return False, f"{label} sind für dieses Zimmer derzeit geschlossen."

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

        channel_blocks = conn.execute(
            """SELECT start_date, end_date FROM zab_channel_blocks
               WHERE room=? AND channel=?""",
            (room, channel),
        ).fetchall()
        for row in channel_blocks:
            if _overlaps(arrival, departure, _parse_date(row["start_date"]), _parse_date(row["end_date"])):
                label = "Direktbuchung" if channel == "direct" else "Booking.com"
                return False, f"{label} ist für diesen Zeitraum geschlossen."

        return True, "Das Zimmer ist verfügbar."

    def direct_overlay_states(room: str, first: date, next_month: date) -> dict[str, str]:
        result: dict[str, str] = {}
        if room not in rooms:
            return result
        with db() as conn:
            enabled = _channel_enabled(conn, room, "direct")
            master_blocks = conn.execute(
                "SELECT start_date, end_date FROM zab_master_blocks WHERE room=?",
                (room,),
            ).fetchall()
            direct_blocks = conn.execute(
                """SELECT start_date, end_date FROM zab_channel_blocks
                   WHERE room=? AND channel='direct'""",
                (room,),
            ).fetchall()

        if not enabled:
            current = first
            while current < next_month:
                result[current.isoformat()] = "closed"
                current += timedelta(days=1)
            return result

        for row in master_blocks:
            start, end = _parse_date(row["start_date"]), _parse_date(row["end_date"])
            current = max(first, start)
            while current < min(next_month, end):
                result[current.isoformat()] = "blocked"
                current += timedelta(days=1)
        for row in direct_blocks:
            start, end = _parse_date(row["start_date"]), _parse_date(row["end_date"])
            current = max(first, start)
            while current < min(next_month, end):
                result[current.isoformat()] = "closed"
                current += timedelta(days=1)
        return result

    def _feed_token() -> str:
        with db() as conn:
            row = conn.execute(
                "SELECT value FROM zab_calendar_meta WHERE key='feed_token'"
            ).fetchone()
        return row["value"] if row else ""

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

        with db() as conn:
            enabled = _channel_enabled(conn, room, channel)
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
            channel_blocks = conn.execute(
                """SELECT id, start_date, end_date, reason FROM zab_channel_blocks
                   WHERE room=? AND channel=? ORDER BY start_date""",
                (room, channel),
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

        if not enabled:
            horizon_start = date.today()
            horizon_end = horizon_start + timedelta(days=730)
            add_event(
                f"zab-{channel}-closed-{room}@zuhause-am-bach",
                horizon_start.isoformat(),
                horizon_end.isoformat(),
                f"Gesperrt - {channel}",
            )

        for row in local:
            add_event(
                row["uid"] or f"zab-booking-{row['id']}@zuhause-am-bach",
                row["arrival"],
                row["departure"],
                "Belegt - Zuhause am Bach",
            )
        for row in master_blocks:
            add_event(
                f"zab-master-block-{row['id']}@zuhause-am-bach",
                row["start_date"],
                row["end_date"],
                "Gesperrt - Zuhause am Bach OS",
            )
        for row in channel_blocks:
            add_event(
                f"zab-{channel}-block-{row['id']}@zuhause-am-bach",
                row["start_date"],
                row["end_date"],
                f"Gesperrt - {channel}",
            )
        for row in external:
            uid = row["uid"] or f"zab-external-{row['source']}-{row['id']}@zuhause-am-bach"
            add_event(uid, row["start_date"], row["end_date"], "Belegt - externer Kalender")

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

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
            today=date.today().isoformat(),
        )

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
        return redirect(url_for("master_calendar_dashboard"))

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
        table = {
            "master": "zab_master_blocks",
            "channel": "zab_channel_blocks",
        }.get(kind)
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
            disabled = conn.execute(
                "SELECT COUNT(*) AS n FROM zab_channel_controls WHERE enabled=0"
            ).fetchone()["n"]
        return jsonify(
            ok=True,
            mode=mode,
            authoritative=mode == "master",
            master_blocks=int(blocks or 0),
            channel_blocks=int(channel_blocks or 0),
            disabled_channels=int(disabled or 0),
        )

    app.extensions["zab_master_room_available"] = room_available_master
    app.extensions["zab_master_direct_states"] = direct_overlay_states
    app.extensions["zab_master_calendar_ical_text"] = ical_text
    app.extensions["zab_master_calendar_mode"] = mode
    app.extensions["zab_master_calendar_authoritative"] = mode == "master"
    app.extensions["zab_master_calendar_initialized"] = True
