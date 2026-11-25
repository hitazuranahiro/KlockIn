from django.conf import settings
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from klockin_api.schema import OrderedTagSchemaGenerator

# Create schema view for Swagger and ReDoc
schema_view = get_schema_view(
    openapi.Info(
        title="KlockIN API",
        default_version="v1",
        description="API documentation for KlockIN by Tomeku. Use the Authorize button to authenticate.",
        contact=openapi.Contact(name="Tomeku"),
        license=openapi.License(name="BSD License"),
    ),
    public=settings.DEBUG,
    permission_classes=(
        (permissions.AllowAny,) if settings.DEBUG else (permissions.IsAdminUser,)
    ),
    generator_class=OrderedTagSchemaGenerator,
)

urlpatterns = [
    # API Documentation URLs
    path(
        "swagger<format>/", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    path("docs/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-docs"),
    # API Endpoints (static configuration)
    path("auth/", include("klockin_api.api_urls.auth.urls")),
    path("asset/", include("klockin_api.api_urls.asset.urls")),
    path("base/", include("klockin_api.api_urls.base.urls")),
    path("employee/", include("klockin_api.api_urls.employee.urls")),
    path("notifications/", include("klockin_api.api_urls.notifications.urls")),
    path("payroll/", include("klockin_api.api_urls.payroll.urls")),
    path("attendance/", include("klockin_api.api_urls.attendance.urls")),
    path("leave/", include("klockin_api.api_urls.leave.urls")),
    path("helpdesk/", include("klockin_api.api_urls.helpdesk.urls")),
    path("project/", include("klockin_api.api_urls.project.urls")),
    path("onboarding/", include("klockin_api.api_urls.onboarding.urls")),
    path("offboarding/", include("klockin_api.api_urls.offboarding.urls")),
    path("recruitment/", include("klockin_api.api_urls.recruitment.urls")),
    path("pms/", include("klockin_api.api_urls.pms.urls")),
    # Screen-shaped aggregates for the mobile client; see api_views/mobile.
    path("mobile/", include("klockin_api.api_urls.mobile.urls")),
]
