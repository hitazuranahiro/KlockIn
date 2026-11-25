import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.admin.models import LogEntry
from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from geofencing.models import GeoFencing
from klockin.testkit import make_company, make_employee, make_user

from ..models import AttendancePunch, EmployeeDevice


PUNCH_URL = "/api/v2/attendance/punch/"
BATCH_URL = "/api/v2/attendance/sync-batch/"


def _selfie():
    content = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(content, format="JPEG")
    return content.getvalue()


def _payload(**overrides):
    return {
        "punch_uuid": str(uuid4()),
        "punch_type": "CLOCK_IN",
        "punched_at": (timezone.now() - timedelta(hours=5)).isoformat(),
        "device_id": "installation-123",
        "gps_lat": "14.599500",
        "gps_long": "120.984200",
        **overrides,
    }


def _online(client, data):
    upload = SimpleUploadedFile("selfie.jpg", _selfie(), content_type="image/jpeg")
    return client.post(PUNCH_URL, {**data, "punch_selfie": upload}, format="multipart")


def _offline(data):
    return {**data, "punch_selfie": base64.b64encode(_selfie()).decode("ascii")}


def _client(user):
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


class IngestionFixture:
    def setUp(self):
        private_dir = TemporaryDirectory()
        self.addCleanup(private_dir.cleanup)
        self.private_path = Path(private_dir.name)
        scope = override_settings(KLOCKIN_SELFIE_ROOT=private_dir.name)
        scope.enable()
        self.addCleanup(scope.disable)
        self.company = make_company("Punch Co")
        self.user = make_user("punch-user")
        self.employee = make_employee(company=self.company, email=self.user.email, user=self.user)
        self.api = _client(self.user)


