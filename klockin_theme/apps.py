"""
AppConfig for the horilla_theme app
"""

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class HorillaThemeConfig(AppConfig):
    """App configuration class for horilla_theme."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "klockin_theme"
    label = "horilla_theme"
    verbose_name = _("Appearance")

    def ready(self):
        """Run app initialization logic (executed after Django setup).
        Used to auto-register URLs and connect signals if required.
        """
        try:
            # Auto-register this app's URLs and add to installed apps
            from django.urls import include, path

            from klockin.urls import urlpatterns

            settings.APPS.append(("horilla_theme"))
            # Add app URLs to main urlpatterns
            urlpatterns.append(
                path("theme/", include("klockin_theme.urls")),
            )

            __import__("klockin_theme.signals")
        except Exception as e:
            import logging

            logging.warning("HorillaThemeConfig.ready failed: %s", e)

        super().ready()
