from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class OrganizationCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "organization categories"

    def __str__(self) -> str:
        return self.name


class SystemTemplate(models.Model):
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    category = models.ForeignKey(OrganizationCategory, on_delete=models.PROTECT, related_name="system_templates")
    version = models.CharField(max_length=30, default="1.0")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "-version"]
        constraints = [models.UniqueConstraint(fields=["code", "version"], name="unique_system_template_version")]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class ModuleDefinition(models.Model):
    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_core = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    available_for_custom = models.BooleanField(
        default=False,
        help_text="Whether this catalog module can be selected for a Custom workspace.",
    )
    navigation_label = models.CharField(max_length=120, blank=True)
    navigation_url_name = models.CharField(max_length=120, blank=True)
    navigation_icon = models.CharField(max_length=80, blank=True)
    navigation_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["navigation_order", "name"]

    def __str__(self) -> str:
        return self.name


class ModuleDependency(models.Model):
    module = models.ForeignKey(ModuleDefinition, on_delete=models.CASCADE, related_name="dependencies")
    required_module = models.ForeignKey(ModuleDefinition, on_delete=models.CASCADE, related_name="required_by")
    explanation = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["module", "required_module"], name="unique_module_dependency")]


class ModuleConflict(models.Model):
    module = models.ForeignKey(ModuleDefinition, on_delete=models.CASCADE, related_name="conflicts")
    conflicting_module = models.ForeignKey(ModuleDefinition, on_delete=models.CASCADE, related_name="conflicted_by")
    explanation = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["module", "conflicting_module"], name="unique_module_conflict")]


class TemplateModule(models.Model):
    system_template = models.ForeignKey(SystemTemplate, on_delete=models.CASCADE, related_name="template_modules")
    module = models.ForeignKey(ModuleDefinition, on_delete=models.PROTECT, related_name="template_modules")
    required = models.BooleanField(default=False)
    enabled_by_default = models.BooleanField(default=True)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["system_template", "module"], name="unique_template_module")]


class ModulePermission(models.Model):
    code = models.SlugField(max_length=100, unique=True)
    module = models.ForeignKey(ModuleDefinition, on_delete=models.CASCADE, related_name="permissions")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["module__name", "name"]

    def __str__(self) -> str:
        return self.name


class RoleTemplate(models.Model):
    system_template = models.ForeignKey(SystemTemplate, on_delete=models.CASCADE, related_name="role_templates")
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    permissions = models.ManyToManyField(ModulePermission, through="RoleTemplatePermission", related_name="role_templates")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["system_template", "code"], name="unique_template_role_code")]

    def __str__(self) -> str:
        return self.name


class RoleTemplatePermission(models.Model):
    role_template = models.ForeignKey(RoleTemplate, on_delete=models.CASCADE)
    permission = models.ForeignKey(ModulePermission, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["role_template", "permission"], name="unique_role_template_permission")]


class OrganizationRole(models.Model):
    organization = models.ForeignKey("Company", on_delete=models.CASCADE, related_name="roles")
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=120)
    source_template_role = models.ForeignKey(RoleTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="organization_roles")
    is_active = models.BooleanField(default=True)
    permissions = models.ManyToManyField(ModulePermission, through="OrganizationRolePermission", related_name="organization_roles")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="unique_organization_role_code")]

    def __str__(self) -> str:
        return self.name


class OrganizationRolePermission(models.Model):
    organization_role = models.ForeignKey(OrganizationRole, on_delete=models.CASCADE)
    permission = models.ForeignKey(ModulePermission, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization_role", "permission"], name="unique_organization_role_permission")]


class WorkflowTemplate(models.Model):
    system_template = models.ForeignKey(SystemTemplate, on_delete=models.CASCADE, related_name="workflow_templates")
    module = models.ForeignKey(ModuleDefinition, on_delete=models.PROTECT, related_name="workflow_templates")
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=160)
    version = models.PositiveSmallIntegerField(default=1)
    definition = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "-version"]
        constraints = [models.UniqueConstraint(fields=["system_template", "code", "version"], name="unique_workflow_template_version")]


class TemplateDashboardWidget(models.Model):
    system_template = models.ForeignKey(SystemTemplate, on_delete=models.CASCADE, related_name="dashboard_widgets")
    module = models.ForeignKey(ModuleDefinition, on_delete=models.PROTECT, related_name="dashboard_widgets")
    code = models.SlugField(max_length=80)
    title = models.CharField(max_length=160)
    component_key = models.CharField(max_length=120)
    display_order = models.PositiveSmallIntegerField(default=0)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["display_order", "title"]
        constraints = [models.UniqueConstraint(fields=["system_template", "code"], name="unique_template_dashboard_widget")]


