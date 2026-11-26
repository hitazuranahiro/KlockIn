"""Validate and persist account defaults for personal document exports."""

from collections.abc import Mapping

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from klockin_auth.models import DocumentExportPreference


EXPORT_DEFAULTS = {
    "payslip": {
        "template": "detailed",
        "show_company": True,
        "show_notes": True,
        "note": "",
    },
    "dtr": {
        "layout": "am-pm",
        "orientation": "portrait",
        "show_company": True,
        "show_notes": True,
        "note": "",
        "show_undertime": True,
    },
}
EXPORT_CHOICES = {
    "template": {
        "detailed": _("Detailed · A4 portrait"),
        "landscape": _("Wide · A4 landscape"),
        "compact": _("Compact · A4 portrait"),
    },
    "layout": {
        "am-pm": _("Morning and afternoon"),
        "first-last": _("First in and last out"),
    },
    "orientation": {"portrait": _("A4 portrait"), "landscape": _("A4 landscape")},
}
EXPORT_NOTE_LIMIT = 160


def normalize_export_options(kind, options):
    if kind not in EXPORT_DEFAULTS or not isinstance(options, Mapping):
        raise ValidationError(_("Choose a supported document and export options."))
    result = {}
    for name, value in options.items():
        if name not in EXPORT_DEFAULTS[kind]:
            raise ValidationError(_("An export option is unsupported."))
        if name == "layout" and value == "ampm":
            value = "am-pm"
        if name in EXPORT_CHOICES:
            if not isinstance(value, str) or value not in EXPORT_CHOICES[name]:
                raise ValidationError(_("Choose an available layout."))
        elif name == "note":
            if not isinstance(value, str):
                raise ValidationError(_("Enter a text note."))
            value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
            if len(value) > EXPORT_NOTE_LIMIT or any(
                not character.isprintable() and character != "\n" for character in value
            ):
                raise ValidationError(_("Enter a note of at most %(limit)s characters."), params={"limit": EXPORT_NOTE_LIMIT})
        elif not isinstance(value, bool):
            if value in ("true", "1"):
                value = True
            elif value in ("false", "0"):
                value = False
            else:
                raise ValidationError(_("Choose whether to show each optional section."))
        result[name] = value
    return result


def get_export_preferences(user):
    saved = {}
    if user and user.is_authenticated:
        saved = (
            DocumentExportPreference.objects.filter(user_id=user.pk)
            .values_list("preferences", flat=True)
            .first()
            or {}
        )
    return {kind: {**defaults, **saved.get(kind, {})} for kind, defaults in EXPORT_DEFAULTS.items()}


def resolve_export_options(user, kind, query):
    # Notes are saved via POST/PATCH and kept out of PDF URLs.
    overrides = {
        name: query.get(name)
        for name in EXPORT_DEFAULTS[kind]
        if name != "note" and name in query
    }
    return {**get_export_preferences(user)[kind], **normalize_export_options(kind, overrides)}


@transaction.atomic
def save_export_preferences(user, changes):
    if not isinstance(changes, Mapping) or not changes:
        raise ValidationError(_("Choose an export preference to save."))
    validated = {kind: normalize_export_options(kind, options) for kind, options in changes.items()}
    # Lock the account even before its preference row exists. A device saving
    # one document type cannot overwrite another device's unrelated settings.
    get_user_model()._base_manager.select_for_update().get(pk=user.pk)
    preferences = get_export_preferences(user)
    for kind, options in validated.items():
        preferences[kind].update(options)
    DocumentExportPreference.objects.update_or_create(
        user_id=user.pk, defaults={"preferences": preferences}
    )
    return preferences
