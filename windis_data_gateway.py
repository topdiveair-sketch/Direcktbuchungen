"""Authenticated mutable Windis data source for the Growth Runtime."""

from __future__ import annotations

import hmac
import os
from datetime import datetime

from flask import jsonify, request

from railway_app import app, db


PARTNER_SEED = [
    ("A", "Donau Niederoesterreich Tourismus GmbH / Wachau-Nibelungengau-Kremstal", "Tourismus", "regionale Familienmarke und Content fuer Familiengaeste", "Kontakt verifizieren und Erstkontakt senden", "Offen", "2026-08-20"),
    ("A", "Donau Niederoesterreich - Welterbesteig Wachau", "Tourismus / Wandern", "Familien-Wandertipp mit Buchbezug", "Kontakt verifizieren und Erstkontakt senden", "Offen", "2026-08-20"),
    ("A", "Thalia Krems - ALEX", "Buchhandel", "Regionalflaeche fuer Hero-Titel", "Kontakt verifizieren und Erstkontakt senden", "Offen", "2026-08-21"),
    ("A", "Stadtbuecherei & Mediathek Krems", "Bibliothek", "regionale Kinderbuchtipps und Lesefoerderung", "Kontakt verifizieren und Erstkontakt senden", "Offen", "2026-08-21"),
    ("A", "Burgruine Aggstein", "Ausflugsziel", "Burgshop plus Windis-Raetselkarte oder Entdeckerpass", "Kontakt verifizieren und Erstkontakt senden", "Offen", "2026-08-22"),
    ("B", "Wachau Info-Center Krems", "Tourismus / Gaesteservice", "Familien-Tipp fuer Gaeste vor Ort", "Kontakt verifizieren und Erstkontakt senden", "Offen", "2026-08-27"),
    ("B", "Treffpunkt Bibliothek - Service des Landes NOe", "Bibliotheksnetzwerk", "regionales Lesefoerderungsangebot", "Kontakt verifizieren und Erstkontakt senden", "Offen", "2026-08-28"),
    ("B", "Fremdenverkehrsverein / Stadtgemeinde Duernstein", "Tourismus", "Duernstein-Geschichte und saisonale Familienaktion", "Kontakt verifizieren und senden", "Offen", "2026-09-01"),
]

KPI_SEED = [
    ("Qualifizierte Partnerkontakte", 0, 15, 30),
    ("Partner-Zusagen / Kooperationen", 0, 3, 6),
    ("Sichtplatzierungen / Partneraktionen bestaetigt", 0, 2, 4),
    ("Unabhaengige Rezensionen (neu)", 0, 40, 100),
    ("Hero-Titel mit klarer Landingpage", 0, 4, 4),
    ("Regionale Verkaufsstellen mit Sichtplatzierung", 0, 3, 6),
    ("Tourismus-/Partnerseiten mit Windis-Verweis", 1, 3, 5),
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _token() -> str:
    return os.environ.get("GROWTH_WEBHOOK_TOKEN", "").strip()


def _authorized() -> bool:
    token = _token()
    supplied = request.headers.get("Authorization", "")
    expected = f"Bearer {token}" if token else ""
    return bool(token) and hmac.compare_digest(supplied, expected)


def _init_tables() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS growth_windis_partners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                priority TEXT NOT NULL,
                partner TEXT NOT NULL UNIQUE,
                category TEXT DEFAULT '',
                approach TEXT DEFAULT '',
                next_step TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Offen',
                target_date TEXT DEFAULT '',
                email TEXT DEFAULT '',
                email_verified INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS growth_windis_kpis (
                metric TEXT PRIMARY KEY,
                start_value REAL NOT NULL DEFAULT 0,
                target_oct REAL NOT NULL DEFAULT 0,
                target_dec REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS n FROM growth_windis_partners").fetchone()["n"]
        if count == 0:
            conn.executemany(
                """INSERT INTO growth_windis_partners
                   (priority,partner,category,approach,next_step,status,target_date,email,email_verified,updated_at)
                   VALUES(?,?,?,?,?,?,?,'',0,?)""",
                [row + (_now(),) for row in PARTNER_SEED],
            )
        count = conn.execute("SELECT COUNT(*) AS n FROM growth_windis_kpis").fetchone()["n"]
        if count == 0:
            conn.executemany(
                """INSERT INTO growth_windis_kpis(metric,start_value,target_oct,target_dec,updated_at)
                   VALUES(?,?,?,?,?)""",
                [row + (_now(),) for row in KPI_SEED],
            )


_init_tables()


@app.get("/growth/windis-data")
def growth_windis_data():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    with db() as conn:
        partners = conn.execute(
            """SELECT priority,partner,category,approach,next_step,status,target_date,email,email_verified,updated_at
               FROM growth_windis_partners ORDER BY priority, target_date, partner"""
        ).fetchall()
        kpis = conn.execute(
            "SELECT metric,start_value,target_oct,target_dec,updated_at FROM growth_windis_kpis ORDER BY metric"
        ).fetchall()
    return jsonify({
        "ok": True,
        "source": "railway-live",
        "updatedAt": _now(),
        "partners": [
            {
                "priority": r["priority"],
                "partner": r["partner"],
                "category": r["category"],
                "approach": r["approach"],
                "nextStep": r["next_step"],
                "status": r["status"],
                "targetDate": r["target_date"],
                "email": r["email"] or None,
                "emailVerified": bool(r["email_verified"]),
                "updatedAt": r["updated_at"],
            }
            for r in partners
        ],
        "kpis": [
            {
                "metric": r["metric"],
                "start": r["start_value"],
                "targetOct": r["target_oct"],
                "targetDec": r["target_dec"],
                "updatedAt": r["updated_at"],
            }
            for r in kpis
        ],
    }), 200


@app.post("/growth/windis-data/partners")
def growth_windis_partner_upsert():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    partner = str(body.get("partner") or "").strip()
    if not partner:
        return jsonify({"error": "partner_required"}), 400
    email = str(body.get("email") or "").strip()
    email_verified = 1 if body.get("emailVerified") is True and email else 0
    values = (
        str(body.get("priority") or "B").strip()[:4],
        partner[:300],
        str(body.get("category") or "").strip()[:300],
        str(body.get("approach") or "").strip()[:2000],
        str(body.get("nextStep") or "").strip()[:2000],
        str(body.get("status") or "Offen").strip()[:100],
        str(body.get("targetDate") or "").strip()[:40],
        email[:320],
        email_verified,
        _now(),
    )
    with db() as conn:
        conn.execute(
            """INSERT INTO growth_windis_partners
               (priority,partner,category,approach,next_step,status,target_date,email,email_verified,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(partner) DO UPDATE SET
                 priority=excluded.priority, category=excluded.category, approach=excluded.approach,
                 next_step=excluded.next_step, status=excluded.status, target_date=excluded.target_date,
                 email=excluded.email, email_verified=excluded.email_verified, updated_at=excluded.updated_at""",
            values,
        )
    return jsonify({"ok": True, "partner": partner, "emailVerified": bool(email_verified)}), 200
