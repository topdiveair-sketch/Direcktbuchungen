import unittest
import urllib.error
from datetime import date
from unittest.mock import patch
import beds24_rates as b

class Beds24AuthStageTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"BEDS24_REFRESH_TOKEN":"example-secret","BEDS24_ROOM_ID_BACHBLICK":"1","BEDS24_PORTAL_PRICE_SLOT_BACHBLICK":"1"})
        self.env.start()
    def tearDown(self):
        self.env.stop()
    def test_refresh_401_distinguished(self):
        err=urllib.error.HTTPError("https://example.invalid",401,"Unauthorized",{},None)
        with patch.object(b,"_token",side_effect=err):
            r=b.push_rate("Bachblick",date(2026,10,13),109)
        self.assertEqual(r["error_code"],"auth_unauthorized")
        self.assertNotIn("example-secret",str(r))
    def test_inventory_401_distinguished(self):
        err=urllib.error.HTTPError("https://example.invalid",401,"Unauthorized",{},None)
        with patch.object(b,"_token",return_value="access-secret"),patch.object(b,"_request",side_effect=err):
            r=b.push_rate("Bachblick",date(2026,10,13),109)
        self.assertEqual(r["error_code"],"inventory_unauthorized")
        self.assertNotIn("access-secret",str(r))
if __name__=="__main__":
    unittest.main()
