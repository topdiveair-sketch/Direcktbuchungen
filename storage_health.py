"""Read-only SQLite/volume readiness, without paths, guest data or credentials."""
import os
from pathlib import Path
import sqlite3


def storage_snapshot(database, volume=None):
    database = Path(database).resolve()
    volume = Path(volume).resolve() if volume else None
    mounted = bool(volume and os.path.ismount(volume))
    on_volume = bool(volume and database.is_relative_to(volume))
    result = dict(ok=False, readonly=True, database_present=database.is_file(),
                  database_readable=False, integrity_ok=False, bookings_table=False,
                  volume_mounted=mounted, database_on_volume=on_volume,
                  restore_tested=False, revision="storage-health-20261030")
    if not result["database_present"]:
        result["error"] = "database_missing"
        return result
    try:
        # mode=ro cannot create an empty database or change its schema/content.
        conn = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            conn.execute("PRAGMA query_only=ON")
            result["integrity_ok"] = conn.execute("PRAGMA quick_check(1)").fetchone()[0] == "ok"
            result["bookings_table"] = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bookings'"
            ).fetchone() is not None
            result["database_readable"] = True
        finally:
            conn.close()
    except sqlite3.Error:
        result["error"] = "database_unreadable"
    result["ok"] = all(result[key] for key in (
        "database_readable", "integrity_ok", "bookings_table", "volume_mounted", "database_on_volume"))
    return result
