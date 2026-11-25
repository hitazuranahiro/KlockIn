"""
Quick-export column paths are client-supplied attribute walks. They must not
be able to reach credentials through relations (employee_user_id__password).
"""

import csv
import io

from django.test import TestCase
from django.urls import reverse

from klockin.testkit import make_company, make_employee, make_user
from klockin_audit.models import AuditTag


class ExportColumnPathTests(TestCase):
    def setUp(self):
        company = make_company("Export Corp")
        self.admin = make_user(
            "export_admin", is_superuser=True, password="pw-not-real"
        )
        make_employee(company=company, email="admin@test.horilla", user=self.admin)
        self.target = make_employee(
            company=company, email="target@test.horilla", first_name="Targeted"
        )
        self.client.force_login(self.admin)
        # client.session returns a fresh store each time: it has to be bound
        # and saved, or the assignment is silently lost.
        session = self.client.session
        session["selected_company"] = str(company.pk)
        session.save()

    def _export(self, columns):
        url = (
            reverse("export-list", kwargs={"short_id": "abc"})
            + "?model=employee.Employee"
        )
        return self.client.post(
            url,
            {"ids": str([self.target.pk]), "columns": str(columns), "format": "csv"},
        )

    def test_export_uses_stable_model_label_from_the_list_view(self):
        tag = AuditTag.objects.create(title="Reviewed")
        response = self.client.get(reverse("audit-tag-list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        export_path = response.context["export_path"]
        self.assertTrue(export_path.endswith("?model=horilla_audit.AuditTag"), export_path)

        old_path = export_path.replace(
            "horilla_audit.AuditTag", "horilla_audit.models.AuditTag"
        )
        for path in (export_path, old_path):
            with self.subTest(path=path):
                csv_response = self.client.post(
                    path,
                    {
                        "ids": str([tag.pk]),
                        "columns": '[["Title", "title"]]',
                        "format": "csv",
                    },
                )
                self.assertEqual(csv_response.status_code, 200)
                self.assertEqual(csv_response["Content-Type"], "text/csv")
                self.assertContains(csv_response, "Reviewed")

    def test_credential_paths_are_blanked(self):
        response = self._export(
            [["Name", "employee_first_name"], ["Pw", "employee_user_id__password"]]
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode(errors="ignore")
        self.assertIn("Targeted", body)
        self.assertNotIn(self.target.employee_user_id.password, body)
        self.assertNotIn("pbkdf2", body)

    def test_private_attributes_are_blanked(self):
        response = self._export([["State", "_state__db"]])
        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        # The last two rows are the header and the one data row, and the private attribute's cell is
        # empty: reading target._state.db would put "default" here.
        self.assertEqual(rows[-2:], [["State"], [""]])
