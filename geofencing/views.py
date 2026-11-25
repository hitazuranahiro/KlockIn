from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from base.models import Company
from geofencing.forms import AllowedLocationFormSet, GeoFencingSetupForm
from klockin.decorators import login_required

from .models import GeoFencing
from .scope import configuration_company, employee_company
from .serializers import EmployeeLocationSerializer, GeoFencingSetupSerializer


def _require_company(request):
    company = configuration_company(request)
    if company is None:
        raise PermissionDenied(_("Select one company to manage its allowed work locations."))
    return company


class GeoFencingSetupGetPostAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(
        permission_required("geofencing.view_geofencing", raise_exception=True),
        name="dispatch",
    )
    def get(self, request):
        company = employee_company(request) if request.user.is_superuser else _require_company(request)
        location = get_object_or_404(GeoFencing, company_id=company)
        serializer = GeoFencingSetupSerializer(location)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @method_decorator(
        permission_required("geofencing.add_geofencing", raise_exception=True),
        name="dispatch",
    )
    def post(self, request):
        data = request.data.copy()
        if not request.user.is_superuser:
            data["company_id"] = _require_company(request).pk
        serializer = GeoFencingSetupSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GeoFencingSetupPutDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_location(self, request, pk):
        fences = GeoFencing.objects.all()
        if not request.user.is_superuser:
            fences = fences.filter(company_id=_require_company(request))
        return get_object_or_404(fences, pk=pk)

    @method_decorator(
        permission_required("geofencing.change_geofencing", raise_exception=True),
        name="dispatch",
    )
    def put(self, request, pk):
        location = self.get_location(request, pk)
        data = request.data.copy()
        if not request.user.is_superuser:
            data["company_id"] = location.company_id_id
        serializer = GeoFencingSetupSerializer(location, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @method_decorator(
        permission_required("geofencing.delete_geofencing", raise_exception=True),
        name="dispatch",
    )
    def delete(self, request, pk):
        location = self.get_location(request, pk)
        location.delete()
        return Response(
            {"message": "GeoFencing location deleted successfully"},
            status=status.HTTP_200_OK,
        )


class GeoFencingEmployeeLocationCheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_company(self, request):
        return employee_company(request)

    def get_company_location(self, request):
        company = self.get_company(request)
        location = GeoFencing.for_company(company)
        if location is None:
            raise serializers.ValidationError(_("No geofencing is configured."))
        return location

    def post(self, request):
        serializer = EmployeeLocationSerializer(data=request.data)
        company_location = self.get_company_location(request)
        if company_location.start:
            if serializer.is_valid():
                try:
                    inside = company_location.allows(**serializer.validated_data)
                except (TypeError, ValueError) as exc:
                    raise serializers.ValidationError(_("Could not verify this location.")) from exc
                if inside:
                    return Response(
                        {"message": "Inside the geofence"}, status=status.HTTP_200_OK
                    )
                return Response(
                    {"message": "Outside the geofence"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        raise serializers.ValidationError(_("Geofencing is not yet started.."))


class GeoFencingSetUpPermissionCheck(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(
        permission_required("geofencing.view_geofencing", raise_exception=True),
        name="dispatch",
    )
    def get(self, request):
        if not request.user.is_superuser:
            _require_company(request)
        return Response(status=200)


def get_company(request):
    if not request.user.is_superuser:
        return _require_company(request)
    company_id = request.session.get("selected_company", "all")
    if company_id == "all":
        return None
    return get_object_or_404(Company, pk=company_id)


@login_required
@permission_required("geofencing.change_geofencing", raise_exception=True)
def geo_location_config(request):
    """Set the primary site and alternate work locations for this company."""
    if request.method not in ("GET", "POST"):
        return HttpResponseBadRequest()
    company = get_company(request)
    instance = GeoFencing.objects.filter(company_id=company).first() or GeoFencing(company_id=company)
    data = request.POST if request.method == "POST" else None
    if instance.pk is None and not request.user.has_perm("geofencing.add_geofencing"):
        if data is not None:
            raise PermissionDenied
        return render(request, "geo_config.html", {"requires_add_permission": True})
    form = GeoFencingSetupForm(data, instance=instance)
    locations_data = data if data is not None and "locations-TOTAL_FORMS" in data else None
    locations = AllowedLocationFormSet(locations_data, instance=instance, prefix="locations")
    if data is not None:
        forms_valid = form.is_valid()
        locations_valid = locations_data is None or locations.is_valid()
        if forms_valid and locations_valid:
            with transaction.atomic():
                fence = form.save()
                if locations_data is not None:
                    locations.instance = fence
                    locations.save()
            messages.success(request, _("Allowed work locations saved."))
            form = GeoFencingSetupForm(instance=fence)
            locations = AllowedLocationFormSet(instance=fence, prefix="locations")
    return render(request, "geo_config.html", {"form": form, "locations": locations})
