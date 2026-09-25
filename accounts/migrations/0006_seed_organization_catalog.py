from django.db import migrations


CATEGORIES = [
    ("engineering", "Engineering"),
    ("construction", "Construction"),
    ("education", "Education"),
    ("healthcare", "Healthcare"),
    ("professional-services", "Professional services"),
    ("general-office", "General office"),
    ("non-profit", "Non-profit"),
    ("retail", "Retail"),
    ("other", "Other"),
]

TEMPLATES = [
    ("engineering-consultancy", "Engineering consultancy management", "engineering"),
    ("construction-management", "Construction project management", "construction"),
    ("school-management", "School management", "education"),
    ("hospital-management", "Healthcare management", "healthcare"),
    ("professional-services", "Professional services management", "professional-services"),
    ("general-office", "General office management", "general-office"),
    ("non-profit-management", "Non-profit management", "non-profit"),
    ("retail-management", "Retail management", "retail"),
    ("custom-organization", "Custom organization", "other"),
]

ENGINEERING_MODULES = [
    ("organization-core", "Organization workspace", True),
    ("team-access", "Team and access", True),
    ("audit-activity", "Audit activity", True),
    ("clients", "Clients", False),
    ("projects", "Projects", False),
    ("document-control", "Document control", False),
    ("workflow-tasks", "Workflow and tasks", False),
    ("site-visits", "Site visits", False),
    ("government-submissions", "Government submissions", False),
    ("municipality-records", "Municipality records", False),
    ("physical-file-tracking", "Physical file tracking", False),
    ("project-payments", "Project payments", False),
    ("reports", "Reports", False),
]


def seed_catalog(apps, schema_editor):
    Category = apps.get_model("accounts", "OrganizationCategory")
    Template = apps.get_model("accounts", "SystemTemplate")
    Module = apps.get_model("accounts", "ModuleDefinition")
    TemplateModule = apps.get_model("accounts", "TemplateModule")
    Company = apps.get_model("accounts", "Company")

    categories = {}
    for code, name in CATEGORIES:
        categories[code], _ = Category.objects.using(schema_editor.connection.alias).get_or_create(
            code=code, defaults={"name": name}
        )

    templates = {}
    for code, name, category_code in TEMPLATES:
        templates[code], _ = Template.objects.using(schema_editor.connection.alias).get_or_create(
            code=code,
            version="1.0",
            defaults={"name": name, "category_id": categories[category_code].pk},
        )

    modules = {}
    for code, name, is_core in ENGINEERING_MODULES:
        modules[code], _ = Module.objects.using(schema_editor.connection.alias).get_or_create(
            code=code, defaults={"name": name, "is_core": is_core}
        )
        TemplateModule.objects.using(schema_editor.connection.alias).get_or_create(
            system_template_id=templates["engineering-consultancy"].pk,
            module_id=modules[code].pk,
            defaults={"required": is_core, "enabled_by_default": True},
        )

    # Metadata-only mapping by the audited, unique slug. Do not assign legacy users or records.
    Company.objects.using(schema_editor.connection.alias).filter(
        slug="garima-engineering-consultancy"
    ).update(
        organization_code="garima-engineering-consultancy",
        category_id=categories["engineering"].pk,
        system_template_id=templates["engineering-consultancy"].pk,
        applied_template_version="1.0",
    )


def unseed_catalog(apps, schema_editor):
    # Intentionally retain catalog rows and organization metadata on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_moduledefinition_organizationcategory_roletemplate_and_more")]

    operations = [migrations.RunPython(seed_catalog, unseed_catalog)]
