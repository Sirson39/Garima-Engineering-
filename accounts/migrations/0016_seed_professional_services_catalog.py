from django.db import migrations


MODULES = [
    ("ps-dashboard", "Dashboard", "ps-dashboard", ["view"]),
    ("ps-clients", "Clients", "ps-clients", ["view", "create", "change", "view_all"]),
    ("ps-services", "Services", "ps-services", ["view", "create", "change"]),
    ("ps-engagements", "Engagements", "ps-engagements", ["view", "create", "change", "view_all"]),
    ("ps-roles", "Roles and permissions", "ps-roles", ["view", "manage", "settings"]),
    ("ps-audit", "Audit Activity", "ps-audit", ["view"]),
]

ROLES = [
    ("organization-admin", "Organization Administrator"),
    ("director", "Managing Partner / Director"),
    ("account-manager", "Account Manager"),
    ("engagement-manager", "Engagement Manager"),
    ("consultant", "Consultant / Professional"),
    ("reviewer", "Reviewer"),
    ("accounts-officer", "Accounts Officer"),
    ("document-controller", "Document Controller"),
    ("client-portal-user", "Client Portal User"),
    ("read-only-auditor", "Read-only Auditor"),
]


def seed_catalog(apps, schema_editor):
    db = schema_editor.connection.alias
    Template = apps.get_model("accounts", "SystemTemplate")
    Module = apps.get_model("accounts", "ModuleDefinition")
    TemplateModule = apps.get_model("accounts", "TemplateModule")
    Permission = apps.get_model("accounts", "ModulePermission")
    Role = apps.get_model("accounts", "RoleTemplate")
    RolePermission = apps.get_model("accounts", "RoleTemplatePermission")
    Navigation = apps.get_model("accounts", "TemplateNavigationItem")
    template = Template.objects.using(db).get(code="professional-services", version="1.0")
    template.name = "Professional Service Management"
    template.description = "Manage clients, services and engagements for consulting, legal, accounting, IT and creative teams."
    template.is_active = True
    template.save(using=db, update_fields=["name", "description", "is_active"])
    permissions = {}
    for order, (code, name, route, actions) in enumerate(MODULES):
        module, _ = Module.objects.using(db).get_or_create(code=code, defaults={
            "name": name, "description": f"{name} for Professional Service Management.",
            "navigation_label": name, "navigation_url_name": route, "navigation_order": order,
        })
        TemplateModule.objects.using(db).get_or_create(system_template=template, module=module,
                                                      defaults={"required": True, "enabled_by_default": True})
        for action in actions:
            permission, _ = Permission.objects.using(db).get_or_create(code=f"{code}.{action}", defaults={
                "module": module, "name": f"{action.replace('_', ' ').capitalize()} {name}",
            })
            permissions[permission.code] = permission
        Navigation.objects.using(db).get_or_create(system_template=template, url_name=route, defaults={
            "module": module, "label": name, "display_order": order,
            "required_permission": permissions[f"{code}.view"],
        })
        if code == "ps-roles":
            Navigation.objects.using(db).get_or_create(system_template=template, url_name="ps-settings", defaults={
                "module": module, "label": "Settings", "display_order": 9,
                "required_permission": permissions["ps-roles.settings"],
            })
    base = {"ps-dashboard.view", "ps-clients.view", "ps-services.view", "ps-engagements.view"}
    for code, name in ROLES:
        role, _ = Role.objects.using(db).get_or_create(system_template=template, code=code, defaults={"name": name})
        selected = set(base)
        if code == "organization-admin":
            selected = set(permissions)
        elif code == "director":
            selected = set(permissions) - {"ps-roles.manage", "ps-roles.settings"}
        elif code == "account-manager":
            selected |= {"ps-clients.create", "ps-clients.change", "ps-engagements.create", "ps-engagements.change", "ps-audit.view"}
        elif code == "engagement-manager":
            selected |= {"ps-engagements.create", "ps-engagements.change", "ps-audit.view"}
        elif code == "read-only-auditor":
            selected |= {"ps-clients.view_all", "ps-engagements.view_all", "ps-audit.view", "ps-roles.view"}
        elif code == "client-portal-user":
            selected = set()
        for permission_code in selected:
            RolePermission.objects.using(db).get_or_create(role_template=role, permission=permissions[permission_code])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_register_valuation_module")]
    operations = [migrations.RunPython(seed_catalog, migrations.RunPython.noop)]
