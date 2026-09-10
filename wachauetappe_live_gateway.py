"""Central live state API for WachauEtappe.

Railway is the operational source of truth. The Windows application mirrors this
state into its local SQLite database only as an offline cache.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import jsonify, request


def init_wachauetappe_live(app, db, require_admin):
    def now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def admin_ok() -> bool:
        # Keep exactly the same credential contract as the existing partner admin API.
        try:
            require_admin()
            return True
        except Exception:
            expected = os.environ.get("ADMIN_PASSWORD", "")
            supplied = request.headers.get("X-Admin-Password", "")
            import hmac
            return bool(expected) and hmac.compare_digest(expected, supplied)

    def unauthorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    def init_tables() -> None:
        with db() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS wachauetappe_hosts(
                  host_id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  location TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'research',
                  published INTEGER NOT NULL DEFAULT 0,
                  accepting_bookings INTEGER NOT NULL DEFAULT 0,
                  direct_url TEXT NOT NULL DEFAULT '',
                  email TEXT NOT NULL DEFAULT '',
                  phone TEXT NOT NULL DEFAULT '',
                  address TEXT NOT NULL DEFAULT '',
                  latitude REAL,
                  longitude REAL,
                  accommodation_type TEXT NOT NULL DEFAULT '',
                  contact_person TEXT NOT NULL DEFAULT '',
                  one_night_verified INTEGER NOT NULL DEFAULT 0,
                  cash_at_host_verified INTEGER NOT NULL DEFAULT 0,
                  luggage_verified INTEGER NOT NULL DEFAULT 0,
                  rooms_total INTEGER NOT NULL DEFAULT 0,
                  beds_total INTEGER NOT NULL DEFAULT 0,
                  raw_json TEXT NOT NULL DEFAULT '{}',
                  updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_we_hosts_location
                  ON wachauetappe_hosts(location,published,accepting_bookings);
                """
            )

        # Bootstrap only missing hosts from the repository seed. Once a row exists,
        # live database changes always win over hosts.json.
        seed = Path(__file__).resolve().parent / "plattform" / "hosts.json"
        if seed.exists():
            try:
                payload = json.loads(seed.read_text(encoding="utf-8"))
                hosts = payload.get("hosts", []) if isinstance(payload, dict) else []
                with db() as c:
                    for h in hosts:
                        if not isinstance(h, dict) or not h.get("id"):
                            continue
                        c.execute(
                            """
                            INSERT OR IGNORE INTO wachauetappe_hosts(
                              host_id,name,location,status,published,accepting_bookings,
                              direct_url,email,phone,address,latitude,longitude,
                              accommodation_type,contact_person,one_night_verified,
                              cash_at_host_verified,luggage_verified,raw_json,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                str(h.get("id")), str(h.get("name") or h.get("id")),
                                str(h.get("location") or ""), str(h.get("status") or "research"),
                                1 if h.get("published") else 0, 1 if h.get("accepting_bookings") else 0,
                                str(h.get("direct_url") or ""), str(h.get("email") or ""),
                                str(h.get("phone") or ""), str(h.get("address") or ""),
                                h.get("latitude"), h.get("longitude"),
                                str(h.get("accommodation_type") or ""), str(h.get("contact_person") or ""),
                                1 if h.get("one_night_verified") or any("1 Nacht" in str(x) for x in h.get("features", [])) else 0,
                                1 if h.get("cash_at_host_verified") else 0,
                                1 if h.get("luggage_verified") else 0,
                                json.dumps(h, ensure_ascii=False), now(),
                            ),
                        )
            except Exception:
                pass

        # Partner accounts are operational records too. Ensure every account has a
        # corresponding central host row without overwriting richer host metadata.
        try:
            with db() as c:
                c.execute(
                    """
                    INSERT OR IGNORE INTO wachauetappe_hosts(
                      host_id,name,location,status,published,accepting_bookings,email,
                      rooms_total,updated_at)
                    SELECT host_id,name,location,'partner_active',0,0,email,rooms_total,updated_at
                    FROM wachauetappe_partner_accounts
                    """
                )
        except Exception:
            pass

    init_tables()

    @app.get("/api/central/live-state")
    def wachauetappe_live_state():
        if not admin_ok():
            return unauthorized()
        f = request.args.get("from") or (date.today() - timedelta(days=7)).isoformat()
        t = request.args.get("to") or (date.today() + timedelta(days=180)).isoformat()
        with db() as c:
            hosts = c.execute(
                """
                SELECT h.*,
                       COALESCE(p.active,0) AS partner_active,
                       COALESCE(p.rooms_total,h.rooms_total,0) AS effective_rooms_total
                FROM wachauetappe_hosts h
                LEFT JOIN wachauetappe_partner_accounts p ON p.host_id=h.host_id
                ORDER BY h.location,h.name
                """
            ).fetchall()
            bookings = c.execute(
                """
                SELECT id,reference,host_id,stay_date,guests,guest_name,guest_email,
                       guest_phone,note,price,payment_method,status,source,created_at,updated_at
                FROM wachauetappe_guest_bookings
                WHERE stay_date BETWEEN ? AND ?
                ORDER BY stay_date,created_at
                """, (f, t)
            ).fetchall()
            availability = c.execute(
                """
                SELECT a.host_id,a.stay_date,
                       CASE WHEN b.stay_date IS NULL THEN a.status ELSE 'full' END AS status,
                       CASE WHEN b.stay_date IS NULL THEN a.rooms_free ELSE 0 END AS rooms_free,
                       a.price,a.breakfast_mode,a.breakfast_price,a.luggage_available,a.updated_at,
                       CASE WHEN b.stay_date IS NULL THEN 0 ELSE 1 END AS booking_blocked
                FROM wachauetappe_partner_availability a
                LEFT JOIN wachauetappe_partner_calendar_blocks b
                  ON b.host_id=a.host_id AND b.stay_date=a.stay_date AND b.provider='booking'
                WHERE a.stay_date BETWEEN ? AND ?
                ORDER BY a.stay_date,a.host_id
                """, (f, t)
            ).fetchall()
        return jsonify({
            "ok": True,
            "serverTime": now(),
            "from": f,
            "to": t,
            "hosts": [dict(r) for r in hosts],
            "bookings": [dict(r) for r in bookings],
            "availability": [dict(r) for r in availability],
        }), 200

    @app.put("/api/central/hosts/<host_id>")
    def wachauetappe_update_host(host_id: str):
        if not admin_ok():
            return unauthorized()
        p = request.get_json(silent=True) or {}
        host_id = str(host_id or "").strip()[:160]
        if not host_id:
            return jsonify({"ok": False, "error": "host_id_required"}), 422
        name = str(p.get("name") or host_id).strip()[:200]
        location = str(p.get("location") or "").strip()[:160]
        rooms = max(0, min(500, int(p.get("roomsTotal") or 0)))
        beds = max(0, min(2000, int(p.get("bedsTotal") or 0)))
        stamp = now()
        with db() as c:
            c.execute(
                """
                INSERT INTO wachauetappe_hosts(
                  host_id,name,location,status,published,accepting_bookings,direct_url,
                  email,phone,address,latitude,longitude,accommodation_type,contact_person,
                  one_night_verified,cash_at_host_verified,luggage_verified,rooms_total,
                  beds_total,raw_json,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(host_id) DO UPDATE SET
                  name=excluded.name,location=excluded.location,status=excluded.status,
                  published=excluded.published,accepting_bookings=excluded.accepting_bookings,
                  direct_url=excluded.direct_url,email=excluded.email,phone=excluded.phone,
                  address=excluded.address,latitude=excluded.latitude,longitude=excluded.longitude,
                  accommodation_type=excluded.accommodation_type,contact_person=excluded.contact_person,
                  one_night_verified=excluded.one_night_verified,
                  cash_at_host_verified=excluded.cash_at_host_verified,
                  luggage_verified=excluded.luggage_verified,rooms_total=excluded.rooms_total,
                  beds_total=excluded.beds_total,raw_json=excluded.raw_json,updated_at=excluded.updated_at
                """,
                (
                    host_id,name,location,str(p.get("status") or "research")[:80],
                    1 if p.get("published") else 0,1 if p.get("acceptingBookings") else 0,
                    str(p.get("directUrl") or "")[:500],str(p.get("email") or "")[:254],
                    str(p.get("phone") or "")[:100],str(p.get("address") or "")[:500],
                    p.get("latitude"),p.get("longitude"),str(p.get("accommodationType") or "")[:160],
                    str(p.get("contactPerson") or "")[:160],1 if p.get("oneNightVerified") else 0,
                    1 if p.get("cashAtHostVerified") else 0,1 if p.get("luggageVerified") else 0,
                    rooms,beds,json.dumps(p,ensure_ascii=False),stamp,
                ),
            )
            # Keep the partner account identity/capacity aligned when an account exists.
            c.execute(
                """UPDATE wachauetappe_partner_accounts
                   SET name=?,location=?,email=?,rooms_total=CASE WHEN ?>0 THEN ? ELSE rooms_total END,
                       updated_at=? WHERE host_id=?""",
                (name, location, str(p.get("email") or "")[:254], rooms, rooms, stamp, host_id),
            )
        return jsonify({"ok": True, "hostId": host_id, "updatedAt": stamp}), 200

    @app.patch("/api/central/bookings/<reference>")
    def wachauetappe_update_booking(reference: str):
        if not admin_ok():
            return unauthorized()
        p = request.get_json(silent=True) or {}
        status = str(p.get("status") or "").strip().lower()
        if status not in {"requested", "confirmed", "declined", "cancelled"}:
            return jsonify({"ok": False, "error": "invalid_status"}), 422
        stamp = now()
        with db() as c:
            cur = c.execute(
                "UPDATE wachauetappe_guest_bookings SET status=?,updated_at=? WHERE reference=?",
                (status, stamp, reference),
            )
        if not cur.rowcount:
            return jsonify({"ok": False, "error": "booking_not_found"}), 404
        return jsonify({"ok": True, "reference": reference, "status": status, "updatedAt": stamp}), 200

    @app.get("/health/wachauetappe-live")
    def wachauetappe_live_health():
        with db() as c:
            hosts = c.execute("SELECT COUNT(*) AS n FROM wachauetappe_hosts").fetchone()["n"]
            bookings = c.execute("SELECT COUNT(*) AS n FROM wachauetappe_guest_bookings").fetchone()["n"]
        return {"ok": True, "liveState": True, "hosts": int(hosts or 0), "bookings": int(bookings or 0)}, 200

    return True
