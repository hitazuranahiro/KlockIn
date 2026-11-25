"""Authenticated encrypted backup and staged restore of attendance selfies."""

import base64
import hashlib
import io
import os
import stat
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .evidence_crypto import (
    ENC_PREFIX, MAX_STORED_SELFIE_BYTES, evidence_cipher, protect_selfie, reveal_selfie,
)
from .storage import PHOTO_NAME, PrivateS3SelfieStorage, PrivateSelfieStorage, private_selfie_storage

MAGIC = b"KLOCKIN-BACKUP-1\0"
TAG_BYTES = 16
NONCE_BYTES = 12


def _backup_cipher(header):
    key = settings.KLOCKIN_EVIDENCE_BACKUP_KEY
    try:
        key_bytes = base64.b64decode(key, altchars=b"-_", validate=True)
        if len(key_bytes) != 32:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured("Set KLOCKIN_EVIDENCE_BACKUP_KEY to a separate 32-byte Fernet-format key.") from exc
    if any(
        key_bytes == base64.urlsafe_b64decode(key) for key in settings.KLOCKIN_EVIDENCE_KEYS
    ):
        raise ImproperlyConfigured("Use different evidence and backup keys.")
    return key_bytes, header[len(MAGIC):]


def _header_ok(header):
    return len(header) == len(MAGIC) + NONCE_BYTES and header.startswith(MAGIC)


def photo_path(root, name):
    if not isinstance(name, str) or not PHOTO_NAME.fullmatch(name):
        raise ValueError("Invalid attendance evidence filename.")
    directory = root / "punches"
    if directory.is_symlink():
        raise ValueError("The private evidence directory must not be a symbolic link.")
    return root / name


def read_photo(path):
    options = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, options), "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_STORED_SELFIE_BYTES:
            raise ValueError("Private evidence is not a supported regular photo file.")
        raw = source.read(MAX_STORED_SELFIE_BYTES + 1)
        if len(raw) != info.st_size:
            raise ValueError("Private evidence changed while being read; retry after writes finish.")
        return raw


def referenced_photo_names():
    from .models import AttendancePunch

    return (
        AttendancePunch.objects.exclude(punch_selfie="")
        .order_by("punch_selfie")
        .values_list("punch_selfie", flat=True)
        .distinct()
        .iterator()
    )


def _photos_to_backup(storage):
    if isinstance(storage, PrivateS3SelfieStorage):
        for name in referenced_photo_names():
            if not PHOTO_NAME.fullmatch(name):
                raise ValueError("Invalid attendance evidence filename.")
            try:
                yield name, storage.read_sealed(name)
            except FileNotFoundError as exc:
                raise ValueError("A referenced selfie is missing from S3. Check the bucket and object prefix.") from exc
        return

    root = Path(storage.location)
    directory = root / "punches"
    if directory.is_symlink():
        raise ValueError("The private evidence directory must not be a symbolic link.")
    for photo in sorted(directory.glob("*")):
        name = f"punches/{photo.name}"
        yield name, read_photo(photo_path(root, name))


class _EncryptedWriter:
    def __init__(self, target, encryptor):
        self.target = target
        self.encryptor = encryptor

    def write(self, chunk):
        self.target.write(self.encryptor.update(chunk))
        return len(chunk)


class _DecryptedReader(io.RawIOBase):
    def __init__(self, source, decryptor, remaining):
        self.source = source
        self.decryptor = decryptor
        self.remaining = remaining
        self.finished = False

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.remaining == 0:
            if not self.finished:
                self.decryptor.finalize()
                self.finished = True
            return 0
        chunk = self.source.read(min(len(buffer), self.remaining))
        if not chunk:
            raise ValueError("The encrypted backup is truncated.")
        plain = self.decryptor.update(chunk)
        buffer[:len(plain)] = plain
        self.remaining -= len(chunk)
        return len(plain)


def _crypto_reader(source):
    header = source.read(len(MAGIC) + NONCE_BYTES)
    if not _header_ok(header):
        raise ValueError("Unrecognized encrypted attendance backup header.")
    key, nonce = _backup_cipher(header)
    end = source.seek(0, os.SEEK_END)
    remaining = end - len(header) - TAG_BYTES
    if remaining <= 0:
        raise ValueError("The encrypted backup is truncated.")
    source.seek(end - TAG_BYTES)
    tag = source.read(TAG_BYTES)
    source.seek(len(header))
    decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    decryptor.authenticate_additional_data(header)
    return io.BufferedReader(_DecryptedReader(source, decryptor, remaining))


