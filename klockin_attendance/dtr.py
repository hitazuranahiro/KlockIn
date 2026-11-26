"""KlockIN attendance workspace, correction history, and DTR export."""

from calendar import monthrange
from datetime import date, datetime, timedelta

from django import forms
from cryptography.fernet import InvalidToken
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, IntegerField, Q, Sum, Value
from django.db.models.functions import Cast, StrIndex, Substr
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from attendance.methods.utils import format_time, strtime_seconds
from attendance.models import Attendance, AttendanceActivity, WorkRecords
from attendance.views.views import attendance_validate
from base.auth_backends import company_scoped_active
from base.methods import has_export_access
from employee.models import Employee
from klockin.export_preferences import resolve_export_options
from klockin.klockin_middlewares import get_selected_company

from .dtr_pdf import render_dtr_pdf
from .dtr_reports import report_response
from .models import AttendancePunch, EmployeeDevice, PunchReview
from .projection import CORRECTION_PREFIX


class AttendanceFilters(forms.Form):
    start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    employee = forms.ModelChoiceField(queryset=Employee.objects.none(), required=False)
    department = forms.ChoiceField(required=False)
    report = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Daily attendance"),
            ("late", "Late arrivals"),
            ("undertime", "Undertime"),
            ("overtime", "Overtime"),
            ("absent", "Absences"),
            ("summary", "Attendance summary"),
            ("unsynced", "Unsynced device queues"),
            ("pending", "Punches awaiting review"),
        ],
    )

    def clean(self):
        data = super().clean()
        start, end = data.get("start"), data.get("end")
        if start and end and not 0 <= (end - start).days <= 92:
            raise forms.ValidationError("Choose a date range of 93 days or fewer.")
        return data


def _staff_company_id(user):
    return (
        Employee._base_manager.filter(employee_user_id=user)
        .values_list("employee_work_info__company_id", flat=True)
        .first()
    )


def _staff_scope(user):
    if not user.has_perm("attendance.view_attendance"):
        return Employee.objects.none()
    if user.is_superuser:
        return Employee.objects.all()
    company_id = _staff_company_id(user)
    if company_id is None:
        return Employee.objects.none()
    return Employee.objects.filter(employee_work_info__company_id=company_id)


def _own_profile(user):
    return Employee._base_manager.filter(employee_user_id=user).first()


def _scope(user):
    if user.has_perm("attendance.view_attendance"):
        return _staff_scope(user)
    return Employee.objects.filter(employee_user_id=user)


def _can_view_evidence(user):
    if not user.has_perms(("attendance.view_attendance", "klockin_attendance.view_punch_evidence")):
        return False
    if user.is_superuser or not company_scoped_active() or get_selected_company() != "all":
        return True
    # The backend unions group permissions in All my companies. Timekeeping
    # reads the employee's work company, so both grants must apply there.
    company_id = _staff_company_id(user)
    if company_id is None:
        return False
    granted = Permission.objects.filter(
        Q(user=user) | Q(
            group__company_assignments__company_id=company_id,
            group__company_assignments__user=user,
        )
    ).filter(
        Q(content_type__app_label="attendance", codename="view_attendance")
        | Q(content_type__app_label="klockin_attendance", codename="view_punch_evidence")
    )
    return granted.values("codename").distinct().count() == 2


def _can_export(request):
    return request.user.has_perm("attendance.view_attendance") and has_export_access(
        request, Attendance
    )


def attendance_today(employee_scope, today):
    clocked = Attendance.objects.filter(
        employee_id__in=employee_scope,
        attendance_date=today,
        attendance_clock_in__isnull=False,
    )
    clock_counts = clocked.aggregate(
        present=Count("pk", distinct=True),
        late=Count("pk", filter=Q(late_come_early_out__type="late_come"), distinct=True),
    )
    return {
        "Present": clock_counts["present"],
        "Late": clock_counts["late"],
        "On time": clock_counts["present"] - clock_counts["late"],
        "Currently in": AttendanceActivity.objects.filter(
            employee_id__in=employee_scope,
            attendance_date__range=(today - timedelta(days=1), today),
            clock_out__isnull=True,
        )
        .values("employee_id")
        .distinct()
        .count(),
    }


