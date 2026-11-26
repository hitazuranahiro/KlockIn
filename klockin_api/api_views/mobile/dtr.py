"""Download the signed-in employee's monthly DTR in the mobile app."""

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from employee.models import Employee
from klockin_attendance.dtr import monthly_dtr_document, requested_dtr_month


class DTRContentNegotiation(DefaultContentNegotiation):
    def select_renderer(self, request, renderers, format_suffix=None):
        # A successful download bypasses DRF rendering. Use JSON for any error,
        # including when the client requests application/pdf.
        return renderers[0], renderers[0].media_type


@method_decorator(never_cache, name="dispatch")
class MobileDTRAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    renderer_classes = (JSONRenderer,)
    content_negotiation_class = DTRContentNegotiation

    def get(self, request):
        employee = get_object_or_404(
            Employee._base_manager.select_related("employee_work_info__company_id"),
            employee_user_id=request.user.pk,
            is_active=True,
        )
        query = request.query_params
        try:
            month = requested_dtr_month(query)
            return monthly_dtr_document(request.user, employee, month, query)
        except ValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
