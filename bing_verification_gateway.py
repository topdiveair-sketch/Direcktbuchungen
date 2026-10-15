"""Bing ownership proof at WSGI boundary, ahead of URL canonicalization."""
from pathlib import Path
from flask import Response
from wachauetappe_gateway import app

_BING_PATHS = {"/BingSiteAuth.xml", "/BingSiteAuth.xml/"}
_original_wsgi_app = app.wsgi_app


def _bing_ownership_wsgi(environ, start_response):
    if environ.get("PATH_INFO") in _BING_PATHS:
        data = (Path(__file__).resolve().parent / "BingSiteAuth.xml").read_bytes()
        response = Response(data, status=200, mimetype="application/xml")
        return response(environ, start_response)
    return _original_wsgi_app(environ, start_response)


app.wsgi_app = _bing_ownership_wsgi
