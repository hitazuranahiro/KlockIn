from math import isfinite

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from geopy.distance import geodesic


MAX_ADDITIONAL_LOCATIONS = 39


def validate_coordinates(latitude, longitude):
    if (
        latitude is None or longitude is None
        or not isfinite(latitude) or not isfinite(longitude)
        or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
    ):
        raise ValueError("Invalid latitude or longitude.")


class GeoFencing(models.Model):
    latitude = models.FloatField()
    longitude = models.FloatField()
    radius_in_meters = models.IntegerField()
    company_id = models.OneToOneField(
        "base.Company",
        related_name="geo_fencing",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    start = models.BooleanField(default=False)

    @classmethod
    def for_company(cls, company):
        """
        The fence that applies to ``company``: its own, else the global one (the row with no
        company), else None. A company-specific fence overrides the global one - including a
        company fence that is switched off (``start=False``), which turns the fence off for
        that company even while the global one is on.
        """
        fence = None
        if company is not None:
            fence = cls.objects.filter(company_id=company).first()
        if fence is None:
            fence = cls.objects.filter(company_id__isnull=True).first()
        return fence

    def locations(self):
        """Send the original required site and all enabled alternate sites."""
        yield {
            "name": str(_("Primary location")),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius_in_meters": self.radius_in_meters,
        }
        yield from self.additional_locations.filter(enabled=True).order_by("id").values(
            "name", "latitude", "longitude", "radius_in_meters"
        )[:MAX_ADDITIONAL_LOCATIONS]

    def allows(self, latitude, longitude):
        validate_coordinates(latitude, longitude)
        matched = False
        for location in self.locations():
            lat = location["latitude"]
            lng = location["longitude"]
            radius = location["radius_in_meters"]
            validate_coordinates(lat, lng)
            if radius < 0:
                raise ValueError("Invalid configured geofence radius.")
            matched |= geodesic((lat, lng), (latitude, longitude)).meters <= radius
        return matched

    def clean(self):
        if self.company_id is None:
            qs = GeoFencing.objects.filter(company_id__isnull=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    _("Only one GeoFencing can have a null company_id.")
                )

        try:
            validate_coordinates(self.latitude, self.longitude)
        except ValueError as exc:
            raise ValidationError(_("Enter valid latitude and longitude coordinates.")) from exc
        if self.radius_in_meters is not None and self.radius_in_meters < 0:
            raise ValidationError({"radius_in_meters": _("Radius must be zero or greater.")})

        return super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()  # Run clean before save
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company_id"],
                name="unique_company_id_when_not_null_geofencing",
                condition=~Q(company_id=None),
            )
        ]


class AllowedWorkLocation(models.Model):
    fence = models.ForeignKey(GeoFencing, on_delete=models.CASCADE, related_name="additional_locations")
    name = models.CharField(max_length=100)
    latitude = models.FloatField(validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(validators=[MinValueValidator(-180), MaxValueValidator(180)])
    radius_in_meters = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(fields=["fence", "name"], name="geofencing_unique_location_name"),
            models.CheckConstraint(condition=Q(latitude__gte=-90, latitude__lte=90), name="geofencing_location_latitude_range"),
            models.CheckConstraint(condition=Q(longitude__gte=-180, longitude__lte=180), name="geofencing_location_longitude_range"),
            models.CheckConstraint(condition=Q(radius_in_meters__gt=0), name="geofencing_location_radius_positive"),
        ]

    def __str__(self):
        return self.name
