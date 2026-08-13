from pathlib import Path
import sys

path = Path(sys.argv[1] if len(sys.argv) > 1 else "index.html")
text = path.read_text(encoding="utf-8")

backup = path.with_suffix(path.suffix + ".bak")
backup.write_text(text, encoding="utf-8")

if 'href="windis.html"' not in text:
    nav_marker = '<div class="nav-links">'
    if nav_marker in text:
        text = text.replace(nav_marker, nav_marker + '\n        <a href="windis.html">🐾 Die Windis</a>', 1)

section = """
<section id="windis-markenzentrum" style="border:1px solid #d8e2dd;border-radius:18px;background:#fff4d8;padding:26px;">
  <div class="section-head">
    <span class="eyebrow" style="color:#176b5a;">🐾 Die Wilden Wachauer Windis</span>
    <h2>Hier wohnen Fidel, Gloria und Pia.</h2>
    <p>Die Geschichten der Wilden Wachauer Windis haben ein echtes Zuhause: in Aggsbach Markt. Entdecke die drei Figuren, ihre Wachau-Abenteuer, die Windi-Chronik und die Orte hinter den Geschichten.</p>
  </div>
  <p><a class="btn" href="windis.html">Die Welt der Windis entdecken</a></p>
</section>
"""
if 'id="windis-markenzentrum"' not in text:
    marker = '<section class="guest-app'
    pos = text.find(marker)
    if pos != -1:
        text = text[:pos] + section + '\n' + text[pos:]
    elif '</main>' in text:
        text = text.replace('</main>', section + '\n</main>', 1)

if 'rel="author" href="windis.html"' not in text and '</head>' in text:
    text = text.replace('</head>', '  <link rel="author" href="windis.html" title="Die Wilden Wachauer Windis">\n</head>', 1)

path.write_text(text, encoding="utf-8")
print(f"Windis-Patch angewendet: {path}")
print(f"Sicherung: {backup}")
