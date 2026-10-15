"""Serve Bing ownership proof before legacy canonical-path redirects."""
from pathlib import Path
from flask import Response, request
from wachauetappe_gateway import app


def _bing_xml_response():
    content = (Path(__file__).resolve().parent / "BingSiteAuth.xml").read_bytes()
    return Response(content, mimetype="application/xml")


@app.get("/BingSiteAuth.xml", strict_slashes=False)
@app.get("/BingSiteAuth.xml/", strict_slashes=False)
def bing_site_auth_xml():
    return _bing_xml_response()


def _bing_verification_preflight():
    if request.path.rstrip("/") == "/BingSiteAuth.xml":
        return _bing_xml_response()
    return None


# Handle ownership proof before any existing canonical-path redirect hooks.
app.before_request_funcs.setdefault(None, []).insert(0, _bing_verification_preflight)
