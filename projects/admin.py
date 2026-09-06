from django.contrib import admin

from projects.models import (
    Client,
    DocumentChecklistItem,
    GovernmentRecord,
    MunicipalityActivity,
    Payment,
    PhysicalFileTransfer,
    Project,
    ProjectComment,
    ProjectDocument,
    ProjectStageHistory,
    SiteVisit,
    SiteVisitAttachment,
    StageAttachment,
    Task,
    TaskAttachment,
)


class ProjectDocumentInline(admin.TabularInline):
    model = ProjectDocument
    extra = 0
    fields = ("display_name", "revision_number", "approval_status", "uploaded_by", "uploaded_at", "is_current")
    readonly_fields = ("uploaded_at",)


class ChecklistInline(admin.TabularInline):
    model = DocumentChecklistItem
    extra = 0
    fields = (
        "name",
        "required",
        "received",
        "original_seen",
        "scanned",
        "verified",
        "received_date",
        "verified_by",
    )


class StageHistoryInline(admin.TabularInline):
    model = ProjectStageHistory
    extra = 0
    fields = ("stage_name", "status", "assigned_employee", "started_at", "completed_at", "due_date")
    readonly_fields = ("started_at", "completed_at")


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "mobile_number", "municipality", "ward_number", "created_at")
    search_fields = ("full_name", "mobile_number", "citizenship_number")
    list_filter = ("municipality", "province", "is_deleted")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "project_number",
        "client",
        "service_type",
        "status",
        "priority",
        "current_responsible_employee",
        "current_file_holder",
        "remaining_balance",
        "updated_at",
    )
    search_fields = ("project_number", "client__full_name", "client__mobile_number", "government_application_number")
    list_filter = ("service_type", "status", "priority", "municipality", "ward_number")
    autocomplete_fields = ("client", "service_type", "current_stage_template", "current_stage_record", "current_responsible_employee", "created_by", "updated_by")
    filter_horizontal = ("members",)
    inlines = [ChecklistInline, ProjectDocumentInline, StageHistoryInline]


@admin.register(DocumentChecklistItem)
class DocumentChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("project", "name", "required", "received", "verified", "exception_approved_by")
    search_fields = ("project__project_number", "name")
    list_filter = ("required", "received", "verified")


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = ("project", "display_name", "revision_number", "approval_status", "uploaded_by", "is_current")
    search_fields = ("project__project_number", "display_name", "original_filename", "document_key")
    list_filter = ("approval_status", "confidentiality_level", "is_current")


@admin.register(ProjectStageHistory)
class ProjectStageHistoryAdmin(admin.ModelAdmin):
    list_display = ("project", "stage_name", "status", "assigned_employee", "started_at", "completed_at", "due_date")
    search_fields = ("project__project_number", "stage_name")
    list_filter = ("status", "stage_template__service_type")


@admin.register(StageAttachment)
class StageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("stage_history", "original_filename", "uploaded_by", "created_at")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("project", "title", "assigned_employee", "status", "priority", "due_date", "completion_date")
    search_fields = ("project__project_number", "title")
    list_filter = ("status", "priority")


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(admin.ModelAdmin):
    list_display = ("task", "original_filename", "uploaded_by", "created_at")


@admin.register(SiteVisit)
class SiteVisitAdmin(admin.ModelAdmin):
    list_display = ("project", "assigned_engineer", "scheduled_date", "actual_visit_date", "visit_status")
    search_fields = ("project__project_number", "contact_person", "site_address")
    list_filter = ("visit_status",)


@admin.register(SiteVisitAttachment)
class SiteVisitAttachmentAdmin(admin.ModelAdmin):
    list_display = ("site_visit", "original_filename", "uploaded_by", "created_at")


@admin.register(GovernmentRecord)
class GovernmentRecordAdmin(admin.ModelAdmin):
    list_display = ("project", "municipality", "submission_type", "current_online_status", "last_checked_date")
    search_fields = ("project__project_number", "government_application_number", "municipality")
    list_filter = ("submission_type", "current_online_status")


@admin.register(MunicipalityActivity)
class MunicipalityActivityAdmin(admin.ModelAdmin):
    list_display = ("project", "municipality", "activity_type", "is_resolved", "recorded_at")
    search_fields = ("project__project_number", "municipality", "details")
    list_filter = ("activity_type", "is_resolved")


@admin.register(PhysicalFileTransfer)
class PhysicalFileTransferAdmin(admin.ModelAdmin):
    list_display = ("project", "file_transferred_from", "file_transferred_to", "current_location", "transfer_date_time", "received_confirmation")
    search_fields = ("project__project_number", "file_transferred_from", "file_transferred_to")
    list_filter = ("current_location", "received_confirmation")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("project", "payment_date", "payment_method", "amount_received", "remaining_balance", "received_by")
    search_fields = ("project__project_number", "receipt_number", "payment_reference")
    list_filter = ("payment_method",)


@admin.register(ProjectComment)
class ProjectCommentAdmin(admin.ModelAdmin):
    list_display = ("project", "commenter", "visibility", "created_at")
    search_fields = ("project__project_number", "comment")
    list_filter = ("visibility",)

