from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.forms import UserForm
from accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserForm
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Garima Details", {"fields": ("employee_code", "phone", "job_title", "nepali_name", "avatar", "notes")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Garima Details", {"fields": ("employee_code", "phone", "job_title", "nepali_name", "avatar", "notes")}),
    )
    list_display = ("username", "display_name", "email", "job_title", "is_staff", "is_active")
    search_fields = ("username", "first_name", "last_name", "email", "employee_code", "phone")
    ordering = ("username",)

