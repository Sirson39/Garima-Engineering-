from __future__ import annotations

import hashlib
import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.models import AuditTimestampModel, SoftDeleteModel
from projects.constants import (
    DOCUMENT_APPROVAL_CHOICES,
    DOCUMENT_CONFIDENTIALITY_CHOICES,
    FILE_LOCATION_CHOICES,
    MUNICIPALITY_ACTIVITY_CHOICES,
    ONLINE_STATUS_CHOICES,
    PAYMENT_METHOD_CHOICES,
    PRIORITY_CHOICES,
    PROJECT_STATUS_CHOICES,
    SUBMISSION_TYPE_CHOICES,
    TASK_PRIORITY_CHOICES,
    TASK_STATUS_CHOICES,
    VISIT_STATUS_CHOICES,
)


User = get_user_model()


def project_document_upload_to(instance, filename: str) -> str:
    token = instance.project.project_number if instance.project_id and instance.project.project_number else "unassigned"
    key = instance.document_key or "documents"
    return f"projects/{token}/documents/{slugify(key)}/{filename}"


def project_scoped_upload_to(instance, filename: str) -> str:
    project = None
    if hasattr(instance, "project") and getattr(instance, "project_id", None):
        project = instance.project
    elif hasattr(instance, "stage_history") and getattr(instance, "stage_history_id", None):
        project = instance.stage_history.project
    elif hasattr(instance, "task") and getattr(instance, "task_id", None):
        project = instance.task.project
    elif hasattr(instance, "site_visit") and getattr(instance, "site_visit_id", None):
        project = instance.site_visit.project
    project_number = project.project_number if project else "unassigned"
    return f"projects/{project_number}/attachments/{filename}"


def site_visit_upload_to(instance, filename: str) -> str:
    project_number = instance.site_visit.project.project_number if instance.site_visit_id else "unassigned"
    return f"projects/{project_number}/site-visits/{filename}"


def make_public_token() -> str:
    return uuid.uuid4().hex[:16]


class Client(SoftDeleteModel):
    full_name = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    citizenship_number = models.CharField(max_length=80, blank=True)
    permanent_address = models.TextField(blank=True)
    current_address = models.TextField(blank=True)
    province = models.CharField(max_length=80, blank=True)
    district = models.CharField(max_length=120, blank=True)
    municipality = models.CharField(max_length=120, blank=True)
    ward_number = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_clients",
    )

    class Meta:
        ordering = ["full_name"]
        indexes = [models.Index(fields=["full_name", "mobile_number", "citizenship_number"])]

    def __str__(self) -> str:
        return self.full_name


