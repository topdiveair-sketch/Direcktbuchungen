"""Authenticated Growth Cockpit execution gateway for Railway."""

from __future__ import annotations

import hmac
import html
import json
import os
from datetime import datetime
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Response, jsonify, request

from railway_app import app, db

RESEND_API_BASE = "https://api.resend.com"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _settings() -> dict[str, str]:
    with db() as conn:
        return {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM site_settings")}


def _gateway_token() -> str:
    return os.environ.get("GROWTH_WEBHOOK_TOKEN", "").strip()


def _authorized() -> bool:
    token = _gateway_token()
    supplied = request.headers.get("Authorization", "")
    expected = f"Bearer {token}" if token else ""
    return bool(token) and hmac.compare_digest(supplied, expected)


def _valid_email(value: str) -> bool:
    _, addr = parseaddr(value or "")
    return bool(addr and "@" in addr and "." in addr.rsplit("@", 1)[-1])


def _resolve_verified_recipient(recipient_ref: str) -> str:
    ref = str(recipient_ref or "").strip()
    if not ref:
        return ""
    with db() as conn:
        row = conn.execute(
            "SELECT email FROM growth_windis_partners WHERE partner=? AND email_verified=1",
            (ref,),
        ).fetchone()
    return str(row["email"] or "").strip() if row else ""


def _resend_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def _resend_request(method: str, path: str, payload: dict | None = None, idempotency_key: str = "") -> tuple[int, dict]:
    key = _resend_key()
    if not key:
        return 0, {"error": "resend_api_key_not_configured"}
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:256]
    req = Request(f"{RESEND_API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"message": raw[:500]}
        return int(exc.code), body
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"resend_network_error:{type(exc).__name__}"}


def _verified_resend_domains() -> tuple[bool, list[str], str]:
    status, body = _resend_request("GET", "/domains")
    if status != 200:
        detail = body.get("message") or body.get("error") or f"http_{status}"
        return False, [], f"resend_api_unavailable:{detail}"
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        rows = []
    domains = [
        str(row.get("name") or "").strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("status") or "").lower() == "verified" and row.get("name")
    ]
    if not domains:
        return False, [], "resend_no_verified_domain"
    return True, domains, "resend_ready"


def _resend_sender() -> tuple[str, str]:
    explicit = os.environ.get("RESEND_FROM", "").strip()
    ok, domains, detail = _verified_resend_domains()
    if not ok:
        return "", detail
    if explicit:
        _, addr = parseaddr(explicit)
        domain = addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""
        if domain not in {item.lower() for item in domains}:
            return "", "resend_from_domain_not_verified"
        return explicit, "resend_ready"
    return f"Wilde Wachauer Windis <windis@{domains[0]}>", "resend_ready"


def _resend_verify() -> tuple[bool, str, str]:
    if not _resend_key():
        return False, "", "resend_api_key_not_configured"
    sender, detail = _resend_sender()
    return bool(sender), sender, detail


def _send_mail(recipient: str, subject: str, body: str, approval_id: str) -> tuple[bool, str]:
    sender, detail = _resend_sender()
    if not sender:
        return False, detail
    status, result = _resend_request(
        "POST",
        "/emails",
        {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "text": body,
        },
        idempotency_key=f"growth-outreach-{approval_id}",
    )
    if status in {200, 201} and result.get("id"):
        return True, f"resend_sent:{result['id']}"
    error = result.get("message") or result.get("error") or f"http_{status}"
    return False, f"resend_send_failed:{error}"


