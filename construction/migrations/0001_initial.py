from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0007_company_city_company_currency_code_and_more"),
    ]
    operations = [
        migrations.CreateModel(
            name="ConstructionProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("project_number", models.CharField(max_length=50)),
                ("name", models.CharField(max_length=255)),
                ("client_name", models.CharField(blank=True, max_length=255)),
                ("project_type", models.CharField(blank=True, max_length=120)),
                ("contract_type", models.CharField(blank=True, max_length=120)),
                ("description", models.TextField(blank=True)),
                ("scope", models.TextField(blank=True)),
                ("address", models.TextField(blank=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("expected_completion_date", models.DateField(blank=True, null=True)),
                ("actual_completion_date", models.DateField(blank=True, null=True)),
                ("contract_value", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("currency_code", models.CharField(default="NPR", max_length=3)),
                ("status", models.CharField(choices=[("planning", "Planning"), ("preconstruction", "Preconstruction"), ("active", "Active"), ("on_hold", "On hold"), ("substantially_complete", "Substantially complete"), ("completed", "Completed"), ("archived", "Archived")], default="planning", max_length=32)),
                ("progress_percentage", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_construction_projects", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="construction_projects", to="accounts.company")),
                ("project_manager", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="managed_construction_projects", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at", "project_number"]},
        ),
        migrations.CreateModel(
            name="ConstructionParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("participant_type", models.CharField(choices=[("client", "Client"), ("consultant", "Consultant"), ("architect", "Architect"), ("engineer", "Engineer"), ("contractor", "General contractor"), ("subcontractor", "Subcontractor"), ("supplier", "Supplier")], max_length=32)),
                ("company_name", models.CharField(max_length=255)),
                ("contact_name", models.CharField(blank=True, max_length=255)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("notes", models.TextField(blank=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="construction.constructionproject")),
            ],
            options={"ordering": ["company_name"]},
        ),
        migrations.CreateModel(
            name="ConstructionProjectMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("project_role", models.CharField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="construction.constructionproject")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="construction_project_memberships", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ConstructionLocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("location_type", models.CharField(choices=[("site", "Site"), ("building", "Building"), ("floor", "Floor"), ("zone", "Zone"), ("room", "Room")], max_length=20)),
                ("name", models.CharField(max_length=160)),
                ("code", models.CharField(blank=True, max_length=50)),
                ("description", models.TextField(blank=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="construction.constructionlocation")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="locations", to="construction.constructionproject")),
            ],
            options={"ordering": ["location_type", "name"]},
        ),
        migrations.AddConstraint(model_name="constructionproject", constraint=models.UniqueConstraint(fields=("organization", "project_number"), name="unique_construction_project_number")),
        migrations.AddConstraint(model_name="constructionprojectmember", constraint=models.UniqueConstraint(fields=("project", "user"), name="unique_construction_project_member")),
        migrations.AddIndex(model_name="constructionproject", index=models.Index(fields=["organization", "status"], name="constructio_organiz_4afe89_idx")),
    ]
