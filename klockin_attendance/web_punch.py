"""Attendance confirmation and private evidence from authenticated browser sessions."""

import ipaddress
import logging
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import OperationalError
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from attendance.methods.utils import get_client_ip
from attendance.models import Attendance, AttendanceActivity, AttendanceGeneralSetting
from attendance.views.clock_in_out import (
    clock_in_attendance_and_activity,
    clock_out_attendance_and_activity,
    early_out,
)
from base.models import AttendanceAllowedIP
from employee.models import Employee

from .address import preview_punch_address, resolve_punch_address
from .models import AttendancePunch
from .serializers import BrowserLocationSerializer, BrowserPunchSerializer
from .services import PunchRejected, ingest_punch
from .views import PunchMultipartParser
from .workday import shift_schedules, workday_date

logger = logging.getLogger(__name__)


@dataclass
class LegacyWebDay:
    attendance: Attendance
    open_activity: AttendanceActivity | None
    shift_schedule: tuple


def _browser_policy(request, employee):
    if not employee or not employee.is_active:
        raise PunchRejected("employee_required", "An active employee profile is required.", 403)
    work = getattr(employee, "employee_work_info", None)
    if work is None:
        raise PunchRejected("work_profile_required", "Your work profile is incomplete.", 403)

    selected = request.session.get("selected_company", "all")
    if selected != "all" and str(selected) != str(work.company_id_id):
        raise PunchRejected("wrong_company", "Switch to your own company before punching.", 403)
    config = AttendanceGeneralSetting._base_manager.filter(company_id=work.company_id_id).first()
    if config is None and selected == "all" and work.company_id_id is not None:
        config = AttendanceGeneralSetting._base_manager.filter(company_id__isnull=True).first()
    if not config or not config.enable_check_in:
        raise PunchRejected("browser_punch_disabled", "Web attendance is disabled for this company.", 403)

    return work


def _check_browser_access(request, employee):
    work = _browser_policy(request, employee)
    ip_rule = AttendanceAllowedIP._base_manager.filter(company_id=work.company_id_id).first()
    if ip_rule is None and work.company_id_id is not None:
        ip_rule = AttendanceAllowedIP._base_manager.filter(company_id__isnull=True).first()
    if ip_rule and ip_rule.is_enabled:
        client_ip = get_client_ip(request)
        for address in (ip_rule.additional_data or {}).get("allowed_ips", []):
            try:
                if ipaddress.ip_address(client_ip) in ipaddress.ip_network(address, strict=False):
                    break
            except ValueError:
                continue
        else:
            raise PunchRejected("unauthorized_network", "Your network is not authorized for attendance.", 403)
    return work


def _workday_activities(employee, work, moment):
    schedules = shift_schedules(work.shift_id_id)
    day = workday_date(moment.astimezone(timezone.get_default_timezone()), schedules)
    rows = AttendanceActivity._base_manager.filter(employee_id=employee, attendance_date=day)
    return day, rows, schedules[day.weekday()]


def browser_punch_direction(request):
    if not request.user.is_authenticated:
        return None
    employee = Employee._base_manager.filter(employee_user_id=request.user.pk).first()
    try:
        work = _browser_policy(request, employee)
    except PunchRejected:
        return None
    _, activities, _ = _workday_activities(employee, work, timezone.now())
    return "out" if activities.filter(clock_out__isnull=True).exists() else "in"


