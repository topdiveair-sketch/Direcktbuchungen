
from __future__ import annotations
import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, date, timedelta
from pathlib import Path

from flask import jsonify, render_template, request, redirect, url_for, flash, session


def init_stability(app, DB_PATH, db, require_admin, ROOMS):
    backup_dir = Path(DB_PATH).parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL DEFAULT 'system',
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS system_settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS legal_pages(
            key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL
        );
        """)
        defaults = {
            "auto_sync_enabled": "1",
            "auto_sync_minutes": "15",
            "backup_keep_days": "30",
            "maintenance_mode": "0",
        }
        for k,v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO system_settings(key,value) VALUES(?,?)",(k,v))

        legal_defaults = {
            "impressum": ("Impressum", "Bitte hier die vollständigen Unternehmens- und Kontaktdaten eintragen."),
            "datenschutz": ("Datenschutzerklärung", "Bitte hier die geprüfte Datenschutzerklärung eintragen."),
            "agb": ("Buchungsbedingungen", "Bitte hier die Buchungs- und Stornobedingungen eintragen."),
            "storno": ("Stornobedingungen", "Kostenlose Stornierung bis 7 Tage vor Anreise. Danach gelten die im Buchungsprozess bestätigten Bedingungen."),
        }
        for k,(title,content) in legal_defaults.items():
            conn.execute("INSERT OR IGNORE INTO legal_pages(key,title,content) VALUES(?,?,?)",(k,title,content))
        legal_live_defaults = {
            "impressum": ("Impressum", """Zuhause am Bach - Wachau

Betreiberin:
Laura Prem
Aggsbach Markt 82
3641 Aggsbach Markt
Österreich

Telefon: +43 664 6437526
E-Mail: Zuhause.am.Bach@outlook.com
Website: https://www.zuhauseambach-wachau.at/

Unternehmensgegenstand:
Beherbergung / Privatzimmervermietung.

Verbraucher können sich bei Fragen oder Beschwerden direkt über die oben genannten Kontaktdaten an uns wenden."""),
            "datenschutz": ("Datenschutzerklärung", """Datenschutzerklärung

Verantwortliche Stelle:
Zuhause am Bach - Wachau
Laura Prem
Aggsbach Markt 82
3641 Aggsbach Markt
Österreich
E-Mail: Zuhause.am.Bach@outlook.com
Telefon: +43 664 6437526

Welche Daten verarbeitet werden
Wir verarbeiten personenbezogene Daten, die im Rahmen einer Anfrage, Buchung, Zahlung, Kontaktaufnahme oder Nutzung des Gästeportals angegeben werden. Dazu können insbesondere Name, Kontaktdaten, Reisedaten, Zahlungsart, Nachrichten, Check-in-Angaben und technisch notwendige Protokolldaten gehören.

Zwecke und Rechtsgrundlagen
Die Verarbeitung erfolgt zur Bearbeitung von Buchungen und Anfragen, zur Durchführung des Aufenthalts, zur Kommunikation mit Gästen, zur Zahlungsabwicklung, zur Rechnungslegung, zur Erfüllung gesetzlicher Pflichten sowie zur Sicherstellung eines stabilen und sicheren Betriebs. Rechtsgrundlagen sind insbesondere Vertragserfüllung bzw. vorvertragliche Maßnahmen, gesetzliche Verpflichtungen und berechtigte Interessen am sicheren Betrieb.

Zahlungsabwicklung
Bei Auswahl von PayPal werden die für die Zahlung erforderlichen Daten im Rahmen des PayPal-Checkouts verarbeitet. PayPal verarbeitet Zahlungsdaten nach den eigenen Datenschutzbestimmungen. Bei Banküberweisung werden auf dieser Website unsere Bankdaten angezeigt; die eigentliche Überweisung erfolgt über das vom Gast verwendete Kreditinstitut.

Technischer Betrieb
Die Website und zugehörige Serverfunktionen werden auf Railway betrieben. Für den E-Mail-Versand wird ein SMTP-Dienst genutzt. Externe Links, etwa zu Google Maps oder zur Gäste-App, werden erst durch aktives Anklicken aufgerufen.

Speicherdauer
Personenbezogene Daten werden nur so lange gespeichert, wie dies für die genannten Zwecke erforderlich ist oder gesetzliche Aufbewahrungspflichten bestehen.

Empfänger
Eine Weitergabe erfolgt nur, soweit sie für Buchungsabwicklung, Zahlung, Kommunikation, IT-Betrieb oder gesetzliche Verpflichtungen erforderlich ist.

Rechte betroffener Personen
Betroffene Personen haben nach Maßgabe der DSGVO insbesondere Rechte auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung, Datenübertragbarkeit und Widerspruch. Beschwerden können an die zuständige Datenschutzbehörde gerichtet werden.

Kontakt für Datenschutzanfragen:
Zuhause.am.Bach@outlook.com"""),
            "agb": ("Buchungsbedingungen", """Buchungsbedingungen

1. Buchungsweg
Die auf der Website angezeigte Verfügbarkeit wird unmittelbar vor Abschluss erneut geprüft.

