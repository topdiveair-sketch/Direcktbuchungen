from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from flask import jsonify, redirect, render_template, url_for


VIENNA = ZoneInfo("Europe/Vienna")


def init_host_automation(app, db, require_admin, db_path):
    """Business-safety automations for Zuhause am Bach.

    All guest/owner email is written to the persistent email_outbox first.
    The existing mail retry worker delivers it via the configured HTTPS provider.
    """

    if app.extensions.get("zab_host_automation_initialized"):
        return
    app.extensions["zab_host_automation_initialized"] = True

    db_path = Path(db_path)

    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS automation_alerts(
                alert_key TEXT PRIMARY KEY,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS automation_runs(
                run_key TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS automation_metrics(
                metric_day TEXT PRIMARY KEY,
                availability_checks INTEGER NOT NULL DEFAULT 0,
                booking_section_views INTEGER NOT NULL DEFAULT 0,
                guest_details_started INTEGER NOT NULL DEFAULT 0,
                booking_submits INTEGER NOT NULL DEFAULT 0,
                booking_abandoned INTEGER NOT NULL DEFAULT 0,
                paypal_orders INTEGER NOT NULL DEFAULT 0,
                confirmed_bookings INTEGER NOT NULL DEFAULT 0,
                revenue REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            """
        )
        metric_cols = {row[1] for row in conn.execute("PRAGMA table_info(automation_metrics)")}
        if "booking_abandoned" not in metric_cols:
            conn.execute("ALTER TABLE automation_metrics ADD COLUMN booking_abandoned INTEGER NOT NULL DEFAULT 0")

    def _now():
        return datetime.now(VIENNA)

    def _iso_now():
        return _now().isoformat(timespec="seconds")

    def _settings():
        with db() as conn:
            return {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM site_settings")}

    def _owner_recipients():
        cfg = _settings()
        primary = (
            os.environ.get("BOOKING_OWNER_EMAIL", "").strip()
            or os.environ.get("SITE_EMAIL", "").strip()
            or cfg.get("email", "").strip()
            or "zuhause.am.bach@outlook.com"
        )
        copy = os.environ.get("BOOKING_COPY_EMAIL", "").strip() or "topdiveair@gmail.com"
        result = [primary]
        if copy and copy.lower() != primary.lower():
            result.append(copy)
        return result

    def _queue_mail(dedupe_key, booking_id, role, recipient, subject, body):
        now = _iso_now()
        with db() as conn:
            conn.execute(
                """INSERT INTO email_outbox
                   (dedupe_key,booking_id,role,recipient,subject,body,status,attempts,last_error,
                    provider_message_id,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,'pending',0,'','',?,?)
                   ON CONFLICT(dedupe_key) DO UPDATE SET
                     recipient=excluded.recipient,
                     body=excluded.body,
                     updated_at=excluded.updated_at,
                     status=CASE WHEN email_outbox.status='sent' THEN 'sent' ELSE 'pending' END,
                     attempts=CASE WHEN email_outbox.status='sent' THEN email_outbox.attempts ELSE 0 END,
                     last_error=CASE WHEN email_outbox.status='sent' THEN email_outbox.last_error ELSE '' END""",
                (dedupe_key, int(booking_id or 0), role, recipient, subject, body, now, now),
            )

    def _queue_owner_notice(key, subject, body, severity="warning"):
        today = _now().date().isoformat()
        for idx, recipient in enumerate(_owner_recipients()):
            _queue_mail(
                f"automation-owner:{today}:{key}:{idx}",
                0,
                f"automation_{severity}",
                recipient,
                subject,
                body,
            )

    def _run_once_key(key, details=""):
        now = _iso_now()
        with db() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO automation_runs(run_key,status,details,created_at,updated_at)
                   VALUES(?,'done',?,?,?)""",
                (key, details, now, now),
            )
        return bool(cur.rowcount)

    def _upsert_alert(alert_key, severity, message):
        now = _iso_now()
        with db() as conn:
            old = conn.execute(
                "SELECT active FROM automation_alerts WHERE alert_key=?",
                (alert_key,),
            ).fetchone()
            conn.execute(
                """INSERT INTO automation_alerts
                   (alert_key,severity,message,active,first_seen,updated_at,resolved_at)
                   VALUES(?,?,?,1,?,?,'')
                   ON CONFLICT(alert_key) DO UPDATE SET
                     severity=excluded.severity,
                     message=excluded.message,
                     active=1,
                     updated_at=excluded.updated_at,
                     resolved_at=''""",
                (alert_key, severity, message, now, now),
            )
        if not old or not int(old["active"] or 0):
            _queue_owner_notice(
                f"alert:{alert_key}",
                f"[{severity.upper()}] Zuhause am Bach – Automatik",
                message,
                severity,
            )

    def _resolve_alerts(prefix, active_keys):
        now = _iso_now()
        with db() as conn:
            rows = conn.execute(
                "SELECT alert_key FROM automation_alerts WHERE active=1 AND alert_key LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
            for row in rows:
                key = row["alert_key"]
                if key not in active_keys:
                    conn.execute(
                        "UPDATE automation_alerts SET active=0,resolved_at=?,updated_at=? WHERE alert_key=?",
                        (now, now, key),
                    )

    def _parse_dt(value):
        try:
            return datetime.fromisoformat(str(value or ""))
        except Exception:
            return None

    def _booking_watchdog():
        today = _now().date().isoformat()
        active = set()
        with db() as conn:
            bookings = conn.execute(
                """SELECT * FROM bookings
                   WHERE status='confirmed' AND departure>=?
                   ORDER BY arrival""",
                (today,),
            ).fetchall()
            outbox = conn.execute(
                """SELECT booking_id,role,status,attempts,last_error
                   FROM email_outbox
                   WHERE booking_id>0"""
            ).fetchall()
            email_log = conn.execute(
                """SELECT booking_id,recipient,status FROM email_log
                   WHERE booking_id>0"""
            ).fetchall()

        by_booking = {}
        for row in outbox:
            by_booking.setdefault(int(row["booking_id"]), []).append(row)
        delivered_to = {}
        for row in email_log:
            if str(row["status"] or "").lower().startswith("gesendet"):
                delivered_to.setdefault(int(row["booking_id"]), set()).add(str(row["recipient"] or "").lower())

        owner_addresses = {x.lower() for x in _owner_recipients()}
        sender = app.extensions.get("zab_send_confirmation")
        for booking in bookings:
            bid = int(booking["id"])
            rows = by_booking.get(bid, [])
            roles = {str(row["role"]) for row in rows}
            delivered = delivered_to.get(bid, set())
            guest_done = "guest" in roles or str(booking["email"] or "").lower() in delivered
            owner_done = "owner" in roles or bool(owner_addresses & delivered)
            missing = set()
            if not guest_done:
                missing.add("guest")
            if not owner_done:
                missing.add("owner")
            if missing and callable(sender):
                try:
                    sender(bid)
                except Exception:
                    app.logger.exception("automation_booking_confirmation_repair_failed booking_id=%s", bid)
            if missing:
                key = f"booking-mail:{bid}"
                active.add(key)
                _upsert_alert(
                    key,
                    "critical",
                    f"Buchung #{bid} ist bestätigt, aber Mail-Rollen fehlen: {', '.join(sorted(missing))}. "
                    "Die Automatik hat einen Reparaturversuch gestartet.",
                )

            bad_rows = [r for r in rows if r["status"] == "pending" and int(r["attempts"] or 0) >= 3]
            if bad_rows:
                key = f"booking-mail-retry:{bid}"
                active.add(key)
                reasons = ", ".join(sorted({str(r["last_error"] or "unbekannt") for r in bad_rows}))
                _upsert_alert(
                    key,
                    "critical",
                    f"Buchung #{bid}: mindestens eine Buchungs-Mail hängt nach mehreren Versuchen in der Outbox. "
                    f"Letzter Status: {reasons}.",
                )

        _resolve_alerts("booking-mail:", active)
        _resolve_alerts("booking-mail-retry:", active)

    def _overbooking_watchdog():
        active = set()
        today = _now().date().isoformat()
        with db() as conn:
            overlaps = conn.execute(
                """SELECT a.id a_id,b.id b_id,a.room,a.arrival,a.departure,b.arrival b_arrival,b.departure b_departure
                   FROM bookings a
                   JOIN bookings b ON a.id < b.id
                    AND a.room=b.room
                    AND a.status='confirmed' AND b.status='confirmed'
                    AND a.arrival < b.departure AND a.departure > b.arrival
                   WHERE a.departure>=? AND b.departure>=?""",
                (today, today),
            ).fetchall()
        for row in overlaps:
            key = f"overlap:{row['a_id']}:{row['b_id']}"
            active.add(key)
            _upsert_alert(
                key,
                "critical",
                f"OVERBOOKING-ALARM: Buchung #{row['a_id']} ({row['arrival']}–{row['departure']}) "
                f"überschneidet sich mit Buchung #{row['b_id']} ({row['b_arrival']}–{row['b_departure']}) "
                f"für {row['room']}.",
            )
        _resolve_alerts("overlap:", active)

    def _ical_watchdog():
        active = set()
        now = _now()
        with db() as conn:
            rows = conn.execute(
                "SELECT room,import_url,last_sync,last_result FROM ical_settings WHERE TRIM(import_url)<>''"
            ).fetchall()
        for row in rows:
            sync = _parse_dt(row["last_sync"])
            stale = not sync or (now.replace(tzinfo=None) - sync.replace(tzinfo=None)) > timedelta(hours=6)
            failed = "fehler" in str(row["last_result"] or "").lower()
            if stale or failed:
                key = f"ical:{row['room']}"
                active.add(key)
                _upsert_alert(
                    key,
                    "critical" if failed else "warning",
                    f"Kalender-Sync für {row['room']} ist {'fehlerhaft' if failed else 'älter als 6 Stunden'}. "
                    f"Letzter Sync: {row['last_sync'] or 'nie'} · Ergebnis: {row['last_result'] or 'kein Ergebnis'}.",
                )
        _resolve_alerts("ical:", active)

    def _payment_reminders():
        now = _now()
        today = now.date()
        site_url = os.environ.get("PUBLIC_SITE_URL", "https://www.zuhauseambach-wachau.at").rstrip("/")
        with db() as conn:
            rows = conn.execute(
                """SELECT * FROM bookings
                   WHERE COALESCE(paid,0)=0
                     AND status NOT IN ('cancelled','expired')
                     AND departure>=?
                   ORDER BY created_at""",
                (today.isoformat(),),
            ).fetchall()
        for booking in rows:
            created = _parse_dt(booking["created_at"])
            if not created:
                continue
            age = now.replace(tzinfo=None) - created.replace(tzinfo=None)
            arrival = date.fromisoformat(booking["arrival"])
            method = str(booking["payment_method"] or "")
            bid = int(booking["id"])
            first = booking["first_name"]
            email = booking["email"]

            if method == "Banküberweisung" and booking["status"] == "confirmed" and arrival > today + timedelta(days=1):
                stages = []
                if age >= timedelta(hours=24):
                    stages.append(("payment_bank_1", "Zahlungserinnerung – Zuhause am Bach"))
                if age >= timedelta(hours=72):
                    stages.append(("payment_bank_2", "Zweite Zahlungserinnerung – Zuhause am Bach"))
                for role, subject in stages:
                    body = (
                        f"Hallo {first},\n\n"
                        f"deine Buchung #{bid} bei Zuhause am Bach – Wachau ist bestätigt. "
                        "In unserem System ist die Banküberweisung noch als offen markiert.\n\n"
                        f"Gesamtbetrag: {float(booking['total']):.2f} EUR\n"
                        f"Anreise: {booking['arrival']}\n"
                        f"Abreise: {booking['departure']}\n\n"
                        "Falls du bereits überwiesen hast, kannst du diese Nachricht ignorieren. "
                        "Wir gleichen den Zahlungseingang persönlich ab.\n\n"
                        "Zuhause am Bach – Wachau"
                    )
                    _queue_mail(f"auto:{bid}:{role}", bid, role, email, subject, body)

            if (
                method in ("PayPal", "paypal_checkout")
                and timedelta(hours=2) <= age <= timedelta(hours=24)
                and booking["status"] in ("inquiry", "pending")
            ):
                body = (
                    f"Hallo {first},\n\n"
                    "deine Buchungsanfrage ist bei uns angekommen, die PayPal-Zahlung ist aber noch nicht abgeschlossen.\n"
                    f"Bitte prüfe die Buchung erneut über unsere sichere Website: {site_url}/#booking\n\n"
                    "Falls du inzwischen bezahlt hast, kannst du diese Nachricht ignorieren.\n\n"
                    "Zuhause am Bach – Wachau"
                )
                _queue_mail(
                    f"auto:{bid}:payment_paypal_open",
                    bid,
                    "payment_paypal_open",
                    email,
                    "PayPal-Zahlung noch offen – Zuhause am Bach",
                    body,
                )

    def _prearrival_upsell():
        now = _now()
        target = now.date() + timedelta(days=2)
        site_url = os.environ.get("PUBLIC_SITE_URL", "https://www.zuhauseambach-wachau.at").rstrip("/")
        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE status='confirmed' AND arrival=?",
                (target.isoformat(),),
            ).fetchall()
        ensure_tokens = app.extensions.get("zab_ensure_tokens")
        for booking in rows:
            bid = int(booking["id"])
            if callable(ensure_tokens):
                public_token, _, _ = ensure_tokens(bid)
            else:
                public_token = str(booking["public_token"] or "")
            portal = f"{site_url}/guest/{public_token}" if public_token else f"{site_url}/"
            body = (
                f"Hallo {booking['first_name']},\n\n"
                "in zwei Tagen beginnt dein Aufenthalt bei Zuhause am Bach – Wachau. "
                "Wenn du noch etwas ergänzen möchtest, kannst du das jetzt bequem im Gästeportal tun:\n\n"
                "• Frühstück – 12 € pro Person/Nacht\n"
                "• Wachauer Jause\n"
                "• Gepäcktransport für Wanderer/Radfahrer\n"
                "• ungefähre Ankunftszeit mitteilen\n\n"
                f"Gästeportal: {portal}\n\n"
                "Wir freuen uns auf dich!\nZuhause am Bach – Wachau"
            )
            _queue_mail(
                f"auto:{bid}:prearrival_upsell",
                bid,
                "prearrival_upsell",
                booking["email"],
                "Noch etwas für deinen Aufenthalt? – Zuhause am Bach",
                body,
            )

    def _housekeeping_automation():
        now = _now()
        today = now.date().isoformat()
        with db() as conn:
            active = conn.execute(
                """SELECT room,first_name,last_name,departure FROM bookings
                   WHERE status='confirmed' AND arrival<=? AND departure>?
                   ORDER BY arrival LIMIT 1""",
                (today, today),
            ).fetchone()
            departure = conn.execute(
                """SELECT room,first_name,last_name FROM bookings
                   WHERE status='confirmed' AND departure=?
                   ORDER BY id DESC LIMIT 1""",
                (today,),
            ).fetchone()
            state = conn.execute(
                "SELECT room,status,note FROM housekeeping WHERE room='Bachblick'"
            ).fetchone()

            if state and state["status"] != "gesperrt":
                if active:
                    conn.execute(
                        "UPDATE housekeeping SET status='belegt',note=?,updated_at=? WHERE room=?",
                        (
                            f"Aktuell belegt · {active['first_name']} {active['last_name']} · Abreise {active['departure']}",
                            _iso_now(),
                            active["room"],
                        ),
                    )
                elif departure and now.hour >= 10 and state["status"] not in ("Reinigung", "fertig"):
                    conn.execute(
                        "UPDATE housekeeping SET status='Reinigung',note=?,updated_at=? WHERE room=?",
                        (
                            f"Checkout heute · {departure['first_name']} {departure['last_name']}",
                            _iso_now(),
                            departure["room"],
                        ),
                    )

    def _occupied_days(start_day, days=60):
        end_day = start_day + timedelta(days=days)
        occupied = set()
        with db() as conn:
            bookings = conn.execute(
                """SELECT arrival,departure FROM bookings
                   WHERE status IN ('confirmed','pending')
                     AND departure>? AND arrival<?""",
                (start_day.isoformat(), end_day.isoformat()),
            ).fetchall()
            external = conn.execute(
                """SELECT start_date,end_date FROM external_blocks
                   WHERE end_date>? AND start_date<?""",
                (start_day.isoformat(), end_day.isoformat()),
            ).fetchall()
        for row in list(bookings) + list(external):
            a = date.fromisoformat(str(row[0]))
            b = date.fromisoformat(str(row[1]))
            cur = max(a, start_day)
            while cur < min(b, end_day):
                occupied.add(cur)
                cur += timedelta(days=1)
        return occupied

    def _gap_nights():
        today = _now().date()
        occupied = _occupied_days(today, 90)
        gaps = []
        cur = today + timedelta(days=1)
        end = today + timedelta(days=90)
        while cur < end:
            if cur not in occupied and (cur - timedelta(days=1)) in occupied and (cur + timedelta(days=1)) in occupied:
                gaps.append(cur.isoformat())
            cur += timedelta(days=1)
        return gaps[:12]

    def _update_metrics():
        today = _now().date()
        start = today.isoformat()
        end = (today + timedelta(days=1)).isoformat()
        event_counts = {}
        with db() as conn:
            try:
                rows = conn.execute(
                    """SELECT event,COUNT(*) c FROM site_events
                       WHERE created_at>=? AND created_at<?
                       GROUP BY event""",
                    (start, end),
                ).fetchall()
                event_counts = {str(r["event"]): int(r["c"]) for r in rows}
            except Exception:
                event_counts = {}
            try:
                checks = conn.execute(
                    "SELECT COUNT(*) c FROM demand_searches WHERE created_at>=? AND created_at<?",
                    (start, end),
                ).fetchone()["c"]
            except Exception:
                checks = 0
            booked = conn.execute(
                """SELECT COUNT(*) c,COALESCE(SUM(total),0) revenue FROM bookings
                   WHERE status='confirmed' AND created_at>=? AND created_at<?""",
                (start, end),
            ).fetchone()
            now = _iso_now()
            conn.execute(
                """INSERT INTO automation_metrics(
                       metric_day,availability_checks,booking_section_views,guest_details_started,
                       booking_submits,booking_abandoned,paypal_orders,confirmed_bookings,revenue,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(metric_day) DO UPDATE SET
                     availability_checks=excluded.availability_checks,
                     booking_section_views=excluded.booking_section_views,
                     guest_details_started=excluded.guest_details_started,
                     booking_submits=excluded.booking_submits,
                     booking_abandoned=excluded.booking_abandoned,
                     paypal_orders=excluded.paypal_orders,
                     confirmed_bookings=excluded.confirmed_bookings,
                     revenue=excluded.revenue,
                     updated_at=excluded.updated_at""",
                (
                    today.isoformat(),
                    int(checks),
                    int(event_counts.get("booking_section_view", 0)),
                    int(event_counts.get("guest_details_started", 0)),
                    int(event_counts.get("booking_submit_nonpaypal", 0)),
                    int(event_counts.get("booking_abandoned", 0)),
                    int(event_counts.get("paypal_order_created", 0)),
                    int(booked["c"] or 0),
                    float(booked["revenue"] or 0),
                    now,
                ),
            )

    def _seo_self_check():
        base = os.environ.get("PUBLIC_SITE_URL", "https://www.zuhauseambach-wachau.at").rstrip("/")
        active = set()
        checks = [
            ("home", base + "/", ("<link rel=\"canonical\"", "application/ld+json")),
            ("robots", base + "/robots.txt", ("sitemap",)),
            ("sitemap", base + "/sitemap.xml", ("<urlset",)),
        ]
        for name, url, needles in checks:
            key = f"seo:{name}"
            try:
                response = requests.get(url, timeout=(4, 10), headers={"User-Agent": "ZAB-Automation/1.0"})
                body = response.text.lower()
                missing = [needle for needle in needles if needle.lower() not in body]
                if response.status_code != 200 or missing:
                    active.add(key)
                    _upsert_alert(
                        key,
                        "warning",
                        f"SEO-Selbsttest {name} auffällig: HTTP {response.status_code}; "
                        f"fehlend: {', '.join(missing) if missing else 'nichts'}.",
                    )
            except requests.RequestException as exc:
                active.add(key)
                _upsert_alert(key, "warning", f"SEO-Selbsttest {name} nicht erreichbar: {str(exc)[:180]}")
        _resolve_alerts("seo:", active)

    def _daily_backup():
        now = _now()
        if now.hour < 3:
            return
        day = now.date().isoformat()
        if not _run_once_key(f"backup:{day}", "daily sqlite backup"):
            return
        backup_dir = db_path.parent / "backups-auto"
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / f"zab-{day}.sqlite3"
        try:
            source = sqlite3.connect(str(db_path))
            dest = sqlite3.connect(str(target))
            source.backup(dest)
            ok = dest.execute("PRAGMA integrity_check").fetchone()[0]
            dest.close()
            source.close()
            if str(ok).lower() != "ok":
                raise RuntimeError(f"integrity_check={ok}")
            cutoff = now.date() - timedelta(days=30)
            for item in backup_dir.glob("zab-*.sqlite3"):
                try:
                    stamp = date.fromisoformat(item.stem.replace("zab-", ""))
                    if stamp < cutoff:
                        item.unlink(missing_ok=True)
                except Exception:
                    continue
        except Exception as exc:
            _upsert_alert("backup:daily", "critical", f"Tägliches Datenbank-Backup fehlgeschlagen: {exc}")

    def _daily_report():
        now = _now()
        if now.hour < 7:
            return
        day = now.date()
        run_key = f"daily-report:{day.isoformat()}"
        if not _run_once_key(run_key, "operator morning report"):
            return

        tomorrow = day + timedelta(days=1)
        with db() as conn:
            arrivals = conn.execute(
                "SELECT first_name,last_name,arrival_time FROM bookings WHERE status='confirmed' AND arrival=?",
                (day.isoformat(),),
            ).fetchall()
            departures = conn.execute(
                "SELECT first_name,last_name FROM bookings WHERE status='confirmed' AND departure=?",
                (day.isoformat(),),
            ).fetchall()
            tomorrow_rows = conn.execute(
                "SELECT first_name,last_name,arrival_time FROM bookings WHERE status='confirmed' AND arrival=?",
                (tomorrow.isoformat(),),
            ).fetchall()
            open_payments = conn.execute(
                "SELECT COUNT(*) c,COALESCE(SUM(total),0) total FROM bookings WHERE status='confirmed' AND COALESCE(paid,0)=0"
            ).fetchone()
            pending_mail = conn.execute(
                "SELECT COUNT(*) c FROM email_outbox WHERE status='pending'"
            ).fetchone()["c"]
            alerts = conn.execute(
                "SELECT severity,message FROM automation_alerts WHERE active=1 ORDER BY severity DESC,updated_at DESC LIMIT 20"
            ).fetchall()
            metrics = conn.execute(
                "SELECT * FROM automation_metrics WHERE metric_day=?",
                (day.isoformat(),),
            ).fetchone()
            try:
                source_rows = conn.execute(
                    """SELECT COALESCE(NULLIF(source,''),'unbekannt') source,COUNT(*) c
                       FROM bookings
                       WHERE created_at>=? AND created_at<?
                       GROUP BY COALESCE(NULLIF(source,''),'unbekannt')
                       ORDER BY c DESC""",
                    (day.isoformat(), (day + timedelta(days=1)).isoformat()),
                ).fetchall()
            except Exception:
                source_rows = []

        gaps = _gap_nights()
        lines = [
            f"Zuhause am Bach – Tagesübersicht {day.isoformat()}",
            "",
            f"Heutige Anreisen: {len(arrivals)}",
        ]
        for row in arrivals:
            lines.append(f"  • {row['first_name']} {row['last_name']} · Ankunft {row['arrival_time'] or 'noch offen'}")
        lines.append(f"Heutige Abreisen: {len(departures)}")
        for row in departures:
            lines.append(f"  • {row['first_name']} {row['last_name']}")
        lines.append(f"Morgige Anreisen: {len(tomorrow_rows)}")
        for row in tomorrow_rows:
            lines.append(f"  • {row['first_name']} {row['last_name']} · Ankunft {row['arrival_time'] or 'noch offen'}")
        lines.extend([
            "",
            f"Offene Zahlungen: {int(open_payments['c'] or 0)} · {float(open_payments['total'] or 0):.2f} EUR",
            f"Nicht versandte Outbox-Mails: {int(pending_mail or 0)}",
            f"Einzelne freie Lückennächte: {', '.join(gaps[:6]) if gaps else 'keine'}",
        ])
        if metrics:
            lines.extend([
                "",
                "Direktbuchungs-Funnel heute:",
                f"  Verfügbarkeitsprüfungen: {metrics['availability_checks']}",
                f"  Buchungsbereich angesehen: {metrics['booking_section_views']}",
                f"  Gästedaten begonnen: {metrics['guest_details_started']}",
                f"  Formular-Absendungen: {metrics['booking_submits']}",
                f"  abgebrochene Buchungssitzungen: {metrics['booking_abandoned']}",
                f"  PayPal-Bestellungen: {metrics['paypal_orders']}",
                f"  bestätigte Buchungen: {metrics['confirmed_bookings']}",
            ])
        if source_rows:
            lines.append("")
            lines.append("Buchungsquellen heute:")
            for row in source_rows:
                lines.append(f"  • {row['source']}: {row['c']}")
        if alerts:
            lines.append("")
            lines.append("Aktive Warnungen:")
            for alert in alerts:
                lines.append(f"  • [{alert['severity']}] {alert['message']}")
        else:
            lines.extend(["", "Systemstatus: keine aktiven Automatik-Warnungen."])

        body = "\n".join(lines)
        for idx, recipient in enumerate(_owner_recipients()):
            _queue_mail(
                f"automation-report:{day.isoformat()}:{idx}",
                0,
                "daily_operator_report",
                recipient,
                f"Zuhause am Bach – Tagesübersicht {day.isoformat()}",
                body,
            )

    def run_automations_once():
        _housekeeping_automation()
        _booking_watchdog()
        _overbooking_watchdog()
        _ical_watchdog()
        _payment_reminders()
        _prearrival_upsell()
        _update_metrics()
        _seo_self_check()
        _daily_backup()
        _daily_report()
        processor = app.extensions.get("zab_process_mail_outbox")
        if callable(processor):
            try:
                processor(limit=30)
            except Exception:
                app.logger.exception("automation_outbox_flush_failed")

    def _worker():
        time.sleep(20)
        while True:
            started = time.monotonic()
            try:
                run_automations_once()
            except Exception:
                app.logger.exception("host_automation_cycle_failed")
            elapsed = time.monotonic() - started
            time.sleep(max(60, 300 - elapsed))

    @app.get("/api/public/gap-nights")
    def public_gap_nights():
        return jsonify({
            "ok": True,
            "room": "Gartenzimmer",
            "dates": _gap_nights(),
            "booking_url": "https://www.zuhauseambach-wachau.at/#booking",
        })

    @app.get("/admin/automation-status")
    def automation_status():
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            alerts = conn.execute(
                "SELECT * FROM automation_alerts ORDER BY active DESC,severity DESC,updated_at DESC LIMIT 100"
            ).fetchall()
            pending_mail = conn.execute(
                """SELECT booking_id,role,recipient,attempts,last_error,updated_at
                   FROM email_outbox WHERE status='pending'
                   ORDER BY updated_at DESC LIMIT 100"""
            ).fetchall()
            metrics = conn.execute(
                "SELECT * FROM automation_metrics ORDER BY metric_day DESC LIMIT 14"
            ).fetchall()
            housekeeping = conn.execute(
                "SELECT * FROM housekeeping ORDER BY room"
            ).fetchall()
            runs = conn.execute(
                "SELECT * FROM automation_runs ORDER BY updated_at DESC LIMIT 30"
            ).fetchall()
        whatsapp_ready = all(
            os.environ.get(name, "").strip()
            for name in ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_GRAPH_VERSION")
        )
        return render_template(
            "automation_status.html",
            alerts=alerts,
            pending_mail=pending_mail,
            metrics=metrics,
            housekeeping=housekeeping,
            runs=runs,
            gap_nights=_gap_nights(),
            whatsapp_ready=whatsapp_ready,
        )

    @app.get("/health/automation")
    def automation_health():
        with db() as conn:
            critical = conn.execute(
                "SELECT COUNT(*) c FROM automation_alerts WHERE active=1 AND severity='critical'"
            ).fetchone()["c"]
            pending = conn.execute(
                "SELECT COUNT(*) c FROM email_outbox WHERE status='pending'"
            ).fetchone()["c"]
        return {
            "ok": int(critical or 0) == 0,
            "critical_alerts": int(critical or 0),
            "pending_mail": int(pending or 0),
            "gap_nights": _gap_nights(),
            "whatsapp_configured": all(
                os.environ.get(name, "").strip()
                for name in ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_GRAPH_VERSION")
            ),
        }, (200 if int(critical or 0) == 0 else 503)

    app.extensions["zab_run_host_automations"] = run_automations_once
    app.extensions["zab_gap_nights"] = _gap_nights

    threading.Thread(target=_worker, name="zab-host-automation", daemon=True).start()
