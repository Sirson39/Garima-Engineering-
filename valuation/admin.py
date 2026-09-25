from django.contrib import admin

from .models import ValuationActivity, ValuationBank, ValuationDocumentChecklist, ValuationRequest, ValuationReviewComment


@admin.register(ValuationBank)
class ValuationBankAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "branch", "organization__name")


@admin.register(ValuationRequest)
class ValuationRequestAdmin(admin.ModelAdmin):
    list_display = ("reference_number", "borrower_name", "organization", "status", "priority", "request_date")
    list_filter = ("organization", "status", "priority")
    search_fields = ("reference_number", "borrower_name", "property_owner_name", "bank_reference_number")


@admin.register(ValuationDocumentChecklist)
class ValuationDocumentChecklistAdmin(admin.ModelAdmin):
    list_display = ("document_type", "request", "status", "is_required", "verified_by")
    list_filter = ("status", "is_required")


@admin.register(ValuationReviewComment)
class ValuationReviewCommentAdmin(admin.ModelAdmin):
    list_display = ("request", "author", "is_resolved", "created_at")
    list_filter = ("is_resolved",)


@admin.register(ValuationActivity)
class ValuationActivityAdmin(admin.ModelAdmin):
    list_display = ("request", "action", "from_status", "to_status", "actor", "created_at")
    list_filter = ("action", "from_status", "to_status")
