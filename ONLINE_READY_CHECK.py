from __future__ import annotations

import py_compile
import sys
from pathlib import Path


REQUIRED_FILES = [
    "app.py",
    "requirements.txt",
    "railway.json",
    "Procfile",
    ".gitignore",
    ".env.example",
    ".env.production.template",
    "LIVE_PREFLIGHT.py",
    "POST_DEPLOY_CHECK.py",
    "README_DEPLOY_RAILWAY.md",
    "templates/index.html",
    "templates/admin_login.html",
    "static/css/style.css",
    "static/js/app.js",
    "static/images/aggsbach-markt-luftbild.png",
]

FORBIDDEN_PARTS = {
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    "backups",
    "restore_points",
    "invoices",
    "documents",
    "media_library",
    "imports",
    "work",
    "outputs",
}

FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
}

TEXT_SUFFIXES = {
    ".py", ".html", ".css", ".js", ".md", ".txt", ".json", ".bat", ".ps1"
}

MOJIBAKE_MARKERS = {
    "\ufffd",
    "\u00c3",
    "\u00c2",
    "\u00e2",
}


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, details: str = "") -> None:
        checks.append((name, ok, details))

    check("Projektordner vorhanden", root.exists() and root.is_dir(), str(root))

    for rel in REQUIRED_FILES:
        check(f"Pflichtdatei {rel}", (root / rel).exists(), rel)

    forbidden = []
    for path in root.rglob("*"):
        rel_parts = set(path.relative_to(root).parts)
        if rel_parts & FORBIDDEN_PARTS:
            if path.name == ".gitkeep" and "data" in rel_parts:
                continue
            forbidden.append(str(path.relative_to(root)))
            continue
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            forbidden.append(str(path.relative_to(root)))

    check("Keine Betriebsdaten/Caches im Paket", not forbidden, ", ".join(forbidden[:12]))

    encoding_errors = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if set(rel.parts) & FORBIDDEN_PARTS:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            encoding_errors.append(f"{rel}: {exc}")
            continue
        if any(marker in content for marker in MOJIBAKE_MARKERS):
            encoding_errors.append(str(rel))

    check("UTF-8 ohne kaputte Umlaute", not encoding_errors, ", ".join(encoding_errors[:12]))

    for name in [
        "app.py", "addons.py", "v6_features.py", "stability.py", "zab_os.py",
        "alltag.py", "host_assistant.py", "smart_host.py", "knowledge.py",
        "quality_v12.py", "LIVE_PREFLIGHT.py", "POST_DEPLOY_CHECK.py",
    ]:
        path = root / name
        if not path.exists():
            continue
        try:
            py_compile.compile(str(path), doraise=True)
            check(f"Python Syntax {name}", True)
        except Exception as exc:
            check(f"Python Syntax {name}", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"{passed}/{total} Online-Ready-Checks OK")
    for name, ok, details in checks:
        suffix = f" - {details}" if details else ""
        print(("OK" if ok else "FEHLT"), name + suffix)

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
