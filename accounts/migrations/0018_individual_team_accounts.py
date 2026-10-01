from django.db import migrations, models
from django.db.models.functions import Lower


LEGACY_GROUPS = [
    "System Administrator", "Director/Management", "Reception/Document Officer",
    "Project Manager", "Planning Engineer", "Structural Engineer", "Site Engineer",
    "Online Processing Officer", "Municipality File Handler", "Accounts Officer", "Read-only/Auditor",
]


def remove_legacy_groups(apps, schema_editor):
    # Only the old demo permission groups; preserve users, memberships and other templates.
    apps.get_model("auth", "Group").objects.using(schema_editor.connection.alias).filter(name__in=LEGACY_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0017_seed_retail_catalog")]
    operations = [
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(Lower("email"), condition=~models.Q(email=""), name="unique_user_login_email_ci"),
        ),
        migrations.RunPython(remove_legacy_groups, migrations.RunPython.noop),
    ]
