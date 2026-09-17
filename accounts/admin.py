from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.forms import UserForm
from accounts.models import Company, User


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "legal_name", "email", "phone")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserForm
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Garima Details", {"fields": ("employee_code", "phone", "job_title", "nepali_name", "avatar", "notes")}),
        ("Platform Access", {"fields": ("company", "company_role", "is_platform_admin")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Garima Details", {"fields": ("employee_code", "phone", "job_title", "nepali_name", "avatar", "notes")}),
        ("Platform Access", {"fields": ("company", "company_role", "is_platform_admin")}),
    )
    list_display = ("username", "display_name", "company", "company_role", "is_platform_admin", "is_active")
    search_fields = ("username", "first_name", "last_name", "email", "employee_code", "phone")
    ordering = ("username",)
