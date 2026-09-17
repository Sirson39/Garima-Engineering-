from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

from accounts.models import Company, User
from accounts.forms import GarimaAuthenticationForm
from core.forms import BootstrapFormMixin


class CompanyForm(BootstrapFormMixin, forms.ModelForm):
    admin_email = forms.EmailField(label="Admin email")
    initial_password = forms.CharField(
        label="Temporary first-login password",
        min_length=8,
        widget=forms.PasswordInput,
        help_text="This password is used only for the first login. Each user must replace it.",
    )

    class Meta:
        model = Company
        fields = ["name", "legal_name", "slug", "email", "phone", "address", "logo", "is_active"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Organization name"
        self.fields["legal_name"].label = "Legal organization name"
        if self.instance.pk:
            for name in ("admin_email", "initial_password"):
                self.fields.pop(name)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("admin_email", "").lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("The Admin email must be new and unused.")
        password = cleaned_data.get("initial_password")
        if password:
            validate_password(password)
        return cleaned_data


class PlatformAuthenticationForm(GarimaAuthenticationForm):
    """Authenticate only the IT company's platform administrators."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_superuser or user.is_platform_admin):
            raise ValidationError("This login is for Platform Super Admins only.", code="not_platform_admin")


class PlatformProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {"first_name": "First name", "last_name": "Last name", "email": "Email address"}

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This email address is already in use.")
        return email
