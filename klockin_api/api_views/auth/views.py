from hashlib import sha256

from axes.handlers.proxy import AxesProxyHandler
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_yasg import openapi
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from employee.models import Employee
from klockin_api.docs import document_api
from klockin_attendance.mobile_audit import MobileAuditDispatchMixin
from klockin_attendance.models import MobileActivity
from klockin_attendance.services import (
    PunchRejected,
    bind_login_device,
    validate_login_device_id,
)

from ...api_methods.base.capabilities import build_capabilities
from ...api_serializers.auth.serializers import (
    GetEmployeeSerializer,
    LoginRequestSerializer,
    PasswordResetSerializer,
)


def _employee_login_identity(badge):
    """Resolve one active employee and account before a company is known."""
    matches = list(
        Employee._base_manager.filter(
            badge_id=badge, is_active=True, employee_user_id__is_active=True,
        )
        .exclude(employee_user_id__username="")
        .values_list("employee_user_id__username", flat=True)[:2]
    )
    if len(matches) == 1:
        return matches[0], True

    # Run the ordinary password check and Axes hooks even for a missing or
    # ambiguous badge. Keep a stable lockout bucket without retaining the badge
    # in Axes or ever colliding with a valid account username (150 chars).
    digest = sha256(badge.encode("utf-8")).hexdigest()
    return f"klockin-unresolved-badge-{digest}".ljust(151, "_"), False


class LoginAPIView(MobileAuditDispatchMixin, APIView):
    mobile_audit_kind = MobileActivity.Kind.LOGIN
    permission_classes = [AllowAny]
    # The only unauthenticated write path in the API. django-axes locks an
    # account after repeated *failed* passwords, but counts nothing when the
    # credentials are valid -- so a leaked password can be replayed to mint
    # tokens as fast as the server answers. ScopedRateThrottle bounds that
    # by IP, on top of the axes lockout.
    throttle_scope = "login"

    @document_api(
        operation_description="Authenticate with an employee badge number or username and return JWTs with employee info",
        request_body=LoginRequestSerializer,
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "employee": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "full_name": openapi.Schema(type=openapi.TYPE_STRING),
                            "employee_profile": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description="Profile image URL",
                            ),
                        },
                    ),
                    "access": openapi.Schema(
                        type=openapi.TYPE_STRING, description="JWT access token"
                    ),
                    "refresh": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="JWT refresh token; exchange at /auth/refresh/",
                    ),
                    "capabilities": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        description="Resolved role, permission booleans and installed-feature manifest; also at /base/capabilities/",
                    ),
                    "face_detection": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "face_detection_image": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Face detection image URL",
                        nullable=True,
                    ),
                    "geo_fencing": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "company_id": openapi.Schema(
                        type=openapi.TYPE_INTEGER, nullable=True
                    ),
                },
            ),
            400: "Missing credentials or invalid device ID",
            403: "The mobile installation is not permitted for this employee",
        },
        tags=["auth"],
    )
    def post(self, request):
        using_badge = "employee_id" in request.data
        using_username = "username" in request.data
        identifier = request.data.get("employee_id" if using_badge else "username")
        password = request.data.get("password")
        if (
            using_badge != using_username
            and isinstance(identifier, str)
            and isinstance(password, str)
            and 0 < len(identifier) <= (50 if using_badge else 150)
            and "\x00" not in identifier
            and (not using_badge or identifier.strip())
        ):
            username, resolved = (
                _employee_login_identity(identifier.strip()) if using_badge else (identifier, True)
            )
            # Pass `request`: django-axes needs it to attribute the attempt to
            # a client and enforce the lockout. Without it the API login is
            # exempt from the brute-force protection the HTML login has --
            # and axes raises rather than silently allowing it.
            user = authenticate(request, username=username, password=password)
            if user and resolved:
                self.mobile_audit_actor = user
                device_id = None
                if "device_id" in request.data:
                    try:
                        device_id = validate_login_device_id(request.data["device_id"])
                    except PunchRejected as exc:
                        return Response({"code": exc.code, "detail": str(exc)}, status=exc.status)

                employee = getattr(user, "employee_get", None)
                if employee is None or (device_id is not None and not employee.is_active):
                    return Response(
                        {
                            "code": "employee_required",
                            "detail": _("An active employee profile is required."),
                        },
                        status=403,
                    )
                face_detection = False
                face_detection_image = None
                geo_fencing = False
                company_id = None
                # Each of these is optional configuration: get_company() can
                # return None, the face_detection and geo_fencing reverse
                # one-to-ones need not exist, and an ImageField with no file
                # raises on .url. Narrowed from bare excepts so a genuine
                # failure in this block is logged instead of silently
                # degrading the login response.
                company = employee.get_company()
                if company is not None:
                    company_id = company.id
                    try:
                        face_detection = company.face_detection.start
                    except (ObjectDoesNotExist, AttributeError):
                        pass
                    # the company's own fence, else the global one
                    from geofencing.models import GeoFencing

                    fence = GeoFencing.for_company(company)
                    geo_fencing = bool(fence and fence.start)
                try:
                    face_detection_image = employee.face_detection.image.url
                except (ObjectDoesNotExist, AttributeError, ValueError):
                    pass
                result = {
                    "employee": GetEmployeeSerializer(employee).data,
                    # Role, permission set and feature manifest in the login
                    # response so the client can paint its navigation on the
                    # first frame rather than after a dozen permission probes.
                    "capabilities": build_capabilities(user),
                    "face_detection": face_detection,
                    "face_detection_image": face_detection_image,
                    "geo_fencing": geo_fencing,
                    "company_id": company_id,
                }
                try:
                    with transaction.atomic():
                        if device_id is not None:
                            bind_login_device(user, device_id)
                        refresh = RefreshToken.for_user(user)
                        result.update(access=str(refresh.access_token), refresh=str(refresh))
                except PunchRejected as exc:
                    return Response({"code": exc.code, "detail": str(exc)}, status=exc.status)
                return Response(result, status=200)
            else:
                # A locked-out caller must be told so, not handed another 401.
                # AxesStandaloneBackend returns None rather than raising, so
                # without this check axes counts the failures but never blocks
                # -- the API would keep accepting guesses past the limit while
                # the HTML login stops at five.
                if AxesProxyHandler.is_locked(
                    request, credentials={"username": username}
                ):
                    return Response(
                        {
                            "error": _(
                                "Too many failed login attempts. Try again later."
                            )
                        },
                        status=429,
                    )
                return Response({"error": _("Invalid credentials")}, status=401)
        else:
            return Response(
                {"error": _("Provide an employee ID or username and your password.")}, status=400
            )


