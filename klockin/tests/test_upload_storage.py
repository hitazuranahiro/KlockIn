from io import BytesIO

from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import SimpleTestCase, override_settings


@override_settings(
    MEDIA_URL="/media/",
    KLOCKIN_S3_ENDPOINT_URL="https://storage.example.test",
    KLOCKIN_S3_BUCKET="klockin-test",
    KLOCKIN_S3_REGION="auto",
    KLOCKIN_S3_ACCESS_KEY_ID="test",
    KLOCKIN_S3_SECRET_ACCESS_KEY="test",
    STORAGES={
        "default": {"BACKEND": "klockin.upload_storage.PrivateUploadStorage"},
    },
)
class PrivateUploadStorageTests(SimpleTestCase):
    def test_default_storage_round_trip_uses_private_object_and_application_url(self):
        name = "employee/documents/My Contract.pdf"
        key = "uploads/" + name
        data = b"%PDF test document"
        location = {"Bucket": "klockin-test", "Key": key}
        client = default_storage.connection.meta.client
        with Stubber(client) as stub:
            stub.add_client_error("head_object", "404", http_status_code=404, expected_params=location)
            stub.add_response("put_object", {}, {
                **location,
                "ContentLength": len(data),
                "IfNoneMatch": "*",
                "ContentType": "application/pdf",
                "Body": ANY,
            })
            stub.add_response("get_object", {
                "Body": StreamingBody(BytesIO(data), len(data)),
                "ContentLength": len(data),
            }, location)
            self.assertEqual(default_storage.save(name, ContentFile(data)), name)
            self.assertEqual(default_storage.url(name), "/media/employee/documents/My%20Contract.pdf")
            with default_storage.open(name, "rb") as source:
                self.assertEqual(source.read(), data)
            stub.assert_no_pending_responses()

    def test_internal_filenames_cannot_be_read_or_linked(self):
        for name in (".generated_secret_key", "x/../profile.png", "x//profile.png", "x\\profile.png"):
            with self.subTest(name=name):
                with self.assertRaises(SuspiciousFileOperation):
                    default_storage.url(name)
                with self.assertRaises(SuspiciousFileOperation):
                    default_storage.open(name, "rb")

    def test_absent_key_does_not_mask_provider_failure(self):
        location = {"Bucket": "klockin-test", "Key": "uploads/missing.png"}
        with Stubber(default_storage.connection.meta.client) as stub:
            stub.add_client_error("get_object", "NoSuchKey", http_status_code=404, expected_params=location)
            stub.add_client_error("get_object", "AccessDenied", http_status_code=403, expected_params=location)
            with self.assertRaises(FileNotFoundError):
                default_storage.open("missing.png", "rb")
            with self.assertRaises(OSError) as unavailable:
                default_storage.open("missing.png", "rb")
            self.assertNotIsInstance(unavailable.exception, FileNotFoundError)
