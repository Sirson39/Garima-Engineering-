from django.db import migrations


MODULES = [
    ("construction-projects", "Construction projects", True, "construction-dashboard", "hard-hat"),
    ("construction-project-directory", "Project directory", True, "construction-project-list", "list"),
    ("construction-locations", "Project locations", True, "construction-project-list", "map-pin"),
    ("construction-tasks", "Construction tasks", True, "construction-project-list", "check-square"),
    ("construction-notifications", "Notifications", True, "construction-dashboard", "bell"),
    ("construction-comments", "Comments", True, "construction-project-list", "message-circle"),
    ("construction-audit", "Audit activity", True, "audit-logs", "history"),
    ("construction-reports", "Construction reports", True, "reports", "bar-chart-3"),
    ("construction-team", "Project team", True, "construction-project-list", "users"),
    ("construction-schedule", "Schedule and milestones", False, "construction-project-list", "calendar-days"),
    ("construction-progress", "Progress tracking", False, "construction-dashboard", "trending-up"),
]

ROLES = [
    ("organization-admin", "Organization Administrator"),
    ("construction-director", "Construction Director"),
    ("project-manager", "Project Manager"),
    ("site-engineer", "Site Engineer"),
    ("planning-engineer", "Planning Engineer"),
    ("quantity-surveyor", "Quantity Surveyor"),
    ("document-controller", "Document Controller"),
    ("foreman", "Foreman/Supervisor"),
    ("client-viewer", "Client/Consultant Viewer"),
]

PERMISSIONS = [
    ("view", "View"), ("create", "Create"), ("change", "Change"),
    ("delete", "Delete"), ("manage", "Manage"),
]


def seed_construction_catalog(apps, schema_editor):
    Category = apps.get_model("accounts", "OrganizationCategory")
    Template = apps.get_model("accounts", "SystemTemplate")
    Module = apps.get_model("accounts", "ModuleDefinition")
    TemplateModule = apps.get_model("accounts", "TemplateModule")
    Permission = apps.get_model("accounts", "ModulePermission")
    RoleTemplate = apps.get_model("accounts", "RoleTemplate")
    RoleTemplatePermission = apps.get_model("accounts", "RoleTemplatePermission")
    Navigation = apps.get_model("accounts", "TemplateNavigationItem")
    Widget = apps.get_model("accounts", "TemplateDashboardWidget")

    category = Category.objects.get(code="construction")
    template, _ = Template.objects.get_or_create(
        code="construction-management",
        version="1.0",
        defaults={
            "name": "Construction project management",
            "description": "A construction workspace for projects, teams, locations and delivery progress.",
            "category": category,
        },
    )
    module_map = {}
    for order, (code, name, required, url_name, icon) in enumerate(MODULES):
        module, _ = Module.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": f"{name} for construction organizations.",
                "is_core": required,
                "navigation_label": name,
                "navigation_url_name": url_name,
                "navigation_icon": icon,
                "navigation_order": order,
            },
        )
        module_map[code] = module
        TemplateModule.objects.get_or_create(
            system_template=template,
            module=module,
            defaults={"required": required, "enabled_by_default": True},
        )
        Navigation.objects.get_or_create(
            system_template=template,
            url_name=url_name,
            defaults={"module": module, "label": name, "icon": icon, "display_order": order},
        )

    permissions = {}
    for module in module_map.values():
        for action, label in PERMISSIONS:
            permission, _ = Permission.objects.get_or_create(
                code=f"{module.code}.{action}",
                defaults={"module": module, "name": f"{label} {module.name}"},
            )
            permissions[(module.code, action)] = permission

    for code, name in ROLES:
        role, _ = RoleTemplate.objects.get_or_create(
            system_template=template,
            code=code,
            defaults={"name": name, "description": f"Construction role: {name}."},
        )
        if code in {"organization-admin", "construction-director"}:
            selected = permissions.values()
        elif code == "project-manager":
            selected = [p for (module, action), p in permissions.items() if module in {"construction-projects", "construction-project-directory", "construction-locations", "construction-tasks", "construction-team", "construction-schedule", "construction-progress"} and action in {"view", "create", "change", "manage"}]
        elif code == "client-viewer":
            selected = [p for (module, action), p in permissions.items() if action == "view" and module in {"construction-projects", "construction-project-directory", "construction-locations", "construction-progress"}]
        else:
            selected = [p for (module, action), p in permissions.items() if action in {"view", "create", "change"} and module in {"construction-projects", "construction-project-directory", "construction-locations", "construction-tasks", "construction-team"}]
        for permission in selected:
            RoleTemplatePermission.objects.get_or_create(role_template=role, permission=permission)

    widgets = [
        ("active-projects", "Active projects", "construction.active-projects", "construction-projects"),
        ("project-status", "Project status", "construction.project-status", "construction-projects"),
        ("contract-value", "Contract value", "construction.contract-value", "construction-projects"),
        ("recent-activity", "Recent activity", "construction.recent-activity", "construction-audit"),
    ]
    for order, (code, title, component_key, module_code) in enumerate(widgets):
        Widget.objects.get_or_create(
            system_template=template,
            code=code,
            defaults={"module": module_map[module_code], "title": title, "component_key": component_key, "display_order": order},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_company_city_company_currency_code_and_more"),
        ("construction", "0001_initial"),
    ]
    operations = [migrations.RunPython(seed_construction_catalog, migrations.RunPython.noop)]
