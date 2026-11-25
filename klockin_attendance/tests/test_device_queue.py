from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from ..models import EmployeeDevice
from .test_ingestion import IngestionFixture


QUEUE_URL = "/api/v2/attendance/device-queue/"


class DeviceQueueTests(IngestionFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.device = EmployeeDevice.objects.create(employee=self.employee, device_id="phone")
        self.observed = timezone.now()

    def report(self, pending=3, **changes):
        return self.api.post(
            QUEUE_URL,
            {
                "device_id": "phone",
                "pending_punches": pending,
                "observed_at": self.observed.isoformat(),
                **changes,
            },
            format="json",
        )

    def test_latest_observation_wins_and_zero_is_reportable(self):
        self.assertEqual(self.report().status_code, 204)
        self.device.refresh_from_db()
        self.assertEqual(self.device.pending_punches, 3)
        self.assertEqual(self.device.queue_observed_at, self.observed)
        self.assertGreaterEqual(self.device.queue_reported_at, self.observed)
        self.assertEqual(self.report(0, observed_at=(self.observed + timedelta(seconds=1)).isoformat()).status_code, 204)
        self.assertEqual(self.report(9).status_code, 204)
        self.device.refresh_from_db()
        self.assertEqual(self.device.pending_punches, 0)

    def test_authentication_binding_and_validation(self):
        self.assertEqual(APIClient().post(QUEUE_URL, {}, format="json").status_code, 401)
        response = self.report(device_id="another-device")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "device_mismatch")
        self.assertEqual(self.report(-1).status_code, 400)
        self.assertEqual(self.report(observed_at=(self.observed + timedelta(days=1)).isoformat()).status_code, 400)
        self.device.refresh_from_db()
        self.assertIsNone(self.device.pending_punches)
        self.device.delete()
        response = self.report()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "device_not_enrolled")
        self.assertFalse(EmployeeDevice.objects.exists())
