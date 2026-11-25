from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from base.media_access import user_can_access_media


class RootMediaAccessTests(SimpleTestCase):
    def test_owned_root_upload_uses_record_access_rules(self):
        user = SimpleNamespace(is_superuser=False)
        holder = object()
        with (
            patch("base.media_access.is_model_media", return_value=False),
            patch("base.media_access.find_holders", return_value=[holder]) as find,
            patch("base.media_access.user_can_access_holder", return_value=False)
            as can_access,
        ):
            self.assertFalse(user_can_access_media(user, "enrollment.jpg"))
            find.assert_called_once_with("enrollment.jpg")
            can_access.assert_called_once_with(user, holder)
            can_access.return_value = True
            self.assertTrue(user_can_access_media(user, "enrollment.jpg"))

    def test_unowned_root_upload_retains_authenticated_access(self):
        user = SimpleNamespace(is_superuser=False)
        with (
            patch("base.media_access.is_model_media", return_value=False),
            patch("base.media_access.find_holders", return_value=[]),
        ):
            self.assertTrue(user_can_access_media(user, "legacy.pdf"))
