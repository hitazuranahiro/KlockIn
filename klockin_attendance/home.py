from datetime import timedelta

from django.db.models import Count
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import time_format

from attendance.models import Attendance
from employee.models import Employee

from .dtr import _staff_scope, attendance_today
from .models import AttendancePunch


def render_home(request, *, team, employee=None, context=None):
    today = timezone.localdate()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    if employee is None:
        employee = getattr(request.user, "employee_get", None)

    team_attendance = team and request.user.has_perm("attendance.view_attendance")
    scope = (
        _staff_scope(request.user)
        if team_attendance
        else Employee.objects.filter(employee_user_id=request.user)
    )
    attendance = Attendance.objects.filter(employee_id__in=scope)
    values = dict(
        attendance.filter(
            attendance_date__range=(days[0], today), attendance_clock_in__isnull=False
        )
        .order_by()
        .values("attendance_date")
        .annotate(total=Count("employee_id", distinct=True))
        .values_list("attendance_date", "total")
    )
    peak = max(values.values(), default=1)
    week = [
        {"date": day, "count": values.get(day, 0), "height": 100 * values.get(day, 0) // peak}
        for day in days
    ]

    if team_attendance:
        totals = attendance_today(scope, today)
        employee_count = scope.filter(is_active=True).count()
        review_count = AttendancePunch.objects.filter(
            employee__in=scope,
            attendance__isnull=True,
            review__isnull=True,
            punched_at__date__range=(days[0], today),
        ).count()
        metrics = [
            ("Checked in", totals["Present"], "Today", "blue"),
            ("Currently in", totals["Currently in"], "Open shifts", "green"),
            ("Late arrivals", totals["Late"], "Today", "amber"),
        ]
    else:
        employee_count = None
        review_count = None
        record = attendance.filter(attendance_date=today).first()
        clock_in = record.attendance_clock_in if record else None
        clock_out = record.attendance_clock_out if record else None
        metrics = [
            ("First in", time_format(clock_in, "g:i A") if clock_in else None, "Today", "blue"),
            ("Last out", time_format(clock_out, "g:i A") if clock_out else None, "Today", "green"),
            ("Worked hours", record.attendance_worked_hour if record else None, "Recorded today", "ink"),
        ]

    return render(
        request,
        "klockin_attendance/home.html",
        {
            **(context or {}),
            "home_title": "Overview" if team else "My workspace",
            "employee": employee,
            "today": today,
            "week": week,
            "week_start": days[0],
            "has_check_ins": bool(values),
            "employee_count": employee_count,
            "review_count": review_count,
            "metrics": metrics,
            "team": team,
            "team_attendance": team_attendance,
            "timekeeping_url": reverse("klockin-attendance"),
        },
    )
