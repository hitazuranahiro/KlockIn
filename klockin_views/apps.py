from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class HorillaViewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "klockin_views"
    label = "horilla_views"
    verbose_name = _("Views")
