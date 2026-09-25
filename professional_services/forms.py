from django import forms
from django.core.exceptions import ValidationError

from accounts.models import OrganizationMembership, OrganizationRole
from .models import Engagement, ProfessionalClient, ProfessionalService, ProfessionalSettings


class WorkspaceForm(forms.ModelForm):
    def __init__(self, *args, access, **kwargs):
        super().__init__(*args, **kwargs)
        self.access = access
        self.instance.organization = access.organization
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            if isinstance(field, forms.DateField):
                field.widget = forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d")
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 3
            if name in {"account_manager", "engagement_manager", "assigned_team"}:
                field.queryset = access.staff()
            if name in {"service", "services_used"}:
                field.queryset = access.services()
            if name == "client":
                field.queryset = access.clients()

    def clean(self):
        data = super().clean()
        # ModelForm excludes organization because it is never client writable.
        # Check tenant uniqueness here for a useful field error, with a DB constraint
        # as the concurrent-write backstop.
        key = "number" if isinstance(self.instance, Engagement) else "code" if isinstance(self.instance, ProfessionalService) else None
        if key and data.get(key) and type(self.instance).objects.filter(
            organization=self.access.organization, **{key: data[key]},
        ).exclude(pk=self.instance.pk).exists():
            self.add_error(key, "This value is already used in this organization.")
        return data


class ClientForm(WorkspaceForm):
    class Meta:
        model = ProfessionalClient
        fields = ["name", "client_type", "contact_person", "email", "phone", "address", "industry",
                  "account_manager", "services_used", "billing_rate", "notes", "status"]
        help_texts = {"billing_rate": "Optional client rate override. Leave blank to use the service or organization rate."}


class ServiceForm(WorkspaceForm):
    class Meta:
        model = ProfessionalService
        fields = ["name", "code", "description", "default_duration_days", "default_billing_method",
                  "default_rate", "default_deliverables", "responsible_department", "status"]


class EngagementForm(WorkspaceForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["billing_method"].required = False
        self.fields["billing_method"].choices = [("", "Use service default"), *self.fields["billing_method"].choices]
        if not self.instance.pk:
            self.initial["billing_method"] = ""

    def clean(self):
        data = super().clean()
        if not data.get("billing_method") and data.get("service"):
            data["billing_method"] = data["service"].default_billing_method
        return data

    class Meta:
        model = Engagement
        fields = ["number", "title", "client", "service", "description", "account_manager", "engagement_manager",
                  "assigned_team", "start_date", "due_date", "billing_method", "contract_amount", "billing_rate", "progress", "status"]
        labels = {"number": "Engagement number", "progress": "Progress (%)"}
        help_texts = {"number": "Unique within this organization.", "assigned_team": "Selected staff can access this engagement when their role permits it.",
                      "billing_rate": "Optional engagement rate override. Leave blank to inherit the client, service or organization rate."}


class SettingsForm(WorkspaceForm):
    class Meta:
        model = ProfessionalSettings
        fields = ["default_rate"]
        help_texts = {"default_rate": "Fallback billing rate in your organization's currency. Client, service and engagement rates can override this."}


class RoleAssignmentForm(forms.Form):
    membership = forms.ModelChoiceField(queryset=OrganizationMembership.objects.none(), label="Staff membership")
    organization_role = forms.ModelChoiceField(queryset=OrganizationRole.objects.none(), label="Workspace role")

    def __init__(self, *args, access, **kwargs):
        super().__init__(*args, **kwargs)
        self.access = access
        self.fields["membership"].queryset = OrganizationMembership.objects.filter(
            organization=access.organization, is_active=True, user__is_active=True,
        ).exclude(user=access.user).select_related("user")
        self.fields["membership"].label_from_instance = lambda member: member.user.display_name
        self.fields["organization_role"].queryset = OrganizationRole.objects.filter(
            organization=access.organization, is_active=True,
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select"

    def clean(self):
        data = super().clean()
        member = data.get("membership")
        if member and member.user_id == self.access.user.pk:
            raise ValidationError("Ask another organization administrator to change your own role.")
        return data
