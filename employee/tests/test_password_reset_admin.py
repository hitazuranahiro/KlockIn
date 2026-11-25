from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from klockin.testkit.factories import make_company, make_employee, make_user


class EmployeePasswordResetAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Credential admin fixtures")
        cls.hr = make_user("reset-hr")
        cls.hr.user_permissions.add(Permission.objects.get(
            content_type__app_label="employee", codename="change_employee",
        ))
        make_employee(company=company, email="reset-hr@example.test", user=cls.hr)
        cls.target = make_employee(company=company, email="reset-target@example.test")
        privileged_user = make_user("reset-superuser", is_superuser=True)
        cls.privileged_employee = make_employee(
            company=company, email="reset-admin@example.test", user=privileged_user,
        )

    def test_individual_reset_requires_post_and_csrf_and_logs_the_actor(self):
        url = reverse("employee-reset-password-admin", args=[self.target.pk])
        password = self.target.employee_user_id.password
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(url).status_code, 405)
        enforcing = Client(enforce_csrf_checks=True)
        enforcing.force_login(self.hr)
        self.assertEqual(enforcing.post(url).status_code, 403)
        self.target.employee_user_id.refresh_from_db()
        self.assertEqual(self.target.employee_user_id.password, password)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.target.employee_user_id.refresh_from_db()
        self.assertNotEqual(self.target.employee_user_id.password, password)
        log = LogEntry.objects.get(user=self.hr, object_id=self.target.employee_user_id.pk)
        self.assertEqual(log.get_change_message(), "Reset employee password.")

    def test_non_superuser_cannot_reset_privileged_accounts(self):
        self.client.force_login(self.hr)
        admin_url = reverse("employee-reset-password-admin", args=[self.privileged_employee.pk])
        self.assertEqual(self.client.post(admin_url).status_code, 403)
        self.assertFalse(LogEntry.objects.filter(user=self.hr).exists())
