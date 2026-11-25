from io import StringIO
from pathlib import Path

from cryptography.fernet import Fernet
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings

from .test_ingestion import IngestionFixture, _online, _payload, _selfie
from ..evidence_crypto import ENC_PREFIX, TEXT_PREFIX
from ..models import AttendancePunch
from ..storage import private_selfie_storage

EVIDENCE_KEY = Fernet.generate_key().decode()
BACKUP_KEY = Fernet.generate_key().decode()


def _raw_location(punch):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT gps_lat, gps_long, detected_address FROM klockin_attendance_attendancepunch WHERE punch_uuid = %s",
            [punch.pk.hex],
        )
        return cursor.fetchone()


class PrivateEvidenceTests(IngestionFixture, TestCase):
    def _create(self):
        result = _online(self.api, _payload(detected_address="Example, Manila"))
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["detected_address"], "Example, Manila")
        return AttendancePunch.objects.get()

    @override_settings(KLOCKIN_EVIDENCE_KEYS=[EVIDENCE_KEY], KLOCKIN_REQUIRE_EVIDENCE_ENCRYPTION=True)
    def test_photo_and_location_encrypt_transparently(self):
        punch = self._create()
        self.assertEqual(str(punch.gps_lat), "14.599500")
        self.assertEqual(punch.detected_address, "Example, Manila")
        self.assertTrue(all(value.startswith(TEXT_PREFIX) for value in _raw_location(punch)))
        raw = (self.private_path / punch.punch_selfie.name).read_bytes()
        self.assertTrue(raw.startswith(ENC_PREFIX))
        self.assertNotIn(_selfie(), raw)
        with override_settings(KLOCKIN_EVIDENCE_KEYS=[Fernet.generate_key().decode(), EVIDENCE_KEY]):
            self.assertEqual(AttendancePunch.objects.get().detected_address, "Example, Manila")
            with punch.punch_selfie.open("rb") as photo:
                self.assertEqual(photo.read(), _selfie())

    def test_legacy_read_backup_backfill_and_staged_restore(self):
        with override_settings(KLOCKIN_EVIDENCE_KEYS=[], KLOCKIN_REQUIRE_EVIDENCE_ENCRYPTION=False):
            punch = self._create()
        path = self.private_path / punch.punch_selfie.name
        archive = self.private_path / "backup.enc"
        restore = self.private_path.parent / (self.private_path.name + "-restore")
        damaged = self.private_path / "damaged.enc"
        self.addCleanup(lambda: _remove_restore(restore))
        original = path.read_bytes()
        self.assertEqual(original, _selfie())
        orphan = path.parent / "orphan.jpg"
        orphan.write_bytes(original)
        with override_settings(KLOCKIN_EVIDENCE_KEYS=[EVIDENCE_KEY], KLOCKIN_EVIDENCE_BACKUP_KEY=BACKUP_KEY):
            punch.refresh_from_db()
            self.assertEqual(punch.detected_address, "Example, Manila")
            output = StringIO()
            call_command("encrypt_attendance_evidence", stdout=output)
            self.assertIn("1 GPS/address row(s) and 2 legacy photo(s)", output.getvalue())
            with self.assertRaises(CommandError):
                call_command("encrypt_attendance_evidence", "--apply")
            call_command("backup_private_evidence", "create", str(archive))
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(original, archive.read_bytes())
            encoded = bytearray(archive.read_bytes())
            encoded[-1] ^= 1
            damaged.write_bytes(encoded)
            with self.assertRaises(CommandError):
                call_command("backup_private_evidence", "restore", str(damaged), "--destination", str(restore), "--apply")
            self.assertFalse(restore.exists())
            self.assertEqual(path.read_bytes(), original)
            call_command("backup_private_evidence", "verify", str(archive))
            call_command("encrypt_attendance_evidence", "--apply", "--backup", str(archive))
            self.assertTrue(path.read_bytes().startswith(ENC_PREFIX))
            self.assertTrue(orphan.read_bytes().startswith(ENC_PREFIX))
            self.assertTrue(all(value.startswith(TEXT_PREFIX) for value in _raw_location(punch)))
            output = StringIO()
            call_command("encrypt_attendance_evidence", "--apply", "--backup", str(archive), stdout=output)
            self.assertIn("0 GPS/address row(s) and 0 legacy photo(s)", output.getvalue())
            call_command("backup_private_evidence", "restore", str(archive), "--destination", str(restore))
            self.assertFalse(restore.exists())
            call_command("backup_private_evidence", "restore", str(archive), "--destination", str(restore), "--apply")
            with override_settings(KLOCKIN_SELFIE_ROOT=restore):
                with private_selfie_storage().open(punch.punch_selfie.name, "rb") as photo:
                    self.assertEqual(photo.read(), original)
            with self.assertRaises(CommandError):
                call_command("backup_private_evidence", "restore", str(archive), "--destination", str(restore), "--apply")


def _remove_restore(path):
    import shutil

    if path.exists():
        shutil.rmtree(path)
