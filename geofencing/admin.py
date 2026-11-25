from django.contrib import admin
from django.core.exceptions import PermissionDenied

from base.models import Company

from .forms import AllowedLocationFormSet
from .models import MAX_ADDITIONAL_LOCATIONS, AllowedWorkLocation, GeoFencing
from .scope import configuration_company


class AllowedWorkLocationInline(admin.TabularInline):
    model = AllowedWorkLocation
    formset = AllowedLocationFormSet
    extra = 1
    max_num = MAX_ADDITIONAL_LOCATIONS


@admin.register(GeoFencing)
class GeoFencingAdmin(admin.ModelAdmin):
    list_display = ("company_id", "start", "radius_in_meters")
    inlines = (AllowedWorkLocationInline,)


    def get_queryset(self, request):
        fences = super().get_queryset(request)
        if request.user.is_superuser:
            return fences
        company = configuration_company(request)
        return fences.filter(company_id=company) if company is not None else fences.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "company_id" and not request.user.is_superuser:
            company = configuration_company(request)
            kwargs["queryset"] = Company.objects.filter(pk=getattr(company, "pk", None))
            kwargs["required"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            company = configuration_company(request)
            if company is None or obj.company_id != company:
                raise PermissionDenied
        super().save_model(request, obj, form, change)
