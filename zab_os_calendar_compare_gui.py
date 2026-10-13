"""Standalone read-only Windows UI for comparing two ZAB calendar JSON exports."""
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import date, timedelta
from zab_os_compare_exports import compare_files
from zab_os_snapshot_client import SnapshotError, get_connection_config
from zab_os_export_snapshot import export_snapshot


def format_report(report):
    lines = [
        "ZAB OS – Kalenderabweichungen (nur lesen)",
        "",
        "Nur in Export 1 belegt: " + (", ".join(report["only_in_first"]) or "keine"),
        "Nur in Export 2 belegt: " + (", ".join(report["only_in_second"]) or "keine"),
        "In beiden belegt: " + (", ".join(report["in_both"]) or "keine"),
        "",
        "ACHTUNG: Nicht belegte Tage sind NICHT als frei bestaetigt.",
        "Keine Buchungen, Preise oder Sperren wurden veraendert.",
    ]
    return "\n".join(lines)


def main():
    root = tk.Tk()
    root.title("Zuhause am Bach OS – Kalendervergleich")
    root.geometry("850x550")
    # The standalone tool intentionally does not change booking or pricing data.
    root.minsize(650, 400)
    outer = ttk.Frame(root, padding=16)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="Quellen: 1 = ZAB-Snapshot, 2 = unabhaengiger Kalenderexport").grid(
        row=7, column=0, columnspan=3, sticky="w", pady=4
    )
    paths = [tk.StringVar(), tk.StringVar()]
    for index, caption in enumerate(("Export 1 (JSON)", "Export 2 (JSON)")):
        ttk.Label(outer, text=caption).grid(row=index, column=0, sticky="w", pady=6)
        ttk.Entry(outer, textvariable=paths[index]).grid(row=index, column=1, sticky="ew", padx=8)
        ttk.Button(outer, text="Datei waehlen", command=lambda i=index: paths[i].set(
            filedialog.askopenfilename(title="Kalenderexport auswaehlen", filetypes=[("JSON", "*.json"), ("Alle Dateien", "*.*")])
        )).grid(row=index, column=2)
    today = date.today()
    start = tk.StringVar(value=today.isoformat())
    end = tk.StringVar(value=(today + timedelta(days=31)).isoformat())
    ttk.Label(outer, text="Von (YYYY-MM-DD)").grid(row=2, column=0, sticky="w", pady=6)
    ttk.Entry(outer, textvariable=start).grid(row=2, column=1, sticky="ew", padx=8)
    ttk.Label(outer, text="Bis (exklusiv)").grid(row=3, column=0, sticky="w", pady=6)
    ttk.Entry(outer, textvariable=end).grid(row=3, column=1, sticky="ew", padx=8)
    output = tk.Text(outer, wrap="word", state="disabled")
    output.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    outer.columnconfigure(1, weight=1)
    outer.rowconfigure(5, weight=1)

    def run_compare():
        try:
            report = compare_files(paths[0].get(), paths[1].get(), start.get(), end.get())
            text = format_report(report)
        except (SnapshotError, ValueError, OSError, KeyError, TypeError) as exc:
            messagebox.showerror("Vergleich fehlgeschlagen", str(exc))
            return
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("1.0", text)
        output.configure(state="disabled")

    def export_first():
        server_url, token = get_connection_config()
        if not server_url or not token:
            messagebox.showerror("Verbindung fehlt", "ZAB_OS_SNAPSHOT_URL und ZAB_BRIDGE_TOKEN in Windows-Umgebungsvariablen einrichten.")
            return
        destination = filedialog.asksaveasfilename(
            title="Neuen Snapshot-Export speichern",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not destination:
            return
        try:
            export_snapshot(destination, start.get(), end.get(), base_url=server_url, token=token)
        except (SnapshotError, OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Snapshot-Export fehlgeschlagen", str(exc))
            return
        paths[0].set(destination)
        messagebox.showinfo("Export gespeichert", "Kalenderstand gesichert. Sync-Status NICHT VERIFIZIERT; keine Naechte freigeben.")

    controls = ttk.Frame(outer)
    controls.grid(row=4, column=0, columnspan=3, pady=8)
    ttk.Button(controls, text="ZAB-Snapshot abrufen (nur lesen)", command=export_first).pack(side="left", padx=5)
    ttk.Button(controls, text="Kalender sicher vergleichen", command=run_compare).pack(side="left", padx=5)
    ttk.Label(outer, text="Nur lokaler Vergleich – keine Netzwerkverbindung, keine Freigabe von Naechten.").grid(
        row=6, column=0, columnspan=3, sticky="w", pady=8
    )
    root.mainloop()


if __name__ == "__main__":
    main()
