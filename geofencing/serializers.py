from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import GeoFencing, validate_coordinates


class GeoFencingSetupSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeoFencing
        fields = "__all__"

    def validate(self, data):
        latitude = data.get("latitude", getattr(self.instance, "latitude", None))
        longitude = data.get("longitude", getattr(self.instance, "longitude", None))
        radius = data.get("radius_in_meters", getattr(self.instance, "radius_in_meters", 0))
        try:
            validate_coordinates(latitude, longitude)
        except ValueError as exc:
            raise serializers.ValidationError(_("Enter valid latitude and longitude coordinates.")) from exc
        if radius < 0:
            raise serializers.ValidationError({"radius_in_meters": _("Radius must be zero or greater.")})
        return data


class EmployeeLocationSerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
