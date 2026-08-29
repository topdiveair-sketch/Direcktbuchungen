"""Authenticated Growth Cockpit execution gateway for Railway."""

from __future__ import annotations

import hmac
import html
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import parseaddr

from flask import Response, jsonify, request

from railway_app import app, db


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


def _smtp_config() -> dict[str, str]:
    cfg = _settings()
    return {
        "host": os.environ.get("SMTP_HOST", "").strip() or cfg.get("smtp_host", "").strip(),
        "port": os.environ.get("SMTP_PORT", "").strip() or cfg.get("smtp_port", "587").strip(),
        "user": os.environ.get("SMTP_USER", "").strip() or cfg.get("smtp_user", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", "").strip() or cfg.get("smtp_password", "").strip(),
        "sender": os.environ.get("SMTP_SENDER", "").strip() or cfg.get("smtp_sender", "").strip(),
    }


def _smtp_ready() -> bool:
    cfg = _smtp_config()
    return bool(cfg["host"] and cfg["user"] and cfg["password"])


def _smtp_error_code(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "smtp_auth_failed"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "smtp_recipient_refused"
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "smtp_sender_refused"
    if isinstance(exc, smtplib.SMTPConnectError):
        return "smtp_connect_failed"
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "smtp_tls_not_supported"
    if isinstance(exc, TimeoutError):
        return "smtp_timeout"
    if isinstance(exc, OSError):
        errno = getattr(exc, "errno", None)
        return f"smtp_os_error:{errno if errno is not None else 'unknown'}"
    return f"smtp_error:{type(exc).__name__}"


def _smtp_ports(cfg: dict[str, str]) -> list[int]:
    configured = int(cfg.get("port") or 587)
    ports = [configured]
    if cfg.get("host", "").lower() in {"smtp.gmail.com", "smtp.googlemail.com"}:
        for candidate in (587, 465):
            if candidate not in ports:
                ports.append(candidate)
    return ports


def _smtp_login_once(cfg: dict[str, str], port: int):
    if port == 465:
        server = smtplib.SMTP_SSL(cfg["host"], port, timeout=15)
    else:
        server = smtplib.SMTP(cfg["host"], port, timeout=15)
        server.ehlo()
        if server.has_extn("starttls"):
            server.starttls()
            server.ehlo()
    server.login(cfg["user"], cfg["password"])
    return server


def _smtp_login_check() -> tuple[bool, str]:
    cfg = _smtp_config()
    if not _smtp_ready():
        return False, "smtp_not_configured"
    failures = []
    for port in _smtp_ports(cfg):
        try:
            server = _smtp_login_once(cfg, port)
            server.quit()
            return True, f"smtp_authenticated:{port}"
        except Exception as exc:
            failures.append(f"{port}={_smtp_error_code(exc)}")
    return False, "smtp_all_transports_failed:" + ",".join(failures)


def _send_mail(recipient: str, subject: str, body: str) -> tuple[bool, str]:
    cfg = _smtp_config()
    if not _smtp_ready():
        return False, "smtp_not_configured"

    msg = EmailMessage()
    msg["From"] = cfg["sender"] or cfg["user"]
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    failures = []
    for port in _smtp_ports(cfg):
        try:
            server = _smtp_login_once(cfg, port)
            try:
                server.send_message(msg)
            finally:
                server.quit()
            return True, f"sent:{port}"
        except Exception as exc:
            failures.append(f"{port}={_smtp_error_code(exc)}")
    return False, "smtp_all_transports_failed:" + ",".join(failures)


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
    smtp_ok, smtp_detail = _smtp_login_check()
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
        "smtp_configured": _smtp_ready(),
        "smtp_authenticated": smtp_ok,
        "smtp_status": smtp_detail,
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
    smtp_ok, smtp_detail = _smtp_login_check()
    body = {
        "ok": smtp_ok and bool(recipient and _valid_email(recipient)),
        "smtpConfigured": _smtp_ready(),
        "smtpAuthenticated": smtp_ok,
        "smtpStatus": smtp_detail,
        "recipientVerified": bool(recipient and _valid_email(recipient)),
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

    ok, detail = _send_mail(recipient, subject, message)
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
    return jsonify({"ok": True, "sent": True, "recipientResolved": True, "transport": detail}), 200


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
