from django.contrib import admin

from .models import OfficeDepartment, OfficeStaffProfile


@admin.register(OfficeDepartment)
class OfficeDepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "department_head", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "code", "organization__name")


@admin.register(OfficeStaffProfile)
class OfficeStaffProfileAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "user", "organization", "department", "employment_status", "account_status")
    list_filter = ("organization", "employment_status", "account_status")
    search_fields = ("employee_id", "user__email", "user__first_name", "user__last_name")
