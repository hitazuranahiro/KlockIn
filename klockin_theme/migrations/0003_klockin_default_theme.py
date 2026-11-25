from django.db import migrations


# Match the full stock palette so existing customizations keep their settings.
ORIGINAL_PALETTE = {
    "name": "Coral Red Theme (Default)",
    "description": "Warm coral-red based theme",
    "primary_50": "#f6f6f6",
    "primary_100": "#FFF5F1",
    "primary_200": "#FEF6F5",
    "primary_300": "#FCEDEB",
    "primary_400": "#FBE5E1",
    "primary_500": "#F7C8C1",
    "primary_600": "#E54F38",
    "primary_700": "#ce4732",
    "primary_800": "#AC3B2A",
    "primary_900": "#672419",
    "dark_50": "#E6E6E6",
    "dark_100": "#A8A8A8",
    "dark_200": "#515151",
    "dark_300": "#501C14",
    "dark_400": "#64748B",
    "dark_500": "#190906",
    "dark_600": "#000000",
    "secondary_50": "#f8fafc",
    "secondary_100": "#f1f5f9",
    "secondary_200": "#e2e8f0",
    "secondary_300": "#cbd5e1",
    "secondary_400": "#FBE5E1",
    "secondary_500": "#F7C8C1",
    "secondary_600": "#E54F38",
    "secondary_700": "#334155",
    "secondary_800": "#1e293b",
    "secondary_900": "#0f172a",
}
KLOCKIN_PALETTE = {
    **ORIGINAL_PALETTE,
    "name": "KlockIN Blue (Default)",
    "description": "KlockIN corporate blue and neutral tones",
    "primary_50": "#F8FAFD",
    "primary_100": "#EFF6FF",
    "primary_200": "#E7F0FC",
    "primary_300": "#D6E7FD",
    "primary_400": "#B7D3F8",
    "primary_500": "#8CB8F2",
    "primary_600": "#0056D6",
    "primary_700": "#0047B4",
    "primary_800": "#003B91",
    "primary_900": "#142D54",
    "dark_300": "#24344F",
    "dark_500": "#141D2D",
    "secondary_400": "#B7D3F8",
    "secondary_500": "#8CB8F2",
    "secondary_600": "#0056D6",
}


def apply_palette(apps, schema_editor, old_palette, new_palette):
    themes = apps.get_model("horilla_theme", "HorillaColorTheme").objects.using(
        schema_editor.connection.alias
    )
    themes.filter(**old_palette).update(**new_palette)


def use_klockin_palette(apps, schema_editor):
    apply_palette(apps, schema_editor, ORIGINAL_PALETTE, KLOCKIN_PALETTE)


def restore_original_palette(apps, schema_editor):
    apply_palette(apps, schema_editor, KLOCKIN_PALETTE, ORIGINAL_PALETTE)


class Migration(migrations.Migration):
    dependencies = [("horilla_theme", "0002_alter_companytheme_is_active_and_more")]
    operations = [migrations.RunPython(use_klockin_palette, restore_original_palette)]
