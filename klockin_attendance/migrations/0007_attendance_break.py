import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("klockin_attendance", "0006_security_evidence")]

    operations = [
        migrations.AddField(
            model_name="attendancepolicy",
            name="break_allowance_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(1440),
                ],
                help_text="Daily allowance for employee-tracked unpaid breaks. Leave blank to disable.",
            ),
        ),
        migrations.CreateModel(
            name="AttendanceBreak",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField()),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("attendance", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="tracked_breaks",
                    to="attendance.attendance",
                )),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=["attendance"], condition=models.Q(ended_at__isnull=True),
                        name="klockin_one_open_break_per_day",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(ended_at__gte=models.F("started_at")),
                        name="klockin_break_ends_after_start",
                    ),
                ],
            },
        ),
    ]
