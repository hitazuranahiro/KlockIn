import hashlib
import os
import stat
from pathlib import Path
from tempfile import SpooledTemporaryFile

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.utils import validate_file_name
from django.core.management.base import BaseCommand, CommandError

from klockin.upload_storage import s3_upload_storage


def _raise_walk_error(error):
    raise error


def _local_uploads(root):
    for directory, directories, filenames, dir_fd in os.fwalk(
        root, follow_symlinks=False, onerror=_raise_walk_error
    ):
        directories[:] = sorted(name for name in directories if not name.startswith("."))
        relative = Path(directory).relative_to(root)
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            info = os.stat(filename, dir_fd=dir_fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                continue
            name = (relative / filename).as_posix()
            if "\\" in name:
                raise SuspiciousFileOperation(f"Invalid media path: {name}")
            validate_file_name(name, allow_relative_path=True)
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            with os.fdopen(os.open(filename, flags, dir_fd=dir_fd), "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise OSError(f"The local file changed during migration: {name}")
                yield name, source, info


def _digest(source, snapshot=None):
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
        if snapshot is not None:
            snapshot.write(chunk)
    return digest.digest()


def _matches_remote(storage, name, expected):
    try:
        with storage.open(name, "rb") as remote:
            if _digest(remote) != expected:
                raise ValueError(f"The existing S3 object differs from the local file: {name}")
    except FileNotFoundError:
        return False
    return True


class Command(BaseCommand):
    help = "Verify or copy ordinary uploaded files from a local media directory to S3."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, help="Media directory (default: MEDIA_ROOT).")
        parser.add_argument("--apply", action="store_true", help="Write missing files to S3.")

    def handle(self, *, source, apply, **options):
        try:
            if source is None and not settings.MEDIA_ROOT:
                raise ValueError("Set MEDIA_ROOT or supply --source.")
            root = (source if source is not None else Path(settings.MEDIA_ROOT)).expanduser()
            if root.is_symlink() or not root.is_dir():
                raise ValueError("The media source must be a directory, not a symbolic link.")
            storage = s3_upload_storage()
            missing = matched = copied = 0
            for name, local, info in _local_uploads(root.resolve()):
                with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as snapshot:
                    expected = _digest(local, snapshot if apply else None)
                    current = os.fstat(local.fileno())
                    if (current.st_size, current.st_mtime_ns) != (info.st_size, info.st_mtime_ns):
                        raise OSError(f"The local file changed during migration: {name}")
                    if _matches_remote(storage, name, expected):
                        matched += 1
                        continue
                    if not apply:
                        missing += 1
                        continue
                    size = snapshot.tell()
                    snapshot.seek(0)
                    try:
                        storage.write_if_absent(name, snapshot, size)
                    except FileExistsError:
                        if not _matches_remote(storage, name, expected):
                            raise OSError(f"The S3 object disappeared during migration: {name}") from None
                        matched += 1
                    else:
                        if not _matches_remote(storage, name, expected):
                            raise OSError(f"The S3 upload could not be verified: {name}")
                        copied += 1
        except (OSError, ValueError, ImproperlyConfigured, SuspiciousFileOperation) as exc:
            raise CommandError(str(exc)) from exc

        if apply:
            result = f"Copied and verified {copied} file(s). {matched} already matched."
        else:
            result = f"Dry run. {missing} file(s) to copy, {matched} already matched."
        self.stdout.write(self.style.SUCCESS(result))
