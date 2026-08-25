from __future__ import annotations

import base64
import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from flask import Response, jsonify, redirect, render_template_string, request


HOLD_MINUTES = 30
DEFAULT_DIRECT_ORIGIN = "https://topdiveair-sketch.github.io"


def init_paypal_checkout(
    app,
    db,
    rooms,
    parse_date,
    price_breakdown,
    room_available_in_conn,
    sync_room,
):
    """Register a server-verified PayPal checkout for direct bookings.

    Flow:
    1. Re-sync Booking iCal before quoting/booking.
    2. Recheck availability inside BEGIN IMMEDIATE.
    3. Create a local pending booking and hold it for 30 minutes.
    4. Create a PayPal order with the server-side amount.
    5. After PayPal approval, capture on the server.
    6. Only a COMPLETED capture marks the booking paid + confirmed.
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
        ensure_column(conn, "bookings", "paypal_order_id", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "paypal_capture_id", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "payment_error", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "checkout_payload", "TEXT DEFAULT ''")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookings_paypal_order ON bookings(paypal_order_id)"
        )

    def cors_headers():
        origin = request.headers.get("Origin", "")
        configured = os.environ.get("DIRECT_BOOKING_ORIGIN", DEFAULT_DIRECT_ORIGIN).rstrip("/")
        local = origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")
        allowed = origin == configured or local
        return {
            "Access-Control-Allow-Origin": origin if allowed else configured,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
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

    def paypal_api_base():
        env = os.environ.get("PAYPAL_ENV", "live").strip().lower()
        return "https://api-m.sandbox.paypal.com" if env == "sandbox" else "https://api-m.paypal.com"

    def paypal_credentials():
        client_id = os.environ.get("PAYPAL_CLIENT_ID", "").strip()
        secret = os.environ.get("PAYPAL_CLIENT_SECRET", "").strip()
        if not client_id or not secret:
            raise RuntimeError("PayPal API-Zugang ist noch nicht eingerichtet.")
        return client_id, secret

    def paypal_http(method, path, *, token="", payload=None, request_id=""):
        url = paypal_api_base() + path
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if request_id:
            headers["PayPal-Request-Id"] = request_id[:108]
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
            except Exception:
                detail = {"message": raw or str(exc)}
            summary = detail.get("message") or detail.get("name") or raw
            details = detail.get("details") or []
            if details:
                first = details[0] or {}
                issue = first.get("issue", "")
                description = first.get("description", "")
                field = first.get("field", "")
                extra = ": ".join(part for part in (issue, description) if part)
                if field:
                    extra = f"{extra} [{field}]" if extra else field
                if extra:
                    summary = f"{summary} – {extra}"
            debug_id = detail.get("debug_id", "")
            if debug_id:
                summary = f"{summary} (PayPal debug_id {debug_id})"
            raise RuntimeError(f"PayPal HTTP {exc.code}: {summary}") from exc

    def paypal_token():
        client_id, secret = paypal_credentials()
        auth = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            paypal_api_base() + "/v1/oauth2/token",
            data=b"grant_type=client_credentials",
            headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/json",
                "Accept-Language": "de_AT",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"PayPal Anmeldung fehlgeschlagen ({exc.code}): {raw}") from exc
        token = data.get("access_token", "")
        if not token:
            raise RuntimeError("PayPal hat kein Access-Token geliefert.")
        return token

    def checkout_base_url():
        configured = os.environ.get("PUBLIC_CHECKOUT_BASE_URL", "").strip().rstrip("/")
        if configured:
            return configured
        if os.environ.get("APP_ENV", "").lower() == "production" or os.environ.get("RAILWAY_ENVIRONMENT"):
            raise RuntimeError("PUBLIC_CHECKOUT_BASE_URL fehlt in Railway.")
        return request.host_url.rstrip("/")

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
            return False, "Der Booking-Kalender konnte gerade nicht sicher aktualisiert werden. Bitte später erneut versuchen."
        with db() as conn:
            row = conn.execute(
                "SELECT import_url,last_sync,last_result FROM ical_settings WHERE room=?",
                (room,),
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
                "Gepäcktransport hat einen streckenabhängigen Preis und kann deshalb nicht automatisch über PayPal abgeschlossen werden. Bitte ohne Gepäcktransport bezahlen oder eine Anfrage senden."
            )
        customer = {
            "first_name": str(data.get("first_name", "")).strip(),
            "last_name": str(data.get("last_name", "")).strip(),
            "email": str(data.get("email", "")).strip(),
            "phone": str(data.get("phone", "")).strip(),
            "message": str(data.get("message", "")).strip(),
        }
        if require_customer and not all(customer[key] for key in ("first_name", "last_name", "email", "phone")):
            raise ValueError("Bitte Name, E-Mail und Telefonnummer vollständig eingeben.")
        return data, room, arrival, departure, adults, chosen, customer

    def authoritative_quote(room, arrival, departure, adults, chosen):
        ok_sync, sync_message = ensure_live_calendar(room)
        if not ok_sync:
            raise ValueError(sync_message)
        with db() as conn:
            ok, availability_message = room_available_in_conn(conn, room, arrival, departure)
        if not ok:
            raise ValueError(availability_message)
        breakdown = price_breakdown(room, arrival, departure, adults, chosen)
        return breakdown, sync_message

    @app.route("/api/paypal/quote", methods=["POST", "OPTIONS"])
    def paypal_quote():
        if request.method == "OPTIONS":
            return Response(status=204, headers=cors_headers())
        try:
            _, room, arrival, departure, adults, chosen, _ = parse_payload(False)
            breakdown, sync_message = authoritative_quote(room, arrival, departure, adults, chosen)
            return api_json(
                {
                    "ok": True,
                    "available": True,
                    "currency": "EUR",
                    "total": breakdown["total"],
                    "breakdown": breakdown,
                    "calendar": sync_message,
                }
            )
        except ValueError as exc:
            return api_json({"ok": False, "available": False, "message": str(exc)}, 409)
        except Exception as exc:
            return api_json({"ok": False, "message": f"Sofortpreis derzeit nicht verfügbar: {exc}"}, 503)

    @app.route("/api/paypal/create-order", methods=["POST", "OPTIONS"])
    def paypal_create_order():
        if request.method == "OPTIONS":
            return Response(status=204, headers=cors_headers())
        try:
            data, room, arrival, departure, adults, chosen, customer = parse_payload(True)
            ok_sync, sync_message = ensure_live_calendar(room)
            if not ok_sync:
                return api_json({"ok": False, "message": sync_message}, 409)

            breakdown = price_breakdown(room, arrival, departure, adults, chosen)
            total = Decimal(str(breakdown["total"])).quantize(Decimal("0.01"))
            if total <= 0:
                return api_json({"ok": False, "message": "Ungültiger Gesamtpreis."}, 400)

            uid = f"ZAB-PAY-{uuid4()}@zuhause-am-bach"
            now = datetime.now()
            hold_expires = now + timedelta(minutes=HOLD_MINUTES)
            payload_store = json.dumps(
                {
                    "extras": chosen,
                    "breakdown": breakdown,
                    "source": "github-pages-paypal",
                },
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
                            uid,
                            room,
                            arrival.isoformat(),
                            departure.isoformat(),
                            adults,
                            1 if chosen["breakfast"] else 0,
                            customer["first_name"],
                            customer["last_name"],
                            customer["email"],
                            customer["phone"],
                            customer["message"],
                            "paypal_checkout",
                            float(total),
                            now.isoformat(timespec="seconds"),
                            hold_expires.isoformat(timespec="seconds"),
                            payload_store,
                        ),
                    )
                    booking_id = cur.lastrowid
            except sqlite3.IntegrityError:
                return api_json({"ok": False, "message": "Der Termin wurde gerade anderweitig reserviert."}, 409)

            try:
                token = paypal_token()
                base = checkout_base_url()
                order = paypal_http(
                    "POST",
                    "/v2/checkout/orders",
                    token=token,
                    request_id=str(uuid4()),
                    payload={
                        "intent": "CAPTURE",
                        "purchase_units": [
                            {
                                "amount": {
                                    "currency_code": "EUR",
                                    "value": f"{total:.2f}",
                                }
                            }
                        ],
                        "payment_source": {
                            "paypal": {
                                "experience_context": {
                                    "return_url": f"{base}/paypal/return?booking={booking_id}",
                                    "cancel_url": f"{base}/paypal/cancel?booking={booking_id}",
                                }
                            }
                        },
                    },
                )
                order_id = str(order.get("id", ""))
                approval_url = next(
                    (
                        link.get("href")
                        for link in order.get("links", [])
                        if link.get("rel") in {"payer-action", "approve"}
                    ),
                    "",
                )
                if not order_id or not approval_url:
                    raise RuntimeError("PayPal hat keinen Freigabelink geliefert.")
                with db() as conn:
                    conn.execute(
                        "UPDATE bookings SET paypal_order_id=?,payment_error='' WHERE id=?",
                        (order_id, booking_id),
                    )
                return api_json(
                    {
                        "ok": True,
                        "booking_id": booking_id,
                        "order_id": order_id,
                        "approval_url": approval_url,
                        "total": float(total),
                        "currency": "EUR",
                        "hold_minutes": HOLD_MINUTES,
                        "hold_expires_at": hold_expires.isoformat(timespec="seconds"),
                    }
                )
            except Exception as exc:
                with db() as conn:
                    conn.execute(
                        """UPDATE bookings SET status='cancelled',released_at=?,
                           release_reason='PayPal-Auftrag konnte nicht erstellt werden',payment_error=?
                           WHERE id=? AND COALESCE(paid,0)=0""",
                        (datetime.now().isoformat(timespec="seconds"), str(exc)[:500], booking_id),
                    )
                return api_json({"ok": False, "message": f"PayPal konnte nicht gestartet werden: {exc}"}, 503)
        except ValueError as exc:
            return api_json({"ok": False, "message": str(exc)}, 400)
        except Exception as exc:
            return api_json({"ok": False, "message": f"Sofortbuchung derzeit nicht möglich: {exc}"}, 503)

    def capture_details(payload):
        captures = []
        for unit in payload.get("purchase_units", []) or []:
            captures.extend(((unit.get("payments") or {}).get("captures") or []))
        completed = [cap for cap in captures if cap.get("status") == "COMPLETED"]
        if not completed:
            return "", None, ""
        cap = completed[0]
        amount = cap.get("amount") or {}
        try:
            value = Decimal(str(amount.get("value", ""))).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            value = None
        return str(cap.get("id", "")), value, str(amount.get("currency_code", ""))

    def capture_or_read(order_id, token):
        try:
            return paypal_http(
                "POST",
                f"/v2/checkout/orders/{order_id}/capture",
                token=token,
                request_id=f"zab-capture-{order_id}",
                payload={},
            )
        except RuntimeError:
            current = paypal_http("GET", f"/v2/checkout/orders/{order_id}", token=token)
            if current.get("status") == "COMPLETED":
                return current
            raise

    SUCCESS_PAGE = """<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Buchung bestätigt</title><style>body{font-family:Arial,sans-serif;background:#f4f8f5;color:#17372f;margin:0;padding:32px}.card{max-width:680px;margin:6vh auto;background:white;padding:30px;border-radius:18px;box-shadow:0 18px 45px rgba(23,55,47,.12)}h1{color:#176b5a}.ok{font-size:42px}.btn{display:inline-block;margin-top:18px;padding:12px 18px;border-radius:10px;background:#176b5a;color:white;text-decoration:none;font-weight:800}</style></head><body><main class='card'><div class='ok'>✅</div><h1>Zahlung erfolgreich – Buchung bestätigt</h1><p>Vielen Dank, {{ name }}. Ihr Zimmer <strong>{{ room }}</strong> ist von <strong>{{ arrival }}</strong> bis <strong>{{ departure }}</strong> verbindlich für Sie reserviert.</p><p>Bezahlt: <strong>{{ total }} EUR</strong><br>PayPal-Transaktion: {{ capture }}</p><p>Wir freuen uns auf Ihren Aufenthalt bei Zuhause am Bach.</p><a class='btn' href='https://topdiveair-sketch.github.io/Direcktbuchungen/index'>Zurück zu Zuhause am Bach</a></main></body></html>"""

    ERROR_PAGE = """<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Zahlung nicht abgeschlossen</title><style>body{font-family:Arial,sans-serif;background:#fff8ef;color:#4d3820;margin:0;padding:32px}.card{max-width:680px;margin:6vh auto;background:white;padding:30px;border-radius:18px;box-shadow:0 18px 45px rgba(70,45,20,.12)}h1{color:#9a351f}.btn{display:inline-block;margin-top:18px;padding:12px 18px;border-radius:10px;background:#176b5a;color:white;text-decoration:none;font-weight:800}</style></head><body><main class='card'><h1>Zahlung nicht abgeschlossen</h1><p>{{ message }}</p><p>Es wurde keine bestätigte Direktbuchung erzeugt.</p><a class='btn' href='https://topdiveair-sketch.github.io/Direcktbuchungen/index'>Zurück zur Buchung</a></main></body></html>"""

    @app.get("/paypal/return")
    def paypal_return():
        booking_id = request.args.get("booking", type=int)
        order_id = request.args.get("token", "").strip()
        if not booking_id or not order_id:
            return render_template_string(ERROR_PAGE, message="PayPal-Rückgabe war unvollständig."), 400

        release_expired()
        with db() as conn:
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if not booking:
            return render_template_string(ERROR_PAGE, message="Buchung wurde nicht gefunden."), 404
        if booking["status"] == "cancelled" and not booking["paid"]:
            return render_template_string(ERROR_PAGE, message="Die Zahlungsfrist ist bereits abgelaufen."), 409
        stored_order = (booking["paypal_order_id"] or "").strip()
        if not stored_order or stored_order != order_id:
            return render_template_string(ERROR_PAGE, message="PayPal-Auftrag passt nicht zur Reservierung."), 409
        if booking["paid"] and booking["status"] == "confirmed":
            return render_template_string(
                SUCCESS_PAGE,
                name=booking["first_name"], room=booking["room"], arrival=booking["arrival"],
                departure=booking["departure"], total=f"{booking['total']:.2f}", capture=booking["paypal_capture_id"] or order_id,
            )

        try:
            token = paypal_token()
            captured = capture_or_read(order_id, token)
            if captured.get("status") != "COMPLETED":
                raise RuntimeError(f"PayPal-Status ist {captured.get('status', 'unbekannt')} statt COMPLETED.")
            capture_id, paid_amount, currency = capture_details(captured)
            expected = Decimal(str(booking["total"])).quantize(Decimal("0.01"))
            if not capture_id or paid_amount != expected or currency != "EUR":
                raise RuntimeError("PayPal-Zahlungsbetrag konnte nicht eindeutig verifiziert werden.")

            paid_at = datetime.now().isoformat(timespec="seconds")
            with db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                current = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
                if not current:
                    conn.rollback()
                    raise RuntimeError("Reservierung wurde zwischenzeitlich entfernt.")
                conn.execute(
                    """UPDATE bookings SET paid=1,paid_at=?,status='confirmed',paypal_capture_id=?,
                       hold_expires_at='',payment_error='',released_at='',release_reason=''
                       WHERE id=?""",
                    (paid_at, capture_id, booking_id),
                )

            return render_template_string(
                SUCCESS_PAGE,
                name=booking["first_name"], room=booking["room"], arrival=booking["arrival"],
                departure=booking["departure"], total=f"{booking['total']:.2f}", capture=capture_id,
            )
        except Exception as exc:
            with db() as conn:
                conn.execute("UPDATE bookings SET payment_error=? WHERE id=?", (str(exc)[:500], booking_id))
            return render_template_string(
                ERROR_PAGE,
                message="PayPal konnte die Zahlung nicht eindeutig bestätigen. Bitte nicht erneut zahlen; kontaktieren Sie uns, falls PayPal bereits eine Belastung anzeigt.",
            ), 502

    @app.get("/paypal/cancel")
    def paypal_cancel():
        booking_id = request.args.get("booking", type=int)
        if booking_id:
            with db() as conn:
                conn.execute(
                    """UPDATE bookings SET status='cancelled',released_at=?,
                       release_reason='PayPal-Zahlung vom Gast abgebrochen'
                       WHERE id=? AND COALESCE(paid,0)=0""",
                    (datetime.now().isoformat(timespec="seconds"), booking_id),
                )
        return render_template_string(
            ERROR_PAGE,
            message="Die PayPal-Zahlung wurde abgebrochen. Der vorläufig reservierte Termin wurde wieder freigegeben.",
        )

    app.extensions["zab_paypal_checkout_enabled"] = True