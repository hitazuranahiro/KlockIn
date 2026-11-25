from django.db import connection
from django.test import TestCase, skipUnlessDBFeature
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from employee.models import Employee
from klockin.testkit import make_company, make_employee, make_user
from klockin_attendance.models import EmployeeDevice


LOGIN_URL = "/api/v1/auth/login/"
PASSWORD = "fixture-test-password"


class EmployeeIdLoginTests(TestCase):
    def setUp(self):
        company = make_company("Badge Login Fixture")
        self.user = make_user("account-login-name", password=PASSWORD)
        self.employee = make_employee(company=company, email=self.user.email, user=self.user)
        Employee._base_manager.filter(pk=self.employee.pk).update(badge_id="EMP-0042")
        self.client = APIClient(REMOTE_ADDR="127.0.0.42")

    def test_badge_authenticates_and_enrolls_the_same_device_as_legacy_username(self):
        response = self.client.post(
            LOGIN_URL,
            {"employee_id": "EMP-0042", "password": PASSWORD, "device_id": "phone-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["employee"]["id"], self.employee.pk)
        self.assertEqual(EmployeeDevice.objects.get(employee=self.employee).device_id, "phone-1")
        response = self.client.post(
            LOGIN_URL,
            {"username": self.user.username, "password": PASSWORD, "device_id": "phone-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

    def _duplicate_badge(self, *, employee_active=True, account_active=True):
        # Simulate legacy inconsistent rows. TestCase rolls back the index
        # removal along with the fixture, leaving the normal constraint intact.
        self.assertTrue(connection.in_atomic_block)
        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX unique_badge_id")
        company = make_company("Other Badge Login Fixture")
        user = make_user("other-badge-account", password=PASSWORD)
        employee = make_employee(company=company, email=user.email, user=user)
        Employee._base_manager.filter(pk=employee.pk).update(
            badge_id="EMP-0042", is_active=employee_active,
        )
        if not account_active:
            user.is_active = False
            user.save(update_fields=["is_active"])

    @skipUnlessDBFeature("supports_partial_indexes", "can_rollback_ddl")
    def test_inactive_employee_does_not_block_active_badge(self):
        self._duplicate_badge(employee_active=False)
        response = self.client.post(
            LOGIN_URL, {"employee_id": "EMP-0042", "password": PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["employee"]["id"], self.employee.pk)

    @skipUnlessDBFeature("supports_partial_indexes", "can_rollback_ddl")
    def test_inactive_account_does_not_block_active_badge(self):
        self._duplicate_badge(account_active=False)
        response = self.client.post(
            LOGIN_URL, {"employee_id": "EMP-0042", "password": PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["employee"]["id"], self.employee.pk)

    @skipUnlessDBFeature("supports_partial_indexes", "can_rollback_ddl")
    def test_duplicate_active_badge_is_rejected_and_username_still_works(self):
        self._duplicate_badge()
        response = self.client.post(
            LOGIN_URL, {"employee_id": "EMP-0042", "password": PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 401, response.data)
        self.assertFalse(OutstandingToken.objects.filter(user=self.user).exists())
        response = self.client.post(
            LOGIN_URL, {"username": self.user.username, "password": PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["employee"]["id"], self.employee.pk)

    def test_unknown_badge_and_wrong_password_share_one_error(self):
        unknown = self.client.post(
            LOGIN_URL, {"employee_id": "EMP-missing", "password": PASSWORD}, format="json"
        )
        wrong = self.client.post(
            LOGIN_URL, {"employee_id": "EMP-0042", "password": "wrong-password"}, format="json"
        )
        self.assertEqual([unknown.status_code, wrong.status_code], [401, 401])
        self.assertEqual(unknown.data, wrong.data)
        self.assertFalse(OutstandingToken.objects.filter(user=self.user).exists())

    def test_badge_and_username_failures_share_the_axes_lockout(self):
        for attempt in range(5):
            identifier = {"employee_id": "EMP-0042"} if attempt % 2 == 0 else {"username": self.user.username}
            response = self.client.post(LOGIN_URL, {**identifier, "password": "wrong-password"}, format="json")
        self.assertEqual(response.status_code, 429, response.data)
        response = self.client.post(LOGIN_URL, {"employee_id": "EMP-0042", "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 429, response.data)

    def test_legacy_username_without_an_employee_profile_returns_403(self):
        web_only = make_user("web-only-account", password=PASSWORD)
        response = self.client.post(
            LOGIN_URL, {"username": web_only.username, "password": PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data["code"], "employee_required")
        self.assertFalse(OutstandingToken.objects.filter(user=web_only).exists())
