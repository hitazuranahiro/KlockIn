"""Use asset contents to invalidate cached copies of interactive UI bundles."""

from functools import lru_cache
from hashlib import file_digest

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


def _asset_version(name):
    path = finders.find(name)
    if not path:
        return ""
    with open(path, "rb") as asset:
        return file_digest(asset, "sha256").hexdigest()[:16]


_production_version = lru_cache(maxsize=16)(_asset_version)


@register.simple_tag
def versioned_static(name):
    url = static(name)
    version = (_asset_version if settings.DEBUG else _production_version)(name)
    return f"{url}?v={version}" if version else url
