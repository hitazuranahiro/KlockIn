"""
klockin/inherit/

Extension infrastructure for Horilla — model field injection and CBV replacement.

Key public symbols re-exported here for convenience:

    from klockin.inherit import HorillaViewInheritMixin   # view extension
    from klockin.inherit import HorillaModelBase           # model metaclass
    from klockin.inherit import INJECTION_MAP              # migration routing
    from klockin.inherit import VIEW_REGISTRY              # registered views
"""

from klockin.inherit.extension_registry import INJECTION_MAP
from klockin.inherit.model_inherit import EXTENSION_REGISTRY, HorillaModelBase
from klockin.inherit.view_inherit import HorillaViewInheritMixin
from klockin.inherit.view_registry import VIEW_REGISTRY

__all__ = [
    "HorillaViewInheritMixin",
    "HorillaModelBase",
    "INJECTION_MAP",
    "EXTENSION_REGISTRY",
    "VIEW_REGISTRY",
]
