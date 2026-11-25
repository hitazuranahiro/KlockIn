from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.contrib.auth.hashers import check_password
from django.db import transaction

from employee.models import Employee

from .mobile_audit import scoped_mobile_activity
from .models import AttendancePolicy, EmployeeDevice, MobileActivity


class DeviceResetActionForm(ActionForm):
    reset_pin = forms.CharField(
        label="Device reset PIN",
        max_length=64,
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "off"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.KLOCKIN_DEVICE_RESET_PIN_HASH:
            self.fields.pop("reset_pin")


@admin.register(EmployeeDevice)
class EmployeeDeviceAdmin(admin.ModelAdmin):
    list_display = ("employee", "device_fingerprint", "enrolled_at")
    readonly_fields = ("employee", "device_fingerprint", "enrolled_at")
    fields = readonly_fields
    search_fields = ("employee__employee_first_name", "employee__employee_last_name")
    action_form = DeviceResetActionForm
    actions = ("reset_binding",)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_reset_binding_permission(self, request):
        return request.user.is_superuser

    @admin.action(permissions=["reset_binding"], description="Reset selected device bindings")
    def reset_binding(self, request, queryset):
        pin_hash = settings.KLOCKIN_DEVICE_RESET_PIN_HASH
        if not pin_hash:
            self.message_user(
                request, "Configure the device reset PIN before resetting a binding.",
                level=messages.ERROR,
            )
            return
        if not check_password(request.POST.get("reset_pin", ""), pin_hash):
            self.message_user(request, "The device reset PIN is invalid.", level=messages.ERROR)
            return

        selected_ids = list(queryset.values_list("employee_id", flat=True))
        with transaction.atomic():
            # Acquire the same employee locks as punch ingestion before releasing a binding.
            employee_ids = list(
                Employee._base_manager.select_for_update()
                .filter(pk__in=selected_ids)
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            bindings = list(EmployeeDevice.objects.filter(employee_id__in=employee_ids))
            for binding in bindings:
                self.log_change(request, binding, "Reset the KlockIN device binding.")
                binding.delete()

        self.message_user(request, f"Reset {len(bindings)} device binding(s).")


@admin.register(AttendancePolicy)
class AttendancePolicyAdmin(admin.ModelAdmin):
    list_display = ("company", "mode", "break_start", "break_end", "break_allowance_minutes")
    search_fields = ("company__company",)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(MobileActivity)
class MobileActivityAdmin(admin.ModelAdmin):
    list_display = (
        "finished_at", "kind", "outcome", "actor", "company", "punch_uuid", "status_code",
    )
    list_filter = ("kind", "outcome")
    readonly_fields = tuple(field.name for field in MobileActivity._meta.fields)

    def get_queryset(self, request):
        return scoped_mobile_activity(request.user).select_related("actor", "company")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
