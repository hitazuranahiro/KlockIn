"""Canonical and previous identities for optional demo fixtures."""

DEMO_EMAIL_DOMAIN = "demo.klockin.invalid"
LEGACY_DEMO_EMAIL_DOMAIN = "horilla.com"


def legacy_demo_email(email):
    """Return the address used by inherited fixtures for the same persona."""
    local_part, _, _ = email.partition("@")
    return f"{local_part}@{LEGACY_DEMO_EMAIL_DOMAIN}"
