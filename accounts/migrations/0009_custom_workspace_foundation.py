from django.db import migrations, models
import django.db.models.deletion


CUSTOM_MODULES = [
    ("custom-authentication", "Authentication", True),
    ("custom-users-staff", "Users and staff", True),
    ("custom-membership", "Organization membership", True),
    ("custom-departments", "Departments", True),
    ("custom-roles", "Roles and permissions", True),
    ("custom-documents", "Documents", True),
    ("custom-notifications", "Notifications", True),
    ("custom-audit", "Audit activity", True),
    ("custom-settings", "Organization settings", True),
    ("custom-clients", "Clients", False),
    ("custom-contacts", "Contacts", False),
    ("custom-projects", "Projects", False),
    ("custom-work-items", "Work items", False),
    ("custom-tasks", "Tasks", False),
    ("custom-requests", "Requests", False),
    ("custom-approvals", "Approvals", False),
    ("custom-calendar", "Calendar", False),
    ("custom-meetings", "Meetings", False),
    ("custom-expenses", "Expenses", False),
    ("custom-payments", "Payments", False),
    ("custom-assets", "Assets", False),
    ("custom-inventory", "Inventory", False),
    ("custom-suppliers", "Suppliers", False),
    ("custom-forms", "Forms", False),
    ("custom-reports", "Reports", False),
    ("custom-announcements", "Announcements", False),
]

STARTING_STRUCTURES = [
    ("blank-workspace", "Blank workspace", "A secure workspace with only the required core capabilities."),
    ("general-office", "General office starter", "A practical starting point for teams, documents, tasks and communication."),
    ("project-based", "Project-based organization", "A workspace centered around projects, work items, tasks and reports."),
    ("client-service", "Client-service organization", "A workspace for client relationships, contacts, requests and delivery work."),
    ("request-approval", "Request and approval system", "A workspace for structured requests, approvals, tasks and audit history."),
    ("document-management", "Document management system", "A workspace focused on documents, reviews, approvals and activity history."),
    ("asset-inventory", "Asset and inventory system", "A workspace for assets, inventory, suppliers and operational records."),
]

STRUCTURE_MODULES = {
    "blank-workspace": [],
    "general-office": ["custom-clients", "custom-contacts", "custom-tasks", "custom-calendar", "custom-meetings", "custom-expenses", "custom-announcements", "custom-reports"],
    "project-based": ["custom-projects", "custom-work-items", "custom-tasks", "custom-calendar", "custom-documents", "custom-reports"],
    "client-service": ["custom-clients", "custom-contacts", "custom-requests", "custom-work-items", "custom-tasks", "custom-documents", "custom-reports"],
    "request-approval": ["custom-requests", "custom-approvals", "custom-tasks", "custom-notifications", "custom-reports"],
    "document-management": ["custom-documents", "custom-approvals", "custom-forms", "custom-reports"],
    "asset-inventory": ["custom-assets", "custom-inventory", "custom-suppliers", "custom-requests", "custom-reports"],
}


