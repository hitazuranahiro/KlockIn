from hashlib import sha256
from pathlib import Path

from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.test import SimpleTestCase


class VersionedAssetsTests(SimpleTestCase):
    def test_punch_bundle_uses_content_versions(self):
        template = Template("{% load versioned_assets %}{% versioned_static path %}")
        for asset in ("klockin/web-punch.js", "klockin/web-punch.css"):
            with self.subTest(asset=asset):
                version = sha256(Path(finders.find(asset)).read_bytes()).hexdigest()[:16]
                url = template.render(Context({"path": asset}))
                self.assertTrue(url.endswith(f"/{asset}?v={version}"), url)
