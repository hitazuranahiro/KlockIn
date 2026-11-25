from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import Throttled
from rest_framework.test import APIClient

from klockin.testkit import make_company, make_employee, make_user

from ..mobile_audit import record_mobile_activity
from ..models import MobileActivity
from .test_ingestion import BATCH_URL, IngestionFixture, _client, _offline, _online, _payload

AUDIT_ENDPOINT = "/api/v2/attendance/mobile-audit/"


class MobileActivityTests(TestCase):
    def test_rejected_login_attempt_logs_metadata_without_credentials(self):
        response = APIClient().post(
            "/api/v1/auth/login/",
            {"username": "rejected-identifier", "password": "rejected-secret", "device_id": "excluded-device"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        event = MobileActivity._base_manager.values().get()
        self.assertIsNone(event["actor_id"])
        self.assertIsNone(event["company_id"])
        self.assertEqual(event["outcome"], MobileActivity.Outcome.REJECTED)
        self.assertNotIn("rejected-identifier", str(event))
        self.assertNotIn("rejected-secret", str(event))
        self.assertNotIn("excluded-device", str(event))

    def test_throttled_sign_in_is_still_audited(self):
        with patch(
            "klockin_api.api_views.auth.views.LoginAPIView.check_throttles",
            side_effect=Throttled(),
        ):
            response = APIClient().post("/api/v1/auth/login/", {}, format="json")
        self.assertEqual(response.status_code, 429)
        event = MobileActivity._base_manager.get(kind=MobileActivity.Kind.LOGIN)
        self.assertEqual(event.status_code, 429)
        self.assertIsNone(event.actor_id)

    def test_successful_employee_login_records_the_actor(self):
        company = make_company("Audit mobile sign-in")
        user = make_user("mobile-audit-user", password="fixture-login-password")
        employee = make_employee(company=company, email=user.email, user=user)
        employee.badge_id = "AUDIT-FIXTURE-ID"
        employee.save(update_fields=["badge_id"])
        response = APIClient().post(
            "/api/v1/auth/login/",
            {"employee_id": employee.badge_id, "password": "fixture-login-password", "device_id": "fixture-device"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        event = MobileActivity._base_manager.get(kind=MobileActivity.Kind.LOGIN)
        self.assertEqual((event.actor_id, event.company_id, event.outcome), (user.pk, company.pk, MobileActivity.Outcome.ACCEPTED))

    def test_admin_api_filters_by_company_and_requires_permission(self):
        first = make_company("Scope A")
        second = make_company("Scope B")
        reader = make_user("event-reader")
        other = make_user("other-audit-actor")
        make_employee(company=first, email=reader.email, user=reader)
        make_employee(company=second, email=other.email, user=other)
        make_event = {
            "kind": MobileActivity.Kind.OFFLINE_BATCH,
            "started_at": timezone.now(),
            "status_code": 200,
            "received_count": 3,
            "accepted_count": 1,
            "rejected_count": 1,
            "replayed_count": 1,
        }
        key = uuid4()
        record_mobile_activity(**make_event, actor=reader, batch_id=key)
        record_mobile_activity(**make_event, actor=other, batch_id=uuid4())
        record_mobile_activity(**make_event, batch_id=uuid4())
        self.assertEqual(_client(reader).get(AUDIT_ENDPOINT).status_code, 403)
        reader.user_permissions.add(Permission.objects.get(
            codename="view_mobileactivity", content_type__app_label="klockin_attendance",
        ))
        result = _client(reader).get(AUDIT_ENDPOINT)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["count"], 1)
        event = result.data["results"][0]
        self.assertEqual(str(event["batch_id"]), str(key))
        self.assertEqual(event["outcome"], MobileActivity.Outcome.PARTIAL)
        self.assertEqual(event["received_count"], 3)


class PunchAttemptAuditTests(IngestionFixture, TestCase):
    def test_unauthenticated_sync_requests_do_not_grow_the_audit_table(self):
        response = APIClient().post(BATCH_URL, [], format="json")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(MobileActivity._base_manager.exists())

    def test_throttled_sync_does_not_write_an_event(self):
        with patch(
            "klockin_attendance.views.AttendanceBatchSyncViewSet.check_throttles",
            side_effect=Throttled(),
        ):
            response = self.api.post(BATCH_URL, [], format="json")
        self.assertEqual(response.status_code, 429)
        self.assertFalse(MobileActivity._base_manager.exists())

    def test_authenticated_sync_validation_failure_is_audited(self):
        response = self.api.post(BATCH_URL, [], format="json")
        self.assertEqual(response.status_code, 400)
        event = MobileActivity._base_manager.get(kind=MobileActivity.Kind.OFFLINE_BATCH)
        self.assertEqual((event.actor_id, event.status_code), (self.user.pk, 400))

    def test_online_batch_replays_and_rejections_are_recorded(self):
        payload = _payload()
        self.assertEqual(_online(self.api, payload).status_code, 201)
        batch = self.api.post(BATCH_URL, [_offline(payload), _offline(_payload(gps_lat="91.0"))], format="json")
        self.assertEqual(batch.status_code, 200)
        events = MobileActivity._base_manager
        online = events.get(kind=MobileActivity.Kind.ONLINE_PUNCH)
        self.assertEqual(str(online.punch_uuid), payload["punch_uuid"])
        summary = events.get(kind=MobileActivity.Kind.OFFLINE_BATCH)
        self.assertEqual((summary.received_count, summary.replayed_count, summary.rejected_count), (2, 1, 1))
        self.assertEqual(summary.outcome, MobileActivity.Outcome.PARTIAL)
        self.assertEqual(events.filter(kind=MobileActivity.Kind.OFFLINE_PUNCH, batch_id=summary.batch_id).count(), 2)
