from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse


PLACEHOLDERS = {
    "",
    "HIER_STARKES_ADMIN_PASSWORT_MINDESTENS_12_ZEICHEN_NICHT_WIEDERVERWENDEN",
    "HIER_MINDESTENS_32_ZUFAELLIGE_ZEICHEN",
    "HIER_ECHTES_GMAIL_APP_PASSWORT_EINTRAGEN",
    "HIER_BACHBLICK_BOOKING_ICAL_LINK_EINTRAGEN",
    "HIER_GOOGLE_API_KEY_WENN_GENUTZT",
}


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def merged_values(env_file: Path | None) -> dict[str, str]:
    values = dict(os.environ)
    if env_file:
        values.update(load_env_file(env_file))
    return values


def is_url(value: str, https_required: bool = True) -> bool:
    parsed = urlparse(value)
    if https_required and parsed.scheme != "https":
        return False
    return bool(parsed.scheme and parsed.netloc)


def present(value: str) -> bool:
    return value.strip() not in PLACEHOLDERS and not value.strip().startswith("HIER_")


def mask(value: str) -> str:
    if not value:
        return "<leer>"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 6) + value[-3:]


def main() -> int:
    env_file = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if env_file and not env_file.exists():
        print(f"FEHLER Env-Datei nicht gefunden: {env_file}")
        return 1

    values = merged_values(env_file)
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, details: str = "") -> None:
        checks.append((name, ok, details))

    check("APP_ENV production", values.get("APP_ENV") == "production", values.get("APP_ENV", "<leer>"))
    check("REQUIRE_PRODUCTION_SECRETS", values.get("REQUIRE_PRODUCTION_SECRETS") == "1", values.get("REQUIRE_PRODUCTION_SECRETS", "<leer>"))
    check("DATA_DIR /data", values.get("DATA_DIR") == "/data", values.get("DATA_DIR", "<leer>"))
    check("SESSION_COOKIE_SECURE", values.get("SESSION_COOKIE_SECURE") == "1", values.get("SESSION_COOKIE_SECURE", "<leer>"))

    secret_key = values.get("SECRET_KEY", "")
    check("SECRET_KEY stark", present(secret_key) and len(secret_key) >= 32, f"Laenge {len(secret_key)}")

    admin_password = values.get("ADMIN_PASSWORD", "")
    check(
        "ADMIN_PASSWORD stark",
        present(admin_password) and len(admin_password) >= 12 and admin_password != "Padi971552",
        f"Laenge {len(admin_password)}, Wert {mask(admin_password)}",
    )

    public_base_url = values.get("PUBLIC_BASE_URL", "")
    check("PUBLIC_BASE_URL https", is_url(public_base_url), public_base_url or "<leer>")

    check("SITE_EMAIL", present(values.get("SITE_EMAIL", "")), values.get("SITE_EMAIL", "<leer>"))
    check("SITE_PHONE", present(values.get("SITE_PHONE", "")), values.get("SITE_PHONE", "<leer>"))
    check("PAYPAL_EMAIL", present(values.get("PAYPAL_EMAIL", "")), values.get("PAYPAL_EMAIL", "<leer>"))

    check("SMTP_HOST", values.get("SMTP_HOST") == "smtp.gmail.com", values.get("SMTP_HOST", "<leer>"))
    check("SMTP_PORT", values.get("SMTP_PORT") == "587", values.get("SMTP_PORT", "<leer>"))
    check("SMTP_USER", present(values.get("SMTP_USER", "")), values.get("SMTP_USER", "<leer>"))
    smtp_password = values.get("SMTP_PASSWORD", "")
    check("SMTP_PASSWORD App-Passwort gesetzt", present(smtp_password) and smtp_password != admin_password, mask(smtp_password))

    bachblick_ical = values.get("ICAL_BACHBLICK_URL", "")
    check("ICAL_BACHBLICK_URL gesetzt", present(bachblick_ical) and is_url(bachblick_ical), bachblick_ical or "<leer>")

    channel_ical = values.get("CHANNEL_BOOKING_COM_IMPORT_URL", "")
    check("CHANNEL_BOOKING_COM_IMPORT_URL gesetzt", present(channel_ical) and is_url(channel_ical), channel_ical or "<leer>")

    google_rating = values.get("GOOGLE_RATING", "")
    google_count = values.get("GOOGLE_REVIEW_COUNT", "")
    check("GOOGLE_RATING", present(google_rating), google_rating or "<leer>")
    check("GOOGLE_REVIEW_COUNT", present(google_count), google_count or "<leer>")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"{passed}/{total} Live-Checks OK")
    for name, ok, details in checks:
        print(("OK" if ok else "FEHLT"), name, details)

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
