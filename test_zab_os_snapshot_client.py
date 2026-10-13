"""Tests for Windows-side read-only OS snapshot client."""
import hashlib
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
        payload = {"room_id":"Bachblick","bookings":[],"blocks":[],"sync":{"verified":False,"provider_status":{}}}
        payload["revision"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with patch("urllib.request.OpenerDirector.open", return_value=Response(payload)) as mocked:
            self.assertEqual(fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20"),payload)
            req = mocked.call_args.args[0]
            self.assertEqual(req.get_header("Authorization"),"Bearer secret")
    def test_missing_sync_status(self):
        payload = {"room_id":"Bachblick","bookings":[],"blocks":[],"revision":"a"*64}
        with patch("urllib.request.OpenerDirector.open", return_value=Response(payload)):
            with self.assertRaisesRegex(SnapshotError,"Synchronisierungsstatus"):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")
    def test_malformed_revision(self):
        payload = {"room_id":"Bachblick","bookings":[],"blocks":[],"revision":"abc","sync":{"verified":False,"provider_status":{}}}
        with patch("urllib.request.OpenerDirector.open", return_value=Response(payload)):
            with self.assertRaisesRegex(SnapshotError,"Pruefsumme"):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")
    def test_tampered_snapshot_is_rejected(self):
        payload = {"room_id":"Bachblick","bookings":[],"blocks":[],"sync":{"verified":False,"provider_status":{}}}
        payload["revision"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        payload["blocks"].append({"start":"2026-10-14","end":"2026-10-15","source":"altered"})
        with patch("urllib.request.OpenerDirector.open", return_value=Response(payload)):
            with self.assertRaisesRegex(SnapshotError,"stimmt nicht"):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")
    def test_invalid_occupancy_intervals_are_rejected(self):
        cases = [
            {"bookings":[{"arrival":"2026-10-16","departure":"2026-10-15","status":"confirmed"}],"blocks":[]},
            {"bookings":[],"blocks":[{"start":"2026-10-20","end":"2026-10-20","source":"Airbnb"}]},
            {"bookings":[{"arrival":"invalid","departure":"2026-10-17","status":"pending"}],"blocks":[]},
            {"bookings":[],"blocks":[{"start":"2026-10-20","end":"invalid","source":"Beds24"}]},
        ]
        for case in cases:
            with self.subTest(case=case):
                payload = {"room_id":"Bachblick","sync":{"verified":False,"provider_status":{}},**case}
                payload["revision"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                with patch("urllib.request.OpenerDirector.open", return_value=Response(payload)):
                    with self.assertRaisesRegex(SnapshotError,"Sperrintervalle"):
                        fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-31")
    def test_unrelated_calendar_records_rejected(self):
        payload = {"room_id":"Bachblick","sync":{"verified":False,"provider_status":{}},"bookings":[],
                   "blocks":[{"start":"2026-09-01","end":"2026-09-02","source":"Airbnb"}]}
        payload["revision"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with patch("urllib.request.OpenerDirector.open", return_value=Response(payload)):
            with self.assertRaisesRegex(SnapshotError,"Sperrintervalle"):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-31")
    def test_invalid_requested_range_rejected(self):
        payload = {"room_id":"Bachblick","sync":{"verified":False,"provider_status":{}},"bookings":[],"blocks":[]}
        payload["revision"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with patch("urllib.request.OpenerDirector.open", return_value=Response(payload)):
            with self.assertRaisesRegex(SnapshotError,"Kalenderzeitraum"):
                fetch_snapshot("https://example.test","secret","2026-10-31","2026-10-13")
    def test_unverified_sync_only(self):
        for sync in ({"verified":True,"provider_status":{}},
                     {"verified":False}):
            with self.subTest(sync=sync):
                payload = {"room_id":"Bachblick","sync":sync,"bookings":[],"blocks":[]}
                payload["revision"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                with patch("urllib.request.OpenerDirector.open", return_value=Response(payload)):
                    with self.assertRaises(SnapshotError):
                        fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-31")
    def test_redirect_is_never_followed(self):
        from zab_os_snapshot_client import _NoRedirect
        handler = _NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Moved", {}, "https://attacker.test/"))
    def test_http_401(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=HTTPError("url",401,"unauthorized",{},None)):
            with self.assertRaisesRegex(SnapshotError,"HTTP 401"):
                fetch_snapshot("https://example.test","bad","2026-10-13","2026-10-20")
    def test_network_failure(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=URLError("offline")):
            with self.assertRaises(SnapshotError):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")
    def test_no_http(self):
        with self.assertRaises(SnapshotError):
            fetch_snapshot("http://example.test","secret","2026-10-13","2026-10-20")
    def test_wrong_room(self):
        with patch("urllib.request.OpenerDirector.open", return_value=Response({"room_id":"another","bookings":[],"blocks":[]})):
            with self.assertRaises(SnapshotError):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")
    def test_missing_calendar(self):
        with patch("urllib.request.OpenerDirector.open", return_value=Response({"room_id":"Bachblick","bookings":[]})):
            with self.assertRaises(SnapshotError):
                fetch_snapshot("https://example.test","secret","2026-10-13","2026-10-20")

if __name__=="__main__":
    unittest.main()
