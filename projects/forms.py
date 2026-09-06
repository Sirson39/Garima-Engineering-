from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model

from core.forms import BootstrapFormMixin, FileUploadValidationMixin
from projects.constants import DOCUMENT_APPROVAL_CHOICES, DOCUMENT_CONFIDENTIALITY_CHOICES, PAYMENT_METHOD_CHOICES, PRIORITY_CHOICES, PROJECT_STATUS_CHOICES, TASK_PRIORITY_CHOICES, TASK_STATUS_CHOICES, VISIT_STATUS_CHOICES
from projects.models import (
    Client,
    DocumentChecklistItem,
    GovernmentRecord,
    MunicipalityActivity,
    Payment,
    PhysicalFileTransfer,
    Project,
    ProjectComment,
    ProjectDocument,
    SiteVisit,
    Task,
)
from workflows.models import WorkflowStageTemplate


User = get_user_model()


class ClientForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "full_name",
            "mobile_number",
            "email",
            "citizenship_number",
            "permanent_address",
            "current_address",
            "province",
            "district",
            "municipality",
            "ward_number",
            "notes",
        ]
        widgets = {
            "permanent_address": forms.Textarea(attrs={"rows": 3}),
            "current_address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class ProjectForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "service_type",
            "client",
            "registration_date",
            "registration_date_bs",
            "property_location",
            "kitta_number",
            "sheet_number",
            "land_area",
            "province",
            "district",
            "municipality",
            "ward_number",
            "government_application_number",
            "project_fee",
            "discount",
            "expected_completion_date",
            "expected_completion_date_bs",
            "current_file_holder",
            "current_file_location",
            "priority",
            "status",
            "internal_remarks",
            "client_visible_remarks",
            "members",
        ]
        widgets = {
            "internal_remarks": forms.Textarea(attrs={"rows": 3}),
            "client_visible_remarks": forms.Textarea(attrs={"rows": 3}),
            "members": forms.SelectMultiple(attrs={"size": 8}),
        }


class ProjectDocumentUploadForm(FileUploadValidationMixin, BootstrapFormMixin, forms.ModelForm):
    file_field_names = ("file",)

    class Meta:
        model = ProjectDocument
        fields = [
            "category",
            "checklist_item",
            "display_name",
            "file",
            "approval_status",
            "confidentiality_level",
            "checked_by",
            "remarks",
        ]
        widgets = {
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }


class ChecklistExceptionForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))


class ProjectStageAdvanceForm(BootstrapFormMixin, forms.Form):
    target_stage = forms.ModelChoiceField(queryset=WorkflowStageTemplate.objects.none(), required=False)
    assigned_employee = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    comments = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    override_missing_documents = forms.BooleanField(required=False)
    override_reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            current_stage = project.current_stage_template
            if current_stage:
                choices = project.service_type.workflow_stages.filter(order__gt=current_stage.order).order_by("order")
            else:
                choices = project.service_type.workflow_stages.order_by("order")
            self.fields["target_stage"].queryset = choices
            self.fields["assigned_employee"].queryset = User.objects.filter(is_active=True, is_staff=True).order_by("first_name", "last_name")
        else:
            self.fields["target_stage"].queryset = WorkflowStageTemplate.objects.all()
            self.fields["assigned_employee"].queryset = User.objects.filter(is_active=True, is_staff=True)


class TaskForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "related_stage",
            "assigned_employee",
            "priority",
            "start_date",
            "due_date",
            "status",
            "comments",
        ]
        widgets = {
            "comments": forms.Textarea(attrs={"rows": 3}),
        }


class PhysicalFileTransferForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PhysicalFileTransfer
        fields = [
            "file_transferred_from",
            "file_transferred_to",
            "current_location",
            "transfer_date_time",
            "purpose",
            "expected_return_date",
            "received_confirmation",
            "actual_return_date",
            "remarks",
        ]
        widgets = {
            "transfer_date_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "purpose": forms.TextInput(),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }


class SiteVisitForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SiteVisit
        fields = [
            "assigned_engineer",
            "scheduled_date",
            "scheduled_date_bs",
            "actual_visit_date",
            "actual_visit_date_bs",
            "site_address",
            "contact_person",
            "contact_number",
            "gps_coordinates",
            "measurements",
            "site_condition",
            "building_information",
            "engineer_observations",
            "follow_up_required",
            "visit_status",
            "engineer_confirmation",
            "recorded_by",
        ]
        widgets = {
            "measurements": forms.Textarea(attrs={"rows": 3}),
            "site_condition": forms.Textarea(attrs={"rows": 3}),
            "building_information": forms.Textarea(attrs={"rows": 3}),
            "engineer_observations": forms.Textarea(attrs={"rows": 3}),
        }


class GovernmentRecordForm(FileUploadValidationMixin, BootstrapFormMixin, forms.ModelForm):
    file_field_names = ("receipt_or_screenshot",)

    class Meta:
        model = GovernmentRecord
        fields = [
            "municipality",
            "government_application_number",
            "submission_type",
            "submission_date",
            "submission_date_bs",
            "submitted_by",
            "current_online_status",
            "receipt_or_screenshot",
            "ward_document_upload_date",
            "ward_document_upload_date_bs",
            "structural_document_upload_date",
            "structural_document_upload_date_bs",
            "asthayi_status",
            "isthayi_status",
            "government_remarks",
            "rejection_or_correction_reason",
            "resubmission_date",
            "resubmission_date_bs",
            "last_checked_date",
            "last_checked_date_bs",
            "recorded_by",
        ]
        widgets = {
            "government_remarks": forms.Textarea(attrs={"rows": 3}),
            "rejection_or_correction_reason": forms.Textarea(attrs={"rows": 3}),
        }


class MunicipalityActivityForm(FileUploadValidationMixin, BootstrapFormMixin, forms.ModelForm):
    file_field_names = ("attachment",)

    class Meta:
        model = MunicipalityActivity
        fields = [
            "municipality",
            "activity_type",
            "details",
            "attachment",
            "recorded_by",
            "recorded_at",
            "resolved_at",
            "is_resolved",
        ]
        widgets = {
            "details": forms.Textarea(attrs={"rows": 4}),
            "recorded_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "resolved_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class PaymentForm(FileUploadValidationMixin, BootstrapFormMixin, forms.ModelForm):
    file_field_names = ("payment_proof",)

    class Meta:
        model = Payment
        fields = [
            "agreed_fee",
            "discount",
            "net_fee",
            "amount_received",
            "remaining_balance",
            "payment_date",
            "payment_date_bs",
            "payment_method",
            "receipt_number",
            "payment_reference",
            "received_by",
            "payment_proof",
            "remarks",
        ]
        widgets = {
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }


class ProjectCommentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectComment
        fields = ["visibility", "comment"]
        widgets = {"comment": forms.Textarea(attrs={"rows": 3})}
