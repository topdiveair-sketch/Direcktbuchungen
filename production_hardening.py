from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from flask import after_this_request, jsonify, request, send_file


DEFAULT_SAFETY_SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/topdiveair-sketch/"
    "Direcktbuchungen/main/booking-calendar.json"
)


def _env_true(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _path_inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def init_production_hardening(app, legacy_app, authorize):
    """Harden Railway SQLite operation without changing public booking semantics.

    The module deliberately does not migrate storage by itself. A Railway volume
    must only be enabled after the currently running database has been exported.
    Once deployed, this module provides a protected consistent SQLite backup
    endpoint so future migrations never need to depend on container shell access.
    """

    db_path = Path(legacy_app.DB_PATH).expanduser().resolve()

    def hardened_db() -> sqlite3.Connection:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        try:
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            pass
        return conn

    # Replace the legacy factory before the calendar/control-center modules are
    # initialized. Existing functions in app.py resolve the module global at
    # call time and therefore also benefit from the hardened connection.
    legacy_app.db = hardened_db

    def storage_status(include_private: bool = False) -> dict:
        mount_raw = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
        mount = Path(mount_raw).expanduser().resolve() if mount_raw else None
        data_dir = Path(os.environ.get("DATA_DIR", str(db_path.parent))).expanduser().resolve()
        persistent = bool(mount and _path_inside(db_path, mount))
        status = {
            "database_exists": db_path.is_file(),
            "database_size_bytes": db_path.stat().st_size if db_path.is_file() else 0,
            "volume_mount_configured": bool(mount),
            "persistent_storage": persistent,
            "persistent_storage_required": _env_true("REQUIRE_PERSISTENT_STORAGE"),
            "sqlite_busy_timeout_ms": 30000,
            "sqlite_wal_requested": True,
        }
        if include_private:
            status.update(
                database_path=str(db_path),
                data_dir=str(data_dir),
                volume_mount_path=str(mount) if mount else "",
            )
        return status

    def quick_check() -> str:
        if not db_path.is_file():
            return "database_missing"
        with hardened_db() as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
        return str(row[0] if row else "unknown")

    def _booking_ical_is_configured() -> bool:
        try:
            with hardened_db() as conn:
                row = conn.execute(
                    "SELECT import_url FROM ical_settings WHERE room='Bachblick'"
                ).fetchone()
            return bool(row and str(row["import_url"] or "").strip().startswith("https://"))
        except sqlite3.DatabaseError:
            return False

    def refresh_booking_safety_snapshot() -> dict:
        """Mirror only known Booking blocks from the public hybrid snapshot.

        This is a fail-closed recovery path for a fresh or partially restored
        database. It is never used as evidence that a date is free. If a real
        Booking iCal URL is configured in the preserved DB, that source remains
        authoritative and this recovery mirror does nothing.
        """
        if not db_path.is_file():
            return {"status": "database_missing", "inserted": 0}
        if _booking_ical_is_configured():
            return {"status": "booking_ical_configured", "inserted": 0}

        snapshot_url = os.environ.get(
            "ZAB_PUBLIC_CALENDAR_JSON_URL", DEFAULT_SAFETY_SNAPSHOT_URL
        ).strip()
        if not snapshot_url:
            return {"status": "snapshot_disabled", "inserted": 0}
        separator = "&" if "?" in snapshot_url else "?"
        req = urllib.request.Request(
            f"{snapshot_url}{separator}_bootstrap={int(datetime.now(timezone.utc).timestamp())}",
            headers={
                "User-Agent": "ZAB-Production-Hardening/1.1",
                "Accept": "application/json",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            # Keep the previous mirrored safety blocks on fetch failure.
            return {"status": "snapshot_unreachable", "inserted": 0, "message": str(exc)[:300]}

        events = payload.get("events")
        if not isinstance(events, list):
            return {"status": "snapshot_invalid", "inserted": 0}

        future_events = []
        today = date.today()
        for event in events:
            if not isinstance(event, dict):
                continue
            source_text = str(event.get("source") or "")
            if "booking ical" not in source_text.casefold():
                continue
            try:
                start = date.fromisoformat(str(event.get("start") or ""))
                end = date.fromisoformat(str(event.get("end") or ""))
            except ValueError:
                continue
            if end <= start or end <= today:
                continue
            future_events.append((start, end))

        inserted = 0
        removed = 0
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with hardened_db() as conn:
                # Remove only blocks previously created by this recovery mirror.
                removed = conn.execute(
                    """DELETE FROM external_blocks
                       WHERE room='Bachblick' AND source='booking_ical'
                         AND uid LIKE 'booking-safety-%@zab'"""
                ).rowcount
                for start, end in future_events:
                    # Do not duplicate a real iCal/API block on identical dates.
                    real = conn.execute(
                        """SELECT 1 FROM external_blocks
                           WHERE room='Bachblick' AND source='booking_ical'
                             AND start_date=? AND end_date=?
                             AND uid NOT LIKE 'booking-safety-%@zab' LIMIT 1""",
                        (start.isoformat(), end.isoformat()),
                    ).fetchone()
                    if real:
                        continue
                    uid = f"booking-safety-{start.isoformat()}-{end.isoformat()}@zab"
                    conn.execute(
                        """INSERT INTO external_blocks
                           (room,start_date,end_date,source,uid,summary,imported_at)
                           VALUES('Bachblick',?,?,'booking_ical',?,'Booking.com Sicherheitsblock',?)""",
                        (start.isoformat(), end.isoformat(), uid, now),
                    )
                    inserted += 1
        except sqlite3.DatabaseError as exc:
            return {"status": "database_error", "inserted": 0, "message": str(exc)[:300]}

        return {
            "status": "mirrored",
            "inserted": inserted,
            "removed_previous": max(0, int(removed or 0)),
            "snapshot_updated_at": str(payload.get("updatedAtIso") or ""),
        }

    safety_lock = threading.Lock()
    safety_state = {
        "last_run": time.monotonic(),
        "result": refresh_booking_safety_snapshot(),
    }

    def maybe_refresh_booking_safety() -> None:
        if time.monotonic() - float(safety_state["last_run"]) < 300:
            return
        if not safety_lock.acquire(blocking=False):
            return
        try:
            if time.monotonic() - float(safety_state["last_run"]) < 300:
                return
            safety_state["last_run"] = time.monotonic()
            safety_state["result"] = refresh_booking_safety_snapshot()
            app.extensions["zab_booking_safety_bootstrap"] = dict(safety_state["result"])
        finally:
            safety_lock.release()

    app.extensions["zab_sqlite_hardened"] = True
    app.extensions["zab_storage_status"] = storage_status
    app.extensions["zab_storage_quick_check"] = quick_check
    app.extensions["zab_refresh_booking_safety"] = refresh_booking_safety_snapshot
    app.extensions["zab_booking_safety_bootstrap"] = dict(safety_state["result"])

    @app.before_request
    def refresh_safety_for_central_calendar():
        if request.path in {"/api/central/zab-calendar", "/api/central/master-calendar"}:
            maybe_refresh_booking_safety()
        return None

    @app.get("/health/zab-storage")
    def zab_storage_health():
        status = storage_status(False)
        integrity = quick_check()
        required = bool(status["persistent_storage_required"])
        ok = (
            status["database_exists"]
            and integrity == "ok"
            and (not required or status["persistent_storage"])
        )
        return jsonify(
            ok=ok,
            sqlite_integrity=integrity,
            booking_safety_bootstrap=app.extensions.get("zab_booking_safety_bootstrap", {}),
            **status,
        ), 200 if ok else 503

    @app.get("/api/central/system/storage-status")
    def central_storage_status():
        if not authorize():
            return jsonify(ok=False, error="unauthorized"), 401
        status = storage_status(True)
        status["sqlite_integrity"] = quick_check()
        status["booking_safety_bootstrap"] = app.extensions.get("zab_booking_safety_bootstrap", {})
        status["ok"] = status["database_exists"] and status["sqlite_integrity"] == "ok"
        return jsonify(status), 200, {"Cache-Control": "no-store"}

    @app.get("/api/central/system/db-backup")
    def central_database_backup():
        """Download a transactionally consistent private SQLite backup.

        The response is protected by the same X-Admin-Password credential as
        the Windows CENTRAL APIs. Guest/booking data therefore never becomes a
        public artifact or a GitHub file.
        """
        if not authorize():
            return jsonify(ok=False, error="unauthorized"), 401
        if not db_path.is_file():
            return jsonify(ok=False, error="database_missing"), 404

        tmp = tempfile.NamedTemporaryFile(prefix="zab-backup-", suffix=".db", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        try:
            with hardened_db() as source, sqlite3.connect(tmp_path) as target:
                source.backup(target)
                result = target.execute("PRAGMA integrity_check").fetchone()
                integrity = str(result[0] if result else "unknown")
            if integrity != "ok":
                tmp_path.unlink(missing_ok=True)
                return jsonify(ok=False, error="backup_integrity_failed", detail=integrity), 500
            checksum = _sha256(tmp_path)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            return jsonify(ok=False, error="backup_failed", detail=str(exc)[:500]), 500

        @after_this_request
        def cleanup(response):
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return response

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        response = send_file(
            tmp_path,
            as_attachment=True,
            download_name=f"zab-production-{stamp}.db",
            mimetype="application/vnd.sqlite3",
            max_age=0,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-ZAB-SHA256"] = checksum
        response.headers["X-ZAB-SQLite-Integrity"] = "ok"
        return response

    return storage_status
