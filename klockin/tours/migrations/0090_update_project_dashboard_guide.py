"""Adapt the existing Project guide to the KlockIN dashboard (Tomeku, 2026-11-25)."""

from django.db import migrations


PROJECT_STEPS = (
    ("Project Management", "Reporting period", "Pick a preset or set the start and end dates for your charts.", ".pr-period-picker", "bottom"),
    ("Project health", "Upcoming deadlines", "Open the task or project lists from these deadline totals.", "#pr-task-kpi-grid", "bottom"),
    ("Task status", "Project activity", "Review task status, active projects and the hours logged in this period.", "#pr-charts-title", "bottom"),
    ("Projects & tasks", "People and deadlines", "See who's contributing and which tasks are coming due.", "#pr-activity-title", "top"),
    ("Timesheets", "Dashboard preferences", "Choose Customize to set which charts appear in the dashboard.", "#pr-open-customize", "bottom"),
)


def update_project_guide(apps, schema_editor):
    database = schema_editor.connection.alias
    tours = apps.get_model("horilla_tour", "Tour").objects.using(database)
    steps = apps.get_model("horilla_tour", "TourStep").objects.using(database)
    progress = apps.get_model("horilla_tour", "TourProgress").objects.using(database)
    project = tours.filter(
        slug="project-management", company_id__isnull=True,
        title="Project Management", modified_by__isnull=True, is_published=True,
    ).first()
    if project is None:
        return

    tours.filter(pk=project.pk).update(
        title="KlockIN Projects",
        description="Review project activity, deadlines and logged hours on the dashboard.",
    )
    for sequence, (old_title, title, description, selector, side) in enumerate(PROJECT_STEPS, 1):
        steps.filter(
            tour_id=project.pk, sequence=sequence, title=old_title, modified_by__isnull=True,
        ).update(title=title, description=description, element_selector=selector, side=side)

    # Only retire the extra built-in if nobody has used or edited it.
    duplicate = tours.filter(
        slug="klockin-project-overview", company_id__isnull=True,
        title="KlockIN Projects", modified_by__isnull=True, trigger="manual",
    ).first()
    if duplicate and not progress.filter(tour_id=duplicate.pk).exists() and not steps.filter(
        tour_id=duplicate.pk, modified_by__isnull=False,
    ).exists():
        tours.filter(pk=duplicate.pk).update(is_published=False)


class Migration(migrations.Migration):
    dependencies = [("horilla_tour", "0089_klockin_workspace_tours")]
    operations = [migrations.RunPython(update_project_guide, migrations.RunPython.noop)]
