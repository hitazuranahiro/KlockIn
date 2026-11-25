from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.db import connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from klockin.testkit import make_company, make_employee, make_user

from ..models import AttendancePunch, EmployeeDevice
from .test_ingestion import IngestionFixture, _client, _online, _payload


LOGIN_URL = "/api/v1/auth/login/"


class DeviceLoginTests(TestCase):
    def setUp(self):
        company = make_company("Login device company")
        self.user = make_user("device-login-user", password="test-login-password")
        self.employee = make_employee(company=company, email=self.user.email, user=self.user)
        self.credentials = {
            "username": self.user.username,
            "password": "test-login-password",
        }
        self.api = APIClient()

    def _login(self, **fields):
        return self.api.post(LOGIN_URL, {**self.credentials, **fields}, format="json")

    def test_first_mobile_login_binds_and_same_installation_can_sign_in_again(self):
        for _ in range(2):
            response = self._login(device_id="installation-1")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertTrue(response.data["access"])
            self.assertTrue(response.data["refresh"])
            self.assertEqual(response.data["employee"]["id"], self.employee.pk)

        self.assertEqual(
            EmployeeDevice.objects.get(employee=self.employee).device_id, "installation-1"
        )

    def test_other_installation_is_denied_without_issuing_tokens(self):
        self.assertEqual(self._login(device_id="installation-1").status_code, 200)
        count = OutstandingToken.objects.filter(user=self.user).count()
        denied = self._login(device_id="installation-2")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["code"], "device_mismatch")
        self.assertNotIn("access", denied.data)
        self.assertNotIn("refresh", denied.data)
        self.assertEqual(OutstandingToken.objects.filter(user=self.user).count(), count)
        self.assertEqual(
            EmployeeDevice.objects.get(employee=self.employee).device_id, "installation-1"
        )

    def test_legacy_jwt_login_passes_without_creating_or_changing_a_binding(self):
        legacy = self.api.post("/api/auth/login/", self.credentials, format="json")
        self.assertEqual(legacy.status_code, 200, legacy.content)
        self.assertTrue(legacy.data["access"])
        self.assertFalse(EmployeeDevice.objects.exists())

        self.assertEqual(self._login(device_id="installation-1").status_code, 200)
        legacy = self._login()
        self.assertEqual(legacy.status_code, 200, legacy.content)
        self.assertTrue(legacy.data["refresh"])
        self.assertEqual(
            EmployeeDevice.objects.get(employee=self.employee).device_id, "installation-1"
        )

    def test_login_validates_supplied_device_id_after_password_authentication(self):
        unauthorized = self._login(password="wrong-password", device_id=None)
        self.assertEqual(unauthorized.status_code, 401)
        for value in (None, 42, "", " trailing ", "newline\nvalue", "a" * 129):
            with self.subTest(value=value):
                response = self._login(device_id=value)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.data["code"], "invalid_device_id")
                self.assertNotIn("access", response.data)
        self.assertFalse(EmployeeDevice.objects.exists())

    def test_first_binding_rolls_back_if_token_creation_fails(self):
        self.api.raise_request_exception = False
        with patch(
            "klockin_api.api_views.auth.views.RefreshToken.for_user",
            side_effect=RuntimeError("failed token issuance"),
        ):
            response = self._login(device_id="installation-1")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(EmployeeDevice.objects.exists())
        self.assertEqual(self._login(device_id="installation-1").status_code, 200)


class ConcurrentDeviceEnrollmentTests(IngestionFixture, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update_of")
    def test_login_and_first_legacy_punch_cannot_bind_different_installations(self):
        start = Barrier(2, timeout=10)

        def login():
            try:
                start.wait()
                return APIClient().post(
                    LOGIN_URL,
                    {
                        "username": self.user.username,
                        "password": "pass",
                        "device_id": "login-installation",
                    },
                    format="json",
                )
            finally:
                connections.close_all()

        def punch():
            try:
                client = _client(self.user)
                start.wait()
                return _online(client, _payload(device_id="punch-installation"))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            login_call, punch_call = pool.submit(login), pool.submit(punch)
            login_response = login_call.result(timeout=20)
            punch_response = punch_call.result(timeout=20)

        binding = EmployeeDevice.objects.get(employee=self.employee)
        if login_response.status_code == 200:
            self.assertEqual(binding.device_id, "login-installation")
            self.assertEqual(punch_response.status_code, 403)
            self.assertEqual(punch_response.data["code"], "device_mismatch")
            self.assertFalse(AttendancePunch.objects.exists())
        else:
            self.assertEqual(login_response.status_code, 403)
            self.assertEqual(login_response.data["code"], "device_mismatch")
            self.assertEqual(punch_response.status_code, 201)
            self.assertEqual(binding.device_id, "punch-installation")
            self.assertEqual(AttendancePunch.objects.get().device_id, binding.device_id)
