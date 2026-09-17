from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
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


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


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
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
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
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
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
        self.geometry("980x720")
        self.minsize(860, 640)
        self.option_add("*Font", "Segoe UI 10")
        self.config_data = load_config()
        self.own_price: float | None = None
        self._build()

    def _build(self):
        top = ttk.Frame(self, padding=16)
        top.pack(fill="x")
        ttk.Label(top, text=APP_NAME, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(top, text="Google-Rang und Preisposition mit einem Klick abrufen.").pack(anchor="w", pady=(2, 10))

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
        self.query_var = tk.StringVar(value="unterkunft wachau nordufer")
        self.room_var = tk.StringVar(value="Bachblick")
        today = date.today()
        self.arrival_var = tk.StringVar(value=today.isoformat())
        self.departure_var = tk.StringVar(value=(today + timedelta(days=1)).isoformat())
        fields = [
            ("Suchbegriff", self.query_var, 42),
            ("Zimmer", self.room_var, 18),
            ("Anreise YYYY-MM-DD", self.arrival_var, 16),
            ("Abreise YYYY-MM-DD", self.departure_var, 16),
        ]
        for i, (label, var, width) in enumerate(fields):
            ttk.Label(query_box, text=label).grid(row=0, column=i, sticky="w")
            if label == "Zimmer":
                w = ttk.Combobox(query_box, textvariable=var, width=width, state="readonly", values=["Bachblick", "Marillenzimmer", "Weinbergzimmer", "Donauzimmer"])
            else:
                w = ttk.Entry(query_box, textvariable=var, width=width)
            w.grid(row=1, column=i, sticky="ew", padx=(0, 8))
        self.fetch_btn = ttk.Button(query_box, text="Jetzt abrufen", command=self.fetch)
        self.fetch_btn.grid(row=1, column=4)
        query_box.columnconfigure(0, weight=1)

        result = ttk.Frame(self, padding=(16, 4, 16, 16))
        result.pack(fill="both", expand=True)
        cards = ttk.Frame(result)
        cards.pack(fill="x", pady=(4, 12))
        self.rank_value = tk.StringVar(value="–")
        self.price_value = tk.StringVar(value="–")
        self.rank_note = tk.StringVar(value="Noch nicht abgefragt")
        self.price_note = tk.StringVar(value="Noch nicht abgefragt")
        for col, title, value, note in [
            (0, "Google-Rang", self.rank_value, self.rank_note),
            (1, "Direktpreis", self.price_value, self.price_note),
        ]:
            box = ttk.LabelFrame(cards, text=title, padding=16)
            box.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 8 if col == 0 else 0))
            ttk.Label(box, textvariable=value, font=("Segoe UI", 28, "bold")).pack(anchor="w")
            ttk.Label(box, textvariable=note, wraplength=420).pack(anchor="w", pady=(5, 0))
            cards.columnconfigure(col, weight=1)

        lower = ttk.Panedwindow(result, orient="horizontal")
        lower.pack(fill="both", expand=True)
        comp_frame = ttk.LabelFrame(lower, text="Preisvergleich für exakt denselben Aufenthalt", padding=10)
        bench_frame = ttk.LabelFrame(lower, text="Öffentliche Benchmarks", padding=10)
        lower.add(comp_frame, weight=1)
        lower.add(bench_frame, weight=1)

        self.price_rank = tk.StringVar(value="–")
        ttk.Label(comp_frame, textvariable=self.price_rank, font=("Segoe UI", 24, "bold")).pack(anchor="w")
        ttk.Label(comp_frame, text="Rang 1 = günstigster Preis. Nur identische Aufenthalte vergleichen.").pack(anchor="w", pady=(0, 8))
        self.comp_tree = ttk.Treeview(comp_frame, columns=("name", "price"), show="headings", height=8)
        self.comp_tree.heading("name", text="Mitbewerber")
        self.comp_tree.heading("price", text="Preis €")
        self.comp_tree.column("name", width=220)
        self.comp_tree.column("price", width=100, anchor="e")
        self.comp_tree.pack(fill="both", expand=True)
        entry_row = ttk.Frame(comp_frame)
        entry_row.pack(fill="x", pady=(8, 0))
        self.comp_name = tk.StringVar(value="Goldene Wachau")
        self.comp_price = tk.StringVar()
        ttk.Entry(entry_row, textvariable=self.comp_name).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Entry(entry_row, textvariable=self.comp_price, width=12).pack(side="left", padx=(0, 6))
        ttk.Button(entry_row, text="Hinzufügen", command=self.add_competitor).pack(side="left")
        ttk.Button(comp_frame, text="Markierten entfernen", command=self.remove_competitor).pack(anchor="e", pady=(6, 0))

        self.bench_tree = ttk.Treeview(bench_frame, columns=("name", "price", "source", "time"), show="headings", height=10)
        for col, text, width in [("name", "Betrieb", 160), ("price", "Preis", 80), ("source", "Quelle", 100), ("time", "Stand", 150)]:
            self.bench_tree.heading(col, text=text)
            self.bench_tree.column(col, width=width, anchor="w")
        self.bench_tree.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Bereit.")
        ttk.Label(result, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

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
        if not self.pw_var.get():
            messagebox.showwarning(APP_NAME, "Bitte zuerst das Admin-Passwort eintragen.")
            return
        try:
            a = date.fromisoformat(self.arrival_var.get().strip())
            d = date.fromisoformat(self.departure_var.get().strip())
            if d <= a:
                raise ValueError
        except Exception:
            messagebox.showwarning(APP_NAME, "Bitte gültige An- und Abreisedaten im Format YYYY-MM-DD eingeben.")
            return
        self.fetch_btn.state(["disabled"])
        self.status_var.set("Abruf läuft …")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        base = self.api_var.get().strip().rstrip("/")
        params = urllib.parse.urlencode({
            "q": self.query_var.get().strip(),
            "room": self.room_var.get().strip(),
            "arrival": self.arrival_var.get().strip(),
            "departure": self.departure_var.get().strip(),
        })
        req = urllib.request.Request(
            f"{base}/api/windows/rank-price-check?{params}",
            headers={"X-Admin-Password": self.pw_var.get(), "Accept": "application/json", "User-Agent": "ZAB-RangPreis-Windows/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            self.after(0, lambda: self._show_result(payload))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                msg = "Admin-Passwort wurde vom Server abgelehnt."
            else:
                msg = f"Serverfehler HTTP {exc.code}."
            self.after(0, lambda: self._show_error(msg))
        except Exception as exc:
            self.after(0, lambda: self._show_error(f"Abruf fehlgeschlagen: {type(exc).__name__}: {exc}"))

    def _show_result(self, data: dict):
        self.fetch_btn.state(["!disabled"])
        if not data.get("ok"):
            self._show_error(data.get("message") or data.get("error") or "Unbekannter Fehler")
            return
        rank = data.get("rank") or {}
        if rank.get("rank") is not None:
            self.rank_value.set(f"#{rank['rank']}")
        elif rank.get("status") == "not_configured":
            self.rank_value.set("API fehlt")
        else:
            self.rank_value.set(">100 / n. g.")
        self.rank_note.set(f"{rank.get('message','')}  Quelle: {rank.get('source','')}")

        own = data.get("own_price") or {}
        self.own_price = float(own.get("total_eur") or 0)
        self.price_value.set(money(self.own_price))
        self.price_note.set(f"{own.get('nights','–')} Nacht/Nächte · Ø {money(own.get('average_nightly_eur'))} pro Nacht")
        self._calc_rank()

        for item in self.bench_tree.get_children():
            self.bench_tree.delete(item)
        for row in data.get("public_benchmarks") or []:
            self.bench_tree.insert("", "end", values=(row.get("name", ""), money(row.get("price_eur")), row.get("source", ""), row.get("checked_at", "")))
        self.status_var.set("Abruf abgeschlossen.")

    def _show_error(self, message: str):
        self.fetch_btn.state(["!disabled"])
        self.status_var.set(message)
        messagebox.showerror(APP_NAME, message)


if __name__ == "__main__":
    App().mainloop()
