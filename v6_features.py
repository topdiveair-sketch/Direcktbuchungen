
from __future__ import annotations
import csv, io, json, os, sqlite3, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe

from flask import (
    Response, flash, jsonify, redirect, render_template, request,
    session, url_for, send_file
)
from werkzeug.utils import secure_filename

def init_v6(app, DB_PATH, db, require_admin, ROOMS):
    uploads = Path(DB_PATH).parent / "documents"
    uploads.mkdir(parents=True, exist_ok=True)
    allowed = {"pdf","jpg","jpeg","png","webp"}

    def ensure_col(conn, table, name, definition):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if name not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    with db() as conn:
        ensure_col(conn, "bookings", "checkin_token", "TEXT DEFAULT ''")
        ensure_col(conn, "bookings", "checked_in", "INTEGER DEFAULT 0")
        ensure_col(conn, "bookings", "language", "TEXT DEFAULT 'de'")
        ensure_col(conn, "bookings", "country", "TEXT DEFAULT ''")
        ensure_col(conn, "bookings", "postal_code", "TEXT DEFAULT ''")
        ensure_col(conn, "bookings", "city", "TEXT DEFAULT ''")
        ensure_col(conn, "bookings", "street", "TEXT DEFAULT ''")
        ensure_col(conn, "bookings", "document_type", "TEXT DEFAULT ''")
        ensure_col(conn, "bookings", "document_number", "TEXT DEFAULT ''")
        ensure_col(conn, "bookings", "vehicle_plate", "TEXT DEFAULT ''")

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS maintenance_blocks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS booking_documents(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            category TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS channel_settings(
            channel TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            import_url TEXT DEFAULT '',
            export_url TEXT DEFAULT '',
            api_key TEXT DEFAULT '',
            note TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS host_notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'neu',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS translations(
            lang TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY(lang,key)
        );
        """)
        for channel in ("Booking.com","Airbnb","Expedia","FeWo-direkt","Google Hotels"):
            conn.execute("INSERT OR IGNORE INTO channel_settings(channel) VALUES(?)",(channel,))
        trans = {
            "de":{"checkin_title":"Online-Check-in","save":"Speichern","welcome":"Willkommen"},
            "en":{"checkin_title":"Online check-in","save":"Save","welcome":"Welcome"},
            "cs":{"checkin_title":"Online check-in","save":"Uložit","welcome":"Vítejte"},
            "sk":{"checkin_title":"Online check-in","save":"Uložiť","welcome":"Vitajte"},
        }
        for lang, items in trans.items():
            for k,v in items.items():
                conn.execute("INSERT OR IGNORE INTO translations(lang,key,value) VALUES(?,?,?)",(lang,k,v))

    def get_booking_by_token(token):
        with db() as conn:
            return conn.execute("SELECT * FROM bookings WHERE checkin_token=? OR public_token=?",(token,token)).fetchone()

    def ensure_token(booking_id):
        with db() as conn:
            row=conn.execute("SELECT checkin_token FROM bookings WHERE id=?",(booking_id,)).fetchone()
            token=row["checkin_token"] or token_urlsafe(24)
            conn.execute("UPDATE bookings SET checkin_token=? WHERE id=?",(token,booking_id))
            return token

    def maintenance_conflict(room, arrival, departure):
        with db() as conn:
            rows=conn.execute("SELECT * FROM maintenance_blocks WHERE room=?",(room,)).fetchall()
        a=date.fromisoformat(arrival) if isinstance(arrival,str) else arrival
        b=date.fromisoformat(departure) if isinstance(departure,str) else departure
        for r in rows:
            s=date.fromisoformat(r["start_date"]); e=date.fromisoformat(r["end_date"])
            if a<e and s<b:
                return True, r["reason"]
        return False, ""

    app.extensions["v6_maintenance_conflict"]=maintenance_conflict
    app.extensions["v6_ensure_checkin_token"]=ensure_token

    @app.route("/checkin/<token>", methods=["GET","POST"])
    def online_checkin(token):
        b=get_booking_by_token(token)
        if not b:
            return "Buchung nicht gefunden",404
        lang=request.args.get("lang", b["language"] or "de")
        with db() as conn:
            t={r["key"]:r["value"] for r in conn.execute("SELECT key,value FROM translations WHERE lang=?",(lang,))}
        if request.method=="POST":
            with db() as conn:
                conn.execute("""UPDATE bookings SET checked_in=1,language=?,country=?,postal_code=?,city=?,street=?,
                             document_type=?,document_number=?,vehicle_plate=?,arrival_time=? WHERE id=?""",
                             (request.form.get("language","de"),request.form.get("country",""),request.form.get("postal_code",""),
                              request.form.get("city",""),request.form.get("street",""),request.form.get("document_type",""),
                              request.form.get("document_number",""),request.form.get("vehicle_plate",""),
                              request.form.get("arrival_time",""),b["id"]))
                conn.execute("INSERT INTO host_notifications(title,message,created_at) VALUES(?,?,?)",
                             ("Online-Check-in",f"{b['first_name']} {b['last_name']} hat online eingecheckt.",datetime.now().isoformat(timespec="seconds")))
            flash("Online-Check-in gespeichert.","success")
            return redirect(url_for("online_checkin",token=token,lang=lang))
        return render_template("online_checkin.html",booking=b,t=t,lang=lang)

    @app.post("/admin/maintenance/add")
    def maintenance_add():
        if not require_admin(): return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute("INSERT INTO maintenance_blocks(room,start_date,end_date,reason,created_at) VALUES(?,?,?,?,?)",
                         (request.form["room"],request.form["start_date"],request.form["end_date"],
                          request.form.get("reason","Wartung"),datetime.now().isoformat(timespec="seconds")))
        flash("Zimmer wurde gesperrt.","success")
        return redirect(url_for("admin"))

    @app.post("/admin/maintenance/<int:block_id>/delete")
    def maintenance_delete(block_id):
        if not require_admin(): return redirect(url_for("admin_login"))
        with db() as conn: conn.execute("DELETE FROM maintenance_blocks WHERE id=?",(block_id,))
        return redirect(url_for("admin"))

    @app.post("/admin/document/<int:booking_id>")
    def document_upload(booking_id):
        if not require_admin(): return redirect(url_for("admin_login"))
        f=request.files.get("document")
        if not f or not f.filename:
            flash("Keine Datei ausgewählt.","error"); return redirect(url_for("admin"))
        ext=f.filename.rsplit(".",1)[-1].lower() if "." in f.filename else ""
        if ext not in allowed:
            flash("Nicht erlaubtes Dateiformat.","error"); return redirect(url_for("admin"))
        safe=secure_filename(f"{booking_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}")
        f.save(uploads/safe)
        with db() as conn:
            conn.execute("INSERT INTO booking_documents(booking_id,filename,original_name,category,uploaded_at) VALUES(?,?,?,?,?)",
                         (booking_id,safe,f.filename,request.form.get("category","Sonstiges"),datetime.now().isoformat(timespec="seconds")))
        flash("Dokument gespeichert.","success")
        return redirect(url_for("admin"))

    @app.get("/admin/document/<int:doc_id>")
    def document_download(doc_id):
        if not require_admin(): return redirect(url_for("admin_login"))
        with db() as conn: row=conn.execute("SELECT * FROM booking_documents WHERE id=?",(doc_id,)).fetchone()
        if not row: return "Nicht gefunden",404
        return send_file(uploads/row["filename"],as_attachment=True,download_name=row["original_name"])

    @app.post("/admin/channel")
    def channel_save():
        if not require_admin(): return redirect(url_for("admin_login"))
        with db() as conn:
            for ch in ("Booking.com","Airbnb","Expedia","FeWo-direkt","Google Hotels"):
                key=ch.replace(".","_").replace("-","_").replace(" ","_")
                conn.execute("""UPDATE channel_settings SET enabled=?,import_url=?,api_key=?,note=? WHERE channel=?""",
                             (1 if request.form.get(key+"_enabled")=="on" else 0,
                              request.form.get(key+"_import_url",""),request.form.get(key+"_api_key",""),
                              request.form.get(key+"_note",""),ch))
        flash("Channel-Einstellungen gespeichert.","success")
        return redirect(url_for("admin"))

    @app.get("/host")
    def host_mobile():
        if not require_admin(): return redirect(url_for("admin_login"))
        today=date.today().isoformat()
        with db() as conn:
            arrivals=conn.execute("SELECT * FROM bookings WHERE arrival=? AND status!='cancelled'",(today,)).fetchall()
            departures=conn.execute("SELECT * FROM bookings WHERE departure=? AND status!='cancelled'",(today,)).fetchall()
            notes=conn.execute("SELECT * FROM host_notifications ORDER BY created_at DESC LIMIT 20").fetchall()
            rooms=conn.execute("SELECT * FROM housekeeping ORDER BY room").fetchall()
        return render_template("host_mobile.html",arrivals=arrivals,departures=departures,notes=notes,rooms=rooms)

    @app.get("/admin/statistics")
    def statistics():
        if not require_admin(): return redirect(url_for("admin_login"))
        with db() as conn:
            monthly=conn.execute("""SELECT substr(arrival,1,7) month,COUNT(*) bookings,
                                 ROUND(SUM(total),2) revenue FROM bookings
                                 WHERE status!='cancelled' GROUP BY substr(arrival,1,7) ORDER BY month""").fetchall()
            by_room=conn.execute("""SELECT room,COUNT(*) bookings,ROUND(SUM(total),2) revenue,
                                 ROUND(AVG(julianday(departure)-julianday(arrival)),1) avg_nights
                                 FROM bookings WHERE status!='cancelled' GROUP BY room""").fetchall()
            sources=[{"source":"Direkt","bookings":conn.execute("SELECT COUNT(*) c FROM bookings WHERE status!='cancelled'").fetchone()["c"]}]
        return render_template("statistics.html",monthly=monthly,by_room=by_room,sources=sources)

    @app.get("/admin/v6-data")
    def v6_admin_data():
        if not require_admin(): return jsonify(error="unauthorized"),401
        with db() as conn:
            blocks=[dict(r) for r in conn.execute("SELECT * FROM maintenance_blocks ORDER BY start_date")]
            channels=[dict(r) for r in conn.execute("SELECT * FROM channel_settings ORDER BY channel")]
            docs=[dict(r) for r in conn.execute("""SELECT d.*,b.first_name,b.last_name,b.room FROM booking_documents d
                                                JOIN bookings b ON b.id=d.booking_id ORDER BY d.uploaded_at DESC""")]
        return jsonify(blocks=blocks,channels=channels,documents=docs)