class Project(SoftDeleteModel):
    public_token = models.CharField(max_length=32, unique=True, default=make_public_token, editable=False)
    project_number = models.CharField(max_length=50, unique=True, blank=True)
    service_type = models.ForeignKey("workflows.ServiceType", on_delete=models.PROTECT, related_name="projects")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="projects")
    registration_date = models.DateField(default=timezone.localdate)
    registration_date_bs = models.CharField(max_length=32, blank=True)
    property_location = models.CharField(max_length=255, blank=True)
    kitta_number = models.CharField(max_length=80, blank=True)
    sheet_number = models.CharField(max_length=80, blank=True)
    land_area = models.CharField(max_length=120, blank=True)
    province = models.CharField(max_length=80, blank=True)
    district = models.CharField(max_length=120, blank=True)
    municipality = models.CharField(max_length=120, blank=True)
    ward_number = models.CharField(max_length=20, blank=True)
    government_application_number = models.CharField(max_length=120, blank=True)
    project_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    net_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_received = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    remaining_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    expected_completion_date = models.DateField(blank=True, null=True)
    expected_completion_date_bs = models.CharField(max_length=32, blank=True)
    current_stage_template = models.ForeignKey(
        "workflows.WorkflowStageTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_projects",
    )
    current_stage_record = models.ForeignKey(
        "ProjectStageHistory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    current_responsible_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_projects",
    )
    current_file_holder = models.CharField(max_length=255, blank=True)
    current_file_location = models.CharField(
        max_length=120,
        choices=FILE_LOCATION_CHOICES,
        default="Reception",
    )
    last_file_handover_at = models.DateTimeField(blank=True, null=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="Normal")
    status = models.CharField(max_length=64, choices=PROJECT_STATUS_CHOICES, default="New")
    internal_remarks = models.TextField(blank=True)
    client_visible_remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_projects",
    )
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="project_memberships")
    closed_at = models.DateTimeField(blank=True, null=True)
    archived_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["project_number"]),
            models.Index(fields=["status", "service_type"]),
            models.Index(fields=["municipality", "ward_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.project_number} - {self.client.full_name}"

    def get_absolute_url(self):
        return reverse("project-detail", kwargs={"pk": self.pk})

    def recalculate_financials(self, save: bool = True):
        total_received = self.payments.filter(is_deleted=False).aggregate(total=Sum("amount_received"))["total"] or Decimal("0.00")
        self.amount_received = total_received
        self.net_fee = (self.project_fee or Decimal("0.00")) - (self.discount or Decimal("0.00"))
        self.remaining_balance = max(self.net_fee - total_received, Decimal("0.00"))
        if save:
            self.save(update_fields=["amount_received", "net_fee", "remaining_balance", "updated_at"])
        return self.remaining_balance

    @property
    def progress_percent(self) -> int:
        if not self.current_stage_template or not self.service_type.workflow_stages.exists():
            return 0
        total_stages = self.service_type.workflow_stages.count()
        current_order = max(self.current_stage_template.order, 1)
        return min(100, int((current_order / total_stages) * 100))

    def save(self, *args, **kwargs):
        if not self.project_number and self.service_type_id:
            from workflows.services import allocate_project_number

            self.project_number = allocate_project_number(self.service_type)
        if not self.net_fee:
            self.net_fee = (self.project_fee or Decimal("0.00")) - (self.discount or Decimal("0.00"))
        if not self.remaining_balance:
            self.remaining_balance = max(self.net_fee - (self.amount_received or Decimal("0.00")), Decimal("0.00"))
        super().save(*args, **kwargs)


class DocumentChecklistItem(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="checklist_items")
    template = models.ForeignKey("workflows.DocumentTemplate", on_delete=models.PROTECT, related_name="project_items")
    category = models.ForeignKey("workflows.DocumentCategory", on_delete=models.PROTECT, related_name="checklist_items")
    name = models.CharField(max_length=255)
    required = models.BooleanField(default=True)
    received = models.BooleanField(default=False)
    original_seen = models.BooleanField(default=False)
    scanned = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    received_date = models.DateField(blank=True, null=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_checklist_items",
    )
    uploaded_document = models.ForeignKey(
        "ProjectDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_checklist_items",
    )
    document_expiry_date = models.DateField(blank=True, null=True)
    remarks = models.TextField(blank=True)
    exception_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_exceptions",
    )
    exception_approved_at = models.DateTimeField(blank=True, null=True)
    exception_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["project__project_number", "template__order", "name"]
        unique_together = ("project", "template")

    def __str__(self) -> str:
        return f"{self.project.project_number} - {self.name}"

    def save(self, *args, **kwargs):
        if self.template_id and self._state.adding:
            self.name = self.name or self.template.name
            self.category_id = self.category_id or self.template.category_id
            self.required = self.template.required
        super().save(*args, **kwargs)

    @property
    def is_missing(self) -> bool:
        return self.required and not self.received and self.exception_approved_by_id is None


class ProjectDocument(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    category = models.ForeignKey("workflows.DocumentCategory", on_delete=models.PROTECT, related_name="documents")
    checklist_item = models.ForeignKey(
        DocumentChecklistItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    document_key = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    revision_number = models.PositiveIntegerField(default=1)
    file = models.FileField(upload_to=project_document_upload_to)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_project_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checked_project_documents",
    )
    approval_status = models.CharField(max_length=32, choices=DOCUMENT_APPROVAL_CHOICES, default="Pending")
    file_size = models.PositiveBigIntegerField(default=0)
    file_checksum = models.CharField(max_length=128, blank=True)
    confidentiality_level = models.CharField(
        max_length=32,
        choices=DOCUMENT_CONFIDENTIALITY_CHOICES,
        default="Internal",
    )
    remarks = models.TextField(blank=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ["-uploaded_at"]
        unique_together = ("project", "document_key", "revision_number")
        indexes = [
            models.Index(fields=["project", "category", "is_current"]),
            models.Index(fields=["project", "document_key"]),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} v{self.revision_number}"

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            self.original_filename = os.path.basename(self.file.name)
        if self.file and not self.display_name:
            self.display_name = self.original_filename
        if self.file and not self.file_checksum:
            digest = hashlib.sha256()
            self.file.seek(0)
            for chunk in self.file.chunks():
                digest.update(chunk)
            self.file_checksum = digest.hexdigest()
            self.file.seek(0)
            self.file_size = getattr(self.file, "size", self.file_size)
        super().save(*args, **kwargs)


class ProjectStageHistory(AuditTimestampModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="stage_histories")
    stage_template = models.ForeignKey("workflows.WorkflowStageTemplate", on_delete=models.PROTECT)
    stage_name = models.CharField(max_length=255)
    stage_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=64, choices=PROJECT_STATUS_CHOICES, default="New")
    assigned_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_stage_histories",
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(blank=True, null=True)
    due_date = models.DateField(blank=True, null=True)
    internal_comments = models.TextField(blank=True)
    returned_for_correction = models.BooleanField(default=False)
    correction_reason = models.TextField(blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_stage_histories",
    )
    handover_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handover_stage_histories",
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.project.project_number} - {self.stage_name}"

    def save(self, *args, **kwargs):
        if self.stage_template_id:
            self.stage_name = self.stage_name or self.stage_template.name
            self.stage_order = self.stage_order or self.stage_template.order
            if self._state.adding and self.status == "New":
                self.status = self.stage_template.default_status
        super().save(*args, **kwargs)

    @property
    def days_at_stage(self) -> int:
        end = self.completed_at or timezone.now()
        return max(0, (end - self.started_at).days)


class StageAttachment(AuditTimestampModel):
    stage_history = models.ForeignKey(ProjectStageHistory, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=project_scoped_upload_to)
    original_filename = models.CharField(max_length=255, blank=True)
    note = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            self.original_filename = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.original_filename or self.file.name


class Task(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=255)
    related_stage = models.ForeignKey(
        ProjectStageHistory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    assigned_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks_assigned",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks_created",
    )
    priority = models.CharField(max_length=20, choices=TASK_PRIORITY_CHOICES, default="Normal")
    start_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=TASK_STATUS_CHOICES, default="New")
    comments = models.TextField(blank=True)
    completion_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["project", "status", "due_date"])]

    def __str__(self) -> str:
        return self.title


