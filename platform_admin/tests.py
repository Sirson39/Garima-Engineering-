from django.test import TestCase
from django.urls import reverse

from accounts.models import Company, OrganizationMembership, PlatformRole, User
from projects.models import Client, Project
from workflows.models import NumberingScheme, ServiceType


class PlatformAdministrationTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_user(
            username="platform-admin",
            password="safe-test-password",
            is_platform_admin=True,
        )
        self.employee = User.objects.create_user(
            username="employee",
            email="employee@example.com",
            password="safe-test-password",
        )

    def test_platform_admin_can_open_dashboard(self):
        self.client.force_login(self.platform_admin)
        response = self.client.get(reverse("platform-dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_platform_root_is_neutral_landing_page(self):
        response = self.client.get(reverse("platform-landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Work Email")
        self.assertContains(response, "Work Email")

    def test_application_root_is_neutral_platform_landing(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Work Email")

    def test_unauthenticated_platform_user_is_sent_to_platform_login(self):
        response = self.client.get(reverse("platform-dashboard"))
        self.assertRedirects(response, f"{reverse('platform-login')}?next={reverse('platform-dashboard')}")

    def test_unified_login_routes_regular_user_without_membership_to_access_message(self):
        response = self.client.post(
            reverse("platform-login"),
            {"email": self.employee.email, "password": "safe-test-password"},
        )
        self.assertRedirects(response, reverse("access-denied"))

    def test_regular_employee_cannot_open_dashboard(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("platform-dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_platform_admin_can_create_company(self):
        self.client.force_login(self.platform_admin)
        response = self.client.post(
            reverse("platform-company-create"),
            {
                "name": "ABC Engineering Consultancy",
                "slug": "abc-engineering",
                "admin_email": "admin@abc.test",
                "admin_full_name": "ABC Administrator",
                "admin_job_title": "Organization Administrator",
                "is_active": "True",
            },
        )
        self.assertRedirects(response, reverse("platform-dashboard"))
        self.assertTrue(Company.objects.filter(slug="abc-engineering").exists())

    def test_platform_admin_sees_six_step_creation_wizard_with_temporary_password_field(self):
        self.client.force_login(self.platform_admin)

        response = self.client.get(reverse("platform-company-create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "STEP 1 OF 6")
        self.assertContains(response, "System template")
        self.assertContains(response, "Review and create")
        self.assertContains(response, "Temporary first-login password")

    def test_company_creation_provisions_only_first_admin_account(self):
        self.client.force_login(self.platform_admin)
        response = self.client.post(
            reverse("platform-company-create"),
            {
                "name": "XYZ Engineering Services",
                "slug": "xyz-engineering-services",
                "admin_email": "admin@xyz.test",
                "admin_full_name": "XYZ Administrator",
                "admin_job_title": "Organization Administrator",
                "is_active": "True",
            },
        )
        self.assertRedirects(response, reverse("platform-dashboard"))
        company = Company.objects.get(slug="xyz-engineering-services")
        self.assertEqual(OrganizationMembership.objects.filter(organization=company).count(), 1)
        first_admin = User.objects.get(company=company, email="admin@xyz.test")
        self.assertTrue(first_admin.has_usable_password())
        self.assertTrue(first_admin.must_change_password)

        invitation = company.invitations.get()
        self.assertIsNone(invitation.accepted_at)
        self.assertTrue(company.memberships.get().is_active)

    def test_company_admin_can_create_engineer_or_staff(self):
        company = Company.objects.create(name="Client Company", slug="client-company")
        admin = User.objects.create_user(
            username="client-admin@test.com",
            email="client-admin@test.com",
            password="safe-test-password",
            company=company,
            company_role=User.ROLE_ADMIN,
        )
        OrganizationMembership.objects.create(user=admin, organization=company, role="admin")
        self.client.force_login(admin)
        response = self.client.post(
            reverse("organization-user-create"),
            {"email": "engineer@client.test", "role": "engineer", "initial_password": "Temporary123!"},
        )
        self.assertRedirects(response, reverse("users-roles"))
        self.assertTrue(User.objects.filter(email="engineer@client.test", company=company).exists())

    def test_platform_admin_can_remove_company_with_post(self):
        company = Company.objects.create(name="Remove Me Engineering", slug="remove-me-engineering")
        membership_user = User.objects.create_user(
            username="remove-me-admin@test.com",
            email="remove-me-admin@test.com",
            password="safe-test-password",
            company=company,
            company_role=User.ROLE_ADMIN,
        )
        OrganizationMembership.objects.create(user=membership_user, organization=company, role="admin")
        self.client.force_login(self.platform_admin)

        response = self.client.post(reverse("platform-company-remove", args=[company.pk]))

        self.assertRedirects(response, reverse("platform-dashboard"))
        self.assertFalse(Company.objects.filter(pk=company.pk).exists())
        self.assertFalse(OrganizationMembership.objects.filter(organization_id=company.pk).exists())
        self.assertFalse(User.objects.filter(pk=membership_user.pk).exists())
        self.assertFalse(User.objects.filter(email="remove-me-admin@test.com").exists())

    def test_removing_company_and_admin_preserves_dashboard_records_and_frees_email(self):
        company = Company.objects.create(name="Garima Engineering", slug="garima-preserve-data")
        admin = User.objects.create_user(
            username="admin@gec.com.np",
            email="admin@gec.com.np",
            password="safe-test-password",
            company=company,
            company_role=User.ROLE_ADMIN,
        )
        OrganizationMembership.objects.create(user=admin, organization=company, role="admin")
        PlatformRole.objects.create(user=admin)
        client_record = Client.objects.create(
            full_name="Dashboard Client",
            mobile_number="9800000000",
            created_by=admin,
        )
        service_type = ServiceType.objects.create(code="KEEP", name="Preserved service")
        NumberingScheme.objects.create(service_type=service_type, service_code="KEEP")
        project_record = Project.objects.create(
            service_type=service_type,
            client=client_record,
            created_by=admin,
            updated_by=admin,
        )
        self.client.force_login(self.platform_admin)

        response = self.client.post(reverse("platform-company-remove", args=[company.pk]))

        self.assertRedirects(response, reverse("platform-dashboard"))
        self.assertFalse(Company.objects.filter(pk=company.pk).exists())
        self.assertFalse(User.objects.filter(email="admin@gec.com.np").exists())
        self.assertTrue(Client.objects.filter(pk=client_record.pk, full_name="Dashboard Client").exists())
        self.assertTrue(Project.objects.filter(pk=project_record.pk).exists())
        project_record.refresh_from_db()
        client_record.refresh_from_db()
        self.assertIsNone(project_record.created_by_id)
        self.assertIsNone(project_record.updated_by_id)
        self.assertIsNone(client_record.created_by_id)

        replacement_admin = User.objects.create_user(
            username="admin@gec.com.np",
            email="admin@gec.com.np",
            password="replacement-password",
        )
        self.assertEqual(replacement_admin.email, "admin@gec.com.np")

    def test_removing_company_preserves_user_who_belongs_to_another_company(self):
        company = Company.objects.create(name="Remove Me", slug="remove-me-shared")
        other_company = Company.objects.create(name="Keep Me", slug="keep-me-shared")
        shared_user = User.objects.create_user(
            username="shared-admin@test.com",
            email="shared-admin@test.com",
            password="safe-test-password",
            company=company,
            company_role=User.ROLE_ADMIN,
        )
        OrganizationMembership.objects.create(user=shared_user, organization=company, role="admin")
        OrganizationMembership.objects.create(user=shared_user, organization=other_company, role="staff")
        self.client.force_login(self.platform_admin)

        response = self.client.post(reverse("platform-company-remove", args=[company.pk]))

        self.assertRedirects(response, reverse("platform-dashboard"))
        shared_user.refresh_from_db()
        self.assertEqual(shared_user.email, "shared-admin@test.com")
        self.assertIsNone(shared_user.company_id)
        self.assertFalse(OrganizationMembership.objects.filter(user=shared_user, organization=company).exists())
        self.assertTrue(OrganizationMembership.objects.filter(user=shared_user, organization=other_company).exists())

    def test_removing_company_preserves_platform_admin_account(self):
        company = Company.objects.create(name="Platform-linked", slug="platform-linked-org")
        protected_user = User.objects.create_user(
            username="protected-admin@test.com",
            email="protected-admin@test.com",
            password="safe-test-password",
            company=company,
            company_role=User.ROLE_ADMIN,
            is_platform_admin=True,
        )
        OrganizationMembership.objects.create(user=protected_user, organization=company, role="admin")
        self.client.force_login(self.platform_admin)

        response = self.client.post(reverse("platform-company-remove", args=[company.pk]))

        self.assertRedirects(response, reverse("platform-dashboard"))
        protected_user.refresh_from_db()
        self.assertEqual(protected_user.email, "protected-admin@test.com")
        self.assertIsNone(protected_user.company_id)
