from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage


DEFAULT_SENDER_EMAIL = "buchung@zuhauseambach-wachau.at"
DEFAULT_SENDER_NAME = "Zuhause am Bach – Wachau"
DEFAULT_REPLY_TO = "Zuhause.am.Bach@outlook.com"


def send_transactional_email(
    to: str,
    subject: str,
    body: str,
    *,
    settings: dict | None = None,
    reply_to: str | None = None,
    important: bool = False,
):
    """Send through Resend first and fall back to authenticated SMTP."""
    cfg = settings or {}
    resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender_email = os.environ.get("MAIL_SENDER_EMAIL", DEFAULT_SENDER_EMAIL).strip()
    sender_name = os.environ.get("MAIL_SENDER_NAME", DEFAULT_SENDER_NAME).strip()
    reply_to = (
        (reply_to or "").strip()
        or os.environ.get("MAIL_REPLY_TO", "").strip()
        or cfg.get("email", "").strip()
        or DEFAULT_REPLY_TO
    )

    if resend_key and sender_email:
        payload = {
            "from": f"{sender_name} <{sender_email}>",
            "to": [to],
            "subject": subject,
            "text": body,
            "reply_to": reply_to,
            "headers": {
                "X-Entity-Ref-ID": "zab-transactional",
            },
        }
        if important:
            payload["headers"].update({
                "Importance": "high",
                "Priority": "urgent",
                "X-Priority": "1",
                "X-MSMail-Priority": "High",
            })
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {resend_key}",
                "Content-Type": "application/json",
                "User-Agent": "ZAB-Booking/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                if 200 <= int(response.status) < 300:
                    return True, "gesendet"
        except urllib.error.HTTPError:
            pass
        except (urllib.error.URLError, TimeoutError, OSError):
            pass

    host = cfg.get("smtp_host", "")
    user = cfg.get("smtp_user", "")
    password = cfg.get("smtp_password", "")
    port = int(cfg.get("smtp_port", "587") or 587)
    sender = cfg.get("smtp_sender", user or cfg.get("email", ""))
    if not host or not user or not password:
        return False, "mail_provider_not_configured"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    if important:
        msg["Importance"] = "high"
        msg["Priority"] = "urgent"
        msg["X-Priority"] = "1"
        msg["X-MSMail-Priority"] = "High"
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True, "gesendet"
    except smtplib.SMTPAuthenticationError:
        return False, "smtp_auth_failed"
    except (smtplib.SMTPException, OSError, TimeoutError):
        return False, "smtp_delivery_failed"
    except Exception:
        return False, "smtp_delivery_failed"
