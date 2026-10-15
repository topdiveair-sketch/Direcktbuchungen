#!/usr/bin/env python3
"""Submit owned public sitemap URLs to IndexNow (Bing and participating engines).

Usage:
    python scripts/indexnow_submit.py              # dry run (no submission)
    python scripts/indexnow_submit.py --submit     # submit once

Does not submit to Google: use the free Google Search Console for Google.
No dependencies beyond Python 3. Never submit third-party URLs.
"""
import argparse
import json
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

BASE = "https://www.zuhauseambach-wachau.at"
KEY = "zab-indexnow-20261012-jauerling"
KEY_LOCATION = BASE + "/" + KEY + ".txt"
SITEMAP = BASE + "/sitemap.xml"
ENDPOINT = "https://api.indexnow.org/indexnow"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ZAB-IndexNow/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true", help="Send a single batch to IndexNow")
    args = parser.parse_args()
    key_text = fetch(KEY_LOCATION).strip()
    if key_text != KEY:
        raise SystemExit("IndexNow ownership key verification failed")
    xml = ET.fromstring(fetch(SITEMAP))
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = list(dict.fromkeys(e.text.strip() for e in xml.findall(".//s:loc", ns) if e.text))
    if not urls or any(urlparse(u).scheme != "https" or urlparse(u).netloc != "www.zuhauseambach-wachau.at" for u in urls):
        raise SystemExit("Sitemap empty or contains external URLs")
    print("Validated owned URLs:", len(urls))
    if not args.submit:
        print("DRY RUN: No URLs submitted. Use --submit after confirming actual content changes.")
        return
    payload = json.dumps({"host": "www.zuhauseambach-wachau.at", "key": KEY, "keyLocation": KEY_LOCATION, "urlList": urls}).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=payload, headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "ZAB-IndexNow/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            print("IndexNow HTTP status:", response.status)
            print("Accepted by endpoint; indexing and rankings are not guaranteed.")
    except urllib.error.HTTPError as exc:
        raise SystemExit("IndexNow rejected request: HTTP " + str(exc.code))


if __name__ == "__main__":
    main()
