from datetime import time, timedelta

import pymupdf
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from attendance.corrections import CORRECTION_PREFIX, MISSED_PUNCH_CORRECTION_PREFIX
from attendance.models import Attendance, AttendanceActivity
from base.models import EmployeeShiftDay
from klockin.export_preferences import save_export_preferences
from klockin.testkit import make_company, make_employee, make_user

from ..dtr_pdf import _daily_clocks


class MonthlyDTRPDFTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Monthly DTR export test")
        cls.user = make_user("monthly-dtr-subject")
        cls.employee = make_employee(
            company=company,
            email=cls.user.email,
            first_name="Ana",
            last_name="Reyes",
            user=cls.user,
        )
        stranger = make_user("monthly-dtr-stranger")
        cls.stranger = make_employee(company=company, email=stranger.email, user=stranger)
        cls.day = timezone.localdate().replace(day=1) - timedelta(days=1)
        next_day = cls.day + timedelta(days=1)
        shift_day, _ = EmployeeShiftDay.objects.get_or_create(
            day=cls.day.strftime("%A").lower()
        )
        Attendance.objects.create(
            employee_id=cls.employee,
            attendance_date=cls.day,
            attendance_day=shift_day,
            attendance_clock_in_date=cls.day,
            attendance_clock_in=time(22),
            attendance_clock_out_date=next_day,
            attendance_clock_out=time(6),
            attendance_worked_hour="07:20",
            minimum_hour="08:00",
        )
        AttendanceActivity.objects.create(
            employee_id=cls.employee,
            attendance_date=cls.day,
            clock_in_date=cls.day,
            clock_in=time(22),
            clock_out_date=next_day,
            clock_out=time(0, 40),
        )
        AttendanceActivity.objects.create(
            employee_id=cls.employee,
            attendance_date=cls.day,
            clock_in_date=next_day,
            clock_in=time(1, 20),
            clock_out_date=next_day,
            clock_out=time(6),
        )

    def test_form_48_prints_both_copies_with_actual_hours_and_overnight_marks(self):
        self.client.force_login(self.user)
        layouts = {
            "ampm": ("A.M.", "P.M.", "Arrival", "Departure", "1:20 +1", "6:00 +1"),
            "first-last": ("First In", "Last Out", "10:00 PM", "6:00 AM +1"),
        }
        for layout, labels in layouts.items():
            with self.subTest(layout=layout):
                response = self.client.get(
                    reverse("klockin-monthly-dtr", args=[self.employee.pk]),
                    {"month": self.day.strftime("%Y-%m"), "layout": layout},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertIn("no-store", response["Cache-Control"])
                self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
                with pymupdf.open(stream=b"".join(response.streaming_content)) as report:
                    self.assertEqual(report.page_count, 1)
                    self.assertEqual(report.metadata["author"], "Tomeku")
                    page = report[0]
                    width, height = page.rect.width, page.rect.height
                    for left, right in ((0, width / 2), (width / 2, width)):
                        text = page.get_text(clip=pymupdf.Rect(left, 0, right, height))
                        self.assertEqual(text.count("DAILY TIME RECORD"), 1)
                        for value in (
                            "CS Form No. 48 style",
                            "Ana",
                            "Reyes",
                            self.day.strftime("%B %Y"),
                            "UNDERTIME",
                            "TOTAL",
                            "Employee Signature",
                            "In-Charge",
                            "+1 means next day",
                            *labels,
                        ):
                            self.assertIn(value, text)
                        self.assertEqual(text.split().count("40"), 2)

    def test_landscape_preview_with_saved_note_and_optional_columns(self):
        self.client.force_login(self.user)
        url = reverse("klockin-monthly-dtr", args=[self.employee.pk])
        note = "Reviewed by Timekeeping. " + "Wide monthly export notes remain readable on the page. " * 2
        save_export_preferences(self.user, {"dtr": {"note": note, "orientation": "landscape"}})

        query = {
            "month": self.day.strftime("%Y-%m"),
            "layout": "first-last",
            "show_company": "0",
            "show_undertime": "0",
            "preview": "1",
            "note": "Literal GET override must not appear",
        }
        response = self.client.get(url, query)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("no-store", response["Cache-Control"])
        with pymupdf.open(stream=b"".join(response.streaming_content)) as report:
            self.assertEqual(report.page_count, 1)
            page = report[0]
            self.assertGreater(page.rect.width, page.rect.height)
            text = page.get_text()
            self.assertEqual(text.count("DAILY TIME RECORD"), 1)
            for item in ("10:00 PM", "6:00 AM +1", "Notes: Reviewed by Timekeeping.", "In-Charge"):
                self.assertIn(item, text)
            for item in ("UNDERTIME", "Monthly DTR export test", "Literal GET override"):
                self.assertNotIn(item, text)

        query.update(show_company="1", show_notes="0", show_undertime="1")
        response = self.client.get(url, query)
        with pymupdf.open(stream=b"".join(response.streaming_content)) as report:
            text = report[0].get_text()
            self.assertIn("Monthly DTR export test", text)
            self.assertIn("UNDERTIME", text)
            self.assertNotIn("Notes: Reviewed", text)

    def test_preview_and_configuration_keep_employee_scope(self):
        self.client.force_login(self.user)
        url = reverse("klockin-monthly-dtr", args=[self.stranger.pk])
        for key in ("preview", "configure"):
            self.assertEqual(self.client.get(url, {key: "1"}).status_code, 404)

    def test_mobile_self_export_with_pdf_accept_and_jwt(self):
        path = "/api/v1/mobile/dtr/"
        headers = {"HTTP_ACCEPT": "application/pdf"}
        client = APIClient()
        self.assertEqual(client.get(path, **headers).status_code, 401)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.user).access_token}")
        response = client.get(
            path,
            {
                "month": self.day.strftime("%Y-%m"), "layout": "first-last",
                "preview": "1", "employee_id": self.stranger.pk,
            },
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].endswith(f"{self.employee.pk}-{self.day:%Y-%m}.pdf\""))
        self.assertIn("no-store", response["Cache-Control"])
        with pymupdf.open(stream=b"".join(response.streaming_content)) as report:
            self.assertIn("10:00 PM", report[0].get_text())
        response = client.get(path, {"orientation": "sideways"}, **headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_missed_punch_approval_preserves_activity_times_in_dtr(self):
        row = Attendance.objects.get(employee_id=self.employee, attendance_date=self.day)
        activities = AttendanceActivity.objects.filter(
            employee_id=self.employee, attendance_date=self.day
        ).order_by("clock_in_date", "clock_in")
        row._change_reason = MISSED_PUNCH_CORRECTION_PREFIX + "Missing overnight check-out"
        row.save()

        self.assertEqual(
            _daily_clocks(row, activities, False), ["1:20 +1", "6:00 +1", "10:00", ""]
        )

        row.attendance_clock_in = time(22, 30)
        row._change_reason = CORRECTION_PREFIX + "Supervisor corrected the daily total"
        row.save()

        self.assertEqual(
            _daily_clocks(row, activities, False), ["", "6:00 +1", "10:30", ""]
        )
