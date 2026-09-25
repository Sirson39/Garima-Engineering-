from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models


class OfficeDepartment(models.Model):
    organization = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="office_departments")
    name = models.CharField(max_length=160)
    code = models.SlugField(max_length=50)
    description = models.TextField(blank=True)
    department_head = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="headed_office_departments",
    )
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="child_departments")
    cost_centre = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="unique_office_department_code"),
            models.UniqueConstraint(fields=["organization", "name"], name="unique_office_department_name"),
        ]

    def clean(self):
        if self.parent_id == self.pk:
            raise ValidationError({"parent": "A department cannot be its own parent."})
        ancestor = self.parent
        seen = set()
        while ancestor:
            if ancestor.pk in seen or ancestor.pk == self.pk:
                raise ValidationError({"parent": "Department hierarchy cannot contain a cycle."})
            seen.add(ancestor.pk)
            ancestor = ancestor.parent

        if self.department_head_id and self.department_head.company_id not in {None, self.organization_id}:
            raise ValidationError({"department_head": "The department head must belong to this organization."})

    def __str__(self):
        return self.name


class OfficeStaffProfile(models.Model):
    EMPLOYMENT_ACTIVE = "active"
    EMPLOYMENT_ON_LEAVE = "on_leave"
    EMPLOYMENT_SUSPENDED = "suspended"
    EMPLOYMENT_RESIGNED = "resigned"
    EMPLOYMENT_TERMINATED = "terminated"
    EMPLOYMENT_ARCHIVED = "archived"
    EMPLOYMENT_STATUS_CHOICES = [
        (EMPLOYMENT_ACTIVE, "Active"),
        (EMPLOYMENT_ON_LEAVE, "On Leave"),
        (EMPLOYMENT_SUSPENDED, "Suspended"),
        (EMPLOYMENT_RESIGNED, "Resigned"),
        (EMPLOYMENT_TERMINATED, "Terminated"),
        (EMPLOYMENT_ARCHIVED, "Archived"),
    ]

    organization = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="office_staff_profiles")
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="office_staff_profiles")
    employee_id = models.CharField(max_length=80)
    department = models.ForeignKey(OfficeDepartment, null=True, blank=True, on_delete=models.SET_NULL, related_name="staff_profiles")
    manager = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports")
    employment_type = models.CharField(max_length=80, blank=True)
    joining_date = models.DateField(null=True, blank=True)
    work_location = models.CharField(max_length=160, blank=True)
    emergency_contact_name = models.CharField(max_length=160, blank=True)
    emergency_contact_phone = models.CharField(max_length=40, blank=True)
    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_STATUS_CHOICES, default=EMPLOYMENT_ACTIVE)
    account_status = models.CharField(max_length=20, choices=[("active", "Active"), ("suspended", "Suspended"), ("archived", "Archived")], default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_id"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="unique_office_staff_user"),
            models.UniqueConstraint(fields=["organization", "employee_id"], name="unique_office_employee_id"),
        ]
        indexes = [models.Index(fields=["organization", "employment_status"])]

    def clean(self):
        if self.user_id and self.user.company_id not in {None, self.organization_id}:
            raise ValidationError({"user": "The staff member must belong to this organization."})
        if self.department_id and self.department.organization_id != self.organization_id:
            raise ValidationError({"department": "The department must belong to this organization."})
        if self.manager_id and self.manager.organization_id != self.organization_id:
            raise ValidationError({"manager": "The manager must belong to this organization."})
        if self.manager_id == self.pk:
            raise ValidationError({"manager": "A staff member cannot manage themselves."})

    @property
    def full_name(self):
        return self.user.display_name

    @property
    def official_email(self):
        return self.user.email

    def __str__(self):
        return f"{self.employee_id} - {self.full_name}"
