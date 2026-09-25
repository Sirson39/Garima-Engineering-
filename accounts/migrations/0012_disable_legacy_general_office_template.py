from django.db import migrations


def disable_legacy_general_office(apps, schema_editor):
    Template = apps.get_model("accounts", "SystemTemplate")
    Template.objects.using(schema_editor.connection.alias).filter(
        code="general-office",
        version="1.0",
    ).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0011_seed_general_office_catalog")]
    operations = [migrations.RunPython(disable_legacy_general_office, migrations.RunPython.noop)]
