from datetime import datetime, time

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import OuterRef, Q, Subquery, Value
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import capfirst
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from attendance.models import Attendance, AttendanceActivity

from .dtr import _staff_scope
from .projection import CORRECTION_PREFIX


PAGE_SIZE = 25
SOURCE_LABELS = {"daily": "Daily attendance", "activity": "Attendance activity"}
ACTION_LABELS = {"+": "Created", "~": "Changed", "-": "Deleted"}
CONTEXT_FIELDS = {"employee_id", "created_at", "created_by", "modified_by"}


def profile_audit_url(user, employee_id):
    if _staff_scope(user).filter(pk=employee_id).exists():
        return reverse("klockin-employee-attendance-audit", args=[employee_id])
    return None


def _event_keys(history, source):
    return (
        history.order_by()
        .annotate(audit_source=Value(source))
        .values("history_id", "history_date", "audit_source")
    )


def _display_value(field, value):
    if value is None:
        return "—"
    if value == "":
        return "Blank"
    if field.choices:
        return dict(field.flatchoices).get(value, value)
    if field.is_relation:
        return f"#{value}"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S %Z")
    if isinstance(value, time):
        return value.isoformat(timespec="seconds")
    return value


def _field_changes(entry, previous):
    if entry.history_type == "-":
        before, after = entry, None
    else:
        before, after = previous if entry.history_type == "~" else None, entry

    changes = []
    for field in entry.tracked_fields:
        if field.primary_key or field.name in CONTEXT_FIELDS:
            continue
        old = getattr(before, field.attname, None)
        new = getattr(after, field.attname, None)
        if old != new:
            changes.append(
                {
                    "field": capfirst(field.verbose_name),
                    "before": _display_value(field, old),
                    "after": _display_value(field, new),
                }
            )
    return changes


def _history_events(history, ids, source):
    if not ids:
        return {}

    # A predecessor can be off-page. Keep it inside the same employee's history.
    previous_ids = (
        history.filter(id=OuterRef("id"))
        .filter(
            Q(history_date__lt=OuterRef("history_date"))
            | Q(history_date=OuterRef("history_date"), history_id__lt=OuterRef("history_id"))
        )
        .order_by("-history_date", "-history_id")
        .values("history_id")[:1]
    )
    entries = list(
        history.filter(history_id__in=ids)
        .select_related("history_user")
        .annotate(previous_id=Subquery(previous_ids))
    )
    previous = history.in_bulk(
        {entry.previous_id for entry in entries if entry.history_type == "~" and entry.previous_id}
    )
    return {
        entry.history_id: {
            "source": SOURCE_LABELS[source],
            "record_id": entry.id,
            "workday": entry.attendance_date,
            "action": ACTION_LABELS[entry.history_type],
            "timestamp": entry.history_date,
            "actor": entry.history_user,
            "reason": (entry.history_change_reason or "").removeprefix(CORRECTION_PREFIX)
            or entry.history_description,
            "changes": _field_changes(entry, previous.get(entry.previous_id)),
        }
        for entry in entries
    }


@login_required
@require_safe
@never_cache
def employee_attendance_audit(request, employee_id):
    if not request.user.has_perm("attendance.view_attendance"):
        raise PermissionDenied
    employee = get_object_or_404(_staff_scope(request.user), pk=employee_id)

    daily = Attendance.history.filter(employee_id=employee)
    activity = AttendanceActivity.history.filter(employee_id=employee)
    keys = (
        _event_keys(daily, "daily")
        .union(_event_keys(activity, "activity"), all=True)
        .order_by("-history_date", "audit_source", "-history_id")
    )
    page = Paginator(keys, PAGE_SIZE).get_page(request.GET.get("page"))
    keys = list(page.object_list)
    histories = {"daily": daily, "activity": activity}
    events = {
        source: _history_events(
            history,
            [key["history_id"] for key in keys if key["audit_source"] == source],
            source,
        )
        for source, history in histories.items()
    }
    entries = [events[key["audit_source"]][key["history_id"]] for key in keys]
    template = (
        "klockin_attendance/_employee_audit.html"
        if request.headers.get("HX-Request") == "true"
        else "klockin_attendance/employee_audit.html"
    )
    return render(request, template, {"employee": employee, "entries": entries, "page": page})
