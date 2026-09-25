from django.db import migrations


MODULES = [
    ("dashboard", "Dashboard", ["view"]),
    ("products", "Products", ["view", "create", "change", "cost"]),
    ("locations", "Store locations", ["view", "create", "change"]),
    ("inventory", "Inventory", ["view", "adjust"]),
    ("suppliers", "Suppliers", ["view", "create", "change"]),
    ("customers", "Customers", ["view", "create", "change"]),
    ("purchases", "Purchases", ["view", "create", "change", "post"]),
    ("sales", "Sales and returns", ["view", "view_all", "create", "change", "post", "refund", "price_override"]),
    ("reports", "Reports", ["view", "export"]),
    ("roles", "Roles and permissions", ["view", "manage"]),
    ("audit", "Audit activity", ["view"]),
]


def seed_retail(apps, schema_editor):
    db = schema_editor.connection.alias
    Template = apps.get_model("accounts", "SystemTemplate")
    Module = apps.get_model("accounts", "ModuleDefinition")
    Installation = apps.get_model("accounts", "TemplateModule")
    Permission = apps.get_model("accounts", "ModulePermission")
    Role = apps.get_model("accounts", "RoleTemplate")
    RolePermission = apps.get_model("accounts", "RoleTemplatePermission")
    Navigation = apps.get_model("accounts", "TemplateNavigationItem")
    template = Template.objects.using(db).get(code="retail-management", version="1.0")
    template.name = "Retail Management"
    template.description = "Manage products, store inventory, purchases, sales and returns in one retail workspace."
    template.is_active = True
    template.save(using=db, update_fields=["name", "description", "is_active"])
    permissions = {}
    for order, (suffix, name, actions) in enumerate(MODULES):
        code = f"rt-{suffix}"
        module, _ = Module.objects.using(db).get_or_create(code=code, defaults={
            "name": name, "description": f"{name} for Retail Management.",
            "navigation_label": name, "navigation_url_name": code, "navigation_order": order,
        })
        Installation.objects.using(db).get_or_create(system_template=template, module=module,
                                                    defaults={"required": suffix != "reports", "enabled_by_default": True})
        for action in actions:
            permission, _ = Permission.objects.using(db).get_or_create(code=f"{code}.{action}", defaults={
                "module": module, "name": f"{action.replace('_', ' ').capitalize()} {name}",
            })
            permissions[permission.code] = permission
        Navigation.objects.using(db).get_or_create(system_template=template, url_name=code, defaults={
            "module": module, "label": name, "display_order": order, "required_permission": permissions[f"{code}.view"],
        })
    view = {code for code in permissions if code.endswith(".view")}
    rules = {
        "organization-admin": ("Organization Administrator", set(permissions)),
        "store-manager": ("Store Manager", set(permissions) - {"rt-roles.manage"}),
        "cashier": ("Cashier", {"rt-dashboard.view", "rt-products.view", "rt-locations.view", "rt-inventory.view",
                                  "rt-customers.view", "rt-customers.create", "rt-customers.change", "rt-sales.view",
                                  "rt-sales.create", "rt-sales.change", "rt-sales.post"}),
        "inventory-controller": ("Inventory Controller", {code for code in permissions if code.startswith(("rt-products.", "rt-locations.", "rt-inventory.", "rt-purchases.", "rt-suppliers."))} | {"rt-dashboard.view"}),
        "purchasing-officer": ("Purchasing Officer", {code for code in permissions if code.startswith(("rt-purchases.", "rt-suppliers."))} | {"rt-dashboard.view", "rt-products.view", "rt-products.cost", "rt-locations.view", "rt-inventory.view"}),
        "read-only-auditor": ("Read-only Auditor", view | {"rt-products.cost", "rt-sales.view_all", "rt-reports.export"}),
    }
    for code, (name, selected) in rules.items():
        role, _ = Role.objects.using(db).get_or_create(system_template=template, code=code, defaults={"name": name})
        for permission_code in selected:
            RolePermission.objects.using(db).get_or_create(role_template=role, permission=permissions[permission_code])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0016_seed_professional_services_catalog")]
    operations = [migrations.RunPython(seed_retail, migrations.RunPython.noop)]