def attendance_metrics(employee_scope, today, *, can_review):
    today_counts = attendance_today(employee_scope, today)
    reported_pending = EmployeeDevice.objects.filter(employee__in=employee_scope).aggregate(
        total=Sum("pending_punches")
    )["total"]
    return {
        **({"Total employees": employee_scope.filter(is_active=True).count()} if can_review else {}),
        "Present": today_counts["Present"],
        "Absent": WorkRecords.objects.filter(
            employee_id__in=employee_scope, date=today, work_record_type="ABS"
        ).count(),
        "Late": today_counts["Late"],
        "On time": today_counts["On time"],
        "Currently in": today_counts["Currently in"],
        "Last reported pending": reported_pending if reported_pending is not None else "—",
        "Awaiting review": AttendancePunch.objects.filter(
            employee__in=employee_scope, attendance__isnull=True, review__isnull=True
        ).count(),
    }


def _recorded_seconds(seconds, formatted):
    if seconds is not None:
        return max(0, seconds)
    try:
        return max(0, strtime_seconds(formatted)) if formatted else 0
    except (TypeError, ValueError):
        return 0


def _attendance_summary(employees, days, start, end):
    summaries = {
        employee.pk: {
            "employee": employee,
            "present": 0,
            "absent": 0,
            "late": 0,
            "worked": 0,
            "undertime": 0,
            "overtime": 0,
        }
        for employee in employees
    }
    if not summaries:
        return []

    records = days.filter(employee_id_id__in=summaries).order_by()
    for record in records.values(
        "employee_id_id",
        "attendance_clock_in",
        "attendance_clock_out",
        "attendance_worked_hour",
        "at_work_second",
        "minimum_hour",
        "attendance_overtime",
        "overtime_second",
    ):
        summary = summaries[record["employee_id_id"]]
        worked = _recorded_seconds(
            record["at_work_second"], record["attendance_worked_hour"]
        )
        summary["worked"] += worked
        summary["overtime"] += _recorded_seconds(
            record["overtime_second"], record["attendance_overtime"]
        )
        if record["attendance_clock_in"] is not None:
            summary["present"] += 1
            if record["attendance_clock_out"] is not None:
                minimum = _recorded_seconds(None, record["minimum_hour"])
                summary["undertime"] += max(0, minimum - worked)

    late_counts = (
        records.filter(late_come_early_out__type="late_come")
        .values("employee_id_id")
        .annotate(day_count=Count("attendance_date", distinct=True))
        .values_list("employee_id_id", "day_count")
    )
    for employee_id, count in late_counts:
        summaries[employee_id]["late"] = count

    absence_counts = (
        WorkRecords.objects.filter(
            employee_id_id__in=summaries,
            date__range=(start, end),
            work_record_type="ABS",
        )
        .order_by()
        .values("employee_id_id")
        .annotate(day_count=Count("date", distinct=True))
        .values_list("employee_id_id", "day_count")
    )
    for employee_id, count in absence_counts:
        summaries[employee_id]["absent"] = count

    for summary in summaries.values():
        for duration in ("worked", "undertime", "overtime"):
            summary[duration] = format_time(summary[duration])
    return list(summaries.values())


def _report_filters(query, employee_scope, today):
    defaults = {"start": today.isoformat(), "end": today.isoformat()}
    filters = AttendanceFilters(query or defaults)
    filters.fields["employee"].queryset = employee_scope.order_by("employee_first_name")
    departments = (
        employee_scope.exclude(employee_work_info__department_id=None)
        .values_list(
            "employee_work_info__department_id",
            "employee_work_info__department_id__department",
        )
        .order_by("employee_work_info__department_id__department")
        .distinct()
    )
    filters.fields["department"].choices = [("", "All departments"), *departments]
    return filters


