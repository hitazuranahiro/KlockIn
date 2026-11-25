"""Update the bundled tours for the KlockIN workspace (Tomeku, 2026-11-25)."""

import re

from django.db import migrations


BRAND = re.compile(r"\bHorilla(?: HRMS| HR)?\b", re.IGNORECASE)
BRANDED_DEFAULTS = (
    "getting-started",
    "dashboard-overview",
    "settings-company",
    "payroll-overview",
)

OVERVIEW = (
    ("Navigation", "Workspace navigation", "Use the sidebar to switch between KlockIN modules.", ""),
    ("Key metrics at a glance", "Today’s attendance", "Check today’s attendance and open shifts at a glance.", ".ki-home-metrics, #md-kpi-grid"),
    ("Make it yours", "Detailed analytics", "Open analytics to explore charts, date filters, and dashboard preferences.", ".ki-home-heading a, #md-open-customize"),
    ("Live charts", "Attendance trends", "Use the chart and its linked records to investigate changes in attendance.", ".ki-home-trend, #department_headcount"),
    ("Act without leaving", "Follow up", "Use the shortcuts to review punches, sync reports, or pending actions.", ".ki-home-quick, #md-pending-approvals"),
    ("Top bar", "Workspace tools", "Open notifications, switch company, or manage your account from the header.", "#header"),
    ("Replay anytime", "Guided tours", "Open the help button to replay a tour for the page you are viewing.", "#tourLauncherBtn"),
)

PERSONAL = (
    ("Your personal dashboard", "My KlockIN workspace", "See your attendance or open detailed self-service reports.", ".ki-home-welcome"),
    ("Key metrics", "Today’s records", "Review the attendance figures available for your account.", ".ki-home-metrics, #essKpiGrid"),
    ("Leave balance", "Personal reports", "Use the report controls to check your attendance and leave information.", ".ki-home-heading a, #essLeaveBalanceChart"),
    ("Attendance calendar", "Check-in history", "See when attendance was recorded over the period shown.", ".ki-home-trend, #essAttendanceCalendar"),
    ("My requests", "Quick actions", "Use the available shortcuts to reach your records and self-service tools.", ".ki-home-quick, #essLeaveRequestsList"),
)

NEW_TOURS = (
    {
        "slug": "klockin-timekeeping",
        "title": "KlockIN Timekeeping",
        "description": "Find attendance records and download a daily time record.",
        "page_match": "klockin-attendance",
        "steps": (
            ("Attendance today", "Review the current totals for the records you can access.", "#kd-today"),
            ("Filter records", "Choose a date range and the report you need. HR reviewers can also filter by employee and department.", ".kd-filters"),
            ("Review results", "Open a daily record from the results. An empty report means the selected dates have no matching records.", ".kd-results"),
            ("Download your DTR", "Choose the month and layout, then download your daily time record.", ".kd-export"),
        ),
    },
    {
        "slug": "klockin-project-overview",
        "title": "KlockIN Projects",
        "description": "Read the project dashboard and find the work that needs attention.",
        "page_match": "project-dashboard-view",
        "steps": (
            ("Project overview", "Use the date controls to choose the period you want to review.", ".pr-period-picker, .pr-header"),
            ("Project activity", "Read the totals and charts for the projects you can access.", ".pr-kpi-grid, .pr-dashboard"),
            ("Dashboard preferences", "Use Customize to choose which charts appear in your workspace.", "#pr-open-customize"),
        ),
    },
)


def update_tours(apps, schema_editor):
    database = schema_editor.connection.alias
    tours = apps.get_model("horilla_tour", "Tour").objects.using(database)
    steps = apps.get_model("horilla_tour", "TourStep").objects.using(database)
    bundled = tours.filter(company_id__isnull=True, slug__in=BRANDED_DEFAULTS)

    for rows in (bundled, steps.filter(tour__in=bundled)):
        for row in rows.filter(modified_by__isnull=True):
            title = BRAND.sub("KlockIN", row.title).removesuffix(" 👋")
            description = BRAND.sub("KlockIN", row.description)
            if (title, description) != (row.title, row.description):
                rows.filter(pk=row.pk).update(title=title, description=description)

    for slug, old_title, title, copy in (
        ("dashboard-highlights", "Dashboard Highlights", "KlockIN Overview", OVERVIEW),
        ("ess-dashboard-tour", "My Dashboard", "My KlockIN Workspace", PERSONAL),
    ):
        defaults = tours.filter(slug=slug, company_id__isnull=True)
        defaults.filter(title=old_title, modified_by__isnull=True).update(title=title)
        for sequence, (old_step, step_title, description, selector) in enumerate(copy, start=1):
            steps.filter(
                tour__in=defaults,
                sequence=sequence,
                title=old_step,
                modified_by__isnull=True,
            ).update(title=step_title, description=description, element_selector=selector)

    for definition in NEW_TOURS:
        tour, created = tours.get_or_create(
            slug=definition["slug"],
            company_id=None,
            defaults={
                "title": definition["title"],
                "description": definition["description"],
                "page_match": definition["page_match"],
                "audience": "all",
                "trigger": "manual",
                "is_published": True,
            },
        )
        if created:
            steps.bulk_create(
                [
                    steps.model(
                        tour=tour,
                        sequence=sequence,
                        title=title,
                        description=description,
                        element_selector=selector,
                    )
                    for sequence, (title, description, selector) in enumerate(definition["steps"], start=1)
                ]
            )


class Migration(migrations.Migration):
    dependencies = [
        ("horilla_tour", "0088_alter_tour_is_active_alter_tourprogress_is_active_and_more"),
    ]
    operations = [migrations.RunPython(update_tours, migrations.RunPython.noop)]
