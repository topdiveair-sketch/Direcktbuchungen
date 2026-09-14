import os
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

import booking_connectivity as bc


SAMPLE_RESERVATIONS = """<?xml version='1.0' encoding='UTF-8'?>
<reservations>
  <reservation>
    <customer>
      <first_name>Anna</first_name>
      <last_name>Example</last_name>
      <countrycode>AT</countrycode>
      <cc_number>4111111111111111</cc_number>
    </customer>
    <id>123456789</id>
    <status>new</status>
    <room>
      <arrival_date>2026-10-01</arrival_date>
      <departure_date>2026-10-03</departure_date>
      <guest_counts><guest_count count='2' type='adult'/></guest_counts>
      <guest_name>Anna Example</guest_name>
      <id>998877</id>
      <info>Breakfast is included in the room rate.</info>
      <meal_plan>Breakfast is included in the room rate.</meal_plan>
      <roomreservation_id>777666</roomreservation_id>
    </room>
  </reservation>
</reservations>
"""


class BookingConnectivityTests(unittest.TestCase):
    def test_reservation_parser_extracts_operational_fields_only(self):
        with patch.dict(os.environ, {"BOOKING_ROOM_ID_BACHBLICK": "998877"}, clear=False):
            records = bc._parse_bxml_reservations(SAMPLE_RESERVATIONS)
        self.assertEqual(len(records), 1)
        row = records[0]
        self.assertEqual(row["reservation_id"], "123456789")
        self.assertEqual(row["room"], "Bachblick")
        self.assertEqual(row["guest_name"], "Anna Example")
        self.assertEqual(row["country"], "AT")
        self.assertEqual(row["guests"], 2)
        self.assertIs(row["breakfast"], True)
        # Payment-card nodes from Booking XML must never enter the returned OS payload.
        self.assertFalse(any("cc_" in key.lower() or "card" in key.lower() for key in row))
        self.assertNotIn("4111111111111111", repr(row))

    def test_breakfast_not_included_is_false(self):
        room = ET.fromstring(
            "<room><meal_plan>Breakfast is not included in the room rate.</meal_plan></room>"
        )
        self.assertIs(bc._breakfast_value(room), False)

    def test_optional_paid_breakfast_stays_unknown(self):
        room = ET.fromstring(
            "<room><meal_plan>Breakfast costs EUR 14 per person per night.</meal_plan></room>"
        )
        self.assertIsNone(bc._breakfast_value(room))

    def test_rate_push_fails_closed_when_connectivity_is_not_configured(self):
        names = [
            "BOOKING_CONNECTIVITY_CLIENT_ID",
            "BOOKING_CONNECTIVITY_CLIENT_SECRET",
            "BOOKING_ROOM_ID_BACHBLICK",
            "BOOKING_RATE_ID_BACHBLICK",
        ]
        clean = {name: "" for name in names}
        with patch.dict(os.environ, clean, clear=False):
            result = bc.push_rate("Bachblick", __import__("datetime").date(2026, 10, 1), 139.0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "not_configured")

    def test_token_credentials_are_never_reported_by_status(self):
        with patch.dict(
            os.environ,
            {
                "BOOKING_CONNECTIVITY_CLIENT_ID": "secret-client-id",
                "BOOKING_CONNECTIVITY_CLIENT_SECRET": "secret-client-secret",
                "BOOKING_ROOM_ID_BACHBLICK": "room-1",
                "BOOKING_RATE_ID_BACHBLICK": "rate-1",
            },
            clear=False,
        ):
            status = bc.connectivity_status("Bachblick")
        self.assertTrue(status["configured"])
        raw = repr(status)
        self.assertNotIn("secret-client-id", raw)
        self.assertNotIn("secret-client-secret", raw)


if __name__ == "__main__":
    unittest.main()
