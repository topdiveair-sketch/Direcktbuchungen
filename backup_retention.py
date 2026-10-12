"""Conservative retention of generated automatic SQLite backups only.

Never touches live DB, manual backups, backups-auto, or unknown file names.
"""
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

AUTO = re.compile(r"^zab-auto-(\d{8})-(\d{6})\.db$")

def prune_auto_backups(directory, now=None):
    folder = Path(directory)
    if not folder.is_dir() or folder.is_symlink():
        return {"deleted": 0, "bytes_freed": 0, "reason": "folder_missing"}
    now = now or datetime.now(timezone.utc)
    items = []
    try:
        for p in folder.iterdir():
            m = AUTO.fullmatch(p.name)
            if not m:
                continue
            try:
                info = p.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_size < 100:
                    continue
                stamp = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                if stamp > now + timedelta(days=1):
                    continue
                items.append((stamp, p, info))
            except (OSError, ValueError):
                continue
    except OSError:
        return {"deleted": 0, "bytes_freed": 0, "reason": "scan_failed"}
    items.sort(key=lambda x: x[0], reverse=True)
    if len(items) <= 40:
        return {"deleted": 0, "bytes_freed": 0, "reason": "few_copies"}
    keep = set(p for _, p, _ in items[:24])
    daily = set()
    monthly = set()
    for stamp, p, _ in items:
        age = now - stamp
        if age <= timedelta(days=30):
            key = stamp.date()
            if key not in daily:
                daily.add(key)
                keep.add(p)
        elif age <= timedelta(days=365):
            key = (stamp.year, stamp.month)
            if key not in monthly:
                monthly.add(key)
                keep.add(p)
    # Keep at least 24 latest automatic backups even when they are all from today.
    deleted = 0
    freed = 0
    for _, p, original in items:
        if p in keep:
            continue
        try:
            current = p.lstat()
            if (not stat.S_ISREG(current.st_mode)
                    or current.st_ino != original.st_ino
                    or current.st_size != original.st_size):
                continue
            p.unlink()
            deleted += 1
            freed += original.st_size
        except OSError:
            continue
    return {"deleted": deleted, "bytes_freed": freed, "kept_auto": len(keep)}
