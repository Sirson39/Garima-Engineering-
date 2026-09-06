from django.contrib import admin

from workflows.models import DocumentCategory, DocumentTemplate, NumberingScheme, ServiceType, WorkflowStageTemplate


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "updated_at")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(NumberingScheme)
class NumberingSchemeAdmin(admin.ModelAdmin):
    list_display = ("service_type", "prefix", "service_code", "year_label", "next_sequence", "is_active")
    search_fields = ("service_type__name", "service_code", "prefix")
    list_filter = ("is_active",)


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "service_type", "order", "is_active")
    search_fields = ("name", "code")
    list_filter = ("service_type", "is_active")


@admin.register(WorkflowStageTemplate)
class WorkflowStageTemplateAdmin(admin.ModelAdmin):
    list_display = ("service_type", "order", "name", "default_status", "wait_type", "is_start", "is_terminal")
    search_fields = ("name", "code", "service_type__name")
    list_filter = ("service_type", "wait_type", "is_start", "is_terminal")


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ("service_type", "order", "name", "category", "required", "allow_exception", "is_active")
    search_fields = ("name", "service_type__name", "category__name")
    list_filter = ("service_type", "required", "allow_exception", "is_active")

