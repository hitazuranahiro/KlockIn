"""Render server documents using the bundled PDF engine and application assets."""

import logging
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.utils.http import content_disposition_header
from django.utils.translation import gettext as _
from xhtml2pdf import pisa

from klockin.uploaded_files import uploaded_image_url_source

logger = logging.getLogger(__name__)
_raster_prefixes = ("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/gif;base64,")


def _document_asset(uri, _relative_to, *, host):
    blocked = str(Path(settings.BASE_DIR) / ".missing-pdf-asset")
    if not uri:
        return blocked
    uri = str(uri)
    if uri.startswith(_raster_prefixes) and len(uri) <= 8 * 1024 * 1024:
        return uri
    try:
        parts = urlsplit(uri)
    except ValueError:
        return blocked
    if parts.scheme or parts.netloc:
        if parts.scheme not in ("http", "https") or not host or parts.netloc != host:
            return blocked
    path = unquote(parts.path)
    if not path.startswith("/") or "\\" in path or "\0" in path or ".." in path.split("/"):
        return blocked

    if settings.STATIC_URL and path.startswith(settings.STATIC_URL):
        name = path.removeprefix(settings.STATIC_URL)
        found = finders.find(name)
        if found:
            return str(found)
        root = Path(settings.STATIC_ROOT).resolve()
        candidate = (root / name).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return str(candidate)
    if settings.MEDIA_URL and path.startswith(settings.MEDIA_URL):
        source = uploaded_image_url_source(path)
        if source and source.startswith(_raster_prefixes) and len(source) <= 8 * 1024 * 1024:
            return source
    return blocked


def document_pdf(markup, filename, *, host=None):
    """Generate an inline PDF without passing browser credentials to a renderer."""
    output = BytesIO()
    try:
        result = pisa.CreatePDF(
            markup,
            dest=output,
            encoding="utf-8",
            link_callback=lambda uri, relative: _document_asset(uri, relative, host=host),
        )
    except Exception:
        logger.exception("Could not render a document PDF.")
        result = None
    contents = output.getvalue()
    if result is None or result.err or not contents.startswith(b"%PDF-"):
        return HttpResponse(_("This PDF could not be generated. Please try again."), status=500)
    response = HttpResponse(contents, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(False, filename)
    response["Cache-Control"] = "private, no-store"
    return response
