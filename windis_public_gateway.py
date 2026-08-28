"""Public-safe Windis planning feed. No contact addresses are exposed."""

from datetime import datetime
from flask import jsonify

from railway_app import app, db


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@app.get("/growth/windis-planning-data")
def growth_windis_planning_data():
    with db() as conn:
        partners = conn.execute(
            "SELECT priority,partner,category,approach,next_step,status,target_date,updated_at FROM growth_windis_partners ORDER BY priority,target_date,partner"
        ).fetchall()
        kpis = conn.execute(
            "SELECT metric,start_value,target_oct,target_dec,updated_at FROM growth_windis_kpis ORDER BY metric"
        ).fetchall()
    return jsonify({
        "ok": True,
        "source": "railway-live-public-safe-v2",
        "updatedAt": _now(),
        "partners": [{
            "priority": r["priority"],
            "partner": r["partner"],
            "category": r["category"],
            "approach": r["approach"],
            "nextStep": r["next_step"],
            "status": r["status"],
            "targetDate": r["target_date"],
            "updatedAt": r["updated_at"],
        } for r in partners],
        "kpis": [{
            "metric": r["metric"],
            "start": r["start_value"],
            "targetOct": r["target_oct"],
            "targetDec": r["target_dec"],
            "updatedAt": r["updated_at"],
        } for r in kpis],
    }), 200
