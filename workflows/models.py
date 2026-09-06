from __future__ import annotations

from django.conf import settings
from django.db import models

from projects.constants import PROJECT_STATUS_CHOICES, WAIT_TYPE_CHOICES


class AuditTimestampModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ServiceType(AuditTimestampModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class NumberingScheme(AuditTimestampModel):
    service_type = models.OneToOneField(ServiceType, on_delete=models.CASCADE, related_name="numbering_scheme")
    prefix = models.CharField(max_length=20, default="GEC")
    service_code = models.CharField(max_length=20)
    year_label = models.CharField(max_length=8, default="2083")
    sequence_width = models.PositiveSmallIntegerField(default=4)
    next_sequence = models.PositiveIntegerField(default=1)
    separator = models.CharField(max_length=5, default="-")
    format_template = models.CharField(
        max_length=255,
        default="{prefix}-{service_code}-{year_label}-{sequence:04d}",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["service_type__name"]

    def __str__(self) -> str:
        return f"{self.service_type.code} numbering"

    def render_number(self, sequence: int) -> str:
        return self.format_template.format(
            prefix=self.prefix,
            service_code=self.service_code,
            year_label=self.year_label,
            sequence=sequence,
        )


class DocumentCategory(AuditTimestampModel):
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    service_type = models.ForeignKey(
        ServiceType,
        on_delete=models.CASCADE,
        related_name="document_categories",
        blank=True,
        null=True,
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        unique_together = ("code", "service_type")

    def __str__(self) -> str:
        return self.name


class WorkflowStageTemplate(AuditTimestampModel):
    service_type = models.ForeignKey(ServiceType, on_delete=models.CASCADE, related_name="workflow_stages")
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    default_status = models.CharField(max_length=64, choices=PROJECT_STATUS_CHOICES, default="New")
    wait_type = models.CharField(max_length=20, choices=WAIT_TYPE_CHOICES, default="internal")
    responsible_role_hint = models.CharField(max_length=120, blank=True)
    due_days_default = models.PositiveIntegerField(default=3)
    requires_document_completion = models.BooleanField(default=True)
    is_start = models.BooleanField(default=False)
    is_terminal = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["service_type__name", "order", "name"]
        unique_together = ("service_type", "code")

    def __str__(self) -> str:
        return f"{self.service_type.code}: {self.name}"


class DocumentTemplate(AuditTimestampModel):
    service_type = models.ForeignKey(ServiceType, on_delete=models.CASCADE, related_name="document_templates")
    category = models.ForeignKey(DocumentCategory, on_delete=models.PROTECT, related_name="document_templates")
    name = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    required = models.BooleanField(default=True)
    allow_exception = models.BooleanField(default=True)
    must_be_seen_original = models.BooleanField(default=True)
    must_be_scanned = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["service_type__name", "order", "name"]
        unique_together = ("service_type", "name")

    def __str__(self) -> str:
        return self.name

