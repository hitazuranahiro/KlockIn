from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from attendance.models import Attendance

from ..models import AttendancePolicy
from ..policies import FIRST_LAST, PAIRED
from .test_ingestion import BATCH_URL, IngestionFixture, _offline, _payload


class MobileAttendancePolicyTests(IngestionFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.zone = ZoneInfo("Asia/Manila")
        self.workday = timezone.now().astimezone(self.zone).date() - timedelta(days=1)

    def sync(self, *punches):
        payload = [
            _offline(_payload(
                punch_type=punch_type,
                punched_at=datetime.combine(self.workday, clock, tzinfo=self.zone).isoformat(),
            ))
            for punch_type, clock in punches
        ]
        result = self.api.post(BATCH_URL, payload, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual([item["status"] for item in result.data["results"]], [201] * len(payload), result.data)

    def test_first_and_last_can_count_the_whole_span(self):
        AttendancePolicy.objects.create(company=self.company, mode=FIRST_LAST)
        self.sync(("CLOCK_IN", time(7, 58)), ("CLOCK_OUT", time(12, 1)),
                  ("CLOCK_IN", time(12, 59)), ("CLOCK_OUT", time(17, 8)))
        row = Attendance.objects.get(employee_id=self.employee, attendance_date=self.workday)
        self.assertEqual(row.attendance_clock_in.replace(tzinfo=None), time(7, 58))
        self.assertEqual(row.attendance_clock_out.replace(tzinfo=None), time(17, 8))
        self.assertEqual(row.attendance_worked_hour, "09:10")

    def test_break_policy_is_snapshotted_and_subtracts_only_overlap(self):
        policy = AttendancePolicy.objects.create(
            company=self.company, mode=FIRST_LAST, break_start=time(12), break_end=time(13),
        )
        self.sync(("CLOCK_IN", time(8)), ("CLOCK_OUT", time(10)))
        policy.mode = PAIRED
        policy.break_start = policy.break_end = None
        policy.save()
        self.sync(("CLOCK_IN", time(11)), ("CLOCK_OUT", time(17)))
        row = Attendance.objects.get(employee_id=self.employee, attendance_date=self.workday)
        self.assertEqual(row.attendance_worked_hour, "08:00")
        self.assertEqual(row.mobile_policy.mode, FIRST_LAST)
        self.assertEqual(row.mobile_policy.break_end, time(13))

    def test_break_is_optional_but_both_times_are_required_if_used(self):
        policy = AttendancePolicy(company=self.company, break_start=time(12))
        with self.assertRaises(ValidationError):
            policy.full_clean()
