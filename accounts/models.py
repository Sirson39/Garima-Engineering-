from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class Company(models.Model):
    """A customer tenant managed by the platform administration layer."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120, unique=True)
    legal_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to="company-logos/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "User",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_companies",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class OrganizationMembership(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_ENGINEER = "engineer"
    ROLE_STAFF = "staff"
    ROLE_CHOICES = [(ROLE_ADMIN, "Admin"), (ROLE_ENGINEER, "Engineer"), (ROLE_STAFF, "Staff")]

    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="organization_memberships")
    organization = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "organization"], name="unique_active_org_membership")]
        ordering = ["organization__name"]


class PlatformRole(models.Model):
    ROLE_SUPER_ADMIN = "super_admin"
    ROLE_CHOICES = [(ROLE_SUPER_ADMIN, "Super Admin")]

    user = models.OneToOneField("User", on_delete=models.CASCADE, related_name="platform_role")
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default=ROLE_SUPER_ADMIN)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class User(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_ENGINEER = "engineer"
    ROLE_VALUATOR = "valuator"
    ROLE_STAFF = "staff"
    COMPANY_ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_ENGINEER, "Engineer"),
        (ROLE_VALUATOR, "Valuator"),
        (ROLE_STAFF, "Staff"),
    ]

    employee_code = models.CharField(max_length=50, blank=True, unique=True, null=True)
    phone = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    nepali_name = models.CharField(max_length=255, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    notes = models.TextField(blank=True)
    company = models.ForeignKey(
        Company,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    company_role = models.CharField(max_length=20, choices=COMPANY_ROLE_CHOICES, default=ROLE_ENGINEER)
    is_platform_admin = models.BooleanField(
        default=False,
        help_text="Allows access to platform-wide company administration. Keep this separate from company roles.",
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="Require a private password to be set after a Super Admin provisions this account.",
    )

    class Meta:
        ordering = ["first_name", "last_name", "username"]

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username
