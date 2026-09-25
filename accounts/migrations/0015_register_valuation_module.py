from django.db import migrations


MODULES = [
    ("valuation-management", "Valuation workspace", True, "valuation-dashboard", "landmark"),
    ("valuation-requests", "Valuation files", True, "valuation-request-list", "file-text"),
    ("valuation-documents", "Document checklist", True, "valuation-request-list", "files"),
    ("valuation-workflow", "Valuation workflow", True, "valuation-request-list", "git-branch"),
    ("valuation-banks", "Banks and clients", True, "valuation-banks", "landmark"),
    ("valuation-audit", "Valuation audit activity", True, "audit-logs", "history"),
]

ROLES = [
    ("organization-admin", "Organization Administrator"),
    ("valuation-coordinator", "Valuation Coordinator"),
    ("document-officer", "Document Officer"),
    ("site-inspector", "Site Inspector"),
    ("valuation-engineer", "Valuation Engineer"),
    ("senior-reviewer", "Senior Reviewer"),
    ("authorized-approver", "Authorized Approver"),
    ("accounts-staff", "Accounts Staff"),
    ("read-only-auditor", "Read-only Auditor"),
]


def seed_valuation_catalog(apps, schema_editor):
    db = schema_editor.connection.alias
    Category = apps.get_model("accounts", "OrganizationCategory")
    Template = apps.get_model("accounts", "SystemTemplate")
    Module = apps.get_model("accounts", "ModuleDefinition")
    TemplateModule = apps.get_model("accounts", "TemplateModule")
    Permission = apps.get_model("accounts", "ModulePermission")
    RoleTemplate = apps.get_model("accounts", "RoleTemplate")
    RoleTemplatePermission = apps.get_model("accounts", "RoleTemplatePermission")
    Navigation = apps.get_model("accounts", "TemplateNavigationItem")
    Widget = apps.get_model("accounts", "TemplateDashboardWidget")

    valuation_category = Category.objects.using(db).get(code="professional-services")
    legacy_template = Template.objects.using(db).get(code="non-profit-management", version="1.0")
    legacy_template.code = "valuation-management"
    legacy_template.name = "Valuation management"
    legacy_template.description = "A Nepal property valuation workspace for engineering consultancies and dedicated valuation organizations."
    legacy_template.category = valuation_category
    legacy_template.save(update_fields=["code", "name", "description", "category"])

    engineering = Template.objects.using(db).get(code="engineering-consultancy", version="1.0")
    templates = [engineering, legacy_template]
    module_map = {}
    permissions = {}
    for order, (code, name, required, url_name, icon) in enumerate(MODULES):
        module, _ = Module.objects.using(db).get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": f"{name} for Nepal property valuation work.",
                "is_core": required,
                "navigation_label": name,
                "navigation_url_name": url_name,
                "navigation_icon": icon,
                "navigation_order": order,
            },
        )
        module_map[code] = module
        for action, label in (("view", "View"), ("create", "Create"), ("change", "Change"), ("delete", "Delete"), ("manage", "Manage")):
            permission, _ = Permission.objects.using(db).get_or_create(
                code=f"{code}.{action}",
                defaults={"module": module, "name": f"{label} {name}"},
            )
            permissions[(code, action)] = permission

    for template in templates:
        for code, module in module_map.items():
            TemplateModule.objects.using(db).get_or_create(
                system_template=template,
                module=module,
                defaults={"required": template.pk == legacy_template.pk, "enabled_by_default": template.pk == legacy_template.pk},
            )
        for order, (code, name, required, url_name, icon) in enumerate(MODULES):
            Navigation.objects.using(db).get_or_create(
                system_template=template,
                url_name=url_name,
                defaults={"module": module_map[code], "label": name, "icon": icon, "display_order": order},
            )

    for role_code, role_name in ROLES:
        role, _ = RoleTemplate.objects.using(db).get_or_create(
            system_template=legacy_template,
            code=role_code,
            defaults={"name": role_name, "description": f"Valuation role: {role_name}."},
        )
        if role_code in {"organization-admin", "authorized-approver", "senior-reviewer"}:
            selected = permissions.values()
        elif role_code == "read-only-auditor":
            selected = [permission for (module, action), permission in permissions.items() if action == "view"]
        else:
            selected = [permission for (module, action), permission in permissions.items() if action in {"view", "create", "change"} and module != "valuation-audit"]
        for permission in selected:
            RoleTemplatePermission.objects.using(db).get_or_create(role_template=role, permission=permission)

    for order, (code, title, component_key, module_code) in enumerate([
        ("total-files", "Total valuation files", "valuation.total-files", "valuation-requests"),
        ("documents-pending", "Documents pending", "valuation.documents-pending", "valuation-documents"),
        ("reports-under-review", "Reports under review", "valuation.reports-under-review", "valuation-workflow"),
        ("recent-activity", "Recent activity", "valuation.recent-activity", "valuation-audit"),
    ]):
        Widget.objects.using(db).get_or_create(
            system_template=legacy_template,
            code=code,
            defaults={"module": module_map[module_code], "title": title, "component_key": component_key, "display_order": order},
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0014_rename_nonprofit_template_to_valuation")]
    operations = [migrations.RunPython(seed_valuation_catalog, migrations.RunPython.noop)]
