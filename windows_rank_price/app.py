from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "Zuhause am Bach - Rang & Preis"
DEFAULT_API = "https://web-production-2b242.up.railway.app"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "ZuhauseAmBach" / "RangPreis"
CONFIG_FILE = CONFIG_DIR / "config.json"

KEYWORDS = [
    "unterkunft wachau nordufer",
    "unterkunft aggsbach markt",
    "privatzimmer wachau",
    "donauradweg unterkunft wachau",
    "welterbesteig unterkunft wachau",
]

COMPETITOR_NAMES = [
    "Goldene Wachau - Privatzimmer",
    "Haus Gerstbauer",
    "Ferienwohnung Alte Post - Wachau",
    "Gästehaus Pumi",
    "Gasthof zur Venus",
    "Haus Birgit",
    "Haus Donaublick",
    "Landhaus Wachau",
    "M-Haus",
    "Villa Venus",
    "Gasthof-Pension zum Kranz",
]


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def _local_free(pointer) -> None:
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    kernel32.LocalFree(ctypes.cast(pointer, wintypes.HLOCAL))


def protect(value: str) -> str:
    raw = value.encode("utf-8")
    in_blob, in_buf = _blob(raw)
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(data).decode("ascii")
    finally:
        _local_free(out_blob.pbData)
        del in_buf


def unprotect(value: str) -> str:
    if not value:
        return ""
    raw = base64.b64decode(value)
    in_blob, in_buf = _blob(raw)
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return data.decode("utf-8")
    finally:
        _local_free(out_blob.pbData)
        del in_buf


def load_config() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        password = unprotect(data.get("admin_password_dpapi", "")) if data.get("admin_password_dpapi") else ""
        return {"api_base": data.get("api_base") or DEFAULT_API, "password": password}
    except Exception:
        return {"api_base": DEFAULT_API, "password": ""}


