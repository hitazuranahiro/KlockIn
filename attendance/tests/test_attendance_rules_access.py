from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from attendance.models import AttendanceGeneralSetting
from base.models import CompanyGroupAssignment
from klockin.testkit.factories import make_company, make_employee, make_user


class AttendanceRulesAccessTests(TestCase):
    def setUp(self):
        self.company = make_company("Attendance settings access")
        self.user = make_user("rules-viewer")
        make_employee(company=self.company, email=self.user.email, user=self.user)
        self.client.force_login(self.user)
        self.url = reverse("attendance-rule-view")

    def test_attendance_viewer_cannot_load_settings_or_create_defaults(self):
        viewer = Group.objects.get(name="Attendance Viewer")
        CompanyGroupAssignment.objects.create(user=self.user, company=self.company, group=viewer)
        count = AttendanceGeneralSetting.objects.count()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(AttendanceGeneralSetting.objects.count(), count)

    def test_read_only_settings_permission_can_view_without_creating_defaults(self):
        permission = Permission.objects.get(
            content_type__app_label="attendance", codename="view_attendancegeneralsetting",
        )
        self.user.user_permissions.add(permission)
        count = AttendanceGeneralSetting.objects.count()
        self.assertContains(self.client.get(self.url), "Enable Check In/Check Out")
        self.assertEqual(AttendanceGeneralSetting.objects.count(), count)
