from django.db import migrations


MODULES = [
    ("hospital-dashboard", "Hospital dashboard", True, "dashboard", "layout-dashboard"),
    ("hospital-facilities", "Facilities and branches", True, "dashboard", "building-2"),
    ("hospital-departments", "Departments", True, "dashboard", "network"),
    ("hospital-staff", "Hospital staff", True, "dashboard", "users"),
    ("hospital-patients", "Patients", True, "dashboard", "user-round"),
    ("hospital-appointments", "Appointments", True, "dashboard", "calendar-days"),
    ("hospital-queue", "Queue management", True, "dashboard", "list-ordered"),
    ("hospital-documents", "Documents", True, "dashboard", "file-text"),
    ("hospital-roles", "Roles and permissions", True, "users-roles", "shield-check"),
    ("hospital-notifications", "Notifications", True, "dashboard", "bell"),
    ("hospital-consent", "Consent", True, "dashboard", "file-check-2"),
    ("hospital-audit", "Audit activity", True, "audit-logs", "history"),
    ("hospital-security", "Security settings", True, "system-settings", "lock-keyhole"),
    ("hospital-reports", "Operational reports", False, "reports", "bar-chart-3"),
]

ROLES = [
    ("healthcare-admin", "Hospital Administrator"),
    ("medical-director", "Medical Director"),
    ("doctor", "Doctor/Clinician"),
    ("nurse", "Nurse"),
    ("reception", "Reception Officer"),
    ("medical-records", "Medical Records Officer"),
    ("billing", "Billing Officer"),
    ("privacy-security", "Privacy/Security Officer"),
    ("read-only-auditor", "Read-only Auditor"),
]


def seed_hospital_catalog(apps, schema_editor):
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

    category = Category.objects.using(db).get(code="healthcare")
    template = Template.objects.using(db).get(code="hospital-management", version="1.0")
    Template.objects.using(db).filter(pk=template.pk).update(
        name="Hospital management",
        description="A simple private-hospital operations workspace for facilities, staff, patients and appointments.",
        category=category,
        is_active=True,
    )

    module_map = {}
    permissions = {}
    for order, (code, name, required, url_name, icon) in enumerate(MODULES):
        module, _ = Module.objects.using(db).get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": f"{name} for Hospital Management organizations.",
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
            permission, _ = Permission.objects.using(db).get_or_create(
                code=f"{code}.{action}",
                defaults={"module": module, "name": f"{label} {name}"},
            )
            permissions[(code, action)] = permission

    Navigation.objects.using(db).get_or_create(
        system_template=template,
        url_name="dashboard",
        defaults={"module": module_map["hospital-dashboard"], "label": "Hospital dashboard", "icon": "layout-dashboard", "display_order": 0},
    )

    for role_code, role_name in ROLES:
        role, _ = RoleTemplate.objects.using(db).get_or_create(
            system_template=template,
            code=role_code,
            defaults={"name": role_name, "description": f"Hospital role: {role_name}."},
        )
        if role_code in {"healthcare-admin", "medical-director"}:
            selected = permissions.values()
        elif role_code == "read-only-auditor":
            selected = [permission for (module, action), permission in permissions.items() if action == "view"]
        else:
            selected = [permission for (module, action), permission in permissions.items() if action == "view" and module in {"hospital-dashboard", "hospital-staff", "hospital-patients", "hospital-appointments", "hospital-queue", "hospital-documents", "hospital-notifications", "hospital-consent"}]
        for permission in selected:
            RoleTemplatePermission.objects.using(db).get_or_create(role_template=role, permission=permission)

    for order, (code, title, component_key, module_code) in enumerate([
        ("appointments-today", "Appointments today", "hospital.appointments-today", "hospital-appointments"),
        ("patients-waiting", "Patients waiting", "hospital.patients-waiting", "hospital-queue"),
        ("available-staff", "Available staff", "hospital.available-staff", "hospital-staff"),
        ("recent-audit", "Recent audit activity", "hospital.recent-audit", "hospital-audit"),
    ]):
        Widget.objects.using(db).get_or_create(
            system_template=template,
            code=code,
            defaults={"module": module_map[module_code], "title": title, "component_key": component_key, "display_order": order},
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0012_disable_legacy_general_office_template")]
    operations = [migrations.RunPython(seed_hospital_catalog, migrations.RunPython.noop)]
