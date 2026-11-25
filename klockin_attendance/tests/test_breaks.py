from datetime import datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import Client, TestCase, override_settings

from attendance.models import Attendance

from ..models import AttendanceBreak, AttendancePolicy
from .test_ingestion import BATCH_URL, IngestionFixture, _offline, _payload


MOBILE_BREAK_URL = "/api/v1/mobile/break/"
MOBILE_HOME_URL = "/api/v1/mobile/home/"
WEB_BREAK_URL = "/timekeeping/break/"


def local(hour, minute=0):
    return datetime(2026, 3, 10, hour, minute, tzinfo=ZoneInfo("Asia/Manila"))


@override_settings(TIME_ZONE="Asia/Manila")
class BreakTests(IngestionFixture, TestCase):
    def punch(self, punch_type, at):
        payload = _offline(_payload(punch_type=punch_type, punched_at=at.isoformat()))
        response = self.api.post(BATCH_URL, [payload], format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"][0]["status"], 201, response.data)

    def action(self, action, at):
        with patch("django.utils.timezone.now", return_value=at):
            return self.api.post(MOBILE_BREAK_URL, {"action": action}, format="json")

    def test_opt_in_and_clock_in_are_required_to_start(self):
        self.assertEqual(self.client.get(WEB_BREAK_URL).status_code, 401)
        self.assertEqual(self.api.get(MOBILE_BREAK_URL).status_code, 200)
        self.assertFalse(self.api.get(MOBILE_BREAK_URL).data["enabled"])
        self.punch("CLOCK_IN", local(8))
        self.assertEqual(self.action("start", local(12)).status_code, 409)
        AttendancePolicy.objects.create(company=self.company, break_allowance_minutes=30)
        self.assertEqual(self.action("invalid", local(12)).status_code, 400)
        self.punch("CLOCK_OUT", local(11))
        self.assertEqual(self.action("start", local(12)).status_code, 409)
        self.assertFalse(AttendanceBreak.objects.exists())

    def test_shared_actions_require_csrf_and_keep_overage(self):
        AttendancePolicy.objects.create(company=self.company, break_allowance_minutes=15)
        self.punch("CLOCK_IN", local(8))
        started = self.action("start", local(12))
        self.assertEqual(started.status_code, 200, started.data)
        self.assertIsNotNone(started.data["active_since"])
        self.assertFalse(started.data["can_start"])
        self.assertEqual(self.action("start", local(12, 5)).status_code, 409)

        web = Client(enforce_csrf_checks=True)
        web.force_login(self.user)
        with patch("django.utils.timezone.now", return_value=local(12, 20)):
            status = web.get(WEB_BREAK_URL)
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["used_seconds"], 1200)
            self.assertEqual(status.json()["remaining_seconds"], 0)
            rejected = web.post(WEB_BREAK_URL, {"action": "end"}, content_type="application/json")
            self.assertEqual(rejected.status_code, 403)
            ended = web.post(
                WEB_BREAK_URL, {"action": "end"}, content_type="application/json",
                headers={"X-CSRFToken": status.cookies["csrftoken"].value},
            )
        self.assertEqual(ended.status_code, 200, ended.content)
        self.assertEqual(ended.json()["used_seconds"], 1200)
        self.assertIsNone(ended.json()["active_since"])
        self.assertEqual(self.action("start", local(12, 21)).status_code, 409)
        self.assertEqual(self.action("end", local(12, 21)).status_code, 409)

    def test_end_still_works_when_company_disables_tracking(self):
        policy = AttendancePolicy.objects.create(company=self.company, break_allowance_minutes=20)
        self.punch("CLOCK_IN", local(8))
        self.assertEqual(self.action("start", local(12)).status_code, 200)
        policy.break_allowance_minutes = None
        policy.save()
        ended = self.action("end", local(12, 10))
        self.assertEqual(ended.status_code, 200, ended.data)
        self.assertFalse(ended.data["enabled"])
        self.assertEqual(ended.data["used_seconds"], 600)

    def test_home_and_checkout_merge_scheduled_and_tracked_breaks(self):
        AttendancePolicy.objects.create(
            company=self.company, break_allowance_minutes=60,
            break_start=time(12), break_end=time(13),
        )
        self.punch("CLOCK_IN", local(8))
        self.assertEqual(self.action("start", local(12, 45)).status_code, 200)
        with patch("django.utils.timezone.now", return_value=local(13, 15)):
            home = self.api.get(MOBILE_HOME_URL).data
        self.assertEqual(home["break_policy"]["used_seconds"], 1800)
        self.assertTrue(home["punch"]["is_clocked_in"])
        self.assertEqual(home["today"]["break"], "01:15:00")
        self.assertEqual(home["today"]["worked"], "04:00:00")

        self.punch("CLOCK_OUT", local(13, 15))
        tracked_break = AttendanceBreak.objects.get()
        self.assertEqual(tracked_break.ended_at, local(13, 15))
        day = Attendance.objects.get(employee_id=self.employee)
        self.assertEqual(day.attendance_worked_hour, "04:00")
        self.assertEqual(day.at_work_second, 14400)

    def test_earlier_offline_checkout_cannot_leave_a_negative_break(self):
        AttendancePolicy.objects.create(company=self.company, break_allowance_minutes=30)
        self.punch("CLOCK_IN", local(8))
        self.assertEqual(self.action("start", local(12)).status_code, 200)
        self.punch("CLOCK_OUT", local(11))
        tracked_break = AttendanceBreak.objects.get()
        self.assertEqual(tracked_break.ended_at, tracked_break.started_at)
        self.assertEqual(Attendance.objects.get(employee_id=self.employee).attendance_worked_hour, "03:00")
