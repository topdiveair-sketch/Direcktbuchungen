from __future__ import annotations

"""Windows launcher with monthly overview plus visible competitor benchmark prices.

Benchmark prices are shown next to Google ranking rows when the backend has a
stored public observation. They are informational only and are never mixed into
the exact same-stay price ranking.
"""

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
        if not candidate:
            continue
        if candidate in wanted or wanted in candidate:
            return row
    return None


class App(MonthApp):
    def __init__(self):
        super().__init__()
        self.rank_tree.configure(columns=("rank", "name", "price", "status", "title"))
        for col, text, width, anchor in [
            ("rank", "Rang", 90, "w"),
            ("name", "Betrieb", 235, "w"),
            ("price", "Benchmarkpreis", 120, "e"),
            ("status", "Status", 170, "w"),
            ("title", "Gefundener Treffer", 460, "w"),
        ]:
            self.rank_tree.heading(col, text=text)
            self.rank_tree.column(col, width=width, anchor=anchor)

    def _show_result(self, data: dict):
        # Let the stable client update cards, price rank, benchmark table and
        # status first. We then redraw only the Google competitor table.
        super()._show_result(data)
        if not data.get("ok"):
            return

        for item in self.rank_tree.get_children():
            self.rank_tree.delete(item)

        provider_error = str(data.get("provider_error") or "").strip()
        benchmarks = [row for row in (data.get("public_benchmarks") or []) if isinstance(row, dict)]
        result_count = int(data.get("ranking_result_count") or 0)

        if provider_error:
            self.rank_tree.insert(
                "",
                "end",
                values=("–", "Google-Rangliste", "–", "derzeit nicht verfügbar", provider_error),
            )
            return

        for row in data.get("competitor_rankings") or []:
            if not isinstance(row, dict):
                continue
            rank = row.get("rank")
            if rank is not None:
                rank_text = f"#{rank}"
                status = "gefunden"
            elif row.get("status") == "not_configured":
                rank_text = "–"
                status = "API fehlt"
            elif row.get("status") in {"error", "unavailable"}:
                rank_text = "–"
                status = "derzeit nicht verfügbar"
            else:
                rank_text = f"nicht in Top {result_count}" if result_count else "nicht gefunden"
                status = "nicht gefunden"

            benchmark = _benchmark_for(row.get("name", ""), benchmarks)
            price_text = money(benchmark.get("price_eur")) if benchmark else "–"
            self.rank_tree.insert(
                "",
                "end",
                values=(rank_text, row.get("name", ""), price_text, status, row.get("title", "")),
            )


if __name__ == "__main__":
    App().mainloop()