class TemplateNavigationItem(models.Model):
    system_template = models.ForeignKey(SystemTemplate, on_delete=models.CASCADE, related_name="navigation_items")
    module = models.ForeignKey(ModuleDefinition, on_delete=models.PROTECT, related_name="navigation_items")
    label = models.CharField(max_length=120)
    url_name = models.CharField(max_length=120)
    icon = models.CharField(max_length=80, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    required_permission = models.ForeignKey(
        ModulePermission,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="navigation_items",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["system_template", "url_name"],
                name="unique_template_navigation_url",
            )
        ]


class OrganizationModule(models.Model):
    organization = models.ForeignKey("Company", on_delete=models.CASCADE, related_name="enabled_modules")
    module = models.ForeignKey(ModuleDefinition, on_delete=models.PROTECT, related_name="organization_installations")
    is_enabled = models.BooleanField(default=True)
    configuration = models.JSONField(default=dict, blank=True)
    enabled_at = models.DateTimeField(auto_now_add=True)
    enabled_by = models.ForeignKey("User", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "module"], name="unique_organization_module")]


class CustomStartingStructure(models.Model):
    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name


class CustomStructureModule(models.Model):
    starting_structure = models.ForeignKey(CustomStartingStructure, on_delete=models.CASCADE, related_name="structure_modules")
    module = models.ForeignKey(ModuleDefinition, on_delete=models.PROTECT, related_name="custom_structure_modules")
    required = models.BooleanField(default=False)
    enabled_by_default = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["starting_structure", "module"],
                name="unique_custom_structure_module",
            )
        ]


class OrganizationConfiguration(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    organization = models.ForeignKey("Company", on_delete=models.CASCADE, related_name="configuration_versions")
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    starting_structure = models.ForeignKey(CustomStartingStructure, null=True, blank=True, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey("User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_configuration_versions")
    published_by = models.ForeignKey("User", null=True, blank=True, on_delete=models.SET_NULL, related_name="published_configuration_versions")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "version"],
                name="unique_organization_configuration_version",
            )
        ]


class OrganizationTerminology(models.Model):
    organization = models.ForeignKey("Company", on_delete=models.CASCADE, related_name="terminology")
    internal_code = models.SlugField(max_length=80)
    label = models.CharField(max_length=120)
    updated_by = models.ForeignKey("User", null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["internal_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "internal_code"],
                name="unique_organization_terminology",
            )
        ]


class OrganizationBranding(models.Model):
    organization = models.OneToOneField("Company", on_delete=models.CASCADE, related_name="branding")
    primary_color = models.CharField(max_length=20, default="#245a78")
    accent_color = models.CharField(max_length=20, default="#3b82f6")
    report_header = models.CharField(max_length=255, blank=True)
    report_footer = models.CharField(max_length=500, blank=True)
    date_format = models.CharField(max_length=32, default="Y-m-d")
    number_format = models.CharField(max_length=32, default="international")
    updated_at = models.DateTimeField(auto_now=True)


class OrganizationInvitation(models.Model):
    organization = models.ForeignKey("Company", on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    full_name = models.CharField(max_length=255, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    role = models.ForeignKey(OrganizationRole, null=True, blank=True, on_delete=models.SET_NULL, related_name="invitations")
    token_digest = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey("User", null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_organization_invitations")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "email", "accepted_at"])]


class Company(models.Model):
    """A customer tenant managed by the platform administration layer."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120, unique=True)
    legal_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    industry = models.CharField(max_length=120, blank=True)
    registration_number = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    province = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    organization_code = models.SlugField(max_length=80, unique=True, null=True, blank=True)
    category = models.ForeignKey(OrganizationCategory, null=True, blank=True, on_delete=models.PROTECT, related_name="organizations")
    system_template = models.ForeignKey(SystemTemplate, null=True, blank=True, on_delete=models.PROTECT, related_name="organizations")
    applied_template_version = models.CharField(max_length=30, blank=True)
    provisioning_status = models.CharField(max_length=20, default="ready", choices=[
        ("pending", "Pending"), ("provisioning", "Provisioning"), ("ready", "Ready"), ("failed", "Failed")
    ])
    website = models.URLField(blank=True)
    tax_identifier = models.CharField(max_length=80, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    timezone_name = models.CharField(max_length=64, blank=True)
    language_code = models.CharField(max_length=12, blank=True)
    currency_code = models.CharField(max_length=3, default="NPR")
    date_format = models.CharField(max_length=32, default="Y-m-d")
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
    organization_role = models.ForeignKey(OrganizationRole, null=True, blank=True, on_delete=models.SET_NULL, related_name="memberships")
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
