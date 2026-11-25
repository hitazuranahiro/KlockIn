"""
admin.py

This page is used to register attendance models with admins site.
"""

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .corrections import CORRECTION_REASON_LIMIT, save_attendance_correction

from .models import (
    Attendance,
    AttendanceActivity,
    AttendanceLateComeEarlyOut,
    AttendanceOverTime,
    AttendanceRequestComment,
    AttendanceValidationCondition,
    GraceTime,
    WorkRecords,
)

class AttendanceCorrectionAdminForm(forms.ModelForm):
    correction_reason = forms.CharField(
        label=_("Reason for correction"),
        min_length=3,
        max_length=CORRECTION_REASON_LIMIT,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    class Meta:
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance._state.adding:
            reason = self.fields["correction_reason"]
            reason.required = False
            reason.widget = forms.HiddenInput()


@admin.register(Attendance, AttendanceActivity)
class AttendanceCorrectionAdmin(admin.ModelAdmin):
    form = AttendanceCorrectionAdminForm

    def save_model(self, request, obj, form, change):
        save = super().save_model
        if change:
            save_attendance_correction(
                obj,
                request.user,
                form.cleaned_data["correction_reason"],
                lambda: save(request, obj, form, change),
            )
        else:
            save(request, obj, form, change)


admin.site.register(AttendanceOverTime)
admin.site.register(AttendanceLateComeEarlyOut)
admin.site.register(AttendanceValidationCondition)
admin.site.register(GraceTime)
admin.site.register(AttendanceRequestComment)
admin.site.register(WorkRecords)
