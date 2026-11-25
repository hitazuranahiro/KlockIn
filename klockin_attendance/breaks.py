"""Employee break timing shared by web, mobile and attendance projection."""

from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.db.models.functions import Greatest
from django.utils import timezone

from attendance.models import Attendance, AttendanceActivity
from employee.models import Employee, EmployeeWorkInformation

from .models import AttendanceBreak, AttendancePolicy
from .policies import elapsed_seconds
from .services import PunchRejected, _lock_employee
from .workday import shift_schedules, workday_date


class BreakError(Exception):
    def __init__(self, detail, status):
        super().__init__(detail)
        self.status = status


@dataclass
class _BreakState:
    attendance: Attendance | None
    active: AttendanceBreak | None
    allowance: int
    used: int
    clocked_in: bool
    as_of: datetime

    def summary(self):
        remaining = max(self.allowance - self.used, 0)
        return {
            "enabled": self.allowance > 0,
            "can_start": self.clocked_in and self.active is None and remaining > 0,
            "allowed_seconds": self.allowance,
            "used_seconds": self.used,
            "remaining_seconds": remaining,
            "active_since": self.active.started_at.isoformat() if self.active else None,
            "as_of": self.as_of.isoformat(),
        }


def _state(employee, as_of):
    work = (
        EmployeeWorkInformation._base_manager.filter(employee_id=employee)
        .values("shift_id_id", "company_id_id")
        .first()
    )
    if work is None:
        return _BreakState(None, None, 0, 0, False, as_of)

    policy_minutes = (
        AttendancePolicy._base_manager.filter(company_id=work["company_id_id"])
        .values_list("break_allowance_minutes", flat=True)
        .first()
    )
    schedule = shift_schedules(work["shift_id_id"])
    workday = workday_date(timezone.localtime(as_of, timezone.get_default_timezone()), schedule)
    attendance = Attendance._base_manager.filter(employee_id=employee, attendance_date=workday).first()

    # An employee who missed checkout can still end the same break after rollover.
    active = (
        AttendanceBreak.objects.filter(attendance__employee_id=employee, ended_at__isnull=True)
        .select_related("attendance")
        .first()
    )
    used = 0
    used_attendance = active.attendance if active else attendance
    if used_attendance is not None:
        used = int(sum(
            elapsed_seconds(start, end)
            for start, end in tracked_break_ranges(used_attendance, as_of=as_of)
        ))
    clocked_in = (
        attendance is not None
        and attendance.attendance_clock_out is None
        and AttendanceActivity._base_manager.filter(
            employee_id=employee, attendance_date=workday, clock_out__isnull=True,
        ).exists()
    )
    return _BreakState(attendance, active, (policy_minutes or 0) * 60, used, clocked_in, as_of)


def employee_break_summary(employee, *, as_of=None):
    return _state(employee, as_of or timezone.now()).summary()


def user_break_summary(user):
    employee = Employee._base_manager.filter(employee_user_id=user.pk, is_active=True).first()
    if employee is None:
        raise BreakError("An active employee profile is required.", 403)
    return employee_break_summary(employee)


@transaction.atomic
def change_break(user, action):
    if action not in ("start", "end"):
        raise BreakError("Use start or end for the break action.", 400)
    try:
        employee = _lock_employee(user)
    except PunchRejected as error:
        raise BreakError(str(error), error.status) from error

    as_of = timezone.now()
    state = _state(employee, as_of)
    if action == "start":
        if state.active:
            raise BreakError("A break is already in progress.", 409)
        if not state.clocked_in:
            raise BreakError("Clock in before starting a break.", 409)
        if not state.allowance:
            raise BreakError("Break tracking is disabled for your company.", 409)
        if state.used >= state.allowance:
            raise BreakError("Your break allowance is used up for this shift.", 409)
        AttendanceBreak.objects.create(attendance=state.attendance, started_at=as_of)
    else:
        if state.active is None:
            raise BreakError("There is no active break to end.", 409)
        state.active.ended_at = max(as_of, state.active.started_at)
        state.active.save(update_fields=["ended_at"])
    return _state(employee, as_of).summary()


def tracked_break_ranges(attendance, *, as_of=None):
    if attendance is None or attendance.pk is None:
        return []
    breaks = attendance.tracked_breaks.all()
    if as_of is None:
        breaks = breaks.filter(ended_at__isnull=False)
    return [(start, end or as_of) for start, end in breaks.values_list("started_at", "ended_at")]


def close_attendance_break(attendance, checkout):
    """Close an open break while holding the employee lock for checkout."""
    attendance.tracked_breaks.filter(ended_at__isnull=True).update(
        ended_at=Greatest("started_at", checkout),
    )