def seed_custom_workspace(apps, schema_editor):
    db = schema_editor.connection.alias
    Category = apps.get_model("accounts", "OrganizationCategory")
    Template = apps.get_model("accounts", "SystemTemplate")
    Module = apps.get_model("accounts", "ModuleDefinition")
    TemplateModule = apps.get_model("accounts", "TemplateModule")
    StartingStructure = apps.get_model("accounts", "CustomStartingStructure")
    StructureModule = apps.get_model("accounts", "CustomStructureModule")
    Permission = apps.get_model("accounts", "ModulePermission")
    RoleTemplate = apps.get_model("accounts", "RoleTemplate")
    RoleTemplatePermission = apps.get_model("accounts", "RoleTemplatePermission")

    category = Category.objects.using(db).get(code="other")
    template = Template.objects.using(db).get(code="custom-organization", version="1.0")
    Template.objects.using(db).filter(pk=template.pk).update(
        description="A controlled workspace builder for organizations with configurable modules, terminology and future records.",
    )

    modules = {}
    for order, (code, name, required) in enumerate(CUSTOM_MODULES):
        module, _ = Module.objects.using(db).get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": f"{name} for controlled Custom workspaces.",
                "is_core": required,
                "available_for_custom": True,
                "navigation_label": name,
                "navigation_order": order,
            },
        )
        if not module.available_for_custom:
            Module.objects.using(db).filter(pk=module.pk).update(available_for_custom=True)
        modules[code] = module
        TemplateModule.objects.using(db).get_or_create(
            system_template=template,
            module=module,
            defaults={"required": required, "enabled_by_default": required},
        )

        for action, label in (("view", "View"), ("create", "Create"), ("change", "Change"), ("delete", "Delete"), ("manage", "Manage")):
            Permission.objects.using(db).get_or_create(
                code=f"{code}.{action}",
                defaults={"module": module, "name": f"{label} {name}"},
            )

    for code, name, description in STARTING_STRUCTURES:
        structure, _ = StartingStructure.objects.using(db).get_or_create(
            code=code,
            defaults={"name": name, "description": description, "display_order": len(StructureModule.objects.using(db).filter(starting_structure__code__lt=code))},
        )
        for module_code in STRUCTURE_MODULES[code]:
            StructureModule.objects.using(db).get_or_create(
                starting_structure=structure,
                module=modules[module_code],
                defaults={"enabled_by_default": True},
            )

    admin_role, _ = RoleTemplate.objects.using(db).get_or_create(
        system_template=template,
        code="organization-admin",
        defaults={"name": "Organization Administrator", "description": "Manage the Custom workspace configuration and users."},
    )
    admin_permissions = Permission.objects.using(db).filter(module__code__in=list(modules))
    for permission in admin_permissions:
        RoleTemplatePermission.objects.using(db).get_or_create(role_template=admin_role, permission=permission)

    staff_role, _ = RoleTemplate.objects.using(db).get_or_create(
        system_template=template,
        code="staff",
        defaults={"name": "Staff", "description": "Use capabilities granted by the organization administrator."},
    )
    staff_permissions = Permission.objects.using(db).filter(module__code__in={"custom-documents", "custom-notifications", "custom-audit"}, code__endswith=".view")
    for permission in staff_permissions:
        RoleTemplatePermission.objects.using(db).get_or_create(role_template=staff_role, permission=permission)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_seed_construction_catalog")]

    operations = [
        migrations.AddField(
            model_name="moduledefinition",
            name="available_for_custom",
            field=models.BooleanField(default=False, help_text="Whether this catalog module can be selected for a Custom workspace."),
        ),
        migrations.CreateModel(
            name="CustomStartingStructure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=80, unique=True)),
                ("name", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("display_order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={"ordering": ["display_order", "name"]},
        ),
        migrations.CreateModel(
            name="OrganizationConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField(default=1)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")], default="draft", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_configuration_versions", to="accounts.user")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="configuration_versions", to="accounts.company")),
                ("published_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="published_configuration_versions", to="accounts.user")),
                ("starting_structure", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="accounts.customstartingstructure")),
            ],
            options={"ordering": ["-version"], "constraints": [models.UniqueConstraint(fields=("organization", "version"), name="unique_organization_configuration_version")]},
        ),
        migrations.CreateModel(
            name="CustomStructureModule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("required", models.BooleanField(default=False)),
                ("enabled_by_default", models.BooleanField(default=True)),
                ("module", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="custom_structure_modules", to="accounts.moduledefinition")),
                ("starting_structure", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="structure_modules", to="accounts.customstartingstructure")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("starting_structure", "module"), name="unique_custom_structure_module")]},
        ),
        migrations.CreateModel(
            name="OrganizationTerminology",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("internal_code", models.SlugField(max_length=80)),
                ("label", models.CharField(max_length=120)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="terminology", to="accounts.company")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="accounts.user")),
            ],
            options={"ordering": ["internal_code"], "constraints": [models.UniqueConstraint(fields=("organization", "internal_code"), name="unique_organization_terminology")]},
        ),
        migrations.RunPython(seed_custom_workspace, migrations.RunPython.noop),
    ]
