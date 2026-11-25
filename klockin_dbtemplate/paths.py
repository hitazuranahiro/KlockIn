"""Resolve template names saved before source directory renames."""

_PREFIXES = (
    ("klockin_audit/", "horilla_audit/"),
    ("klockin_automations/", "horilla_automations/"),
    ("admin/klockin_dbtemplate/", "admin/horilla_dbtemplate/"),
    ("klockin_theme/", "horilla_theme/"),
    ("klockin_tours/", "horilla_tour/"),
    ("klockin_widgets/", "horilla_widgets/"),
)

_RENAMED_BASENAMES = frozenset(
    {
        "attr.html",
        "audit_log.html",
        "card.html",
        "clearable_file_input.html",
        "company.html",
        "department.html",
        "department_form.html",
        "detailed_view.html",
        "form.html",
        "history_view.html",
        "job_position.html",
        "job_position_form.html",
        "kanban_view.html",
        "list.html",
        "list_table.html",
        "multiselect_widget.html",
        "nav.html",
        "profile_view.html",
        "section.html",
        "select_option.html",
        "tab_content_shell.html",
        "tabs.html",
        "user.html",
        "user_signup.html",
    }
)


def template_names(name):
    """Return the current path and earlier paths for stored template overrides."""
    basename = name.rsplit("/", 1)[-1]
    prefix, _, stem = basename.partition("_")
    if prefix not in ("klockin", "horilla") or stem not in _RENAMED_BASENAMES:
        return _directory_names(name)

    current, *previous = _directory_names(name.removesuffix(basename))
    return (
        f"{current}klockin_{stem}",
        f"{current}horilla_{stem}",
        *(f"{directory}horilla_{stem}" for directory in previous),
    )


def _directory_names(name):
    for current, previous in _PREFIXES:
        if name.startswith(current):
            return name, previous + name[len(current) :]
        if name.startswith(previous):
            return current + name[len(previous) :], name
    return (name,)
