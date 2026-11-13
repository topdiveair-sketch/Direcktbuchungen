"""Offline regression tests for the opt-in, read-only volume diagnostics."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from volume_diagnostics import scan_volume, volume_diagnostics


class VolumeDiagnosticsTests(unittest.TestCase):
    def test_metadata_without_contents_or_symlink_following(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "backups").mkdir()
            (base / "backups" / "copy.db").write_bytes(b"x" * 120)
            (base / "small.log").write_bytes(b"a" * 30)
            (base / "link").symlink_to(base / "backups", target_is_directory=True)
            result = scan_volume(td)
            self.assertTrue(result["readonly"])
            self.assertEqual(result["directory_bytes"]["backups"], 120)
            self.assertEqual(result["directory_bytes"]["(root)"], 30)
            self.assertEqual(result["read_errors"], 0)
            self.assertNotIn("copy.db", str(result))

    def test_fail_closed_endpoint(self):
        app = Flask(__name__)
        app.register_blueprint(volume_diagnostics)
        client = app.test_client()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(client.get("/internal/volume-diagnostics").status_code, 404)
        with patch.dict(os.environ, {"ZAB_VOLUME_DIAG_ENABLED": "1",
                                   "ZAB_VOLUME_DIAG_TOKEN": "x" * 40}):
            self.assertEqual(client.get("/internal/volume-diagnostics").status_code, 404)
            self.assertEqual(client.get("/internal/volume-diagnostics",
                headers={"X-ZAB-Diagnostics-Token": "wrong"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
