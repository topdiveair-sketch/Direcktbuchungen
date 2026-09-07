"""Daily idempotent scheduler for market-leader KPI snapshots."""
from __future__ import annotations

import os
import threading
import time
from datetime import date


def init_market_leader_scheduler(app, db, summary):
    if app.extensions.get("zab_market_leader_scheduler_initialized"):
        return
    app.extensions["zab_market_leader_scheduler_initialized"] = True

    def already_done_today() -> bool:
        try:
            with db() as conn:
                return bool(
                    conn.execute(
                        "SELECT 1 FROM market_run_quality WHERE snapshot_date=?",
                        (date.today().isoformat(),),
                    ).fetchone()
                )
        except Exception:
            return False

    def loop():
        # Provider monitor starts after 45 seconds. Give it time to refresh first.
        time.sleep(90)
        while True:
            try:
                if not already_done_today():
                    summary(refresh_competitors=True)
            except Exception:
                # Measurement must never take down the booking application.
                pass
            time.sleep(3600)

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        threading.Thread(
            target=loop,
            daemon=True,
            name="zab-market-leader-daily",
        ).start()