def create_backup(archive):
    """Publish a protected backup under a new name, leaving files where they are."""
    evidence_cipher(required=True)
    header = MAGIC + os.urandom(NONCE_BYTES)
    key, nonce = _backup_cipher(header)
    storage = private_selfie_storage()
    if archive.exists() or archive.is_symlink():
        raise FileExistsError("The backup destination already exists.")

    names = set()
    with tempfile.NamedTemporaryFile(dir=archive.parent, prefix=".klockin-backup-", delete=False) as target:
        temporary = Path(target.name)
        try:
            target.write(header)
            encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
            encryptor.authenticate_additional_data(header)
            with tarfile.open(mode="w|", fileobj=_EncryptedWriter(target, encryptor)) as bundle:
                for name, raw in _photos_to_backup(storage):
                    if raw.startswith(ENC_PREFIX):
                        reveal_selfie(raw)
                        sealed = raw
                    else:
                        sealed = protect_selfie(raw, required=True)
                    entry = tarfile.TarInfo(name)
                    entry.size = len(sealed)
                    entry.mode = 0o600
                    bundle.addfile(entry, io.BytesIO(sealed))
                    names.add(name)
            if any(name not in names for name in referenced_photo_names()):
                raise ValueError("A referenced selfie was missing from the backup. Check private storage and pause writes.")
            target.write(encryptor.finalize())
            target.write(encryptor.tag)
            target.flush()
            os.fsync(target.fileno())
            os.link(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
    return len(names)


def verify_backup(archive, *, staged_destination=None):
    """Authenticate the archive and every stored selfie. Never extract raw paths."""
    evidence_cipher(required=True)
    hashes = {}
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(archive, flags), "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("The backup input must be a regular file.")
        with _crypto_reader(source) as plaintext:
            while plaintext.read(128 * 1024):
                pass
        source.seek(0)
        with _crypto_reader(source) as plaintext:
            with tarfile.open(mode="r|", fileobj=plaintext) as bundle:
                for entry in bundle:
                    if (
                        not entry.isreg() or not PHOTO_NAME.fullmatch(entry.name)
                        or not 0 < entry.size <= MAX_STORED_SELFIE_BYTES or entry.name in hashes
                    ):
                        raise ValueError("Unsupported or duplicate entry in attendance backup.")
                    with bundle.extractfile(entry) as item:
                        sealed = item.read(MAX_STORED_SELFIE_BYTES + 1)
                    if len(sealed) != entry.size or not sealed.startswith(ENC_PREFIX):
                        raise ValueError("The archive contains unencrypted or incomplete evidence.")
                    hashes[entry.name] = hashlib.sha256(reveal_selfie(sealed)).digest()
                    if staged_destination is not None:
                        photo = photo_path(staged_destination, entry.name)
                        with os.fdopen(os.open(photo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as target:
                            target.write(sealed)
                            target.flush()
                            os.fsync(target.fileno())
            # tarfile stops at an end marker. Force AES-GCM tag verification.
            while plaintext.read(128 * 1024):
                pass
    return hashes


def restore_backup(archive, destination, *, apply=False):
    storage_root = Path(PrivateSelfieStorage().location)
    public = (settings.MEDIA_ROOT, settings.STATIC_ROOT, *(
        item[1] if isinstance(item, (tuple, list)) else item
        for item in settings.STATICFILES_DIRS
    ))
    if destination == storage_root or destination.is_relative_to(storage_root) or any(
        root and destination.is_relative_to(Path(root).resolve()) for root in public
    ):
        raise ValueError("Restore into a new staging directory outside the live and public roots.")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("The restore destination already exists.")
    if not apply:
        return len(verify_backup(archive))
    with tempfile.TemporaryDirectory(prefix=".klockin-restore-", dir=destination.parent) as temporary:
        staged = Path(temporary)
        (staged / "punches").mkdir(mode=0o700)
        hashes = verify_backup(archive, staged_destination=staged)
        destination.mkdir(mode=0o700)
        try:
            (staged / "punches").rename(destination / "punches")
        except OSError:
            destination.rmdir()
            raise
        return len(hashes)
