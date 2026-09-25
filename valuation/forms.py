from django import forms

from core.forms import BootstrapFormMixin
from .models import ValuationBank, ValuationRequest


class ValuationBankForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ValuationBank
        fields = ["name", "branch", "contact_name", "contact_phone", "contact_email", "is_active"]


class ValuationRequestForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ValuationRequest
        fields = [
            "request_date", "bank", "bank_branch", "bank_reference_number", "borrower_name",
            "property_owner_name", "contact_number", "valuation_purpose", "assigned_engineer",
            "assigned_site_inspector", "required_completion_date", "priority", "notes",
        ]
        widgets = {"request_date": forms.DateInput(attrs={"type": "date"}), "required_completion_date": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["bank"].queryset = organization.valuation_banks.filter(is_active=True)
        self.fields["assigned_engineer"].queryset = organization.users.filter(is_active=True).order_by("first_name", "last_name", "email")
        self.fields["assigned_site_inspector"].queryset = organization.users.filter(is_active=True).order_by("first_name", "last_name", "email")
