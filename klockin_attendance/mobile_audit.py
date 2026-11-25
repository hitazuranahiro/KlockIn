"""Audit mobile outcomes without retaining request or credential payloads."""

import logging
from uuid import UUID

from django.db import DatabaseError, transaction
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from employee.models import Employee

from .models import MobileActivity

logger = logging.getLogger(__name__)


def _company_id(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        Employee._base_manager.filter(employee_user_id=user.pk)
        .values_list("employee_work_info__company_id", flat=True)
        .first()
    )


def _punch_uuid(value):
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str) or len(value) > 45:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _outcome(status_code, replayed_count, accepted_count, rejected_count):
    outcomes = MobileActivity.Outcome
    if status_code >= 500:
        return outcomes.FAILED
    if status_code >= 400 or (rejected_count and not (accepted_count or replayed_count)):
        return outcomes.REJECTED
    if rejected_count:
        return outcomes.PARTIAL
    if replayed_count and not accepted_count:
        return outcomes.REPLAYED
    return outcomes.ACCEPTED


def record_mobile_activity(
    *, kind, started_at, status_code, actor=None, punch_uuid=None, batch_id=None,
    received_count=0, accepted_count=0, replayed_count=0, rejected_count=0, outcome=None,
):
    """Persist a completed attempt. Call after the operation transaction exits."""
    if not getattr(actor, "is_authenticated", False):
        actor = None
    if kind not in MobileActivity.Kind.values:
        raise ValueError("Unknown mobile activity kind.")
    outcome = outcome or _outcome(status_code, replayed_count, accepted_count, rejected_count)
    if outcome not in MobileActivity.Outcome.values:
        raise ValueError("Unknown mobile activity outcome.")
    try:
        with transaction.atomic():
            MobileActivity._base_manager.create(
                kind=kind,
                outcome=outcome,
                actor=actor,
                company_id=_company_id(actor),
                punch_uuid=_punch_uuid(punch_uuid),
                batch_id=batch_id,
                started_at=started_at,
                status_code=status_code,
                received_count=received_count,
                accepted_count=accepted_count,
                replayed_count=replayed_count,
                rejected_count=rejected_count,
            )
    except DatabaseError:
        # An audit outage cannot change an already-completed punch receipt.
        logger.error("Could not persist a mobile activity event (%s).", kind)


def scoped_mobile_activity(user):
    entries = MobileActivity._base_manager.all()
    if user.is_superuser:
        return entries
    company_id = _company_id(user)
    return entries.filter(company_id=company_id) if company_id is not None else entries.none()


class MobileActivityList(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not request.user.has_perm("klockin_attendance.view_mobileactivity"):
            raise PermissionDenied
        entries = scoped_mobile_activity(request.user).values(
            "id", "kind", "outcome", "actor_id", "company_id", "punch_uuid",
            "batch_id", "started_at", "finished_at", "status_code", "received_count",
            "accepted_count", "replayed_count", "rejected_count",
        )
        paginator = PageNumberPagination()
        return paginator.get_paginated_response(paginator.paginate_queryset(entries, request))


class MobileAuditDispatchMixin:
    """Record sign-ins and attendance attempts from authenticated users."""

    def dispatch(self, request, *args, **kwargs):
        if request.method != "POST":
            return super().dispatch(request, *args, **kwargs)
        from django.utils import timezone

        started_at = timezone.now()
        status_code = 500
        self.mobile_audit_details = {}
        try:
            response = super().dispatch(request, *args, **kwargs)
            status_code = response.status_code
            return response
        finally:
            # `_user` is already resolved by DRF when authentication succeeded.
            # Accessing `request.user` can retry a failed authentication here.
            actor = getattr(self, "mobile_audit_actor", None) or getattr(
                getattr(self, "request", None), "_user", None,
            )
            # Unauthenticated or throttled attendance requests never reach
            # punch handling. Keep these in HTTP logs so they cannot grow the
            # attendance audit table. Sign-in has its own edge rate limit.
            is_login = self.mobile_audit_kind == MobileActivity.Kind.LOGIN
            if is_login or (status_code != 429 and getattr(actor, "is_authenticated", False)):
                record_mobile_activity(
                    kind=self.mobile_audit_kind,
                    actor=actor,
                    started_at=started_at,
                    status_code=status_code,
                    **self.mobile_audit_details,
                )
