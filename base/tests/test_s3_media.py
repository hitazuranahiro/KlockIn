from base64 import b64decode
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
from django.core.files.base import ContentFile
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings

from base.forms import PassWordResetForm
from base.views import protected_media


@override_settings(KLOCKIN_UPLOAD_STORAGE="s3")
class S3MediaDeliveryTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/media/")
        self.request.user = SimpleNamespace(is_authenticated=True)
        backend = patch("base.views.default_storage")
        authorization = patch("base.views.user_can_access_media", return_value=True)
        self.backend = backend.start()
        self.authorization = authorization.start()
        self.addCleanup(backend.stop)
        self.addCleanup(authorization.stop)

    def test_authorized_file_uses_storage_and_keeps_content_protections(self):
        path = "employee/document/report.svg"
        self.backend.open.return_value = ContentFile(b"<svg/>", name=path)

        response = protected_media(self.request, path)
        self.addCleanup(response.close)

        self.authorization.assert_called_once_with(self.request.user, path)
        self.backend.open.assert_called_once_with(path, "rb")
        self.assertEqual(b"".join(response.streaming_content), b"<svg/>")
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="report.svg"')
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_denial_does_not_read_storage(self):
        self.authorization.return_value = False
        with self.assertRaises(Http404):
            protected_media(self.request, "employee/document/private.pdf")
        self.backend.open.assert_not_called()

    def test_noncanonical_hidden_and_server_only_names_are_rejected(self):
        paths = (
            "base/icon/../secret.png",
            "base/icon/a\\..\\secret.png",
            "base/icon//a.png",
            ".hidden/a.png",
            "gdrive_oauth_credentials_file/config.json",
            "gdrive_service_account_file/config.json",
        )
        for path in paths:
            with self.subTest(path=path), self.assertRaises(Http404):
                protected_media(self.request, path)

        self.authorization.assert_not_called()
        self.backend.open.assert_not_called()

    def test_public_icon_is_served_from_storage_without_an_account(self):
        path = "base/icon/brand.png"
        self.request.user = AnonymousUser()
        self.backend.open.return_value = ContentFile(b"icon", name=path)

        response = protected_media(self.request, path)
        self.addCleanup(response.close)

        self.authorization.assert_not_called()
        self.backend.open.assert_called_once_with(path, "rb")
        self.assertEqual(b"".join(response.streaming_content), b"icon")
        self.assertEqual(response["Content-Type"], "image/png")

    def test_missing_object_and_storage_outage_are_distinguished(self):
        path = "employee/document/report.pdf"
        self.backend.open.side_effect = FileNotFoundError
        with self.assertRaises(Http404):
            protected_media(self.request, path)

        self.backend.open.side_effect = OSError
        with self.assertLogs("base.views", level="ERROR"):
            self.assertEqual(protected_media(self.request, path).status_code, 503)


@override_settings(WHITE_LABELLING=True)
class StorageLogoTests(SimpleTestCase):
    def test_password_reset_attaches_hq_logo_from_storage(self):
        png = b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8"
            "AAwMCAO+aM80AAAAASUVORK5CYII="
        )
        name = "base/company/icon/brand.png"
        storage = Mock()
        storage.open.return_value = ContentFile(png, name=name)
        company = SimpleNamespace(
            company="HQ", icon=SimpleNamespace(name=name, storage=storage)
        )

        form = PassWordResetForm()
        with patch("base.forms.Company.objects.filter") as companies:
            companies.return_value.last.return_value = company
            company_name, logo_source = form.get_branding(None)

        with (
            patch("base.forms.EmailMultiAlternatives") as email,
            patch("base.forms.loader.render_to_string", return_value="Reset"),
        ):
            form.send_mail(
                "subject", "body", {"logo_path": logo_source},
                "staff@example.test", "employee@example.test", "html",
            )

        storage.open.assert_called_once_with(name, "rb")
        self.assertEqual(company_name, "HQ")
        email.return_value.send.assert_called_once()
        attachment = email.return_value.attach.call_args.args[0]
        self.assertEqual(attachment["Content-ID"], "<company_logo>")
        self.assertEqual(attachment.get_filename(), "brand.png")
        self.assertEqual(attachment.get_payload(decode=True), png)