def _filtered_scope(employee_scope, data):
    if data["employee"] is not None:
        employee_scope = employee_scope.filter(pk=data["employee"].pk)
    if data["department"]:
        employee_scope = employee_scope.filter(
            employee_work_info__department_id=data["department"]
        )
    return employee_scope


def _report_query(employee_scope, data):
    start, end, report = data["start"], data["end"], data["report"]
    days = Attendance.objects.filter(
        employee_id__in=employee_scope, attendance_date__range=(start, end),
    ).select_related("employee_id", "employee_id__employee_work_info__department_id")
    if report == "summary":
        employees = employee_scope.select_related(
            "employee_work_info__department_id"
        ).order_by("employee_first_name", "employee_last_name", "pk")
        return employees, days
    if report == "unsynced":
        devices = EmployeeDevice.objects.filter(employee__in=employee_scope).filter(
            Q(queue_reported_at__date__range=(start, end)) | Q(queue_reported_at__isnull=True)
        ).select_related("employee").order_by("employee__employee_first_name", "pk")
        return devices, days
    if report == "pending":
        pending = AttendancePunch.objects.filter(
            employee__in=employee_scope, attendance__isnull=True, review__isnull=True,
            punched_at__date__range=(start, end),
        ).select_related("employee").order_by("-punched_at", "-pk")
        return pending, days
    if report == "absent":
        absences = WorkRecords.objects.filter(
            employee_id__in=employee_scope, date__range=(start, end), work_record_type="ABS",
        ).select_related("employee_id").order_by("-date", "pk")
        return absences, days
    if report == "late":
        days = days.filter(late_come_early_out__type="late_come").distinct()
    if report == "undertime":
        separator = StrIndex("minimum_hour", Value(":"))
        minimum = 3600 * Cast(
            Substr("minimum_hour", 1, separator - 1), IntegerField()
        ) + 60 * Cast(Substr("minimum_hour", separator + 1, 2), IntegerField())
        days = (
            days.filter(
                attendance_clock_out__isnull=False,
                minimum_hour__regex=r"^[0-9]+:[0-9]{2}(:[0-9]{2})?$",
            )
            .annotate(minimum_seconds=minimum)
            .filter(at_work_second__lt=F("minimum_seconds"))
        )
    if report == "overtime":
        days = days.filter(overtime_second__gt=0)
    return days.order_by("-attendance_date", "employee_id__employee_first_name", "pk"), days


@login_required
@require_safe
@never_cache
def attendance_workspace(request):
    today = timezone.localdate()
    employee_scope = _scope(request.user)
    can_review = request.user.has_perm("attendance.view_attendance")
    can_view_evidence = _can_view_evidence(request.user)
    query = request.GET.copy()
    if not query:
        query.update({"start": today.isoformat(), "end": today.isoformat()})
    filters = _report_filters(query, employee_scope, today)
    context = {
        "filters": filters,
        "can_review": can_review,
        "can_view_evidence": can_view_evidence,
        "can_export": _can_export(request),
        "month_value": today.strftime("%Y-%m"),
        "profile": _own_profile(request.user),
    }
    if not filters.is_valid():
        return render(request, "klockin_attendance/workspace.html", context)
    data = filters.cleaned_data
    employee_scope = _filtered_scope(employee_scope, data)
    report = data["report"]
    rows, days = _report_query(employee_scope, data)
    if report in {"", "late", "undertime", "overtime"}:
        rows = rows.prefetch_related("klockin_punches")
    query.pop("page", None)
    page = Paginator(rows, 25).get_page(request.GET.get("page"))
    context.update(
        metrics=attendance_metrics(employee_scope, today, can_review=can_review),
        report=report,
        report_label=dict(filters.fields["report"].choices)[report],
        report_start=data["start"],
        report_end=data["end"],
        page=page,
        query_string=query.urlencode(),
    )
    if report == "summary":
        context["summary_rows"] = _attendance_summary(page, days, data["start"], data["end"])
    return render(request, "klockin_attendance/workspace.html", context)


