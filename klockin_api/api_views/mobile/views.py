"""
Screen-shaped aggregates for the mobile client.

Everything else in this API is resource-shaped, and rightly so. The home
screen is the exception: it renders punch state, today's hours, a role band,
who is on leave, the latest announcement and an unread badge, which came to
eight or more round trips on a cold start over a mobile network. The previous
Flutter app made fourteen.

Deliberately narrow. This returns exactly what the home screen draws and
nothing else -- it is a view of existing data, not a second API. Resist
growing it into a general-purpose "give me everything" endpoint; if another
screen needs an aggregate, it gets its own, so each one stays readable and
cheap.
"""

from datetime import UTC, date, datetime

from django.apps import apps
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.methods.utils import strtime_seconds
from attendance.models import Attendance, AttendanceActivity
from employee.models import EmployeeWorkInformation
from klockin_api.api_methods.base.announcements import announcements_for
from klockin_api.api_methods.base.capabilities import build_capabilities
from klockin_attendance.breaks import employee_break_summary, tracked_break_ranges
from klockin_attendance.policies import FIRST_LAST, duration_totals
from klockin_attendance.workday import shift_schedules, workday_bounds, workday_date


def _format_seconds(seconds):
    seconds = max(int(seconds or 0), 0)
    return f"{seconds // 3600:02}:{(seconds % 3600) // 60:02}:{seconds % 60:02}"


def _activity_timestamp(recorded, day, clock, zone):
    # Older activity rows can have only the separate date and time columns.
    return (
        recorded.astimezone(zone)
        if recorded
        else datetime.combine(day, clock, tzinfo=zone)
    )


def _activity_ranges(employee, workday, zone):
    activities = AttendanceActivity.objects.filter(
        employee_id=employee, attendance_date=workday
    )
    ranges = []
    for activity in activities:
        clock_in_date = activity.clock_in_date or workday
        start = _activity_timestamp(
            activity.in_datetime, clock_in_date, activity.clock_in, zone
        )
        end = None
        if activity.clock_out is not None:
            end = _activity_timestamp(
                activity.out_datetime,
                activity.clock_out_date or clock_in_date,
                activity.clock_out,
                zone,
            )
        ranges.append((start, end))
    return sorted(ranges, key=lambda interval: interval[0].timestamp())


def _elapsed_seconds(start, end):
    delta = end.astimezone(UTC) - start.astimezone(UTC)
    return max(delta.total_seconds(), 0)


def _punch_block(attendance, ranges, active_since):
    first_clock_in = attendance.attendance_clock_in if attendance else None
    if first_clock_in is None and ranges:
        first_clock_in = ranges[0][0].time()
    return {
        "is_clocked_in": active_since is not None,
        "clock_in_time": first_clock_in.strftime("%H:%M") if first_clock_in else None,
        "last_activity_at": (
            active_since.replace(tzinfo=None).isoformat() if active_since else None
        ),
        "active_since": active_since.isoformat() if active_since else None,
    }


def _worked_seconds(attendance, active_since, calculated_seconds):
    if attendance and active_since is None:
        # The settled DTR can contain a supervisor correction or an import.
        if attendance.at_work_second is not None:
            return attendance.at_work_second
        return strtime_seconds(attendance.attendance_worked_hour or "00:00")
    return calculated_seconds


def _geofence_block(employee):
    """Config only. The client sends coordinates and the punch endpoint rules."""
    from geofencing.models import GeoFencing

    company = employee.get_company()
    # the company's own fence, else the global one
    fence = GeoFencing.for_company(company)
    if fence is None or not fence.start:
        return {"enabled": False}
    return {
        "enabled": True,
        "latitude": fence.latitude,
        "longitude": fence.longitude,
        "radius_in_meters": fence.radius_in_meters,
        "locations": list(fence.locations()),
    }


def _on_leave_today(employee):
    if not apps.is_installed("leave"):
        return []
    LeaveRequest = apps.get_model("leave", "LeaveRequest")
    today = date.today()
    requests = (
        LeaveRequest.objects.filter(
            status__in=["approved", "cancel_requested"],
            start_date__lte=today,
            end_date__gte=today,
        )
        .select_related("employee_id")
        .exclude(employee_id=employee)[:10]
    )
    return [
        {
            "id": leave.employee_id.id,
            "name": leave.employee_id.get_full_name(),
            "leave_type": getattr(leave.leave_type_id, "leave_type", None),
        }
        for leave in requests
        if leave.employee_id
    ]


def _latest_announcement(employee):
    """
    The newest announcement this employee is actually an audience for.

    Announcements carry targeting (``employees``, ``department``,
    ``job_position``, or the denormalised ``filtered_employees``) and an
    ``expire_date``. Taking ``objects.order_by("-created_at").first()`` ignores
    both, so the home screen served a department-targeted or long-expired
    announcement to everyone in the company. The manager scopes by company, so
    this was never cross-tenant -- but "everyone in the company" is not the
    audience the author chose.
    """
    announcement = announcements_for(employee).order_by("-created_at").first()
    if not announcement:
        return None
    return {
        "id": announcement.id,
        "title": announcement.title,
        "created_at": announcement.created_at.isoformat(),
    }


def _unread_notification_count(user):
    return user.notifications.unread().count()


