"""Backup zip helper smoke tests."""

import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

from django.test import SimpleTestCase

from klockin_backup.zip import zip_folder, zip_uploaded_files


class ZipFolderTests(SimpleTestCase):
    def test_zips_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            root.mkdir()
            (root / "note.txt").write_text("hello", encoding="utf-8")
            (root / ".generated_secret_key").write_text("internal", encoding="utf-8")
            credentials = root / "gdrive_oauth_credentials_file"
            credentials.mkdir()
            (credentials / "config.json").write_text("internal", encoding="utf-8")
            out = Path(tmp) / "out.zip"
            zip_folder(str(root), str(out))
            with zipfile.ZipFile(out) as zf:
                self.assertEqual(zf.namelist(), ["note.txt"])

    def test_zips_remote_uploads_without_internal_files(self):
        storage = Mock()
        storage.iter_upload_names.return_value = [
            "documents/contract.txt",
            ".generated_secret_key",
            "gdrive_oauth_credentials_file/config.json",
            "../outside",
        ]
        storage.open.return_value = BytesIO(b"private document")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.zip"
            zip_uploaded_files(storage, out)
            with zipfile.ZipFile(out) as zf:
                self.assertEqual(zf.namelist(), ["documents/contract.txt"])
                self.assertEqual(zf.read("documents/contract.txt"), b"private document")
        storage.open.assert_called_once_with("documents/contract.txt", "rb")
