from datetime import date

import pymupdf
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from employee.models import EmployeeBankDetails
from klockin.export_preferences import get_export_preferences, save_export_preferences
from klockin.testkit import make_company, make_employee, make_user
from payroll.models.models import Payslip
from payroll.views.views import payslip_attachment_pdf


class PayslipPDFLayoutsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Synthetic Payroll Company")
        cls.user = make_user("pdf-layout-owner")
        employee = make_employee(
            company=cls.company, user=cls.user, email=cls.user.email,
            first_name="Alma", last_name="SyntheticWorker",
        )
        EmployeeBankDetails.objects.create(
            employee_id=employee, bank_name="Synthetic Bank", account_number="QA-001",
        )
        cls.payslip = Payslip.objects.create(
            employee_id=employee,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            status="paid",
            pay_head_data={
                "basic_pay": 15000,
                "gross_pay": 15700,
                "total_deductions": 900,
                "net_pay": 14800,
                "contract_wage": 255,
                "regular_hours_label": "160 h",
                "ot_hours_label": "4 h",
                "paid_days": 30,
                "allowances": [{"title": "Transport Allowance", "amount": 700}],
                "pretax_deductions": [{"title": "Pension Contribution", "amount": 350}],
                "post_tax_deductions": [{"title": "Sample Loan Deduction", "amount": 100}],
                "federal_tax": 450,
                "loss_of_pay": 0,
            },
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.pdf_url = reverse("payslip-pdf", kwargs={"id": self.payslip.pk})
        self.html_url = reverse("view-payslip-pdf", kwargs={"payslip_id": self.payslip.pk})
        self.api_url = f"/api/v1/payroll/payslip-download/{self.payslip.pk}"

    def _read_pdf(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        with pymupdf.open(stream=response.content, filetype="pdf") as document:
            text = " ".join(" ".join(page.get_text().split()) for page in document)
            sizes = [tuple(page.rect)[2:] for page in document]
        return text, sizes

    def test_default_and_all_presets_keep_the_same_payroll_rows(self):
        for preset in (None, "detailed", "landscape", "compact"):
            with self.subTest(preset=preset):
                response = self.client.get(self.pdf_url, {"template": preset} if preset else {})
                text, sizes = self._read_pdf(response)
                self.assertTrue(response.headers["Content-Disposition"].startswith("inline;"))
                for width, height in sizes:
                    self.assertAlmostEqual(width, 842 if preset == "landscape" else 595, delta=1)
                    self.assertAlmostEqual(height, 595 if preset == "landscape" else 842, delta=1)
                for value in (
                    "March 01, 2026 to March 31, 2026", "Paid", "30 of 31",
                    "Alma SyntheticWorker", "Synthetic Payroll Company", "Synthetic Bank", "QA-001",
                    "Regular hours:", "160 h", "4 h", "Transport Allowance", "Pension Contribution",
                    "Sample Loan Deduction", "Income Tax", "15700.00", "14800.00",
                ):
                    self.assertIn(value, text)

    def test_company_notes_toggles_and_preview_download_modes(self):
        save_export_preferences(self.user, {"payslip": {"note": "Optional reconciliation note."}})
        response = self.client.get(self.pdf_url, {
            "template": "compact", "show_company": "0", "show_notes": "0",
            "download": "1",
        })
        text, _ = self._read_pdf(response)
        self.assertTrue(response.headers["Content-Disposition"].startswith("attachment;"))
        self.assertNotIn("Synthetic Payroll Company", text)
        self.assertNotIn("Optional reconciliation note.", text)
        self.assertIn("Pay period", text)
        self.assertIn("Pension Contribution", text)
        self.assertIn("QA-001", text)

        response = self.client.get(self.html_url, {
            "preview": "1", "download": "1", "note": "Untrusted URL note",
        })
        text, _ = self._read_pdf(response)
        self.assertTrue(response.headers["Content-Disposition"].startswith("inline;"))
        self.assertIn("Optional reconciliation note.", text)
        self.assertNotIn("Untrusted URL note", text)
        save_export_preferences(self.user, {"payslip": {"note": "<script>do not render</script>"}})
        html = self.client.get(self.html_url)
        self.assertTrue(html.headers["Content-Type"].startswith("text/html"))
        self.assertContains(html, "&lt;script&gt;do not render&lt;/script&gt;")
        self.assertNotContains(html, "<script>do not render</script>")

    def test_saved_preferences_apply_and_one_off_override_does_not_persist(self):
        save_export_preferences(self.user, {"payslip": {"template": "landscape", "show_company": False}})
        text, [(width, height), *_] = self._read_pdf(self.client.get(self.pdf_url))
        self.assertGreater(width, height)
        self.assertNotIn("Synthetic Payroll Company", text)
        text, [(width, height), *_] = self._read_pdf(self.client.get(self.pdf_url, {"template": "compact", "show_company": "1"}))
        self.assertLess(width, height)
        self.assertIn("Synthetic Payroll Company", text)
        self.assertEqual(get_export_preferences(self.user)["payslip"]["template"], "landscape")
        self.assertFalse(get_export_preferences(self.user)["payslip"]["show_company"])

    def test_email_attachment_uses_standard_copy_without_senders_note(self):
        save_export_preferences(self.user, {"payslip": {
            "template": "landscape", "show_company": False, "note": "Personal sender note.",
        }})
        request = RequestFactory().get(self.pdf_url, {"template": "unsupported", "configure": "1"})
        request.user = self.user
        request.session = {}
        text, [(width, height), *_] = self._read_pdf(payslip_attachment_pdf(request, self.payslip.pk))
        self.assertLess(width, height)
        self.assertIn("Synthetic Payroll Company", text)
        self.assertNotIn("Personal sender note.", text)

    def test_bearer_pdf_contract_and_validation(self):
        api = APIClient()
        token = RefreshToken.for_user(self.user).access_token
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        cases = (
            ({"format": "pdf", "template": "landscape"}, {}),
            ({"template": "landscape"}, {"HTTP_ACCEPT": "application/pdf"}),
            ({"preview": "1", "template": "landscape"}, {}),
        )
        for query, headers in cases:
            with self.subTest(query=query, headers=headers):
                response = api.get(self.api_url, query, **headers)
                text, [(width, height), *_] = self._read_pdf(response)
                self.assertGreater(width, height)
                self.assertIn("Transport Allowance", text)
                self.assertIn(f"payslip-{self.payslip.pk}.pdf", response.headers["Content-Disposition"])

        invalid = api.get(self.api_url, {"format": "pdf", "template": "unsupported"})
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("detail", invalid.json())
        self.assertEqual(self.client.get(self.pdf_url, {"template": "unsupported"}).status_code, 400)
        download = api.get(self.api_url, {"download": "1"})
        self._read_pdf(download)
        self.assertTrue(download.headers["Content-Disposition"].startswith("attachment;"))

    def test_peer_cannot_open_preview_or_download_another_payslip(self):
        peer = make_user("pdf-layout-peer")
        make_employee(company=self.company, user=peer, email=peer.email)
        self.client.force_login(peer)
        web = self.client.get(self.pdf_url, {"configure": "1", "preview": "1"})
        self.assertEqual(web.status_code, 302)
        self.assertNotIn(b"QA-001", web.content)
        api = APIClient()
        token = RefreshToken.for_user(peer).access_token
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = api.get(self.api_url, {"format": "pdf", "template": "compact"})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"QA-001", response.content)

    def test_compact_and_landscape_keep_last_rows_on_long_payslips(self):
        self.payslip.pay_head_data["allowances"].extend(
            {"title": f"Recorded allowance {index:02d}", "amount": 10}
            for index in range(1, 65)
        )
        self.payslip.save(update_fields=["pay_head_data"])
        for preset in ("compact", "landscape"):
            with self.subTest(preset=preset):
                text, sizes = self._read_pdf(self.client.get(self.pdf_url, {"template": preset}))
                self.assertGreater(len(sizes), 1)
                self.assertIn("Recorded allowance 01", text)
                self.assertIn("Recorded allowance 64", text)
                self.assertIn("14800.00", text)
