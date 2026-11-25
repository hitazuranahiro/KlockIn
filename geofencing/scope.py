"""Resolve the tenant used for geofence management and capture separately."""

from base.auth_backends import company_scoped_active
from base.models import Company
from klockin.klockin_middlewares import get_selected_company


def employee_company(request):
    employee = getattr(request.user, "employee_get", None)
    return employee.get_company() if employee else None


def configuration_company(request):
    """Use the same selected tenant as the company-scoped permission backend."""
    if company_scoped_active():
        selected = get_selected_company()
        if selected == "all":
            return None
        if selected is not None:
            return Company.objects.filter(pk=selected).first()
    return employee_company(request)
