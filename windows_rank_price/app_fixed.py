from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from tkinter import messagebox

from app import APP_NAME, App as BaseApp


class App(BaseApp):
    """Thread-safe Windows client.

    All Tk variable reads and UI updates stay on the main Tk thread. The worker
    only performs the HTTP request and communicates back through a Queue.
    """

    def __init__(self):
        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        super().__init__()
        self.after(100, self._drain_result_queue)

    def fetch(self):
        password = self.pw_var.get()
        if not password:
            messagebox.showwarning(APP_NAME, "Bitte zuerst das Admin-Passwort eintragen.")
            return

        arrival = self.arrival_var.get().strip()
        departure = self.departure_var.get().strip()
        try:
            a = date.fromisoformat(arrival)
            d = date.fromisoformat(departure)
            if d <= a:
                raise ValueError
        except Exception:
            messagebox.showwarning(
                APP_NAME,
                "Bitte gültige An- und Abreisedaten im Format YYYY-MM-DD eingeben.",
            )
            return

        request_data = {
            "base": self.api_var.get().strip().rstrip("/"),
            "password": password,
            "q": self.query_var.get().strip(),
            "room": self.room_var.get().strip(),
            "arrival": arrival,
            "departure": departure,
        }

        self.fetch_btn.state(["disabled"])
        self.status_var.set("Abruf läuft …")
        threading.Thread(
            target=self._fetch_worker_safe,
            args=(request_data,),
            daemon=True,
        ).start()

    def _fetch_worker_safe(self, request_data: dict):
        params = urllib.parse.urlencode(
            {
                "q": request_data["q"],
                "room": request_data["room"],
                "arrival": request_data["arrival"],
                "departure": request_data["departure"],
            }
        )
        request = urllib.request.Request(
            f"{request_data['base']}/api/windows/rank-price-check?{params}",
            headers={
                "X-Admin-Password": request_data["password"],
                "Accept": "application/json",
                "User-Agent": "ZAB-RangPreis-Windows/1.1",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(
                    response.read().decode("utf-8", errors="replace")
                )
            self.result_queue.put(("result", payload))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                msg = "Admin-Passwort wurde vom Server abgelehnt."
            else:
                msg = f"Serverfehler HTTP {exc.code}."
            self.result_queue.put(("error", msg))
        except Exception as exc:
            self.result_queue.put(
                ("error", f"Abruf fehlgeschlagen: {type(exc).__name__}: {exc}")
            )

    def _drain_result_queue(self):
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "result":
                    self._show_result(payload)
                else:
                    self._show_error(str(payload))
        except queue.Empty:
            pass

        if self.winfo_exists():
            self.after(100, self._drain_result_queue)


if __name__ == "__main__":
    App().mainloop()
