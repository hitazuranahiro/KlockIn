from datetime import time, timedelta
from io import BytesIO

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from base.models import CompanyGroupAssignment
from klockin.testkit.factories import make_attendance, make_company, make_employee, make_user
from report.models import ReportRunLog

from ..models import AttendancePunch, EmployeeDevice


class TimekeepingReportExportsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("EDTR report company")
        cls.admin = make_user("timekeeping-report-admin", is_superuser=True)
        make_employee(company=company, email="report-admin@example.test", user=cls.admin)
        cls.viewer = make_user("timekeeping-report-viewer")
        viewer_group = Group.objects.get(name="Attendance Viewer")
        cls.viewer.groups.add(viewer_group)
        CompanyGroupAssignment.objects.create(user=cls.viewer, group=viewer_group, company=company)
        make_employee(company=company, email="report-viewer@example.test", user=cls.viewer)
        cls.day = timezone.localdate()
        cls.employee = make_employee(
            company=company, email="report-employee@example.test", first_name="Alice",
        )
        cls.day_record = make_attendance(
            employee=cls.employee, attendance_date=cls.day, clock_in=time(8), clock_out=time(17),
            at_work_second=9 * 3600,
        )
        captured = timezone.now() - timedelta(minutes=5)
        cls.punch = AttendancePunch.objects.create(
            punch_uuid="5850b2e8-8cee-40e0-a112-58dc42eff213",
            employee=cls.employee,
            attendance=cls.day_record,
            punch_type=AttendancePunch.PunchType.CLOCK_IN,
            punched_at=captured,
            server_receive_timestamp=timezone.now(),
            detected_address="Private report address",
            device_id="private-test-installation-id",
            punch_selfie="punches/private-photo.jpg",
            gps_lat="14.599512",
            gps_long="120.984222",
            source=AttendancePunch.Source.OFFLINE,
        )
        cls.device = EmployeeDevice.objects.create(
            employee=cls.employee, device_id=cls.punch.device_id, pending_punches=2,
            queue_observed_at=captured, queue_reported_at=timezone.now(),
        )
        other_company = make_company("Unrelated report company", hq=False)
        other = make_employee(company=other_company, email="other-report@example.test", first_name="Unrelated")
        EmployeeDevice.objects.create(employee=other, device_id="outside-device", pending_punches=4)

    def test_all_formats_export_same_filtered_device_queue(self):
        self.client.force_login(self.admin)
        url = reverse("klockin-attendance-export")
        filters = {"start": self.day, "end": self.day, "report": "unsynced", "employee": self.employee.pk}
        csv_response = self.client.get(url, {**filters, "format": "csv"})
        self.assertContains(csv_response, "Observed on device")
        self.assertContains(csv_response, self.device.device_fingerprint)
        self.assertNotContains(csv_response, self.device.device_id)
        self.assertNotContains(csv_response, "Unrelated")
        self.assertContains(csv_response, "disconnected")
        workbook = load_workbook(BytesIO(self.client.get(url, {**filters, "format": "xlsx"}).content))
        rows = list(workbook["Data"].values)
        self.assertTrue(any("Device fingerprint" in row for row in rows))
        self.assertTrue(any(self.device.device_fingerprint in row for row in rows))
        pdf = self.client.get(url, {**filters, "format": "pdf"})
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        print_view = self.client.get(url, {**filters, "format": "print"})
        self.assertContains(print_view, "Use your browser")
        self.assertContains(print_view, self.device.device_fingerprint)
        self.assertEqual(ReportRunLog.objects.filter(report_slug="timekeeping-unsynced").count(), 4)

    def test_viewer_can_view_own_company_reports_without_private_punch_evidence(self):
        self.client.force_login(self.viewer)
        detail = reverse("klockin-attendance-detail", args=[self.day_record.pk])
        response = self.client.get(detail)
        self.assertContains(response, "Audit history")
        self.assertNotContains(response, "Correct attendance")
        for private in ("Private report address", self.punch.device_id, self.punch.device_fingerprint, "GPS"):
            self.assertNotContains(response, private)
        self.assertEqual(self.client.post(detail, {}).status_code, 403)
        for name in ("klockin-punch-selfie", "klockin-punch-review"):
            self.assertEqual(self.client.get(reverse(name, args=[self.punch.pk])).status_code, 403)
        report = self.client.get(reverse("klockin-attendance-export"), {"report": "unsynced", "start": self.day, "end": self.day})
        self.assertContains(report, "Reported pending")
        self.assertNotContains(report, "Device fingerprint")
        self.assertNotContains(report, self.punch.device_fingerprint)
        self.assertNotContains(report, "Unrelated")