Bei erfolgreicher PayPal-Zahlung wird die Buchung nach serverseitiger Zahlungsbestätigung als bestätigt markiert und der Zeitraum verbindlich reserviert.

Bei Auswahl von Banküberweisung oder Zahlung vor Ort wird der Zeitraum zunächst vorgemerkt. Die persönliche Buchungsbestätigung folgt anschließend.

2. Preise
Alle auf der Website dargestellten Preise verstehen sich in Euro. Der im Buchungsprozess ausgewiesene Gesamtpreis berücksichtigt die ausgewählten Zusatzleistungen und gegebenenfalls gültige Rabatte. Gesetzliche Abgaben oder Ortstaxen können zusätzlich anfallen, sofern sie nicht ausdrücklich als enthalten ausgewiesen sind.

3. Zahlung
PayPal-Zahlungen werden über den sicheren PayPal-Checkout abgewickelt. Bei Banküberweisung werden Kontoinhaber, IBAN, Betrag und Verwendungszweck im Buchungsprozess bzw. in der Bestätigung angezeigt. Bei Zahlung vor Ort ist der Betrag bei Anreise fällig, sofern nichts anderes vereinbart wurde.

4. Check-in und Check-out
Check-in ist grundsätzlich ab 14:00 Uhr möglich, Check-out bis 10:00 Uhr. Abweichungen bedürfen einer vorherigen Vereinbarung.

5. Nutzung der Unterkunft
Gäste verpflichten sich zu einem sorgfältigen Umgang mit Unterkunft, Inventar und Hausumgebung. Schäden sind unverzüglich zu melden. Zusätzliche Gäste, Veranstaltungen, Rauchen oder Haustiere bedürfen einer ausdrücklichen Vereinbarung, soweit sie nicht bereits Bestandteil der bestätigten Buchung sind.

6. Stornierung
Es gelten die auf der Website veröffentlichten Stornobedingungen sowie gegebenenfalls abweichende Bedingungen in der individuellen Buchungsbestätigung.

7. Anwendbares Recht
Es gilt österreichisches Recht, soweit keine zwingenden verbraucherschützenden Vorschriften entgegenstehen."""),
            "storno": ("Stornobedingungen", """Stornobedingungen

Eine Stornierung ist bis 7 Tage vor Anreise kostenlos möglich, sofern in der individuellen Buchungsbestätigung nichts Abweichendes vereinbart wurde.

Bei späterer Stornierung, Nichtanreise oder vorzeitiger Abreise können Stornokosten anfallen. Die konkrete Höhe richtet sich nach den bestätigten Buchungsbedingungen, dem Zeitpunkt der Stornierung, der Aufenthaltsdauer und einer möglichen Weitervermietung.

Stornierungen sollen über den persönlichen Stornierungslink aus der Buchungsbestätigung oder schriftlich per E-Mail an Zuhause.am.Bach@outlook.com erfolgen. Maßgeblich ist der Zeitpunkt des Eingangs.

