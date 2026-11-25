from klockin.settings import TEMPLATES

TEMPLATES[0]["OPTIONS"]["context_processors"].append(
    "klockin_crumbs.context_processors.breadcrumbs",
)
