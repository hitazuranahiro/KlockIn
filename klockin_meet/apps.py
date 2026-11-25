from django.apps import AppConfig
from django.conf import settings


class HorillaMeetConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "klockin_meet"
    label = "horilla_meet"
    verbose_name = "Meet"

    def ready(self):
        from django.urls import include, path

        from klockin.urls import urlpatterns
        from klockin_meet import signals

        settings.APPS.append("horilla_meet")

        urlpatterns.append(
            path("meet/", include("klockin_meet.urls")),
        )
        super().ready()