Bei außergewöhnlichen Umständen kann Zuhause am Bach - Wachau im Einzelfall eine kulante Lösung anbieten; ein Anspruch darauf besteht nicht."""),
        }
        for k,(title,content) in legal_live_defaults.items():
            conn.execute(
                "INSERT INTO legal_pages(key,title,content) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET title=excluded.title,content=excluded.content",
                (k,title,content),
            )
        legal_envs = {
            "impressum": os.environ.get("LEGAL_IMPRESSUM_TEXT", "").strip(),
            "datenschutz": os.environ.get("LEGAL_DATENSCHUTZ_TEXT", "").strip(),
            "agb": os.environ.get("LEGAL_AGB_TEXT", "").strip(),
            "storno": os.environ.get("LEGAL_STORNO_TEXT", "").strip(),
        }
        for key, content in legal_envs.items():
            if content:
                conn.execute("UPDATE legal_pages SET content=? WHERE key=?", (content, key))

    def audit(action, details="", user="system"):
        with db() as conn:
            conn.execute("INSERT INTO audit_log(user,action,details,created_at) VALUES(?,?,?,?)",
                         (user,action,details,datetime.now().isoformat(timespec="seconds")))

    def get_system_settings():
        with db() as conn:
            return {r["key"]:r["value"] for r in conn.execute("SELECT key,value FROM system_settings")}

    def rotate_backups():
        settings = get_system_settings()
        keep_days = int(settings.get("backup_keep_days","30") or 30)
        cutoff = datetime.now() - timedelta(days=keep_days)
        removed = 0
        for file in backup_dir.glob("*.db"):
            if datetime.fromtimestamp(file.stat().st_mtime) < cutoff:
                file.unlink()
                removed += 1
        return removed

    def create_backup(label="auto"):
        if not Path(DB_PATH).exists():
            return None
        target = backup_dir / f"zab-{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        shutil.copy2(DB_PATH,target)
        rotate_backups()
        return target

    def run_auto_sync_once():
        results=[]
        sync_func = app.extensions.get("zab_sync_room")
        if not sync_func:
            return results
        for room in ROOMS:
            try:
                count,msg = sync_func(room)
                results.append((room,count,msg))
            except Exception as exc:
                results.append((room,0,f"Fehler: {exc}"))
        audit("ical_auto_sync", json.dumps(results, ensure_ascii=False))
        return results

    def scheduler_loop():
        while True:
            try:
                settings=get_system_settings()
                if settings.get("auto_sync_enabled","1")=="1":
                    run_auto_sync_once()
                    create_backup("auto")
                minutes=max(5,int(settings.get("auto_sync_minutes","15") or 15))
            except Exception as exc:
                audit("scheduler_error",str(exc))
                minutes=15
            time.sleep(minutes*60)

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        thread=threading.Thread(target=scheduler_loop,daemon=True,name="zab-auto-sync")
        thread.start()

    app.extensions["zab_audit"]=audit
    app.extensions["zab_create_backup"]=create_backup
    app.extensions["zab_rotate_backups"]=rotate_backups

    @app.get("/health")
    def health():
        checks={"database":False,"templates":False,"static":False}
        try:
            with db() as conn:
                conn.execute("SELECT 1").fetchone()
            checks["database"]=True
        except Exception:
            pass
        checks["templates"]=(Path(app.template_folder)/"index.html").exists()
        checks["static"]=(Path(app.static_folder)/"css"/"style.css").exists()
        ok=all(checks.values())
        return jsonify(status="ok" if ok else "degraded",checks=checks,time=datetime.now().isoformat()), (200 if ok else 503)

    @app.get("/system-test")
    def system_test():
        if not require_admin():
            return redirect(url_for("admin_login"))
        tests=[]
        try:
            with db() as conn:
                conn.execute("SELECT 1").fetchone()
            tests.append(("Datenbank","OK"))
        except Exception as exc:
            tests.append(("Datenbank",f"Fehler: {exc}"))

        for name,path in [
            ("Startseite",Path(app.template_folder)/"index.html"),
            ("CSS",Path(app.static_folder)/"css"/"style.css"),
            ("JavaScript",Path(app.static_folder)/"js"/"app.js"),
        ]:
            tests.append((name,"OK" if path.exists() else "Fehlt"))

        with db() as conn:
            rooms=len(list(conn.execute("SELECT room FROM room_prices")))
            bookings=conn.execute("SELECT COUNT(*) c FROM bookings").fetchone()["c"]
            blocks=conn.execute("SELECT COUNT(*) c FROM external_blocks").fetchone()["c"]
        return render_template("system_test.html",tests=tests,rooms=rooms,bookings=bookings,blocks=blocks)

    @app.route("/admin/legal",methods=["GET","POST"])
    def legal_admin():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method=="POST":
            with db() as conn:
                for key in ("impressum","datenschutz","agb","storno"):
                    conn.execute("UPDATE legal_pages SET content=? WHERE key=?",
                                 (request.form.get(key,""),key))
            audit("legal_update","Rechtstexte aktualisiert","admin")
            flash("Rechtstexte gespeichert.","success")
            return redirect(url_for("legal_admin"))
        with db() as conn:
            pages={r["key"]:dict(r) for r in conn.execute("SELECT * FROM legal_pages")}
        return render_template("legal_admin.html",pages=pages)

    @app.get("/legal/<key>")
    def legal_page(key):
        with db() as conn:
            page=conn.execute("SELECT * FROM legal_pages WHERE key=?",(key,)).fetchone()
        if not page:
            return "Nicht gefunden",404
        return render_template("legal_page.html",page=page)

    @app.post("/admin/system-settings")
    def system_settings_save():
        if not require_admin():
            return redirect(url_for("admin_login"))
        vals={
            "auto_sync_enabled":"1" if request.form.get("auto_sync_enabled")=="on" else "0",
            "auto_sync_minutes":str(max(5,int(request.form.get("auto_sync_minutes","15") or 15))),
            "backup_keep_days":str(max(1,int(request.form.get("backup_keep_days","30") or 30))),
            "maintenance_mode":"1" if request.form.get("maintenance_mode")=="on" else "0",
        }
        with db() as conn:
            for k,v in vals.items():
                conn.execute("""INSERT INTO system_settings(key,value) VALUES(?,?)
                             ON CONFLICT(key) DO UPDATE SET value=excluded.value""",(k,v))
        audit("system_settings",json.dumps(vals),"admin")
        flash("Systemeinstellungen gespeichert.","success")
        return redirect(url_for("admin"))

    @app.get("/admin/audit")
    def audit_view():
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            rows=conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 500").fetchall()
        return render_template("audit.html",rows=rows)

    @app.post("/admin/backup-now")
    def backup_now():
        if not require_admin():
            return redirect(url_for("admin_login"))
        target=create_backup("manual")
        audit("backup_manual",str(target),"admin")
        flash("Backup erstellt.","success")
        return redirect(url_for("admin"))

    @app.get("/admin/stability-data")
    def stability_data():
        if not require_admin():
            return jsonify(error="unauthorized"),401
        return jsonify(settings=get_system_settings())
