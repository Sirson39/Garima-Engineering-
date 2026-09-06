from __future__ import annotations

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from pathlib import Path

from core.models import OrganizationProfile


class BootstrapFormMixin:
    input_classes = {
        forms.Textarea: "form-control",
        forms.Select: "form-select",
        forms.SelectMultiple: "form-select",
        forms.CheckboxInput: "form-check-input",
        forms.ClearableFileInput: "form-control",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget_class = field.widget.__class__
            if widget_class in self.input_classes:
                css = self.input_classes[widget_class]
            else:
                css = "form-control"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css}".strip()
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("role", "switch")


class FileUploadValidationMixin:
    allowed_extensions = {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".jpg",
        ".jpeg",
        ".png",
        ".dwg",
        ".dxf",
        ".zip",
    }
    max_upload_size = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", 50 * 1024 * 1024)
    file_field_names: tuple[str, ...] = ()

    def clean(self):
        cleaned_data = super().clean()
        for field_name in self.file_field_names:
            uploaded_file = cleaned_data.get(field_name)
            if not uploaded_file:
                continue
            suffix = Path(uploaded_file.name).suffix.lower()
            if suffix and suffix not in self.allowed_extensions:
                self.add_error(field_name, "Unsupported file type.")
            if uploaded_file.size > self.max_upload_size:
                self.add_error(field_name, "File is too large.")
        return cleaned_data


class OrganizationProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = OrganizationProfile
        fields = [
            "company_name",
            "short_name",
            "slogan",
            "logo",
            "address",
            "phone",
            "email",
            "website",
            "primary_color",
            "accent_color",
            "default_bs_year",
            "public_notice",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "public_notice": forms.Textarea(attrs={"rows": 4}),
        }