def prepare_browser_punch(request, employee, data, received_at):
    """Run under the same employee lock used for mobile punch ingestion."""
    work = _check_browser_access(request, employee)
    day, activities, schedule = _workday_activities(employee, work, received_at)
    active = activities.filter(clock_out__isnull=True).order_by("-pk").first()
    checking_in = data["punch_type"] == AttendancePunch.PunchType.CLOCK_IN
    if checking_in == bool(active):
        detail = "You are already clocked in." if checking_in else "Clock in before clocking out."
        raise PunchRejected("invalid_punch_state", detail, 409)

    attendance = Attendance._base_manager.select_for_update(of=("self",)).filter(
        employee_id=employee, attendance_date=day,
    ).first()
    if not attendance or not activities.exists():
        return None
    from .projection import (
        activity_links_match,
        attendance_has_manual_history,
        is_approved_missed_checkin,
    )

    linked = AttendancePunch.objects.filter(attendance=attendance, activity__isnull=False)
    if not linked.filter(projectable=False).exists() and activity_links_match(
        {activity.pk: activity for activity in activities}, linked.filter(projectable=True, review__isnull=True)
    ):
        return None

    if (
        not checking_in
        and activities.count() == 1
        and is_approved_missed_checkin(attendance, active)
    ):
        return None

    if attendance_has_manual_history(attendance):
        raise PunchRejected("attendance_locked", "This attendance record needs manual review.", 409)
    return LegacyWebDay(attendance, active, schedule)


def project_legacy_browser_punch(punch, legacy):
    """Continue a workday opened before it had a complete evidence ledger."""
    attendance = legacy.attendance
    local = punch.punched_at.astimezone(ZoneInfo(settings.TIME_ZONE))
    time_text = local.strftime("%H:%M")
    minimum, shift_start, shift_end = legacy.shift_schedule
    if punch.punch_type == AttendancePunch.PunchType.CLOCK_IN:
        clock_in_attendance_and_activity(
            employee=punch.employee,
            date_today=local.date(),
            attendance_date=attendance.attendance_date,
            day=attendance.attendance_day,
            now=time_text,
            shift=attendance.shift_id,
            minimum_hour=minimum,
            start_time=shift_start,
            end_time=shift_end,
            in_datetime=local,
        )
        activity = AttendanceActivity._base_manager.filter(
            employee_id=punch.employee, attendance_date=attendance.attendance_date,
            in_datetime=punch.punched_at,
        ).order_by("-pk").first()
    else:
        activity = legacy.open_activity
        attendance = clock_out_attendance_and_activity(
            punch.employee, local.date(), time_text, out_datetime=local,
            attendance_date=attendance.attendance_date,
        )
        if attendance is not None and shift_start != shift_end:
            early_out(attendance, shift_start, shift_end, attendance.shift_id)

    if attendance is None or activity is None:
        return None
    punch.activity = activity
    punch.save(update_fields=["activity"])
    return attendance


def _validation_response(serializer):
    error = next(iter(serializer.errors.values()))
    return Response({"detail": str(error[0])}, status=400)


def _rejected_response(error):
    return Response({"detail": str(error), "code": error.code}, status=error.status)


class BrowserAttendanceView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)


class BrowserPunchView(BrowserAttendanceView):
    parser_classes = (PunchMultipartParser,)

    def post(self, request):
        serializer = BrowserPunchSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_response(serializer)
        try:
            punch, duplicate = ingest_punch(
                request.user, serializer.validated_data, timezone.now(),
                AttendancePunch.Source.WEB, browser_request=request,
            )
        except PunchRejected as error:
            return _rejected_response(error)
        except (OperationalError, OSError):
            logger.exception("Could not save browser punch.")
            return Response({"detail": "Attendance is temporarily unavailable. Try again."}, status=503)

        if not duplicate:
            resolve_punch_address(punch)
        html = render_to_string(
            "attendance/components/in_out_component.html", request=request._request
        )
        return Response({"ok": True, "html": html}, status=200 if duplicate else 201)


class LocationPreviewThrottle(SimpleRateThrottle):
    rate = "30/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": "web_punch_location", "ident": request.user.pk}


class BrowserPunchLocationView(BrowserAttendanceView):
    parser_classes = (JSONParser,)
    throttle_classes = (LocationPreviewThrottle,)

    def post(self, request):
        serializer = BrowserLocationSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_response(serializer)
        employee = Employee._base_manager.filter(employee_user_id=request.user.pk).first()
        try:
            _check_browser_access(request, employee)
        except PunchRejected as error:
            return _rejected_response(error)
        return Response({"address": preview_punch_address(**serializer.validated_data)})
