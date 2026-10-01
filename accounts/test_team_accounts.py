from importlib import import_module
from io import StringIO
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import Company, OrganizationMembership, SystemTemplate, User
from accounts.forms import OrganizationUserForm
from projects.models import Client, Project, Task, SiteVisit
from projects.services import project_queryset_for_user, resolve_employee_for_stage
from workflows.models import ServiceType, WorkflowStageTemplate


class TeamAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        template = SystemTemplate.objects.get(code="engineering-consultancy", version="1.0")
        cls.company = Company.objects.create(name="Team Engineering", slug="team-engineering", system_template=template)
        cls.other_company = Company.objects.create(name="Other Engineering", slug="other-engineering", system_template=template)
        cls.admin = cls.make_user("owner", "admin")
        cls.engineer = cls.make_user("engineer", "engineer")
        cls.staff = cls.make_user("staff", "staff")
        cls.outsider = cls.make_user("outsider", "engineer", cls.other_company)
        cls.service = ServiceType.objects.create(code="TEAM", name="Team service")
        cls.customer = Client.objects.create(organization=cls.company, full_name="Team client", mobile_number="123")
        cls.project = Project.objects.create(organization=cls.company, client=cls.customer, service_type=cls.service, project_number="TEAM-1")
        cls.other_project = Project.objects.create(organization=cls.other_company, client=cls.customer, service_type=cls.service, project_number="OTHER-1")
        cls.task = Task.objects.create(project=cls.project, title="Engineering task", assigned_employee=cls.engineer)
        Task.objects.create(project=cls.other_project, title="Other organization task", assigned_employee=cls.engineer)
        cls.project.members.add(cls.staff)
        SiteVisit.objects.create(project=cls.project, assigned_engineer=cls.engineer)

    @classmethod
    def make_user(cls, name, role, company=None):
        company = company or cls.company
        user = User.objects.create_user(username=name, email=f"{name}@team.test", first_name=name.title(),
                                        password="Original-Complex-Pass-83!", company=company, company_role=role)
        OrganizationMembership.objects.create(user=user, organization=company, role=role)
        return user

    def payload(self, **changes):
        return {"first_name": "New", "last_name": "Engineer", "email": "new@team.test", "role": "engineer",
                "initial_password": "Private-First-Login-83!", "confirm_password": "Private-First-Login-83!", **changes}

    def test_admin_creates_individual_hashed_account_and_membership(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("organization-user-create"), self.payload())
        self.assertRedirects(response, reverse("users-roles"))
        user = User.objects.get(email="new@team.test")
        self.assertTrue(user.check_password(self.payload()["initial_password"]))
        self.assertNotEqual(user.password, self.payload()["initial_password"])
        self.assertTrue(user.must_change_password)
        self.assertFalse(user.is_staff or user.is_superuser or user.is_platform_admin)
        self.assertFalse(user.groups.exists())
        self.assertEqual(user.organization_memberships.get().organization, self.company)
        self.assertEqual(user.get_full_name(), "New Engineer")
        response = self.client.get(reverse("users-roles"))
        self.assertContains(response, "new@team.test")
        self.assertNotContains(response, self.outsider.email)
        self.assertNotContains(response, "No roles assigned")
        self.assertNotContains(response, self.payload()["initial_password"])

    def test_first_login_password_change_then_correct_dashboard(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("organization-user-create"), self.payload(role="staff"))
        self.client.logout()
        response = self.client.post(reverse("login"), {"email": "new@team.test", "password": self.payload()["initial_password"]})
        self.assertRedirects(response, reverse("password-change"))
        self.assertRedirects(self.client.get(reverse("staff-dashboard")), reverse("password-change"))
        response = self.client.post(reverse("password-change"), {
            "old_password": self.payload()["initial_password"],
            "new_password1": "Personal-Replacement-92!", "new_password2": "Personal-Replacement-92!",
        }, follow=True)
        self.assertContains(response, "Staff dashboard")
        user = User.objects.get(email="new@team.test")
        self.assertFalse(user.must_change_password)
        self.assertFalse(user.check_password(self.payload()["initial_password"]))
        self.assertTrue(user.check_password("Personal-Replacement-92!"))

    def test_validation_rejects_duplicates_bad_passwords_and_admin_type(self):
        User.objects.create_user(username="reserved@team.test")
        for changes, field in [
            ({"email": self.engineer.email.upper()}, "email"),
            ({"email": "reserved@team.test"}, "email"),
            ({"confirm_password": "different"}, "confirm_password"),
            ({"initial_password": "password", "confirm_password": "password"}, "initial_password"),
            ({"role": "admin"}, "role"),
        ]:
            with self.subTest(changes=changes):
                form = OrganizationUserForm(self.payload(**changes))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_database_rejects_case_insensitive_duplicate_email(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="duplicate", email=self.engineer.email.upper())

    def test_employee_cannot_manage_accounts_or_admin_pages(self):
        self.client.force_login(self.engineer)
        for name in ("users-roles", "organization-user-create", "reports", "system-settings", "payments", "project-create", "client-create", "workflow-catalog"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertEqual(self.client.post(reverse("organization-user-create"), self.payload()).status_code, 403)
        self.assertFalse(User.objects.filter(email="new@team.test").exists())

    def test_admin_of_another_organization_cannot_create_here(self):
        OrganizationMembership.objects.create(user=self.staff, organization=self.other_company, role="admin")
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse("organization-user-create"), self.payload()).status_code, 403)
        session = self.client.session
        session["organization_id"] = self.other_company.pk
        session.save()
        self.assertRedirects(self.client.post(reverse("organization-user-create"), self.payload()), reverse("users-roles"))
        self.assertEqual(User.objects.get(email="new@team.test").company, self.other_company)

    def test_selected_organization_requires_membership(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["organization_id"] = self.other_company.pk
        session.save()
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)
        self.assertEqual(self.client.post(reverse("organization-user-create"), self.payload()).status_code, 403)

    def test_inactive_membership_and_unaffiliated_account_denied(self):
        self.client.force_login(self.engineer)
        self.engineer.organization_memberships.update(is_active=False)
        self.assertEqual(self.client.get(reverse("engineer-dashboard")).status_code, 403)
        orphan = User.objects.create_user(username="no-organization", is_staff=True)
        self.client.force_login(orphan)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)

    def test_engineer_dashboard_contains_only_assigned_tenant_work(self):
        self.client.force_login(self.engineer)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("engineer-dashboard"))
        response = self.client.get(reverse("engineer-dashboard"))
        self.assertTemplateUsed(response, "core/engineer_dashboard.html")
        self.assertContains(response, "Engineering task")
        self.assertNotContains(response, "Other organization task")
        self.assertContains(response, "My upcoming site visits")
        self.assertNotContains(response, reverse("users-roles"))
        self.assertEqual(self.client.get(reverse("staff-dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("project-detail", args=[self.other_project.pk])).status_code, 404)
        response = self.client.get(reverse("project-detail", args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add Payment")
        self.assertNotContains(response, "Workflow Control")

    def test_staff_dashboard_and_scoped_project_lists(self):
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("staff-dashboard"))
        response = self.client.get(reverse("staff-dashboard"))
        self.assertTemplateUsed(response, "core/staff_dashboard.html")
        self.assertContains(response, "Document follow-up")
        self.assertNotContains(response, "My upcoming site visits")
        self.assertEqual(set(project_queryset_for_user(self.admin)), {self.project})
        self.assertEqual(set(project_queryset_for_user(self.engineer)), {self.project})
        self.assertEqual(set(project_queryset_for_user(self.outsider)), set())

    def test_assignment_forms_include_new_accounts_without_django_staff_access(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("project-task-create", args=[self.project.pk]))
        employees = response.context["form"].fields["assigned_employee"].queryset
        self.assertIn(self.engineer, employees)
        self.assertIn(self.staff, employees)
        self.assertNotIn(self.outsider, employees)
        stage = WorkflowStageTemplate.objects.create(service_type=self.service, code="ENGINEERING", name="Design", order=1, responsible_role_hint="Planning Engineer")
        self.assertEqual(resolve_employee_for_stage(stage, self.company.pk), self.engineer)

    def test_removal_migration_preserves_users_and_unrelated_groups(self):
        migration = import_module("accounts.migrations.0018_individual_team_accounts")
        legacy = Group.objects.create(name="Planning Engineer")
        self.engineer.groups.add(legacy)
        keep = Group.objects.create(name="Unrelated workspace group")
        before = User.objects.count()
        migration.remove_legacy_groups(apps, SimpleNamespace(connection=connection))
        self.assertFalse(Group.objects.filter(name__in=migration.LEGACY_GROUPS).exists())
        self.assertTrue(Group.objects.filter(pk=keep.pk).exists())
        self.assertEqual(User.objects.count(), before)
        self.assertTrue(self.admin.organization_memberships.filter(role="admin", is_active=True).exists())

    def test_catalog_seed_does_not_recreate_demo_accounts_or_groups(self):
        before = User.objects.count(), Group.objects.count()
        call_command("seed_demo_data", stdout=StringIO())
        self.assertEqual((User.objects.count(), Group.objects.count()), before)
