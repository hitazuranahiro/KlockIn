from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ParseError

from ..storage import private_selfie_storage
from ..views import PunchJSONParser, UploadTooLarge


class PrivateUploadTests(SimpleTestCase):
    def test_storage_rejects_plain_and_prefixed_static_sources(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "static"
            for entry in (source, ("assets", source)):
                with self.subTest(entry=entry), override_settings(
                    STATICFILES_DIRS=[entry], KLOCKIN_SELFIE_ROOT=source / "private"
                ):
                    with self.assertRaises(ImproperlyConfigured):
                        private_selfie_storage().location

    def test_batch_json_read_is_bounded_and_excessive_nesting_is_rejected(self):
        parser = PunchJSONParser()
        with patch("klockin_attendance.views.MAX_OFFLINE_BYTES", 64):
            stream = BytesIO(b"[" * 5000)
            with self.assertRaises(UploadTooLarge):
                parser.parse(stream)
            self.assertEqual(stream.tell(), 65)
        with patch("rest_framework.parsers.JSONParser.parse", side_effect=RecursionError):
            with self.assertRaises(ParseError):
                parser.parse(BytesIO(b"[]"))
