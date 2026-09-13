from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from flask import Response, jsonify, redirect, render_template_string, request


HOLD_MINUTES = 30
DEFAULT_DIRECT_ORIGIN = "https://topdiveair-sketch.github.io"
DEFAULT_RETURN_URL = "https://topdiveair-sketch.github.io/Direcktbuchungen/"
STRIPE_API_BASE = "https://api.stripe.com/v1"


def init_stripe_checkout(
    app,
    db,
    rooms,
    parse_date,
    price_breakdown,
    room_available_in_conn,
    sync_room,
):
    """Register a server-verified Stripe Checkout flow for card payments.

    The feature remains dormant until STRIPE_SECRET_KEY is configured. Prices are
    always recalculated server-side and availability is rechecked against Booking
    before a Stripe Checkout Session is created.
    """

    def ensure_column(conn, table, column, definition):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    with db() as conn:
        ensure_column(conn, "bookings", "paid", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "bookings", "paid_at", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "hold_expires_at", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "released_at", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "release_reason", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "payment_error", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "checkout_payload", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "stripe_session_id", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "stripe_payment_intent_id", "TEXT DEFAULT ''")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookings_stripe_session ON bookings(stripe_session_id)"
        )

    def cors_headers():
        origin = request.headers.get("Origin", "").rstrip("/")
        configured = os.environ.get("DIRECT_BOOKING_ORIGIN", DEFAULT_DIRECT_ORIGIN).rstrip("/")
        local = origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")
        allowed = origin == configured or local
        return {
            "Access-Control-Allow-Origin": origin if allowed else configured,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400",
            "Vary": "Origin",
            "Cache-Control": "no-store",
        }

    def api_json(payload, status=200):
        response = jsonify(payload)
        response.status_code = status
        for key, value in cors_headers().items():
            response.headers[key] = value
        return response

    def secret_key():
        return os.environ.get("STRIPE_SECRET_KEY", "").strip()

    def checkout_base_url():
        configured = os.environ.get("PUBLIC_CHECKOUT_BASE_URL", "").strip().rstrip("/")
        if configured:
            return configured
        return request.host_url.rstrip("/")

    def stripe_http(method, path, *, params=None):
        key = secret_key()
        if not key:
            raise RuntimeError("Kartenzahlung ist noch nicht aktiviert.")
        body = None
        if params is not None:
            body = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(
            STRIPE_API_BASE + path,
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
                message = (detail.get("error") or {}).get("message") or raw
            except Exception:
                message = raw or str(exc)
            raise RuntimeError(f"Stripe HTTP {exc.code}: {message}") from exc

    def release_expired():
        extension = app.extensions.get("zab_release_expired_holds")
        if extension:
            try:
                extension()
                return
            except Exception:
                pass
        now_iso = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            conn.execute(
                """UPDATE bookings
                   SET status='cancelled', released_at=?, release_reason='Zahlungsfrist abgelaufen'
                   WHERE status='pending' AND COALESCE(paid,0)=0
                     AND COALESCE(hold_expires_at,'')!='' AND hold_expires_at<=?""",
                (now_iso, now_iso),
            )

    def ensure_live_calendar(room):
        if room not in rooms:
            return False, "Unbekanntes Zimmer."
        release_expired()
        count, message = sync_room(room)
        if message != "Synchronisierung erfolgreich.":
            return False, "Der Booking-Kalender konnte gerade nicht sicher aktualisiert werden."
        with db() as conn:
            row = conn.execute(
                "SELECT import_url,last_sync FROM ical_settings WHERE room=?", (room,)
            ).fetchone()
        if not row or not (row["import_url"] or "").strip():
            return False, "Für dieses Zimmer ist noch kein Booking-Kalender verbunden."
        try:
            synced = datetime.fromisoformat(row["last_sync"])
        except Exception:
            return False, "Der Kalenderstatus ist nicht aktuell genug für eine Sofortzahlung."
        if datetime.now() - synced > timedelta(minutes=5):
            return False, "Der Kalenderstatus ist nicht aktuell genug für eine Sofortzahlung."
        return True, f"Booking-Kalender aktuell ({count} Sperrtermine eingelesen)."

    def parse_payload(require_customer=False):
        data = request.get_json(silent=True) or {}
        try:
            room = str(data.get("room", "")).strip()
            arrival = parse_date(str(data.get("arrival", "")))
            departure = parse_date(str(data.get("departure", "")))
            adults = max(1, min(2, int(data.get("adults", 2))))
        except Exception as exc:
            raise ValueError("Bitte gültige Reisedaten eingeben.") from exc
        if room != "Bachblick":
            raise ValueError("Derzeit ist ausschließlich Bachblick für Direktbuchungen freigegeben.")
        if room not in rooms or departure <= arrival:
            raise ValueError("Bitte gültiges Zimmer sowie An- und Abreise wählen.")
        extras_raw = data.get("extras") if isinstance(data.get("extras"), dict) else {}
        chosen = {
            "breakfast": bool(extras_raw.get("breakfast")),
            "jause": bool(extras_raw.get("jause")),
            "luggage": bool(extras_raw.get("luggage")),
            "dog": False,
            "baby_bed": False,
        }
        if chosen["luggage"]:
            raise ValueError(
                "Gepäcktransport hat einen streckenabhängigen Preis und kann nicht automatisch per Karte bezahlt werden."
            )
        customer = {
            "first_name": str(data.get("first_name", "")).strip(),
            "last_name": str(data.get("last_name", "")).strip(),
            "email": str(data.get("email", "")).strip(),
            "phone": str(data.get("phone", "")).strip(),
            "message": str(data.get("message", "")).strip(),
        }
        if require_customer and not all(customer[k] for k in ("first_name", "last_name", "email", "phone")):
            raise ValueError("Bitte Name, E-Mail und Telefonnummer vollständig eingeben.")
        return data, room, arrival, departure, adults, chosen, customer

    def finalize_paid_session(session):
        session_id = str(session.get("id", ""))
        metadata = session.get("metadata") or {}
        booking_id = int(metadata.get("booking_id") or 0)
        if not session_id or not booking_id or session.get("payment_status") != "paid":
            return False, booking_id
        with db() as conn:
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if not booking or str(booking["stripe_session_id"] or "") != session_id:
                return False, booking_id
            expected = int(round(float(booking["total"]) * 100))
            if int(session.get("amount_total") or 0) != expected or str(session.get("currency", "")).lower() != "eur":
                conn.execute(
                    "UPDATE bookings SET payment_error=? WHERE id=?",
                    ("Stripe-Betrag oder Währung stimmt nicht überein", booking_id),
                )
                return False, booking_id
            paid_at = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                """UPDATE bookings
                   SET status='confirmed', paid=1, paid_at=?, hold_expires_at='',
                       released_at='', release_reason='', payment_error='',
                       stripe_payment_intent_id=?
                   WHERE id=?""",
                (paid_at, str(session.get("payment_intent") or ""), booking_id),
            )
        alert = app.extensions.get("zab_send_priority_alert")
        if alert:
            try:
                alert(booking_id, "confirmed")
            except Exception:
                pass
        return True, booking_id

    @app.route("/api/stripe/status", methods=["GET", "OPTIONS"])
    def stripe_status():
        if request.method == "OPTIONS":
            return Response(status=204, headers=cors_headers())
        return api_json(
            {
                "ok": True,
                "configured": bool(secret_key()),
                "webhook_configured": bool(os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()),
            }
        )

    @app.route("/api/stripe/create-checkout-session", methods=["POST", "OPTIONS"])
    def stripe_create_session():
        if request.method == "OPTIONS":
            return Response(status=204, headers=cors_headers())
        if not secret_key():
            return api_json({"ok": False, "message": "Kartenzahlung ist noch nicht aktiviert."}, 503)
        try:
            _, room, arrival, departure, adults, chosen, customer = parse_payload(True)
            ok_sync, sync_message = ensure_live_calendar(room)
            if not ok_sync:
                return api_json({"ok": False, "message": sync_message}, 409)
            breakdown = price_breakdown(room, arrival, departure, adults, chosen)
            total = Decimal(str(breakdown["total"])).quantize(Decimal("0.01"))
            if total <= 0:
                return api_json({"ok": False, "message": "Ungültiger Gesamtpreis."}, 400)

            uid = f"ZAB-CARD-{uuid4()}@zuhause-am-bach"
            now = datetime.now()
            hold_expires = now + timedelta(minutes=HOLD_MINUTES)
            payload_store = json.dumps(
                {"extras": chosen, "breakdown": breakdown, "source": "github-pages-stripe"},
                ensure_ascii=False,
            )
            try:
                with db() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    ok, message = room_available_in_conn(conn, room, arrival, departure)
                    if not ok:
                        conn.rollback()
                        return api_json({"ok": False, "message": message}, 409)
                    cur = conn.execute(
                        """INSERT INTO bookings
                           (uid,room,arrival,departure,adults,breakfast,first_name,last_name,
                            email,phone,message,payment_method,total,status,created_at,
                            paid,hold_expires_at,checkout_payload)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,0,?,?)""",
                        (
                            uid, room, arrival.isoformat(), departure.isoformat(), adults,
                            1 if chosen["breakfast"] else 0,
                            customer["first_name"], customer["last_name"], customer["email"],
                            customer["phone"], customer["message"], "stripe_checkout",
                            float(total), now.isoformat(timespec="seconds"),
                            hold_expires.isoformat(timespec="seconds"), payload_store,
                        ),
                    )
                    booking_id = int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return api_json({"ok": False, "message": "Der Termin wurde gerade anderweitig reserviert."}, 409)

            base = checkout_base_url()
            success_url = f"{base}/stripe/success?session_id={{CHECKOUT_SESSION_ID}}&booking={booking_id}"
            cancel_url = f"{base}/stripe/cancel?booking={booking_id}"
            expires_at = int(time.time()) + (HOLD_MINUTES * 60)
            params = {
                "mode": "payment",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "customer_email": customer["email"],
                "line_items[0][price_data][currency]": "eur",
                "line_items[0][price_data][unit_amount]": str(int(total * 100)),
                "line_items[0][price_data][product_data][name]": "Zuhause am Bach – Wachau · Bachblick",
                "line_items[0][quantity]": "1",
                "metadata[booking_id]": str(booking_id),
                "metadata[arrival]": arrival.isoformat(),
                "metadata[departure]": departure.isoformat(),
                "expires_at": str(expires_at),
                "locale": "auto",
            }
            try:
                session = stripe_http("POST", "/checkout/sessions", params=params)
                session_id = str(session.get("id", ""))
                checkout_url = str(session.get("url", ""))
                if not session_id or not checkout_url:
                    raise RuntimeError("Stripe hat keinen Checkout-Link geliefert.")
                with db() as conn:
                    conn.execute(
                        "UPDATE bookings SET stripe_session_id=? WHERE id=?",
                        (session_id, booking_id),
                    )
                return api_json(
                    {
                        "ok": True,
                        "configured": True,
                        "booking_id": booking_id,
                        "checkout_url": checkout_url,
                        "total": float(total),
                        "currency": "EUR",
                    }
                )
            except Exception as exc:
                with db() as conn:
                    conn.execute(
                        """UPDATE bookings SET status='cancelled', released_at=?,
                           release_reason='Stripe Session konnte nicht erstellt werden', payment_error=?
                           WHERE id=? AND COALESCE(paid,0)=0""",
                        (datetime.now().isoformat(timespec="seconds"), str(exc)[:500], booking_id),
                    )
                return api_json({"ok": False, "message": f"Kartenzahlung derzeit nicht verfügbar: {exc}"}, 503)
        except ValueError as exc:
            return api_json({"ok": False, "message": str(exc)}, 409)
        except Exception as exc:
            return api_json({"ok": False, "message": f"Kartenzahlung derzeit nicht verfügbar: {exc}"}, 503)

    @app.get("/stripe/success")
    def stripe_success():
        session_id = request.args.get("session_id", "").strip()
        booking_id = request.args.get("booking", type=int)
        if not session_id or not booking_id or not secret_key():
            return redirect(os.environ.get("STRIPE_RETURN_URL", DEFAULT_RETURN_URL) + "?payment=error")
        try:
            session = stripe_http("GET", "/checkout/sessions/" + urllib.parse.quote(session_id, safe=""))
            ok, verified_booking_id = finalize_paid_session(session)
            if not ok or verified_booking_id != booking_id:
                return redirect(os.environ.get("STRIPE_RETURN_URL", DEFAULT_RETURN_URL) + "?payment=error")
            return render_template_string(
                """<!doctype html><html lang='de'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Zahlung bestätigt</title><body style='font-family:Arial,sans-serif;max-width:680px;margin:60px auto;padding:24px'><h1>✅ Kartenzahlung bestätigt</h1><p>Ihre Buchung bei <strong>Zuhause am Bach – Wachau</strong> wurde bezahlt und verbindlich bestätigt.</p><p>Buchungsnummer: {{ booking_id }}</p><p><a href='{{ return_url }}'>Zurück zur Unterkunftsseite</a></p></body></html>""",
                booking_id=booking_id,
                return_url=os.environ.get("STRIPE_RETURN_URL", DEFAULT_RETURN_URL),
            ), 200
        except Exception:
            return redirect(os.environ.get("STRIPE_RETURN_URL", DEFAULT_RETURN_URL) + "?payment=error")

    @app.get("/stripe/cancel")
    def stripe_cancel():
        booking_id = request.args.get("booking", type=int)
        if booking_id:
            with db() as conn:
                conn.execute(
                    """UPDATE bookings SET status='cancelled', released_at=?,
                       release_reason='Kartenzahlung abgebrochen'
                       WHERE id=? AND COALESCE(paid,0)=0""",
                    (datetime.now().isoformat(timespec="seconds"), booking_id),
                )
        return redirect(os.environ.get("STRIPE_RETURN_URL", DEFAULT_RETURN_URL) + "?payment=cancelled")

    app.extensions["zab_stripe_checkout_enabled"] = bool(secret_key())
    return {"configured": bool(secret_key())}
