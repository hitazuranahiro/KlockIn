"""Stable model paths for settings that store Python identifiers in the database."""


def model_paths(model):
    """Return the stored identity first, followed by any current package path."""
    module = model.__module__
    path = f"{module}.{model.__name__}"
    app = model._meta.app_config
    if app and app.label.startswith("horilla_"):
        prefix = f"{app.name}."
        if app.name != app.label and module.startswith(prefix):
            return (f"{app.label}.{path[len(prefix):]}", path)
    return (path,)
