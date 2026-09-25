from django.test import TestCase
from django.urls import reverse

from accounts.models import Company, OrganizationMembership, SystemTemplate, User
from .models import OfficeDepartment, OfficeStaffProfile


class OfficeFoundationTests(TestCase):
    def setUp(self):
        self.template = SystemTemplate.objects.get(code="general-office-management", version="1.0")
        self.organization = Company.objects.create(
            name="Office One",
            slug="office-one",
            organization_code="office-one",
            system_template=self.template,
            category=self.template.category,
        )
        self.user = User.objects.create_user(
            username="office-admin@example.com",
            email="office-admin@example.com",
            password="safe-test-password",
            company=self.organization,
        )
        OrganizationMembership.objects.create(user=self.user, organization=self.organization, role="admin")

    def test_department_and_staff_are_organization_scoped(self):
        department = OfficeDepartment.objects.create(organization=self.organization, name="Operations", code="operations")
        profile = OfficeStaffProfile.objects.create(organization=self.organization, user=self.user, employee_id="EMP-001", department=department)

        self.assertEqual(profile.full_name, self.user.display_name)
        self.assertEqual(OfficeDepartment.objects.filter(organization=self.organization).count(), 1)

    def test_office_dashboard_requires_office_membership(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("office-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Office One")

    def test_department_hierarchy_rejects_cycles(self):
        parent = OfficeDepartment.objects.create(organization=self.organization, name="Parent", code="parent")
        child = OfficeDepartment.objects.create(organization=self.organization, name="Child", code="child", parent=parent)
        child.parent = child
        with self.assertRaises(Exception):
            child.full_clean()