class PasswordResetAPIView(APIView):
    """
    Allows an authenticated employee to change their own password.

    GET  — returns the fields required for the reset form.
    POST — verifies the old password and saves the new one.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "login"

    def get(self, _request):
        return Response(
            {"fields": ["old_password", "new_password", "confirm_password"]},
            status=200,
        )

    def post(self, request):
        serializer = PasswordResetSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"message": _("Password updated successfully.")}, status=200)


class RevocationAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Refuse a refresh token that was issued before the password changed.

    ``CHECK_REVOKE_TOKEN`` is enforced in exactly one place upstream:
    ``JWTAuthentication.get_user()``, which runs only when an *access* token
    authenticates a request. ``TokenRefreshSerializer.validate()`` checks the
    signature, the expiry and ``USER_AUTHENTICATION_RULE`` -- and never looks
    at the revoke claim. So a refresh token survived the password change that
    was supposed to end the session, and because rotation mints a replacement
    on every call it could be renewed indefinitely for the full refresh
    lifetime.

    Verified before this fix: refresh after a password change returned 200 and
    a fresh token pair; the access token it issued was then rejected with 401,
    because ``access_token`` copies the stale hash across. So the practical
    effect was a session that could not be used but also could not be killed
    -- and the safety of the whole 30-day window rested on one setting staying
    on, and on nothing ever using ``JWTStatelessUserAuthentication``, which
    skips the check by design.

    Checked here rather than left to the access token so that a password reset
    means what it says: the credential stops working at the point it is
    presented.
    """

    def validate(self, attrs):
        if jwt_settings.CHECK_REVOKE_TOKEN:
            refresh = self.token_class(attrs["refresh"])
            user_id = refresh.payload.get(jwt_settings.USER_ID_CLAIM)
            user = (
                get_user_model()
                .objects.filter(**{jwt_settings.USER_ID_FIELD: user_id})
                .first()
            )
            if user is None or refresh.payload.get(
                jwt_settings.REVOKE_TOKEN_CLAIM
            ) != get_md5_hash_password(user.password):
                raise AuthenticationFailed(
                    _("The user's password has been changed."),
                    code="password_changed",
                )
        return super().validate(attrs)


class TokenRefreshAPIView(TokenRefreshView):
    """
    Exchange a refresh token for a new access token.

    ROTATE_REFRESH_TOKENS is on, so the response also carries a replacement
    refresh token and the one just spent is blacklisted -- clients must store
    the new one.

    Throttled under the "login" scope because this endpoint mints access
    tokens: unthrottled, a leaked refresh token is an unmetered token factory.
    """

    serializer_class = RevocationAwareTokenRefreshSerializer
    throttle_scope = "login"


class LogoutAPIView(TokenBlacklistView):
    """
    Blacklist a refresh token so it can no longer be exchanged.

    Note what this does not do: access tokens are stateless and are not
    revocable, so one issued moments before logout stays valid until it
    expires (at most ACCESS_TOKEN_LIFETIME). Blacklisting the refresh token
    caps the session rather than ending it instantly. Password change remains
    the immediate kill switch, via CHECK_REVOKE_TOKEN.
    """

    throttle_scope = "login"
