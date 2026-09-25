from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.models import (
    Company,
    CustomStartingStructure,
    ModuleDefinition,
    OrganizationCategory,
    OrganizationConfiguration,
    OrganizationMembership,
    OrganizationTerminology,
    PlatformRole,
    SystemTemplate,
    TemplateModule,
    User,
)
from accounts.services import ProvisioningError, provision_organization
from core.models import LoginAttempt


class LoginAttemptTests(TestCase):
    def test_register_failure_locks_account_after_threshold(self):
        attempt, _ = LoginAttempt.objects.get_or_create(identifier="demo", ip_address="127.0.0.1")
        attempt.register_failure(limit=2, window_minutes=10)
        self.assertFalse(attempt.is_locked())
        attempt.register_failure(limit=2, window_minutes=10)
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_locked())
        self.assertIsNotNone(attempt.locked_until)


class OrganizationCatalogTests(TestCase):
    def test_seeded_engineering_template_has_core_and_workflow_modules(self):
        category = OrganizationCategory.objects.get(code="engineering")
        template = SystemTemplate.objects.get(code="engineering-consultancy", version="1.0")

        self.assertEqual(template.category, category)
        module_codes = set(template.template_modules.values_list("module__code", flat=True))
        self.assertTrue(
            {
                "organization-core",
                "team-access",
                "audit-activity",
                "clients",
                "projects",
                "document-control",
                "workflow-tasks",
                "site-visits",
                "government-submissions",
                "municipality-records",
                "physical-file-tracking",
                "project-payments",
                "reports",
            }.issubset(module_codes)
        )
        self.assertSetEqual(
            module_codes - {
                "valuation-management",
                "valuation-requests",
                "valuation-documents",
                "valuation-workflow",
                "valuation-banks",
                "valuation-audit",
            },
            {
                "organization-core",
                "team-access",
                "audit-activity",
                "clients",
                "projects",
                "document-control",
                "workflow-tasks",
                "site-visits",
                "government-submissions",
                "municipality-records",
                "physical-file-tracking",
                "project-payments",
                "reports",
            },
        )
        self.assertTrue(
            {
                "valuation-management",
                "valuation-requests",
                "valuation-documents",
                "valuation-workflow",
                "valuation-banks",
                "valuation-audit",
            }.issubset(module_codes)
        )
        self.assertEqual(
            TemplateModule.objects.filter(system_template=template, required=True).count(),
            3,
        )


class OrphanedOrganizationAdminCleanupTests(TestCase):
    def test_command_removes_unprivileged_orphan_and_its_stale_platform_role(self):
        user = User.objects.create_user(
            username="admin@gec.com.np",
            email="admin@gec.com.np",
            password="safe-test-password",
        )
        PlatformRole.objects.create(user=user)

        call_command("remove_orphaned_org_admin", "admin@gec.com.np", stdout=StringIO())

        self.assertFalse(User.objects.filter(email__iexact="admin@gec.com.np").exists())
        self.assertFalse(PlatformRole.objects.filter(user_id=user.pk).exists())
        replacement = User.objects.create_user(
            username="admin@gec.com.np",
            email="admin@gec.com.np",
            password="replacement-password",
        )
        self.assertEqual(replacement.email, "admin@gec.com.np")

    def test_command_refuses_an_account_still_attached_to_an_organization(self):
        from accounts.models import Company

        company = Company.objects.create(name="Still Active", slug="still-active")
        user = User.objects.create_user(
            username="attached@example.com",
            email="attached@example.com",
            password="safe-test-password",
            company=company,
        )
        OrganizationMembership.objects.create(user=user, organization=company, role="admin")

        with self.assertRaises(CommandError):
            call_command("remove_orphaned_org_admin", "attached@example.com", stdout=StringIO())

        self.assertTrue(User.objects.filter(pk=user.pk).exists())


class OrganizationProvisioningTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            username="platform-admin",
            email="platform@example.com",
            password="safe-test-password",
            is_platform_admin=True,
        )
        self.template = SystemTemplate.objects.get(code="engineering-consultancy", version="1.0")

    def test_engineering_provisioning_creates_isolated_workspace_and_invitation(self):
        modules = set(
            TemplateModule.objects.filter(system_template=self.template).values_list("module__code", flat=True)
        )

        organization = provision_organization(
            actor=self.actor,
            organization_data={
                "name": "Provisioned Engineering",
                "legal_name": "Provisioned Engineering Pvt. Ltd.",
                "slug": "provisioned-engineering",
                "organization_code": "provisioned-engineering",
                "is_active": True,
            },
            template=self.template,
            module_codes=modules,
            branding_data={},
            admin_data={
                "email": "admin@provisioned.test",
                "full_name": "Provisioned Admin",
                "job_title": "Director",
                "phone": "9800000000",
            },
        )

        self.assertEqual(organization.system_template, self.template)
        self.assertEqual(organization.provisioning_status, "ready")
        self.assertEqual(organization.enabled_modules.count(), len(modules))
        self.assertEqual(organization.memberships.count(), 1)
        self.assertTrue(organization.memberships.first().is_active)
        self.assertEqual(organization.invitations.count(), 1)
        provisioned_admin = User.objects.get(email="admin@provisioned.test")
        self.assertTrue(provisioned_admin.has_usable_password())
        self.assertTrue(provisioned_admin.must_change_password)

    def test_missing_required_module_rolls_back_everything(self):
        required = set(
            TemplateModule.objects.filter(system_template=self.template, required=True)
            .values_list("module__code", flat=True)
        )

        with self.assertRaises(ProvisioningError):
            provision_organization(
                actor=self.actor,
                organization_data={"name": "Broken", "slug": "broken", "organization_code": "broken"},
                template=self.template,
                module_codes=required - {next(iter(required))},
                branding_data={},
                admin_data={"email": "broken@example.com"},
            )

        self.assertFalse(Company.objects.filter(slug="broken").exists())
        self.assertFalse(User.objects.filter(email="broken@example.com").exists())

    def test_custom_catalog_has_locked_core_and_starting_structures(self):
        template = SystemTemplate.objects.get(code="custom-organization", version="1.0")
        core_codes = set(
            TemplateModule.objects.filter(system_template=template, required=True)
            .values_list("module__code", flat=True)
        )

        self.assertEqual(len(core_codes), 9)
        self.assertTrue(CustomStartingStructure.objects.filter(code="project-based").exists())
        self.assertTrue(ModuleDefinition.objects.filter(code="custom-projects", available_for_custom=True).exists())

    def test_custom_provisioning_creates_configuration_and_terminology(self):
        template = SystemTemplate.objects.get(code="custom-organization", version="1.0")
        structure = CustomStartingStructure.objects.get(code="client-service")
        modules = set(
            TemplateModule.objects.filter(system_template=template, enabled_by_default=True)
            .values_list("module__code", flat=True)
        )
        organization = provision_organization(
            actor=self.actor,
            organization_data={
                "name": "Custom Services",
                "slug": "custom-services",
                "organization_code": "custom-services",
                "is_active": True,
            },
            template=template,
            module_codes=modules,
            branding_data={},
            admin_data={"email": "custom-admin@example.com", "full_name": "Custom Admin"},
            custom_starting_structure=structure,
        )

        configuration = OrganizationConfiguration.objects.get(organization=organization)
        self.assertEqual(configuration.status, OrganizationConfiguration.STATUS_PUBLISHED)
        self.assertEqual(configuration.starting_structure, structure)
        self.assertEqual(OrganizationTerminology.objects.filter(organization=organization).count(), 5)

    def test_custom_provisioning_rejects_unknown_module(self):
        template = SystemTemplate.objects.get(code="custom-organization", version="1.0")

        with self.assertRaises(ProvisioningError):
            provision_organization(
                actor=self.actor,
                organization_data={"name": "Unsafe Custom", "slug": "unsafe-custom", "organization_code": "unsafe-custom"},
                template=template,
                module_codes={"custom-authentication", "engineering-projects"},
                branding_data={},
                admin_data={"email": "unsafe-custom@example.com"},
            )

        self.assertFalse(Company.objects.filter(slug="unsafe-custom").exists())

    def test_general_office_provisioning_creates_staff_profile(self):
        from office.models import OfficeStaffProfile

        template = SystemTemplate.objects.get(code="general-office-management", version="1.0")
        modules = set(
            TemplateModule.objects.filter(system_template=template)
            .values_list("module__code", flat=True)
        )
        organization = provision_organization(
            actor=self.actor,
            organization_data={
                "name": "Office Provisioned",
                "slug": "office-provisioned",
                "organization_code": "office-provisioned",
                "is_active": True,
            },
            template=template,
            module_codes=modules,
            branding_data={},
            admin_data={"email": "office-admin@example.com", "full_name": "Office Administrator"},
        )

        profile = OfficeStaffProfile.objects.get(organization=organization)
        self.assertEqual(profile.employee_id, f"ADMIN-{profile.user_id:04d}")
        self.assertEqual(profile.user.email, "office-admin@example.com")

    def test_hospital_template_has_simple_operations_catalog(self):
        template = SystemTemplate.objects.get(code="hospital-management", version="1.0")
        modules = set(TemplateModule.objects.filter(system_template=template).values_list("module__code", flat=True))

        self.assertEqual(template.name, "Hospital management")
        self.assertIn("hospital-patients", modules)
        self.assertIn("hospital-appointments", modules)
        self.assertIn("hospital-queue", modules)
        self.assertNotIn("hospital-prescriptions", modules)
        self.assertEqual(TemplateModule.objects.filter(system_template=template, required=True).count(), 13)
