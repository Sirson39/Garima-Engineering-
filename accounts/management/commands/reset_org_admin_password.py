from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import OrganizationMembership, User
from accounts.services import generate_temporary_password


class Command(BaseCommand):
    help = "Generate a one-time temporary password for an organization administrator."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Administrator email address")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        user = User.objects.filter(email__iexact=email, company__isnull=False).first()
        if not user:
            raise CommandError("No organization administrator was found for this email.")

        temporary_password = generate_temporary_password()
        user.set_password(temporary_password)
        user.is_active = True
        user.must_change_password = True
        user.save(update_fields=["password", "is_active", "must_change_password"])
        OrganizationMembership.objects.filter(user=user, organization=user.company).update(is_active=True)

        self.stdout.write(self.style.SUCCESS("Temporary credentials generated:"))
        self.stdout.write(f"Email: {user.email}")
        self.stdout.write(f"Temporary password: {temporary_password}")
        self.stdout.write("The administrator must change this password after first login.")
