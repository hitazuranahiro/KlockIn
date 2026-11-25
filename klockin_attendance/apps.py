from django.apps import AppConfig
from django.conf import settings


class KlockinAttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "klockin_attendance"
    verbose_name = "KlockIN attendance"

    def ready(self):
        from .evidence_crypto import evidence_cipher

        evidence_cipher()

        if self.label not in settings.APPS:
            settings.APPS.append(self.label)
