"""
Admin registration for the horilla_theme app
"""

from django.contrib import admin

from klockin_theme.models import CompanyTheme, HorillaColorTheme

# Register your horilla_theme models here.
admin.site.register(HorillaColorTheme)
admin.site.register(CompanyTheme)