class TaskAttachment(AuditTimestampModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=project_scoped_upload_to)
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            self.original_filename = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.original_filename or self.file.name


class SiteVisit(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="site_visits")
    assigned_engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_visits_assigned",
    )
    scheduled_date = models.DateField(blank=True, null=True)
    scheduled_date_bs = models.CharField(max_length=32, blank=True)
    actual_visit_date = models.DateField(blank=True, null=True)
    actual_visit_date_bs = models.CharField(max_length=32, blank=True)
    site_address = models.CharField(max_length=255, blank=True)
    contact_person = models.CharField(max_length=255, blank=True)
    contact_number = models.CharField(max_length=30, blank=True)
    gps_coordinates = models.CharField(max_length=120, blank=True)
    measurements = models.TextField(blank=True)
    site_condition = models.TextField(blank=True)
    building_information = models.TextField(blank=True)
    engineer_observations = models.TextField(blank=True)
    follow_up_required = models.BooleanField(default=False)
    visit_status = models.CharField(max_length=32, choices=VISIT_STATUS_CHOICES, default="Scheduled")
    engineer_confirmation = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_visits_recorded",
    )

    class Meta:
        ordering = ["-scheduled_date", "-updated_at"]

    def __str__(self) -> str:
        return f"Site visit for {self.project.project_number}"


class SiteVisitAttachment(AuditTimestampModel):
    site_visit = models.ForeignKey(SiteVisit, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=site_visit_upload_to)
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            self.original_filename = os.path.basename(self.file.name)
        super().save(*args, **kwargs)


