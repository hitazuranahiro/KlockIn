from pathlib import Path

from cryptography.fernet import InvalidToken
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from klockin_attendance.evidence_backup import photo_path, read_photo, referenced_photo_names
from klockin_attendance.evidence_crypto import (
    ENC_PREFIX,
    evidence_cipher,
    protect_selfie,
    reveal_selfie,
)
from klockin_attendance.storage import PrivateS3SelfieStorage


def _verify_target(name, plaintext, sealed):
    if not sealed.startswith(ENC_PREFIX) or reveal_selfie(sealed) != plaintext:
        raise ValueError(f"The existing S3 object does not match the local selfie: {name}")


class Command(BaseCommand):
    help = "Verify or copy database-referenced attendance selfies from a local directory to S3."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, required=True, help="Directory containing punches/.")
        parser.add_argument("--apply", action="store_true", help="Write any missing encrypted objects to S3.")

    def handle(self, *, source, apply, **options):
        try:
            evidence_cipher(required=True)
            source = source.expanduser().resolve(strict=True)
            if not source.is_dir():
                raise ValueError("The evidence source must be a directory containing punches/.")
            storage = PrivateS3SelfieStorage()
            missing = 0
            matched = 0
            copied = 0
            for name in referenced_photo_names():
                raw = read_photo(photo_path(source, name))
                plaintext = reveal_selfie(raw)
                try:
                    remote = storage.read_sealed(name)
                except FileNotFoundError:
                    if not apply:
                        missing += 1
                        continue
                    sealed = raw if raw.startswith(ENC_PREFIX) else protect_selfie(raw, required=True)
                    try:
                        storage.write_sealed(name, sealed)
                    except FileExistsError:
                        # A concurrent import may have already published this object.
                        pass
                    else:
                        copied += 1
                        _verify_target(name, plaintext, storage.read_sealed(name))
                        continue
                    remote = storage.read_sealed(name)
                _verify_target(name, plaintext, remote)
                matched += 1
        except InvalidToken as exc:
            raise CommandError("Selfie authentication failed. Check the evidence keys and source files.") from exc
        except (OSError, ValueError, ImproperlyConfigured) as exc:
            raise CommandError(str(exc)) from exc

        if apply:
            result = f"Copied and verified {copied} photo(s). {matched} already matched."
        else:
            result = f"Dry run. {missing} photo(s) to copy, {matched} already matched."
        self.stdout.write(self.style.SUCCESS(result))
