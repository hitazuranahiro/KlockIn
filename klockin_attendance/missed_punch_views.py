"""Employee submission and supervisor review for missed punches."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from attendance.corrections import (
    CORRECTION_REASON_LIMIT,
    can_review_missed_punch_requests,
    decide_missed_punch_request,
    missed_punch_reporting_manager,
    missed_punch_requests,
    submit_missed_punch_request,
)


class MissedPunchForm(forms.Form):
    attendance_date = forms.DateField(
        label=_("Work date"),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    time_in = forms.TimeField(
        label=_("Check-in time"),
        required=False,
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    time_out = forms.TimeField(
        label=_("Check-out time"),
        required=False,
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    clock_out_date = forms.DateField(
        label=_("Check-out date"),
        required=False,
        help_text=_("For a check-out after midnight, choose the following date."),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    reason = forms.CharField(
        label=_("Reason"),
        min_length=3,
        max_length=CORRECTION_REASON_LIMIT,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def missed_punch_workspace(request):
    manager = missed_punch_reporting_manager(request.user)
    form = MissedPunchForm(
        request.POST if request.method == "POST" else None,
        initial={"attendance_date": timezone.localdate()},
        label_suffix="",
    )
    if request.method == "POST" and form.is_valid():
        try:
            submit_missed_punch_request(request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, _("Request sent to your reporting manager."))
            return redirect(reverse("klockin-missed-punches", fragment="my-requests"))

    own = missed_punch_requests(request.user).order_by("-requested_at", "-pk")
    own_page = Paginator(own, 15).get_page(request.GET.get("mine"))
    team_page = None
    if can_review_missed_punch_requests(request.user):
        pending = (
            missed_punch_requests(request.user, approvals=True)
            .filter(status="pending")
            .order_by("requested_at", "pk")
        )
        team_page = Paginator(pending, 15).get_page(request.GET.get("team"))

    return render(
        request,
        "klockin_attendance/missed_punches.html",
        {"form": form, "manager": manager, "own_page": own_page, "team_page": team_page},
    )


@login_required
@never_cache
@require_POST
def missed_punch_decision(request, pk):
    decision = request.POST.get("decision")
    if decision not in {"approve", "reject"}:
        return HttpResponseBadRequest(_("Choose Approve or Reject."))
    try:
        decide_missed_punch_request(request.user, pk, approve=decision == "approve")
    except ValidationError as error:
        for message in error.messages:
            messages.error(request, message)
    else:
        messages.success(
            request,
            _("Missed punch approved.") if decision == "approve" else _("Request rejected."),
        )
    return redirect(reverse("klockin-missed-punches", fragment="team-requests"))
