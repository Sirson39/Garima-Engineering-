from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


User = get_user_model()


class AuditTimestampModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(AuditTimestampModel):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)


class OrganizationProfile(AuditTimestampModel):
    company_name = models.CharField(max_length=255, default="Garima Engineering Consultancy")
    short_name = models.CharField(max_length=120, blank=True)
    slogan = models.CharField(max_length=255, blank=True)
    logo = models.ImageField(upload_to="branding/", blank=True, null=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    primary_color = models.CharField(max_length=20, default="#0f5c7a")
    accent_color = models.CharField(max_length=20, default="#d97706")
    default_bs_year = models.CharField(max_length=8, default="2083")
    public_notice = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="updated_branding_profiles",
    )

    class Meta:
        verbose_name = "Organization profile"
        verbose_name_plural = "Organization profile"

    def __str__(self) -> str:
        return self.company_name

    @classmethod
    def load(cls) -> "OrganizationProfile":
        profile, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "company_name": "Garima Engineering Consultancy",
                "default_bs_year": "2083",
            },
        )
        return profile


class AuditLog(AuditTimestampModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=120)
    object_type = models.CharField(max_length=120, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    summary = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["project", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} at {self.created_at:%Y-%m-%d %H:%M}"


class Notification(AuditTimestampModel):
    LEVEL_INFO = "info"
    LEVEL_SUCCESS = "success"
    LEVEL_WARNING = "warning"
    LEVEL_DANGER = "danger"

    LEVEL_CHOICES = [
        (LEVEL_INFO, "Info"),
        (LEVEL_SUCCESS, "Success"),
        (LEVEL_WARNING, "Warning"),
        (LEVEL_DANGER, "Danger"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default=LEVEL_INFO)
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "created_at"])]

    def __str__(self) -> str:
        return self.title

    def mark_read(self) -> None:
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "updated_at"])


class LoginAttempt(AuditTimestampModel):
    identifier = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(blank=True, null=True)
    locked_until = models.DateTimeField(blank=True, null=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_attempts",
    )

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["identifier", "ip_address"])]
        unique_together = ("identifier", "ip_address")

    def __str__(self) -> str:
        return f"{self.identifier} @ {self.ip_address or 'unknown'}"

    def is_locked(self, now=None) -> bool:
        now = now or timezone.now()
        return bool(self.locked_until and self.locked_until > now)

    def register_failure(self, limit: int, window_minutes: int) -> None:
        now = timezone.now()
        if self.last_attempt_at and (now - self.last_attempt_at).total_seconds() > window_minutes * 60:
            self.attempts = 0
            self.locked_until = None
        self.attempts += 1
        self.last_attempt_at = now
        if self.attempts >= limit:
            self.locked_until = now + timedelta(minutes=window_minutes)
        self.save()

    def clear(self) -> None:
        self.attempts = 0
        self.last_attempt_at = timezone.now()
        self.locked_until = None
        self.save(update_fields=["attempts", "last_attempt_at", "locked_until", "updated_at"])