class GovernmentRecord(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="government_records")
    municipality = models.CharField(max_length=120, blank=True)
    government_application_number = models.CharField(max_length=120, blank=True)
    submission_type = models.CharField(max_length=40, choices=SUBMISSION_TYPE_CHOICES, default="Initial")
    submission_date = models.DateField(blank=True, null=True)
    submission_date_bs = models.CharField(max_length=32, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="government_submissions",
    )
    current_online_status = models.CharField(max_length=40, choices=ONLINE_STATUS_CHOICES, default="Not Started")
    receipt_or_screenshot = models.FileField(upload_to=project_scoped_upload_to, blank=True, null=True)
    ward_document_upload_date = models.DateField(blank=True, null=True)
    ward_document_upload_date_bs = models.CharField(max_length=32, blank=True)
    structural_document_upload_date = models.DateField(blank=True, null=True)
    structural_document_upload_date_bs = models.CharField(max_length=32, blank=True)
    asthayi_status = models.CharField(max_length=80, blank=True)
    isthayi_status = models.CharField(max_length=80, blank=True)
    government_remarks = models.TextField(blank=True)
    rejection_or_correction_reason = models.TextField(blank=True)
    resubmission_date = models.DateField(blank=True, null=True)
    resubmission_date_bs = models.CharField(max_length=32, blank=True)
    last_checked_date = models.DateField(blank=True, null=True)
    last_checked_date_bs = models.CharField(max_length=32, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="government_records_recorded",
    )

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Government record for {self.project.project_number}"


class MunicipalityActivity(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="municipality_activities")
    municipality = models.CharField(max_length=120, blank=True)
    activity_type = models.CharField(max_length=40, choices=MUNICIPALITY_ACTIVITY_CHOICES, default="Comment")
    details = models.TextField()
    attachment = models.FileField(upload_to=project_scoped_upload_to, blank=True, null=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="municipality_activities_recorded",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(blank=True, null=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self) -> str:
        return f"{self.activity_type} - {self.project.project_number}"


class PhysicalFileTransfer(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="file_transfers")
    file_transferred_from = models.CharField(max_length=255)
    file_transferred_to = models.CharField(max_length=255)
    current_location = models.CharField(max_length=120, choices=FILE_LOCATION_CHOICES)
    transfer_date_time = models.DateTimeField(default=timezone.now)
    purpose = models.CharField(max_length=255)
    expected_return_date = models.DateField(blank=True, null=True)
    received_confirmation = models.BooleanField(default=False)
    actual_return_date = models.DateField(blank=True, null=True)
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="file_transfers_recorded",
    )

    class Meta:
        ordering = ["-transfer_date_time"]

    def __str__(self) -> str:
        return f"{self.project.project_number}: {self.file_transferred_from} -> {self.file_transferred_to}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        project = self.project
        if project:
            project.current_file_holder = self.file_transferred_to
            project.current_file_location = self.current_location
            project.last_file_handover_at = self.transfer_date_time
            project.save(update_fields=["current_file_holder", "current_file_location", "last_file_handover_at", "updated_at"])


class Payment(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="payments")
    agreed_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    net_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_received = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    remaining_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    payment_date = models.DateField(blank=True, null=True)
    payment_date_bs = models.CharField(max_length=32, blank=True)
    payment_method = models.CharField(max_length=40, choices=PAYMENT_METHOD_CHOICES, default="Cash")
    receipt_number = models.CharField(max_length=120, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_received",
    )
    payment_proof = models.FileField(upload_to=project_scoped_upload_to, blank=True, null=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-payment_date", "-updated_at"]

    def __str__(self) -> str:
        return f"Payment for {self.project.project_number}"

    def save(self, *args, **kwargs):
        if not self.net_fee:
            self.net_fee = (self.agreed_fee or Decimal("0.00")) - (self.discount or Decimal("0.00"))
        if not self.remaining_balance:
            self.remaining_balance = max(self.net_fee - (self.amount_received or Decimal("0.00")), Decimal("0.00"))
        super().save(*args, **kwargs)
        self.project.recalculate_financials(save=True)


class ProjectComment(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="comments")
    commenter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    visibility = models.CharField(
        max_length=20,
        choices=[("internal", "Internal"), ("client", "Client visible")],
        default="internal",
    )
    comment = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Comment on {self.project.project_number}"
