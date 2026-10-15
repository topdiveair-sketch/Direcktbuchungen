#!/usr/bin/env python3
"""Kostenloser SEO-Schnelltest fuer Zuhause am Bach. Python 3, keine Zusatzpakete.
Ausfuehren: python scripts/seo_check.py
Nur lesende HTTP-Abfragen; keine Buchungs- oder Zahlungsdaten.
"""
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

BASE = "https://www.zuhauseambach-wachau.at"
PAGES = [
    "/", "/en/", "/nl/", "/cs/", "/sk/", "/hu/", "/pl/",
    "/it/", "/fr/", "/es/", "/ch/",
    "/unterkunft-donauradweg-wachau",
    "/unterkunft-welterbesteig-wachau", "/robots.txt",
    "/sitemap.xml", "/llms.txt",
]

def get(path):
    req = urllib.request.Request(BASE + path, headers={
        "User-Agent": "ZAB-SEO-Check/1.0 (read-only; site owner)",
        "Accept": "text/html,application/xml,text/plain,*/*",
    })
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.status, response.geturl(), response.read(2_000_000).decode("utf-8", "replace")

def main():
    errors = []
    for path in PAGES:
        try:
            status, final_url, body = get(path)
            problems = []
            if status != 200:
                problems.append("HTTP " + str(status))
            if path == "/robots.txt" and "Sitemap:" not in body:
                problems.append("Sitemap-Angabe fehlt")
            if path == "/sitemap.xml":
                root = ET.fromstring(body)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                urls = [e.text for e in root.findall(".//sm:loc", ns)]
                print("  Sitemap-URLs:", len(urls))
                if not urls or BASE + "/" not in urls:
                    problems.append("Startseite fehlt in Sitemap")
            if path in ("/", "/en/", "/nl/", "/cs/", "/sk/", "/hu/", "/pl/", "/it/", "/fr/", "/es/", "/ch/") and "<title>" not in body.lower():
                problems.append("HTML-Titel fehlt")
            if path in ("/", "/en/", "/nl/", "/cs/", "/sk/", "/hu/", "/pl/", "/it/", "/fr/", "/es/", "/ch/") and "canonical" not in body.lower():
                problems.append("Canonical-Hinweis fehlt")
            print(("FEHLER" if problems else "OK"), status, path, " | ".join(problems))
            errors.extend(path + ": " + p for p in problems)
        except (urllib.error.URLError, TimeoutError, ET.ParseError, ValueError) as exc:
            print("FEHLER", path, str(exc))
            errors.append(path + ": " + str(exc))
    if errors:
        print("\nProbleme:", len(errors))
        return 1
    print("\nTechnischer Schnelltest bestanden. Dies beweist keine Google-Indexierung.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
