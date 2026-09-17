from __future__ import annotations

"""Stable Windows launcher for Zuhause am Bach - Rang & Preis.

Extends the base client with a separate day-by-day monthly price overview while
keeping the base app's single rank/price result consumer untouched.
"""

import json
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
import tkinter as tk
from tkinter import ttk

from app import App as BaseApp, APP_NAME, money


class App(BaseApp):
    def __init__(self):
        self.month_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.month_window = None
        self.month_tree = None
        self.month_status = None
        self.month_summary = None
        self.month_var = None
        self.month_room_var = None
        self.month_button = None
        super().__init__()
        self._install_month_button()
        self.after(120, self._poll_month_results)

    def _install_month_button(self):
        children = self.winfo_children()
        if not children:
            return
        top = children[0]
        bar = ttk.Frame(top)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="Monatsübersicht Tag für Tag", command=self.open_month_overview).pack(side="right")

    def open_month_overview(self):
        if self.month_window is not None and self.month_window.winfo_exists():
            self.month_window.lift()
            self.month_window.focus_force()
            return

        win = tk.Toplevel(self)
        self.month_window = win
        win.title(f"{APP_NAME} - Monatsübersicht")
        win.geometry("820x760")
        win.minsize(720, 580)

        outer = ttk.Frame(win, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Monatsübersicht - Tag für Tag", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Direktpreis je Kalendertag für genau 1 Nacht. Keine geschätzten Mitbewerberpreise.",
        ).pack(anchor="w", pady=(2, 12))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 10))
        try:
            default_month = date.fromisoformat(self.arrival_var.get().strip()).strftime("%Y-%m")
        except Exception:
            default_month = date.today().strftime("%Y-%m")
        self.month_var = tk.StringVar(value=default_month)
        self.month_room_var = tk.StringVar(value=self.room_var.get().strip() or "Bachblick")

        ttk.Label(controls, text="Monat YYYY-MM").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.month_var, width=14).grid(row=1, column=0, sticky="w", padx=(0, 10))
        ttk.Label(controls, text="Zimmer").grid(row=0, column=1, sticky="w")
        ttk.Combobox(
            controls,
            textvariable=self.month_room_var,
            state="readonly",
            values=["Bachblick", "Marillenzimmer", "Weinbergzimmer", "Donauzimmer"],
            width=20,
        ).grid(row=1, column=1, sticky="w", padx=(0, 10))
        self.month_button = ttk.Button(controls, text="Monat laden", command=self.fetch_month_overview)
        self.month_button.grid(row=1, column=2, sticky="w")

        self.month_summary = tk.StringVar(value="Noch nicht geladen.")
        ttk.Label(outer, textvariable=self.month_summary, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        table_frame = ttk.Frame(outer)
        table_frame.pack(fill="both", expand=True)
        self.month_tree = ttk.Treeview(
            table_frame,
            columns=("date", "weekday", "price", "status"),
            show="headings",
            height=24,
        )
        for col, label, width, anchor in [
            ("date", "Datum", 130, "w"),
            ("weekday", "Wochentag", 140, "w"),
            ("price", "Direktpreis 1 Nacht", 170, "e"),
            ("status", "Hinweis", 300, "w"),
        ]:
            self.month_tree.heading(col, text=label)
            self.month_tree.column(col, width=width, anchor=anchor)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.month_tree.yview)
        self.month_tree.configure(yscrollcommand=scroll.set)
        self.month_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.month_status = tk.StringVar(value="Bereit.")
        ttk.Label(outer, textvariable=self.month_status).pack(anchor="w", pady=(8, 0))
        win.protocol("WM_DELETE_WINDOW", self._close_month_window)

    def _close_month_window(self):
        if self.month_window is not None:
            try:
                self.month_window.destroy()
            except Exception:
                pass
        self.month_window = None
        self.month_tree = None
        self.month_status = None
        self.month_summary = None
        self.month_var = None
        self.month_room_var = None
        self.month_button = None

    def fetch_month_overview(self):
        if not self.month_window or not self.month_window.winfo_exists():
            return
        password = self.pw_var.get()
        if not password:
            self.month_status.set("Fehler: Bitte zuerst im Hauptfenster das Admin-Passwort eintragen.")
            return
        month = (self.month_var.get() or "").strip()
        try:
            year_text, month_text = month.split("-", 1)
            year = int(year_text)
            month_num = int(month_text)
            if year < 2020 or year > 2100 or month_num < 1 or month_num > 12:
                raise ValueError
        except Exception:
            self.month_status.set("Fehler: Monat bitte als YYYY-MM eingeben, z. B. 2026-09.")
            return

        request_data = {
            "base": self.api_var.get().strip().rstrip("/"),
            "password": password,
            "month": f"{year:04d}-{month_num:02d}",
            "room": self.month_room_var.get().strip(),
        }
        self.month_button.state(["disabled"])
        self.month_status.set("Monat wird geladen …")
        threading.Thread(target=self._month_worker, args=(request_data,), daemon=True).start()

    def _month_worker(self, request_data: dict):
        params = urllib.parse.urlencode({"month": request_data["month"], "room": request_data["room"]})
        req = urllib.request.Request(
            f"{request_data['base']}/api/windows/month-overview?{params}",
            headers={
                "X-Admin-Password": request_data["password"],
                "Accept": "application/json",
                "User-Agent": "ZAB-RangPreis-Windows/1.3",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            self.month_queue.put(("ok", payload))
        except urllib.error.HTTPError as exc:
            msg = "Admin-Passwort wurde vom Server abgelehnt." if exc.code == 401 else f"Serverfehler HTTP {exc.code}."
            self.month_queue.put(("error", msg))
        except Exception as exc:
            self.month_queue.put(("error", f"Monatsabruf fehlgeschlagen: {type(exc).__name__}: {exc}"))

    def _poll_month_results(self):
        try:
            while True:
                kind, payload = self.month_queue.get_nowait()
                if kind == "ok":
                    self._show_month_result(payload if isinstance(payload, dict) else {})
                else:
                    self._show_month_error(str(payload))
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(120, self._poll_month_results)

    def _show_month_error(self, message: str):
        if self.month_button is not None:
            self.month_button.state(["!disabled"])
        if self.month_status is not None:
            clean = " ".join(str(message or "Unbekannter Fehler").split())
            self.month_status.set(f"Fehler: {clean}")

    def _show_month_result(self, data: dict):
        if self.month_button is not None:
            self.month_button.state(["!disabled"])
        if not data.get("ok"):
            self._show_month_error(data.get("message") or data.get("error") or "Unbekannter Fehler")
            return
        if self.month_tree is None or not self.month_tree.winfo_exists():
            return
        for item in self.month_tree.get_children():
            self.month_tree.delete(item)
        for row in data.get("rows") or []:
            status = "" if row.get("status") == "ok" else (row.get("message") or "nicht verfügbar")
            self.month_tree.insert(
                "",
                "end",
                values=(row.get("date", ""), row.get("weekday", ""), money(row.get("total_eur")), status),
            )
        summary = data.get("summary") or {}
        if self.month_summary is not None:
            self.month_summary.set(
                f"{data.get('room','')} · {data.get('month','')} · "
                f"Minimum {money(summary.get('min_eur'))} · "
                f"Durchschnitt {money(summary.get('average_eur'))} · "
                f"Maximum {money(summary.get('max_eur'))}"
            )
        if self.month_status is not None:
            self.month_status.set(
                f"{summary.get('priced_days', 0)} von {summary.get('days', 0)} Tagen berechnet."
            )


if __name__ == "__main__":
    App().mainloop()
