from django.core.exceptions import ValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from klockin.export_preferences import get_export_preferences, save_export_preferences


@method_decorator(never_cache, name="dispatch")
class ExportPreferencesAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(get_export_preferences(request.user))

    def patch(self, request):
        try:
            preferences = save_export_preferences(request.user, request.data)
        except ValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
        return Response(preferences)
