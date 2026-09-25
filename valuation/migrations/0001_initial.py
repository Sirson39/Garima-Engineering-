import valuation.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("accounts", "0014_rename_nonprofit_template_to_valuation")]
    operations = [
        migrations.CreateModel(
            name="ValuationBank",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                ("branch", models.CharField(blank=True, max_length=180)),
                ("contact_name", models.CharField(blank=True, max_length=160)),
                ("contact_phone", models.CharField(blank=True, max_length=40)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="valuation_banks", to="accounts.company")),
            ],
            options={"ordering": ["name", "branch"], "constraints": [models.UniqueConstraint(fields=("organization", "name", "branch"), name="unique_valuation_bank_branch")]},
        ),
        migrations.CreateModel(
            name="ValuationRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference_number", models.CharField(max_length=80)),
                ("request_date", models.DateField()),
                ("bank_branch", models.CharField(blank=True, max_length=180)),
                ("bank_reference_number", models.CharField(blank=True, max_length=120)),
                ("borrower_name", models.CharField(max_length=255)),
                ("property_owner_name", models.CharField(max_length=255)),
                ("contact_number", models.CharField(blank=True, max_length=40)),
                ("valuation_purpose", models.CharField(max_length=255)),
                ("required_completion_date", models.DateField(blank=True, null=True)),
                ("priority", models.CharField(choices=[("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")], default="normal", max_length=20)),
                ("status", models.CharField(choices=[("request_received", "Request received"), ("documents_pending", "Documents pending"), ("documents_verified", "Documents verified"), ("site_visit_scheduled", "Site visit scheduled"), ("site_inspection_completed", "Site inspection completed"), ("valuation_drafted", "Valuation drafted"), ("internal_review", "Internal review"), ("correction_required", "Correction required"), ("approved", "Approved"), ("report_issued", "Report issued"), ("archived", "Archived")], default="request_received", max_length=40)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_engineer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="valuation_requests_as_engineer", to="accounts.user")),
                ("assigned_site_inspector", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="valuation_requests_as_inspector", to="accounts.user")),
                ("bank", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="valuation_requests", to="valuation.valuationbank")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_valuation_requests", to="accounts.user")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="valuation_requests", to="accounts.company")),
            ],
            options={"ordering": ["-created_at"], "constraints": [models.UniqueConstraint(fields=("organization", "reference_number"), name="unique_valuation_reference")], "indexes": [models.Index(fields=("organization", "status", "request_date"), name="valuation_v_organiz_c377ae_idx")]},
        ),
        migrations.CreateModel(
            name="ValuationDocumentChecklist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_type", models.CharField(max_length=180)),
                ("is_required", models.BooleanField(default=True)),
                ("status", models.CharField(choices=[("required", "Required"), ("received", "Received"), ("verified", "Verified"), ("not_applicable", "Not applicable"), ("expired", "Expired"), ("correction_required", "Correction required")], default="required", max_length=30)),
                ("file", models.FileField(blank=True, null=True, upload_to=valuation.models.valuation_document_upload_to)),
                ("received_at", models.DateTimeField(blank=True, null=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="document_checklist", to="valuation.valuationrequest")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="verified_valuation_documents", to="accounts.user")),
            ],
            options={"ordering": ["document_type"], "constraints": [models.UniqueConstraint(fields=("request", "document_type"), name="unique_valuation_document_type")]},
        ),
        migrations.CreateModel(
            name="ValuationReviewComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("comment", models.TextField()),
                ("is_resolved", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="valuation_review_comments", to="accounts.user")),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="review_comments", to="valuation.valuationrequest")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ValuationActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=80)),
                ("from_status", models.CharField(blank=True, max_length=40)),
                ("to_status", models.CharField(blank=True, max_length=40)),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="valuation_activities", to="accounts.user")),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="valuation.valuationrequest")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
