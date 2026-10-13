"""Tests for Windows-side read-only OS snapshot client."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from zab_os_snapshot_client import SnapshotError, fetch_snapshot

class Response:
    status = 200
    def __init__(self, payload):
        self.data = io.BytesIO(json.dumps(payload).encode("utf-8"))
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, *args):
        return self.data.read(*args)

class ClientTests(unittest.TestCase):
    def test_success(self):
        payload = {"room_id":"Bachblick","bookings":[],"blocks":[],"revision":"a"*64,"sync":{"verified":False}}
        with patch("urllib.request.urlopen", return_value=Response(payload)) as mocked:
            self.assertEqual(fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20"),payload)
            req = mocked.call_args.args[0]
            self.assertEqual(req.get_header("Authorization"),"Bearer secret")
    def test_missing_sync_status(self):
        payload = {"room_id":"Bachblick","bookings":[],"blocks":[],"revision":"a"*64}
        with patch("urllib.request.urlopen", return_value=Response(payload)):
            with self.assertRaisesRegex(SnapshotError,"Synchronisierungsstatus"):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")
    def test_malformed_revision(self):
        payload = {"room_id":"Bachblick","bookings":[],"blocks":[],"revision":"abc","sync":{"verified":False}}
        with patch("urllib.request.urlopen", return_value=Response(payload)):
            with self.assertRaisesRegex(SnapshotError,"Pruefsumme"):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")
    def test_http_401(self):
        with patch("urllib.request.urlopen", side_effect=HTTPError("url",401,"unauthorized",{},None)):
            with self.assertRaisesRegex(SnapshotError,"HTTP 401"):
                fetch_snapshot("https://example.test","bad","2026-10-13","2026-10-20")
    def test_network_failure(self):
        with patch("urllib.request.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(SnapshotError):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")
    def test_no_http(self):
        with self.assertRaises(SnapshotError):
            fetch_snapshot("http://example.test","secret","2026-10-13","2026-10-20")
    def test_wrong_room(self):
        with patch("urllib.request.urlopen", return_value=Response({"room_id":"another","bookings":[],"blocks":[]})):
            with self.assertRaises(SnapshotError):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")
    def test_missing_calendar(self):
        with patch("urllib.request.urlopen", return_value=Response({"room_id":"Bachblick","bookings":[]})):
            with self.assertRaises(SnapshotError):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")

if __name__=="__main__":
    unittest.main()
