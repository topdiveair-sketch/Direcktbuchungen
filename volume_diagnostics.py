"""Optional read-only volume diagnostics. Not registered by default.

To enable, explicitly register the blueprint and configure both:
ZAB_VOLUME_DIAG_ENABLED=1 and ZAB_VOLUME_DIAG_TOKEN=<random 32+ chars>.
Never expose this endpoint without authentication.
"""
import hmac
import os
import stat
from pathlib import Path
from flask import Blueprint, jsonify, request

volume_diagnostics = Blueprint("volume_diagnostics", __name__)

def scan_volume(root="/data", max_entries=100000):
    """Collect metadata only. Never open, modify, or delete files; avoid symlinks."""
    base = Path(root)
    if not base.is_dir():
        return {"error": "volume_unavailable"}
    seen = 0
    by_directory = {}
    largest = []
    errors = 0
    stack = [(base, "")]
    while stack and seen < max_entries:
        directory, category = stack.pop()
        try:
            with os.scandir(directory) as it:
                for item in it:
                    seen += 1
                    if seen > max_entries:
                        break
                    try:
                        info = item.stat(follow_symlinks=False)
                        if stat.S_ISDIR(info.st_mode):
                            top = item.name if not category else category
                            stack.append((Path(item.path), top))
                        elif stat.S_ISREG(info.st_mode):
                            group = category or "(root)"
                            by_directory[group] = by_directory.get(group, 0) + info.st_size
                            # Return file size and category only; no names or sensitive paths.
                            largest.append((info.st_size, group, Path(item.name).suffix.lower()[:12]))
                            if len(largest) > 30:
                                largest.sort(reverse=True)
                                largest = largest[:20]
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    largest.sort(reverse=True)
    vfs = os.statvfs(base)
    return {
        "capacity_bytes": vfs.f_blocks * vfs.f_frsize,
        "available_bytes": vfs.f_bavail * vfs.f_frsize,
        "directory_bytes": dict(sorted(by_directory.items(), key=lambda kv: -kv[1])[:20]),
        "largest_files": [{"bytes": size, "group": group, "extension": ext} for size, group, ext in largest[:20]],
        "entries_scanned": seen,
        "truncated": bool(stack) or seen >= max_entries,
        "read_errors": errors,
        "readonly": True,
    }

@volume_diagnostics.get("/internal/volume-diagnostics")
def volume_diagnostics_route():
    token = os.environ.get("ZAB_VOLUME_DIAG_TOKEN", "")
    supplied = request.headers.get("X-ZAB-Diagnostics-Token", "")
    if (os.environ.get("ZAB_VOLUME_DIAG_ENABLED") != "1"
            or len(token) < 32
            or not hmac.compare_digest(token, supplied)):
        return jsonify({"error": "not_found"}), 404
    response = jsonify(scan_volume())
    response.headers["Cache-Control"] = "no-store"
    return response
