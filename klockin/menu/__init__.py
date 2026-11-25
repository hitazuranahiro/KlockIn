"""
klockin.menu — public API for all menu registries.

App menu.py files import from here::

    from klockin.menu import settings_menu

Then use the registry as a decorator::

    @settings_menu.register
    class MyAppSettings:
        ...
"""

from klockin.menu.settings_menu import get_settings_menu
from klockin.menu.settings_menu import settings_registry as settings_menu

__all__ = [
    "settings_menu",
    "get_settings_menu",
]
