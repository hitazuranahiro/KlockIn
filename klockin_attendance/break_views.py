import json

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .breaks import BreakError, change_break, user_break_summary


def _break_action(payload):
    return payload.get("action") if isinstance(payload, dict) else None


@never_cache
@ensure_csrf_cookie
def web_break(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Sign in to manage breaks."}, status=401)
    try:
        if request.method in ("GET", "HEAD"):
            return JsonResponse(user_break_summary(request.user))
        if request.method == "POST":
            try:
                payload = json.loads(request.body)
            except ValueError:
                raise BreakError("Send a JSON object with a break action.", 400)
            return JsonResponse(change_break(request.user, _break_action(payload)))
        return JsonResponse({"detail": "Use GET or POST."}, status=405, headers={"Allow": "GET, HEAD, POST"})
    except BreakError as error:
        return JsonResponse({"detail": str(error)}, status=error.status)


@method_decorator(never_cache, name="dispatch")
class MobileBreakAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def get(self, request):
        try:
            return Response(user_break_summary(request.user))
        except BreakError as error:
            return Response({"detail": str(error)}, status=error.status)

    def post(self, request):
        try:
            return Response(change_break(request.user, _break_action(request.data)))
        except BreakError as error:
            return Response({"detail": str(error)}, status=error.status)
