from django.urls import path

from klockin_attendance.break_views import MobileBreakAPIView

from ...api_views.mobile.dtr import MobileDTRAPIView
from ...api_views.mobile.export_preferences import ExportPreferencesAPIView
from ...api_views.mobile.views import MobileHomeAPIView

urlpatterns = [
    path("export-preferences/", ExportPreferencesAPIView.as_view(), name="api-mobile-export-preferences"),
    path("home/", MobileHomeAPIView.as_view(), name="api-mobile-home"),
    path("break/", MobileBreakAPIView.as_view(), name="api-mobile-break"),
    path("dtr/", MobileDTRAPIView.as_view(), name="api-mobile-dtr"),
]
