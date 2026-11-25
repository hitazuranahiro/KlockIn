"""
The home screen in one request.

Rendering it from the resource endpoints took eight or more round trips on a
cold start (the previous Flutter app made fourteen). These pin the shape the
client binds to, and the one derived value -- break time -- that has no
stored field behind it.
"""

from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from attendance.models import AttendanceActivity
from base.models import EmployeeShift, EmployeeShiftDay, EmployeeShiftSchedule
from klockin.klockin_middlewares import set_selected_company
from klockin.testkit import make_company, make_employee, make_user
from klockin.testkit.factories import make_attendance

HOME_URL = "/api/v1/mobile/home/"

LOCAL_ZONE = ZoneInfo("Asia/Manila")
FIXED_TODAY = date(2026, 3, 10)
CONFIRMED_AT = datetime.combine(FIXED_TODAY, time(15), tzinfo=LOCAL_ZONE)


class _FrozenDate(date):
    @classmethod
    def today(cls):
        return FIXED_TODAY


@override_settings(TIME_ZONE="Asia/Manila")
class MobileHomeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)
        self.company = make_company("Home Co")
        self.user = make_user("home_user")
        self.employee = make_employee(
            company=self.company,
            email="home@test.horilla",
            first_name="Hana",
            user=self.user,
        )
        self.client.force_authenticate(user=self.user)
        clock = patch("klockin_api.api_views.mobile.views.date", _FrozenDate)
        clock.start()
        self.addCleanup(clock.stop)
        confirmation = patch(
            "klockin_api.api_views.mobile.views.timezone.now",
            return_value=CONFIRMED_AT.astimezone(UTC),
        )
        confirmation.start()
        self.addCleanup(confirmation.stop)

    def test_requires_authentication(self):
        self.assertEqual(APIClient().get(HOME_URL).status_code, 401)

    def test_returns_every_block_the_screen_draws(self):
        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        for key in (
            "employee",
            "capabilities",
            "punch",
            "geofence",
            "today",
            "on_leave_today",
            "announcement",
            "unread_notifications",
        ):
            self.assertIn(key, response.data)
        # Embedded so the tab bar needs no extra call.
        self.assertIn("role", response.data["capabilities"])
        self.assertIn("features", response.data["capabilities"])

    def test_clean_slate_is_not_clocked_in(self):
        punch = self.client.get(HOME_URL).data["punch"]
        self.assertFalse(punch["is_clocked_in"])
        self.assertIsNone(punch["clock_in_time"])

    def test_today_contains_authoritative_workday_boundaries_and_timestamp(self):
        today = self.client.get(HOME_URL).data["today"]
        self.assertEqual(today["workday"], "2026-03-10")
        self.assertEqual(today["time_zone"], "Asia/Manila")
        self.assertEqual(today["confirmed_at"], CONFIRMED_AT.isoformat())
        self.assertEqual(today["workday_starts_at"], "2026-03-10T00:00:00+08:00")
        self.assertEqual(today["workday_ends_at"], "2026-03-11T00:00:00+08:00")

    def test_overnight_snapshot_uses_previous_workday_until_noon(self):
        previous = FIXED_TODAY - timedelta(days=1)
        previous_day, _ = EmployeeShiftDay.objects.get_or_create(day="monday")
        shift = EmployeeShift.objects.create(employee_shift="Home Overnight")
        work_info = self.employee.employee_work_info
        work_info.shift_id = shift
        work_info.save(update_fields=["shift_id"])
        EmployeeShiftSchedule.objects.create(
            shift_id=shift, day=previous_day, start_time=time(22), end_time=time(6)
        )
        started_at = datetime.combine(previous, time(22), tzinfo=LOCAL_ZONE)
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=previous,
            clock_in_date=previous,
            clock_in=time(22),
            in_datetime=started_at,
        )
        with patch(
            "klockin_api.api_views.mobile.views.timezone.now",
            return_value=datetime(2026, 3, 9, 21, 30, tzinfo=UTC),
        ):
            early = self.client.get(HOME_URL).data
        self.assertEqual(early["today"]["workday"], previous.isoformat())
        self.assertEqual(early["today"]["confirmed_at"], "2026-03-10T05:30:00+08:00")
        self.assertEqual(early["today"]["workday_ends_at"], "2026-03-10T12:00:00+08:00")
        self.assertEqual(early["today"]["worked"], "07:30:00")
        self.assertEqual(early["punch"]["active_since"], started_at.isoformat())
        self.assertTrue(early["punch"]["is_clocked_in"])

        with patch(
            "klockin_api.api_views.mobile.views.timezone.now",
            return_value=datetime(2026, 3, 10, 4, tzinfo=UTC),
        ):
            noon = self.client.get(HOME_URL).data
        self.assertEqual(noon["today"]["workday"], FIXED_TODAY.isoformat())
        self.assertEqual(noon["today"]["workday_starts_at"], "2026-03-10T12:00:00+08:00")
        self.assertEqual(noon["today"]["worked"], "00:00:00")
        self.assertIsNone(noon["punch"]["active_since"])

    def test_confirmed_worked_time_uses_settled_dtr_hours(self):
        make_attendance(
            employee=self.employee,
            attendance_date=FIXED_TODAY,
            minimum_hour="04:00",
            clock_out="13:00:00",
        )
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=FIXED_TODAY,
            clock_in_date=FIXED_TODAY,
            clock_in=time(9),
        )
        data = self.client.get(HOME_URL).data
        self.assertEqual(data["today"]["worked"], "04:00:00")
        self.assertFalse(data["punch"]["is_clocked_in"])
        self.assertIsNone(data["punch"]["active_since"])

    def test_a_new_non_overnight_workday_does_not_reuse_previous_dtr_hours(self):
        make_attendance(
            employee=self.employee,
            attendance_date=FIXED_TODAY - timedelta(days=1),
            at_work_second=8 * 3600,
        )
        data = self.client.get(HOME_URL).data
        self.assertEqual(data["today"]["workday"], FIXED_TODAY.isoformat())
        self.assertEqual(data["today"]["worked"], "00:00:00")
        self.assertIsNone(data["punch"]["active_since"])

    def test_geofence_reports_disabled_when_unconfigured(self):
        self.assertEqual(self.client.get(HOME_URL).data["geofence"], {"enabled": False})

    def test_break_is_derived_from_the_gap_between_activity_pairs(self):
        """
        Attendance stores at_work_second and overtime_second but no break
        total, so this is computed. A 30-minute gap between clocking out and
        back in must surface as 00:30:00.
        """
        today = FIXED_TODAY
        base = timezone.make_aware(datetime.combine(today, datetime.min.time()))

        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=9)).time(),
            in_datetime=base + timedelta(hours=9),
            clock_out_date=today,
            clock_out=(base + timedelta(hours=12)).time(),
            out_datetime=base + timedelta(hours=12),
        )
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=12, minutes=30)).time(),
            in_datetime=base + timedelta(hours=12, minutes=30),
        )

        data = self.client.get(HOME_URL).data
        self.assertEqual(data["today"]["break"], "00:30:00")
        self.assertEqual(data["today"]["worked"], "05:30:00")
        self.assertEqual(data["punch"]["active_since"], "2026-03-10T12:30:00+08:00")
        self.assertTrue(
            data["punch"]["is_clocked_in"],
            "the second activity has no clock_out, so the employee is still in",
        )

    def test_a_clock_out_without_an_out_datetime_does_not_500(self):
        """
        clock_out is a TimeField; out_datetime is a separate nullable
        DateTimeField written by a different code path, so a row can carry one
        without the other. Every other test here sets both, which is why this
        went unnoticed until a real server returned 500 on the home screen.
        """
        today = FIXED_TODAY
        base = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=9)).time(),
            in_datetime=base + timedelta(hours=9),
            clock_out_date=today,
            clock_out=(base + timedelta(hours=12)).time(),
            out_datetime=None,
        )
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=12, minutes=30)).time(),
            in_datetime=base + timedelta(hours=12, minutes=30),
        )

        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200)
        # The break is still correct: it is rebuilt from clock_out_date +
        # clock_out, which are written even when out_datetime is not. Reading
        # the nullable column instead would report a real 30-minute break as
        # zero, which is worse than the 500 it replaced -- it looks like data.
        self.assertEqual(response.data["today"]["break"], "00:30:00")

    def test_an_open_activity_without_an_in_datetime_does_not_500(self):
        """in_datetime is nullable too, and last_activity_at dereferenced it."""
        today = FIXED_TODAY
        base = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=9)).time(),
            in_datetime=None,
        )

        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["punch"]["is_clocked_in"])
        # Rebuilt from the date+time pair rather than reported as absent.
        self.assertTrue(
            response.data["punch"]["last_activity_at"].startswith(today.isoformat())
        )

    def test_single_open_activity_means_no_break(self):
        today = FIXED_TODAY
        base = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=9)).time(),
            in_datetime=base + timedelta(hours=9),
        )
        self.assertEqual(self.client.get(HOME_URL).data["today"]["break"], "00:00:00")


