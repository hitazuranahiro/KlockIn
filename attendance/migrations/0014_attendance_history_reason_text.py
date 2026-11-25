from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("attendance", "0013_alter_attendanceconflictresolution_resolution")]

    operations = [
        migrations.AlterField(
            model_name="historicalattendance",
            name="history_change_reason",
            field=models.TextField(null=True),
        ),
        migrations.AlterField(
            model_name="historicalattendanceactivity",
            name="history_change_reason",
            field=models.TextField(null=True),
        ),
    ]
