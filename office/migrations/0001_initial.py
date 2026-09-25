import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("accounts", "0010_describe_custom_template")]
    operations = [
        migrations.CreateModel(
            name="OfficeDepartment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("code", models.SlugField(max_length=50)),
                ("description", models.TextField(blank=True)),
                ("cost_centre", models.CharField(blank=True, max_length=80)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("department_head", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="headed_office_departments", to="accounts.user")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="office_departments", to="accounts.company")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="child_departments", to="office.officedepartment")),
            ],
            options={"ordering": ["name"], "constraints": [models.UniqueConstraint(fields=("organization", "code"), name="unique_office_department_code"), models.UniqueConstraint(fields=("organization", "name"), name="unique_office_department_name")]},
        ),
        migrations.CreateModel(
            name="OfficeStaffProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("employee_id", models.CharField(max_length=80)),
                ("employment_type", models.CharField(blank=True, max_length=80)),
                ("joining_date", models.DateField(blank=True, null=True)),
                ("work_location", models.CharField(blank=True, max_length=160)),
                ("emergency_contact_name", models.CharField(blank=True, max_length=160)),
                ("emergency_contact_phone", models.CharField(blank=True, max_length=40)),
                ("employment_status", models.CharField(choices=[("active", "Active"), ("on_leave", "On Leave"), ("suspended", "Suspended"), ("resigned", "Resigned"), ("terminated", "Terminated"), ("archived", "Archived")], default="active", max_length=20)),
                ("account_status", models.CharField(choices=[("active", "Active"), ("suspended", "Suspended"), ("archived", "Archived")], default="active", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("department", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="staff_profiles", to="office.officedepartment")),
                ("manager", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="direct_reports", to="office.officestaffprofile")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="office_staff_profiles", to="accounts.company")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="office_staff_profiles", to="accounts.user")),
            ],
            options={"ordering": ["employee_id"], "constraints": [models.UniqueConstraint(fields=("organization", "user"), name="unique_office_staff_user"), models.UniqueConstraint(fields=("organization", "employee_id"), name="unique_office_employee_id")], "indexes": [models.Index(fields=("organization", "employment_status"), name="office_offi_organiz_3fa569_idx")]},
        ),
    ]
