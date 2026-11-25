from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase


class _ObjectStorage:
    def __init__(self):
        self.objects = {}
        self.writes = []

    def open(self, name, mode):
        if name not in self.objects:
            raise FileNotFoundError(name)
        return BytesIO(self.objects[name])

    def write_if_absent(self, name, source, size):
        if name in self.objects:
            raise FileExistsError(name)
        content = source.read(size + 1)
        if len(content) != size:
            raise ValueError("Unexpected upload size")
        self.writes.append(name)
        self.objects[name] = content


class MigrateUploadedMediaTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.storage = _ObjectStorage()
        factory = patch(
            "base.management.commands.migrate_uploaded_media.s3_upload_storage",
            return_value=self.storage,
        )
        factory.start()
        self.addCleanup(factory.stop)

    def _migrate(self, *, apply=False):
        output = StringIO()
        call_command(
            "migrate_uploaded_media", source=self.root, apply=apply, stdout=output
        )
        return output.getvalue()

    def test_dry_run_and_repeat_preserve_names_originals_and_local_only_files(self):
        key = "employee/document/signed offer.pdf"
        upload = self.root / key
        upload.parent.mkdir(parents=True)
        upload.write_bytes(b"Employee document")
        secret = self.root / ".generated_secret_key"
        secret.write_bytes(b"Server secret")
        hidden = self.root / "employee" / ".state"
        hidden.mkdir()
        (hidden / "job.txt").write_bytes(b"Local state")
        (self.root / "linked.txt").symlink_to(secret)
        (self.root / "linked-directory").symlink_to(upload.parent, target_is_directory=True)

        self.assertIn("1 file(s) to copy", self._migrate())
        self.assertEqual(self.storage.objects, {})
        self.assertIn("Copied and verified 1", self._migrate(apply=True))
        self.assertIn("1 already matched", self._migrate(apply=True))
        self.assertEqual(self.storage.writes, [key])
        self.assertEqual(self.storage.objects, {key: upload.read_bytes()})
        self.assertEqual(secret.read_bytes(), b"Server secret")

    def test_refuses_existing_object_with_different_bytes(self):
        name = "leave-request.pdf"
        path = self.root / name
        path.write_bytes(b"local")
        self.storage.objects[name] = b"different remote data"

        with self.assertRaisesRegex(CommandError, "object differs"):
            self._migrate(apply=True)

        self.assertEqual(self.storage.writes, [])
        self.assertEqual(self.storage.objects[name], b"different remote data")
        self.assertEqual(path.read_bytes(), b"local")
