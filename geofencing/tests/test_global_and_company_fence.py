"""A global geofence and company geofences must work together (issue #1286).

Reported as: after a global fence exists, adding a fence for a company answers "Not valid", and the
global fence is not applied to any company. Both come from the same place:

* the setup page validated a company's new fence before giving it its company, and the model
  allows only one fence without a company - so as soon as a global fence existed, the new one
  (still company-less at that moment) was rejected;
* every lookup asked only for ``company_id=<this company>``, so the global fence was never used.

A company's own fence overrides the global one; a company with none falls back to it.
Nominatim is mocked - the model asks it to reverse-geocode on save.
"""


from tempfile import TemporaryDirectory
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse

from attendance.models import AttendanceActivity, AttendanceGeneralSetting
from geofencing.models import GeoFencing
from klockin.testkit import make_company, make_employee, make_user
from klockin_attendance.models import AttendancePunch
from klockin_attendance.tests.test_ingestion import _selfie

FENCE = {
    "latitude": "12.97",
    "longitude": "77.59",
    "radius_in_meters": "150",
    "start": "on",
}


def make_fence(company=None, **extra):
    values = {
        "latitude": 12.97,
        "longitude": 77.59,
        "radius_in_meters": 100,
        "start": True,
    }
    values.update(extra)
    return GeoFencing.objects.create(company_id=company, **values)


class FenceForCompanyTests(TestCase):
    def setUp(self):
        self.acme = make_company("Acme")
        self.globex = make_company("Globex", hq=False)

    def test_a_company_without_a_fence_uses_the_global_one(self):
        global_fence = make_fence(None, radius_in_meters=500)
        self.assertEqual(GeoFencing.for_company(self.acme), global_fence)
        self.assertEqual(GeoFencing.for_company(self.globex), global_fence)

    def test_a_companys_own_fence_overrides_the_global_one(self):
        make_fence(None, radius_in_meters=500)
        own = make_fence(self.acme, radius_in_meters=50)
        self.assertEqual(GeoFencing.for_company(self.acme), own)

    def test_no_fence_at_all_is_none(self):
        self.assertIsNone(GeoFencing.for_company(self.acme))
        self.assertIsNone(GeoFencing.for_company(None))

    def test_the_web_punch_check_follows_the_global_fence(self):
        from attendance.methods.utils import geofence_denial_web

        make_fence(None, radius_in_meters=100)
        far_away = RequestFactory().get("/", {"latitude": "40.0", "longitude": "-74.0"})
        self.assertIsNotNone(geofence_denial_web(far_away, self.acme))
        nearby = RequestFactory().get("/", {"latitude": "12.97", "longitude": "77.59"})
        self.assertIsNone(geofence_denial_web(nearby, self.acme))

    def test_a_switched_off_global_fence_blocks_nobody(self):
        from attendance.methods.utils import geofence_denial_web

        make_fence(None, start=False)
        far_away = RequestFactory().get("/", {"latitude": "40.0", "longitude": "-74.0"})
        self.assertIsNone(geofence_denial_web(far_away, self.acme))


