from django import forms
from django.core.exceptions import ValidationError

from core.forms import BootstrapFormMixin
from .models import OfficeDepartment


class OfficeDepartmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = OfficeDepartment
        fields = ["name", "code", "description", "department_head", "parent", "cost_centre", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["department_head"].queryset = organization.users.filter(is_active=True).order_by("first_name", "last_name", "email")
        self.fields["parent"].queryset = organization.office_departments.exclude(pk=self.instance.pk).order_by("name")

    def clean(self):
        cleaned = super().clean()
        self.instance.organization = self.organization
        try:
            self.instance.department_head = cleaned.get("department_head")
            self.instance.parent = cleaned.get("parent")
            self.instance.clean()
        except ValidationError as error:
            raise error
        return cleaned
