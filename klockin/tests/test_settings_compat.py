import os
from types import SimpleNamespace
from unittest.mock import patch

import environ
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from klockin.settings.compat import apply_legacy_aliases, environment_key
from klockin_dbtemplate.conf import get_setting


class SettingNamesTests(SimpleTestCase):
    def test_legacy_environment_is_used_only_without_a_new_name(self):
        with patch.dict(os.environ, {"HORILLA_REQUIRE_SCHEDULER": "1"}, clear=True):
            env = environ.Env()
            self.assertTrue(env.bool(environment_key("REQUIRE_SCHEDULER")))
            with patch.dict(os.environ, {"KLOCKIN_REQUIRE_SCHEDULER": "0"}):
                self.assertFalse(env.bool(environment_key("REQUIRE_SCHEDULER")))
            with patch.dict(os.environ, {"KLOCKIN_REQUIRE_SCHEDULER": ""}):
                self.assertEqual(
                    environment_key("REQUIRE_SCHEDULER"), "KLOCKIN_REQUIRE_SCHEDULER"
                )

    def test_local_python_setting_aliases_support_both_names(self):
        namespace = {
            name: getattr(settings, name)
            for name in (
                "KLOCKIN_ENV",
                "KLOCKIN_FIRST_DAY_OF_WEEK",
                "KLOCKIN_REQUIRE_SCHEDULER",
                "KLOCKIN_SCHEDULER_HISTORY_DAYS",
                "KLOCKIN_ALLOW_PYTHON_TAX_FORMULAS",
                "KLOCKIN_TRUSTED_PROXIES",
                "KLOCKIN_DATE_FORMATS",
                "KLOCKIN_TIME_FORMATS",
            )
        }
        apply_legacy_aliases(namespace, SimpleNamespace(HORILLA_FIRST_DAY_OF_WEEK="0"))
        self.assertEqual(namespace["KLOCKIN_FIRST_DAY_OF_WEEK"], "0")
        apply_legacy_aliases(
            namespace,
            SimpleNamespace(
                HORILLA_FIRST_DAY_OF_WEEK="0", KLOCKIN_FIRST_DAY_OF_WEEK="6"
            ),
        )
        self.assertEqual(namespace["HORILLA_FIRST_DAY_OF_WEEK"], "6")

    @override_settings(HORILLA_DBTEMPLATE_AUTO_POPULATE_CONTENT=True)
    def test_database_template_setting_uses_legacy_value_when_needed(self):
        self.assertTrue(get_setting("AUTO_POPULATE_CONTENT"))
        with override_settings(KLOCKIN_DBTEMPLATE_AUTO_POPULATE_CONTENT=False):
            self.assertFalse(get_setting("AUTO_POPULATE_CONTENT"))
