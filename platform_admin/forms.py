from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from accounts.models import (
    Company,
    CustomStartingStructure,
    ModuleDefinition,
    OrganizationCategory,
    SystemTemplate,
    TemplateModule,
    User,
)
from accounts.services import generate_temporary_password
from accounts.forms import GarimaAuthenticationForm
from core.forms import BootstrapFormMixin


class CompanyForm(BootstrapFormMixin, forms.ModelForm):
    admin_full_name = forms.CharField(label="Full name", max_length=255, required=False)
    admin_email = forms.EmailField(label="Administrator email", required=False)
    admin_phone = forms.CharField(label="Administrator phone", max_length=30, required=False)
    admin_job_title = forms.CharField(label="Administrator job title", max_length=120, required=False)
    admin_temporary_password = forms.CharField(label="Temporary first-login password", max_length=128, required=False)
    modules = forms.MultipleChoiceField(label="Enabled modules", required=False, widget=forms.CheckboxSelectMultiple)
    custom_starting_structure = forms.ModelChoiceField(
        label="Starting structure",
        queryset=CustomStartingStructure.objects.filter(is_active=True),
        required=False,
        empty_label="Blank workspace",
    )

    class Meta:
        model = Company
        fields = [
            "name", "legal_name", "organization_code", "slug", "category", "system_template",
            "industry", "description", "registration_number", "tax_identifier", "email", "phone",
            "website", "address", "is_active",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "description": forms.Textarea(attrs={"rows": 3})}

    organization_fields = set(Meta.fields) - {"category", "system_template"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Organization name"
        self.fields["legal_name"].label = "Legal organization name"
        self.fields["organization_code"].label = "Organization code"
        self.fields["tax_identifier"].label = "PAN/VAT number"
        self.fields["email"].label = "Official email"
        self.fields["is_active"].label = "Workspace status"
        self.fields["is_active"].widget = forms.Select(choices=[(True, "Active"), (False, "Inactive")])
        self.fields["category"].queryset = OrganizationCategory.objects.filter(is_active=True)
        self.fields["system_template"].queryset = SystemTemplate.objects.filter(is_active=True).select_related("category")
        if not self.instance.pk and not self.is_bound:
            self.initial.setdefault("admin_temporary_password", generate_temporary_password())
            default_template = self.fields["system_template"].queryset.filter(
                code="engineering-consultancy",
                version="1.0",
            ).first()
            if default_template:
                self.initial.setdefault("system_template", default_template.pk)
                self.initial.setdefault("category", default_template.category_id)
        self._refresh_module_choices()
        if self.instance.pk:
            for name in ("admin_full_name", "admin_email", "admin_phone", "admin_job_title", "admin_temporary_password", "modules", "custom_starting_structure"):
                self.fields.pop(name)

    def _refresh_module_choices(self):
        template_id = self.data.get("system_template") or self.initial.get("system_template")
        if hasattr(template_id, "pk"):
            template_id = template_id.pk
        modules = ModuleDefinition.objects.none()
        template = SystemTemplate.objects.filter(pk=template_id).first() if template_id else None
        if template_id:
            if template and template.code == "custom-organization":
                modules = ModuleDefinition.objects.filter(
                    is_active=True,
                    available_for_custom=True,
                ).distinct().order_by("is_core", "navigation_order", "name")
            else:
                modules = ModuleDefinition.objects.filter(
                    is_active=True,
                    template_modules__system_template_id=template_id,
                ).distinct().order_by("navigation_order", "name")
        self.fields["modules"].choices = [(module.code, module.name) for module in modules]
        self.custom_module_codes = {module.code for module in modules}
        self.custom_required_module_codes = {module.code for module in modules if module.is_core} if template and template.code == "custom-organization" else set()
        if not self.is_bound and template_id:
            if template and template.code == "custom-organization":
                structure = self.initial.get("custom_starting_structure")
                if not structure:
                    structure = CustomStartingStructure.objects.filter(code="blank-workspace").first()
                if structure:
                    self.initial["custom_starting_structure"] = structure.pk
                    defaults = structure.structure_modules.filter(enabled_by_default=True).values_list("module__code", flat=True)
                else:
                    defaults = []
                self.initial["modules"] = sorted(set(defaults) | self.custom_required_module_codes)
            else:
                self.initial["modules"] = list(
                    TemplateModule.objects.filter(
                        system_template_id=template_id,
                        enabled_by_default=True,
                    ).values_list("module__code", flat=True)
                )

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk:
            if not cleaned_data.get("organization_code"):
                cleaned_data["organization_code"] = slugify(cleaned_data.get("name", ""))
            if not cleaned_data.get("slug"):
                cleaned_data["slug"] = slugify(cleaned_data.get("name", ""))
            category = cleaned_data.get("category") or OrganizationCategory.objects.filter(code="engineering").first()
            template = cleaned_data.get("system_template") or SystemTemplate.objects.filter(code="engineering-consultancy", version="1.0").first()
            cleaned_data["category"] = category
            cleaned_data["system_template"] = template
            if template and category and template.category_id != category.pk:
                self.add_error("system_template", "Choose a template that belongs to the selected category.")
            if template and not TemplateModule.objects.filter(system_template=template).exists():
                self.add_error("system_template", "This template is catalogued but is not available for provisioning yet.")
            email = cleaned_data.get("admin_email", "").lower()
            if email and User.objects.filter(email__iexact=email).exists():
                self.add_error("admin_email", "This administrator email is already in use.")
            if not email:
                self.add_error("admin_email", "An administrator email is required.")
            if not cleaned_data.get("admin_full_name"):
                self.add_error("admin_full_name", "Enter the primary administrator's name.")
            if cleaned_data.get("admin_temporary_password") and len(cleaned_data["admin_temporary_password"]) < 8:
                self.add_error("admin_temporary_password", "Use at least 8 characters for the temporary password.")
            if template:
                if template.code == "custom-organization":
                    structure = cleaned_data.get("custom_starting_structure")
                    defaults = structure.structure_modules.filter(enabled_by_default=True).values_list("module__code", flat=True) if structure else []
                    required = ModuleDefinition.objects.filter(available_for_custom=True, is_core=True).values_list("code", flat=True)
                    cleaned_data["modules"] = list(set(cleaned_data.get("modules", [])) | set(defaults) | set(required))
                else:
                    defaults = TemplateModule.objects.filter(
                        system_template=template,
                        enabled_by_default=True,
                    ).values_list("module__code", flat=True)
                if not cleaned_data.get("modules"):
                    cleaned_data["modules"] = list(defaults)
        if cleaned_data.get("system_template") and cleaned_data.get("modules") is not None:
            template = cleaned_data["system_template"]
            if template.code == "custom-organization":
                allowed = set(ModuleDefinition.objects.filter(is_active=True, available_for_custom=True).values_list("code", flat=True))
                required = set(ModuleDefinition.objects.filter(is_active=True, available_for_custom=True, is_core=True).values_list("code", flat=True))
                cleaned_data["modules"] = list(set(cleaned_data.get("modules", [])) | required)
            else:
                allowed = set(
                    TemplateModule.objects.filter(system_template=template)
                    .values_list("module__code", flat=True)
                )
            invalid = set(cleaned_data.get("modules", [])) - allowed
            if invalid:
                self.add_error("modules", "One or more selected modules are not available for this template.")
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
