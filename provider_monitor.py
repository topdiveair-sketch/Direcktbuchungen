from __future__ import annotations

import hashlib
import json
import os
import re
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from html import unescape
from html.parser import HTMLParser

from flask import flash, jsonify, redirect, render_template, request, url_for


DIRECT_BOOKING_URL = "https://topdiveair-sketch.github.io/Direcktbuchungen/index"
PROPERTY_MARKERS = ("zuhause am bach", "zu hause am bach")

SEED_LISTINGS = [
    (
        "Booking.com",
        "OTA",
        "https://www.booking.com/hotel/at/zu-hause-am-bach.de.html?checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&group_children=0",
    ),
    (
        "Google Hotels",
        "Metasuche",
        "https://www.google.at/travel/hotels/entity/CgsIncbWpIupyZPWARAB",
    ),
    (
        "Agoda",
        "OTA/Partner",
        "https://www.agoda.com/zu-hause-am-bach/hotel/aggsbach-markt-at.html",
    ),
    (
        "HolidayCheck",
        "Vergleichsportal",
        "https://www.holidaycheck.at/hi/zuhause-am-bach-ruhige-unterkunft-fuer-erholungssuchende-am-welterbesteig-und-donauradweg/d66cc36b-7f57-4db0-8211-e5f75fcc669a",
    ),
    (
        "BedandBreakfast.eu",
        "Buchungsportal",
        "https://www.bedandbreakfast.eu/de/a/uPgcxyGpBIaE/zuhause-am-bach-ruhige-unterkunft-fur-erholungssuchende-am-welterbesteig-und-donauradweg",
    ),
    (
        "Planet of Hotels",
        "Buchungsportal",
        "https://de.planetofhotels.com/osterreich/aggsbach/zuhause-am-bach-ruhige-unterkunft-fur-erholungssuchende-am-welterbesteig-und-donauradweg",
    ),
    (
        "ViaMichelin",
        "Buchungsportal",
        "https://www.viamichelin.at/karten-stadtplan/hotels/poi/aggsbach-3641-0b55c4fb",
    ),
    (
        "Donau Niederoesterreich",
        "Tourismus",
        "https://www.donau.com/unterkunft/zu-hause-am-bach-wachau",
    ),
    (
        "Outdooractive Unterkunft",
        "Tourismus",
        "https://www.outdooractive.com/de/accommodation/donau-niederoesterreich/zuhause-am-bach-wachau/811335547/",
    ),
    (
        "Outdooractive Anbieterprofil",
        "Partnerprofil",
        "https://www.outdooractive.com/en/source/zuhause-am-bach-wachau-/809406434/",
    ),
    (
        "Marktgemeinde Aggsbach",
        "Gemeinde",
        "https://www.aggsbach.gv.at/Zuhause_am_Bach_-_Privatzimmervermietung",
    ),
    (
        "Eigene Direktbuchung",
        "Direkt",
        DIRECT_BOOKING_URL,
    ),
]


