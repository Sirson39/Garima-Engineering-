from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from accounts.models import OrganizationMembership
from core.models import AuditTimestampModel


class BillingMethod(models.TextChoices):
    FIXED = "fixed", "Fixed Price"
    HOURLY = "hourly", "Hourly / Time and Materials"
    MILESTONE = "milestone", "Milestone"
    RETAINER = "retainer", "Retainer"
    INTERNAL = "internal", "Non-billable / Internal"


def engagement_number():
    return f"ENG-{uuid4().hex[:12].upper()}"


def rate_field():
    return models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                               validators=[MinValueValidator(Decimal("0"))])


def validate_staff(organization_id, user_id, field):
    if user_id and not OrganizationMembership.objects.filter(
        organization_id=organization_id, user_id=user_id, is_active=True, user__is_active=True,
    ).exists():
        raise ValidationError({field: "Choose an active member of this organization."})


class ScopedRecord(AuditTimestampModel):
    organization = models.ForeignKey("accounts.Company", on_delete=models.PROTECT)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProfessionalSettings(ScopedRecord):
    organization = models.OneToOneField("accounts.Company", on_delete=models.PROTECT,
                                      related_name="professional_settings")
    default_rate = rate_field()

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(default_rate__gte=0) | models.Q(default_rate__isnull=True),
                                              name="ps_settings_rate_nonnegative")]


class ProfessionalService(ScopedRecord):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40)
    description = models.TextField(blank=True)
    default_duration_days = models.PositiveIntegerField(null=True, blank=True)
    default_billing_method = models.CharField(max_length=20, choices=BillingMethod.choices, default=BillingMethod.FIXED)
    default_rate = rate_field()
    default_deliverables = models.TextField(blank=True)
    responsible_department = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="ps_unique_service_code"),
            models.CheckConstraint(condition=models.Q(default_rate__gte=0) | models.Q(default_rate__isnull=True), name="ps_service_rate_nonnegative"),
        ]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self):
        return f"{self.code} - {self.name}"


class ProfessionalClient(ScopedRecord):
    class Status(models.TextChoices):
        PROSPECTIVE = "prospective", "Prospective"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    client_type = models.CharField(max_length=80, blank=True)
    contact_person = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    industry = models.CharField(max_length=120, blank=True)
    account_manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name="ps_clients")
    services_used = models.ManyToManyField(ProfessionalService, blank=True, related_name="clients")
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROSPECTIVE)
    billing_rate = rate_field()

    class Meta:
        ordering = ["name", "pk"]
        indexes = [models.Index(fields=["organization", "status"])]
        constraints = [models.CheckConstraint(condition=models.Q(billing_rate__gte=0) | models.Q(billing_rate__isnull=True), name="ps_client_rate_nonnegative")]

    def clean(self):
        super().clean()
        validate_staff(self.organization_id, self.account_manager_id, "account_manager")

    def __str__(self):
        return self.name


class Engagement(ScopedRecord):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On Hold"
        AWAITING_CLIENT = "awaiting_client", "Awaiting Client"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        ARCHIVED = "archived", "Archived"

    number = models.CharField(max_length=50, default=engagement_number)
    client = models.ForeignKey(ProfessionalClient, on_delete=models.PROTECT, related_name="engagements")
    service = models.ForeignKey(ProfessionalService, on_delete=models.PROTECT, related_name="engagements")
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    account_manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name="ps_accounts")
    engagement_manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                           related_name="ps_managed_engagements")
    assigned_team = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="ps_engagements")
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    billing_method = models.CharField(max_length=20, choices=BillingMethod.choices, default=BillingMethod.FIXED)
    contract_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                          validators=[MinValueValidator(Decimal("0"))])
    billing_rate = rate_field()
    progress = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ["-updated_at", "pk"]
        indexes = [models.Index(fields=["organization", "status"]), models.Index(fields=["organization", "due_date"])]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="ps_unique_engagement_number"),
            models.CheckConstraint(condition=models.Q(progress__lte=100), name="ps_progress_at_most_100"),
            models.CheckConstraint(condition=models.Q(due_date__gte=models.F("start_date")) | models.Q(start_date__isnull=True) | models.Q(due_date__isnull=True), name="ps_engagement_date_order"),
            models.CheckConstraint(condition=models.Q(billing_rate__gte=0) | models.Q(billing_rate__isnull=True), name="ps_engagement_rate_nonnegative"),
            models.CheckConstraint(condition=models.Q(contract_amount__gte=0) | models.Q(contract_amount__isnull=True), name="ps_contract_nonnegative"),
        ]

    def clean(self):
        super().clean()
        for field in ("client", "service"):
            if getattr(self, f"{field}_id") and getattr(self, field).organization_id != self.organization_id:
                raise ValidationError({field: "Choose a record from this organization."})
        for field in ("account_manager", "engagement_manager"):
            validate_staff(self.organization_id, getattr(self, f"{field}_id"), field)
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValidationError({"due_date": "Due date must be on or after the start date."})

    @property
    def effective_rate(self):
        if self.billing_method == BillingMethod.INTERNAL:
            return Decimal("0.00")
        for rate in (self.billing_rate, self.client.billing_rate, self.service.default_rate):
            if rate is not None:
                return rate
        return ProfessionalSettings.objects.filter(organization_id=self.organization_id).values_list("default_rate", flat=True).first()

    def __str__(self):
        return f"{self.number} - {self.title}"
