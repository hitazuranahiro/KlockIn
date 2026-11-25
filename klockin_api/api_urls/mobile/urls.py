from django.urls import path

from klockin_attendance.break_views import MobileBreakAPIView

from ...api_views.mobile.views import MobileHomeAPIView

urlpatterns = [
    path("home/", MobileHomeAPIView.as_view(), name="api-mobile-home"),
    path("break/", MobileBreakAPIView.as_view(), name="api-mobile-break"),
]