class PunchIngestionTests(IngestionFixture, TestCase):
    def test_authenticated_multipart_and_cross_transport_replay(self):
        payload = _payload()
        self.assertEqual(_online(APIClient(), payload).status_code, 401)
        posted = _online(self.api, payload)
        self.assertEqual(posted.status_code, 201, posted.content)
        self.assertEqual(posted.data["sync_status"], "SYNCED")
        self.assertFalse(posted.data["duplicate"])
        self.assertNotIn("punch_selfie", posted.data)

        punch = AttendancePunch.objects.get()
        self.assertEqual(punch.employee, self.employee)
        self.assertEqual(punch.source, "ONLINE")
        self.assertEqual(EmployeeDevice.objects.get().device_id, payload["device_id"])
        self.assertEqual(punch.server_receive_timestamp, punch.punched_at)
        self.assertEqual(punch.device_punched_at, parse_datetime(payload["punched_at"]))
        self.assertEqual(parse_datetime(posted.data["punched_at"]), punch.punched_at)
        with punch.punch_selfie.open("rb") as selfie:
            self.assertEqual(selfie.read(), _selfie())
        with self.assertRaises(ValueError):
            punch.punch_selfie.url

        replay = self.api.post(BATCH_URL, [_offline(payload)], format="json")
        self.assertEqual(replay.status_code, 200, replay.content)
        receipt = replay.data["results"][0]
        self.assertEqual(receipt["status"], 200)
        self.assertTrue(receipt["duplicate"])
        self.assertEqual(
            receipt["server_receive_timestamp"], posted.data["server_receive_timestamp"]
        )
        self.assertEqual(AttendancePunch.objects.count(), 1)
        self.assertEqual(len(list(self.private_path.glob("punches/*"))), 1)

    def test_batch_returns_independent_outcomes_and_uuid_conflicts(self):
        valid = _payload()
        invalid = _payload(gps_lat="180.000000")
        conflict = {**valid, "detected_address": "different address"}
        invalid_uuid = {**valid, "punch_uuid": "malformed"}
        response = self.api.post(
            BATCH_URL,
            [_offline(item) for item in (valid, invalid, conflict, invalid_uuid)],
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        receipts = response.data["results"]
        self.assertEqual([receipt["status"] for receipt in receipts], [201, 400, 409, 400])
        self.assertEqual([receipt["index"] for receipt in receipts], [0, 1, 2, 3])
        self.assertEqual(receipts[1]["punch_uuid"], invalid["punch_uuid"])
        self.assertEqual(receipts[2]["code"], "punch_conflict")
        self.assertIsNone(receipts[3]["punch_uuid"])
        self.assertEqual(AttendancePunch.objects.get().source, "OFFLINE")

        other_user = make_user("other-punch-user")
        make_employee(company=self.company, email=other_user.email, user=other_user)
        result = _online(_client(other_user), valid)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "punch_conflict")
        self.assertFalse(EmployeeDevice.objects.filter(employee__employee_user_id=other_user).exists())

    def test_batch_requires_bounded_array_and_valid_selfie(self):
        items = [_offline(_payload()) for _ in range(6)]
        too_many = self.api.post(BATCH_URL, items, format="json")
        self.assertEqual(too_many.status_code, 400)
        invalid = self.api.post(
            BATCH_URL, [{**_payload(), "punch_selfie": "bad-image!"}], format="json"
        )
        self.assertEqual(invalid.data["results"][0]["status"], 400)
        self.assertFalse(AttendancePunch.objects.exists())

    def test_device_binding_and_repeat_window_apply_to_late_punches(self):
        punched_at = timezone.now() - timedelta(hours=5)
        first = _payload(punched_at=punched_at.isoformat())
        def sync(data):
            return self.api.post(BATCH_URL, [_offline(data)], format="json").data["results"][0]

        self.assertEqual(sync(first)["status"], 201)
        first_event = AttendancePunch.objects.get()
        self.assertEqual(first_event.device_punched_at, punched_at)
        self.assertEqual(first_event.punched_at, punched_at)
        self.assertGreater(first_event.server_receive_timestamp, punched_at)
        repeat = _payload(punched_at=(punched_at - timedelta(seconds=179)).isoformat())
        result = sync(repeat)
        self.assertEqual((result["status"], result["code"]), (409, "punch_too_soon"))
        boundary = _payload(
            device_id="replacement-device",
            punch_type="CLOCK_OUT",
            punched_at=(punched_at + timedelta(minutes=3)).isoformat(),
        )
        denied = sync(boundary)
        self.assertEqual((denied["status"], denied["code"]), (403, "device_mismatch"))
        boundary["device_id"] = first["device_id"]
        self.assertEqual(sync(boundary)["status"], 201)

    def test_geofence_applies_to_both_transports(self):
        GeoFencing.objects.bulk_create(
            [
                GeoFencing(
                    latitude=14.5995,
                    longitude=120.9842,
                    radius_in_meters=100,
                    company_id=self.company,
                    start=True,
                )
            ]
        )
        first = _payload(gps_lat="0.000000")
        outside = _online(self.api, first)
        self.assertEqual((outside.status_code, outside.data["code"]), (403, "outside_geofence"))
        second = _payload(punch_type="CLOCK_OUT", gps_lat="0.000000")
        response = self.api.post(BATCH_URL, [_offline(second)], format="json")
        self.assertEqual(response.data["results"][0]["code"], "outside_geofence")
        self.assertFalse(EmployeeDevice.objects.exists())
        inside = _online(self.api, _payload())
        self.assertEqual(inside.status_code, 201, inside.content)

    def test_storage_and_binding_roll_back_when_projection_fails(self):
        payload = _payload()
        with patch(
            "klockin_attendance.projection.project_punch", side_effect=OSError("unavailable")
        ):
            failed = _online(self.api, payload)
        self.assertEqual(failed.status_code, 503)
        self.assertFalse(EmployeeDevice.objects.exists())
        self.assertFalse(AttendancePunch.objects.exists())
        self.assertEqual(list(self.private_path.glob("punches/*")), [])
        self.assertEqual(_online(self.api, payload).status_code, 201)

    def test_admin_reset_requires_configured_pin_and_logs_success(self):
        EmployeeDevice.objects.create(employee=self.employee, device_id="old-device")
        admin_user = make_user("device-admin", is_superuser=True)
        make_employee(company=self.company, email=admin_user.email, user=admin_user)
        self.client.force_login(admin_user)
        url = reverse("admin:klockin_attendance_employeedevice_changelist")
        body = {"action": "reset_binding", "_selected_action": str(self.employee.pk), "index": 0}
        with override_settings(KLOCKIN_DEVICE_RESET_PIN_HASH=""):
            self.client.post(url, body)
            self.assertTrue(EmployeeDevice.objects.exists())
        with override_settings(KLOCKIN_DEVICE_RESET_PIN_HASH=make_password("246810")):
            self.client.post(url, {**body, "reset_pin": "wrong"})
            self.assertTrue(EmployeeDevice.objects.exists())
            self.client.post(url, {**body, "reset_pin": "246810"})
        self.assertFalse(EmployeeDevice.objects.exists())
        self.assertTrue(
            LogEntry.objects.filter(user=admin_user, change_message__contains="KlockIN").exists()
        )


class ConcurrentPunchTests(IngestionFixture, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update_of")
    def test_simultaneous_retries_persist_one_event_and_one_photo(self):
        payload = _payload()
        start = Barrier(2, timeout=10)

        def post():
            try:
                client = _client(self.user)
                start.wait()
                return _online(client, payload).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            submissions = [pool.submit(post) for _ in range(2)]
            statuses = sorted(future.result(timeout=20) for future in submissions)
        self.assertEqual(statuses, [200, 201])
        self.assertEqual(AttendancePunch.objects.count(), 1)
        self.assertEqual(EmployeeDevice.objects.count(), 1)
        self.assertEqual(len(list(self.private_path.glob("punches/*"))), 1)
