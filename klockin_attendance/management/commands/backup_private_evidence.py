from pathlib import Path
import tarfile

from cryptography.exceptions import InvalidTag
from cryptography.fernet import InvalidToken
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from klockin_attendance.evidence_backup import create_backup, restore_backup, verify_backup


class Command(BaseCommand):
    help = "Create, verify, or stage an encrypted backup of private attendance photos."

    def add_arguments(self, parser):
        parser.add_argument("operation", choices=("create", "verify", "restore"))
        parser.add_argument("archive", type=Path)
        parser.add_argument("--destination", type=Path)
        parser.add_argument("--apply", action="store_true", help="Publish a verified restore into the new staging directory.")

    def handle(self, *, operation, archive, destination, apply, **options):
        archive = archive.expanduser().absolute()
        if operation != "restore" and (destination is not None or apply):
            raise CommandError("--destination and --apply are available only for restore.")
        try:
            if operation == "create":
                count = create_backup(archive)
                message = "Created an authenticated encrypted backup"
            elif operation == "verify":
                count = len(verify_backup(archive))
                message = "Verified the encrypted backup"
            else:
                if destination is None:
                    raise CommandError("Supply a new --destination directory for restore.")
                destination = destination.expanduser().absolute()
                if destination.is_symlink():
                    raise CommandError("The restore destination may not be a symbolic link.")
                count = restore_backup(archive, destination.resolve(), apply=apply)
                message = "Staged the encrypted restore" if apply else "Verified restore dry run"
        except (InvalidTag, InvalidToken) as exc:
            raise CommandError("Backup authentication failed. Check the keys and archive integrity.") from exc
        except (OSError, ValueError, ImproperlyConfigured, tarfile.TarError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"{message} ({count} photo(s))."))
