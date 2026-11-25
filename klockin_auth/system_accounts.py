from django.db.models import Case, When

SYSTEM_BOT_USERNAME = "KlockIN Bot"
_LEGACY_SYSTEM_BOT_USERNAME = "Horilla Bot"
_SYSTEM_BOT_USERNAMES = (SYSTEM_BOT_USERNAME, _LEGACY_SYSTEM_BOT_USERNAME)


def is_system_bot(user):
    return getattr(user, "username", None) in _SYSTEM_BOT_USERNAMES


def get_system_bot():
    from .models import HorillaUser

    # Keep existing installations working when their original account is the
    # only system actor, and prefer the current account on fresh installations.
    return (
        HorillaUser.objects.filter(username__in=_SYSTEM_BOT_USERNAMES)
        .order_by(Case(When(username=SYSTEM_BOT_USERNAME, then=0), default=1))
        .first()
    )
