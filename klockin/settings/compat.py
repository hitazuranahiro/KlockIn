"""Fallbacks for deployments that still use the upstream setting names."""

import os


_RENAMED_SETTINGS = (
    "ENV",
    "FIRST_DAY_OF_WEEK",
    "REQUIRE_SCHEDULER",
    "SCHEDULER_HISTORY_DAYS",
    "ALLOW_PYTHON_TAX_FORMULAS",
    "TRUSTED_PROXIES",
    "DATE_FORMATS",
    "TIME_FORMATS",
)


def environment_key(name):
    """Prefer an explicitly supplied KlockIN variable, including an empty value."""
    primary = f"KLOCKIN_{name}"
    legacy = f"HORILLA_{name}"
    return primary if primary in os.environ or legacy not in os.environ else legacy


def apply_legacy_aliases(namespace, overrides=None):
    """Expose both setting spellings and accept older local Python overrides."""
    provided = vars(overrides) if overrides is not None else {}
    for name in _RENAMED_SETTINGS:
        primary = f"KLOCKIN_{name}"
        legacy = f"HORILLA_{name}"
        if primary in provided:
            namespace[primary] = provided[primary]
        elif legacy in provided:
            namespace[primary] = provided[legacy]
        namespace[legacy] = namespace[primary]
