from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import PermissionDenied

from accounts.models import Company, OrganizationCategory, OrganizationMembership, SystemTemplate, User
from .models import ConstructionProject
from .services import construction_projects_for_user


class ConstructionFoundationTests(TestCase):
    def setUp(self):
        self.construction_template = SystemTemplate.objects.get(code="construction-management", version="1.0")
        self.engineering_template = SystemTemplate.objects.get(code="engineering-consultancy", version="1.0")
        self.category = OrganizationCategory.objects.get(code="construction")
        self.org_a = Company.objects.create(
            name="Build A", slug="build-a", organization_code="build-a", category=self.category,
            system_template=self.construction_template,
        )
        self.org_b = Company.objects.create(
            name="Build B", slug="build-b", organization_code="build-b", category=self.category,
            system_template=self.construction_template,
        )
        self.user = User.objects.create_user(
            username="manager@build-a.test", email="manager@build-a.test", password="safe-test-password", company=self.org_a,
        )
        OrganizationMembership.objects.create(user=self.user, organization=self.org_a, role="admin", is_active=True)
        self.other_user = User.objects.create_user(
            username="manager@build-b.test", email="manager@build-b.test", password="safe-test-password", company=self.org_b,
        )
        OrganizationMembership.objects.create(user=self.other_user, organization=self.org_b, role="admin", is_active=True)

    def test_construction_template_is_registered_with_phase_one_modules(self):
        self.assertEqual(self.construction_template.category.code, "construction")
        self.assertGreaterEqual(self.construction_template.template_modules.count(), 9)
        self.assertTrue(self.construction_template.template_modules.filter(required=True).exists())

    def test_engineering_template_remains_separate(self):
        self.assertEqual(self.engineering_template.category.code, "engineering")
        self.assertEqual(self.engineering_template.organizations.filter(system_template=self.construction_template).count(), 0)
        # Migration 0015 adds six optional valuation modules to the original 13.
        self.assertEqual(self.engineering_template.template_modules.count(), 19)

    def test_projects_are_isolated_by_organization(self):
        project_a = ConstructionProject.objects.create(
            organization=self.org_a, project_number="A-001", name="A project", project_manager=self.user,
        )
        ConstructionProject.objects.create(
            organization=self.org_b, project_number="B-001", name="B project", project_manager=self.other_user,
        )
        self.assertEqual(list(construction_projects_for_user(self.user, self.org_a)), [project_a])
        with self.assertRaises(PermissionDenied):
            construction_projects_for_user(self.user, self.org_b)

    def test_project_list_never_exposes_another_organization(self):
        ConstructionProject.objects.create(organization=self.org_a, project_number="A-001", name="A project", project_manager=self.user)
        ConstructionProject.objects.create(organization=self.org_b, project_number="B-001", name="B project", project_manager=self.other_user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("construction-project-list"))
        self.assertContains(response, "A-001")
        self.assertNotContains(response, "B-001")

    def test_platform_admin_cannot_automatically_open_private_construction_records(self):
        platform_admin = User.objects.create_user(
            username="platform@example.com", email="platform@example.com", password="safe-test-password", is_platform_admin=True,
        )
        self.client.force_login(platform_admin)
        response = self.client.get(reverse("construction-dashboard"))
        self.assertEqual(response.status_code, 403)