class HomeAnnouncementAudienceTests(TestCase):
    """
    The home screen may only surface an announcement this employee is for.

    ``Announcement`` carries targeting (``employees``, ``department``,
    ``job_position``, and the denormalised ``filtered_employees``) and an
    ``expire_date``; the web self-service dashboard filters on all of them.
    The aggregate took ``objects.order_by("-created_at").first()``, which
    honoured none -- so an announcement written for one department, or expired
    a month ago, was handed to everyone in the company.
    """

    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)
        self.company = make_company("Audience Co")
        self.user = make_user("audience_user")
        self.employee = make_employee(
            company=self.company,
            email="audience@test.horilla",
            first_name="Ada",
            user=self.user,
        )
        self.client.force_authenticate(user=self.user)

    def _announcement(self, title, **fields):
        from base.models import Announcement

        announcement = Announcement.objects.create(title=title, **fields)
        announcement.company_id.set([self.company])
        return announcement

    def test_untargeted_announcement_is_returned(self):
        """A broadcast -- no targeting at all -- is addressed to everyone."""
        self._announcement("All hands Friday")
        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNotNone(response.data["announcement"])
        self.assertEqual(response.data["announcement"]["title"], "All hands Friday")

    def test_announcement_for_another_department_is_withheld(self):
        from base.models import Department

        other = Department.objects.create(department="Executive")
        announcement = self._announcement("Exec-only restructure")
        announcement.department.set([other])

        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(
            response.data["announcement"],
            "an announcement targeted at a department this employee is not in "
            "must not appear on their home screen",
        )

    def test_expired_announcement_is_withheld(self):
        self._announcement(
            "Last year's office move", expire_date=date.today() - timedelta(days=30)
        )
        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(
            response.data["announcement"],
            "an announcement past its expire_date must not be surfaced",
        )
