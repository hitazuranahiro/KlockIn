from django.urls import path

from . import audit, dtr, missed_punch_views
from .web_punch import BrowserPunchLocationView, BrowserPunchView

urlpatterns = [
    path("", dtr.attendance_workspace, name="klockin-attendance"),
    path(
        "missed-punches/",
        missed_punch_views.missed_punch_workspace,
        name="klockin-missed-punches",
    ),
    path(
        "missed-punches/<int:pk>/decision/",
        missed_punch_views.missed_punch_decision,
        name="klockin-missed-punch-decision",
    ),
    path("web-punch/", BrowserPunchView.as_view(), name="klockin-web-punch"),
    path("web-punch/location/", BrowserPunchLocationView.as_view(), name="klockin-web-punch-location"),
    path("export/", dtr.attendance_export, name="klockin-attendance-export"),
    path("day/<int:pk>/", dtr.attendance_detail, name="klockin-attendance-detail"),
    path(
        "punch/<uuid:punch_uuid>/review/",
        dtr.punch_review,
        name="klockin-punch-review",
    ),
    path(
        "employee/<int:employee_id>/dtr.pdf",
        dtr.monthly_dtr,
        name="klockin-monthly-dtr",
    ),
    path(
        "employee/<int:employee_id>/audit/",
        audit.employee_attendance_audit,
        name="klockin-employee-attendance-audit",
    ),
    path(
        "punch/<uuid:punch_uuid>/selfie/", dtr.punch_selfie, name="klockin-punch-selfie"
    ),
]
