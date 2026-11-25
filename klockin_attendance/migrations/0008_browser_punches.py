from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("klockin_attendance", "0007_attendance_break")]

    operations = [
        migrations.AlterField(
            model_name="attendancepunch",
            name="source",
            field=models.CharField(
                choices=[("ONLINE", "Mobile online"), ("OFFLINE", "Mobile offline"), ("WEB", "Web")],
                max_length=7,
            ),
        ),
        migrations.AddField(
            model_name="attendancepunch",
            name="projectable",
            field=models.BooleanField(default=True, editable=False),
        ),
    ]
