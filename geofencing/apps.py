from django.apps import AppConfig
from django.conf import settings


class GeofencingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "geofencing"

    def ready(self):
        from django.urls import include, path

        from klockin.urls import urlpatterns

        if self.label not in settings.APPS:
            settings.APPS.append(self.label)

        urlpatterns.append(
            path("api/geofencing/", include("geofencing.urls")),
        )
        super().ready()
