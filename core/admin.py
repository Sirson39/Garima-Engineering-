from django.contrib import admin

from core.models import AuditLog, LoginAttempt, Notification, OrganizationProfile


@admin.register(OrganizationProfile)
class OrganizationProfileAdmin(admin.ModelAdmin):
    list_display = ("company_name", "short_name", "default_bs_year", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "project", "object_type", "object_id")
    search_fields = ("action", "summary", "object_type", "object_id", "project__project_number", "actor__username")
    list_filter = ("action", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "title", "level", "is_read")
    search_fields = ("title", "message", "user__username")
    list_filter = ("level", "is_read")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("identifier", "ip_address", "attempts", "locked_until", "updated_at")
    search_fields = ("identifier", "ip_address")
    list_filter = ("locked_until",)
    readonly_fields = ("created_at", "updated_at")

