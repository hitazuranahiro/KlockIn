from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from klockin.export_preferences import get_export_preferences, resolve_export_options
from klockin.testkit import make_company, make_employee, make_user


class ExportPreferencesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Document preference test")
        cls.user = make_user("document-preferences")
        cls.other = make_user("document-preferences-other")
        for user in (cls.user, cls.other):
            make_employee(company=company, email=user.email, user=user)

    def test_preferences_are_account_scoped_and_partial_updates_keep_other_options(self):
        url = reverse("api-mobile-export-preferences")
        api = APIClient()
        self.assertIn(api.get(url).status_code, (401, 403))
        api.force_authenticate(self.user)
        self.assertEqual(api.get(url).data["payslip"]["template"], "detailed")
        response = api.patch(
            url, {"payslip": {"template": "compact", "note": "Payroll reference"}}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        response = api.patch(url, {"dtr": {"show_undertime": False}}, format="json")
        self.assertEqual(response.data["payslip"]["template"], "compact")
        self.assertFalse(response.data["dtr"]["show_undertime"])
        self.assertIn("no-store", response["Cache-Control"])
        api.force_authenticate(self.other)
        self.assertEqual(api.get(url).data["payslip"]["template"], "detailed")

    def test_rejects_unknown_or_invalid_options_without_partial_changes(self):
        api = APIClient()
        api.force_authenticate(self.user)
        url = reverse("api-mobile-export-preferences")
        for options in (
            {"payslip": {"template": "landscape", "gross_pay": 100000}},
            {"payslip": {"template": ["landscape"]}},
            {"payslip": {"note": "x" * 161}},
            {"dtr": {"show_undertime": "invalid"}},
        ):
            self.assertEqual(api.patch(url, options, format="json").status_code, 400)
        self.assertEqual(get_export_preferences(self.user)["payslip"]["template"], "detailed")

    def test_web_save_is_available_in_api_and_note_stays_out_of_pdf_query(self):
        self.client.force_login(self.user)
        url = reverse("save-export-preferences", args=["dtr", 19])
        response = self.client.post(
            url, {"month": "2026-11", "orientation": "landscape", "note": "Private export note"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("configure=1", response["Location"])
        self.assertNotIn("Private", response["Location"])
        settings = resolve_export_options(
            self.user, "dtr", QueryDict("layout=ampm&show_company=0&note=Ignored")
        )
        self.assertEqual(settings["layout"], "am-pm")
        self.assertEqual(settings["orientation"], "landscape")
        self.assertFalse(settings["show_company"])
        self.assertEqual(settings["note"], "Private export note")
