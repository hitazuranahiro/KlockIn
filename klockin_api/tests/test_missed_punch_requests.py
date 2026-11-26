from datetime import date, datetime, time, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings

from attendance.corrections import MISSED_PUNCH_CORRECTION_PREFIX
from attendance.models import Attendance, AttendanceActivity, AttendanceMissedPunchRequest, WorkRecords
from base.models import EmployeeShift, EmployeeShiftDay, EmployeeShiftSchedule
from employee.models import EmployeeWorkInformation
from klockin.testkit import make_company, make_employee, make_user
from klockin_attendance.models import AttendanceBreak, AttendancePolicy, AttendancePunch
from klockin_attendance.tests.test_ingestion import BATCH_URL, _client, _offline, _payload


URL = "/api/v1/attendance/missed-punch/"
DAY = date(2025, 10, 8)
ZONE = ZoneInfo("Asia/Manila")


def stamp(hour, minute=0, second=0, day=DAY):
    return datetime.combine(day, time(hour, minute, second), tzinfo=ZONE)


@override_settings(TIME_ZONE="Asia/Manila")
class MissedPunchRequestTests(TestCase):
    def setUp(self):
        self.company = make_company("Missed Punch Company")
        self.employee_user = make_user("missed-punch-employee")
        self.employee = make_employee(company=self.company, user=self.employee_user, email=self.employee_user.email)
        self.manager_user = make_user("missed-punch-manager")
        self.manager = make_employee(company=self.company, user=self.manager_user, email=self.manager_user.email)
        EmployeeWorkInformation.objects.filter(employee_id=self.employee).update(reporting_manager_id=self.manager)
        self.employee_api = _client(self.employee_user)
        self.manager_api = _client(self.manager_user)

    def submit(self, expected=201, **punches):
        response = self.employee_api.post(URL, {
            "attendance_date": DAY.isoformat(), "reason": "I forgot to punch.", **punches,
        }, format="json")
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def decide(self, pk, *, approve=True, expected=200, client=None):
        verb = "approve" if approve else "reject"
        response = (client or self.manager_api).put(f"{URL}{pk}/{verb}/")
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def _day(self, **fields):
        return Attendance.objects.create(employee_id=self.employee, attendance_date=DAY, **fields)

    def _activity(self, start, end=None):
        return AttendanceActivity.objects.create(
            employee_id=self.employee, attendance_date=DAY,
            clock_in_date=start.date(), clock_in=start.time(), in_datetime=start,
            clock_out_date=end.date() if end else None, clock_out=end.time() if end else None, out_datetime=end,
        )

    def test_checkin_only_no_attendance_or_work_record_until_approved(self):
        request = self.submit(time_in="08:00")
        self.assertEqual(request["status"], "pending")
        self.assertEqual(request["time_in"], "08:00:00")
        self.assertIsNone(request["time_out"])
        self.assertIsNone(request["attendance_id"])
        self.assertFalse(Attendance.objects.filter(employee_id=self.employee, attendance_date=DAY).exists())
        self.assertFalse(WorkRecords.objects.filter(employee_id=self.employee, date=DAY).exists())
        self.assertFalse(AttendanceActivity.objects.filter(employee_id=self.employee, attendance_date=DAY).exists())
        self.assertEqual(self.manager_api.get(URL, {"scope": "approvals"}).data["count"], 1)
        home = self.manager_api.get("/api/v1/mobile/home/").data
        self.assertEqual(home["pending_approvals"]["by_kind"]["missed_punch"], 1)
        self.decide(request["id"], client=self.employee_api, expected=404)

        response = self.decide(request["id"])
        daily = Attendance.objects.get(pk=response["attendance_id"])
        activity = AttendanceActivity.objects.get(employee_id=self.employee, attendance_date=DAY)
        self.assertEqual(response["status"], "approved")
        self.assertEqual(daily.attendance_clock_in, time(8))
        self.assertIsNone(daily.attendance_clock_out)
        self.assertEqual(activity.in_datetime, stamp(8))
        self.assertIsNone(activity.out_datetime)
        self.assertEqual(daily.history.first().history_user, self.manager_user)
        self.assertEqual(daily.history.first().history_change_reason, MISSED_PUNCH_CORRECTION_PREFIX + request["reason"])
        self.assertEqual(activity.history.first().history_user, self.manager_user)
        self.assertEqual(self.manager_api.get(URL, {"scope": "approvals"}).data["count"], 0)
        self.assertEqual(self.employee_api.get(URL).data["results"][0]["status"], "approved")

    def test_checkout_closes_only_open_interval_and_combines_breaks(self):
        daily = self._day(attendance_clock_in=time(8), attendance_clock_in_date=DAY, attendance_worked_hour="04:00")
        first = self._activity(stamp(8), stamp(12))
        final = self._activity(stamp(13, second=11))
        AttendancePolicy.objects.create(company=self.company, break_start=time(11, 30), break_end=time(13, 30))
        AttendanceBreak.objects.create(attendance=daily, started_at=stamp(13, 15), ended_at=stamp(14))
        running = AttendanceBreak.objects.create(attendance=daily, started_at=stamp(16, 30))

        request = self.submit(time_out="17:00")
        daily.refresh_from_db()
        self.assertIsNone(daily.attendance_clock_out)
        self.assertEqual(daily.attendance_worked_hour, "04:00")
        self.decide(request["id"])

        daily.refresh_from_db()
        first.refresh_from_db()
        final.refresh_from_db()
        running.refresh_from_db()
        self.assertEqual(daily.attendance_clock_in, time(8))
        self.assertEqual(daily.attendance_clock_in_date, DAY)
        self.assertEqual(daily.attendance_clock_out, time(17))
        self.assertEqual(daily.attendance_worked_hour, "06:00")
        self.assertEqual(AttendanceActivity.objects.filter(employee_id=self.employee).count(), 2)
        self.assertEqual(first.out_datetime, stamp(12))
        self.assertEqual(final.in_datetime, stamp(13, second=11))
        self.assertEqual(final.out_datetime, stamp(17))
        self.assertEqual(running.ended_at, stamp(17))

    def test_checkin_preserves_existing_out_and_requires_chronology(self):
        next_day = DAY + timedelta(days=1)
        daily = self._day(attendance_clock_out=time(6), attendance_clock_out_date=next_day)
        self.submit(time_in="07:00", clock_in_date=next_day.isoformat(), expected=400)
        request = self.submit(time_in="22:00")
        self.decide(request["id"])
        daily.refresh_from_db()
        self.assertEqual(daily.attendance_clock_out, time(6))
        self.assertEqual(daily.attendance_clock_out_date, next_day)
        self.assertEqual(daily.attendance_worked_hour, "08:00")

    def test_both_and_rejection_history_and_date_validation(self):
        self.submit(time_out="17:00", expected=400)
        self.submit(time_in="22:00", time_out="06:00", expected=400)
        self.submit(time_in="22:00", clock_out_date=DAY.isoformat(), expected=400)
        request = self.submit(time_in="22:00", time_out="06:00", clock_out_date=(DAY + timedelta(days=1)).isoformat())
        self.submit(time_in="08:00", expected=409)
        decision = self.decide(request["id"], approve=False)
        self.assertEqual(decision["status"], "rejected")
        self.assertFalse(Attendance.objects.filter(employee_id=self.employee, attendance_date=DAY).exists())
        self.decide(request["id"], expected=409)
        request = self.submit(time_in="08:00", time_out="17:00")
        decision = self.decide(request["id"])
        self.assertEqual(decision["status"], "approved")
        self.assertEqual(Attendance.objects.get(pk=decision["attendance_id"]).attendance_worked_hour, "09:00")

    def test_permissions_are_direct_and_same_company(self):
        peer_user = make_user("missed-punch-peer", is_superuser=True)
        make_employee(company=self.company, user=peer_user, email=peer_user.email)
        request = self.submit(time_in="08:00")
        self.decide(request["id"], expected=404, client=_client(peer_user))
        other_company = make_company("Unrelated Company")
        EmployeeWorkInformation.objects.filter(employee_id=self.manager).update(company_id=other_company)
        self.assertEqual(self.manager_api.get(URL, {"scope": "approvals"}).data["count"], 0)
        self.decide(request["id"], expected=404)
        self.assertTrue(AttendanceMissedPunchRequest.objects.filter(pk=request["id"], status="pending").exists())

    def test_pending_legacy_and_new_real_punch_are_protected(self):
        daily = self._day(is_validate_request=True)
        self.submit(time_in="08:00", expected=409)
        Attendance.objects.filter(pk=daily.pk).update(is_validate_request=False)
        request = self.submit(time_in="08:00")
        daily.attendance_clock_in = time(7, 58)
        daily.attendance_clock_in_date = DAY
        daily.is_validate_request = False
        daily.save()
        self.decide(request["id"], expected=409)
        daily.refresh_from_db()
        self.assertEqual(daily.attendance_clock_in, time(7, 58))

    def test_approved_punches_keep_shift_validation_and_late_and_early_reports(self):
        shift = EmployeeShift.objects.create(employee_shift="Missed punch dated shift")
        shift_day = EmployeeShiftDay.objects.get(day=DAY.strftime("%A").lower())
        EmployeeShiftSchedule.objects.create(
            shift_id=shift, day=shift_day, start_time=time(8), end_time=time(17),
            minimum_working_hour="08:00",
        )
        EmployeeWorkInformation.objects.filter(employee_id=self.employee).update(shift_id=shift)
        request = self.submit(time_in="09:00", time_out="16:00")
        daily = Attendance.objects.get(pk=self.decide(request["id"])["attendance_id"])
        self.assertEqual(daily.shift_id, shift)
        self.assertEqual(daily.minimum_hour, "08:00")
        self.assertEqual(daily.attendance_worked_hour, "07:00")
        self.assertTrue(daily.attendance_validated)
        self.assertEqual(
            set(daily.late_come_early_out.values_list("type", flat=True)),
            {"late_come", "early_out"},
        )

    def test_approved_checkin_can_receive_real_mobile_out_without_replacement(self):
        corrected = self.decide(self.submit(time_in="08:00")["id"])
        with TemporaryDirectory() as directory, override_settings(KLOCKIN_SELFIE_ROOT=directory):
            for kind, moment, projection in (
                ("CLOCK_OUT", stamp(7), "PENDING"),
                ("CLOCK_OUT", stamp(17), "LINKED"),
                ("CLOCK_IN", stamp(7, 30), "PENDING"),
            ):
                payload = _offline(_payload(punch_type=kind, punched_at=moment.isoformat()))
                response = self.employee_api.post(BATCH_URL, [payload], format="json")
                self.assertEqual(response.status_code, 200, response.data)
                receipt = response.data["results"][0]
                self.assertEqual(receipt["status"], 201, receipt)
                self.assertEqual(receipt["projection_status"], projection, receipt)
        daily = Attendance.objects.get(pk=corrected["attendance_id"])
        self.assertEqual(daily.attendance_clock_in, time(8))
        self.assertEqual(daily.attendance_clock_out, time(17))
        self.assertEqual(daily.attendance_worked_hour, "09:00")
        self.assertFalse(AttendancePunch.objects.get(punched_at=stamp(17)).projectable)

    def test_submission_and_decision_queue_notifications_after_commit(self):
        with patch("attendance.corrections.notify.send") as send:
            with self.captureOnCommitCallbacks(execute=True):
                request = self.submit(time_in="08:00")
            self.assertEqual(send.call_args.kwargs["recipient"], self.manager_user)
            with self.captureOnCommitCallbacks(execute=True):
                self.decide(request["id"], approve=False)
            self.assertEqual(send.call_args.kwargs["recipient"], self.employee_user)
