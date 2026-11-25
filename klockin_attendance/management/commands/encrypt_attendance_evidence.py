import hashlib
import os
import tarfile
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.db.models.functions import Cast

from klockin_attendance.evidence_backup import photo_path, read_photo, referenced_photo_names, verify_backup
from klockin_attendance.evidence_crypto import (
    ENC_PREFIX, TEXT_PREFIX, evidence_cipher, protect_selfie, reveal_selfie,
)
from klockin_attendance.models import AttendancePunch
from klockin_attendance.storage import private_selfie_storage

FIELDS = ("gps_lat", "gps_long", "detected_address")


def _replace_verified_photo(path, raw):
    sealed = protect_selfie(raw, required=True)
    if reveal_selfie(sealed) != raw:
        raise ValueError("The new evidence could not be verified.")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".klockin-encrypt-", delete=False) as target:
        temporary = Path(target.name)
        try:
            target.write(sealed)
            target.flush()
            os.fsync(target.fileno())
            if read_photo(path) != raw:
                raise ValueError("The legacy photo changed, retry after writes finish.")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _query():
    return AttendancePunch.objects.annotate(**{
        f"_raw_{field}": Cast(field, output_field=models.TextField()) for field in FIELDS
    })


def _clear_fields(punch):
    for field in FIELDS:
        raw = getattr(punch, f"_raw_{field}")
        if raw and not raw.startswith(TEXT_PREFIX):
            yield field


def _process_photos(root, backed_up, *, apply):
    directory = root / "punches"
    if directory.is_symlink():
        raise ValueError("The private evidence directory must not be a symbolic link.")
    names = {f"punches/{photo.name}" for photo in directory.glob("*")}
    if any(name not in names for name in referenced_photo_names()):
        raise ValueError("A referenced selfie is missing from the volume. Confirm the private storage mount.")
    count = 0
    for name in sorted(names):
        target = photo_path(root, name)
        raw = read_photo(target)
        if raw.startswith(ENC_PREFIX):
            reveal_selfie(raw)
            continue
        if apply:
            if backed_up.get(name) != hashlib.sha256(raw).digest():
                raise CommandError("A legacy photo does not match the verified backup. Take a fresh backup and retry.")
            _replace_verified_photo(target, raw)
        count += 1
    return count


def _process_locations(*, apply):
    if not apply:
        return sum(bool(tuple(_clear_fields(punch))) for punch in _query().iterator())
    count = 0
    for pk in AttendancePunch.objects.values_list("pk", flat=True).iterator():
        with transaction.atomic():
            punch = _query().select_for_update().get(pk=pk)
            fields = tuple(_clear_fields(punch))
            if fields:
                punch.save(update_fields=fields)
                count += 1
    return count


class Command(BaseCommand):
    help = "Inspect or encrypt legacy attendance evidence using a verified recoverable photo backup."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup", type=Path, help="Verified archive created before changing legacy photos.")

    def handle(self, *, apply, backup, **options):
        if settings.KLOCKIN_SELFIE_STORAGE != "local":
            raise CommandError(
                "Legacy evidence encryption requires local storage. Run it against the local volume before importing to S3."
            )
        if apply and backup is None:
            raise CommandError("Create a private evidence backup and supply it as --backup before applying.")
        try:
            evidence_cipher(required=apply)
            backed_up = verify_backup(backup.expanduser().absolute()) if backup else {}
            root = Path(private_selfie_storage().location)
            photos = _process_photos(root, backed_up, apply=apply)
            rows = _process_locations(apply=apply)
        except (InvalidTag, InvalidToken) as exc:
            raise CommandError("Evidence authentication failed. Check the encryption keys and the backup.") from exc
        except (OSError, ValueError, ImproperlyConfigured, tarfile.TarError) as exc:
            raise CommandError(str(exc)) from exc
        verb = "Encrypted" if apply else "Dry run found"
        self.stdout.write(f"{verb} {rows} GPS/address row(s) and {photos} legacy photo(s).")
