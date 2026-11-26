"""Employee submission and direct-manager decisions for missed punches."""

from django.core.exceptions import ValidationError
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.corrections import (
    CORRECTION_REASON_LIMIT,
    MissedPunchConflict,
    decide_missed_punch_request,
    missed_punch_requests,
    submit_missed_punch_request,
)
from attendance.models import AttendanceMissedPunchRequest
from klockin_api.api_methods.base.pagination import HorillaPageNumberPagination


class MissedPunchInput(serializers.Serializer):
    attendance_date = serializers.DateField()
    time_in = serializers.TimeField(required=False, allow_null=True)
    time_out = serializers.TimeField(required=False, allow_null=True)
    clock_in_date = serializers.DateField(required=False, allow_null=True)
    clock_out_date = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(min_length=3, max_length=CORRECTION_REASON_LIMIT)


class MissedPunchRequestSerializer(serializers.ModelSerializer):
    employee_id = serializers.IntegerField(read_only=True)
    employee_first_name = serializers.CharField(source="employee.employee_first_name", read_only=True)
    employee_last_name = serializers.CharField(source="employee.employee_last_name", read_only=True)
    attendance_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = AttendanceMissedPunchRequest
        fields = (
            "id", "employee_id", "employee_first_name", "employee_last_name",
            "attendance_date", "time_in", "time_out", "clock_in_date", "clock_out_date",
            "reason", "status", "requested_at", "decided_at", "attendance_id",
        )
        read_only_fields = fields


def _validation_error(error):
    response_status = status.HTTP_409_CONFLICT if isinstance(error, MissedPunchConflict) else status.HTTP_400_BAD_REQUEST
    return Response({"detail": error.messages[0]}, status=response_status)


class MissedPunchRequestAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        scope = request.query_params.get("scope", "mine")
        if scope not in ("mine", "approvals"):
            return Response({"detail": "Use mine or approvals for the scope."}, status=400)
        records = missed_punch_requests(request.user, approvals=scope == "approvals")
        if scope == "approvals":
            records = records.filter(status=AttendanceMissedPunchRequest.Status.PENDING)
        pagination = HorillaPageNumberPagination()
        page = pagination.paginate_queryset(records, request)
        return pagination.get_paginated_response(MissedPunchRequestSerializer(page, many=True).data)

    def post(self, request):
        form = MissedPunchInput(data=request.data)
        form.is_valid(raise_exception=True)
        try:
            created = submit_missed_punch_request(request.user, **form.validated_data)
        except ValidationError as error:
            return _validation_error(error)
        return Response(MissedPunchRequestSerializer(created).data, status=status.HTTP_201_CREATED)


class MissedPunchDecisionAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    approve = False

    def put(self, request, pk):
        try:
            decided = decide_missed_punch_request(request.user, pk, approve=self.approve)
        except ValidationError as error:
            return _validation_error(error)
        return Response(MissedPunchRequestSerializer(decided).data)
