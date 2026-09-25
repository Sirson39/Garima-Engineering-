from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import SoftDeleteModel


class ConstructionProject(SoftDeleteModel):
    STATUS_PLANNING = "planning"
    STATUS_PRECONSTRUCTION = "preconstruction"
    STATUS_ACTIVE = "active"
    STATUS_ON_HOLD = "on_hold"
    STATUS_SUBSTANTIALLY_COMPLETE = "substantially_complete"
    STATUS_COMPLETED = "completed"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_PLANNING, "Planning"),
        (STATUS_PRECONSTRUCTION, "Preconstruction"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_ON_HOLD, "On hold"),
        (STATUS_SUBSTANTIALLY_COMPLETE, "Substantially complete"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    organization = models.ForeignKey("accounts.Company", on_delete=models.PROTECT, related_name="construction_projects")
    project_number = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    client_name = models.CharField(max_length=255, blank=True)
    project_type = models.CharField(max_length=120, blank=True)
    contract_type = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    scope = models.TextField(blank=True)
    address = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    expected_completion_date = models.DateField(null=True, blank=True)
    actual_completion_date = models.DateField(null=True, blank=True)
    contract_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency_code = models.CharField(max_length=3, default="NPR")
    project_manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="managed_construction_projects")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PLANNING)
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_construction_projects")

    class Meta:
        ordering = ["-updated_at", "project_number"]
        constraints = [models.UniqueConstraint(fields=["organization", "project_number"], name="unique_construction_project_number")]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return f"{self.project_number} - {self.name}"


class ConstructionParticipant(SoftDeleteModel):
    PARTICIPANT_CHOICES = [
        ("client", "Client"),
        ("consultant", "Consultant"),
        ("architect", "Architect"),
        ("engineer", "Engineer"),
        ("contractor", "General contractor"),
        ("subcontractor", "Subcontractor"),
        ("supplier", "Supplier"),
    ]

    project = models.ForeignKey(ConstructionProject, on_delete=models.CASCADE, related_name="participants")
    participant_type = models.CharField(max_length=32, choices=PARTICIPANT_CHOICES)
    company_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["company_name"]


class ConstructionProjectMember(models.Model):
    project = models.ForeignKey(ConstructionProject, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="construction_project_memberships")
    project_role = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="unique_construction_project_member")]


class ConstructionLocation(SoftDeleteModel):
    LOCATION_CHOICES = [(value, value.replace("_", " ").title()) for value in ("site", "building", "floor", "zone", "room")]

    project = models.ForeignKey(ConstructionProject, on_delete=models.CASCADE, related_name="locations")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    location_type = models.CharField(max_length=20, choices=LOCATION_CHOICES)
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["location_type", "name"]

    def __str__(self) -> str:
        return self.name
