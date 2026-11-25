from datetime import time, timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity
from base.models import EmployeeShiftDay
from klockin.testkit import make_company, make_employee, make_user


class EmployeeAttendanceAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Audit office")
        outside_company = make_company("Other audit office", hq=False)
        cls.subject_user = make_user("audit-subject")
        cls.subject = make_employee(
            company=company, email=cls.subject_user.email, user=cls.subject_user
        )
        cls.reviewer = make_user("audit-reviewer")
        cls.reviewer_employee = make_employee(
            company=company, email=cls.reviewer.email, user=cls.reviewer
        )
        cls.outside_reviewer = make_user("audit-outside-reviewer")
        make_employee(
            company=outside_company, email=cls.outside_reviewer.email, user=cls.outside_reviewer
        )
        can_review = Permission.objects.get(
            content_type__app_label="attendance", codename="view_attendance"
        )
        cls.reviewer.user_permissions.add(can_review)
        cls.outside_reviewer.user_permissions.add(can_review)
        cls.path = reverse("klockin-employee-attendance-audit", args=[cls.subject.pk])
        cls.workday = timezone.localdate() - timedelta(days=2)
        cls.shift_day, _ = EmployeeShiftDay.objects.get_or_create(
            day=cls.workday.strftime("%A").lower()
        )
        cls.initial_time = timezone.now() - timedelta(hours=2)

    def _activity(self):
        entry = AttendanceActivity(
            employee_id=self.subject,
            shift_day=self.shift_day,
            attendance_date=self.workday,
            clock_in_date=self.workday,
            clock_in=time(8),
        )
        entry._history_date = self.initial_time
        entry.save()
        return entry

    def test_daily_and_activity_changes_show_actor_reason_and_before_after(self):
        attendance = Attendance(
            employee_id=self.subject,
            attendance_day=self.shift_day,
            attendance_date=self.workday,
            attendance_clock_in_date=self.workday,
            attendance_clock_in=time(9),
        )
        attendance._history_date = self.initial_time
        attendance.save()
        attendance._history_user = self.reviewer
        attendance._change_reason = "KlockIN correction: Confirmed the employee arrival time."
        attendance._history_date = self.initial_time + timedelta(minutes=2)
        attendance.attendance_clock_in = time(9, 15)
        attendance.save()
        activity = self._activity()
        activity._history_user = self.reviewer
        activity._history_date = self.initial_time + timedelta(minutes=3)
        activity.clock_in = time(8, 5)
        activity.save()
        activity.history.filter(history_type="~").update(history_description="Legacy reason text")

        self.client.force_login(self.reviewer)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertContains(response, "Before")
        self.assertContains(response, "After")
        self.assertContains(response, "Confirmed the employee arrival time.")
        self.assertContains(response, "Legacy reason text")
        activity_event, daily_event = response.context["entries"][:2]
        self.assertEqual(activity_event["source"], "Attendance activity")
        self.assertEqual(daily_event["source"], "Daily attendance")
        self.assertEqual(daily_event["actor"], self.reviewer)
        self.assertEqual(daily_event["timestamp"], attendance._history_date)
        self.assertIn(
            {"field": "Check-In", "before": "09:00:00", "after": "09:15:00"},
            daily_event["changes"],
        )
        self.assertIn(
            {"field": "Check In", "before": "08:00:00", "after": "08:05:00"},
            activity_event["changes"],
        )

    def test_pagination_keeps_off_page_predecessors_and_history_past_31_rows(self):
        activity = self._activity()
        activity._history_user = self.reviewer
        for revision in range(1, 38):
            activity._history_date = self.initial_time + timedelta(minutes=revision)
            activity._change_reason = f"Arrival revision {revision}"
            activity.clock_in = time(8, revision)
            activity.save()

        self.client.force_login(self.reviewer)
        newest = self.client.get(self.path)
        self.assertContains(newest, "Page 1 of 2")
        self.assertEqual(newest.context["page"].paginator.count, 38)
        self.assertContains(newest, "Arrival revision 37")
        self.assertNotContains(newest, "Arrival revision 12")
        boundary = newest.context["entries"][-1]
        self.assertEqual(boundary["reason"], "Arrival revision 13")
        self.assertIn(
            {"field": "Check In", "before": "08:12:00", "after": "08:13:00"},
            boundary["changes"],
        )

        older = self.client.get(self.path, {"page": 2}, HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(older, "klockin_attendance/_employee_audit.html")
        self.assertContains(older, "Page 2 of 2")
        self.assertContains(older, "Arrival revision 12")
        self.assertEqual(older.context["entries"][-1]["action"], "Created")

    def test_deleted_activity_remains_auditable(self):
        activity = self._activity()
        pk = activity.pk
        activity._history_user = self.reviewer
        activity._history_date = self.initial_time + timedelta(minutes=1)
        activity._change_reason = "Duplicate activity removed"
        activity.delete()

        self.client.force_login(self.reviewer)
        response = self.client.get(self.path)
        deletion = response.context["entries"][0]
        self.assertEqual(deletion["action"], "Deleted")
        self.assertEqual(deletion["record_id"], pk)
        self.assertEqual(deletion["reason"], "Duplicate activity removed")
        self.assertIn(
            {"field": "Check In", "before": "08:00:00", "after": "—"},
            deletion["changes"],
        )

    def test_permission_and_company_boundaries(self):
        self.assertEqual(self.client.get(self.path).status_code, 302)
        self.client.force_login(self.subject_user)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.outside_reviewer)
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        self.assertEqual(self.client.post(self.path).status_code, 405)

    def test_staff_profile_tab_exposes_link_only_inside_audit_scope(self):
        tab_path = reverse(
            "hzp-profile-tab", args=["employeeprofileview-Attendance", self.subject.pk]
        )
        for actor, allowed in ((self.reviewer, True), (self.subject_user, False)):
            with self.subTest(actor=actor):
                self.client.force_login(actor)
                response = self.client.get(tab_path, HTTP_HX_REQUEST="true")
                if allowed:
                    self.assertContains(response, self.path)
                else:
                    self.assertNotContains(response, self.path)

        self.client.force_login(self.reviewer)
        profile = self.client.get(reverse("profile-attendance-tab"), HTTP_HX_REQUEST="true")
        self.assertContains(
            profile,
            reverse("klockin-employee-attendance-audit", args=[self.reviewer_employee.pk]),
        )
