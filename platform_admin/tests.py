from django.test import TestCase
from django.urls import reverse

from accounts.models import Company, OrganizationMembership, User


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
                "initial_password": "Temporary123!",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("platform-dashboard"))
        self.assertTrue(Company.objects.filter(slug="abc-engineering").exists())

    def test_company_creation_provisions_only_first_admin_account(self):
        self.client.force_login(self.platform_admin)
        response = self.client.post(
            reverse("platform-company-create"),
            {
                "name": "XYZ Engineering Services",
                "slug": "xyz-engineering-services",
                "admin_email": "admin@xyz.test",
                "initial_password": "Temporary123!",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("platform-dashboard"))
        company = Company.objects.get(slug="xyz-engineering-services")
        self.assertEqual(OrganizationMembership.objects.filter(organization=company).count(), 1)
        self.assertEqual(User.objects.filter(company=company, must_change_password=True).count(), 1)

        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"email": "admin@xyz.test", "password": "Temporary123!"},
        )
        self.assertRedirects(response, reverse("password-change"))

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
