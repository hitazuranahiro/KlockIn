"""Storage-aware image access for server-rendered reports and mail."""

from base64 import b64encode
from mimetypes import guess_type
from urllib.parse import unquote

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage


def read_uploaded_image(upload):
    if not upload:
        return None
    name, storage = (upload, default_storage) if isinstance(upload, str) else (
        upload.name, upload.storage
    )
    try:
        with storage.open(name, "rb") as image:
            return name, image.read()
    except (OSError, SuspiciousFileOperation):
        return None


def uploaded_image_source(upload):
    image = read_uploaded_image(upload)
    if image is None:
        return None
    name, content = image
    content_type, _ = guess_type(name)
    if not content_type or not content_type.startswith("image/"):
        return None
    return f"data:{content_type};base64,{b64encode(content).decode('ascii')}"


def uploaded_image_url_source(uri):
    if settings.MEDIA_URL and uri.startswith(settings.MEDIA_URL):
        return uploaded_image_source(unquote(uri[len(settings.MEDIA_URL):]))
    return None
