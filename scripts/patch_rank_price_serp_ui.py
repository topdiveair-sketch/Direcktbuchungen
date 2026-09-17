from pathlib import Path

p = Path("windows_rank_price/app.py")
s = p.read_text(encoding="utf-8")

old = '''        rank = data.get("rank") or {}
        if rank.get("rank") is not None:
            self.rank_value.set(f"#{rank['rank']}")
        elif rank.get("status") == "not_configured":
            self.rank_value.set("API fehlt")
        else:
            self.rank_value.set(">100 / n. g.")
        self.rank_note.set(f"{rank.get('message','')}  Quelle: {rank.get('source','')}")

        for item in self.rank_tree.get_children():
            self.rank_tree.delete(item)
        for row in data.get("competitor_rankings") or []:
            r = row.get("rank")
            if r is not None:
                rank_text = f"#{r}"
                status = "gefunden"
            elif row.get("status") == "not_configured":
                rank_text = "–"
                status = "SERP-API fehlt"
            elif row.get("status") == "error":
                rank_text = "–"
                status = "Abfragefehler"
            else:
                rank_text = ">100 / n. g."
                status = "nicht gefunden"
            self.rank_tree.insert("", "end", values=(rank_text, row.get("name", ""), status, row.get("title", "")))
'''

new = '''        rank = data.get("rank") or {}
        provider_error = str(data.get("provider_error") or "").strip()
        if provider_error:
            self.rank_value.set("–")
            self.rank_note.set(provider_error)
        elif rank.get("rank") is not None:
            self.rank_value.set(f"#{rank['rank']}")
            self.rank_note.set(f"{rank.get('message','')}  Quelle: {rank.get('source','')}")
        elif rank.get("status") == "not_configured":
            self.rank_value.set("API fehlt")
            self.rank_note.set(rank.get("message") or "SERP-API ist nicht konfiguriert.")
        else:
            self.rank_value.set(">100 / n. g.")
            self.rank_note.set(f"{rank.get('message','')}  Quelle: {rank.get('source','')}")

        for item in self.rank_tree.get_children():
            self.rank_tree.delete(item)
        if provider_error:
            self.rank_tree.insert("", "end", values=("–", "Google-Rangliste", "derzeit nicht verfügbar", provider_error))
        else:
            for row in data.get("competitor_rankings") or []:
                r = row.get("rank")
                if r is not None:
                    rank_text = f"#{r}"
                    status = "gefunden"
                elif row.get("status") == "not_configured":
                    rank_text = "–"
                    status = "SERP-API fehlt"
                elif row.get("status") in {"error", "unavailable"}:
                    rank_text = "–"
                    status = "derzeit nicht verfügbar"
                else:
                    rank_text = ">100 / n. g."
                    status = "nicht gefunden"
                self.rank_tree.insert("", "end", values=(rank_text, row.get("name", ""), status, row.get("title", "")))
'''

if old not in s:
    if "provider_error = str(data.get(\"provider_error\") or \"\").strip()" in s:
        print("UI patch already applied")
    else:
        raise SystemExit("target result block not found")
else:
    s = s.replace(old, new, 1)

old_status = '''        self.status_var.set(f"Abruf abgeschlossen: {len(data.get('competitor_rankings') or [])} Mitbewerber geprüft.")'''
new_status = '''        if provider_error:
            self.status_var.set("Direktpreis geladen. Google-Rangliste derzeit nicht verfügbar.")
        else:
            self.status_var.set(f"Abruf abgeschlossen: {len(data.get('competitor_rankings') or [])} Mitbewerber geprüft.")'''

if old_status in s:
    s = s.replace(old_status, new_status, 1)
elif "Direktpreis geladen. Google-Rangliste derzeit nicht verfügbar." not in s:
    raise SystemExit("target status block not found")

p.write_text(s, encoding="utf-8")
print("Windows SERP UI patch applied")
