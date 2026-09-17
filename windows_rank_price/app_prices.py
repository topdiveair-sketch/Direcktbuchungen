from __future__ import annotations

"""Windows launcher with monthly overview plus 1-night and 3-night competitor prices."""

import re
import unicodedata

from app_fixed import App as MonthApp
from app import money


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _benchmark_for(name: str, rows: list[dict]) -> dict | None:
    wanted = _norm(name)
    if not wanted:
        return None
    for row in rows:
        candidate = _norm(row.get("name", ""))
        if candidate and candidate == wanted:
            return row
    for row in rows:
        candidate = _norm(row.get("name", ""))
        if candidate and (candidate in wanted or wanted in candidate):
            return row
    return None


class App(MonthApp):
    def __init__(self):
        super().__init__()
        self.geometry("1380x880")
        self.rank_tree.configure(
            columns=("rank", "name", "one", "three", "avg", "availability", "status", "title")
        )
        for col, text, width, anchor in [
            ("rank", "Rang", 80, "w"),
            ("name", "Betrieb", 230, "w"),
            ("one", "1 Nacht", 105, "e"),
            ("three", "3 Nächte", 105, "e"),
            ("avg", "Ø/Nacht (3N)", 115, "e"),
            ("availability", "Buchbarkeit", 125, "w"),
            ("status", "Google-Status", 135, "w"),
            ("title", "Gefundener Treffer", 320, "w"),
        ]:
            self.rank_tree.heading(col, text=text)
            self.rank_tree.column(col, width=width, anchor=anchor)

    def _show_result(self, data: dict):
        super()._show_result(data)
        if not data.get("ok"):
            return

        for item in self.rank_tree.get_children():
            self.rank_tree.delete(item)

        provider_error = str(data.get("provider_error") or "").strip()
        benchmarks = [row for row in (data.get("public_benchmarks") or []) if isinstance(row, dict)]
        result_count = int(data.get("ranking_result_count") or 0)

        for row in data.get("competitor_rankings") or []:
            if not isinstance(row, dict):
                continue
            rank = row.get("rank")
            if rank is not None:
                rank_text = f"#{rank}"
                google_status = "gefunden"
            elif row.get("status") == "not_configured":
                rank_text = "–"
                google_status = "API fehlt"
            elif row.get("status") in {"error", "unavailable"}:
                rank_text = "–"
                google_status = "nicht verfügbar"
            else:
                rank_text = f"nicht Top {result_count}" if result_count else "nicht gefunden"
                google_status = "nicht gefunden"

            benchmark = _benchmark_for(row.get("name", ""), benchmarks) or {}
            one_text = money(benchmark.get("one_night_total_eur"))
            three_text = money(benchmark.get("three_night_total_eur"))
            avg_text = money(benchmark.get("three_night_average_eur"))
            availability = str(benchmark.get("availability") or "kein Preis gefunden")

            self.rank_tree.insert(
                "",
                "end",
                values=(
                    rank_text,
                    row.get("name", ""),
                    one_text,
                    three_text,
                    avg_text,
                    availability,
                    google_status,
                    row.get("title", ""),
                ),
            )

        if provider_error:
            self.status_var.set(
                "Mitbewerberpreise wurden separat abgefragt; organische Google-Rangliste derzeit nicht verfügbar."
            )
        else:
            n1 = int(data.get("hotel_one_night_match_count") or 0)
            n3 = int(data.get("hotel_three_night_match_count") or 0)
            price_error = str(data.get("hotel_price_error") or "").strip()
            suffix = f" · Preisfehler: {price_error}" if price_error else ""
            self.status_var.set(
                f"Abruf abgeschlossen · 1 Nacht: {n1} Preis-Treffer · 3 Nächte: {n3} Preis-Treffer{suffix}"
            )


if __name__ == "__main__":
    App().mainloop()
