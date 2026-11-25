from django.apps import apps
from django.test import TestCase
from django.urls import reverse

from klockin.testkit.factories import make_company, make_employee, make_user

from .models import Tour, TourStep


class WorkspaceTourTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user(
            "workspace-tour-admin",
            email="tour-admin@demo.klockin.invalid",
            is_superuser=True,
        )
        make_employee(company=make_company(), email=cls.admin.email, user=cls.admin)

    def test_relocated_app_keeps_its_tables_and_migration_label(self):
        config = apps.get_app_config("horilla_tour")
        self.assertEqual(config.name, "klockin.tours")
        self.assertEqual(Tour._meta.db_table, "horilla_tour_tour")

    def test_bundled_tours_match_each_workspace(self):
        self.client.force_login(self.admin)
        for url_name, slug, target in (
            ("dashboard", "dashboard-highlights", ".ki-home-metrics"),
            ("ess-dashboard", "ess-dashboard-tour", ".ki-home-welcome"),
            ("klockin-attendance", "klockin-timekeeping", ".kd-filters"),
            ("project-dashboard-view", "project-management", ".pr-period-picker"),
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse("tour-active"), {"path": reverse(url_name)})
                self.assertEqual(response.status_code, 200)
                tours = {tour["slug"]: tour for tour in response.json()["tours"]}
                self.assertIn(slug, tours)
                self.assertIn("KlockIN", tours[slug]["title"])
                self.assertTrue(any(target in (step["element"] or "") for step in tours[slug]["steps"]))
                self.assertNotIn("klockin-project-overview", tours)

    def test_live_path_also_selects_page_specific_steps(self):
        tour = Tour.objects.create(
            slug="specific-step-test", title="Specific step test", page_match="klockin-attendance",
            is_published=True, trigger="manual",
        )
        TourStep.objects.create(
            tour=tour, sequence=1, title="Attendance only", description="For the current page.",
            page_match="klockin-attendance",
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("tour-active"), {"path": reverse("klockin-attendance")})
        tours = {item["slug"]: item for item in response.json()["tours"]}
        self.assertEqual(tours[tour.slug]["steps"][0]["title"], "Attendance only")
