"""Every legacy API punch URL requires the KlockIN evidence contract."""

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from attendance.models import Attendance, AttendanceActivity
from klockin.testkit import make_company, make_employee, make_user
from klockin_attendance.models import AttendancePunch


class LegacyPunchUpgradeTests(TestCase):
    def test_mobile_clock_in_and_out_require_v2_on_both_prefixes(self):
        company = make_company("Punch upgrade test")
        user = make_user("legacy-punch")
        employee = make_employee(company=company, email=user.email, user=user)
        token = RefreshToken.for_user(user).access_token
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        for prefix in ("/api/v1", "/api"):
            for path in ("clock-in", "clock-out"):
                with self.subTest(prefix=prefix, path=path):
                    response = client.post(f"{prefix}/attendance/{path}/", {}, format="json")
                    self.assertEqual(response.status_code, 426)
                    self.assertEqual(response.json()["code"], "attendance_v2_required")
        self.assertFalse(Attendance.objects.filter(employee_id=employee).exists())
        self.assertFalse(AttendanceActivity.objects.filter(employee_id=employee).exists())
        self.assertFalse(AttendancePunch.objects.filter(employee=employee).exists())
