import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="zab-regression-")
os.environ["ADMIN_PASSWORD"] = "test-password-123"
os.environ["SECRET_KEY"] = "x" * 40
os.environ.pop("SESSION_COOKIE_SECURE", None)
os.environ["SITE_PHONE"] = "+43111222333"
os.environ["PUBLIC_BASE_URL"] = "https://example.test"
os.environ["SMTP_HOST"] = "smtp.example.test"
os.environ["SMTP_USER"] = "mailer@example.test"
os.environ["SMTP_PASSWORD"] = "app-password"
os.environ["PAYPAL_ME_URL"] = "https://paypal.me/example"
os.environ["GOOGLE_REVIEW_URL"] = "https://g.page/r/example"
os.environ["ICAL_BACHBLICK_URL"] = "https://ical.example.test/bachblick.ics"
os.environ["LEGAL_IMPRESSUM_TEXT"] = "Geprueftes Impressum fuer Test."

import app  # noqa: E402


client = app.app.test_client()
results = []


def check(name, ok, details=""):
    results.append((name, bool(ok), details))


check("Local HTTP cookie default", app.app.config["SESSION_COOKIE_SECURE"] is False)

with app.db() as conn:
    settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM site_settings")}
    bachblick_ical = conn.execute("SELECT import_url FROM ical_settings WHERE room='Bachblick'").fetchone()["import_url"]
    impressum = conn.execute("SELECT content FROM legal_pages WHERE key='impressum'").fetchone()["content"]

check("Env site settings import", settings.get("smtp_host") == "smtp.example.test" and settings.get("public_base_url") == "https://example.test")
check("Env iCal import", bachblick_ical == "https://ical.example.test/bachblick.ics")
check("Env legal text import", impressum == "Geprueftes Impressum fuer Test.")

with app.db() as conn:
    luggage = conn.execute("SELECT price FROM extras WHERE key='luggage'").fetchone()["price"]
index_html = client.get("/").data.decode("utf-8", errors="replace")
check("Luggage default price is 15", float(luggage) == 15.0, str(luggage))
check(
    "Booking extras shown before rooms",
    index_html.find("booking-services") != -1 and index_html.find("booking-services") < index_html.find('id="zimmer"'),
)
check(
    "Homepage UTF-8 umlauts",
    "Frühstück" in index_html and "Gepäcktransport" in index_html and "Gemütlich" in index_html,
)

bad_encoding_files = []
for source_path in BASE.rglob("*"):
    if not source_path.is_file() or source_path.suffix.lower() not in {".py", ".html", ".css", ".js", ".md", ".txt", ".json"}:
        continue
    if any(part in {"__pycache__", ".pytest_cache", ".venv", "venv", "work", "data"} for part in source_path.relative_to(BASE).parts):
        continue
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        bad_encoding_files.append(str(source_path.relative_to(BASE)))
        continue
    if any(marker in source_text for marker in ("\ufffd", "\u00c3", "\u00c2", "\u00e2")):
        bad_encoding_files.append(str(source_path.relative_to(BASE)))
check("Source has no mojibake umlauts", not bad_encoding_files, ", ".join(bad_encoding_files[:8]))

availability_with_luggage = client.post(
    "/api/availability",
    data={
        "room": "Bachblick",
        "arrival": "2026-09-01",
        "departure": "2026-09-03",
        "adults": "2",
        "luggage": "true",
    },
)
availability_payload = availability_with_luggage.get_json()
check(
    "Availability message UTF-8",
    availability_payload.get("message") == "Das Zimmer ist verfügbar."
    and b"verf\xc3\xbcgbar" in availability_with_luggage.data,
    availability_payload.get("message", ""),
)
luggage_lines = [
    item for item in availability_payload.get("breakdown", {}).get("extras", [])
    if item.get("label") == "Gepäcktransport"
]
check(
    "Luggage availability price is 15",
    availability_with_luggage.status_code == 200 and luggage_lines and luggage_lines[0].get("amount") == 15.0,
    str(luggage_lines),
)

with client:
    login = client.post("/admin/login", data={"password": "test-password-123"}, follow_redirects=False)
    check("Admin login", login.status_code == 302, str(login.status_code))

    created = client.post(
        "/quality/user",
        data={
            "username": "maid",
            "display_name": "Housekeeping",
            "password": "abcdefgh",
            "role": "housekeeping",
        },
        follow_redirects=False,
    )
    check("Create housekeeping user", created.status_code == 302, str(created.status_code))

    client.get("/admin/logout")
    staff_login = client.post(
        "/staff/login",
        data={"username": "maid", "password": "abcdefgh"},
        follow_redirects=False,
    )
    check("Staff login redirects to host", staff_login.status_code == 302 and staff_login.headers.get("Location") == "/host")
    check("Housekeeping can open host", client.get("/host", follow_redirects=False).status_code == 200)
    check("Housekeeping cannot open admin", client.get("/admin", follow_redirects=False).status_code == 302)


booking_data = {
    "room": "Bachblick",
    "arrival": "2026-09-01",
    "departure": "2026-09-03",
    "adults": "2",
    "breakfast": "on",
    "first_name": "Test",
    "last_name": "Gast",
    "email": "testgast@example.com",
    "phone": "+431234567",
    "payment_method": "vor_ort",
}

first_booking = client.post("/book", data=booking_data, follow_redirects=False)
second_booking = client.post("/book", data=booking_data, follow_redirects=False)
with app.db() as conn:
    count = conn.execute("SELECT COUNT(*) c FROM bookings").fetchone()["c"]

check("First booking succeeds", first_booking.status_code == 200, str(first_booking.status_code))
check("Duplicate booking is rejected", second_booking.status_code == 302 and count == 1, f"status={second_booking.status_code}, count={count}")


passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{len(results)} erfolgreich")
for name, ok, details in results:
    suffix = f" ({details})" if details else ""
    print(("OK" if ok else "FEHLER"), name + suffix)

if passed != len(results):
    raise SystemExit(1)
