"""Publish consistent, integrity-checked SQLite backups, including WAL commits."""
import os
from pathlib import Path
import sqlite3
import tempfile
import time


def verified_sqlite_backup(database, target):
    database, target = Path(database).resolve(), Path(target).resolve()
    if database == target:
        raise ValueError("Backup target must differ from the live database")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".zab-backup-", suffix=".tmp", dir=target.parent)
    os.close(descriptor)
    source = destination = None
    deadline = time.monotonic() + 30
    def bounded_progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite backup deadline exceeded")
    try:
        source = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)
        destination = sqlite3.connect(temporary)
        source.backup(destination, pages=256, progress=bounded_progress, sleep=0.01)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("Backup integrity check failed")
        destination.close()
        destination = None
        source.close()
        source = None
        os.replace(temporary, target)
        return target
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()
        Path(temporary).unlink(missing_ok=True)