class WhereTheFenceIsReadTests(TestCase):
    """Every place that reports or enforces the fence must read the same one."""

    def setUp(self):
        self.acme = make_company("Acme")
        self.user = make_user("fence-employee")
        self.employee = make_employee(
            company=self.acme, email="fence-employee@test.horilla", user=self.user
        )

    def test_the_api_punch_check_enforces_the_global_fence(self):
        from klockin_attendance.services import PunchRejected, _check_geofence

        make_fence(None, start=True)
        with self.assertRaises(PunchRejected) as denied:
            _check_geofence(self.employee, 40.0, -74.0)
        self.assertEqual(denied.exception.code, "outside_geofence")

    def test_no_fence_at_all_lets_the_punch_through(self):
        from klockin_attendance.services import _check_geofence

        self.assertIsNone(_check_geofence(self.employee, 40.0, -74.0))

    def test_the_mobile_config_reports_the_global_fence(self):
        from klockin_api.api_views.mobile.views import _geofence_block

        make_fence(None, radius_in_meters=500)
        block = _geofence_block(self.employee)
        self.assertTrue(block["enabled"])
        self.assertEqual(block["radius_in_meters"], 500)

    def test_the_mobile_config_is_off_without_any_fence(self):
        from klockin_api.api_views.mobile.views import _geofence_block

        self.assertEqual(_geofence_block(self.employee), {"enabled": False})

    def test_the_login_response_reports_the_global_fence(self):
        from rest_framework.test import APIClient

        make_fence(None, start=True)
        self.user.set_password("fence-pass-1")
        self.user.save()
        response = APIClient().post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": "fence-pass-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["geo_fencing"], True)

    def test_the_login_response_is_off_without_any_fence(self):
        from rest_framework.test import APIClient

        self.user.set_password("fence-pass-1")
        self.user.save()
        response = APIClient().post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": "fence-pass-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["geo_fencing"], False)

    def test_a_switched_off_company_fence_overrides_an_enabled_global_one(
        self
    ):
        from attendance.methods.utils import geofence_denial_web
        from klockin_api.api_views.mobile.views import _geofence_block

        make_fence(None, start=True)
        own = make_fence(self.acme, start=False)
        self.assertEqual(GeoFencing.for_company(self.acme), own)
        self.assertEqual(_geofence_block(self.employee), {"enabled": False})
        far_away = RequestFactory().get("/", {"latitude": "40.0", "longitude": "-74.0"})
        self.assertIsNone(geofence_denial_web(far_away, self.acme))


class FenceButtonWithAllCompaniesTests(TestCase):
    """With "all companies" selected the check-in button must still send the location."""

    def setUp(self):
        self.acme = make_company("Acme")
        self.user = make_user("fence-button-user")
        make_employee(
            company=self.acme, email="fence-button@test.horilla", user=self.user
        )
        # reload: the user still holds the employee object created above, whose work information
        # was cached before the company was set
        self.user = type(self.user).objects.get(pk=self.user.pk)

    def request(self, selected):
        request = RequestFactory().get("/")
        request.user = self.user
        request.session = {"selected_company": selected}
        return request

    def test_all_companies_uses_the_employees_own_company(self):
        from base.templatetags.klockinfilters import is_geofencing_enabled

        make_fence(None, start=True)
        self.assertTrue(is_geofencing_enabled(self.request("all")))

    def test_all_companies_follows_a_switched_off_company_fence(self):
        from base.templatetags.klockinfilters import is_geofencing_enabled

        make_fence(None, start=True)
        make_fence(self.acme, start=False)
        self.assertFalse(is_geofencing_enabled(self.request("all")))

    def test_a_selected_company_still_uses_that_company(self):
        from base.templatetags.klockinfilters import is_geofencing_enabled

        make_fence(None, start=True)
        self.assertTrue(is_geofencing_enabled(self.request(str(self.acme.pk))))

    def test_no_fence_means_no_location_is_requested(self):
        from base.templatetags.klockinfilters import is_geofencing_enabled

        self.assertFalse(is_geofencing_enabled(self.request("all")))


