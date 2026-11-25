from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from attendance.models import Attendance, AttendanceActivity, AttendanceGeneralSetting
from attendance.views.clock_in_out import clock_in, clock_out_attendance_and_activity
from base.models import EmployeeShiftDay
from geofencing.models import GeoFencing

from ..models import AttendancePunch, EmployeeDevice
from .test_ingestion import IngestionFixture, _online, _payload, _selfie


class BrowserPunchTests(IngestionFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.clock = datetime(2026, 10, 5, 8, tzinfo=ZoneInfo("Asia/Manila"))
        self.url = reverse("klockin-web-punch")
        self.user.is_new_employee = False
        self.user.save(update_fields=["is_new_employee"])
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = str(self.company.pk)
        session.save()
        AttendanceGeneralSetting.objects.create(
            company_id=self.company, enable_check_in=True
        )

    def submit(self, action="in", clock=None, uuid=None, client=None, **overrides):
        form = {
            "action": action,
            "punch_uuid": uuid or str(uuid4()),
            "latitude": "14.599500",
            "longitude": "120.984200",
            "selfie": SimpleUploadedFile(
                "web.jpg", _selfie(), content_type="image/jpeg"
            ),
            **overrides,
        }
        with patch(
            "klockin_attendance.web_punch.timezone.now",
            return_value=clock or self.clock,
        ):
            return (client or self.client).post(self.url, form)

    def test_web_evidence_and_mobile_clockout_share_one_interval(self):
        sent = self.submit()
        self.assertEqual(sent.status_code, 201, sent.content)
        self.assertTrue(sent.json()["ok"])
        event = AttendancePunch.objects.get()
        self.assertEqual(event.source, AttendancePunch.Source.WEB)
        self.assertIsNone(event.device_punched_at)
        self.assertEqual(event.punched_at, self.clock)
        self.assertFalse(EmployeeDevice.objects.exists())
        with event.punch_selfie.open("rb") as photo:
            self.assertEqual(photo.read(), _selfie())

        clock_out = self.clock + timedelta(hours=8)
        with patch("klockin_attendance.views.timezone.now", return_value=clock_out):
            response = _online(self.api, _payload(punch_type="CLOCK_OUT"))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(AttendanceActivity.objects.count(), 1)
        event.refresh_from_db()
        self.assertEqual(event.activity.out_datetime, clock_out)
        self.assertEqual(Attendance.objects.get().attendance_worked_hour, "08:00")
        self.assertEqual(EmployeeDevice.objects.get().device_id, "installation-123")

    def test_browser_replay_remains_idempotent_across_server_times(self):
        uuid = str(uuid4())
        self.assertEqual(self.submit(uuid=uuid).status_code, 201)
        replay = self.submit(uuid=uuid, clock=self.clock + timedelta(minutes=10))
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(AttendancePunch.objects.count(), 1)
        self.assertEqual(AttendanceActivity.objects.count(), 1)
        conflict = self.submit(uuid=uuid, latitude="14.600000")
        self.assertEqual(conflict.status_code, 409)

    def test_evidence_and_session_request_are_required(self):
        anonymous = APIClient()
        self.assertEqual(self.submit(client=anonymous).status_code, 403)
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(self.submit(client=csrf_client).status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.submit(selfie="").status_code, 400)
        self.assertEqual(self.submit("out").status_code, 409)
        legacy = RequestFactory().get(reverse("clock-in"), HTTP_HX_REQUEST="true")
        legacy.user = self.user
        legacy.session = {}
        self.assertEqual(clock_in(legacy).status_code, 410)
        self.assertFalse(AttendancePunch.objects.exists())
        self.assertFalse(AttendanceActivity.objects.exists())

    def test_company_geofence_applies_to_browser(self):
        GeoFencing.objects.create(
            company_id=self.company,
            latitude=10,
            longitude=100,
            radius_in_meters=100,
            start=True,
        )
        self.assertEqual(self.submit().status_code, 403)
        self.assertFalse(AttendancePunch.objects.exists())

    def test_company_allowlist_applies_in_the_all_companies_session(self):
        from base.models import AttendanceAllowedIP

        AttendanceAllowedIP.objects.create(
            company_id=self.company, is_enabled=True,
            additional_data={"allowed_ips": ["192.0.2.8"]},
        )
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

        response = self.submit()
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["code"], "unauthorized_network")
        self.assertFalse(AttendancePunch.objects.exists())

    def test_previous_day_open_activity_does_not_hide_current_checkin(self):
        from ..web_punch import browser_punch_direction

        yesterday = self.clock - timedelta(days=1)
        activity_day = EmployeeShiftDay.objects.get(day="sunday")
        AttendanceActivity.objects.create(
            employee_id=self.employee, shift_day=activity_day, attendance_date=yesterday.date(),
            clock_in_date=yesterday.date(), clock_in="08:00", in_datetime=yesterday,
        )
        request = RequestFactory().get("/")
        request.user = self.user
        request.session = {"selected_company": str(self.company.pk)}
        with patch("klockin_attendance.web_punch.timezone.now", return_value=self.clock):
            self.assertEqual(browser_punch_direction(request), "in")
        self.assertEqual(self.submit().status_code, 201)

    def test_existing_legacy_interval_closes_without_reprojecting_history(self):
        day = EmployeeShiftDay.objects.get(day="monday")
        record = Attendance.objects.create(
            employee_id=self.employee,
            attendance_day=day,
            attendance_date=self.clock.date(),
            attendance_clock_in_date=self.clock.date(),
            attendance_clock_in="08:00",
        )
        activity = AttendanceActivity.objects.create(
            employee_id=self.employee,
            shift_day=day,
            attendance_date=self.clock.date(),
            clock_in_date=self.clock.date(),
            clock_in="08:00",
            in_datetime=self.clock,
        )
        response = self.submit("out", clock=self.clock + timedelta(hours=8))
        self.assertEqual(response.status_code, 201, response.content)
        event = AttendancePunch.objects.get()
        self.assertFalse(event.projectable)
        self.assertEqual(event.attendance_id, record.pk)
        self.assertEqual(event.activity_id, activity.pk)
        self.assertEqual(Attendance.objects.get().attendance_worked_hour, "08:00")

        response = self.submit("in", clock=self.clock + timedelta(hours=8, minutes=10))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(AttendanceActivity.objects.count(), 2)
        activity.refresh_from_db()
        self.assertEqual(activity.out_datetime, self.clock + timedelta(hours=8))

    def test_browser_can_continue_after_a_trusted_nonbrowser_checkout(self):
        self.assertEqual(self.submit().status_code, 201)
        first_checkout = self.clock + timedelta(hours=4)
        clock_out_attendance_and_activity(self.employee, self.clock.date(), "12:00", first_checkout)

        later_clock_in = self.submit(clock=first_checkout + timedelta(minutes=15))
        self.assertEqual(later_clock_in.status_code, 201, later_clock_in.content)
        later_clock_out = self.submit("out", clock=self.clock + timedelta(hours=8))
        self.assertEqual(later_clock_out.status_code, 201, later_clock_out.content)
        self.assertEqual(AttendanceActivity.objects.count(), 2)
        self.assertEqual(Attendance.objects.get().attendance_worked_hour, "07:45")
        first = AttendanceActivity.objects.order_by("in_datetime").first()
        self.assertEqual(first.out_datetime, first_checkout)
