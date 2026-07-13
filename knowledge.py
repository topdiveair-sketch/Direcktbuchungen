
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path

from flask import (
    Response, flash, jsonify, redirect, render_template,
    request, send_file, url_for
)
from werkzeug.utils import secure_filename


def init_knowledge(app, DB_PATH, db, require_admin, ROOMS):
    media_dir = Path(DB_PATH).parent / "media_library"
    template_dir = Path(DB_PATH).parent / "document_templates"
    media_dir.mkdir(parents=True, exist_ok=True)
    template_dir.mkdir(parents=True, exist_ok=True)

    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS master_data(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL DEFAULT '',
            unit TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 100,
            note TEXT NOT NULL DEFAULT '',
            UNIQUE(category,key)
        );

        CREATE TABLE IF NOT EXISTS knowledge_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assistant TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL DEFAULT '',
            opening_hours TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS media_library(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            rights_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS document_templates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS faq_knowledge(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Allgemein',
            assistant TEXT NOT NULL DEFAULT 'Gloria',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        """)

        # Stammdaten
        defaults = [
            ("Unterkunft", "Check-in ab", "15:00", "Uhr", "Standard-Check-in"),
            ("Unterkunft", "Check-out bis", "10:00", "Uhr", "Standard-Check-out"),
            ("Unterkunft", "WLAN", "In Gäste-App und Zimmer", "", ""),
            ("Unterkunft", "Parkplatz", "Im Hof", "", ""),
            ("Unterkunft", "Fahrradunterstand", "Innenbereich", "", ""),
            ("Unterkunft", "E-Bike laden", "Ja", "", ""),
            ("Preise", "Frühstück", "12.00", "EUR/Person/Nacht", ""),
            ("Preise", "Wachauer Jause", "29.90", "EUR/2 Personen", ""),
            ("Preise", "Gepäcktransport", "25.00", "EUR/Fahrt", "Richtwert"),
            ("Hausregeln", "Rauchen", "Nicht im Zimmer", "", ""),
            ("Hausregeln", "Ruhezeit", "22:00 bis 07:00", "", ""),
            ("Hausregeln", "Haustiere", "Nach Absprache", "", ""),
        ]
        for category, key, value, unit, note in defaults:
            conn.execute("""
                INSERT OR IGNORE INTO master_data(category,key,value,unit,note)
                VALUES(?,?,?,?,?)
            """, (category, key, value, unit, note))

        # Wissenseinträge
        if conn.execute("SELECT COUNT(*) c FROM knowledge_entries").fetchone()["c"] == 0:
            now = datetime.now().isoformat(timespec="seconds")
            entries = [
                ("Fidel","Wandern","Welterbesteig Wachau","Etappen und Orientierung",
                 "Informationen zu Etappen, Wegbeschaffenheit, Gehzeiten und Rückfahrtmöglichkeiten.",
                 "Wachau","","","","Welterbesteig,Wandern"),
                ("Fidel","Radfahren","Donauradweg","Radfahren entlang der Donau",
                 "Hinweise zu Radweg, Abstellmöglichkeit, E-Bike-Laden, Werkzeug und Gepäcktransport.",
                 "Wachau","","","","Donauradweg,Rad"),
                ("Fidel","Ausflug","Burgruine Aggstein","Ausflug zur Burgruine",
                 "Beliebtes Ausflugsziel oberhalb der Donau. Anreise und Öffnungszeiten später ergänzen.",
                 "Aggstein","","","","Burg,Ausflug"),
                ("Gloria","Unterkunft","Frühstück","Frühstück bei Zuhause am Bach",
                 "Ausgiebiges regionales Frühstück, vegetarisch oder vegan möglich.",
                 "Zuhause am Bach","","","","Frühstück"),
                ("Gloria","Unterkunft","Anreise","Anreise und Check-in",
                 "Check-in standardmäßig ab 15:00 Uhr. Spätere Anreise bitte vorab melden.",
                 "Aggsbach Markt","","","","Check-in"),
                ("Pia","Kinder","Windis-Rätsel","Rätsel für junge Gäste",
                 "Kleine Rätsel und Aufgaben rund um die Wachau und die Wilden Wachauer Windis.",
                 "Zuhause am Bach","","","","Kinder,Rätsel"),
                ("Pia","Kinder","Wachau-Schatzsuche","Schatzsuche vorbereiten",
                 "Eine einfache Schatzsuche rund um Haus, Bach und Umgebung.",
                 "Aggsbach Markt","","","","Kinder,Schatzsuche"),
            ]
            for assistant, category, title, summary, content, location, phone, link, hours, tags in entries:
                conn.execute("""
                    INSERT INTO knowledge_entries
                    (assistant,category,title,summary,content,location,phone,link,opening_hours,tags,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """, (assistant,category,title,summary,content,location,phone,link,hours,tags,now,now))

        # Dokumentvorlagen
        now = datetime.now().isoformat(timespec="seconds")
        templates = [
            ("booking_confirmation","Buchungsbestätigung","Ihre Buchung bei Zuhause am Bach",
             "Hallo {{first_name}},\n\nvielen Dank für Ihre Buchung.\nZimmer: {{room}}\nAnreise: {{arrival}}\nAbreise: {{departure}}\nGesamt: {{total}} EUR\n\nHerzliche Grüße\nZuhause am Bach"),
            ("arrival_info","Anreiseinformation","Informationen zu Ihrer Anreise",
             "Hallo {{first_name}},\n\nCheck-in ist ab {{checkin_time}} möglich.\nAdresse: {{address}}\nBitte teilen Sie uns Ihre ungefähre Ankunftszeit mit.\n\nZuhause am Bach"),
            ("cancellation","Stornobestätigung","Ihre Stornierung",
             "Hallo {{first_name}},\n\nIhre Buchung für {{room}} wurde storniert.\n\nZuhause am Bach"),
            ("review_request","Bewertungsanfrage","Danke für Ihren Aufenthalt",
             "Hallo {{first_name}},\n\nvielen Dank für Ihren Aufenthalt. Wir freuen uns über eine Google-Bewertung.\n\nZuhause am Bach"),
            ("offer","Angebot","Ihr Angebot von Zuhause am Bach",
             "Hallo {{first_name}},\n\nwir bieten Ihnen folgenden Aufenthalt an:\n{{offer_details}}\n\nGesamtpreis: {{total}} EUR"),
        ]
        for key, title, subject, body in templates:
            conn.execute("""
                INSERT OR IGNORE INTO document_templates(template_key,title,subject,body,updated_at)
                VALUES(?,?,?,?,?)
            """, (key,title,subject,body,now))

        # FAQ
        if conn.execute("SELECT COUNT(*) c FROM faq_knowledge").fetchone()["c"] == 0:
            faq = [
                ("Wann ist Check-in?","Check-in ist standardmäßig ab 15:00 Uhr möglich.","Anreise","Gloria"),
                ("Gibt es Frühstück?","Ja, Frühstück ist optional und kostet 12 Euro pro Person und Nacht.","Frühstück","Gloria"),
                ("Kann ich mein E-Bike laden?","Ja, E-Bikes können sicher abgestellt und geladen werden.","Radfahren","Fidel"),
                ("Wo kann ich wandern?","Der Welterbesteig Wachau bietet zahlreiche Etappen in der Region.","Wandern","Fidel"),
                ("Gibt es etwas für Kinder?","Pia bietet Rätsel, Geschichten und eine vorbereitete Schatzsuche.","Kinder","Pia"),
            ]
            for question, answer, category, assistant in faq:
                conn.execute("""
                    INSERT INTO faq_knowledge(question,answer,category,assistant,created_at)
                    VALUES(?,?,?,?,?)
                """, (question,answer,category,assistant,now))

    def list_categories():
        with db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM master_data ORDER BY category"
            ).fetchall()
        return [r["category"] for r in rows]

    @app.get("/wissen")
    def knowledge_dashboard():
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            counts = {
                "master": conn.execute("SELECT COUNT(*) c FROM master_data").fetchone()["c"],
                "knowledge": conn.execute("SELECT COUNT(*) c FROM knowledge_entries").fetchone()["c"],
                "media": conn.execute("SELECT COUNT(*) c FROM media_library").fetchone()["c"],
                "templates": conn.execute("SELECT COUNT(*) c FROM document_templates").fetchone()["c"],
                "faq": conn.execute("SELECT COUNT(*) c FROM faq_knowledge").fetchone()["c"],
            }
            recent = conn.execute("""
                SELECT * FROM knowledge_entries ORDER BY updated_at DESC LIMIT 8
            """).fetchall()
        return render_template("knowledge_dashboard.html", counts=counts, recent=recent)

    @app.route("/wissen/stammdaten", methods=["GET","POST"])
    def master_data():
        if not require_admin():
            return redirect(url_for("admin_login"))

        if request.method == "POST":
            category = request.form["category"].strip()
            key = request.form["key"].strip()
            with db() as conn:
                conn.execute("""
                    INSERT INTO master_data(category,key,value,unit,active,sort_order,note)
                    VALUES(?,?,?,?,1,?,?)
                    ON CONFLICT(category,key) DO UPDATE SET
                        value=excluded.value,
                        unit=excluded.unit,
                        active=excluded.active,
                        sort_order=excluded.sort_order,
                        note=excluded.note
                """, (
                    category,
                    key,
                    request.form.get("value","").strip(),
                    request.form.get("unit","").strip(),
                    int(request.form.get("sort_order","100") or 100),
                    request.form.get("note","").strip(),
                ))
            flash("Stammdatum gespeichert.", "success")
            return redirect(url_for("master_data"))

        category = request.args.get("category","")
        with db() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM master_data WHERE category=? ORDER BY sort_order,key",
                    (category,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM master_data ORDER BY category,sort_order,key"
                ).fetchall()
        return render_template(
            "master_data.html",
            rows=rows,
            categories=list_categories(),
            selected_category=category,
        )

    @app.post("/wissen/stammdaten/<int:item_id>/update")
    def master_data_update(item_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute("""
                UPDATE master_data
                SET value=?,unit=?,active=?,sort_order=?,note=?
                WHERE id=?
            """, (
                request.form.get("value",""),
                request.form.get("unit",""),
                1 if request.form.get("active")=="on" else 0,
                int(request.form.get("sort_order","100") or 100),
                request.form.get("note",""),
                item_id,
            ))
        return redirect(url_for("master_data"))

    @app.route("/wissen/eintraege", methods=["GET","POST"])
    def knowledge_entries():
        if not require_admin():
            return redirect(url_for("admin_login"))

        if request.method == "POST":
            now = datetime.now().isoformat(timespec="seconds")
            with db() as conn:
                conn.execute("""
                    INSERT INTO knowledge_entries
                    (assistant,category,title,summary,content,location,phone,link,opening_hours,tags,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    request.form["assistant"],
                    request.form["category"].strip(),
                    request.form["title"].strip(),
                    request.form.get("summary","").strip(),
                    request.form["content"].strip(),
                    request.form.get("location","").strip(),
                    request.form.get("phone","").strip(),
                    request.form.get("link","").strip(),
                    request.form.get("opening_hours","").strip(),
                    request.form.get("tags","").strip(),
                    now, now,
                ))
            flash("Wissenseintrag gespeichert.", "success")
            return redirect(url_for("knowledge_entries"))

        assistant = request.args.get("assistant","")
        query = request.args.get("q","").strip()
        sql = "SELECT * FROM knowledge_entries WHERE 1=1"
        params = []
        if assistant:
            sql += " AND assistant=?"
            params.append(assistant)
        if query:
            sql += " AND (title LIKE ? OR summary LIKE ? OR content LIKE ? OR tags LIKE ?)"
            params.extend(["%"+query+"%"]*4)
        sql += " ORDER BY assistant,category,sort_order,title"
        with db() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return render_template(
            "knowledge_entries.html",
            rows=rows,
            assistant=assistant,
            query=query,
        )

    @app.route("/wissen/eintrag/<int:item_id>", methods=["GET","POST"])
    def knowledge_entry_edit(item_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            row = conn.execute("SELECT * FROM knowledge_entries WHERE id=?", (item_id,)).fetchone()
        if not row:
            return "Nicht gefunden", 404

        if request.method == "POST":
            with db() as conn:
                conn.execute("""
                    UPDATE knowledge_entries SET
                        assistant=?,category=?,title=?,summary=?,content=?,location=?,
                        phone=?,link=?,opening_hours=?,tags=?,active=?,sort_order=?,updated_at=?
                    WHERE id=?
                """, (
                    request.form["assistant"],
                    request.form["category"],
                    request.form["title"],
                    request.form.get("summary",""),
                    request.form["content"],
                    request.form.get("location",""),
                    request.form.get("phone",""),
                    request.form.get("link",""),
                    request.form.get("opening_hours",""),
                    request.form.get("tags",""),
                    1 if request.form.get("active")=="on" else 0,
                    int(request.form.get("sort_order","100") or 100),
                    datetime.now().isoformat(timespec="seconds"),
                    item_id,
                ))
            flash("Wissenseintrag aktualisiert.", "success")
            return redirect(url_for("knowledge_entry_edit", item_id=item_id))

        return render_template("knowledge_entry_edit.html", row=row)

    @app.route("/wissen/faq", methods=["GET","POST"])
    def faq_manager():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            with db() as conn:
                conn.execute("""
                    INSERT INTO faq_knowledge(question,answer,category,assistant,created_at)
                    VALUES(?,?,?,?,?)
                """, (
                    request.form["question"].strip(),
                    request.form["answer"].strip(),
                    request.form.get("category","Allgemein"),
                    request.form.get("assistant","Gloria"),
                    datetime.now().isoformat(timespec="seconds"),
                ))
            return redirect(url_for("faq_manager"))
        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM faq_knowledge ORDER BY assistant,category,question"
            ).fetchall()
        return render_template("faq_manager.html", rows=rows)

    @app.route("/wissen/vorlagen", methods=["GET","POST"])
    def template_manager():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            with db() as conn:
                conn.execute("""
                    INSERT INTO document_templates(template_key,title,subject,body,active,updated_at)
                    VALUES(?,?,?,?,1,?)
                    ON CONFLICT(template_key) DO UPDATE SET
                        title=excluded.title,
                        subject=excluded.subject,
                        body=excluded.body,
                        active=excluded.active,
                        updated_at=excluded.updated_at
                """, (
                    request.form["template_key"].strip(),
                    request.form["title"].strip(),
                    request.form.get("subject","").strip(),
                    request.form["body"],
                    datetime.now().isoformat(timespec="seconds"),
                ))
            flash("Vorlage gespeichert.", "success")
            return redirect(url_for("template_manager"))

        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM document_templates ORDER BY title"
            ).fetchall()
        return render_template("template_manager.html", rows=rows)

    @app.route("/wissen/medien", methods=["GET","POST"])
    def media_manager():
        if not require_admin():
            return redirect(url_for("admin_login"))
        allowed = {"jpg","jpeg","png","webp","pdf","mp4"}

        if request.method == "POST":
            upload = request.files.get("file")
            if not upload or not upload.filename:
                flash("Bitte Datei auswählen.", "error")
                return redirect(url_for("media_manager"))
            ext = upload.filename.rsplit(".",1)[-1].lower() if "." in upload.filename else ""
            if ext not in allowed:
                flash("Dateityp nicht erlaubt.", "error")
                return redirect(url_for("media_manager"))

            filename = secure_filename(
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{upload.filename}"
            )
            upload.save(media_dir / filename)

            with db() as conn:
                conn.execute("""
                    INSERT INTO media_library
                    (title,category,filename,original_name,description,rights_note,created_at)
                    VALUES(?,?,?,?,?,?,?)
                """, (
                    request.form["title"].strip(),
                    request.form.get("category","Allgemein"),
                    filename,
                    upload.filename,
                    request.form.get("description",""),
                    request.form.get("rights_note",""),
                    datetime.now().isoformat(timespec="seconds"),
                ))
            flash("Medium gespeichert.", "success")
            return redirect(url_for("media_manager"))

        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM media_library ORDER BY created_at DESC"
            ).fetchall()
        return render_template("media_manager.html", rows=rows)

    @app.get("/wissen/medium/<int:item_id>")
    def media_download(item_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            row = conn.execute("SELECT * FROM media_library WHERE id=?", (item_id,)).fetchone()
        if not row:
            return "Nicht gefunden", 404
        return send_file(media_dir / row["filename"], as_attachment=True, download_name=row["original_name"])

    @app.get("/wissen/export.csv")
    def knowledge_export():
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            rows = conn.execute("""
                SELECT assistant,category,title,summary,content,location,phone,link,opening_hours,tags,active
                FROM knowledge_entries ORDER BY assistant,category,title
            """).fetchall()

        out = io.StringIO()
        writer = csv.writer(out, delimiter=";")
        writer.writerow([
            "Assistent","Kategorie","Titel","Kurztext","Inhalt","Ort",
            "Telefon","Link","Öffnungszeiten","Tags","Aktiv"
        ])
        for row in rows:
            writer.writerow(list(row))
        return Response(
            "\ufeff"+out.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition":"attachment; filename=wissensdatenbank.csv"}
        )

    @app.get("/api/knowledge/search")
    def knowledge_search_api():
        query = request.args.get("q","").strip()
        assistant = request.args.get("assistant","").strip()
        sql = "SELECT id,assistant,category,title,summary,content,location,phone,link,opening_hours,tags FROM knowledge_entries WHERE active=1"
        params = []
        if assistant:
            sql += " AND assistant=?"
            params.append(assistant)
        if query:
            sql += " AND (title LIKE ? OR summary LIKE ? OR content LIKE ? OR tags LIKE ?)"
            params.extend(["%"+query+"%"]*4)
        sql += " ORDER BY sort_order,title LIMIT 50"
        with db() as conn:
            rows = [dict(r) for r in conn.execute(sql, tuple(params))]
        return jsonify(rows)

    @app.get("/api/master-data")
    def master_data_api():
        category = request.args.get("category","")
        with db() as conn:
            if category:
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM master_data WHERE active=1 AND category=? ORDER BY sort_order,key",
                    (category,)
                )]
            else:
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM master_data WHERE active=1 ORDER BY category,sort_order,key"
                )]
        return jsonify(rows)
