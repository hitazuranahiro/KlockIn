from datetime import time, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from attendance.models import Attendance, AttendanceActivity
from base.models import EmployeeShift, EmployeeShiftDay, EmployeeShiftSchedule
from klockin.testkit.factories import (
    make_attendance,
    make_company,
    make_employee,
    make_user,
)

from ..models import AttendancePunch, PunchReview
from ..projection import CORRECTION_PREFIX, project_punch


@override_settings(TIME_ZONE="Asia/Manila")
class DailyTimeRecordTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company()
        cls.admin = make_user("dtr-admin", is_superuser=True)
        make_employee(company=company, email="admin@example.test", user=cls.admin)
        cls.employee_user = make_user("dtr-employee")
        cls.employee = make_employee(
            company=company, email="timekeeper@example.test", user=cls.employee_user
        )
        cls.day = timezone.localdate() - timedelta(days=3)
        for name in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ):
            EmployeeShiftDay.objects.get_or_create(day=name)

    def add_punch(self, punch_type, hour, *, day=None):
        punch = AttendancePunch.objects.create(
            punch_uuid=uuid4(),
            employee=self.employee,
            punch_type=punch_type,
            punched_at=timezone.make_aware(
                timezone.datetime.combine(day or self.day, time(hour))
            ),
            device_id="dtr-test-installation",
            punch_selfie="punches/evidence.jpg",
            gps_lat="14.599512",
            gps_long="120.984222",
            source=AttendancePunch.Source.OFFLINE,
            sync_status=AttendancePunch.SyncStatus.SYNCED,
            server_receive_timestamp=timezone.now(),
            request_digest="a" * 64,
        )
        return punch, project_punch(punch)

    def test_checkout_arriving_first_reconciles_when_checkin_arrives(self):
        out, result = self.add_punch(AttendancePunch.PunchType.CLOCK_OUT, 17)
        self.assertIsNone(result)
        _, attendance = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 9)
        out.refresh_from_db()
        self.assertEqual(out.attendance_id, attendance.pk)
        self.assertEqual(attendance.attendance_worked_hour, "08:00")
        self.assertEqual(attendance.attendance_clock_out, time(17))
        self.assertEqual(
            AttendanceActivity.objects.filter(employee_id=self.employee).count(), 1
        )

    def test_overnight_checkout_links_previous_scheduled_day(self):
        shift = EmployeeShift.objects.create(employee_shift="Night")
        self.employee.employee_work_info.shift_id = shift
        self.employee.employee_work_info.save(update_fields=["shift_id"])
        shift_day = EmployeeShiftDay.objects.get(day=self.day.strftime("%A").lower())
        EmployeeShiftSchedule.objects.create(
            shift_id=shift,
            day=shift_day,
            start_time=time(22),
            end_time=time(6),
            minimum_working_hour="08:00",
        )
        self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 22)
        _, attendance = self.add_punch(
            AttendancePunch.PunchType.CLOCK_OUT, 6, day=self.day + timedelta(days=1)
        )
        self.assertEqual(attendance.attendance_date, self.day)
        self.assertEqual(attendance.attendance_worked_hour, "08:00")
        self.assertEqual(
            attendance.attendance_clock_out_date, self.day + timedelta(days=1)
        )

    def test_manual_correction_stores_reason_and_protects_day(self):
        self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 9)
        _, attendance = self.add_punch(AttendancePunch.PunchType.CLOCK_OUT, 17)
        self.client.force_login(self.admin)
        url = reverse("klockin-attendance-detail", args=[attendance.pk])
        correction = {"clock_in": "09:30", "clock_out": "17:00", "worked_minutes": 450}
        self.assertEqual(self.client.post(url, correction).status_code, 200)
        response = self.client.post(
            url, {**correction, "reason": "Supervisor verified arrival"}
        )
        self.assertEqual(response.status_code, 302)
        attendance.refresh_from_db()
        self.assertEqual(attendance.attendance_clock_in, time(9, 30))
        history = attendance.history.latest()
        self.assertEqual(
            history.history_change_reason,
            CORRECTION_PREFIX + "Supervisor verified arrival",
        )
        self.assertEqual(history.history_user, self.admin)
        _, result = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 18)
        self.assertIsNone(result)
        self.assertEqual(
            Attendance.objects.get(pk=attendance.pk).attendance_clock_in, time(9, 30)
        )

    def test_review_links_evidence_without_overwriting_attendance_or_projection(self):
        _, attendance = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 9)
        punch, result = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 18)
        self.assertIsNone(result)
        self.client.force_login(self.admin)
        review_url = reverse("klockin-punch-review", args=[punch.pk])
        workspace = reverse("klockin-attendance")
        filters = {"start": self.day, "end": self.day, "report": "pending"}
        self.assertContains(self.client.get(workspace, filters), review_url)
        self.assertContains(self.client.get(review_url), "Link evidence")
        self.assertContains(
            self.client.post(review_url, {"attendance": attendance.pk}),
            "This field is required.",
        )
        self.assertFalse(PunchReview.objects.exists())

        reason = "Supervisor confirmed the second photo is supplementary"
        response = self.client.post(
            review_url, {"attendance": attendance.pk, "reason": reason}, follow=True
        )
        self.assertContains(response, "Supplementary mobile evidence")
        self.assertContains(response, reason)
        self.assertContains(response, self.admin.get_username())
        review = PunchReview.objects.get(punch=punch)
        self.assertEqual(review.attendance_id, attendance.pk)
        self.assertEqual(review.attendance_reference, attendance.pk)
        self.assertEqual(review.attendance_date, self.day)
        self.assertEqual(review.reviewed_by_id, self.admin.pk)
        self.assertEqual(review.reason, reason)
        self.assertIsNone(AttendancePunch.objects.get(pk=punch.pk).attendance_id)
        self.assertNotContains(self.client.get(workspace, filters), review_url)
        self.assertContains(self.client.get(review_url), reason)

        self.client.post(
            review_url, {"attendance": attendance.pk, "reason": "Replacement reason"}
        )
        self.assertEqual(PunchReview.objects.get(punch=punch).reason, reason)
        _, projected = self.add_punch(AttendancePunch.PunchType.CLOCK_OUT, 17)
        self.assertEqual(projected.pk, attendance.pk)
        self.assertEqual(projected.attendance_worked_hour, "08:00")
        self.assertEqual(projected.attendance_clock_out, time(17))
        punch.refresh_from_db()
        self.assertIsNone(punch.attendance_id)
        self.assertIsNone(punch.activity_id)

    def test_review_perm_and_target_scope(self):
        _, target = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 9)
        punch, _ = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 10)
        review_url = reverse("klockin-punch-review", args=[punch.pk])
        reason = "Supervisor reviewed mobile evidence"
        company = self.employee.employee_work_info.company_id
        reviewer = make_user("evidence-reviewer")
        make_employee(company=company, email="evidence@example.test", user=reviewer)
        view, change = (
            Permission.objects.get(content_type__app_label="attendance", codename=name)
            for name in ("view_attendance", "change_attendance")
        )
        evidence_permission = Permission.objects.get(codename="view_punch_evidence")
        reviewer.user_permissions.add(view)
        self.client.force_login(self.employee_user)
        self.assertEqual(self.client.get(review_url).status_code, 403)
        self.client.force_login(reviewer)
        self.assertEqual(self.client.get(review_url).status_code, 403)
        reviewer.user_permissions.add(evidence_permission)
        self.assertContains(
            self.client.get(review_url), "permission to change attendance"
        )
        self.assertEqual(
            self.client.post(
                review_url, {"attendance": target.pk, "reason": reason}
            ).status_code,
            403,
        )

        reviewer.user_permissions.add(change)
        other = make_employee(company=company, email="other-target@example.test")
        other_employee_record = make_attendance(
            employee=other, attendance_date=self.day
        )
        wrong_day = make_attendance(
            employee=self.employee, attendance_date=self.day - timedelta(days=1)
        )
        for invalid in (other_employee_record, wrong_day):
            self.assertContains(
                self.client.post(
                    review_url, {"attendance": invalid.pk, "reason": reason}
                ),
                "Select a valid choice.",
            )
        other_company = make_company("Other evidence company", hq=False)
        outsider = make_user("outside-evidence-reviewer")
        make_employee(company=other_company, email="outside@example.test", user=outsider)
        outsider.user_permissions.add(view, change, evidence_permission)
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(review_url).status_code, 404)
        self.assertEqual(
            self.client.post(
                review_url, {"attendance": target.pk, "reason": reason}
            ).status_code,
            404,
        )
        self.assertFalse(PunchReview.objects.exists())
        self.client.force_login(reviewer)
        response = self.client.post(
            review_url, {"attendance": target.pk, "reason": reason}
        )
        self.assertRedirects(
            response, reverse("klockin-attendance-detail", args=[target.pk])
        )
        self.assertEqual(PunchReview.objects.get(punch=punch).reviewed_by_id, reviewer.pk)

    def test_review_requires_daily_record_and_handles_later_auto_projection(self):
        punch, result = self.add_punch(AttendancePunch.PunchType.CLOCK_OUT, 17)
        self.assertIsNone(result)
        self.client.force_login(self.admin)
        review_url = reverse("klockin-punch-review", args=[punch.pk])
        response = self.client.get(review_url)
        self.assertContains(response, "No eligible daily attendance record")
        self.assertContains(response, reverse("attendance-view"))

        _, attendance = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 9)
        response = self.client.post(
            review_url,
            {"attendance": attendance.pk, "reason": "An outdated review was open"},
            follow=True,
        )
        self.assertContains(response, "Punch applied to attendance")
        self.assertFalse(PunchReview.objects.exists())

    def test_review_accepts_prior_day_for_overnight_shift(self):
        shift = EmployeeShift.objects.create(employee_shift="Night review")
        self.employee.employee_work_info.shift_id = shift
        self.employee.employee_work_info.save(update_fields=["shift_id"])
        shift_day = EmployeeShiftDay.objects.get(day=self.day.strftime("%A").lower())
        EmployeeShiftSchedule.objects.create(
            shift_id=shift,
            day=shift_day,
            start_time=time(22),
            end_time=time(6),
            minimum_working_hour="08:00",
        )
        _, attendance = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 22)
        punch, result = self.add_punch(
            AttendancePunch.PunchType.CLOCK_IN, 1, day=self.day + timedelta(days=1)
        )
        self.assertIsNone(result)
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("klockin-punch-review", args=[punch.pk]),
            {"attendance": attendance.pk, "reason": "Evidence from the overnight shift"},
        )
        self.assertRedirects(
            response, reverse("klockin-attendance-detail", args=[attendance.pk])
        )
        self.assertEqual(PunchReview.objects.get(punch=punch).attendance_date, self.day)

    def test_workspace_pdf_and_employee_selfie_access(self):
        punch, _ = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 9)
        self.add_punch(AttendancePunch.PunchType.CLOCK_OUT, 17)
        self.client.force_login(self.employee_user)
        response = self.client.get(
            reverse("klockin-attendance"),
            {
                "start": self.day,
                "end": self.day,
            },
        )
        self.assertContains(response, "Timekeeping")
        self.assertContains(response, "08:00")
        response = self.client.get(
            reverse("klockin-monthly-dtr", args=[self.employee.pk]),
            {
                "month": self.day.strftime("%Y-%m"),
            },
        )
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))
        response = self.client.get(reverse("klockin-punch-selfie", args=[punch.pk]))
        self.assertEqual(response.status_code, 403)

    def test_selfie_only_served_to_same_company_reviewer(self):
        punch, _ = self.add_punch(AttendancePunch.PunchType.CLOCK_IN, 9)
        reviewer_permission = Permission.objects.get(
            content_type__app_label="attendance", codename="view_attendance"
        )
        evidence_permission = Permission.objects.get(codename="view_punch_evidence")
        company = self.employee.employee_work_info.company_id
        reviewer = make_user("same-company-reviewer")
        make_employee(company=company, email="reviewer@example.test", user=reviewer)
        reviewer.user_permissions.add(reviewer_permission, evidence_permission)
        other_reviewer = make_user("other-company-reviewer")
        other_company = make_company("Other company", hq=False)
        make_employee(
            company=other_company,
            email="other-reviewer@example.test",
            user=other_reviewer,
        )
        other_reviewer.user_permissions.add(reviewer_permission, evidence_permission)

        photo = BytesIO()
        Image.new("RGB", (8, 8), "blue").save(photo, format="JPEG")
        evidence = photo.getvalue()
        url = reverse("klockin-punch-selfie", args=[punch.pk])
        with TemporaryDirectory() as root, override_settings(KLOCKIN_SELFIE_ROOT=root):
            punch.punch_selfie.save("punch.jpg", ContentFile(evidence))
            self.client.force_login(reviewer)
            response = self.client.get(url)
            self.assertEqual(response["Content-Type"], "image/jpeg")
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(b"".join(response.streaming_content), evidence)
            self.client.force_login(other_reviewer)
            self.assertEqual(self.client.get(url).status_code, 404)
