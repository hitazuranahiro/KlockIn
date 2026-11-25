from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from botocore.exceptions import ClientError, EndpointConnectionError
from cryptography.fernet import Fernet
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from klockin.testkit import make_company, make_employee, make_user

from ..evidence_crypto import ENC_PREFIX, protect_selfie, reveal_selfie
from ..models import AttendancePunch
from ..storage import private_selfie_storage
from .test_ingestion import IngestionFixture, _online, _payload, _selfie


ENDPOINT = "https://r2.example.test"
BUCKET = "private-test-evidence"
S3_SETTINGS = {
    "KLOCKIN_SELFIE_STORAGE": "s3",
    "KLOCKIN_SELFIE_S3_ENDPOINT_URL": ENDPOINT,
    "KLOCKIN_SELFIE_S3_BUCKET": BUCKET,
    "KLOCKIN_SELFIE_S3_ACCESS_KEY_ID": "test-access-key",
    "KLOCKIN_SELFIE_S3_SECRET_ACCESS_KEY": "test-secret-key",
    "KLOCKIN_SELFIE_S3_REGION": "auto",
    "KLOCKIN_EVIDENCE_KEYS": [Fernet.generate_key().decode()],
    "KLOCKIN_EVIDENCE_BACKUP_KEY": Fernet.generate_key().decode(),
    "KLOCKIN_REQUIRE_EVIDENCE_ENCRYPTION": True,
    "KLOCKIN_REVERSE_GEOCODER_URL": "",
}


def _s3_error(operation, code, status):
    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        operation,
    )


class _Bucket:
    def __init__(self):
        self.objects = {}
        self.put_names = []
        self.get_names = []
        self.available = True

    def get_object(self, *, Bucket, Key):
        assert Bucket == BUCKET
        self.get_names.append(Key)
        try:
            payload = self.objects[Key]
        except KeyError:
            raise _s3_error("GetObject", "NoSuchKey", 404) from None
        return {"Body": BytesIO(payload), "ContentLength": len(payload)}

    def head_object(self, *, Bucket, Key):
        assert Bucket == BUCKET
        if Key not in self.objects:
            raise _s3_error("HeadObject", "404", 404)
        return {"ContentLength": len(self.objects[Key])}

    def put_object(self, *, Bucket, Key, Body, IfNoneMatch, ContentType):
        assert Bucket == BUCKET
        assert IfNoneMatch == "*" and ContentType == "application/octet-stream"
        assert Body.startswith(ENC_PREFIX)
        if not self.available:
            raise EndpointConnectionError(endpoint_url=ENDPOINT)
        if Key in self.objects:
            raise _s3_error("PutObject", "PreconditionFailed", 412)
        self.objects[Key] = Body
        self.put_names.append(Key)
        return {}

    def delete_object(self, *, Bucket, Key):
        assert Bucket == BUCKET
        self.objects.pop(Key, None)
        return {}


class _S3Fixture:
    def setUp(self):
        super().setUp()
        self.bucket = _Bucket()
        client = patch(
            "klockin_attendance.storage._s3_client", return_value=self.bucket
        )
        client.start()
        self.addCleanup(client.stop)


@override_settings(**S3_SETTINGS)
class S3PrivateStorageTests(_S3Fixture, SimpleTestCase):
    def test_seals_on_write_opens_privately_and_never_overwrites_existing_key(self):
        storage = private_selfie_storage()
        name = storage.save("punches/sample.jpg", ContentFile(_selfie()))
        sealed = self.bucket.objects[name]
        self.assertTrue(sealed.startswith(ENC_PREFIX))
        self.assertNotIn(_selfie(), sealed)
        self.assertEqual(storage.read_sealed(name), sealed)
        with storage.open(name, "rb") as photo:
            self.assertEqual(photo.read(), _selfie())
        with self.assertRaises(ValueError):
            storage.url(name)
        with self.assertRaises(FileExistsError):
            storage.write_sealed(name, protect_selfie(b"another photo", required=True))
        self.assertEqual(self.bucket.objects[name], sealed)
        with self.assertRaises(FileNotFoundError):
            storage.read_sealed("punches/missing.jpg")

    @override_settings(KLOCKIN_EVIDENCE_KEYS=[])
    def test_s3_never_uploads_plaintext_without_evidence_keys(self):
        with self.assertRaises(ImproperlyConfigured):
            private_selfie_storage().save("punches/sample.jpg", ContentFile(_selfie()))
        self.assertEqual(self.bucket.objects, {})


