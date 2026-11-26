"""Record reasons and snapshots for human attendance corrections."""

import json
from datetime import UTC, datetime, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import ForeignKey
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from attendance.methods.utils import format_time
from attendance.models import Attendance, AttendanceActivity, AttendanceMissedPunchRequest
from employee.models import Employee, EmployeeWorkInformation
from notifications.signals import notify


CORRECTION_PREFIX = "KlockIN correction: "
MISSED_PUNCH_CORRECTION_PREFIX = CORRECTION_PREFIX + "Approved missed punch: "
CORRECTION_REASON_LIMIT = 200


def mark_correction(instance, actor, reason, *, prefix=CORRECTION_PREFIX):
    instance._history_user = actor
    instance._change_reason = prefix + str(reason)


def _preserve_previous_state(instance):
    latest = instance.history.order_by("-history_date", "-pk").first()
    history_fields = {field.attname for field in instance.history.model._meta.fields}
    if latest is None or any(
        getattr(instance, field.attname) != getattr(latest, field.attname)
        for field in instance._meta.fields
        if field.attname in history_fields
    ):
        instance.history.bulk_history_create(
            [instance], update=True, default_change_reason="State before correction"
        )


def _lock_attendance(instance, replacement_employee_id=None):
    records = type(instance)._base_manager
    original_employee_id = records.values_list("employee_id_id", flat=True).get(
        pk=instance.pk
    )
    employee_ids = {
        original_employee_id, instance.employee_id_id, replacement_employee_id
    } - {None}
    list(
        Employee._base_manager.select_for_update()
        .filter(pk__in=employee_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    return records.select_for_update(of=("self",)).get(pk=instance.pk)


@transaction.atomic
def save_attendance_correction(
    instance, actor, reason, save, *, replacement_employee_id=None
):
    before = _lock_attendance(instance, replacement_employee_id)
    _preserve_previous_state(before)
    mark_correction(instance, actor, reason)
    return save()


def _apply_requested_values(attendance):
    if attendance.requested_data is None:
        return
    for name, value in json.loads(attendance.requested_data).items():
        field = attendance._meta.get_field(name)
        converter = field.target_field if isinstance(field, ForeignKey) else field
        # Older request snapshots use both "None" and empty strings for
        # optional relations.
        if value == "None" or (
            value == "" and isinstance(field, ForeignKey) and field.null
        ):
            value = None
        setattr(attendance, field.attname, converter.to_python(value))


@transaction.atomic
def apply_attendance_request_approval(
    attendance, actor, *, approved_by=None, finalize_created=False
):
    """Approve a pending request and write history for the daily row and activity."""
    attendance = _lock_attendance(attendance)
    if not attendance.is_validate_request:
        return None

    previous_clock_in = {
        "attendance_date": attendance.attendance_date,
        "clock_in_date": attendance.attendance_clock_in_date,
        "clock_in": attendance.attendance_clock_in,
    }
    reason = (attendance.request_description or "").strip() or _(
        "Approved attendance correction request"
    )
    _preserve_previous_state(attendance)
    _apply_requested_values(attendance)
    attendance.attendance_validated = True
    attendance.is_validate_request_approved = True
    attendance.is_validate_request = False
    attendance.request_description = None
    if approved_by is not None:
        attendance.approved_by = approved_by
    if finalize_created and attendance.request_type == "create_request":
        attendance.request_type = "created_request"
        attendance.requested_data = None
    mark_correction(attendance, actor, reason)
    attendance.save()

    if attendance.attendance_clock_in is not None and (
        attendance.attendance_clock_out is None
        or attendance.attendance_clock_out_date is None
    ):
        activities = list(
            AttendanceActivity.objects.select_for_update(of=("self",)).filter(
                employee_id_id=attendance.employee_id_id, **previous_clock_in
            )
        )
        activity_values = {
            "employee_id_id": attendance.employee_id_id,
            "attendance_date": attendance.attendance_date,
            "clock_in_date": attendance.attendance_clock_in_date,
            "clock_in": attendance.attendance_clock_in,
        }
        if not activities:
            activities = [AttendanceActivity()]
        for activity in activities:
            if activity.pk is not None:
                _preserve_previous_state(activity)
            for field, value in activity_values.items():
                setattr(activity, field, value)
            mark_correction(activity, actor, reason)
            activity.save()
    return attendance


class MissedPunchConflict(ValidationError):
    """The record changed or a pending request already exists."""


def _employee_for(user):
    return Employee._base_manager.filter(
        employee_user_id=user.pk, employee_user_id__is_active=True, is_active=True,
    ).first()


def _company_for(employee):
    return (
        EmployeeWorkInformation._base_manager.filter(employee_id=employee)
        .values_list("company_id_id", flat=True)
        .first()
    )


def _direct_reports(manager):
    company_id = _company_for(manager) if manager is not None else None
    if company_id is None:
        return Employee._base_manager.none()
    return Employee._base_manager.filter(
        is_active=True,
        employee_user_id__is_active=True,
        employee_work_info__reporting_manager_id=manager,
        employee_work_info__company_id_id=company_id,
    ).exclude(pk=manager.pk)


def missed_punch_reporting_manager(user):
    employee = _employee_for(user)
    if employee is None:
        return None
    work = (
        EmployeeWorkInformation._base_manager.filter(employee_id=employee)
        .select_related("reporting_manager_id__employee_user_id")
        .first()
    )
    if work is None or work.company_id_id is None or work.reporting_manager_id is None:
        return None
    manager = work.reporting_manager_id
    if (
        manager.pk != employee.pk
        and manager.is_active
        and manager.employee_user_id_id is not None
        and manager.employee_user_id.is_active
        and _company_for(manager) == work.company_id_id
    ):
        return manager
    return None


def can_review_missed_punch_requests(user):
    return _direct_reports(_employee_for(user)).exists()


def missed_punch_requests(user, *, approvals=False):
    employee = _employee_for(user)
    requests = AttendanceMissedPunchRequest.objects.select_related("employee", "decided_by")
    if employee is None:
        return requests.none()
    if approvals:
        return requests.filter(employee__in=_direct_reports(employee))
    return requests.filter(employee=employee)


def _local_stamp(day, clock):
    if day is None or clock is None:
        return None
    return datetime.combine(day, clock, tzinfo=timezone.get_default_timezone())


def _activity_stamp(activity, direction):
    return getattr(activity, f"{direction}_datetime") or _local_stamp(
        getattr(activity, f"clock_{direction}_date") or activity.attendance_date,
        getattr(activity, f"clock_{direction}"),
    )


def _missed_punch_inputs(work_date, time_in, time_out, clock_in_date, clock_out_date):
    today = timezone.localdate(timezone=timezone.get_default_timezone())
    if work_date is None or work_date > today:
        raise ValidationError(_("Select a work date that has already started."))
    if time_in is None and time_out is None:
        raise ValidationError(_("Enter a missing check-in, check-out, or both."))

    for clock, day in ((time_in, clock_in_date), (time_out, clock_out_date)):
        if clock is None and day is not None:
            raise ValidationError(_("A punch date requires a punch time."))
        if clock is None:
            continue
        if clock.tzinfo is not None:
            raise ValidationError(_("Enter punch times in your attendance time zone."))
        day = day or work_date
        if day != work_date and day - work_date != timedelta(days=1):
            raise ValidationError(_("Punch dates must be on the workday or the next day."))
        if _local_stamp(day, clock) > timezone.now():
            raise ValidationError(_("A requested punch cannot be in the future."))

    return (
        _local_stamp(clock_in_date or work_date, time_in),
        _local_stamp(clock_out_date or work_date, time_out),
    )


def _locked_day(employee, work_date):
    daily = Attendance._base_manager.select_for_update(of=("self",)).filter(
        employee_id=employee, attendance_date=work_date,
    ).first()
    activities = list(
        AttendanceActivity._base_manager.select_for_update(of=("self",))
        .filter(employee_id=employee, attendance_date=work_date)
        .order_by("clock_in_date", "clock_in", "pk")
    )
    return daily, activities


def _lock_missed_punch_people(employee_id, manager_id):
    employee_ids = (employee_id, manager_id)
    list(
        Employee._base_manager.select_for_update(of=("self",))
        .filter(pk__in=employee_ids).order_by("pk").values_list("pk", flat=True)
    )
    list(
        EmployeeWorkInformation._base_manager.select_for_update(of=("self",))
        .filter(employee_id_id__in=employee_ids).order_by("pk").values_list("pk", flat=True)
    )


def _validate_missing_times(daily, activities, requested_in, requested_out):
    if daily is not None and daily.is_validate_request:
        raise MissedPunchConflict(_("An attendance correction is already pending for this workday."))
    existing_in = getattr(daily, "attendance_clock_in", None)
    existing_out = getattr(daily, "attendance_clock_out", None)
    if requested_in is not None and (existing_in is not None or activities):
        raise MissedPunchConflict(_("A check-in is already recorded for this workday."))
    if requested_out is not None and existing_out is not None:
        raise MissedPunchConflict(_("A check-out is already recorded for this workday."))

    opened = [row for row in activities if row.clock_out is None and row.out_datetime is None]
    if requested_out is not None and activities and len(opened) != 1:
        raise MissedPunchConflict(_("This workday does not have one open activity to close."))
    activity = opened[0] if opened else None
    time_in = requested_in
    time_out = requested_out
    if existing_in is not None:
        time_in = _activity_stamp(activity, "in") if activity is not None else _local_stamp(
            daily.attendance_clock_in_date or daily.attendance_date, existing_in,
        )
    if existing_out is not None:
        time_out = _local_stamp(daily.attendance_clock_out_date or daily.attendance_date, existing_out)
    if requested_out is not None and time_in is None:
        raise ValidationError(_("Enter a check-in as well when none is recorded."))
    if time_in is not None and time_out is not None:
        duration = time_out.astimezone(UTC) - time_in.astimezone(UTC)
        if not timedelta(0) < duration <= timedelta(days=1):
            raise ValidationError(_("Check-out must follow check-in within 24 hours."))
    if requested_out is not None and any(
        end is not None and end > time_in
        for end in (_activity_stamp(row, "out") for row in activities if row != activity)
    ):
        raise MissedPunchConflict(_("The requested check-out overlaps another activity."))
    return activity, time_in, time_out


def _notify_missed_punch(actor, recipient, verb):
    if recipient is not None:
        transaction.on_commit(
            lambda: notify.send(actor, recipient=recipient, verb=str(verb), redirect="/timekeeping/missed-punches/"),
            robust=True,
        )


@transaction.atomic
def submit_missed_punch_request(
    user, *, attendance_date, time_in=None, time_out=None,
    clock_in_date=None, clock_out_date=None, reason,
):
    employee = _employee_for(user)
    if employee is None:
        raise PermissionDenied
    manager = missed_punch_reporting_manager(user)
    if manager is None:
        raise ValidationError(_("A reporting manager in your company is required."))
    _lock_missed_punch_people(employee.pk, manager.pk)
    if missed_punch_reporting_manager(user) != manager:
        raise MissedPunchConflict(_("Your reporting manager changed. Reload and submit again."))
    reason = (reason or "").strip()
    if not 3 <= len(reason) <= CORRECTION_REASON_LIMIT:
        raise ValidationError(_("Enter a reason between 3 and 200 characters."))
    requested_in, requested_out = _missed_punch_inputs(
        attendance_date, time_in, time_out, clock_in_date, clock_out_date,
    )
    if AttendanceMissedPunchRequest.objects.filter(
        employee=employee, attendance_date=attendance_date,
        status=AttendanceMissedPunchRequest.Status.PENDING,
    ).exists():
        raise MissedPunchConflict(_("You already have a pending request for this workday."))
    daily, activities = _locked_day(employee, attendance_date)
    _validate_missing_times(daily, activities, requested_in, requested_out)
    request = AttendanceMissedPunchRequest.objects.create(
        employee=employee, attendance_date=attendance_date,
        time_in=time_in, time_out=time_out,
        clock_in_date=requested_in.date() if requested_in is not None else None,
        clock_out_date=requested_out.date() if requested_out is not None else None,
        reason=reason,
    )
    _notify_missed_punch(user, manager.employee_user_id, _("submitted a missed punch request"))
    return request


def _apply_missed_punch(request, user):
    from attendance.views.clock_in_out import early_out, late_come
    from klockin_attendance.breaks import close_attendance_break, tracked_break_ranges
    from klockin_attendance.models import AttendancePolicy, MobileDayPolicy
    from klockin_attendance.policies import duration_totals
    from klockin_attendance.workday import shift_schedules

    employee = request.employee
    work_date = request.attendance_date
    requested_in, requested_out = _missed_punch_inputs(
        work_date, request.time_in, request.time_out, request.clock_in_date, request.clock_out_date,
    )
    daily, activities = _locked_day(employee, work_date)
    activity, time_in, time_out = _validate_missing_times(daily, activities, requested_in, requested_out)
    work = EmployeeWorkInformation._base_manager.get(employee_id=employee)
    shift_id = work.shift_id_id if daily is None else daily.shift_id_id
    minimum_hour, shift_start, shift_end = shift_schedules(shift_id)[work_date.weekday()]
    if daily is None:
        daily = Attendance(
            employee_id=employee, attendance_date=work_date,
            shift_id_id=work.shift_id_id, work_type_id_id=work.work_type_id_id,
            minimum_hour=minimum_hour,
        )
    else:
        _preserve_previous_state(daily)

    for direction, stamp in (("in", requested_in), ("out", requested_out)):
        if stamp is not None:
            setattr(daily, f"attendance_clock_{direction}", stamp.time())
            setattr(daily, f"attendance_clock_{direction}_date", stamp.date())

    if activity is None:
        activity = AttendanceActivity(employee_id=employee, attendance_date=work_date)
        activities.append(activity)
        activity.in_datetime = time_in
        activity.clock_in = time_in.time()
        activity.clock_in_date = time_in.date()
    else:
        _preserve_previous_state(activity)
    if time_out is not None:
        activity.out_datetime = time_out
        activity.clock_out = time_out.time()
        activity.clock_out_date = time_out.date()
        if daily.pk is not None:
            close_attendance_break(daily, time_out)

    policy_snapshot = getattr(daily, "mobile_policy", None)
    policy = policy_snapshot or AttendancePolicy._base_manager.filter(company_id=work.company_id_id).first()
    zone = timezone.get_default_timezone()
    intervals = []
    for row in activities:
        interval_in, interval_out = _activity_stamp(row, "in"), _activity_stamp(row, "out")
        if interval_in is None or interval_out is None:
            continue
        intervals.append((interval_in.astimezone(zone), interval_out.astimezone(zone)))
    seconds, _ = duration_totals(intervals, policy, excluded_ranges=tracked_break_ranges(daily))
    daily.attendance_worked_hour = format_time(seconds)
    daily.attendance_validated = time_out is not None
    mark_correction(daily, user, request.reason, prefix=MISSED_PUNCH_CORRECTION_PREFIX)
    daily.save()
    if policy_snapshot is None and policy is not None:
        MobileDayPolicy.objects.create(
            attendance=daily, mode=policy.mode, break_start=policy.break_start, break_end=policy.break_end,
        )
    activity.shift_day = daily.attendance_day
    mark_correction(activity, user, request.reason, prefix=MISSED_PUNCH_CORRECTION_PREFIX)
    activity.save()
    if shift_start != shift_end:
        if requested_in is not None and not daily.late_come_early_out.filter(type="late_come").exists():
            late_come(daily, shift_start, shift_end, daily.shift_id)
        if requested_out is not None and not daily.late_come_early_out.filter(type="early_out").exists():
            early_out(daily, shift_start, shift_end, daily.shift_id)
    return daily


@transaction.atomic
def decide_missed_punch_request(user, request_id, *, approve):
    manager = _employee_for(user)
    if manager is None:
        raise Http404
    try:
        pending = missed_punch_requests(user, approvals=True).get(pk=request_id)
    except AttendanceMissedPunchRequest.DoesNotExist:
        raise Http404 from None

    _lock_missed_punch_people(pending.employee_id, manager.pk)
    if _employee_for(user) != manager:
        raise Http404
    try:
        pending = missed_punch_requests(user, approvals=True).select_for_update(of=("self",)).get(pk=request_id)
    except AttendanceMissedPunchRequest.DoesNotExist:
        raise Http404 from None
    if pending.status != AttendanceMissedPunchRequest.Status.PENDING:
        raise MissedPunchConflict(_("This request has already been decided."))
    if approve:
        pending.attendance = _apply_missed_punch(pending, user)
    pending.status = AttendanceMissedPunchRequest.Status.APPROVED if approve else AttendanceMissedPunchRequest.Status.REJECTED
    pending.decided_at = timezone.now()
    pending.decided_by = manager
    pending.save(update_fields=["attendance", "status", "decided_at", "decided_by"])
    verb = _("approved your missed punch request") if approve else _("rejected your missed punch request")
    _notify_missed_punch(user, pending.employee.employee_user_id, verb)
    return pending
