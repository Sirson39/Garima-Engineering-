from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import OrganizationMembership, User


class Command(BaseCommand):
    help = "Remove an unprivileged organization admin account left orphaned after organization removal."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Exact email address of the orphaned organization account")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip()
        users = User.objects.select_for_update().filter(email__iexact=email)
        if users.count() != 1:
            raise CommandError(f"Expected exactly one account for {email}; no account was removed.")

        user = users.get()
        if user.is_superuser or user.is_platform_admin:
            raise CommandError("This account has platform administrator privileges; it was not removed.")
        if user.company_id or OrganizationMembership.objects.filter(user=user).exists():
            raise CommandError("This account is still attached to an organization; it was not removed.")

        user.delete()
        self.stdout.write(self.style.SUCCESS(f"Removed orphaned account {email}. Its email is now available."))
