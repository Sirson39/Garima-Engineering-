from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": "form-control login-input",
                "autocomplete": "username",
                "placeholder": "Enter your username",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "form-control login-input login-password-input",
                "autocomplete": "current-password",
                "placeholder": "Enter your password",
            }
        )

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


class UnifiedAuthenticationForm(forms.Form):
    error_messages = {"invalid_login": "The email address or password is incorrect."}

    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Enter your password"}))

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email", "").strip()
        password = cleaned_data.get("password")
        if not email or not password:
            return cleaned_data
        user = User.objects.filter(email__iexact=email).first()
        authenticated_user = user and authenticate(self.request, username=user.username, password=password)
        if authenticated_user is None:
            raise ValidationError(self.error_messages["invalid_login"])
        self.user_cache = authenticated_user
        return cleaned_data

    def get_user(self):
        return self.user_cache


class OrganizationUserForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(label="User email")
    role = forms.ChoiceField(label="Organization role", choices=[("engineer", "Engineer"), ("staff", "Staff")])
    initial_password = forms.CharField(label="Temporary first-login password", min_length=8, widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already in use.")
        return email

    def clean_initial_password(self):
        password = self.cleaned_data["initial_password"]
        validate_password(password)
        return password


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
            "company",
            "company_role",
            "is_platform_admin",
            "groups",
        ]
        widgets = {
            "groups": forms.SelectMultiple(attrs={"size": 8}),
        }
