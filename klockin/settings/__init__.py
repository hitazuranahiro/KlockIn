"""
klockin/settings/__init__.py
Combines official base settings + client overrides.
"""

from .base import *
from .compat import apply_legacy_aliases as _apply_legacy_aliases

# Import client overrides (if file exists)
_client_settings = None
try:
    from .addons import *
    from . import local_settings as _client_settings
    from .local_settings import *
except ImportError:
    pass

_apply_legacy_aliases(globals(), _client_settings)
