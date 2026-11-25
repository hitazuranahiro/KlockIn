import json
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from attendance.corrections import CORRECTION_PREFIX
from attendance.forms import AttendanceUpdateForm
from attendance.models import Attendance, AttendanceActivity
from base.models import EmployeeShift, EmployeeShiftDay
from klockin.testkit import make_company, make_employee, make_user


class AttendanceCorrectionAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Attendance audit")
        cls.actor = make_user("attendance-auditor", is_superuser=True)
        make_employee(company=company, email="actor@example.test", user=cls.actor)
        cls.shift = EmployeeShift.objects.create(employee_shift="Audit shift")
        cls.employee = make_employee(
            company=company, email="record@example.test", shift=cls.shift
        )
        cls.day = timezone.localdate() - timedelta(days=10)
        for offset in range(3):
            workday = cls.day + timedelta(days=offset)
            EmployeeShiftDay.objects.get_or_create(day=workday.strftime("%A").lower())

    def attendance(self, day=None, **fields):
        day = day or self.day
        return Attendance.objects.create(
            employee_id=self.employee,
            shift_id=self.shift,
            attendance_date=day,
            attendance_clock_in_date=day,
            attendance_clock_in=time(9),
            minimum_hour="08:00",
            **fields,
        )

    def correction_payload(self, clock_in="09:30"):
        return {
            "employee_id": self.employee.pk,
            "shift_id": self.shift.pk,
            "attendance_date": self.day.isoformat(),
            "attendance_clock_in_date": self.day.isoformat(),
            "attendance_clock_in": clock_in,
            "attendance_clock_out_date": self.day.isoformat(),
            "attendance_clock_out": "17:00",
            "attendance_worked_hour": "07:30",
            "minimum_hour": "08:00",
        }

    def assert_correction(self, record, field, old, new, reason):
        after, before = record.history.order_by("-history_date", "-pk")[:2]
        self.assertEqual(after.history_user_id, self.actor.pk)
        self.assertEqual(after.history_change_reason, CORRECTION_PREFIX + reason)
        self.assertEqual(getattr(before, field), old)
        self.assertEqual(getattr(after, field), new)

    def test_legacy_edit_requires_a_reason_and_preserves_the_current_preimage(self):
        attendance = self.attendance()
        Attendance.objects.filter(pk=attendance.pk).update(
            attendance_clock_in=time(9, 5)
        )
        self.client.force_login(self.actor)
        url = reverse("attendance-update", args=[attendance.pk])
        headers = {"HX-Request": "true"}
        self.assertContains(
            self.client.get(url, headers=headers), 'name="correction_reason"'
        )
        response = self.client.post(url, self.correction_payload(), headers=headers)
        self.assertContains(response, "This field is required.")
        attendance.refresh_from_db()
        self.assertEqual(attendance.attendance_clock_in, time(9, 5))

        reason = "Verified with signed supervisor statement. " * 4
        response = self.client.post(
            url,
            {**self.correction_payload(), "correction_reason": reason.strip()},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        attendance.refresh_from_db()
        self.assertEqual(attendance.attendance_clock_in, time(9, 30))
        self.assert_correction(
            attendance, "attendance_clock_in", time(9, 5), time(9, 30), reason.strip()
        )

    def test_staff_api_update_requires_a_reason_and_leaves_reads_unchanged(self):
        attendance = self.attendance()
        api = APIClient()
        api.force_authenticate(self.actor)
        url = f"/api/v1/attendance/attendance/{attendance.pk}"
        response = api.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("correction_reason", response.data)
        response = api.put(url, self.correction_payload(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("correction_reason", response.data)
        attendance.refresh_from_db()
        self.assertEqual(attendance.attendance_clock_in, time(9))

        reason = "Verified arrival with the shift supervisor."
        response = api.put(
            url, {**self.correction_payload(), "correction_reason": reason}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("correction_reason", response.data)
        self.assert_correction(
            attendance, "attendance_clock_in", time(9), time(9, 30), reason
        )

    def test_legacy_form_reuse_for_creation_does_not_require_a_correction_reason(self):
        payload = self.correction_payload()
        form = AttendanceUpdateForm(payload)
        self.assertNotIn("correction_reason", form.fields)
        self.assertTrue(form.is_valid(), form.errors)

    def test_approval_routes_record_attendance_and_activity_before_and_after(self):
        self.client.force_login(self.actor)
        api = APIClient()
        api.force_authenticate(self.actor)
        reason = "Employee submitted the supervisor-signed arrival time."
        for index, channel in enumerate(("web", "bulk", "api")):
            with self.subTest(channel=channel):
                day = self.day + timedelta(days=index)
                attendance = self.attendance(
                    day,
                    is_validate_request=True,
                    request_type="update_request",
                    request_description=reason,
                    requested_data=json.dumps(
                        {
                            "attendance_clock_in": "09:20:00",
                            "attendance_clock_out": "None",
                            "attendance_clock_out_date": "None",
                            "shift_id": "None",
                            "work_type_id": "",
                        }
                    ),
                )
                activity = AttendanceActivity.objects.create(
                    employee_id=self.employee,
                    attendance_date=day,
                    clock_in_date=day,
                    clock_in=time(9),
                )
                if channel == "web":
                    response = self.client.post(
                        reverse("approve-validate-attendance-request", args=[attendance.pk])
                    )
                    self.assertEqual(response.status_code, 302)
                elif channel == "bulk":
                    response = self.client.post(
                        reverse("bulk-approve-attendance-request"),
                        {"ids": json.dumps([attendance.pk])},
                    )
                    self.assertEqual(response.status_code, 200)
                else:
                    response = api.put(
                        f"/api/v1/attendance/attendance-request-approve/{attendance.pk}",
                        {},
                        format="json",
                    )
                    self.assertEqual(response.status_code, 200, response.data)

                attendance.refresh_from_db()
                self.assertTrue(attendance.is_validate_request_approved)
                self.assertIsNone(attendance.attendance_clock_out)
                self.assert_correction(
                    attendance, "attendance_clock_in", time(9), time(9, 20), reason
                )
                self.assert_correction(activity, "clock_in", time(9), time(9, 20), reason)

    def test_django_admin_requires_a_reason_on_activity_edit(self):
        shift_day = EmployeeShiftDay.objects.get(day=self.day.strftime("%A").lower())
        activity = AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=self.day,
            shift_day=shift_day,
            clock_in_date=self.day,
            clock_in=time(9),
            clock_out_date=self.day,
            clock_out=time(17),
        )
        self.client.force_login(self.actor)
        url = reverse("admin:attendance_attendanceactivity_change", args=[activity.pk])
        self.assertContains(self.client.get(url), 'name="correction_reason"')
        payload = {
            "employee_id": self.employee.pk,
            "attendance_date": self.day.isoformat(),
            "shift_day": shift_day.pk,
            "in_datetime_0": self.day.isoformat(),
            "in_datetime_1": "09:15:00",
            "clock_in_date": self.day.isoformat(),
            "clock_in": "09:15:00",
            "clock_out_date": self.day.isoformat(),
            "out_datetime_0": self.day.isoformat(),
            "out_datetime_1": "17:00:00",
            "clock_out": "17:00:00",
            "is_active": "on",
        }
        self.assertContains(self.client.post(url, payload), "This field is required.")
        reason = "Supervisor confirmed the clock-in correction."
        response = self.client.post(url, {**payload, "correction_reason": reason})
        if response.status_code != 302:
            self.fail(response.context["adminform"].form.errors.as_text())
        self.assert_correction(activity, "clock_in", time(9), time(9, 15), reason)
