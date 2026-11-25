from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from ..address import _lookup_address, resolve_punch_address
from ..models import AttendancePunch
from .test_ingestion import BATCH_URL, IngestionFixture, _offline, _online, _payload


PRIVATE_ENDPOINT = "https://maps.example.test/reverse"


class ReverseLookupTests(SimpleTestCase):
    def setUp(self):
        self.punch = SimpleNamespace(
            gps_lat=Decimal("14.599536"), gps_long=Decimal("120.984221"), detected_address=""
        )

    @patch("klockin_attendance.address.requests.Session")
    def test_private_lookup_only_sends_a_rounded_coordinate_pair(self, session_factory):
        session = session_factory.return_value.__enter__.return_value
        response = session.get.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.return_value = [b'{"display_name":"  Malate,  Manila  "}']

        self.assertEqual(_lookup_address(PRIVATE_ENDPOINT, self.punch), "Malate, Manila")
        self.assertFalse(session.trust_env)
        session.get.assert_called_once_with(
            PRIVATE_ENDPOINT,
            params={"lat": "14.59954", "lon": "120.98422", "format": "jsonv2"},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "KlockIN attendance",
            },
            timeout=1.5,
            allow_redirects=False,
            stream=True,
        )

    @patch("klockin_attendance.address.requests.Session")
    def test_disabled_and_public_endpoints_send_no_requests(self, session_factory):
        with override_settings(KLOCKIN_REVERSE_GEOCODER_URL=""):
            resolve_punch_address(self.punch)
        with override_settings(
            KLOCKIN_REVERSE_GEOCODER_URL="https://nominatim.openstreetmap.org/reverse"
        ):
            with self.assertLogs("klockin_attendance.address", level="WARNING"):
                resolve_punch_address(self.punch)
        session_factory.assert_not_called()

    @patch("klockin_attendance.address.requests.Session")
    def test_redirect_and_oversized_response_do_not_resolve(self, session_factory):
        session = session_factory.return_value.__enter__.return_value
        response = session.get.return_value.__enter__.return_value
        response.status_code = 302
        self.assertEqual(_lookup_address(PRIVATE_ENDPOINT, self.punch), "")
        response.iter_content.assert_not_called()

        response.status_code = 200
        response.iter_content.return_value = [b"12345678", b"9"]
        with patch("klockin_attendance.address.MAX_RESPONSE_BYTES", 8):
            self.assertEqual(_lookup_address(PRIVATE_ENDPOINT, self.punch), "")


@override_settings(KLOCKIN_REVERSE_GEOCODER_URL=PRIVATE_ENDPOINT)
class PunchAddressReceiptTests(IngestionFixture, TestCase):
    def test_offline_punch_syncs_when_provider_is_unavailable(self):
        with patch("klockin_attendance.address._lookup_address", side_effect=requests.Timeout):
            with self.assertLogs("klockin_attendance.address", level="WARNING"):
                response = self.api.post(BATCH_URL, [_offline(_payload())], format="json")

        receipt = response.data["results"][0]
        self.assertEqual(receipt["status"], 201)
        self.assertEqual(receipt["sync_status"], "SYNCED")
        self.assertEqual(receipt["detected_address"], "")
        self.assertEqual(AttendancePunch.objects.get().sync_status, "SYNCED")

    @patch("klockin_attendance.address._lookup_address")
    def test_submitted_label_remains_available_without_egress(self, lookup):
        response = _online(self.api, _payload(detected_address="Malate, Manila"))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["detected_address"], "Malate, Manila")
        lookup.assert_not_called()


@override_settings(KLOCKIN_REVERSE_GEOCODER_URL=PRIVATE_ENDPOINT)
class CommittedAddressReceiptTests(IngestionFixture, TransactionTestCase):
    def test_new_address_is_cached_and_returned_on_cross_transport_replay(self):
        payload = _payload()

        def lookup(endpoint, punch):
            self.assertEqual(endpoint, PRIVATE_ENDPOINT)
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(AttendancePunch.objects.get(pk=punch.pk).sync_status, "SYNCED")
            return "Malate, Manila"

        with patch("klockin_attendance.address._lookup_address", side_effect=lookup) as lookup_mock:
            saved = _online(self.api, payload)
            replay = self.api.post(BATCH_URL, [_offline(payload)], format="json")

        self.assertEqual(saved.status_code, 201, saved.content)
        self.assertEqual(saved.data["detected_address"], "Malate, Manila")
        self.assertEqual(replay.data["results"][0]["status"], 200)
        self.assertEqual(replay.data["results"][0]["detected_address"], "Malate, Manila")
        self.assertEqual(AttendancePunch.objects.get().detected_address, "Malate, Manila")
        lookup_mock.assert_called_once()