@override_settings(**S3_SETTINGS)
class S3PrivateEvidenceTests(_S3Fixture, IngestionFixture, TestCase):
    def _post(self, payload):
        field = AttendancePunch._meta.get_field("punch_selfie")
        with patch.object(field, "storage", private_selfie_storage()):
            return _online(self.api, payload)

    def _reviewer(self, name, company):
        reviewer = make_user(name)
        make_employee(company=company, email=reviewer.email, user=reviewer)
        reviewer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="attendance", codename="view_attendance"
            ),
            Permission.objects.get(
                content_type__app_label="klockin_attendance",
                codename="view_punch_evidence",
            ),
        )
        return reviewer

    def test_punch_upload_and_company_scoped_web_preview(self):
        posted = self._post(_payload())
        self.assertEqual(posted.status_code, 201, posted.data)
        punch = AttendancePunch.objects.get()
        name = punch.punch_selfie.name
        self.assertEqual(self.bucket.put_names, [name])
        self.assertFalse((self.private_path / name).exists())
        url = reverse("klockin-punch-selfie", args=[punch.pk])
        other_company = make_company("Another evidence company", hq=False)
        field = AttendancePunch._meta.get_field("punch_selfie")
        with patch.object(field, "storage", private_selfie_storage()):
            self.client.force_login(self._reviewer("different-reviewer", other_company))
            reads_before = len(self.bucket.get_names)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(len(self.bucket.get_names), reads_before)
            self.client.force_login(self._reviewer("evidence-reviewer", self.company))
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/jpeg")
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(b"".join(response.streaming_content), _selfie())

    def test_unavailable_s3_returns_retryable_receipt(self):
        self.bucket.available = False
        payload = _payload()
        with self.assertLogs("klockin_attendance.views", level="ERROR"):
            response = self._post(payload)
        self.assertEqual(response.status_code, 503, response.data)
        self.assertEqual(response.data["code"], "punch_unavailable")
        self.assertFalse(AttendancePunch.objects.exists())
        self.bucket.available = True
        self.assertEqual(self._post(payload).status_code, 201)
        self.assertEqual(AttendancePunch.objects.count(), 1)
        self.assertEqual(len(self.bucket.objects), 1)

    def _local_photo(self):
        with override_settings(
            KLOCKIN_SELFIE_STORAGE="local",
            KLOCKIN_EVIDENCE_KEYS=[],
            KLOCKIN_REQUIRE_EVIDENCE_ENCRYPTION=False,
        ):
            posted = self._post(_payload())
        self.assertEqual(posted.status_code, 201, posted.data)
        name = AttendancePunch.objects.get().punch_selfie.name
        return name, self.private_path / name

    def test_dry_run_idempotent_import_and_s3_archive_restore(self):
        name, photo = self._local_photo()
        self.assertEqual(photo.read_bytes(), _selfie())
        command = ("import_private_evidence_to_s3", "--source", str(self.private_path))
        call_command(*command, stdout=StringIO())
        self.assertEqual(self.bucket.objects, {})
        call_command(*command, "--apply", stdout=StringIO())
        call_command(*command, "--apply", stdout=StringIO())
        self.assertEqual(self.bucket.put_names, [name])
        self.assertEqual(photo.read_bytes(), _selfie())
        self.assertEqual(reveal_selfie(self.bucket.objects[name]), _selfie())

        with TemporaryDirectory() as directory:
            archive = Path(directory) / "backup.enc"
            staged = Path(directory) / "restore"
            call_command(
                "backup_private_evidence", "create", str(archive), stdout=StringIO()
            )
            call_command(
                "backup_private_evidence", "verify", str(archive), stdout=StringIO()
            )
            call_command(
                "backup_private_evidence",
                "restore",
                str(archive),
                "--destination",
                str(staged),
                "--apply",
                stdout=StringIO(),
            )
            self.assertEqual((staged / name).read_bytes(), self.bucket.objects[name])

    def test_import_never_replaces_different_photo(self):
        name, photo = self._local_photo()
        existing = protect_selfie(b"existing evidence", required=True)
        self.bucket.objects[name] = existing
        with self.assertRaises(CommandError):
            call_command(
                "import_private_evidence_to_s3",
                "--source",
                str(self.private_path),
                "--apply",
                stdout=StringIO(),
            )
        self.assertEqual(self.bucket.objects[name], existing)
        self.assertEqual(self.bucket.put_names, [])
        self.assertEqual(photo.read_bytes(), _selfie())

    def test_backup_fails_without_publishing_partial_archive_for_missing_s3_photo(self):
        posted = self._post(_payload())
        self.assertEqual(posted.status_code, 201, posted.data)
        name = AttendancePunch.objects.get().punch_selfie.name
        del self.bucket.objects[name]
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "backup.enc"
            with self.assertRaises(CommandError):
                call_command(
                    "backup_private_evidence", "create", str(archive), stdout=StringIO()
                )
            self.assertEqual(list(archive.parent.iterdir()), [])
