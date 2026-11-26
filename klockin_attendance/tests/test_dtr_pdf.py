from datetime import time, timedelta

import pymupdf
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from attendance.corrections import CORRECTION_PREFIX, MISSED_PUNCH_CORRECTION_PREFIX
from attendance.models import Attendance, AttendanceActivity
from base.models import EmployeeShiftDay
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
