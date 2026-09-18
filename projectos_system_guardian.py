"""Prem ProjectOS System Guardian.

Central health audit and conservative self-healing for the user's application
landscape. The guardian may perform only low-risk repairs. Destructive actions,
secret changes and infrastructure deletion are deliberately excluded.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


DEFAULT_TARGETS = [
    {
        "name": "Direktpreis API",
        "url": "https://web-production-2b242.up.railway.app/health/wachauetappe_production",
        "kind": "json",
        "required": True,
    },
    {
        "name": "ZAB Master / Booking Control",
        "url": "https://web-production-907d68.up.railway.app/health/zab-control-center",
        "kind": "json",
        "required": True,
    },
    {
        "name": "Direktbuchung Website",
        "url": "https://topdiveair-sketch.github.io/Direcktbuchungen/",
        "kind": "html",
        "required": True,
    },
    {
        "name": "Gaesteguide",
        "url": "https://topdiveair-sketch.github.io/Gaeste/",
        "kind": "html",
        "required": False,
    },
    {
        "name": "Mobile App",
        "url": "https://topdiveair-sketch.github.io/HaendyMen/",
        "kind": "html",
        "required": False,
    },
    {
        "name": "Direktanfrage",
        "url": "https://topdiveair-sketch.github.io/Direkt/",
        "kind": "html",
        "required": False,
    },
    {
        "name": "Gaeste App",
        "url": "https://topdiveair-sketch.github.io/gaestapp/",
        "kind": "html",
        "required": False,
    },
]

SEVERITY_ORDER = {"ok": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utcnow().isoformat(timespec="seconds")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _targets() -> list[dict[str, Any]]:
    raw = os.environ.get("PROJECTOS_GUARDIAN_TARGETS_JSON", "").strip()
    if not raw:
        return list(DEFAULT_TARGETS)
    try:
        parsed = json.loads(raw)
    except Exception:
        return list(DEFAULT_TARGETS)
    if not isinstance(parsed, list):
        return list(DEFAULT_TARGETS)
    targets: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        if not name or not url.startswith("https://"):
            continue
        targets.append(
            {
                "name": name[:100],
                "url": url,
                "kind": str(item.get("kind") or "json")[:20],
                "required": bool(item.get("required", False)),
            }
        )
    return targets or list(DEFAULT_TARGETS)


def _finding(
    component: str,
    severity: str,
    code: str,
    message: str,
    *,
    repaired: bool = False,
    manual_action_required: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "component": component,
        "severity": severity,
        "code": code,
        "message": message,
        "repaired": repaired,
        "manual_action_required": manual_action_required,
        "details": details or {},
    }


def _http_check(target: dict[str, Any], timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    req = urllib.request.Request(
        target["url"],
        headers={
            "User-Agent": "Prem-ProjectOS-System-Guardian/1.0",
            "Accept": "application/json,text/html,text/plain,*/*",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            content_type = str(response.headers.get("Content-Type", ""))
            body = response.read(262144).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return _finding(
            target["name"],
            "critical" if target.get("required") else "error",
            "http_error",
            f"HTTP {exc.code} von {target['name']}.",
            details={"url": target["url"], "http_status": exc.code},
        )
    except Exception as exc:
        return _finding(
            target["name"],
            "critical" if target.get("required") else "error",
            "unreachable",
            f"{target['name']} ist nicht erreichbar.",
            details={"url": target["url"], "error": str(exc)[:300]},
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if status >= 500:
        severity = "critical" if target.get("required") else "error"
        return _finding(
            target["name"],
            severity,
            "server_error",
            f"{target['name']} antwortet mit HTTP {status}.",
            details={"url": target["url"], "http_status": status, "latency_ms": elapsed_ms},
        )

    if target.get("kind") == "json" or "json" in content_type.lower():
        try:
            payload = json.loads(body)
        except Exception:
            return _finding(
                target["name"],
                "error",
                "invalid_json",
                f"{target['name']} liefert keine gueltige JSON-Antwort.",
                details={"url": target["url"], "latency_ms": elapsed_ms},
            )
        if isinstance(payload, dict):
            if payload.get("ok") is False:
                return _finding(
                    target["name"],
                    "critical" if target.get("required") else "error",
                    "reported_unhealthy",
                    f"{target['name']} meldet einen Fehlerzustand.",
                    manual_action_required=True,
                    details={"url": target["url"], "payload": payload, "latency_ms": elapsed_ms},
                )
            if payload.get("degraded") is True:
                return _finding(
                    target["name"],
                    "warning",
                    "reported_degraded",
                    f"{target['name']} ist erreichbar, meldet aber einen eingeschraenkten Zustand.",
                    manual_action_required=True,
                    details={"url": target["url"], "payload": payload, "latency_ms": elapsed_ms},
                )

    if elapsed_ms > 4000:
        return _finding(
            target["name"],
            "warning",
            "slow_response",
            f"{target['name']} antwortet ungewoehnlich langsam.",
            details={"url": target["url"], "latency_ms": elapsed_ms},
        )

    return _finding(
        target["name"],
        "ok",
        "reachable",
        f"{target['name']} ist erreichbar.",
        details={"url": target["url"], "http_status": status, "latency_ms": elapsed_ms},
    )


def init_projectos_system_guardian(app, db: Callable):
    state_lock = threading.Lock()
    state: dict[str, Any] = {
        "last_run": None,
        "last_result": None,
        "running": False,
        "scheduler_started": False,
    }

    def _db_checks(auto_repair: bool) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        try:
            with db() as conn:
                quick = conn.execute("PRAGMA quick_check").fetchone()
                quick_value = str(quick[0] if quick else "").strip().lower()
                if quick_value != "ok":
                    findings.append(
                        _finding(
                            "ProjectOS Datenbank",
                            "critical",
                            "sqlite_integrity",
                            "SQLite-Integritaetspruefung ist fehlgeschlagen.",
                            manual_action_required=True,
                            details={"quick_check": quick_value},
                        )
                    )
                else:
                    findings.append(
                        _finding(
                            "ProjectOS Datenbank",
                            "ok",
                            "sqlite_integrity",
                            "SQLite-Integritaet ist in Ordnung.",
                        )
                    )

                tables = {
                    str(row[0])
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                required_tables = {"bookings", "ical_settings"}
                missing = sorted(required_tables - tables)
                if missing:
                    findings.append(
                        _finding(
                            "ProjectOS Datenbank",
                            "critical",
                            "required_tables_missing",
                            "Erforderliche Datenbanktabellen fehlen.",
                            manual_action_required=True,
                            details={"missing_tables": missing},
                        )
                    )

                if "ical_settings" in tables:
                    row = conn.execute(
                        "SELECT import_url,last_sync,last_result FROM ical_settings WHERE room='Bachblick'"
                    ).fetchone()
                    if row:
                        import_url = str(row["import_url"] or "").strip()
                        last_sync = str(row["last_sync"] or "").strip()
                        last_result = str(row["last_result"] or "").strip()
                        stale = True
                        if last_sync:
                            try:
                                parsed = datetime.fromisoformat(last_sync)
                                if parsed.tzinfo is None:
                                    parsed = parsed.replace(tzinfo=timezone.utc)
                                stale = _utcnow() - parsed.astimezone(timezone.utc) > timedelta(minutes=30)
                            except Exception:
                                stale = True
                        if not import_url:
                            findings.append(
                                _finding(
                                    "Booking iCal",
                                    "warning",
                                    "ical_not_configured",
                                    "Booking-iCal ist fuer Bachblick nicht konfiguriert.",
                                    manual_action_required=True,
                                )
                            )
                        elif stale:
                            repaired = False
                            repair_details: dict[str, Any] = {"last_sync": last_sync, "last_result": last_result}
                            if auto_repair:
                                sync = app.extensions.get("zab_sync_room")
                                if callable(sync):
                                    try:
                                        count, message = sync("Bachblick")
                                        repaired = "erfolgreich" in str(message).lower()
                                        repair_details.update({"events": count, "repair_result": str(message)})
                                    except Exception as exc:
                                        repair_details["repair_error"] = str(exc)[:300]
                            findings.append(
                                _finding(
                                    "Booking iCal",
                                    "info" if repaired else "warning",
                                    "ical_stale",
                                    (
                                        "Booking-iCal war veraltet und wurde automatisch synchronisiert."
                                        if repaired
                                        else "Booking-iCal wurde seit mehr als 30 Minuten nicht erfolgreich synchronisiert."
                                    ),
                                    repaired=repaired,
                                    manual_action_required=not repaired,
                                    details=repair_details,
                                )
                            )
                        else:
                            findings.append(
                                _finding(
                                    "Booking iCal",
                                    "ok",
                                    "ical_fresh",
                                    "Booking-iCal-Synchronisierung ist aktuell.",
                                    details={"last_sync": last_sync, "last_result": last_result},
                                )
                            )
        except Exception as exc:
            findings.append(
                _finding(
                    "ProjectOS Datenbank",
                    "critical",
                    "database_unavailable",
                    "Die ProjectOS-Datenbank konnte nicht geprueft werden.",
                    manual_action_required=True,
                    details={"error": str(exc)[:300]},
                )
            )
        return findings

    def _runtime_checks(auto_repair: bool) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        required_extensions = [
            ("Direktbuchungs-Metriken", "zab_direct_booking_metrics_initialized"),
            ("Marktfuehrer-Metriken", "zab_market_leader_metrics_initialized"),
            ("Marktfuehrer-Scheduler", "zab_market_leader_scheduler_initialized"),
        ]
        for label, key in required_extensions:
            if app.extensions.get(key):
                findings.append(_finding(label, "ok", "extension_loaded", f"{label} ist aktiv."))
            else:
                findings.append(
                    _finding(
                        label,
                        "error",
                        "extension_missing",
                        f"{label} ist nicht initialisiert.",
                        manual_action_required=True,
                    )
                )

        releaser = app.extensions.get("zab_release_expired_holds")
        if callable(releaser):
            if auto_repair:
                try:
                    releaser()
                    findings.append(
                        _finding(
                            "Buchungs-Holds",
                            "ok",
                            "expired_holds_released",
                            "Abgelaufene Buchungs-Holds wurden bereinigt.",
                            repaired=True,
                        )
                    )
                except Exception as exc:
                    findings.append(
                        _finding(
                            "Buchungs-Holds",
                            "warning",
                            "hold_cleanup_failed",
                            "Abgelaufene Buchungs-Holds konnten nicht automatisch bereinigt werden.",
                            manual_action_required=True,
                            details={"error": str(exc)[:300]},
                        )
                    )
            else:
                findings.append(
                    _finding("Buchungs-Holds", "ok", "cleanup_available", "Automatische Hold-Bereinigung ist verfuegbar.")
                )

        booking_checker = app.extensions.get("zab_booking_connectivity_status")
        if callable(booking_checker):
            try:
                status = booking_checker("Bachblick")
            except Exception as exc:
                status = {"configured": False, "error": str(exc)[:300]}
            if status.get("configured"):
                findings.append(
                    _finding("Booking Connectivity", "ok", "booking_connectivity_ready", "Booking.com Connectivity ist betriebsbereit.")
                )
            else:
                findings.append(
                    _finding(
                        "Booking Connectivity",
                        "warning",
                        "booking_connectivity_incomplete",
                        "Booking.com Connectivity ist nicht vollstaendig konfiguriert; Kalender-Fallback bleibt erforderlich.",
                        manual_action_required=True,
                        details=status,
                    )
                )

        required_env = ["SECRET_KEY", "ADMIN_PASSWORD"]
        missing_env = [name for name in required_env if not os.environ.get(name, "").strip()]
        if missing_env:
            findings.append(
                _finding(
                    "ProjectOS Konfiguration",
                    "critical",
                    "required_env_missing",
                    "Erforderliche Produktionskonfiguration fehlt.",
                    manual_action_required=True,
                    details={"missing_variables": missing_env},
                )
            )
        else:
            findings.append(
                _finding("ProjectOS Konfiguration", "ok", "required_env_present", "Erforderliche Produktionsvariablen sind gesetzt.")
            )
        return findings

    def run_audit(auto_repair: bool = False) -> dict[str, Any]:
        with state_lock:
            if state["running"]:
                previous = state.get("last_result")
                return previous or {
                    "ok": False,
                    "status": "busy",
                    "generated_at": _iso_now(),
                    "findings": [],
                }
            state["running"] = True

        started = time.monotonic()
        findings: list[dict[str, Any]] = []
        try:
            findings.extend(_runtime_checks(auto_repair))
            findings.extend(_db_checks(auto_repair))
            timeout = max(2.0, min(float(os.environ.get("PROJECTOS_GUARDIAN_HTTP_TIMEOUT_SECONDS", "8")), 20.0))
            for target in _targets():
                findings.append(_http_check(target, timeout))

            worst = max((SEVERITY_ORDER.get(item["severity"], 0) for item in findings), default=0)
            errors = sum(1 for item in findings if SEVERITY_ORDER.get(item["severity"], 0) >= 3)
            warnings = sum(1 for item in findings if item["severity"] == "warning")
            repaired = sum(1 for item in findings if item.get("repaired"))
            manual = sum(1 for item in findings if item.get("manual_action_required"))
            status = "critical" if worst >= 4 else "error" if worst >= 3 else "degraded" if worst >= 2 else "ok"
            result = {
                "ok": errors == 0,
                "status": status,
                "mode": "repair" if auto_repair else "audit",
                "generated_at": _iso_now(),
                "duration_ms": int((time.monotonic() - started) * 1000),
                "summary": {
                    "checks": len(findings),
                    "errors": errors,
                    "warnings": warnings,
                    "repairs_applied": repaired,
                    "manual_actions": manual,
                },
                "findings": findings,
                "guardrails": {
                    "destructive_actions": False,
                    "secret_mutation": False,
                    "infrastructure_deletion": False,
                    "safe_repairs_only": True,
                },
            }
            with state_lock:
                state["last_run"] = result["generated_at"]
                state["last_result"] = result
            return result
        finally:
            with state_lock:
                state["running"] = False

    def _scheduler_loop() -> None:
        interval = max(300, min(int(os.environ.get("PROJECTOS_GUARDIAN_INTERVAL_SECONDS", "900")), 86400))
        initial_delay = max(5, min(int(os.environ.get("PROJECTOS_GUARDIAN_INITIAL_DELAY_SECONDS", "30")), 600))
        time.sleep(initial_delay)
        while True:
            try:
                run_audit(auto_repair=_env_bool("PROJECTOS_GUARDIAN_AUTO_REPAIR", True))
            except Exception:
                pass
            time.sleep(interval)

    def start_scheduler() -> bool:
        enabled = _env_bool("PROJECTOS_GUARDIAN_ENABLED", bool(os.environ.get("PROJECTOS_ANALYTICS_TOKEN", "").strip()))
        if not enabled:
            return False
        with state_lock:
            if state["scheduler_started"]:
                return True
            state["scheduler_started"] = True
        thread = threading.Thread(target=_scheduler_loop, name="projectos-system-guardian", daemon=True)
        thread.start()
        return True

    app.extensions["projectos_system_guardian_run"] = run_audit
    app.extensions["projectos_system_guardian_state"] = state
    app.extensions["projectos_system_guardian_initialized"] = True
    app.extensions["projectos_system_guardian_scheduler"] = start_scheduler()
    return run_audit
