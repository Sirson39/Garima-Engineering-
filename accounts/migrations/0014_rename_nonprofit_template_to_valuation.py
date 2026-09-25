from django.db import migrations


def rename_template(apps, schema_editor):
    Template = apps.get_model("accounts", "SystemTemplate")
    Template.objects.using(schema_editor.connection.alias).filter(
        code="non-profit-management",
        version="1.0",
    ).update(
        name="Valuation management",
        description="A future workspace template for valuation and assessment organizations.",
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_seed_hospital_management_catalog")]
    operations = [migrations.RunPython(rename_template, migrations.RunPython.noop)]
