import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.dateparse import parse_datetime
from PIL import Image
from rest_framework import serializers

from .models import AttendancePunch


MAX_SELFIE_BYTES = 2 * 1024 * 1024
MAX_SELFIE_PIXELS = 16_000_000
MAX_BATCH_ITEMS = 5
ALLOWED_CLOCK_SKEW = timedelta(minutes=5)


class PunchSelfieField(serializers.FileField):
    def to_internal_value(self, data):
        upload = super().to_internal_value(data)
        if upload.size > MAX_SELFIE_BYTES:
            raise serializers.ValidationError("Selfies must be 2 MiB or smaller.")

        try:
            with Image.open(upload, formats=("JPEG", "PNG")) as image:
                if image.width * image.height > MAX_SELFIE_PIXELS:
                    raise serializers.ValidationError("The image exceeds 16 megapixels.")
                if getattr(image, "n_frames", 1) != 1:
                    raise serializers.ValidationError("Submit a single still image.")
                image_format = image.format
                image.load()
        except (Image.DecompressionBombError, OSError, SyntaxError, ValueError):
            raise serializers.ValidationError("Submit a valid JPEG or PNG image.")
        finally:
            upload.seek(0)

        upload.name = "selfie.jpg" if image_format == "JPEG" else "selfie.png"
        return upload


class EncodedSelfieField(PunchSelfieField):
    def to_internal_value(self, data):
        max_encoded_size = 4 * ((MAX_SELFIE_BYTES + 2) // 3)
        if not isinstance(data, str) or len(data) > max_encoded_size:
            raise serializers.ValidationError("Submit a Base64 selfie of at most 2 MiB.")
        try:
            content = base64.b64decode(data, validate=True)
        except ValueError:
            raise serializers.ValidationError("The selfie is not valid Base64.")
        return super().to_internal_value(SimpleUploadedFile("selfie", content))


class PunchSerializer(serializers.Serializer):
    trust_server_time = True

    punch_uuid = serializers.UUIDField()
    punch_type = serializers.ChoiceField(
        choices=AttendancePunch.PunchType.choices,
        error_messages={"invalid_choice": "Use CLOCK_IN or CLOCK_OUT."},
    )
    punched_at = serializers.CharField(max_length=40)
    device_id = serializers.CharField(max_length=128)
    punch_selfie = PunchSelfieField(write_only=True)
    gps_lat = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=Decimal(-90), max_value=Decimal(90)
    )
    gps_long = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=Decimal(-180), max_value=Decimal(180)
    )
    detected_address = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )

    def validate_punch_uuid(self, value):
        if value.version != 4:
            raise serializers.ValidationError("Use a UUIDv4 for each punch.")
        return value

    def validate_punched_at(self, value):
        try:
            stamp = parse_datetime(value)
            if stamp is not None and stamp.utcoffset() is not None:
                stamp = stamp.astimezone(timezone.utc)
            else:
                stamp = None
        except (OverflowError, ValueError):
            stamp = None
        if stamp is None:
            raise serializers.ValidationError("Use an ISO 8601 timestamp with a UTC offset.")

        if stamp < datetime(1970, 1, 1, tzinfo=timezone.utc):
            raise serializers.ValidationError("Use a punch timestamp on or after 1970.")
        if not self.trust_server_time and stamp > self.context["received_at"] + ALLOWED_CLOCK_SKEW:
            raise serializers.ValidationError("The punch time is ahead of the server clock.")
        return stamp


class OfflinePunchSerializer(PunchSerializer):
    trust_server_time = False
    punch_selfie = EncodedSelfieField(write_only=True)


class DeviceQueueReportSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=128, trim_whitespace=False)
    pending_punches = serializers.IntegerField(min_value=0, max_value=2_147_483_647)
    observed_at = serializers.DateTimeField(default_timezone=timezone.utc)

    def validate_observed_at(self, value):
        if value > self.context["received_at"] + ALLOWED_CLOCK_SKEW:
            raise serializers.ValidationError("The queue observation is ahead of the server clock.")
        return value


class PunchReceiptSerializer(serializers.ModelSerializer):
    projection_status = serializers.SerializerMethodField()

    class Meta:
        model = AttendancePunch
        fields = (
            "punch_uuid",
            "sync_status",
            "punched_at",
            "server_receive_timestamp",
            "attendance_id",
            "projection_status",
            "detected_address",
        )

    def get_projection_status(self, obj):
        return "LINKED" if obj.attendance_id else "PENDING"
