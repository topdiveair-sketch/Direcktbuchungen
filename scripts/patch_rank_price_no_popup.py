from pathlib import Path

path = Path("windows_rank_price/app.py")
text = path.read_text(encoding="utf-8")
old = '        messagebox.showerror(APP_NAME, message)\n'
new = (
    '        clean = " ".join(str(message or "Unbekannter Fehler").split())\n'
    '        self.status_var.set(f"Fehler: {clean}")\n'
    '        self.rank_note.set(clean)\n'
)
if old not in text:
    raise SystemExit("modal fetch error popup line not found")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

updated = path.read_text(encoding="utf-8")
if 'messagebox.showerror(APP_NAME, message)' in updated:
    raise SystemExit("modal fetch error popup still present")
if 'self.status_var.set(f"Fehler: {clean}")' not in updated:
    raise SystemExit("non-modal error status not installed")
print("no-popup patch verified")
