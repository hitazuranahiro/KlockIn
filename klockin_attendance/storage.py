import re
from contextlib import closing
from functools import cached_property
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage

from .evidence_crypto import ENC_PREFIX, MAX_STORED_SELFIE_BYTES, evidence_cipher, protect_selfie, reveal_selfie

PHOTO_NAME = re.compile(r"punches/[a-zA-Z0-9_.-]+\.(?:jpg|jpeg|png)", re.IGNORECASE)


class PrivateSelfieStorage(FileSystemStorage):
    @property
    def location(self):
        root = Path(settings.KLOCKIN_SELFIE_ROOT).resolve()
        static_sources = (
            entry[1] if isinstance(entry, (tuple, list)) else entry
            for entry in settings.STATICFILES_DIRS
        )
        public_roots = (settings.MEDIA_ROOT, settings.STATIC_ROOT, *static_sources)
        if any(path and root.is_relative_to(Path(path).resolve()) for path in public_roots):
            raise ImproperlyConfigured(
                "KLOCKIN_SELFIE_ROOT must be outside the public media and static roots."
            )
        return str(root)

    def _open(self, name, mode="rb"):
        if mode != "rb":
            raise ValueError("Attendance selfies are read only.")
        with super()._open(name, mode) as source:
            payload = source.read(MAX_STORED_SELFIE_BYTES + 1)
        if len(payload) > MAX_STORED_SELFIE_BYTES:
            raise OSError("Stored selfie exceeds the permitted size.")
        return ContentFile(reveal_selfie(payload), name=name)

    def _save(self, name, content):
        return super()._save(name, ContentFile(protect_selfie(content.read()), name=name))

    def url(self, name):
        raise ValueError("Attendance selfies have no public URL.")


def _s3_client(endpoint, region, access_key, secret_key):
    from boto3.session import Session
    from botocore.config import Config

    return Session().client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=2,
            read_timeout=4,
            retries={"mode": "standard", "total_max_attempts": 2},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


class PrivateS3SelfieStorage(Storage):
    """Store only encrypted photo bytes and serve them through Django."""

    def __init__(self):
        self.endpoint = settings.KLOCKIN_SELFIE_S3_ENDPOINT_URL
        self.bucket = settings.KLOCKIN_SELFIE_S3_BUCKET
        self.access_key = settings.KLOCKIN_SELFIE_S3_ACCESS_KEY_ID
        self.secret_key = settings.KLOCKIN_SELFIE_S3_SECRET_ACCESS_KEY
        self.region = settings.KLOCKIN_SELFIE_S3_REGION
        if not all((self.endpoint, self.bucket, self.access_key, self.secret_key, self.region)):
            raise ImproperlyConfigured("Set the KLOCKIN_SELFIE_S3 endpoint, bucket, credentials and region.")
        try:
            endpoint = urlsplit(self.endpoint)
            valid_port = endpoint.port is None or 0 < endpoint.port <= 65535
        except ValueError:
            raise ImproperlyConfigured("Set a valid HTTPS attendance storage endpoint.") from None
        if (
            endpoint.scheme != "https" or not endpoint.hostname or not valid_port
            or endpoint.username is not None or endpoint.password is not None
            or endpoint.path not in ("", "/") or endpoint.query or endpoint.fragment
        ):
            raise ImproperlyConfigured("Set an HTTPS attendance storage endpoint with only a host and optional port.")
        evidence_cipher(required=True)

    @cached_property
    def client(self):
        return _s3_client(self.endpoint, self.region, self.access_key, self.secret_key)

    def _request(self, operation, name, **parameters):
        from botocore.exceptions import BotoCoreError, ClientError

        if not isinstance(name, str) or not PHOTO_NAME.fullmatch(name):
            raise ValueError("Invalid attendance evidence filename.")
        try:
            return getattr(self.client, operation)(Bucket=self.bucket, Key=name, **parameters)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if operation in ("get_object", "head_object") and code in ("NoSuchKey", "NotFound", "404"):
                raise FileNotFoundError("Attendance photo is missing from object storage.") from exc
            if operation == "put_object" and code in ("PreconditionFailed", "412"):
                raise FileExistsError("Attendance photo already exists in object storage.") from exc
            raise OSError("Attendance evidence storage request failed.") from exc
        except BotoCoreError as exc:
            raise OSError("Attendance evidence storage is unavailable.") from exc

    def read_sealed(self, name):
        from botocore.exceptions import BotoCoreError

        response = self._request("get_object", name)
        with closing(response["Body"]) as body:
            expected = response.get("ContentLength")
            if not isinstance(expected, int) or not 0 < expected <= MAX_STORED_SELFIE_BYTES:
                raise OSError("Stored selfie has an invalid size.")
            try:
                payload = body.read(MAX_STORED_SELFIE_BYTES + 1)
            except BotoCoreError as exc:
                raise OSError("Attendance photo could not be read from object storage.") from exc
        if len(payload) != expected or not payload.startswith(ENC_PREFIX):
            raise OSError("Stored selfie is incomplete or unencrypted.")
        return payload

    def write_sealed(self, name, sealed):
        if not 0 < len(sealed) <= MAX_STORED_SELFIE_BYTES or not sealed.startswith(ENC_PREFIX):
            raise ValueError("Object storage requires a supported encrypted selfie.")
        reveal_selfie(sealed)
        self._request("put_object", name, Body=sealed, IfNoneMatch="*", ContentType="application/octet-stream")

    def _open(self, name, mode="rb"):
        if mode != "rb":
            raise ValueError("Attendance selfies are read only.")
        return ContentFile(reveal_selfie(self.read_sealed(name)), name=name)

    def get_available_name(self, name, max_length=None):
        # New punches use unique keys. The conditional PUT arbitrates collisions
        # without a separate HEAD on every punch.
        if not PHOTO_NAME.fullmatch(name) or (max_length is not None and len(name) > max_length):
            raise SuspiciousFileOperation("Invalid attendance evidence filename.")
        return name

    def _save(self, name, content):
        raw = content.read(MAX_STORED_SELFIE_BYTES + 1)
        if not 0 < len(raw) <= MAX_STORED_SELFIE_BYTES:
            raise OSError("Uploaded selfie has an invalid size.")
        self.write_sealed(name, protect_selfie(raw, required=True))
        return name

    def exists(self, name):
        try:
            self._request("head_object", name)
        except FileNotFoundError:
            return False
        return True

    def delete(self, name):
        self._request("delete_object", name)

    def url(self, name):
        raise ValueError("Attendance selfies have no public URL.")


def private_selfie_storage():
    backend = settings.KLOCKIN_SELFIE_STORAGE
    if backend == "local":
        return PrivateSelfieStorage(file_permissions_mode=0o600, directory_permissions_mode=0o700)
    if backend == "s3":
        return PrivateS3SelfieStorage()
    raise ImproperlyConfigured("KLOCKIN_SELFIE_STORAGE must be local or s3.")
