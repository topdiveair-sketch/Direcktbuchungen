from pathlib import Path
import py_compile, zipfile, sys

base=Path(__file__).resolve().parent
checks=[]
for name in ["app.py","addons.py","v6_features.py","stability.py","zab_os.py","alltag.py","host_assistant.py","smart_host.py","knowledge.py","quality_v12.py"]:
    path=base/name
    try:
        py_compile.compile(str(path),doraise=True)
        checks.append((name,"OK"))
    except Exception as exc:
        checks.append((name,f"FEHLER: {exc}"))

for path in [
    base/"templates"/"index.html",
    base/"templates"/"admin.html",
    base/"static"/"css"/"style.css",
    base/"static"/"js"/"app.js",
    base/"static"/"images"/"aggsbach-markt-luftbild.png",
]:
    checks.append((str(path.relative_to(base)),"OK" if path.exists() else "FEHLT"))

for name,status in checks:
    print(f"{name}: {status}")

if any(status!="OK" for _,status in checks):
    sys.exit(1)
print("SYSTEMDATEIEN: OK")