class _PageTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []
        self.meta_description = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if key in {"description", "og:description", "twitter:description"} and not self.meta_description:
                self.meta_description = attrs_dict.get("content", "").strip()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "template"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        clean = " ".join(str(data).split())
        if not clean:
            return
        self.text_parts.append(clean)
        if self._in_title:
            self.title_parts.append(clean)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean_text(value: str, limit: int = 12000) -> str:
    value = unescape(str(value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _render_url(url: str, horizon_days: int) -> str:
    checkin = date.today() + timedelta(days=max(1, horizon_days))
    checkout = checkin + timedelta(days=1)
    return (
        url.replace("{checkin}", checkin.isoformat())
        .replace("{checkout}", checkout.isoformat())
    )


def _request_page(url: str, horizon_days: int) -> tuple[int, str, str]:
    rendered = _render_url(url, horizon_days)
    req = urllib.request.Request(
        rendered,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0 Safari/537.36 ZuhauseAmBachMonitor/1.0"
            ),
            "Accept-Language": "de-AT,de;q=0.9,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.8,*/*;q=0.5",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(2_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            return int(response.status), raw.decode(charset, errors="replace"), rendered
    except urllib.error.HTTPError as exc:
        body = exc.read(200_000).decode("utf-8", errors="replace")
        return int(exc.code), body, rendered


def _jsonld_objects(html: str) -> list[dict]:
    found: list[dict] = []
    blocks = re.findall(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html,
        flags=re.I | re.S,
    )

    def walk(node):
        if isinstance(node, dict):
            found.append(node)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for block in blocks:
        try:
            walk(json.loads(unescape(block).strip()))
        except Exception:
            continue
    return found


def _preferred_jsonld(html: str) -> dict:
    objects = _jsonld_objects(html)
    if not objects:
        return {}
    scored: list[tuple[int, dict]] = []
    for obj in objects:
        name = str(obj.get("name") or "").lower()
        obj_type = str(obj.get("@type") or "").lower()
        score = 0
        if any(marker in name for marker in PROPERTY_MARKERS):
            score += 20
        if any(kind in obj_type for kind in ("hotel", "lodging", "bedandbreakfast", "product")):
            score += 5
        if obj.get("aggregateRating"):
            score += 3
        if obj.get("offers"):
            score += 2
        if obj.get("description"):
            score += 1
        scored.append((score, obj))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] else {}


def _normalize_number(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\xa0", " ")
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return ""
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return ""
    if number.is_integer():
        return str(int(number))
    return ("%.2f" % number).rstrip("0").rstrip(".")


def _extract_price(page_text: str, obj: dict) -> str:
    currency = ""
    candidates = []

    def take_offer(offer):
        nonlocal currency
        if not isinstance(offer, dict):
            return
        currency = str(offer.get("priceCurrency") or currency or "").upper()
        for key in ("price", "lowPrice", "highPrice"):
            if offer.get(key) is not None:
                candidates.append(offer.get(key))

    offers = obj.get("offers") if isinstance(obj, dict) else None
    if isinstance(offers, list):
        for offer in offers:
            take_offer(offer)
    else:
        take_offer(offers)
    if obj.get("price") is not None:
        candidates.append(obj.get("price"))
        currency = str(obj.get("priceCurrency") or currency or "").upper()

    for candidate in candidates:
        normalized = _normalize_number(candidate)
        if normalized:
            prefix = "€" if currency == "EUR" else ("$" if currency == "USD" else currency)
            return f"{prefix} {normalized}".strip()

    preferred_patterns = [
        r"(?:ab|from|starting at|preis(?:e)? ab)\s*€\s*([0-9]{1,4}(?:[.,][0-9]{1,2})?)",
        r"(?:ab|from|starting at|preis(?:e)? ab)\s*([0-9]{1,4}(?:[.,][0-9]{1,2})?)\s*€",
        r"€\s*([0-9]{1,4}(?:[.,][0-9]{1,2})?)",
        r"([0-9]{1,4}(?:[.,][0-9]{1,2})?)\s*€",
    ]
    lower = page_text.lower()
    for pattern in preferred_patterns:
        matches = re.findall(pattern, lower, flags=re.I)
        numbers = []
        for match in matches[:30]:
            norm = _normalize_number(match)
            if not norm:
                continue
            try:
                number = float(norm)
            except ValueError:
                continue
            if 20 <= number <= 2000:
                numbers.append(number)
        if numbers:
            value = min(numbers)
            return f"€ {value:.2f}".replace(".00", "")
    return ""


def _extract_rating(page_text: str, obj: dict) -> str:
    aggregate = obj.get("aggregateRating") if isinstance(obj, dict) else None
    if isinstance(aggregate, dict):
        value = _normalize_number(aggregate.get("ratingValue"))
        if value:
            return value.replace(".", ",")

    patterns = [
        r"bewertet mit\s*([0-9]{1,2}[,.][0-9])",
        r"(?:scored|rated)\s*([0-9]{1,2}[,.][0-9])",
        r"(?:bewertung|rating|score)\s*[:\-]?\s*([0-9]{1,2}[,.][0-9])",
        r"\b([0-9][,.][0-9])\s*(?:/\s*10|von\s*10)",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, flags=re.I)
        if match:
            return match.group(1).replace(".", ",")
    return ""


def _extract_review_count(page_text: str, obj: dict) -> str:
    aggregate = obj.get("aggregateRating") if isinstance(obj, dict) else None
    if isinstance(aggregate, dict):
        value = _normalize_number(aggregate.get("reviewCount") or aggregate.get("ratingCount"))
        if value:
            return value
    patterns = [
        r"([0-9]{1,6})\s*(?:g[aä]stebewertungen|bewertungen|reviews|ratings|rezensionen)",
        r"(?:aus|from|von)\s*([0-9]{1,6})\s*(?:bewertungen|reviews|ratings|rezensionen)",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, flags=re.I)
        if match:
            return match.group(1)
    return ""


def _extract_description(parser: _PageTextParser, obj: dict) -> str:
    if isinstance(obj, dict) and obj.get("description"):
        return _clean_text(obj.get("description"), 7000)
    if parser.meta_description:
        return _clean_text(parser.meta_description, 7000)
    visible = _clean_text(" ".join(parser.text_parts), 20000)
    lower = visible.lower()
    starts = [lower.find(marker) for marker in PROPERTY_MARKERS if lower.find(marker) >= 0]
    start = min(starts) if starts else 0
    return _clean_text(visible[start : start + 7000], 7000)


def _text_fingerprint(description: str) -> str:
    stable = description.lower()
    stable = re.sub(r"https?://\S+", " ", stable)
    stable = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", " ", stable)
    stable = re.sub(r"\b\d{1,2}:\d{2}\b", " ", stable)
    stable = re.sub(r"[€$£]\s*[0-9.,]+|[0-9.,]+\s*[€$£]", " ", stable)
    stable = re.sub(r"\b\d+(?:[.,]\d+)?\b", "#", stable)
    stable = re.sub(r"\s+", " ", stable).strip()
    return hashlib.sha256(stable.encode("utf-8")).hexdigest() if stable else ""


def _parse_page(html: str) -> dict[str, str | int]:
    parser = _PageTextParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    obj = _preferred_jsonld(html)
    page_text = _clean_text(" ".join(parser.text_parts), 30000)
    title = _clean_text(obj.get("name") if isinstance(obj, dict) else "", 500)
    if not title:
        title = _clean_text(" ".join(parser.title_parts), 500)
    description = _extract_description(parser, obj)
    raw_lower = html.lower()
    return {
        "title": title,
        "description": description,
        "description_hash": _text_fingerprint(description),
        "price": _extract_price(page_text, obj),
        "rating": _extract_rating(page_text, obj),
        "review_count": _extract_review_count(page_text, obj),
        "booking_link": 1 if "booking.com" in raw_lower else 0,
        "direct_link": 1 if "topdiveair-sketch.github.io/direcktbuchungen" in raw_lower else 0,
    }


def init_provider_monitor(app, db, require_admin):
    if app.extensions.get("zab_provider_monitor_initialized"):
        return
    app.extensions["zab_provider_monitor_initialized"] = True
    run_lock = threading.Lock()

    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS provider_monitor_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Portal',
                url TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_checked TEXT DEFAULT '',
                last_http INTEGER DEFAULT 0,
                last_status TEXT DEFAULT 'neu',
                last_error TEXT DEFAULT '',
                current_title TEXT DEFAULT '',
                current_description TEXT DEFAULT '',
                current_description_hash TEXT DEFAULT '',
                current_price TEXT DEFAULT '',
                current_rating TEXT DEFAULT '',
                current_review_count TEXT DEFAULT '',
                booking_link INTEGER NOT NULL DEFAULT 0,
                direct_link INTEGER NOT NULL DEFAULT 0,
                last_rendered_url TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS provider_monitor_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT DEFAULT '',
                new_value TEXT DEFAULT '',
                changed_at TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(listing_id) REFERENCES provider_monitor_listings(id)
            );
            CREATE TABLE IF NOT EXISTS provider_monitor_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        defaults = {
            "enabled": "1",
            "interval_minutes": "360",
            "price_horizon_days": "30",
            "alerts_enabled": "1",
            "alert_email": "",
            "last_run": "",
            "last_run_result": "noch nie",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO provider_monitor_settings(key,value) VALUES(?,?)",
                (key, value),
            )
        for name, category, url in SEED_LISTINGS:
            conn.execute(
                """INSERT OR IGNORE INTO provider_monitor_listings
                   (name,category,url,active,created_at) VALUES(?,?,?,1,?)""",
                (name, category, url, _now()),
            )

    def settings() -> dict[str, str]:
        with db() as conn:
            return {
                row["key"]: row["value"]
                for row in conn.execute("SELECT key,value FROM provider_monitor_settings")
            }

    def set_setting(key: str, value: str) -> None:
        with db() as conn:
            conn.execute(
                """INSERT INTO provider_monitor_settings(key,value) VALUES(?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (key, value),
            )

    def site_settings() -> dict[str, str]:
        with db() as conn:
            return {
                row["key"]: row["value"]
                for row in conn.execute("SELECT key,value FROM site_settings")
            }

    def _record_change(conn, listing_id: int, field: str, old, new, baseline: bool) -> dict | None:
        old_text = str(old or "")
        new_text = str(new or "")
        if baseline or old_text == new_text:
            return None
        conn.execute(
            """INSERT INTO provider_monitor_changes
               (listing_id,field,old_value,new_value,changed_at,acknowledged)
               VALUES(?,?,?,?,?,0)""",
            (listing_id, field, old_text[:12000], new_text[:12000], _now()),
        )
        return {"listing_id": listing_id, "field": field, "old": old_text, "new": new_text}

    def _check_one(row, horizon_days: int) -> list[dict]:
        changes: list[dict] = []
        checked_at = _now()
        try:
            http_status, html, rendered_url = _request_page(row["url"], horizon_days)
            if http_status >= 400:
                with db() as conn:
                    baseline = not bool(row["last_checked"])
                    change = _record_change(
                        conn,
                        row["id"],
                        "Abrufstatus",
                        row["last_status"],
                        f"HTTP {http_status}",
                        baseline,
                    )
                    if change:
                        changes.append(change)
                    conn.execute(
                        """UPDATE provider_monitor_listings
                           SET last_checked=?,last_http=?,last_status=?,last_error=?,last_rendered_url=?
                           WHERE id=?""",
                        (checked_at, http_status, "blockiert/fehler", f"HTTP {http_status}", rendered_url, row["id"]),
                    )
                return changes

            parsed = _parse_page(html)
            with db() as conn:
                previous = conn.execute(
                    "SELECT * FROM provider_monitor_listings WHERE id=?", (row["id"],)
                ).fetchone()
                baseline = not bool(previous["last_checked"])
                comparisons = [
                    ("Titel", previous["current_title"], parsed["title"]),
                    ("Beschreibung", previous["current_description_hash"], parsed["description_hash"]),
                    ("Preis", previous["current_price"], parsed["price"]),
                    ("Bewertung", previous["current_rating"], parsed["rating"]),
                    ("Anzahl Bewertungen", previous["current_review_count"], parsed["review_count"]),
                    ("Booking-Link", previous["booking_link"], parsed["booking_link"]),
                    ("Direktbuchungs-Link", previous["direct_link"], parsed["direct_link"]),
                ]
                for field, old, new in comparisons:
                    change = _record_change(conn, row["id"], field, old, new, baseline)
                    if change:
                        if field == "Beschreibung":
                            change["old"] = previous["current_description"]
                            change["new"] = parsed["description"]
                            conn.execute(
                                """UPDATE provider_monitor_changes SET old_value=?,new_value=?
                                   WHERE id=(SELECT MAX(id) FROM provider_monitor_changes WHERE listing_id=? AND field='Beschreibung')""",
                                (
                                    str(previous["current_description"] or "")[:12000],
                                    str(parsed["description"] or "")[:12000],
                                    row["id"],
                                ),
                            )
                        changes.append(change)
                status_change = _record_change(
                    conn,
                    row["id"],
                    "Abrufstatus",
                    previous["last_status"],
                    "ok",
                    baseline,
                )
                if status_change:
                    changes.append(status_change)
                conn.execute(
                    """UPDATE provider_monitor_listings SET
                       last_checked=?,last_http=?,last_status='ok',last_error='',
                       current_title=?,current_description=?,current_description_hash=?,
                       current_price=?,current_rating=?,current_review_count=?,
                       booking_link=?,direct_link=?,last_rendered_url=?
                       WHERE id=?""",
                    (
                        checked_at,
                        http_status,
                        parsed["title"],
                        parsed["description"],
                        parsed["description_hash"],
                        parsed["price"],
                        parsed["rating"],
                        parsed["review_count"],
                        int(parsed["booking_link"]),
                        int(parsed["direct_link"]),
                        rendered_url,
                        row["id"],
                    ),
                )
        except Exception as exc:
            with db() as conn:
                previous = conn.execute(
                    "SELECT * FROM provider_monitor_listings WHERE id=?", (row["id"],)
                ).fetchone()
                baseline = not bool(previous["last_checked"])
                change = _record_change(
                    conn,
                    row["id"],
                    "Abrufstatus",
                    previous["last_status"],
                    "fehler",
                    baseline,
                )
                if change:
                    changes.append(change)
                conn.execute(
                    """UPDATE provider_monitor_listings
                       SET last_checked=?,last_status='fehler',last_error=? WHERE id=?""",
                    (checked_at, f"{type(exc).__name__}: {exc}"[:1000], row["id"]),
                )
        return changes

    def _send_change_alert(changes: list[dict]) -> tuple[bool, str]:
        cfg = settings()
        if cfg.get("alerts_enabled", "1") != "1" or not changes:
            return False, "deaktiviert/keine Aenderung"
        site = site_settings()
        recipient = (
            cfg.get("alert_email", "").strip()
            or os.environ.get("PROVIDER_MONITOR_ALERT_EMAIL", "").strip()
            or site.get("email", "").strip()
        )
        host = site.get("smtp_host", "").strip()
        user = site.get("smtp_user", "").strip()
        password = site.get("smtp_password", "")
        sender = site.get("smtp_sender", "").strip() or user
        try:
            port = int(site.get("smtp_port", "587") or 587)
        except ValueError:
            port = 587
        if not recipient or not host or not sender:
            return False, "SMTP/Empfaenger nicht konfiguriert"

        with db() as conn:
            names = {
                row["id"]: row["name"]
                for row in conn.execute("SELECT id,name FROM provider_monitor_listings")
            }
        lines = ["Der Anbieter-Monitor hat Aenderungen gefunden:", ""]
        for item in changes[:50]:
            old = str(item.get("old") or "-").replace("\n", " ")[:700]
            new = str(item.get("new") or "-").replace("\n", " ")[:700]
            lines.extend(
                [
                    f"{names.get(item['listing_id'], 'Anbieter')} - {item['field']}",
                    f"Alt: {old}",
                    f"Neu: {new}",
                    "",
                ]
            )
        msg = EmailMessage()
        msg["Subject"] = f"[Zuhause am Bach] Anbieter-Monitor: {len(changes)} Aenderung(en)"
        msg["From"] = sender
        msg["To"] = recipient
        msg.set_content("\n".join(lines))
        try:
            context = ssl.create_default_context()
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as smtp:
                    if user and password:
                        smtp.login(user, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=20) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                    if user and password:
                        smtp.login(user, password)
                    smtp.send_message(msg)
            return True, "gesendet"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"[:500]

    def run_all(source: str = "scheduler") -> tuple[bool, str, int]:
        if not run_lock.acquire(blocking=False):
            return False, "Pruefung laeuft bereits", 0
        try:
            cfg = settings()
            horizon_days = max(1, min(365, int(cfg.get("price_horizon_days", "30") or 30)))
            with db() as conn:
                rows = conn.execute(
                    "SELECT * FROM provider_monitor_listings WHERE active=1 ORDER BY id"
                ).fetchall()
            all_changes: list[dict] = []
            for row in rows:
                all_changes.extend(_check_one(row, horizon_days))
                time.sleep(0.4)
            sent, mail_status = _send_change_alert(all_changes)
            result = (
                f"{len(rows)} Anbieter geprueft, {len(all_changes)} Aenderungen"
                + (f", E-Mail {mail_status}" if all_changes else "")
            )
            set_setting("last_run", _now())
            set_setting("last_run_result", result)
            return True, result, len(all_changes)
        finally:
            run_lock.release()

    app.extensions["zab_provider_monitor_run"] = run_all

    def scheduler_loop():
        time.sleep(45)
        while True:
            try:
                cfg = settings()
                if cfg.get("enabled", "1") == "1":
                    run_all("scheduler")
                minutes = max(60, min(1440, int(cfg.get("interval_minutes", "360") or 360)))
            except Exception:
                minutes = 360
            time.sleep(minutes * 60)

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        thread = threading.Thread(
            target=scheduler_loop,
            daemon=True,
            name="zab-provider-monitor",
        )
        thread.start()

    @app.get("/admin/provider-monitor")
    def provider_monitor_dashboard():
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            listings = conn.execute(
                """SELECT * FROM provider_monitor_listings
                   ORDER BY active DESC, category, name"""
            ).fetchall()
            changes = conn.execute(
                """SELECT c.*,l.name AS listing_name,l.url AS listing_url
                   FROM provider_monitor_changes c
                   JOIN provider_monitor_listings l ON l.id=c.listing_id
                   ORDER BY c.id DESC LIMIT 250"""
            ).fetchall()
            open_changes = conn.execute(
                "SELECT COUNT(*) AS n FROM provider_monitor_changes WHERE acknowledged=0"
            ).fetchone()["n"]
        return render_template(
            "provider_monitor.html",
            listings=listings,
            changes=changes,
            open_changes=open_changes,
            monitor_settings=settings(),
            direct_url=DIRECT_BOOKING_URL,
        )

    @app.post("/admin/provider-monitor/run")
    def provider_monitor_run():
        if not require_admin():
            return redirect(url_for("admin_login"))
        ok, message, _ = run_all("manual")
        flash(message, "success" if ok else "error")
        return redirect(url_for("provider_monitor_dashboard"))

    @app.post("/admin/provider-monitor/settings")
    def provider_monitor_save_settings():
        if not require_admin():
            return redirect(url_for("admin_login"))
        enabled = "1" if request.form.get("enabled") == "on" else "0"
        alerts_enabled = "1" if request.form.get("alerts_enabled") == "on" else "0"
        try:
            interval = max(60, min(1440, int(request.form.get("interval_minutes", "360") or 360)))
        except ValueError:
            interval = 360
        try:
            horizon = max(1, min(365, int(request.form.get("price_horizon_days", "30") or 30)))
        except ValueError:
            horizon = 30
        set_setting("enabled", enabled)
        set_setting("alerts_enabled", alerts_enabled)
        set_setting("interval_minutes", str(interval))
        set_setting("price_horizon_days", str(horizon))
        set_setting("alert_email", request.form.get("alert_email", "").strip()[:320])
        flash("Anbieter-Monitor Einstellungen gespeichert.", "success")
        return redirect(url_for("provider_monitor_dashboard"))

    @app.post("/admin/provider-monitor/listing")
    def provider_monitor_add_listing():
        if not require_admin():
            return redirect(url_for("admin_login"))
        name = request.form.get("name", "").strip()[:200]
        category = request.form.get("category", "Portal").strip()[:100] or "Portal"
        url = request.form.get("url", "").strip()[:3000]
        if not name or not url.startswith(("https://", "http://")):
            flash("Bitte Anbietername und gueltige URL eingeben.", "error")
            return redirect(url_for("provider_monitor_dashboard"))
        try:
            with db() as conn:
                conn.execute(
                    """INSERT INTO provider_monitor_listings
                       (name,category,url,active,created_at) VALUES(?,?,?,1,?)""",
                    (name, category, url, _now()),
                )
            flash("Anbieter hinzugefuegt.", "success")
        except Exception:
            flash("Diese URL ist bereits im Monitor vorhanden.", "error")
        return redirect(url_for("provider_monitor_dashboard"))

    @app.post("/admin/provider-monitor/listing/<int:listing_id>/toggle")
    def provider_monitor_toggle_listing(listing_id: int):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute(
                "UPDATE provider_monitor_listings SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?",
                (listing_id,),
            )
        return redirect(url_for("provider_monitor_dashboard"))

    @app.post("/admin/provider-monitor/ack")
    def provider_monitor_acknowledge():
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute("UPDATE provider_monitor_changes SET acknowledged=1 WHERE acknowledged=0")
        flash("Aenderungen als gelesen markiert.", "success")
        return redirect(url_for("provider_monitor_dashboard"))

    @app.get("/health/provider-monitor")
    def provider_monitor_health():
        cfg = settings()
        with db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM provider_monitor_listings WHERE active=1"
            ).fetchone()["n"]
            failed = conn.execute(
                """SELECT COUNT(*) AS n FROM provider_monitor_listings
                   WHERE active=1 AND last_checked<>'' AND last_status<>'ok'"""
            ).fetchone()["n"]
            changes = conn.execute(
                "SELECT COUNT(*) AS n FROM provider_monitor_changes WHERE acknowledged=0"
            ).fetchone()["n"]
        return jsonify(
            ok=True,
            enabled=cfg.get("enabled", "1") == "1",
            active_listings=int(total or 0),
            failed_listings=int(failed or 0),
            unread_changes=int(changes or 0),
            last_run=cfg.get("last_run", ""),
            last_run_result=cfg.get("last_run_result", ""),
        )
