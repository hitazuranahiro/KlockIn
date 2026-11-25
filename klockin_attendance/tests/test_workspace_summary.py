from datetime import timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance, AttendanceLateComeEarlyOut, WorkRecords
from base.models import EmployeeShiftDay
from klockin.testkit.factories import make_attendance, make_company, make_employee, make_user

from ..models import EmployeeDevice


@override_settings(TIME_ZONE="Asia/Manila")
class WorkspaceSummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Summary company")
        cls.reviewer = make_user("summary-reviewer")
        make_employee(company=company, email=cls.reviewer.email, user=cls.reviewer)
        cls.reviewer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="attendance", codename="view_attendance"
            )
        )
        cls.employee_user = make_user("summary-employee")
        cls.employee = make_employee(
            company=company,
            email=cls.employee_user.email,
            user=cls.employee_user,
            first_name="Summary staff",
        )
        elsewhere = make_company("Other summary company", hq=False)
        cls.other = make_employee(
            company=elsewhere, email="elsewhere@example.test", first_name="Outside scope"
        )
        cls.day = timezone.localdate() - timedelta(days=4)
        for offset in range(5):
            name = (cls.day + timedelta(days=offset)).strftime("%A").lower()
            EmployeeShiftDay.objects.get_or_create(day=name)

        short = Attendance.objects.create(
            employee_id=cls.employee,
            attendance_date=cls.day,
            attendance_clock_in_date=cls.day,
            attendance_clock_in="09:00",
            attendance_clock_out_date=cls.day,
            attendance_clock_out="16:00",
            attendance_worked_hour="07:00",
            minimum_hour="08:00",
        )
        AttendanceLateComeEarlyOut.objects.get_or_create(
            attendance_id=short, employee_id=cls.employee, type="late_come"
        )
        overtime = make_attendance(
            employee=cls.employee,
            attendance_date=cls.day + timedelta(days=1),
            overtime_second=3600,
        )
        # The report must also handle older rows with only the HH:MM values.
        Attendance.objects.filter(pk=overtime.pk).update(
            at_work_second=None, overtime_second=None
        )
        WorkRecords.objects.create(
            employee_id=cls.employee,
            date=cls.day + timedelta(days=2),
            work_record_type="ABS",
            note="Absence recorded",
        )
        make_attendance(
            employee=cls.employee, attendance_date=cls.day + timedelta(days=3)
        )
        make_attendance(employee=cls.other, attendance_date=cls.day)
        report_time = timezone.now()
        EmployeeDevice.objects.create(
            employee=cls.employee,
            device_id="scope-1",
            pending_punches=2,
            queue_observed_at=report_time,
            queue_reported_at=report_time,
        )
        EmployeeDevice.objects.create(
            employee=cls.other,
            device_id="scope-2",
            pending_punches=10,
            queue_observed_at=report_time,
            queue_reported_at=report_time,
        )

    def summary(self):
        return self.client.get(
            reverse("klockin-attendance"),
            {"report": "summary", "start": self.day, "end": self.day + timedelta(days=2)},
        )

    def test_company_summary_aggregates_recorded_time_and_scopes_headcount(self):
        self.client.force_login(self.reviewer)
        response = self.summary()
        self.assertContains(response, "Recorded work")
        self.assertEqual(response.context["metrics"]["Total employees"], 2)
        self.assertEqual(response.context["metrics"]["Last reported pending"], 2)
        self.assertNotContains(response, "Outside scope")
        rows = {row["employee"].pk: row for row in response.context["summary_rows"]}
        self.assertEqual(len(rows), 2)
        summary = rows[self.employee.pk]
        self.assertEqual((summary["present"], summary["absent"], summary["late"]), (2, 1, 1))
        self.assertEqual(
            (summary["worked"], summary["undertime"], summary["overtime"]),
            ("16:00", "01:00", "01:00"),
        )

    def test_employee_report_contains_only_their_aggregate(self):
        self.client.force_login(self.employee_user)
        response = self.summary()
        self.assertContains(response, "Summary staff")
        self.assertNotContains(response, "Total employees")
        self.assertEqual(
            [row["employee"].pk for row in response.context["summary_rows"]],
            [self.employee.pk],
        )

    def test_unsynced_report_includes_only_the_scoped_devices(self):
        self.client.force_login(self.reviewer)
        day = timezone.localdate()
        response = self.client.get(
            reverse("klockin-attendance"),
            {"report": "unsynced", "start": day, "end": day},
        )
        self.assertContains(response, "Counts reflect each device")
        self.assertEqual(
            [(binding.employee_id, binding.pending_punches) for binding in response.context["page"]],
            [(self.employee.pk, 2)],
        )
