from __future__ import annotations

import os

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


def valuation_document_upload_to(instance, filename):
    organization_code = instance.request.organization.organization_code or instance.request.organization.slug
    return f"valuations/{organization_code}/{instance.request.reference_number}/{filename}"


class ValuationBank(models.Model):
    organization = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="valuation_banks")
    name = models.CharField(max_length=180)
    branch = models.CharField(max_length=180, blank=True)
    contact_name = models.CharField(max_length=160, blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "branch"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name", "branch"], name="unique_valuation_bank_branch")
        ]

    def __str__(self):
        return f"{self.name}{' - ' + self.branch if self.branch else ''}"


class ValuationRequest(models.Model):
    STATUS_REQUEST_RECEIVED = "request_received"
    STATUS_DOCUMENTS_PENDING = "documents_pending"
    STATUS_DOCUMENTS_VERIFIED = "documents_verified"
    STATUS_SITE_VISIT_SCHEDULED = "site_visit_scheduled"
    STATUS_SITE_INSPECTION_COMPLETED = "site_inspection_completed"
    STATUS_VALUATION_DRAFTED = "valuation_drafted"
    STATUS_INTERNAL_REVIEW = "internal_review"
    STATUS_CORRECTION_REQUIRED = "correction_required"
    STATUS_APPROVED = "approved"
    STATUS_REPORT_ISSUED = "report_issued"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_REQUEST_RECEIVED, "Request received"),
        (STATUS_DOCUMENTS_PENDING, "Documents pending"),
        (STATUS_DOCUMENTS_VERIFIED, "Documents verified"),
        (STATUS_SITE_VISIT_SCHEDULED, "Site visit scheduled"),
        (STATUS_SITE_INSPECTION_COMPLETED, "Site inspection completed"),
        (STATUS_VALUATION_DRAFTED, "Valuation drafted"),
        (STATUS_INTERNAL_REVIEW, "Internal review"),
        (STATUS_CORRECTION_REQUIRED, "Correction required"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REPORT_ISSUED, "Report issued"),
        (STATUS_ARCHIVED, "Archived"),
    ]
    PRIORITY_CHOICES = [("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")]

    organization = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="valuation_requests")
    reference_number = models.CharField(max_length=80)
    request_date = models.DateField()
    bank = models.ForeignKey(ValuationBank, null=True, blank=True, on_delete=models.PROTECT, related_name="valuation_requests")
    bank_branch = models.CharField(max_length=180, blank=True)
    bank_reference_number = models.CharField(max_length=120, blank=True)
    borrower_name = models.CharField(max_length=255)
    property_owner_name = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=40, blank=True)
    valuation_purpose = models.CharField(max_length=255)
    assigned_engineer = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="valuation_requests_as_engineer")
    assigned_site_inspector = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="valuation_requests_as_inspector")
    required_completion_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="normal")
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default=STATUS_REQUEST_RECEIVED)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_valuation_requests")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "reference_number"], name="unique_valuation_reference")]
        indexes = [models.Index(fields=["organization", "status", "request_date"])]

    def clean(self):
        for field_name in ("assigned_engineer", "assigned_site_inspector"):
            user = getattr(self, field_name)
            if user and user.company_id not in {None, self.organization_id}:
                raise ValidationError({field_name: "The assigned user must belong to this organization."})
        if self.bank_id and self.bank.organization_id != self.organization_id:
            raise ValidationError({"bank": "The bank must belong to this organization."})

    def __str__(self):
        return f"{self.reference_number} - {self.borrower_name}"

    def get_absolute_url(self):
        return reverse("valuation-request-detail", kwargs={"pk": self.pk})


class ValuationDocumentChecklist(models.Model):
    STATUS_REQUIRED = "required"
    STATUS_RECEIVED = "received"
    STATUS_VERIFIED = "verified"
    STATUS_NOT_APPLICABLE = "not_applicable"
    STATUS_EXPIRED = "expired"
    STATUS_CORRECTION_REQUIRED = "correction_required"
    STATUS_CHOICES = [
        (STATUS_REQUIRED, "Required"),
        (STATUS_RECEIVED, "Received"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_NOT_APPLICABLE, "Not applicable"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CORRECTION_REQUIRED, "Correction required"),
    ]

    request = models.ForeignKey(ValuationRequest, on_delete=models.CASCADE, related_name="document_checklist")
    document_type = models.CharField(max_length=180)
    is_required = models.BooleanField(default=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_REQUIRED)
    file = models.FileField(upload_to=valuation_document_upload_to, blank=True, null=True)
    received_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_valuation_documents")
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document_type"]
        constraints = [models.UniqueConstraint(fields=["request", "document_type"], name="unique_valuation_document_type")]

    def save(self, *args, **kwargs):
        if self.file and not self.file.name:
            self.file.name = os.path.basename(self.file.name)
        super().save(*args, **kwargs)


class ValuationReviewComment(models.Model):
    request = models.ForeignKey(ValuationRequest, on_delete=models.CASCADE, related_name="review_comments")
    author = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="valuation_review_comments")
    comment = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ValuationActivity(models.Model):
    request = models.ForeignKey(ValuationRequest, on_delete=models.CASCADE, related_name="activities")
    actor = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="valuation_activities")
    action = models.CharField(max_length=80)
    from_status = models.CharField(max_length=40, blank=True)
    to_status = models.CharField(max_length=40, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