class SetupPageTests(TestCase):
    def setUp(self):
        self.acme = make_company("Acme")
        self.admin = make_user("fence-admin", is_superuser=True)
        make_employee(
            company=self.acme, email="fence-admin@test.horilla", user=self.admin
        )
        self.client.force_login(self.admin)
        self.url = reverse("geo-config")

    def post_for(self, company_id, **extra):
        session = self.client.session
        session["selected_company"] = company_id
        session.save()
        response = self.client.post(self.url, {**FENCE, **extra})
        return response

    def test_a_company_fence_can_be_added_after_a_global_one(self):
        make_fence(None)
        response = self.post_for(str(self.acme.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(GeoFencing.objects.filter(company_id=self.acme).exists())
        self.assertEqual(GeoFencing.objects.count(), 2)

    def test_the_global_fence_can_still_be_edited(self):
        global_fence = make_fence(None, radius_in_meters=100)
        self.post_for("all", radius_in_meters="250")
        global_fence.refresh_from_db()
        self.assertEqual(global_fence.radius_in_meters, 250)
        self.assertEqual(GeoFencing.objects.count(), 1)

    def test_a_second_global_fence_is_still_refused(self):
        make_fence(None)
        other = GeoFencing(
            latitude=1, longitude=1, radius_in_meters=10, company_id=None
        )
        with self.assertRaises(ValidationError):
            other.save()

    def test_editing_a_company_fence_updates_it_in_place(self):
        own = make_fence(self.acme, radius_in_meters=100)
        self.post_for(str(self.acme.pk), radius_in_meters="300")
        own.refresh_from_db()
        self.assertEqual(own.radius_in_meters, 300)
        self.assertEqual(GeoFencing.objects.count(), 1)


class WebPunchWithAllCompaniesTests(TestCase):
    """Confirmed browser punches use the employee's fence with All selected."""

    def setUp(self):
        self.acme = make_company("Acme")
        # Otherwise middleware selects the user's company for them.
        self.user = make_user("fence-punch-user", is_superuser=True)
        make_employee(
            company=self.acme, email="fence-punch@test.horilla", user=self.user
        )
        AttendanceGeneralSetting.objects.create(company_id=None, enable_check_in=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()
        selfie_dir = self.enterContext(TemporaryDirectory())
        self.enterContext(self.settings(KLOCKIN_SELFIE_ROOT=selfie_dir))

    def punch(self, **location):
        return self.client.post(
            reverse("klockin-web-punch"),
            {
                "action": "in",
                "punch_uuid": str(uuid4()),
                "selfie": SimpleUploadedFile("web.jpg", _selfie(), content_type="image/jpeg"),
                **location,
            },
        )

    def test_a_punch_from_outside_the_fence_is_refused_with_all_selected(self):
        make_fence(None, radius_in_meters=100)
        response = self.punch(latitude="40.0", longitude="-74.0")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["code"], "outside_geofence")
        self.assertFalse(AttendanceActivity.objects.exists())
        self.assertFalse(AttendancePunch.objects.exists())

    def test_a_punch_without_a_location_is_refused_with_all_selected(self):
        make_fence(None, radius_in_meters=100)
        response = self.punch()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("required", response.json()["detail"])
        self.assertFalse(AttendanceActivity.objects.exists())
        self.assertFalse(AttendancePunch.objects.exists())

    def test_a_punch_inside_the_fence_is_not_stopped_by_it(self):
        make_fence(None, radius_in_meters=100)
        response = self.punch(latitude="12.97", longitude="77.59")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(AttendanceActivity.objects.count(), 1)
        self.assertEqual(AttendancePunch.objects.get().source, AttendancePunch.Source.WEB)


class AllowedWorkLocationsTests(TestCase):
    def test_an_alternate_site_is_allowed_for_its_company_only(self):
        from geofencing.models import AllowedWorkLocation
        from klockin_attendance.services import PunchRejected, _check_geofence

        acme = make_company("Alternate office")
        other = make_company("Other office")
        acme_employee = make_employee(company=acme, email="alternate@demo.klockin.invalid")
        other_employee = make_employee(company=other, email="other-office@demo.klockin.invalid")
        acme_fence = make_fence(acme, start=True)
        make_fence(other, start=True)
        site = AllowedWorkLocation.objects.create(
            fence=acme_fence, name="East office", latitude=14.6, longitude=121.1, radius_in_meters=100,
        )
        _check_geofence(acme_employee, 14.6, 121.1)
        with self.assertRaises(PunchRejected):
            _check_geofence(other_employee, 14.6, 121.1)
        site.enabled = False
        site.save(update_fields=["enabled"])
        with self.assertRaises(PunchRejected):
            _check_geofence(acme_employee, 14.6, 121.1)


    def test_admin_queryset_hides_other_companies_and_global_fences(self):
        from django.contrib import admin
        from geofencing.admin import GeoFencingAdmin

        own = make_company("My work locations")
        other = make_company("Another company's work locations")
        user = make_user("geofence-location-editor")
        make_employee(company=own, email=user.email, user=user)
        user.refresh_from_db()
        own_fence = make_fence(own)
        make_fence(other)
        make_fence(None)
        request = RequestFactory().get("/admin/geofencing/geofencing/")
        request.user = user
        model_admin = GeoFencingAdmin(GeoFencing, admin.site)
        self.assertEqual(list(model_admin.get_queryset(request)), [own_fence])
        company_model_field = GeoFencing._meta.get_field("company_id")
        field = model_admin.formfield_for_foreignkey(company_model_field, request)
        self.assertEqual(list(field.queryset), [own])


class ScopedGeofenceConfigurationTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Group, Permission

        from base.models import CompanyGroupAssignment

        self.home = make_company("Geofence home")
        self.away = make_company("Geofence assigned", hq=False)
        self.user = make_user("scoped-geofence-editor")
        make_employee(company=self.home, email=self.user.email, user=self.user)
        self.home_role = Group.objects.create(name="Home geofence viewer")
        selected_role = Group.objects.create(name="Assigned geofence editor")
        selected_role.permissions.set(Permission.objects.filter(
            content_type__app_label="geofencing",
            codename__in=("view_geofencing", "change_geofencing", "delete_geofencing"),
        ))
        CompanyGroupAssignment.objects.create(user=self.user, company=self.home, group=self.home_role)
        CompanyGroupAssignment.objects.create(user=self.user, company=self.away, group=selected_role)
        self.home_fence = make_fence(self.home, radius_in_meters=100)
        self.away_fence = make_fence(self.away, radius_in_meters=200)
        self.client.force_login(self.user)
        self.select_company(str(self.away.pk))
        self.config_url = reverse("geo-config")

    def select_company(self, selected):
        session = self.client.session
        session["selected_company"] = selected
        session.save()

    def test_change_only_role_can_find_selected_company_settings_and_edit_its_fence(self):
        response = self.client.get(reverse("attendance-rule-view"))
        self.assertContains(response, f'hx-get="{self.config_url}"')
        self.assertContains(self.client.get(self.config_url), "Alternate allowed work locations")
        response = self.client.post(self.config_url, {**FENCE, "radius_in_meters": "300"})
        self.assertEqual(response.status_code, 200)
        self.home_fence.refresh_from_db()
        self.away_fence.refresh_from_db()
        self.assertEqual(self.home_fence.radius_in_meters, 100)
        self.assertEqual(self.away_fence.radius_in_meters, 300)

    def test_change_only_role_cannot_create_missing_company_fence(self):
        self.away_fence.delete()
        self.assertContains(self.client.get(self.config_url), "permission to add geofencing")
        self.assertEqual(self.client.post(self.config_url, FENCE).status_code, 403)
        self.assertFalse(GeoFencing.objects.filter(company_id=self.away).exists())

    def test_setup_jwt_mutation_stays_in_token_company(self):
        from django.contrib.auth.models import Permission
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import AccessToken

        self.home_role.permissions.set(Permission.objects.filter(
            content_type__app_label="geofencing",
            codename__in=("view_geofencing", "change_geofencing", "delete_geofencing"),
        ))
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.user)}")
        setup_url = "/api/geofencing/setup/"
        result = api.get(setup_url)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["company_id"], self.home.pk)
        away_url = f"{setup_url}{self.away_fence.pk}/"
        self.assertEqual(api.put(away_url, {"radius_in_meters": 900}).status_code, 404)
        self.assertEqual(api.delete(away_url).status_code, 404)
        home_url = f"{setup_url}{self.home_fence.pk}/"
        response = api.put(home_url, {"company_id": self.away.pk, "radius_in_meters": 350})
        self.assertEqual(response.status_code, 200)
        self.home_fence.refresh_from_db()
        self.assertEqual(self.home_fence.company_id_id, self.home.pk)
        self.assertEqual(self.home_fence.radius_in_meters, 350)
        self.away_fence.refresh_from_db()
        self.assertEqual(self.away_fence.radius_in_meters, 200)

    def test_all_companies_requires_single_company_selection(self):
        self.select_company("all")
        self.assertContains(self.client.get(reverse("attendance-rule-view")), "Select one company")
        self.assertEqual(self.client.post(self.config_url, FENCE).status_code, 403)
