from django.template import engines
from django.test import SimpleTestCase

from .paths import template_names


class TemplatePathCompatibilityTests(SimpleTestCase):
    def test_current_and_older_paths_resolve_in_the_same_order(self):
        paths = (
            "klockin_widgets/klockin_attr.html",
            "klockin_widgets/horilla_attr.html",
            "horilla_widgets/horilla_attr.html",
        )
        for name in paths:
            with self.subTest(name=name):
                self.assertEqual(template_names(name), paths)

    def test_renamed_file_with_unchanged_directory(self):
        self.assertEqual(
            template_names("generic/horilla_list.html"),
            ("generic/klockin_list.html", "generic/horilla_list.html"),
        )

    def test_saved_template_can_load_previous_tag_library(self):
        engine = engines["django"]
        template = engine.from_string("{% load horillafilters %}KlockIN")
        self.assertEqual(template.render(), "KlockIN")