def save_config(api_base: str, password: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "api_base": api_base.rstrip("/"),
        "admin_password_dpapi": protect(password) if password else "",
    }
    CONFIG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def money(value) -> str:
    try:
        return f"{float(value):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "–"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x850")
        self.minsize(980, 720)
        self.option_add("*Font", "{Segoe UI} 10")
        self.config_data = load_config()
        self.own_price: float | None = None
        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._build()
        self.after(100, self._poll_results)

    def _build(self):
        top = ttk.Frame(self, padding=16)
        top.pack(fill="x")
        ttk.Label(top, text=APP_NAME, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(top, text="Google-Rangliste aller relevanten Mitbewerber und exakter Direktpreis.").pack(anchor="w", pady=(2, 10))

        settings = ttk.LabelFrame(top, text="Verbindung", padding=10)
        settings.pack(fill="x", pady=(0, 10))
        self.api_var = tk.StringVar(value=self.config_data["api_base"])
        self.pw_var = tk.StringVar(value=self.config_data["password"])
        ttk.Label(settings, text="Railway URL").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.api_var, width=55).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(settings, text="Admin-Passwort").grid(row=0, column=1, sticky="w")
        ttk.Entry(settings, textvariable=self.pw_var, show="•", width=28).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(settings, text="Speichern", command=self.save_settings).grid(row=1, column=2)
        settings.columnconfigure(0, weight=1)

        query_box = ttk.LabelFrame(top, text="Abfrage", padding=10)
        query_box.pack(fill="x")
        self.query_var = tk.StringVar(value=KEYWORDS[0])
        self.room_var = tk.StringVar(value="Bachblick")
        today = date.today()
        self.arrival_var = tk.StringVar(value=today.isoformat())
        self.departure_var = tk.StringVar(value=(today + timedelta(days=1)).isoformat())

        ttk.Label(query_box, text="Suchbegriff").grid(row=0, column=0, sticky="w")
        ttk.Combobox(query_box, textvariable=self.query_var, width=42, values=KEYWORDS).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(query_box, text="Zimmer").grid(row=0, column=1, sticky="w")
        ttk.Combobox(query_box, textvariable=self.room_var, width=18, state="readonly", values=["Bachblick", "Marillenzimmer", "Weinbergzimmer", "Donauzimmer"]).grid(row=1, column=1, padx=(0, 8))
        ttk.Label(query_box, text="Anreise YYYY-MM-DD").grid(row=0, column=2, sticky="w")
        ttk.Entry(query_box, textvariable=self.arrival_var, width=16).grid(row=1, column=2, padx=(0, 8))
        ttk.Label(query_box, text="Abreise YYYY-MM-DD").grid(row=0, column=3, sticky="w")
        ttk.Entry(query_box, textvariable=self.departure_var, width=16).grid(row=1, column=3, padx=(0, 8))
        self.fetch_btn = ttk.Button(query_box, text="Jetzt abrufen", command=self.fetch)
        self.fetch_btn.grid(row=1, column=4)
        query_box.columnconfigure(0, weight=1)

        result = ttk.Frame(self, padding=(16, 4, 16, 16))
        result.pack(fill="both", expand=True)

        cards = ttk.Frame(result)
        cards.pack(fill="x", pady=(4, 10))
        self.rank_value = tk.StringVar(value="–")
        self.price_value = tk.StringVar(value="–")
        self.rank_note = tk.StringVar(value="Noch nicht abgefragt")
        self.price_note = tk.StringVar(value="Noch nicht abgefragt")
        for col, title, value, note in [
            (0, "Zuhause am Bach – Google-Rang", self.rank_value, self.rank_note),
            (1, "Direktpreis", self.price_value, self.price_note),
        ]:
            box = ttk.LabelFrame(cards, text=title, padding=14)
            box.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 8 if col == 0 else 0))
            ttk.Label(box, textvariable=value, font=("Segoe UI", 26, "bold")).pack(anchor="w")
            ttk.Label(box, textvariable=note, wraplength=500).pack(anchor="w", pady=(4, 0))
            cards.columnconfigure(col, weight=1)

        ranking_frame = ttk.LabelFrame(result, text="Google-Rangliste Mitbewerber", padding=10)
        ranking_frame.pack(fill="both", expand=True, pady=(0, 10))
        ttk.Label(ranking_frame, text="Organische Google.at-Position für denselben Suchbegriff. Nicht gefundene Betriebe werden nicht geschätzt.").pack(anchor="w", pady=(0, 6))
        self.rank_tree = ttk.Treeview(ranking_frame, columns=("rank", "name", "status", "title"), show="headings", height=10)
        for col, text, width in [
            ("rank", "Rang", 70),
            ("name", "Betrieb", 260),
            ("status", "Status", 180),
            ("title", "Gefundener Treffer", 560),
        ]:
            self.rank_tree.heading(col, text=text)
            self.rank_tree.column(col, width=width, anchor="w")
        self.rank_tree.pack(fill="both", expand=True)

        lower = ttk.Panedwindow(result, orient="horizontal")
        lower.pack(fill="both", expand=True)
        comp_frame = ttk.LabelFrame(lower, text="Preisrang – exakt derselbe Aufenthalt", padding=10)
        bench_frame = ttk.LabelFrame(lower, text="Öffentliche Preis-Benchmarks", padding=10)
        lower.add(comp_frame, weight=1)
        lower.add(bench_frame, weight=1)

        self.price_rank = tk.StringVar(value="–")
        ttk.Label(comp_frame, textvariable=self.price_rank, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(comp_frame, text="Rang 1 = günstigster Preis. Nur identische Aufenthalte vergleichen.").pack(anchor="w", pady=(0, 6))
        self.comp_tree = ttk.Treeview(comp_frame, columns=("name", "price"), show="headings", height=6)
        self.comp_tree.heading("name", text="Mitbewerber")
        self.comp_tree.heading("price", text="Preis €")
        self.comp_tree.column("name", width=250)
        self.comp_tree.column("price", width=100, anchor="e")
        self.comp_tree.pack(fill="both", expand=True)
        entry_row = ttk.Frame(comp_frame)
        entry_row.pack(fill="x", pady=(6, 0))
        self.comp_name = tk.StringVar(value=COMPETITOR_NAMES[0])
        self.comp_price = tk.StringVar()
        ttk.Combobox(entry_row, textvariable=self.comp_name, values=COMPETITOR_NAMES).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Entry(entry_row, textvariable=self.comp_price, width=12).pack(side="left", padx=(0, 6))
        ttk.Button(entry_row, text="Hinzufügen", command=self.add_competitor).pack(side="left")
        ttk.Button(comp_frame, text="Markierten entfernen", command=self.remove_competitor).pack(anchor="e", pady=(5, 0))

        self.bench_tree = ttk.Treeview(bench_frame, columns=("name", "price", "source", "time"), show="headings", height=8)
        for col, text, width in [("name", "Betrieb", 180), ("price", "Preis", 90), ("source", "Quelle", 110), ("time", "Stand", 150)]:
            self.bench_tree.heading(col, text=text)
            self.bench_tree.column(col, width=width, anchor="w")
        self.bench_tree.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Bereit.")
        ttk.Label(result, textvariable=self.status_var).pack(anchor="w", pady=(7, 0))

    def save_settings(self):
        try:
            save_config(self.api_var.get().strip(), self.pw_var.get())
            self.status_var.set("Verbindungseinstellungen gespeichert. Passwort ist per Windows-DPAPI geschützt.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Speichern fehlgeschlagen:\n{exc}")

    def add_competitor(self):
        name = self.comp_name.get().strip() or "Mitbewerber"
        raw = self.comp_price.get().strip().replace(",", ".")
        try:
            price = float(raw)
            if price <= 0:
                raise ValueError
        except Exception:
            messagebox.showwarning(APP_NAME, "Bitte einen gültigen Preis eingeben.")
            return
        self.comp_tree.insert("", "end", values=(name, f"{price:.2f}"))
        self.comp_price.set("")
        self._calc_rank()

    def remove_competitor(self):
        for item in self.comp_tree.selection():
            self.comp_tree.delete(item)
        self._calc_rank()

    def _calc_rank(self):
        if self.own_price is None:
            self.price_rank.set("–")
            return
        prices = [("Zuhause am Bach", self.own_price)]
        for item in self.comp_tree.get_children():
            name, raw = self.comp_tree.item(item, "values")
            try:
                prices.append((name, float(raw)))
            except Exception:
                pass
        prices.sort(key=lambda row: row[1])
        pos = next((i for i, row in enumerate(prices, start=1) if row[0] == "Zuhause am Bach"), 1)
        self.price_rank.set(f"Preisrang {pos} / {len(prices)}")

    def fetch(self):
        password = self.pw_var.get()
        if not password:
            messagebox.showwarning(APP_NAME, "Bitte zuerst das Admin-Passwort eintragen.")
            return
        api_base = self.api_var.get().strip().rstrip("/")
        query = self.query_var.get().strip()
        room = self.room_var.get().strip()
        arrival = self.arrival_var.get().strip()
        departure = self.departure_var.get().strip()
        try:
            a = date.fromisoformat(arrival)
            d = date.fromisoformat(departure)
            if d <= a:
                raise ValueError
        except Exception:
            messagebox.showwarning(APP_NAME, "Bitte gültige An- und Abreisedaten im Format YYYY-MM-DD eingeben.")
            return
        self.fetch_btn.state(["disabled"])
        self.status_var.set("Abruf läuft … Google-Rangliste kann einige Sekunden dauern.")
        threading.Thread(
            target=self._fetch_worker,
            args=(api_base, password, query, room, arrival, departure),
            daemon=True,
        ).start()

    def _fetch_worker(self, base: str, password: str, query: str, room: str, arrival: str, departure: str):
        params = urllib.parse.urlencode({"q": query, "room": room, "arrival": arrival, "departure": departure})
        req = urllib.request.Request(
            f"{base}/api/windows/rank-price-check?{params}",
            headers={
                "X-Admin-Password": password,
                "Accept": "application/json",
                "User-Agent": "ZAB-RangPreis-Windows/1.2",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=50) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            self.result_queue.put(("ok", payload))
        except urllib.error.HTTPError as exc:
            msg = "Admin-Passwort wurde vom Server abgelehnt." if exc.code == 401 else f"Serverfehler HTTP {exc.code}."
            self.result_queue.put(("error", msg))
        except Exception as exc:
            self.result_queue.put(("error", f"Abruf fehlgeschlagen: {type(exc).__name__}: {exc}"))

    def _poll_results(self):
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "ok":
                    self._show_result(payload if isinstance(payload, dict) else {})
                else:
                    self._show_error(str(payload))
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll_results)

    def _show_result(self, data: dict):
        self.fetch_btn.state(["!disabled"])
        if not data.get("ok"):
            self._show_error(data.get("message") or data.get("error") or "Unbekannter Fehler")
            return

        rank = data.get("rank") or {}
        provider_error = str(data.get("provider_error") or "").strip()
        if provider_error:
            self.rank_value.set("–")
            self.rank_note.set(provider_error)
        elif rank.get("rank") is not None:
            self.rank_value.set(f"#{rank['rank']}")
            self.rank_note.set(f"{rank.get('message','')}  Quelle: {rank.get('source','')}")
        elif rank.get("status") == "not_configured":
            self.rank_value.set("API fehlt")
            self.rank_note.set(rank.get("message") or "SERP-API ist nicht konfiguriert.")
        else:
            self.rank_value.set(">100 / n. g.")
            self.rank_note.set(f"{rank.get('message','')}  Quelle: {rank.get('source','')}")

        for item in self.rank_tree.get_children():
            self.rank_tree.delete(item)
        if provider_error:
            self.rank_tree.insert("", "end", values=("–", "Google-Rangliste", "derzeit nicht verfügbar", provider_error))
        else:
            for row in data.get("competitor_rankings") or []:
                r = row.get("rank")
                if r is not None:
                    rank_text = f"#{r}"
                    status = "gefunden"
                elif row.get("status") == "not_configured":
                    rank_text = "–"
                    status = "SERP-API fehlt"
                elif row.get("status") in {"error", "unavailable"}:
                    rank_text = "–"
                    status = "derzeit nicht verfügbar"
                else:
                    rank_text = ">100 / n. g."
                    status = "nicht gefunden"
                self.rank_tree.insert("", "end", values=(rank_text, row.get("name", ""), status, row.get("title", "")))

        own = data.get("own_price") or {}
        try:
            self.own_price = float(own.get("total_eur") or 0)
        except (TypeError, ValueError):
            self.own_price = 0.0
        self.price_value.set(money(self.own_price))
        self.price_note.set(f"{own.get('nights','–')} Nacht/Nächte · Ø {money(own.get('average_nightly_eur'))} pro Nacht")
        self._calc_rank()

        for item in self.bench_tree.get_children():
            self.bench_tree.delete(item)
        for row in data.get("public_benchmarks") or []:
            self.bench_tree.insert("", "end", values=(row.get("name", ""), money(row.get("price_eur")), row.get("source", ""), row.get("checked_at", "")))
        if provider_error:
            self.status_var.set("Direktpreis geladen. Google-Rangliste derzeit nicht verfügbar.")
        else:
            self.status_var.set(f"Abruf abgeschlossen: {len(data.get('competitor_rankings') or [])} Mitbewerber geprüft.")

    def _show_error(self, message: str):
        self.fetch_btn.state(["!disabled"])
        self.status_var.set(message)
        messagebox.showerror(APP_NAME, message)


if __name__ == "__main__":
    App().mainloop()
