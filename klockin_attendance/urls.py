from django.urls import path

from .mobile_audit import MobileActivityList
from .views import AttendanceBatchSyncViewSet, AttendancePunchViewSet, DeviceQueueReportView


app_name = "klockin_attendance"

urlpatterns = [
    path("mobile-audit/", MobileActivityList.as_view(), name="mobile_audit"),
    path("punch/", AttendancePunchViewSet.as_view({"post": "create"}), name="attendance_punch"),
    path("device-queue/", DeviceQueueReportView.as_view(), name="device_queue"),
    path(
        "sync-batch/",
        AttendanceBatchSyncViewSet.as_view({"post": "create"}),
        name="attendance_batch_sync",
    ),
]
