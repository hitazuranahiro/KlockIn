"""Apply mobile punches to their employee's dated attendance record."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings

from attendance.corrections import CORRECTION_PREFIX, MISSED_PUNCH_CORRECTION_PREFIX
from attendance.methods.utils import format_time
from attendance.models import Attendance, AttendanceActivity, AttendanceMissedPunchRequest
from attendance.views.views import attendance_validate
from attendance.views.clock_in_out import early_out, late_come
from base.models import EmployeeShiftDay
from employee.models import EmployeeWorkInformation

from .breaks import close_attendance_break, tracked_break_ranges
from .models import AttendancePolicy, AttendancePunch, MobileDayPolicy
from .policies import duration_totals
from .workday import WEEKDAYS, shift_schedules, workday_bounds, workday_date


def _pairs(punches):
    opened = None
    for punch in punches:
        if punch.punch_type == AttendancePunch.PunchType.CLOCK_IN:
            if opened is None:
                opened = punch
        elif opened is not None and opened.punched_at < punch.punched_at:
            yield opened, punch
            opened = None
    if opened is not None:
        yield opened, None


def attendance_has_manual_history(daily):
    return (
        daily.is_validate_request
        or daily.is_validate_request_approved
        or daily.attendance_overtime_approve
        or any(marker.penaltyaccounts_set.exists() for marker in daily.late_come_early_out.all())
        or daily.history.filter(history_change_reason__startswith=CORRECTION_PREFIX).exists()
    )


def activity_links_match(activities, linked):
    opened = set()
    closed = set()
    for event in linked:
        if event.punch_type == AttendancePunch.PunchType.CLOCK_IN:
            opened.add(event.activity_id)
        else:
            closed.add(event.activity_id)
    return opened == set(activities) and closed == {
        pk for pk, activity in activities.items() if activity.clock_out is not None
    }


def _summary(activities, policy, zone, attendance):
    first = min(activities, key=lambda row: row.in_datetime)
    closed = [row for row in activities if row.out_datetime is not None]
    last = (
        max(closed, key=lambda row: row.out_datetime)
        if len(closed) == len(activities)
        else None
    )
    ranges = [(row.in_datetime.astimezone(zone), row.out_datetime.astimezone(zone)) for row in closed]
    seconds, _ = duration_totals(ranges, policy, excluded_ranges=tracked_break_ranges(attendance))
    return {
        "attendance_clock_in_date": first.clock_in_date,
        "attendance_clock_in": first.clock_in,
        "attendance_clock_out_date": last.clock_out_date if last else None,
        "attendance_clock_out": last.clock_out if last else None,
        "attendance_worked_hour": format_time(seconds),
    }


def is_approved_missed_checkin(daily, activity):
    """Recognize an untouched open interval created by a check-in-only approval."""
    if (
        activity is None
        or daily.attendance_clock_out is not None
        or daily.attendance_clock_out_date is not None
        or daily.is_validate_request
        or daily.is_validate_request_approved
        or daily.attendance_overtime_approve
        or activity.clock_out is not None
        or activity.out_datetime is not None
        or activity.in_datetime is None
    ):
        return False
    clock_in = daily.attendance_clock_in
    clock_in_date = daily.attendance_clock_in_date
    if clock_in is None or clock_in_date is None:
        return False
    recorded = datetime.combine(clock_in_date, clock_in, tzinfo=ZoneInfo(settings.TIME_ZONE))
    eligible = (
        activity.clock_in == clock_in
        and activity.clock_in_date == clock_in_date
        and activity.in_datetime == recorded
        and daily.missed_punch_requests.filter(
            status=AttendanceMissedPunchRequest.Status.APPROVED,
            time_in=clock_in,
            clock_in_date=clock_in_date,
            time_out__isnull=True,
        ).exists()
    )
    if not eligible:
        return False
    correction = daily.history.filter(history_change_reason__startswith=CORRECTION_PREFIX).first()
    return bool(
        correction is not None
        and correction.history_change_reason.startswith(MISSED_PUNCH_CORRECTION_PREFIX)
        and not any(marker.penaltyaccounts_set.exists() for marker in daily.late_come_early_out.all())
    )


def _close_approved_missed_checkin(punch, daily, activity, zone, shift_start, shift_end):
    duration = punch.punched_at.astimezone(UTC) - activity.in_datetime.astimezone(UTC)
    if not timedelta(0) < duration <= timedelta(days=1):
        return None
    local_out = punch.punched_at.astimezone(zone)
    activity.clock_out = local_out.time()
    activity.clock_out_date = local_out.date()
    activity.out_datetime = punch.punched_at
    activity.save(update_fields=["clock_out", "clock_out_date", "out_datetime"])

    close_attendance_break(daily, punch.punched_at)
    summary = _summary([activity], getattr(daily, "mobile_policy", None), zone, daily)
    daily.attendance_clock_out = activity.clock_out
    daily.attendance_clock_out_date = activity.clock_out_date
    daily.attendance_worked_hour = summary["attendance_worked_hour"]
    daily.attendance_validated = attendance_validate(daily)
    daily.save()
    if shift_start != shift_end:
        early_out(daily, shift_start, shift_end, daily.shift_id)

    # The checkout is genuine evidence, but an official manual check-in is
    # deliberately outside the evidence sequence used to rebuild later days.
    punch.activity = activity
    punch.attendance = daily
    punch.projectable = False
    punch.save(update_fields=["activity", "attendance", "projectable"])
    return daily


def project_punch(punch):
    """Reconcile the affected shift during the ingestion employee lock."""
    local_zone = ZoneInfo(settings.TIME_ZONE)
    work_info = EmployeeWorkInformation.objects.filter(
        employee_id=punch.employee
    ).first()
    if work_info is None:
        return None

    shift_days = {
        day.day: day for day in EmployeeShiftDay.objects.filter(day__in=WEEKDAYS)
    }
    if len(shift_days) != len(WEEKDAYS):
        return None
    schedules = shift_schedules(work_info.shift_id_id)
    work_date = workday_date(punch.punched_at.astimezone(local_zone), schedules)
    day = shift_days[WEEKDAYS[work_date.weekday()]]
    minimum_hour, shift_start, shift_end = schedules[work_date.weekday()]
    start, end = workday_bounds(work_date, schedules, local_zone)

    # A staff evidence attachment must not become a clock interval later.
    punches = AttendancePunch.objects.filter(
        employee_id=punch.employee_id,
        punched_at__gte=start,
        punched_at__lt=end,
        review__isnull=True,
        projectable=True,
    ).order_by("punched_at", "punch_uuid")
    daily = (
        Attendance.objects.select_for_update(of=("self",))
        .filter(employee_id=punch.employee, attendance_date=work_date)
        .first()
    )
    activities = {
        row.pk: row
        for row in AttendanceActivity.objects.select_for_update(of=("self",)).filter(
            employee_id=punch.employee, attendance_date=work_date
        )
    }
    if daily is not None and len(activities) == 1 and punch.punch_type == AttendancePunch.PunchType.CLOCK_OUT:
        activity = next(iter(activities.values()))
        if is_approved_missed_checkin(daily, activity):
            return _close_approved_missed_checkin(punch, daily, activity, local_zone, shift_start, shift_end)

    pairs = list(_pairs(punches))
    if not pairs:
        return None

    policy = None
    needs_snapshot = daily is None
    if daily is not None:
        policy = getattr(daily, "mobile_policy", None)
        if (
            not activities
            or daily.klockin_punches.filter(projectable=False).exists()
            or not activity_links_match(
                activities,
                (event for event in punches if event.attendance_id == daily.pk and event.activity_id),
            )
            or attendance_has_manual_history(daily)
            or any(row.in_datetime is None for row in activities.values())
            or any(
                getattr(daily, key) != value
                for key, value in _summary(activities.values(), policy, local_zone, daily).items()
            )
        ):
            return None
    elif activities:
        return None
    else:
        policy = AttendancePolicy._base_manager.filter(company_id=work_info.company_id_id).first()
        daily = Attendance(
            employee_id=punch.employee,
            attendance_date=work_date,
            attendance_day=day,
            shift_id=work_info.shift_id,
            work_type_id=work_info.work_type_id,
            minimum_hour=minimum_hour,
        )

    links = {}
    projected_activities = []
    for clock_in, clock_out in pairs:
        activity = activities.pop(clock_in.activity_id, None) or AttendanceActivity(
            employee_id=punch.employee, attendance_date=work_date, shift_day=day
        )
        in_local = clock_in.punched_at.astimezone(local_zone)
        out_local = clock_out.punched_at.astimezone(local_zone) if clock_out else None
        fields = {
            "in_datetime": clock_in.punched_at,
            "clock_in_date": in_local.date(),
            "clock_in": in_local.time(),
            "out_datetime": clock_out.punched_at if clock_out else None,
            "clock_out_date": out_local.date() if out_local else None,
            "clock_out": out_local.time() if out_local else None,
        }
        if activity.pk is None or any(
            getattr(activity, key) != value for key, value in fields.items()
        ):
            for key, value in fields.items():
                setattr(activity, key, value)
            activity.save()
        projected_activities.append(activity)
        links[clock_in.pk] = activity.pk
        if clock_out is not None:
            links[clock_out.pk] = activity.pk

    if daily.pk and all(row.out_datetime is not None for row in projected_activities):
        checkout = max(row.out_datetime for row in projected_activities)
        close_attendance_break(daily, checkout)
    summary = _summary(projected_activities, policy, local_zone, daily)
    if daily.pk is None or any(
        getattr(daily, key) != value for key, value in summary.items()
    ):
        for key, value in summary.items():
            setattr(daily, key, value)
        daily.attendance_validated = (
            daily.attendance_clock_out is not None and attendance_validate(daily)
        )
        daily.save()
        if shift_start != shift_end:
            daily.late_come_early_out.filter(
                type__in=("late_come", "early_out")
            ).delete()
            late_come(daily, shift_start, shift_end, daily.shift_id)
            if daily.attendance_clock_out is not None:
                early_out(daily, shift_start, shift_end, daily.shift_id)

    if needs_snapshot and policy is not None:
        MobileDayPolicy.objects.create(
            attendance=daily, mode=policy.mode, break_start=policy.break_start, break_end=policy.break_end
        )

    for event in punches:
        activity_id = links.get(event.pk)
        attendance_id = daily.pk if activity_id is not None else None
        if event.activity_id != activity_id or event.attendance_id != attendance_id:
            AttendancePunch.objects.filter(pk=event.pk).update(
                activity_id=activity_id, attendance_id=attendance_id
            )
    for obsolete_activity in activities.values():
        obsolete_activity.delete()

    if punch.pk in links:
        punch.activity_id = links[punch.pk]
        punch.attendance_id = daily.pk
        return daily
    return None
