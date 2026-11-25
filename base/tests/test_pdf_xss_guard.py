"""Shared document exports apply the markup guard before rendering."""

from io import BytesIO

from django.test import SimpleTestCase
from pypdf import PdfReader

from base.methods import generate_pdf


class GeneratePdfXssGuardTests(SimpleTestCase):
    def test_script_payload_is_refused(self):
        response = generate_pdf(
            "<html><body><script>fetch('/etc/passwd')</script></body></html>",
            {},
            path=False,
            title="Document",
        )

        self.assertEqual(response.status_code, 400)

    def test_local_file_exfiltration_payload_is_refused(self):
        # The shape the advisory describes: read a local file, post it out.
        payload = (
            "<html><body><script>"
            "var x=new XMLHttpRequest();"
            "x.open('GET','file:///etc/passwd');"
            "x.send();"
            "</script></body></html>"
        )

        response = generate_pdf(payload, {}, path=False, title="Document")

        self.assertEqual(response.status_code, 400)

    def test_onerror_handler_is_refused(self):
        response = generate_pdf(
            "<img src=x onerror=\"fetch('//evil.test')\">",
            {},
            path=False,
            title="Document",
        )

        self.assertEqual(response.status_code, 400)

    def test_ordinary_payslip_markup_still_renders(self):
        markup = (
            "<html><body><h1>Payslip</h1><table><tr><td>Basic</td>"
            "<td>50000</td></tr></table></body></html>"
        )
        response = generate_pdf(markup, {}, path=False, title="Payslip")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        text = PdfReader(BytesIO(response.content)).pages[0].extract_text()
        self.assertIn("Payslip", text)
        self.assertIn("50000", text)
