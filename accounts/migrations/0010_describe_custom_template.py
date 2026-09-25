from django.db import migrations


def update_custom_description(apps, schema_editor):
    Template = apps.get_model("accounts", "SystemTemplate")
    Template.objects.using(schema_editor.connection.alias).filter(
        code="custom-organization",
        version="1.0",
    ).update(
        description="A controlled workspace builder for organizations with configurable modules, terminology and future records.",
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_custom_workspace_foundation")]
    operations = [migrations.RunPython(update_custom_description, migrations.RunPython.noop)]
