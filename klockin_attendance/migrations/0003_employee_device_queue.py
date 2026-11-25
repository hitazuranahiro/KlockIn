from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("klockin_attendance", "0002_punch_review")]

    operations = [
        migrations.AddField(
            model_name="employeedevice",
            name="pending_punches",
            field=models.PositiveIntegerField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="employeedevice",
            name="queue_observed_at",
            field=models.DateTimeField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="employeedevice",
            name="queue_reported_at",
            field=models.DateTimeField(editable=False, null=True),
        ),
    ]
