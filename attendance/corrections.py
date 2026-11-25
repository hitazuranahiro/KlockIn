"""Record reasons and snapshots for human attendance corrections."""

import json

from django.db import transaction
from django.db.models import ForeignKey
from django.utils.translation import gettext_lazy as _

from attendance.models import AttendanceActivity
from employee.models import Employee


CORRECTION_PREFIX = "KlockIN correction: "
CORRECTION_REASON_LIMIT = 200


def mark_correction(instance, actor, reason):
    instance._history_user = actor
    instance._change_reason = CORRECTION_PREFIX + str(reason)


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
