from django.urls import path

from . import audit, dtr

urlpatterns = [
    path("", dtr.attendance_workspace, name="klockin-attendance"),
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
