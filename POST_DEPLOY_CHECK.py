from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from urllib.parse import urljoin


def open_url(opener, url: str, data: dict[str, str] | None = None, timeout: int = 15):
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=encoded, method="POST" if data else "GET")
    return opener.open(req, timeout=timeout)


def body_text(response) -> str:
    charset = response.headers.get_content_charset() or "utf-8"
    return response.read().decode(charset, errors="replace")


def main() -> int:
    if len(sys.argv) < 2:
        print("Nutzung: python POST_DEPLOY_CHECK.py https://deine-domain.example")
        return 1

    base_url = sys.argv[1].rstrip("/") + "/"
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, details: str = "") -> None:
        checks.append((name, ok, details))

    try:
        health_response = open_url(opener, urljoin(base_url, "health"))
        payload = json.loads(body_text(health_response))
        check("/health", health_response.status == 200 and payload.get("status") == "ok", str(payload))
    except Exception as exc:
        check("/health", False, str(exc))

    for path, needle in [
        ("", "Zuhause am Bach"),
        ("admin/login", "password"),
        ("legal/impressum", "Laura Prem"),
        ("legal/datenschutz", "Datenschutz"),
        ("api/calendar?room=Bachblick", "Bachblick"),
    ]:
        try:
            response = open_url(opener, urljoin(base_url, path))
            text = body_text(response)
            check(f"/{path or ''}", response.status == 200 and needle in text, f"Status {response.status}")
        except urllib.error.HTTPError as exc:
            check(f"/{path or ''}", False, f"HTTP {exc.code}")
        except Exception as exc:
            check(f"/{path or ''}", False, str(exc))

    if admin_password:
        try:
            response = open_url(opener, urljoin(base_url, "admin/login"), {"password": admin_password})
            final_url = response.geturl()
            text = body_text(response)
            check("Admin-Login live", "admin/login" not in final_url and "Smart Host" in text, final_url)
        except Exception as exc:
            check("Admin-Login live", False, str(exc))
    else:
        check("Admin-Login live", True, "uebersprungen: ADMIN_PASSWORD nicht gesetzt")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"{passed}/{total} Post-Deploy-Checks OK")
    for name, ok, details in checks:
        suffix = f" - {details}" if details else ""
        print(("OK" if ok else "FEHLER"), name + suffix)

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
