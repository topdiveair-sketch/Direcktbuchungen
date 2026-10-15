#!/usr/bin/env python3
"""Kostenloser Direktbuchungs-Wirtschaftsbericht (nur lokale SQLite-Leserechte).

Aufruf: python scripts/direktbuchung_roi.py /pfad/zur/buchungen.sqlite --provision 15
Keine personenbezogenen Daten in der Ausgabe. Keine Netzwerkzugriffe.
Hinweis: Provision ist eine Annahme, keine aus Booking.com gelesene Vertragsrate.
"""
import argparse
import sqlite3
from collections import Counter

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="Pfad zur vorhandenen SQLite-Datenbank")
    parser.add_argument("--provision", type=float, default=15, help="angenommene OTA-Provision in Prozent (Standard: 15)")
    args = parser.parse_args()
    if not 0 <= args.provision <= 100:
        parser.error("Provision muss zwischen 0 und 100 liegen")
    connection = sqlite3.connect("file:" + __import__("pathlib").Path(args.database).resolve().as_posix() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(bookings)")}
    required = {"total", "status"}
    if not required <= columns:
        parser.error("Die Tabelle bookings braucht Spalten: total, status")
    source = "source" if "source" in columns else "'' AS source"
    rows = connection.execute(f"SELECT total, status, {source} FROM bookings").fetchall()
    counts = Counter()
    revenue = Counter()
    for row in rows:
        status = str(row["status"] or "").lower()
        if status in {"cancelled", "canceled", "storniert", "deleted", "expired", "rejected", "pending"}:
            continue
        src = str(row["source"] or "").strip().lower()
        channel = "OTA" if any(word in src for word in ("booking.com", "airbnb", "expedia", "ota")) else ("Direkt/ungeklaert" if not src or "direct" in src or "direkt" in src else "Sonstige/ungeklaert")
        try:
            amount = float(row["total"] or 0)
        except (TypeError, ValueError):
            continue
        if amount < 0:
            continue
        counts[channel] += 1
        revenue[channel] += amount
    print("Buchungen (ohne klar stornierte/offene Statuswerte):")
    for channel in ("OTA", "Direkt/ungeklaert", "Sonstige/ungeklaert"):
        print(f"{channel}: {counts[channel]} Buchungen, {revenue[channel]:.2f} EUR")
    ota = revenue["OTA"]
    print(f"Rechnerische Provision auf erkannte OTA-Buchungen bei {args.provision:g}%: {ota * args.provision / 100:.2f} EUR")
    print("Achtung: Unklare Quellen nicht als sichere Direktbuchungen interpretieren.")
    print("Nicht enthalten: Zahlungsgebuehren, OTA-Rabatte, Steuern, Stornos nach Statusvarianten oder Zusatzleistungen.")

if __name__ == "__main__":
    main()
