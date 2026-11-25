import json
import logging
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.db import DatabaseError

from .models import AttendancePunch


logger = logging.getLogger(__name__)
LOOKUP_TIMEOUT_SECONDS = 1.5
MAX_RESPONSE_BYTES = 64 * 1024


def _lookup_address(endpoint, punch):
    url = urlsplit(endpoint)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.hostname.rstrip(".") == "nominatim.openstreetmap.org"
    ):
        raise ValueError("Configure a private HTTPS reverse geocoding endpoint.")

    params = {
        "lat": f"{punch.gps_lat:.5f}",
        "lon": f"{punch.gps_long:.5f}",
        "format": "jsonv2",
    }
    with requests.Session() as session:
        session.trust_env = False
        with session.get(
            endpoint,
            params=params,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "KlockIN attendance",
            },
            timeout=LOOKUP_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                return ""
            payload = bytearray()
            for chunk in response.iter_content(chunk_size=4096):
                payload.extend(chunk)
                if len(payload) > MAX_RESPONSE_BYTES:
                    return ""

    data = json.loads(payload)
    address = data.get("display_name", "") if isinstance(data, dict) else ""
    if not isinstance(address, str):
        return ""
    max_length = AttendancePunch._meta.get_field("detected_address").max_length
    return " ".join(address.split())[:max_length].rstrip()


def resolve_punch_address(punch):
    """Cache an optional address after the evidence transaction has committed."""
    endpoint = settings.KLOCKIN_REVERSE_GEOCODER_URL
    if not endpoint or punch.detected_address:
        return

    try:
        address = _lookup_address(endpoint, punch)
        if address and AttendancePunch.objects.filter(pk=punch.pk, detected_address="").update(
            detected_address=address
        ):
            punch.detected_address = address
    except (requests.RequestException, ValueError, RecursionError, DatabaseError):
        logger.warning("KlockIN could not resolve or cache a punch address.")
