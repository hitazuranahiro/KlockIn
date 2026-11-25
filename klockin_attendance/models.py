from hashlib import sha256

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from base.klockin_company_manager import HorillaCompanyManager

from .policies import ATTENDANCE_MODES, PAIRED
from .evidence_crypto import EncryptedEvidenceDecimalField, EncryptedEvidenceTextField
from .storage import private_selfie_storage


def _device_fingerprint(device_id):
    return sha256(device_id.encode()).hexdigest()[:12]


class AttendancePunch(models.Model):
    class PunchType(models.TextChoices):
        CLOCK_IN = "CLOCK_IN", "Clock in"
        CLOCK_OUT = "CLOCK_OUT", "Clock out"

    class Source(models.TextChoices):
        ONLINE = "ONLINE", "Mobile online"
        OFFLINE = "OFFLINE", "Mobile offline"

    class SyncStatus(models.TextChoices):
        SYNCED = "SYNCED", "Synced"
        PENDING = "PENDING", "Pending"

    punch_uuid = models.UUIDField(primary_key=True, editable=False)
    employee = models.ForeignKey(
        "employee.Employee", on_delete=models.PROTECT, related_name="klockin_punches"
    )
    attendance = models.ForeignKey(
        "attendance.Attendance",
        on_delete=models.SET_NULL,
        related_name="klockin_punches",
        null=True,
        blank=True,
        editable=False,
    )
    activity = models.ForeignKey(
        "attendance.AttendanceActivity",
        on_delete=models.SET_NULL,
        related_name="klockin_punches",
        null=True,
        blank=True,
        editable=False,
    )
    punch_type = models.CharField(max_length=9, choices=PunchType.choices)
    punched_at = models.DateTimeField()
    device_punched_at = models.DateTimeField(editable=False, null=True)
    device_id = models.CharField(max_length=128)
    punch_selfie = models.ImageField(upload_to="punches/", storage=private_selfie_storage)
    gps_lat = EncryptedEvidenceDecimalField()
    gps_long = EncryptedEvidenceDecimalField()
    detected_address = EncryptedEvidenceTextField(max_length=500, blank=True)
    server_receive_timestamp = models.DateTimeField()
    source = models.CharField(max_length=7, choices=Source.choices)
    sync_status = models.CharField(
        max_length=7, choices=SyncStatus.choices, default=SyncStatus.PENDING
    )
    request_digest = models.CharField(max_length=64, editable=False)

    @property
    def device_fingerprint(self):
        return _device_fingerprint(self.device_id)

    class Meta:
        permissions = [("view_punch_evidence", "Can view mobile punch evidence")]
        indexes = [
            models.Index(
                fields=["employee", "punched_at"], name="klockin_employee_punch_time"
            )
        ]


class EmployeeDevice(models.Model):
    employee = models.OneToOneField(
        "employee.Employee",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="klockin_device",
    )
    device_id = models.CharField(max_length=128)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    pending_punches = models.PositiveIntegerField(null=True, editable=False)
    queue_observed_at = models.DateTimeField(null=True, editable=False)
    queue_reported_at = models.DateTimeField(null=True, editable=False)

    @property
    def device_fingerprint(self):
        return _device_fingerprint(self.device_id)

    class Meta:
        verbose_name = "KlockIN device binding"
        verbose_name_plural = "KlockIN device bindings"

    def __str__(self):
        return f"Device binding for employee {self.employee_id}"


class PunchReview(models.Model):
    """A staff decision to retain a mobile punch as supplementary evidence."""

    punch = models.OneToOneField(
        AttendancePunch, on_delete=models.PROTECT, related_name="review"
    )
    attendance = models.ForeignKey(
        "attendance.Attendance",
        null=True,
        on_delete=models.SET_NULL,
        related_name="klockin_punch_reviews",
    )
    attendance_reference = models.PositiveBigIntegerField(editable=False)
    attendance_date = models.DateField(editable=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    reviewed_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=200)


class AttendancePolicy(models.Model):
    """Company defaults for new daily mobile attendance records."""

    company = models.OneToOneField("base.Company", on_delete=models.CASCADE)
    mode = models.CharField(max_length=10, choices=ATTENDANCE_MODES, default=PAIRED)
    break_start = models.TimeField(blank=True, null=True, verbose_name="Unpaid break starts")
    break_end = models.TimeField(blank=True, null=True, verbose_name="Unpaid break ends")

    objects = HorillaCompanyManager("company")

    def clean(self):
        super().clean()
        if (self.break_start is None) != (self.break_end is None):
            raise ValidationError("Enter both break times or leave both blank.")
        if self.break_start is not None and self.break_start == self.break_end:
            raise ValidationError("Break start and end must be different.")

    def __str__(self):
        return str(self.company)


class MobileDayPolicy(models.Model):
    """Policy snapshot protects earlier workdays from a later settings change."""

    attendance = models.OneToOneField(
        "attendance.Attendance", on_delete=models.CASCADE, related_name="mobile_policy"
    )
    mode = models.CharField(max_length=10, choices=ATTENDANCE_MODES, default=PAIRED)
    break_start = models.TimeField(blank=True, null=True)
    break_end = models.TimeField(blank=True, null=True)


class MobileActivity(models.Model):
    """A bounded, deliberately metadata-only mobile API audit event."""

    class Kind(models.TextChoices):
        LOGIN = "LOGIN", "Sign in"
        ONLINE_PUNCH = "ONLINE_PUNCH", "Online punch"
        OFFLINE_BATCH = "OFFLINE_BATCH", "Offline sync batch"
        OFFLINE_PUNCH = "OFFLINE_PUNCH", "Offline punch"
        QUEUE_REPORT = "QUEUE_REPORT", "Device queue report"

    class Outcome(models.TextChoices):
        ACCEPTED = "ACCEPTED", "Accepted"
        REPLAYED = "REPLAYED", "Already received"
        PARTIAL = "PARTIAL", "Partially accepted"
        REJECTED = "REJECTED", "Rejected"
        FAILED = "FAILED", "Unavailable"

    objects = HorillaCompanyManager()

    kind = models.CharField(max_length=16, choices=Kind.choices)
    outcome = models.CharField(max_length=8, choices=Outcome.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    company = models.ForeignKey(
        "base.Company", on_delete=models.SET_NULL, null=True, blank=True,
    )
    punch_uuid = models.UUIDField(null=True, blank=True)
    batch_id = models.UUIDField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(auto_now_add=True)
    status_code = models.PositiveSmallIntegerField()
    received_count = models.PositiveIntegerField(default=0)
    accepted_count = models.PositiveIntegerField(default=0)
    replayed_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)

    objects = HorillaCompanyManager("company")

    class Meta:
        default_permissions = ("view",)
        ordering = ("-finished_at", "-pk")
        indexes = [
            models.Index(fields=["company", "-finished_at"], name="klockin_mobile_audit_company"),
        ]
