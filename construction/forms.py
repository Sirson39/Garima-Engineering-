from django import forms

from .models import ConstructionProject


class ConstructionProjectForm(forms.ModelForm):
    class Meta:
        model = ConstructionProject
        fields = [
            "project_number", "name", "client_name", "project_type", "contract_type",
            "description", "scope", "address", "start_date", "expected_completion_date",
            "contract_value", "currency_code", "project_manager", "status", "progress_percentage",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "scope": forms.Textarea(attrs={"rows": 3}),
            "address": forms.Textarea(attrs={"rows": 2}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "expected_completion_date": forms.DateInput(attrs={"type": "date"}),
            "contract_value": forms.NumberInput(attrs={"step": "0.01"}),
            "progress_percentage": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
        }
