from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from klockin.export_preferences import (
    EXPORT_CHOICES,
    EXPORT_DEFAULTS,
    EXPORT_NOTE_LIMIT,
    get_export_preferences,
    resolve_export_options,
    save_export_preferences,
)


def _document_url(kind, pk):
    name = {"payslip": "payslip-pdf", "dtr": "klockin-monthly-dtr"}.get(kind)
    if name is None:
        raise Http404
    return reverse(name, args=[pk])


def _option_query(options):
    return {
        key: ("1" if value else "0") if isinstance(value, bool) else value
        for key, value in options.items()
        if key != "note"
    }


@never_cache
def render_export_setup(request, kind, pk, *, month=None, title=None):
    """Render after the document view has verified object-level access."""
    action = _document_url(kind, pk)
    error = None
    try:
        options = resolve_export_options(request.user, kind, request.GET)
    except ValidationError as exc:
        error = exc.messages[0]
        options = get_export_preferences(request.user)[kind]
    query = _option_query(options)
    if kind == "dtr":
        query["month"] = month
        title = title or _("Daily time record")
        back = reverse("klockin-attendance")
        back_label = _("Timekeeping")
    else:
        title = title or _("Payslip")
        back = reverse("view-created-payslip", args=[pk])
        back_label = _("Payslip details")

    return render(
        request,
        "exports/document_setup.html",
        {
            "title": title,
            "kind": kind,
            "month": month,
            "action": action,
            "back": back,
            "back_label": back_label,
            "save_url": reverse("save-export-preferences", args=[kind, pk]),
            "preview_url": action + "?" + urlencode({**query, "preview": "1"}),
            "download_url": action + "?" + urlencode({**query, "download": "1"}),
            "choices": EXPORT_CHOICES,
            "options": options,
            "query": query,
            "note_limit": EXPORT_NOTE_LIMIT,
            "error": error,
        },
        status=400 if error else 200,
    )


@login_required
@never_cache
@require_POST
def save_document_preferences(request, kind, pk):
    action = _document_url(kind, pk)
    options = {
        name: request.POST[name] for name in EXPORT_DEFAULTS[kind] if name in request.POST
    }
    try:
        save_export_preferences(request.user, {kind: options})
    except ValidationError as exc:
        return HttpResponseBadRequest(exc.messages[0])
    messages.success(request, _("Default export preferences saved for your account."))
    query = {"configure": "1"}
    if kind == "dtr" and "month" in request.POST:
        query["month"] = request.POST["month"]
    return redirect(action + "?" + urlencode(query))
