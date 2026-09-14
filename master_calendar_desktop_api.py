from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import jsonify, request

CHANNELS = ("direct", "booking")


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return first, next_month


def _as_bool_or_none(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"", "inherit", "standard", "default", "none", "null"}:
        return None
    if text in {"1", "true", "yes", "on", "open", "offen"}:
        return True
    if text in {"0", "false", "no", "off", "closed", "geschlossen"}:
        return False
    raise ValueError("Ungültiger Kanalstatus")


def _as_price_or_none(value):
    if value is None or str(value).strip() == "":
        return None
    price = float(str(value).replace(",", "."))
    if price < 0 or price > 10000:
        raise ValueError("Ungültiger Preis")
    return round(price, 2)


def init_master_calendar_desktop_api(app, db, rooms, authorize, direct_rate_fn=None):
    """Authenticated JSON bridge used by the local Windows ZAB OS.

    The desktop client can read one month and write per-day channel/price
    overrides. It never exposes guest contact details.
    """

    def _authorized():
        try:
            return bool(authorize())
        except Exception:
            return False

    def _table_columns(conn, table: str) -> set[str]:
        try:
            return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
        except Exception:
            return set()

    def _global_enabled(conn, room: str, channel: str) -> bool:
        row = conn.execute(
            "SELECT enabled FROM zab_channel_controls WHERE room=? AND channel=?",
            (room, channel),
        ).fetchone()
        return True if row is None else bool(row["enabled"])

    def _day_row(conn, room: str, channel: str, day: date):
        return conn.execute(
            """SELECT enabled_override, price FROM zab_channel_day_settings
               WHERE room=? AND channel=? AND day=?""",
            (room, channel, day.isoformat()),
        ).fetchone()

    def _channel_open(conn, room: str, channel: str, day: date) -> bool:
        setting = _day_row(conn, room, channel, day)
        if setting is not None and setting["enabled_override"] is not None:
            return bool(setting["enabled_override"])
        if not _global_enabled(conn, room, channel):
            return False
        blocked = conn.execute(
            """SELECT 1 FROM zab_channel_blocks
               WHERE room=? AND channel=? AND start_date<=? AND end_date>?
               LIMIT 1""",
            (room, channel, day.isoformat(), day.isoformat()),
        ).fetchone()
        return not bool(blocked)

    def _base_direct_price(room: str, day: date):
        if room == "Bachblick" and callable(direct_rate_fn):
            try:
                value = direct_rate_fn(day)
            except Exception:
                value = None
            if value is not None:
                return float(value)
        try:
            return float(rooms[room].get("price"))
        except Exception:
            return None

    def _effective_direct_price(conn, room: str, day: date):
        setting = _day_row(conn, room, "direct", day)
        if setting is not None and setting["price"] is not None:
            return float(setting["price"]), True
        return _base_direct_price(room, day), False

    def _booking_target_price(conn, room: str, day: date):
        setting = _day_row(conn, room, "booking", day)
        if setting is not None and setting["price"] is not None:
            return float(setting["price"]), True
        return None, False

    def _occupancy_rows(conn, start: date, end: date):
        out = []
        bcols = _table_columns(conn, "bookings")
        if bcols:
            cols = [
                "id", "room", "arrival", "departure", "status", "uid",
                "first_name", "last_name", "adults", "total",
            ]
            for optional in ("country", "nationality", "source"):
                if optional in bcols:
                    cols.append(optional)
            sql = (
                "SELECT " + ",".join(cols) + " FROM bookings "
                "WHERE status IN ('pending','confirmed') AND arrival<? AND departure>?"
            )
            try:
                rows = conn.execute(sql, (end.isoformat(), start.isoformat())).fetchall()
            except Exception:
                rows = []
            for row in rows:
                data = dict(row)
                country = str(data.get("country") or data.get("nationality") or "").strip()
                guest = " ".join(
                    part for part in (
                        str(data.get("first_name") or "").strip(),
                        str(data.get("last_name") or "").strip(),
                    ) if part
                ).strip()
                out.append({
                    "kind": "direct",
                    "id": str(data.get("id") or ""),
                    "uid": str(data.get("uid") or ""),
                    "room": str(data.get("room") or ""),
                    "arrival": str(data.get("arrival") or ""),
                    "departure": str(data.get("departure") or ""),
                    "guest_name": guest,
                    "country": country,
                    "guests": int(data.get("adults") or 0),
                    "source": str(data.get("source") or "direct"),
                })

        try:
            external = conn.execute(
                """SELECT id,room,start_date,end_date,source,uid,summary
                   FROM external_blocks
                   WHERE start_date<? AND end_date>?""",
                (end.isoformat(), start.isoformat()),
            ).fetchall()
        except Exception:
            external = []
        for row in external:
            data = dict(row)
            meta = conn.execute(
                """SELECT guest_name,country,guests,booking_reference
                   FROM zab_external_guest_meta
                   WHERE room=? AND source=? AND uid=? AND start_date=? AND end_date=?""",
                (
                    data.get("room"), data.get("source"), data.get("uid") or "",
                    data.get("start_date"), data.get("end_date"),
                ),
            ).fetchone()
            md = dict(meta) if meta is not None else {}
            guest_name = str(md.get("guest_name") or "").strip()
            if not guest_name:
                summary = str(data.get("summary") or "").strip()
                if summary and summary.casefold() not in {"reserved", "reservation", "not available", "blocked", "busy", "unavailable", "booking.com"}:
                    guest_name = summary
            out.append({
                "kind": "external",
                "id": str(data.get("id") or ""),
                "uid": str(data.get("uid") or ""),
                "room": str(data.get("room") or ""),
                "arrival": str(data.get("start_date") or ""),
                "departure": str(data.get("end_date") or ""),
                "guest_name": guest_name,
                "country": str(md.get("country") or ""),
                "guests": int(md.get("guests") or 0),
                "booking_reference": str(md.get("booking_reference") or ""),
                "source": str(data.get("source") or "external"),
            })
        return out

    @app.get("/api/central/master-calendar")
    def central_master_calendar_snapshot():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        try:
            year = int(request.args.get("year", date.today().year))
            month = int(request.args.get("month", date.today().month))
            start, end = _month_bounds(year, month)
        except Exception:
            return jsonify(ok=False, error="invalid_month"), 400

        payload = {room: {} for room in rooms}
        controls = {}
        with db() as conn:
            for room in rooms:
                controls[room] = {
                    channel: _global_enabled(conn, room, channel)
                    for channel in CHANNELS
                }
                current = start
                while current < end:
                    direct_price, direct_override = _effective_direct_price(conn, room, current)
                    booking_price, booking_override = _booking_target_price(conn, room, current)
                    drow = _day_row(conn, room, "direct", current)
                    brow = _day_row(conn, room, "booking", current)
                    payload[room][current.isoformat()] = {
                        "direct": {
                            "open": _channel_open(conn, room, "direct", current),
                            "price": direct_price,
                            "price_override": direct_override,
                            "state_override": None if drow is None else drow["enabled_override"],
                        },
                        "booking": {
                            "open": _channel_open(conn, room, "booking", current),
                            "price": booking_price,
                            "price_override": booking_override,
                            "state_override": None if brow is None else brow["enabled_override"],
                        },
                    }
                    current += timedelta(days=1)
            occupancy = _occupancy_rows(conn, start, end)

        return jsonify(
            ok=True,
            year=year,
            month=month,
            rooms=list(rooms),
            controls=controls,
            days=payload,
            occupancy=occupancy,
            note="Booking-Preis ist Sollpreis; iCal überträgt keine Preise.",
        ), 200, {"Cache-Control": "no-store"}

    @app.post("/api/central/master-calendar/day-setting")
    def central_master_calendar_day_setting():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        room = str(data.get("room") or "").strip()
        if room not in rooms:
            return jsonify(ok=False, error="unknown_room"), 400
        try:
            start = date.fromisoformat(str(data.get("start_date") or ""))
            end = date.fromisoformat(str(data.get("end_date") or data.get("start_date") or ""))
        except Exception:
            return jsonify(ok=False, error="invalid_dates"), 400
        if end < start or (end - start).days > 370:
            return jsonify(ok=False, error="invalid_range"), 400

        supplied = {}
        try:
            for channel in CHANNELS:
                enabled_key = f"{channel}_enabled"
                price_key = f"{channel}_price"
                if enabled_key in data:
                    supplied[(channel, "enabled")] = _as_bool_or_none(data.get(enabled_key))
                if price_key in data:
                    supplied[(channel, "price")] = _as_price_or_none(data.get(price_key))
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        if not supplied:
            return jsonify(ok=False, error="no_changes"), 400

        updated = 0
        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            current = start
            while current <= end:
                for channel in CHANNELS:
                    relevant = any((channel, field) in supplied for field in ("enabled", "price"))
                    if not relevant:
                        continue
                    old = conn.execute(
                        """SELECT enabled_override,price FROM zab_channel_day_settings
                           WHERE room=? AND day=? AND channel=?""",
                        (room, current.isoformat(), channel),
                    ).fetchone()
                    enabled = old["enabled_override"] if old is not None else None
                    price = old["price"] if old is not None else None
                    if (channel, "enabled") in supplied:
                        value = supplied[(channel, "enabled")]
                        enabled = None if value is None else (1 if value else 0)
                    if (channel, "price") in supplied:
                        price = supplied[(channel, "price")]
                    if enabled is None and price is None:
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
                            (room, current.isoformat(), channel, enabled, price, now),
                        )
                    updated += 1
                current += timedelta(days=1)
        return jsonify(ok=True, updated=updated), 200, {"Cache-Control": "no-store"}

    @app.post("/api/central/master-calendar/channel")
    def central_master_calendar_channel():
        if not _authorized():
            return jsonify(ok=False, error="unauthorized"), 401
        data = request.get_json(silent=True) or {}
        room = str(data.get("room") or "").strip()
        channel = str(data.get("channel") or "").strip().lower()
        if room not in rooms or channel not in CHANNELS or "enabled" not in data:
            return jsonify(ok=False, error="invalid_channel"), 400
        try:
            enabled = _as_bool_or_none(data.get("enabled"))
        except ValueError:
            return jsonify(ok=False, error="invalid_enabled"), 400
        if enabled is None:
            enabled = True
        with db() as conn:
            conn.execute(
                """INSERT INTO zab_channel_controls(room,channel,enabled,updated_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(room,channel) DO UPDATE SET
                     enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (room, channel, 1 if enabled else 0, datetime.now().isoformat(timespec="seconds")),
            )
        return jsonify(ok=True, room=room, channel=channel, enabled=bool(enabled)), 200

    app.extensions["zab_master_calendar_desktop_api"] = True
