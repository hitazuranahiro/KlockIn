"""Resolve template names saved before source directory renames."""

_PREFIXES = (
    ("klockin_audit/", "horilla_audit/"),
    ("klockin_automations/", "horilla_automations/"),
    ("admin/klockin_dbtemplate/", "admin/horilla_dbtemplate/"),
    ("klockin_theme/", "horilla_theme/"),
    ("klockin_tours/", "horilla_tour/"),
    ("klockin_widgets/", "horilla_widgets/"),
)


def template_names(name):
    """Return the current name followed by its previous name, when applicable."""
    for current, previous in _PREFIXES:
        if name.startswith(current):
            return name, previous + name[len(current):]
        if name.startswith(previous):
            return current + name[len(previous):], name
    return (name,)