def _init_growth_tables() -> None:
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS growth_publications (
                id INTEGER PRIMARY KEY AUTOINCREMENT, approval_id TEXT NOT NULL UNIQUE,
                brand TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
                channel TEXT DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS growth_outreach_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, approval_id TEXT NOT NULL UNIQUE,
                recipient TEXT NOT NULL, subject TEXT NOT NULL, status TEXT NOT NULL,
                detail TEXT DEFAULT '', created_at TEXT NOT NULL
            );
        """)


_init_growth_tables()

import windis_data_gateway  # noqa: E402,F401
import windis_public_gateway  # noqa: E402,F401


@app.get("/health/growth-channels")
def growth_channel_health():
    resend_ok, sender, resend_detail = _resend_verify()
    with db() as conn:
        verified = conn.execute(
            "SELECT COUNT(*) AS n FROM growth_windis_partners WHERE email_verified=1 AND COALESCE(email,'')<>''"
        ).fetchone()["n"]
        outreach_count = conn.execute("SELECT COUNT(*) AS n FROM growth_outreach_log").fetchone()["n"]
        last_outreach = conn.execute(
            "SELECT status,detail,created_at FROM growth_outreach_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {
        "ok": True,
        "gateway_token_configured": bool(_gateway_token()),
        "mail_transport": "resend_https",
        "resend_configured": bool(_resend_key()),
        "resend_ready": resend_ok,
        "resend_status": resend_detail,
        "resend_sender_configured": bool(sender),
        "verified_recipient_count": int(verified or 0),
        "outreach_log_count": int(outreach_count or 0),
        "last_outreach": dict(last_outreach) if last_outreach else None,
        "publish_endpoint": "/growth/action",
        "outreach_endpoint": "/growth/action",
        "windis_data_endpoint": "/growth/windis-planning-data",
    }, 200


@app.get("/growth/action/verify")
def growth_action_verify():
    if not _gateway_token():
        return jsonify({"error": "growth_webhook_token_not_configured"}), 503
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401

    recipient_ref = str(request.args.get("recipientRef") or "").strip()
    recipient = _resolve_verified_recipient(recipient_ref) if recipient_ref else ""
    resend_ok, sender, resend_detail = _resend_verify()
    recipient_ok = bool(recipient and _valid_email(recipient))
    body = {
        "ok": resend_ok and recipient_ok,
        "transport": "resend_https",
        "resendConfigured": bool(_resend_key()),
        "resendReady": resend_ok,
        "resendStatus": resend_detail,
        "senderConfigured": bool(sender),
        "recipientVerified": recipient_ok,
    }
    return jsonify(body), 200 if body["ok"] else 503


@app.post("/growth/action")
def growth_action():
    if not _gateway_token():
        return jsonify({"error": "growth_webhook_token_not_configured"}), 503
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    approval_id = str(payload.get("approvalId") or "").strip()
    kind = str(payload.get("kind") or "").strip()
    brand = str(payload.get("brand") or "").strip()
    message = str(payload.get("message") or "").strip()
    task = str(payload.get("task") or "").strip()
    channel = str(payload.get("channel") or "").strip()

    if not approval_id or kind not in {"publish", "sendExternalMessage"}:
        return jsonify({"error": "invalid_action"}), 400
    if not message:
        return jsonify({"error": "reviewed_content_required"}), 422
    if len(message) > 20000:
        return jsonify({"error": "message_too_long"}), 422

    if kind == "publish":
        with db() as conn:
            existing = conn.execute(
                "SELECT id FROM growth_publications WHERE approval_id=?", (approval_id,)
            ).fetchone()
            if existing:
                public_url = request.host_url.rstrip("/") + f"/growth/publications/{existing['id']}"
                return jsonify({"ok": True, "idempotent": True, "publicUrl": public_url}), 200
            title = task or "Aktuelle Empfehlung"
            cur = conn.execute(
                "INSERT INTO growth_publications(approval_id,brand,title,body,channel,created_at) VALUES(?,?,?,?,?,?)",
                (approval_id, brand or "unknown", title[:240], message, channel, _now()),
            )
            publication_id = cur.lastrowid
        return jsonify({
            "ok": True,
            "published": True,
            "publicUrl": request.host_url.rstrip("/") + f"/growth/publications/{publication_id}",
        }), 201

    recipient = str(payload.get("recipient") or "").strip()
    recipient_ref = str(payload.get("recipientRef") or "").strip()
    if not recipient and recipient_ref:
        recipient = _resolve_verified_recipient(recipient_ref)
    subject = str(payload.get("subject") or "Kooperationsanfrage Wilde Wachauer Windis").strip()[:240]

    if not _valid_email(recipient):
        return jsonify({"error": "verified_recipient_required"}), 422

    with db() as conn:
        existing = conn.execute(
            "SELECT status,detail FROM growth_outreach_log WHERE approval_id=?", (approval_id,)
        ).fetchone()
        if existing and existing["status"] == "sent":
            return jsonify({"ok": True, "idempotent": True, "sent": True}), 200

    ok, detail = _send_mail(recipient, subject, message, approval_id)
    with db() as conn:
        conn.execute(
            """INSERT INTO growth_outreach_log(approval_id,recipient,subject,status,detail,created_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(approval_id) DO UPDATE SET recipient=excluded.recipient,
               subject=excluded.subject,status=excluded.status,detail=excluded.detail,
               created_at=excluded.created_at""",
            (approval_id, recipient, subject, "sent" if ok else "failed", detail, _now()),
        )

    if not ok:
        return jsonify({"error": detail}), 502
    return jsonify({"ok": True, "sent": True, "recipientResolved": True, "transport": "resend_https"}), 200


@app.get("/growth/publications")
def growth_publications():
    with db() as conn:
        rows = conn.execute(
            "SELECT id,brand,title,body,channel,created_at FROM growth_publications ORDER BY id DESC LIMIT 50"
        ).fetchall()
    return jsonify({"ok": True, "publications": [dict(row) for row in rows]}), 200


@app.get("/growth/publications/<int:publication_id>")
def growth_publication_page(publication_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT id,brand,title,body,channel,created_at FROM growth_publications WHERE id=?",
            (publication_id,),
        ).fetchone()
        settings = {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM site_settings")}
    if not row:
        return Response("Not found", status=404, content_type="text/plain; charset=utf-8")

    booking_url = settings.get("public_base_url", "").strip()
    cta = (
        f'<p><a href="{html.escape(booking_url, quote=True)}" style="display:inline-block;padding:12px 18px;background:#174b2c;color:#fff;text-decoration:none;border-radius:10px;font-weight:700">Direkt buchen</a></p>'
        if row["brand"] == "zuhause_am_bach" and booking_url else ""
    )
    body_html = "<br>".join(html.escape(row["body"]).splitlines())
    page = f"""<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(row['title'])}</title><style>body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f4f6f4;color:#132319;margin:0}}main{{max-width:760px;margin:6vh auto;padding:30px;background:#fff;border:1px solid #dde4df;border-radius:18px}}h1{{line-height:1.15}}.meta{{color:#6b776f;font-size:14px}}.copy{{font-size:18px;line-height:1.65;margin:26px 0}}</style></head><body><main><div class=\"meta\">{html.escape(row['brand'])} · {html.escape(row['created_at'])}</div><h1>{html.escape(row['title'])}</h1><div class=\"copy\">{body_html}</div>{cta}</main></body></html>"""
    return Response(page, content_type="text/html; charset=utf-8")