def _pending_approvals(request):
    """
    What is waiting on this caller to decide, by kind.

    Built from the same scoping the list endpoints use, so the count matches
    what a client sees when it opens those lists. The caller's own requests
    are excluded: every list includes them, and no one approves their own.
    Kinds with no manager path (reimbursements need the payroll permission)
    count only for callers who could act on them.
    """
    from base.methods import filtersubordinates
    from base.models import ShiftRequest, WorkTypeRequest
    from klockin_api.api_methods.base.methods import permission_based_queryset

    employee = request.user.employee_get
    by_kind = {}

    if apps.is_installed("leave"):
        from leave.methods import filter_conditional_leave_request

        LeaveRequest = apps.get_model("leave", "LeaveRequest")
        LeaveAllocationRequest = apps.get_model("leave", "LeaveAllocationRequest")
        leave = filtersubordinates(
            request, LeaveRequest.objects.all(), "leave.view_leaverequest"
        ) | filter_conditional_leave_request(request)
        by_kind["leave"] = (
            leave.filter(status="requested")
            .exclude(employee_id=employee)
            .distinct()
            .count()
        )
        by_kind["allocation"] = (
            filtersubordinates(
                request,
                LeaveAllocationRequest.objects.all(),
                "leave.view_leaveallocationrequest",
            )
            .filter(status="requested")
            .exclude(employee_id=employee)
            .count()
        )

    by_kind["attendance"] = (
        filtersubordinates(
            request=request,
            perm="attendance.view_attendance",
            queryset=Attendance.objects.filter(is_validate_request=True),
        )
        .exclude(employee_id=employee)
        .count()
    )

    for kind, model, perm in (
        ("shift", ShiftRequest, "base.view_shiftrequest"),
        ("work_type", WorkTypeRequest, "base.view_worktyperequest"),
    ):
        by_kind[kind] = (
            permission_based_queryset(
                request.user, perm, model.objects.all(), user_obj=True
            )
            .filter(approved=False, canceled=False)
            .exclude(employee_id=employee)
            .count()
        )

    if apps.is_installed("payroll") and request.user.has_perm(
        "payroll.change_reimbursement"
    ):
        Reimbursement = apps.get_model("payroll", "Reimbursement")
        by_kind["reimbursement"] = (
            Reimbursement.objects.filter(status="requested")
            .exclude(employee_id=employee)
            .count()
        )

    return {"total": sum(by_kind.values()), "by_kind": by_kind}


class MobileHomeAPIView(APIView):
    """Everything the home screen draws, in one request."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee = request.user.employee_get
        zone = timezone.get_default_timezone()
        confirmed_at = timezone.localtime(timezone.now(), zone)
        shift_id = (
            EmployeeWorkInformation.objects.filter(employee_id=employee)
            .values_list("shift_id_id", flat=True)
            .first()
        )
        schedules = shift_schedules(shift_id)
        workday = workday_date(confirmed_at, schedules)
        starts_at, ends_at = workday_bounds(workday, schedules, zone)
        attendance_today = Attendance.objects.filter(
            employee_id=employee, attendance_date=workday
        ).first()
        ranges = _activity_ranges(employee, workday, zone)
        active_since = None
        if attendance_today is None or attendance_today.attendance_clock_out is None:
            active_since = next((start for start, end in ranges if end is None), None)
        policy = getattr(attendance_today, "mobile_policy", None)
        intervals = [(start, end if end is not None else confirmed_at) for start, end in ranges]
        tracked_breaks = tracked_break_ranges(attendance_today, as_of=confirmed_at)
        calculated_seconds, unpaid_break = duration_totals(
            intervals, policy, excluded_ranges=tracked_breaks,
        )
        worked_seconds = _worked_seconds(attendance_today, active_since, calculated_seconds)
        clocked_out_break = 0
        if not policy or policy.mode != FIRST_LAST:
            clocked_out_break = sum(
                _elapsed_seconds(previous_end, start)
                for (_, previous_end), (start, _) in zip(ranges, ranges[1:])
                if previous_end is not None
            )
        break_seconds = unpaid_break + clocked_out_break

        return Response(
            {
                "employee": {
                    "id": employee.id,
                    "name": employee.get_full_name(),
                    "avatar": employee.get_avatar(),
                },
                "capabilities": build_capabilities(request.user),
                "punch": _punch_block(attendance_today, ranges, active_since),
                "geofence": _geofence_block(employee),
                "break_policy": employee_break_summary(employee, as_of=confirmed_at),
                "today": {
                    "worked": _format_seconds(worked_seconds),
                    "break": _format_seconds(break_seconds),
                    "overtime": _format_seconds(
                        attendance_today.overtime_second if attendance_today else 0
                    ),
                    "workday": workday.isoformat(),
                    "time_zone": zone.key,
                    "confirmed_at": confirmed_at.isoformat(),
                    "workday_starts_at": starts_at.isoformat(),
                    "workday_ends_at": ends_at.isoformat(),
                },
                "on_leave_today": _on_leave_today(employee),
                "announcement": _latest_announcement(employee),
                "unread_notifications": _unread_notification_count(request.user),
                "pending_approvals": _pending_approvals(request),
            },
            status=200,
        )
