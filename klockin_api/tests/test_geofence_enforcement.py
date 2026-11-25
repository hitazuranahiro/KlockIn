"""An enabled fence denies a punch when its configuration cannot be evaluated."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from klockin_attendance.services import PunchRejected, _check_geofence


class GeofenceFailClosedTests(SimpleTestCase):
    @patch("klockin_attendance.services.GeoFencing.for_company")
    def test_invalid_fence_denies_the_punch(self, get_fence):
        employee = SimpleNamespace(get_company=lambda: object())
        get_fence.return_value = SimpleNamespace(
            start=True, allows=Mock(side_effect=ValueError("Invalid fence")), pk=7
        )
        with self.assertLogs("klockin_attendance.services", level="ERROR"):
            with self.assertRaises(PunchRejected) as denial:
                _check_geofence(employee, 14.6, 120.9)
        self.assertEqual(denial.exception.status, 503)
        self.assertEqual(denial.exception.code, "geofence_unavailable")

    @patch("klockin_attendance.services.GeoFencing.for_company")
    def test_disabled_fence_skips_distance_calculation(self, get_fence):
        employee = SimpleNamespace(get_company=lambda: object())
        get_fence.return_value = SimpleNamespace(start=False, allows=Mock())
        _check_geofence(employee, 14.6, 120.9)
        get_fence.return_value.allows.assert_not_called()