@login_required
@require_safe
@never_cache
def attendance_export(request):
    if not _can_export(request):
        raise PermissionDenied
    query = request.GET.copy()
    format = query.get("format", "csv").lower()
    if format not in {"csv", "xlsx", "pdf", "print"}:
        return HttpResponseBadRequest("Choose CSV, Excel, PDF, or print.")
    query.pop("format", None)
    today = timezone.localdate()
    employee_scope = _staff_scope(request.user)
    filters = _report_filters(query, employee_scope, today)
    if not filters.is_valid():
        return HttpResponseBadRequest("Choose valid attendance filters and a date range of 93 days or fewer.")
    data = filters.cleaned_data
    report = data["report"]
    rows, days = _report_query(_filtered_scope(employee_scope, data), data)
    limit = 500 if format in {"pdf", "print"} else 5000
    rows = list(rows[:limit + 1])
    if len(rows) > limit:
        return HttpResponseBadRequest(f"This format supports {limit} rows. Narrow the report filters.")
    if report == "summary":
        rows = _attendance_summary(rows, days, data["start"], data["end"])
    return report_response(
        request, report, dict(filters.fields["report"].choices)[report], rows, data,
        format, include_device=_can_view_evidence(request.user),
    )

@login_required
@require_safe
@never_cache
def punch_selfie(request, punch_uuid):
    if not _can_view_evidence(request.user):
        raise PermissionDenied
    punch = get_object_or_404(
        AttendancePunch.objects.filter(employee__in=_staff_scope(request.user)),
        pk=punch_uuid,
    )
    try:
        image = punch.punch_selfie.open("rb")
    except (OSError, InvalidToken) as exc:
        raise Http404("Selfie unavailable.") from exc
    content_type = (
        "image/png"
        if punch.punch_selfie.name.lower().endswith(".png")
        else "image/jpeg"
    )
    response = FileResponse(image, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    return response


class PunchReviewForm(forms.Form):
    attendance = forms.ModelChoiceField(
        queryset=Attendance.objects.none(), label="Daily attendance record"
    )
    reason = forms.CharField(
        label="Reason for linking",
        min_length=3,
        max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, eligible_attendance, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attendance"].queryset = eligible_attendance


def _eligible_attendance(punch):
    captured = timezone.localtime(punch.punched_at, timezone.get_default_timezone())
    captured_date = captured.date()
    scope = Attendance.objects.filter(employee_id_id=punch.employee_id)
    previous_date = captured_date - timedelta(days=1)
    previous = scope.filter(attendance_date=previous_date).first()
    eligible_dates = [captured_date]
    if previous and (
        previous.attendance_clock_out_date == captured_date
        or (captured.hour < 12 and previous.is_night_shift())
    ):
        eligible_dates.append(previous_date)
    return scope.filter(attendance_date__in=eligible_dates).order_by("-attendance_date")


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
@never_cache
def punch_review(request, punch_uuid):
    can_edit = request.user.has_perm("attendance.change_attendance")
    if not _can_view_evidence(request.user) or (request.method == "POST" and not can_edit):
        raise PermissionDenied

    employee_scope = _staff_scope(request.user)
    punches = AttendancePunch.objects.filter(
        employee__in=employee_scope
    ).select_related("employee", "review__reviewed_by")
    punch = get_object_or_404(punches, pk=punch_uuid)
    review = getattr(punch, "review", None)
    form = None

    if request.method == "POST":
        with transaction.atomic():
            # Ingestion and DTR correction take the employee lock first.
            get_object_or_404(
                employee_scope.select_for_update(of=("self",)), pk=punch.employee_id
            )
            punch = get_object_or_404(
                punches.select_for_update(of=("self",)), pk=punch_uuid
            )
            if punch.attendance_id or getattr(punch, "review", None):
                messages.info(request, "This punch has already been linked.")
                return redirect("klockin-punch-review", punch_uuid=punch_uuid)
            eligible = _eligible_attendance(punch)
            form = PunchReviewForm(request.POST, eligible_attendance=eligible)
            if form.is_valid():
                target = (
                    eligible.select_for_update(of=("self",))
                    .filter(pk=form.cleaned_data["attendance"].pk)
                    .first()
                )
                if target is not None:
                    PunchReview.objects.create(
                        punch=punch,
                        attendance=target,
                        attendance_reference=target.pk,
                        attendance_date=target.attendance_date,
                        reviewed_by=request.user,
                        reason=form.cleaned_data["reason"],
                    )
                    messages.success(request, "Supplementary punch evidence linked.")
                    return redirect("klockin-attendance-detail", pk=target.pk)
                form.add_error("attendance", "That daily record is no longer available.")
    elif can_edit and review is None and not punch.attendance_id:
        form = PunchReviewForm(eligible_attendance=_eligible_attendance(punch))

    return render(
        request,
        "klockin_attendance/punch_review.html",
        {
            "punch": punch,
            "review": review,
            "form": form,
            "has_eligible_attendance": (
                form is not None and form.fields["attendance"].queryset.exists()
            ),
            "can_create_attendance": request.user.has_perm("attendance.add_attendance"),
        },
    )


class CorrectionForm(forms.Form):
    clock_in = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    clock_out = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    next_day = forms.BooleanField(required=False, label="Checkout on the following day")
    worked_minutes = forms.IntegerField(
        min_value=0, max_value=1440, label="Worked minutes"
    )
    reason = forms.CharField(
        min_length=3, max_length=200, widget=forms.Textarea(attrs={"rows": 3})
    )

    def clean(self):
        data = super().clean()
        clock_in, clock_out = data.get("clock_in"), data.get("clock_out")
        if clock_in is not None and clock_out is not None:
            today = date(2000, 1, 1)
            end = today + timedelta(days=int(data["next_day"]))
            minutes = (
                datetime.combine(end, clock_out) - datetime.combine(today, clock_in)
            ).total_seconds() / 60
            if not 0 < minutes <= 1440:
                raise forms.ValidationError(
                    "Checkout must follow check-in within 24 hours."
                )
            if data.get("worked_minutes", 0) > minutes:
                self.add_error(
                    "worked_minutes", "Worked minutes cannot exceed the elapsed time."
                )
        return data


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
@never_cache
def attendance_detail(request, pk):
    can_review = request.user.has_perm("attendance.view_attendance")
    can_edit = can_review and request.user.has_perm("attendance.change_attendance")
    attendance = get_object_or_404(
        Attendance.objects.filter(employee_id__in=_scope(request.user)).select_related(
            "employee_id"
        ),
        pk=pk,
    )
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        form = CorrectionForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                Employee._base_manager.select_for_update().get(
                    pk=attendance.employee_id_id
                )
                attendance = Attendance.objects.select_for_update(of=("self",)).get(
                    pk=pk
                )
                clock_in_date = (
                    attendance.attendance_clock_in_date or attendance.attendance_date
                )
                attendance.attendance_clock_in_date = clock_in_date
                attendance.attendance_clock_in = data["clock_in"]
                attendance.attendance_clock_out_date = clock_in_date + timedelta(
                    days=int(data["next_day"])
                )
                attendance.attendance_clock_out = data["clock_out"]
                attendance.attendance_worked_hour = format_time(
                    data["worked_minutes"] * 60
                )
                attendance.attendance_validated = attendance_validate(attendance)
                attendance.attendance_overtime_approve = False
                attendance._history_user = request.user
                attendance._change_reason = CORRECTION_PREFIX + data["reason"]
                attendance.save()
            messages.success(request, "Attendance correction saved.")
            return redirect("klockin-attendance-detail", pk=pk)
    else:
        form = CorrectionForm(
            initial={
                "clock_in": attendance.attendance_clock_in,
                "clock_out": attendance.attendance_clock_out,
                "next_day": (
                    attendance.attendance_clock_out_date is not None
                    and attendance.attendance_clock_out_date
                    > (
                        attendance.attendance_clock_in_date
                        or attendance.attendance_date
                    )
                ),
                "worked_minutes": (attendance.at_work_second or 0) // 60,
            }
        )

    can_view_evidence = _can_view_evidence(request.user)
    audits = []
    punches = ()
    punch_reviews = ()
    if can_view_evidence:
        punches = attendance.klockin_punches.order_by("punched_at", "pk")
        punch_reviews = (
            attendance.klockin_punch_reviews.filter(
                punch__employee_id=attendance.employee_id_id
            )
            .select_related("punch", "reviewed_by")
            .order_by("-reviewed_at", "-pk")
        )
    if can_review:
        history = list(
            attendance.history.select_related("history_user").order_by(
                "-history_date", "-pk"
            )[:31]
        )
        fields = (
            "attendance_clock_in_date",
            "attendance_clock_in",
            "attendance_clock_out_date",
            "attendance_clock_out",
            "attendance_worked_hour",
            "attendance_validated",
            "attendance_overtime_approve",
        )
        for after, before in zip(history, history[1:]):
            changes = after.diff_against(before, included_fields=fields).changes
            if changes:
                audits.append((after, changes))
    return render(
        request,
        "klockin_attendance/detail.html",
        {
            "attendance": attendance,
            "can_review": can_review,
            "can_view_evidence": can_view_evidence,
            "form": form if can_edit else None,
            "audits": audits,
            "punches": punches,
            "punch_reviews": punch_reviews,
        },
    )


@login_required
@require_safe
@never_cache
def monthly_dtr(request, employee_id):
    employee = get_object_or_404(_scope(request.user), pk=employee_id)
    try:
        month = requested_dtr_month(request.GET)
        if request.GET.get("configure") == "1":
            from klockin.export_views import render_export_setup

            return render_export_setup(
                request, "dtr", employee.pk, month=month.strftime("%Y-%m")
            )
        return monthly_dtr_document(request.user, employee, month, request.GET)
    except ValidationError as error:
        if request.GET.get("preview") == "1":
            return HttpResponseBadRequest(error.messages[0], content_type="text/plain")
        return render(
            request,
            "klockin_attendance/workspace.html",
            {
                "report_error": error.messages[0],
                "profile": _own_profile(request.user),
            },
            status=400,
        )


def requested_dtr_month(query):
    month_text = query.get("month", timezone.localdate().strftime("%Y-%m"))
    try:
        return datetime.strptime(month_text, "%Y-%m").date()
    except ValueError as error:
        raise ValidationError("Choose a valid month.") from error


def monthly_dtr_document(user, employee, month, query):
    options = resolve_export_options(user, "dtr", query)
    last_day = monthrange(month.year, month.month)[1]
    month_end = month.replace(day=last_day)
    rows = {
        row.attendance_date.day: row
        for row in Attendance.objects.filter(
            employee_id=employee, attendance_date__range=(month, month_end)
        )
    }
    use_first_last = options["layout"] == "first-last"
    intervals = {}
    if not use_first_last:
        for interval in AttendanceActivity.objects.filter(
            employee_id=employee, attendance_date__range=(month, month_end)
        ).order_by("attendance_date", "clock_in_date", "clock_in"):
            intervals.setdefault(interval.attendance_date.day, []).append(interval)
    company = employee.get_company() if options["show_company"] else None
    return render_dtr_pdf(
        employee, month, last_day, rows, intervals, use_first_last,
        orientation=options["orientation"],
        company_name=company.company if company else "",
        show_undertime=options["show_undertime"],
        note=options["note"] if options["show_notes"] else "",
        preview=query.get("preview") == "1",
    )
