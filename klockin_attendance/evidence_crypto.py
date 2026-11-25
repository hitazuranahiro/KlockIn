"""Versioned authenticated encryption for stored punch evidence."""

from decimal import Decimal

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

ENC_PREFIX = b"KLOCKIN-EVIDENCE-V1\0"
TEXT_PREFIX = "klockin:v1:"
TEXT_ESCAPE = "klockin:clear:"
MAX_STORED_SELFIE_BYTES = 3 * 1024 * 1024


def evidence_cipher(*, required=False):
    keys = settings.KLOCKIN_EVIDENCE_KEYS
    if not keys:
        if required or settings.KLOCKIN_REQUIRE_EVIDENCE_ENCRYPTION:
            raise ImproperlyConfigured("Set at least one KLOCKIN_EVIDENCE_KEYS entry.")
        return None
    try:
        return MultiFernet([Fernet(key) for key in keys])
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured("Each KLOCKIN_EVIDENCE_KEYS entry must be a Fernet key.") from exc


def seal(value, purpose, *, required=False):
    cipher = evidence_cipher(required=required)
    return cipher.encrypt(purpose + b"\0" + value) if cipher else None


def unseal(value, purpose):
    content = evidence_cipher(required=True).decrypt(value)
    label, marker, data = content.partition(b"\0")
    if not marker or label != purpose:
        raise InvalidToken
    return data


def protect_selfie(value, *, required=False):
    token = seal(value, b"photo", required=required)
    return ENC_PREFIX + token if token else value


def reveal_selfie(value):
    if value.startswith(ENC_PREFIX):
        return unseal(value[len(ENC_PREFIX):], b"photo")
    return value


class EncryptedEvidenceTextField(models.TextField):
    """Read legacy clear text and encrypt populated values on write."""

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        token = seal(value.encode(), self.name.encode())
        if not token and value.startswith((TEXT_PREFIX, TEXT_ESCAPE)):
            return TEXT_ESCAPE + value
        return TEXT_PREFIX + token.decode("ascii") if token else value

    def from_db_value(self, value, expression, connection):
        if value and value.startswith(TEXT_PREFIX):
            value = unseal(value[len(TEXT_PREFIX):].encode("ascii"), self.name.encode()).decode()
        elif value and value.startswith(TEXT_ESCAPE):
            value = value[len(TEXT_ESCAPE):]
        return self.to_python(value)


class EncryptedEvidenceDecimalField(EncryptedEvidenceTextField):
    def to_python(self, value):
        return Decimal(value) if value is not None else None

    def get_prep_value(self, value):
        # The decimal is a Python value for projections and templates, but the
        # underlying database column stores a text envelope.
        if value is None:
            return None
        value = format(Decimal(value), "f")
        token = seal(value.encode(), self.name.encode())
        return TEXT_PREFIX + token.decode("ascii") if token else value
