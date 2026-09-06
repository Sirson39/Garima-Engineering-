from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.conf import settings
from django.core.exceptions import ValidationError

from accounts.models import User
from core.forms import BootstrapFormMixin
from core.models import LoginAttempt


class GarimaAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "locked": "This account is temporarily locked because of repeated failed login attempts.",
    }

    def clean(self):
        username = self.data.get(self.add_prefix("username"), "").strip()
        ip_address = self.request.META.get("REMOTE_ADDR", "")
        attempt, _ = LoginAttempt.objects.get_or_create(identifier=username or "unknown", ip_address=ip_address or None)
        if attempt.is_locked():
            raise ValidationError(self.error_messages["locked"], code="locked")
        try:
            cleaned_data = super().clean()
        except ValidationError:
            attempt.register_failure(
                limit=settings.LOGIN_ATTEMPT_LIMIT,
                window_minutes=settings.LOGIN_ATTEMPT_WINDOW_MINUTES,
            )
            raise
        attempt.clear()
        return cleaned_data


class UserForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "nepali_name",
            "email",
            "phone",
            "employee_code",
            "job_title",
            "avatar",
            "is_active",
            "is_staff",
            "groups",
        ]
        widgets = {
            "groups": forms.SelectMultiple(attrs={"size": 8}),
        }

