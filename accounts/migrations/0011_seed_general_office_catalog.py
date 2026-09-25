from django.db import migrations


MODULES = [
    ("office-dashboard", "Dashboard", True, "office-dashboard", "layout-dashboard"),
    ("office-staff", "Staff directory", True, "office-staff", "users"),
    ("office-departments", "Departments", True, "office-departments", "network"),
    ("office-roles", "Roles and permissions", True, "users-roles", "shield-check"),
    ("office-tasks", "Tasks", True, "tasks", "check-square"),
    ("office-documents", "Documents", True, "documents", "file-text"),
    ("office-notifications", "Notifications", True, "office-dashboard", "bell"),
    ("office-announcements", "Announcements", True, "office-dashboard", "megaphone"),
    ("office-audit", "Audit activity", True, "audit-logs", "history"),
    ("office-settings", "Organization settings", True, "system-settings", "settings"),
    ("office-clients", "Clients and contacts", False, "office-dashboard", "contact-round"),
    ("office-projects", "Internal projects", False, "office-dashboard", "briefcase"),
    ("office-calendar", "Calendar", False, "office-dashboard", "calendar-days"),
    ("office-meetings", "Meetings", False, "office-dashboard", "calendar-clock"),
    ("office-requests", "Requests and approvals", False, "office-dashboard", "inbox"),
    ("office-leave", "Leave management", False, "office-dashboard", "calendar-off"),
    ("office-attendance", "Attendance", False, "office-dashboard", "clock-3"),
    ("office-expenses", "Expenses", False, "office-dashboard", "receipt"),
    ("office-assets", "Assets", False, "office-dashboard", "package"),
    ("office-reports", "Reports", False, "reports", "bar-chart-3"),
    ("office-suppliers", "Suppliers", False, "office-dashboard", "truck"),
    ("office-purchase-requests", "Purchase requests", False, "office-dashboard", "shopping-cart"),
    ("office-inventory", "Inventory", False, "office-dashboard", "boxes"),
    ("office-visitor-management", "Visitor management", False, "office-dashboard", "user-round-check"),
    ("office-correspondence", "Correspondence", False, "office-dashboard", "mail"),
    ("office-support", "Support tickets", False, "office-dashboard", "messages-square"),
    ("office-timesheets", "Timesheets", False, "office-dashboard", "timer"),
    ("office-knowledge-base", "Knowledge base", False, "office-dashboard", "book-open"),
    ("office-training", "Training records", False, "office-dashboard", "graduation-cap"),
    ("office-onboarding", "Employee onboarding", False, "office-dashboard", "user-plus"),
    ("office-offboarding", "Employee offboarding", False, "office-dashboard", "user-minus"),
]

ROLES = [
    ("organization-owner", "Organization Owner"),
    ("organization-admin", "Organization Administrator"),
    ("office-manager", "Office Manager"),
    ("department-manager", "Department Manager"),
    ("hr-officer", "HR Officer"),
    ("accounts-officer", "Accounts Officer"),
    ("document-controller", "Document Controller"),
    ("asset-manager", "Asset Manager"),
    ("reception-officer", "Reception Officer"),
    ("project-manager", "Project Manager"),
    ("staff", "Staff"),
    ("read-only-auditor", "Read-only Auditor"),
]


def seed_general_office(apps, schema_editor):
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

    category = Category.objects.using(db).get(code="general-office")
    template, _ = Template.objects.using(db).get_or_create(
        code="general-office-management",
        version="1.0",
        defaults={
            "name": "General office management",
            "description": "A ready-to-use workspace for staff, departments, tasks, documents and office operations.",
            "category": category,
        },
    )
    Template.objects.using(db).filter(pk=template.pk).update(
        name="General office management",
        description="A ready-to-use workspace for staff, departments, tasks, documents and office operations.",
        category=category,
        is_active=True,
    )

    module_map = {}
    for order, (code, name, required, url_name, icon) in enumerate(MODULES):
        module, _ = Module.objects.using(db).get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": f"{name} for General Office organizations.",
                "is_core": required,
                "navigation_label": name,
                "navigation_url_name": url_name,
                "navigation_icon": icon,
                "navigation_order": order,
            },
        )
        module_map[code] = module
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

    for order, (code, name, required, url_name, icon) in enumerate(MODULES):
        if url_name in {"office-dashboard", "office-staff", "office-departments"}:
            Navigation.objects.using(db).get_or_create(
                system_template=template,
                url_name=url_name,
                defaults={"module": module_map[code], "label": name, "icon": icon, "display_order": order},
            )

    permissions = {
        permission.code: permission
        for permission in Permission.objects.using(db).filter(module__in=module_map.values())
    }
    for role_code, role_name in ROLES:
        role, _ = RoleTemplate.objects.using(db).get_or_create(
            system_template=template,
            code=role_code,
            defaults={"name": role_name, "description": f"General Office role: {role_name}."},
        )
        if role_code in {"organization-owner", "organization-admin"}:
            selected = permissions.values()
        elif role_code == "read-only-auditor":
            selected = [permission for code, permission in permissions.items() if code.endswith(".view") or code == "office-audit.view"]
        elif role_code in {"office-manager", "department-manager"}:
            selected = [permission for code, permission in permissions.items() if code.endswith((".view", ".create", ".change", ".manage"))]
        else:
            selected = [permission for code, permission in permissions.items() if code.endswith(".view") and permission.module_id in {module_map["office-dashboard"].pk, module_map["office-staff"].pk, module_map["office-departments"].pk, module_map["office-tasks"].pk, module_map["office-documents"].pk, module_map["office-notifications"].pk, module_map["office-announcements"].pk}]
        for permission in selected:
            RoleTemplatePermission.objects.using(db).get_or_create(role_template=role, permission=permission)

    widgets = [
        ("active-staff", "Active staff", "office.active-staff", "office-staff"),
        ("departments", "Departments", "office.departments", "office-departments"),
        ("open-tasks", "Open tasks", "office.open-tasks", "office-tasks"),
        ("recent-activity", "Recent activity", "office.recent-activity", "office-audit"),
    ]
    for order, (code, title, component_key, module_code) in enumerate(widgets):
        Widget.objects.using(db).get_or_create(
            system_template=template,
            code=code,
            defaults={"module": module_map[module_code], "title": title, "component_key": component_key, "display_order": order},
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0010_describe_custom_template")]
    operations = [migrations.RunPython(seed_general_office, migrations.RunPython.noop)]
