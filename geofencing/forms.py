from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm

from .models import AllowedWorkLocation, GeoFencing, MAX_ADDITIONAL_LOCATIONS


class GeoFencingSetupForm(ModelForm):
    verbose_name = _("Geofence Configuration")

    class Meta:
        model = GeoFencing
        exclude = ["company_id"]


AllowedLocationFormSet = inlineformset_factory(
    GeoFencing,
    AllowedWorkLocation,
    fields=("name", "latitude", "longitude", "radius_in_meters", "enabled"),
    extra=1,
    max_num=MAX_ADDITIONAL_LOCATIONS,
    validate_max=True,
    can_delete=True,
)
