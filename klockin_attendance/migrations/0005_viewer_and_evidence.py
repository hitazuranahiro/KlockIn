from django.conf import settings
from django.db import migrations
from django.db.models import Q


EVIDENCE_GROUPS = ("Admin", "HR Manager", "Attendance Manager")


def assign_permissions(apps, schema_editor):
    database = schema_editor.connection.alias
    content_types = apps.get_model("contenttypes", "ContentType").objects.using(database)
    permissions = apps.get_model("auth", "Permission").objects.using(database)
    groups = apps.get_model("auth", "Group").objects.using(database)
    users = apps.get_model(settings.AUTH_USER_MODEL).objects.using(database)

    attendance_type, _ = content_types.get_or_create(
        app_label="attendance", model="attendance"
    )
    view_attendance, _ = permissions.get_or_create(
        content_type=attendance_type,
        codename="view_attendance",
        defaults={"name": "Can view attendance"},
    )
    change_attendance, _ = permissions.get_or_create(
        content_type=attendance_type,
        codename="change_attendance",
        defaults={"name": "Can change attendance"},
    )
    punch_type, _ = content_types.get_or_create(
        app_label="klockin_attendance", model="attendancepunch"
    )
    evidence, _ = permissions.get_or_create(
        content_type=punch_type,
        codename="view_punch_evidence",
        defaults={"name": "Can view mobile punch evidence"},
    )

    viewer, created = groups.get_or_create(name="Attendance Viewer")
    if created:
        viewer.permissions.add(view_attendance)

    for name in EVIDENCE_GROUPS:
        group, _ = groups.get_or_create(name=name)
        group.permissions.add(evidence)
    for group in groups.filter(permissions=view_attendance).filter(
        permissions=change_attendance
    ):
        group.permissions.add(evidence)

    # A direct user permission applies across company contexts. Grant it only
    # when both earlier permissions already applied globally. Preserve existing
    # company-scoped roles via the group grants above.
    view = Q(user_permissions=view_attendance)
    change = Q(user_permissions=change_attendance)
    if not settings.COMPANY_SCOPED_PERMISSIONS:
        view |= Q(groups__permissions=view_attendance)
        change |= Q(groups__permissions=change_attendance)
    can_view = users.filter(view)
    can_change = users.filter(change)
    editors = users.filter(
        pk__in=can_view.values("pk"), is_active=True, is_superuser=False
    ).filter(pk__in=can_change.values("pk"))
    editors = editors.exclude(Q(user_permissions=evidence) | Q(groups__permissions=evidence))
    for user in editors.iterator():
        user.user_permissions.add(evidence)


class Migration(migrations.Migration):
    dependencies = [
        ("klockin_attendance", "0004_trusted_clock_and_policy"),
        ("attendance", "0014_attendance_history_reason_text"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="attendancepunch",
            options={"permissions": [("view_punch_evidence", "Can view mobile punch evidence")]},
        ),
        migrations.RunPython(assign_permissions, migrations.RunPython.noop),
    ]
