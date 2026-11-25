import hashlib
import json
import logging
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from django.db import transaction

from employee.models import Employee
from geofencing.models import GeoFencing

from .models import AttendancePunch, EmployeeDevice


logger = logging.getLogger(__name__)
REPEAT_WINDOW = timedelta(minutes=3)


class PunchRejected(Exception):
    def __init__(self, code, detail, status):
        super().__init__(detail)
        self.code = code
        self.status = status


def validate_login_device_id(value):
    max_length = EmployeeDevice._meta.get_field("device_id").max_length
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= max_length
        or not value.isprintable()
        or value != value.strip()
    ):
        raise PunchRejected(
            "invalid_device_id",
            f"Device ID must be printable text of 1 to {max_length} characters "
            "without surrounding whitespace.",
            400,
        )
    return value


def _lock_employee(user):
    employee = (
        Employee._base_manager.select_for_update(of=("self",))
        .filter(employee_user_id=user.pk, is_active=True)
        .first()
    )
    if employee is None:
        raise PunchRejected("employee_required", "An active employee profile is required.", 403)
    return employee


def _device_binding(employee, device_id):
    binding = EmployeeDevice.objects.filter(employee=employee).first()
    if binding is not None and binding.device_id != device_id:
        raise PunchRejected(
            "device_mismatch",
            "The employee is registered to another device. Contact your administrator.",
            403,
        )
    return binding


def bind_login_device(user, device_id):
    """Bind within the caller's token-issuance transaction."""
    employee = _lock_employee(user)
    if _device_binding(employee, device_id) is None:
        EmployeeDevice.objects.create(employee=employee, device_id=device_id)


@transaction.atomic
def report_device_queue(user, device_id, pending_punches, observed_at, received_at):
    employee = _lock_employee(user)
    binding = _device_binding(employee, device_id)
    if binding is None:
        raise PunchRejected("device_not_enrolled", "Enroll this device by signing in.", 403)
    if binding.queue_observed_at is not None and observed_at <= binding.queue_observed_at:
        return
    binding.pending_punches = pending_punches
    binding.queue_observed_at = observed_at
    binding.queue_reported_at = received_at
    binding.save(update_fields=["pending_punches", "queue_observed_at", "queue_reported_at"])


def _request_digest(data):
    photo = hashlib.sha256()
    upload = data["punch_selfie"]
    for chunk in upload.chunks():
        photo.update(chunk)
    upload.seek(0)

    latitude = data["gps_lat"]
    longitude = data["gps_long"]
    payload = [
        data["punch_type"],
        data["punched_at"].isoformat(),
        data["device_id"],
        str(latitude.copy_abs() if latitude.is_zero() else latitude),
        str(longitude.copy_abs() if longitude.is_zero() else longitude),
        data["detected_address"],
        photo.hexdigest(),
    ]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _replay(punch, employee, digest):
    if punch.employee_id != employee.pk or punch.request_digest != digest:
        raise PunchRejected(
            "punch_conflict", "That punch UUID is unavailable for this payload.", 409
        )
    return punch, True


def _check_geofence(employee, latitude, longitude):
    fence = GeoFencing.for_company(employee.get_company())
    if fence is None or not fence.start:
        return

    try:
        within_fence = fence.allows(latitude, longitude)
    except (TypeError, ValueError):
        logger.exception("Invalid geofence configuration %s", fence.pk)
        raise PunchRejected("geofence_unavailable", "Location verification is unavailable.", 503)

    if not within_fence:
        raise PunchRejected(
            "outside_geofence", "The punch is outside the permitted work location.", 403
        )


def ingest_punch(user, data, received_at, source):
    """Commit immutable evidence once, serialize device and time checks per employee."""
    from .projection import project_punch

    digest = _request_digest(data)
    upload = data["punch_selfie"]
    punch_uuid = data["punch_uuid"]
    field = AttendancePunch._meta.get_field("punch_selfie")
    selfie_name = None
    ready_to_commit = False

    try:
        with transaction.atomic(durable=True):
            employee = _lock_employee(user)

            existing = AttendancePunch.objects.filter(pk=punch_uuid).first()
            if existing is not None:
                return _replay(existing, employee, digest)

            binding = _device_binding(employee, data["device_id"])

            device_punched_at = data["punched_at"]
            punched_at = (
                received_at if source == AttendancePunch.Source.ONLINE else device_punched_at
            )
            if AttendancePunch.objects.filter(
                employee=employee,
                punched_at__gt=punched_at - REPEAT_WINDOW,
                punched_at__lt=punched_at + REPEAT_WINDOW,
            ).exists():
                raise PunchRejected(
                    "punch_too_soon", "Punches must be at least three minutes apart.", 409
                )

            _check_geofence(employee, data["gps_lat"], data["gps_long"])

            # The primary key also arbitrates simultaneous collisions between employees.
            punch, created = AttendancePunch.objects.get_or_create(
                punch_uuid=punch_uuid,
                defaults={
                    **data,
                    "punched_at": punched_at,
                    "device_punched_at": device_punched_at,
                    "employee": employee,
                    "punch_selfie": "",
                    "source": source,
                    "request_digest": digest,
                    "server_receive_timestamp": received_at,
                },
            )
            if not created:
                return _replay(punch, employee, digest)

            if binding is None:
                EmployeeDevice.objects.create(employee=employee, device_id=punch.device_id)

            filename = f"{punch_uuid.hex}-{uuid4().hex}{Path(upload.name).suffix}"
            selfie_name = field.generate_filename(punch, filename)
            selfie_name = field.storage.save(selfie_name, upload, max_length=field.max_length)
            punch.punch_selfie = selfie_name
            punch.sync_status = AttendancePunch.SyncStatus.SYNCED
            punch.save(update_fields=["punch_selfie", "sync_status"])
            attendance = project_punch(punch)
            if attendance is not None and punch.attendance_id != attendance.pk:
                punch.attendance = attendance
                punch.save(update_fields=["attendance"])
            ready_to_commit = True
    except Exception:
        # A commit failure can be ambiguous. Keep the file in that case so a
        # successfully committed row cannot lose its evidence.
        if selfie_name and not ready_to_commit:
            try:
                field.storage.delete(selfie_name)
            except OSError:
                logger.exception("Failed to clean up selfie for punch %s", punch_uuid)
        raise

    return punch, False
