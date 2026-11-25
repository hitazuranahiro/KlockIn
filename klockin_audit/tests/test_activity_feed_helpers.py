"""Audit activity-feed helper smoke tests."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

from django.templatetags.static import static
from django.test import SimpleTestCase
from django.utils.translation import gettext as _

from klockin_audit.activity_feed import (
    history_action_phrase,
    history_date_label,
    normalize_log_entries,
    normalize_tracking_entries,
)


class HistoryActionPhraseTests(SimpleTestCase):
    def test_empty_changes(self):
        self.assertEqual(history_action_phrase([]), _("updated record"))

    def test_single_field(self):
        phrase = history_action_phrase([{"field_label": "Department"}])
        self.assertIn("department", phrase.lower())


class HistoryDateLabelTests(SimpleTestCase):
    def test_today_and_yesterday(self):
        today = date(2026, 8, 7)
        self.assertEqual(
            history_date_label(datetime(2026, 8, 7, 12, 0), today=today),
            _("Today"),
        )
        self.assertEqual(
            history_date_label(datetime(2026, 8, 6, 12, 0), today=today),
            _("Yesterday"),
        )


class SystemAuditActorTests(SimpleTestCase):
    def test_existing_system_account_uses_klockin_display(self):
        system_account = SimpleNamespace(
            username="Horilla Bot",
            employee_get=SimpleNamespace(get_full_name=lambda: "Horilla Bot"),
        )
        entry = SimpleNamespace(actor=system_account, action=0)
        item = normalize_log_entries([entry])[0]

        self.assertEqual(item["actor_name"], "KlockIN Bot")
        self.assertEqual(item["actor_avatar"], static("klockin/mark.png"))
        self.assertEqual(system_account.username, "Horilla Bot")

    def test_automated_tracking_entry_uses_same_origin_mark(self):
        entries = normalize_tracking_entries(
            [{"type": "Scheduled update", "updated_by": None}]
        )

        self.assertEqual(entries[0]["actor_name"], "KlockIN Bot")
        self.assertEqual(entries[0]["actor_avatar"], static("klockin/mark.png"))
