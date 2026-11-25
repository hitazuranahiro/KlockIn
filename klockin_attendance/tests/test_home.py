from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from base.models import EmployeeShiftDay
from klockin.testkit.factories import make_attendance, make_company, make_employee, make_user


class WorkspaceHomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Workspace test company")
        cls.admin = make_user("workspace-admin", is_superuser=True)
        make_employee(company=company, user=cls.admin, email=cls.admin.email)

        today = timezone.localdate()
        EmployeeShiftDay.objects.get_or_create(day=today.strftime("%A").lower())
        cls.employee_user = make_user("workspace-employee")
        employee = make_employee(
            company=company, user=cls.employee_user, email=cls.employee_user.email
        )
        make_attendance(employee=employee, attendance_date=today, clock_in="08:45:00")
        other = make_employee(company=company, email="workspace-other@example.test")
        make_attendance(employee=other, attendance_date=today, clock_in="11:15:00")

    def test_team_overview_renders_live_counts_without_a_chart_cdn(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard"))

        self.assertTemplateUsed(response, "klockin_attendance/home.html")
        self.assertContains(response, "Attendance today")
        self.assertContains(response, "Punches awaiting review")
        self.assertNotContains(response, "cdn.jsdelivr.net/npm/apexcharts")
        self.assertEqual(response.context["week"][-1]["count"], 2)
        self.assertEqual(response.context["employee_count"], 3)
        self.assertContains(response, "?view=analytics")

    def test_employee_home_keeps_its_personal_scope(self):
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("dashboard"), follow=True)

        self.assertRedirects(response, reverse("ess-dashboard"))
        self.assertContains(response, "My attendance today")
        self.assertContains(response, "8:45 AM")
        self.assertNotContains(response, "11:15 AM")
        self.assertNotContains(response, "Punches awaiting review")
        self.assertEqual(response.context["week"][-1]["count"], 1)

    def test_existing_report_dashboards_are_still_accessible(self):
        self.client.force_login(self.admin)
        analytics = self.client.get(reverse("dashboard"), {"view": "analytics"})
        self.assertTemplateUsed(analytics, "dashboard.html")

        self.client.force_login(self.employee_user)
        details = self.client.get(reverse("ess-dashboard"), {"view": "details"})
        self.assertTemplateUsed(details, "base/ess_dashboard.html")

    def test_empty_timekeeping_day_displays_the_results_panel(self):
        self.client.force_login(self.admin)
        empty_date = timezone.localdate().replace(year=2000, month=1, day=1)
        response = self.client.get(
            reverse("klockin-attendance"), {"start": empty_date, "end": empty_date}
        )

        self.assertContains(response, "0 results")
        self.assertContains(response, "No attendance records in this date range.")
