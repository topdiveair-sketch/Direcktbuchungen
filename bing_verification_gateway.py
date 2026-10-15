"""Production entrypoint: preserve existing gateway and serve Bing ownership XML."""
from pathlib import Path
from flask import Response
from wachauetappe_gateway import app


@app.get('/BingSiteAuth.xml', strict_slashes=False)
@app.get('/BingSiteAuth.xml/', strict_slashes=False)
def bing_site_auth_xml():
    content = (Path(__file__).resolve().parent / 'BingSiteAuth.xml').read_bytes()
    return Response(content, mimetype='application/xml')
