"""
Configuration for the database template application.

Reads from Django settings with KLOCKIN_DBTEMPLATE_* prefix.
Django 6.x compatible.
"""

from django.conf import settings


def get_setting(name, default=None):
    """Get a setting with KLOCKIN_DBTEMPLATE_ prefix."""
    primary = f"KLOCKIN_DBTEMPLATE_{name}"
    if hasattr(settings, primary):
        return getattr(settings, primary)
    return getattr(settings, f"HORILLA_DBTEMPLATE_{name}", default)


# Cache backend name from CACHES (e.g. "default" or "klockin_dbtemplate")
CACHE_BACKEND = get_setting("CACHE_BACKEND", "default")

# Whether to auto-populate content from filesystem/app loaders when content is empty
AUTO_POPULATE_CONTENT = get_setting("AUTO_POPULATE_CONTENT", False)


def get_cache():
    """Return the cache backend instance, or None if caching is disabled."""
    if not hasattr(settings, "CACHES") or CACHE_BACKEND not in settings.CACHES:
        return None
    try:
        from django.core.cache import caches

        cache = caches[CACHE_BACKEND]
        return cache
    except Exception:
        return None
