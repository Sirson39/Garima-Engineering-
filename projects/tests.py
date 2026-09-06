from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from projects.models import Client, Project
from projects.services import advance_project_stage, create_project_initial_state, project_queryset_for_user, user_can_access_project
from workflows.models import DocumentCategory, DocumentTemplate, NumberingScheme, ServiceType, WorkflowStageTemplate


class ProjectWorkflowTests(TestCase):
    def setUp(self):
        self.reception_group = Group.objects.create(name="Reception/Document Officer")
        self.manager_group = Group.objects.create(name="Director/Management")
        self.service = ServiceType.objects.create(code="TS", name="Test Service", description="Test workflow")
        NumberingScheme.objects.create(
            service_type=self.service,
            prefix="GEC",
            service_code="TS",
            year_label="2083",
            sequence_width=4,
            next_sequence=1,
            separator="-",
            format_template="{prefix}-{service_code}-{year_label}-{sequence:04d}",
            is_active=True,
        )
        self.category = DocumentCategory.objects.create(service_type=self.service, code="client-docs", name="Client documents", order=1)
        self.stage_1 = WorkflowStageTemplate.objects.create(
            service_type=self.service,
            code="TS-01",
            name="Registration",
            order=1,
            default_status="New",
            wait_type="internal",
            responsible_role_hint="Reception/Document Officer",
            due_days_default=1,
            requires_document_completion=False,
            is_start=True,
        )
        self.stage_2 = WorkflowStageTemplate.objects.create(
            service_type=self.service,
            code="TS-02",
            name="Verification",
            order=2,
            default_status="Documents Verification",
            wait_type="internal",
            responsible_role_hint="Reception/Document Officer",
            due_days_default=2,
        )
        self.template = DocumentTemplate.objects.create(
            service_type=self.service,
            category=self.category,
            name="Lalpurja",
            order=1,
            required=True,
            allow_exception=True,
            must_be_seen_original=True,
            must_be_scanned=True,
        )
        self.staff = User.objects.create_user(username="staff", password="pass1234", is_staff=True)
        self.staff.groups.add(self.reception_group)
        self.manager = User.objects.create_user(username="manager", password="pass1234", is_staff=True)
        self.manager.groups.add(self.manager_group)
        self.client = Client.objects.create(
            full_name="Test Client",
            mobile_number="9841000000",
            created_by=self.staff,
        )

    def create_project(self):
        project = Project.objects.create(
            service_type=self.service,
            client=self.client,
            project_fee=Decimal("100000.00"),
            created_by=self.staff,
            updated_by=self.staff,
        )
        create_project_initial_state(project, actor=self.staff)
        project.refresh_from_db()
        return project

    def test_project_number_generated_and_checklist_cloned(self):
        project = self.create_project()
        self.assertTrue(project.project_number.startswith("GEC-TS-2083-0001"))
        self.assertEqual(project.checklist_items.count(), 1)
        self.assertEqual(project.current_stage_template, self.stage_1)

    def test_stage_transition_blocks_missing_documents(self):
        project = self.create_project()
        with self.assertRaises(ValidationError):
            advance_project_stage(project=project, actor=self.staff, target_stage=self.stage_2)

    def test_management_override_approves_exception_and_advances(self):
        project = self.create_project()
        stage = advance_project_stage(
            project=project,
            actor=self.manager,
            target_stage=self.stage_2,
            override_missing_documents=True,
            override_reason="Manager approved exception",
        )
        project.refresh_from_db()
        checklist_item = project.checklist_items.first()
        self.assertIsNotNone(checklist_item.exception_approved_by)
        self.assertEqual(checklist_item.exception_approved_by, self.manager)
        self.assertEqual(project.current_stage_template, self.stage_2)
        self.assertEqual(stage.stage_template, self.stage_2)

    def test_access_scopes_projects_to_staff_membership(self):
        project = self.create_project()
        outsider = User.objects.create_user(username="outsider", password="pass1234", is_staff=False)
        self.assertTrue(user_can_access_project(self.staff, project))
        self.assertFalse(user_can_access_project(outsider, project))
        self.assertEqual(project_queryset_for_user(outsider).count(), 0)

