from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BackupConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "klockin_backup"
    label = "horilla_backup"
    verbose_name = _("Backup")

    def ready(self):
        from django.urls import include, path

        from klockin.urls import urlpatterns

        urlpatterns.append(
            path("backup/", include("klockin_backup.urls")),
        )
        super().ready()
