import logging
from io import BytesIO
from uuid import UUID, uuid4

from django.db import OperationalError
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .address import resolve_punch_address
from .mobile_audit import MobileAuditDispatchMixin, record_mobile_activity
from .models import AttendancePunch, MobileActivity
from .serializers import (
    MAX_BATCH_ITEMS,
    MAX_SELFIE_BYTES,
    DeviceQueueReportSerializer,
    OfflinePunchSerializer,
    PunchReceiptSerializer,
    PunchSerializer,
)
from .services import PunchRejected, ingest_punch, report_device_queue


logger = logging.getLogger(__name__)
MAX_ONLINE_BYTES = MAX_SELFIE_BYTES + 64 * 1024
MAX_OFFLINE_BYTES = 15 * 1024 * 1024


class UploadTooLarge(APIException):
    status_code = 413
    default_detail = "The attendance upload exceeds the request size limit."
    default_code = "request_too_large"


class PunchJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        data = stream.read(MAX_OFFLINE_BYTES + 1)
        if len(data) > MAX_OFFLINE_BYTES:
            raise UploadTooLarge()
        try:
            return super().parse(BytesIO(data), media_type, parser_context)
        except RecursionError as exc:
            raise ParseError("The attendance JSON is nested too deeply.") from exc


class PunchMultipartParser(MultiPartParser):
    def parse(self, stream, media_type=None, parser_context=None):
        try:
            length = int(parser_context["request"].META.get("CONTENT_LENGTH", 0))
        except (TypeError, ValueError) as exc:
            raise ParseError("The attendance upload has an invalid content length.") from exc
        if length > MAX_ONLINE_BYTES:
            raise UploadTooLarge()
        return super().parse(stream, media_type, parser_context)


def _submitted_uuid(data):
    if not isinstance(data, dict):
        return None
    value = data.get("punch_uuid")
    if not isinstance(value, str) or len(value) > 45:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _process_punch(user, serializer, received_at, source):
    if not serializer.is_valid():
        return 400, {
            "punch_uuid": _submitted_uuid(serializer.initial_data),
            "code": "invalid_punch",
            "detail": "The punch payload failed validation.",
            "errors": serializer.errors,
        }

    data = serializer.validated_data
    punch_uuid = str(data["punch_uuid"])
    try:
        punch, duplicate = ingest_punch(user, data, received_at, source)
    except PunchRejected as exc:
        return exc.status, {"punch_uuid": punch_uuid, "code": exc.code, "detail": str(exc)}
    except (OSError, OperationalError):
        logger.exception("Could not complete attendance punch %s", punch_uuid)
        return 503, {
            "punch_uuid": punch_uuid,
            "code": "punch_unavailable",
            "detail": "Attendance storage is temporarily unavailable. Retry this UUID.",
        }

    if not duplicate:
        resolve_punch_address(punch)
    receipt = PunchReceiptSerializer(punch).data
    return (200 if duplicate else 201), {
        **receipt,
        "duplicate": duplicate,
        "server_sync_timestamp": received_at.isoformat(),
    }


def _receipt_counts(status, receipt):
    return {
        "received_count": 1,
        "accepted_count": int(status == 201),
        "replayed_count": int(status == 200 and bool(receipt.get("duplicate"))),
        "rejected_count": int(status >= 400),
    }


class AttendancePunchViewSet(MobileAuditDispatchMixin, viewsets.ViewSet):
    mobile_audit_kind = MobileActivity.Kind.ONLINE_PUNCH
    permission_classes = (IsAuthenticated,)
    parser_classes = (PunchMultipartParser,)

    def create(self, request):
        received_at = timezone.now()
        serializer = PunchSerializer(data=request.data, context={"received_at": received_at})
        status, receipt = _process_punch(
            request.user, serializer, received_at, AttendancePunch.Source.ONLINE
        )
        self.mobile_audit_details = {"punch_uuid": receipt.get("punch_uuid"), **_receipt_counts(status, receipt)}
        return Response(receipt, status=status)


class AttendanceBatchSyncViewSet(MobileAuditDispatchMixin, viewsets.ViewSet):
    mobile_audit_kind = MobileActivity.Kind.OFFLINE_BATCH
    permission_classes = (IsAuthenticated,)
    parser_classes = (PunchJSONParser,)

    def create(self, request):
        received_at = timezone.now()
        data = request.data
        if not isinstance(data, list) or not 1 <= len(data) <= MAX_BATCH_ITEMS:
            return Response(
                {"code": "invalid_batch", "detail": "Submit an array of one to five punches."},
                status=400,
            )

        batch_id = uuid4()
        results = []
        totals = dict.fromkeys(_receipt_counts(201, {}), 0)
        for index, item in enumerate(data):
            serializer = OfflinePunchSerializer(data=item, context={"received_at": received_at})
            status, receipt = _process_punch(
                request.user, serializer, received_at, AttendancePunch.Source.OFFLINE
            )
            counts = _receipt_counts(status, receipt)
            for key, value in counts.items():
                totals[key] += value
            record_mobile_activity(
                kind=MobileActivity.Kind.OFFLINE_PUNCH,
                actor=request.user,
                started_at=received_at,
                status_code=status,
                punch_uuid=receipt.get("punch_uuid"),
                batch_id=batch_id,
                **counts,
            )
            results.append({"index": index, "status": status, **receipt})
        self.mobile_audit_details = {"batch_id": batch_id, **totals}
        if all(item["status"] >= 500 for item in results):
            self.mobile_audit_details["outcome"] = MobileActivity.Outcome.FAILED
        return Response({"results": results})


class DeviceQueueReportView(MobileAuditDispatchMixin, APIView):
    mobile_audit_kind = MobileActivity.Kind.QUEUE_REPORT
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def post(self, request):
        received_at = timezone.now()
        serializer = DeviceQueueReportSerializer(
            data=request.data, context={"received_at": received_at}
        )
        serializer.is_valid(raise_exception=True)
        try:
            report_device_queue(request.user, received_at=received_at, **serializer.validated_data)
        except PunchRejected as exc:
            return Response({"code": exc.code, "detail": str(exc)}, status=exc.status)
        return Response(status=204)
