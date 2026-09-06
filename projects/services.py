from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.services import log_audit, notify_user
from projects.models import (
    Client,
    DocumentChecklistItem,
    Project,
    ProjectDocument,
    ProjectStageHistory,
    Task,
)
from workflows.models import DocumentTemplate, NumberingScheme, WorkflowStageTemplate


User = get_user_model()


def user_has_role(user, *role_names: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=role_names).exists()


def project_queryset_for_user(user):
    qs = Project.objects.filter(is_deleted=False).select_related("client", "service_type", "current_responsible_employee")
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser or (user.is_staff and user.groups.filter(name__in={"System Administrator", "Director/Management", "Project Manager"}).exists()):
        return qs
    return qs.filter(Q(created_by=user) | Q(current_responsible_employee=user) | Q(members=user)).distinct()


def user_can_access_project(user, project: Project) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.is_staff and user.groups.filter(name__in={"System Administrator", "Director/Management", "Project Manager"}).exists():
        return True
    return project.created_by_id == user.id or project.current_responsible_employee_id == user.id or project.members.filter(id=user.id).exists()


def next_stage_template(service_type, current_stage: WorkflowStageTemplate | None = None) -> WorkflowStageTemplate | None:
    stages = list(service_type.workflow_stages.order_by("order", "id"))
    if not stages:
        return None
    if current_stage is None:
        return stages[0]
    for index, stage in enumerate(stages):
        if stage.id == current_stage.id and index + 1 < len(stages):
            return stages[index + 1]
    return None


def allocate_project_number(service_type) -> str:
    with transaction.atomic():
        scheme = NumberingScheme.objects.select_for_update().select_related("service_type").get(
            service_type=service_type, is_active=True
        )
        sequence = scheme.next_sequence
        scheme.next_sequence += 1
        scheme.save(update_fields=["next_sequence", "updated_at"])
        return scheme.render_number(sequence)


def create_project_checklist(project: Project) -> list[DocumentChecklistItem]:
    created = []
    templates = (
        DocumentTemplate.objects.filter(service_type=project.service_type, is_active=True)
        .select_related("category")
        .order_by("order", "name")
    )
    for template in templates:
        checklist_item, _ = DocumentChecklistItem.objects.get_or_create(
            project=project,
            template=template,
            defaults={
                "category": template.category,
                "name": template.name,
                "required": template.required,
            },
        )
        created.append(checklist_item)
    return created


def required_documents_missing(project: Project) -> list[DocumentChecklistItem]:
    return list(
        DocumentChecklistItem.objects.filter(
            project=project,
            required=True,
            received=False,
            exception_approved_by__isnull=True,
            is_deleted=False,
        ).select_related("template", "category")
    )


def resolve_employee_for_stage(stage: WorkflowStageTemplate | None):
    if not stage or not stage.responsible_role_hint:
        return User.objects.filter(is_active=True, is_staff=True).order_by("first_name", "last_name").first()
    candidates = User.objects.filter(
        is_active=True,
        groups__name__iexact=stage.responsible_role_hint,
    ).order_by("first_name", "last_name")
    user = candidates.first()
    if user:
        return user
    return User.objects.filter(is_active=True, is_staff=True).order_by("first_name", "last_name").first()


def initialize_project_workflow(project: Project, actor=None):
    with transaction.atomic():
        create_project_checklist(project)
        first_stage = next_stage_template(project.service_type)
        if first_stage:
            assignee = resolve_employee_for_stage(first_stage)
            stage_history = ProjectStageHistory.objects.create(
                project=project,
                stage_template=first_stage,
                stage_name=first_stage.name,
                stage_order=first_stage.order,
                status=first_stage.default_status,
                assigned_employee=assignee,
                due_date=timezone.localdate() + timedelta(days=first_stage.due_days_default),
            )
            project.current_stage_template = first_stage
            project.current_stage_record = stage_history
            project.current_responsible_employee = assignee
            project.status = first_stage.default_status
            project.save(
                update_fields=[
                    "current_stage_template",
                    "current_stage_record",
                    "current_responsible_employee",
                    "status",
                    "updated_at",
                ]
            )
            if assignee:
                create_task_for_stage(project, stage_history, actor=actor, assignee=assignee)
                notify_user(
                    assignee,
                    f"New project assigned: {project.project_number}",
                    f"{project.client.full_name} is waiting on {first_stage.name.lower()}.",
                    project=project,
                    level="info",
                    link=reverse("project-detail", kwargs={"pk": project.pk}),
                )
            log_audit(actor, "project.workflow.initialized", project=project, obj=stage_history, summary="Initial workflow created")
            return stage_history
        return None


def create_task_for_stage(project: Project, stage_history: ProjectStageHistory, actor=None, assignee=None) -> Task:
    assignee = assignee or stage_history.assigned_employee or resolve_employee_for_stage(stage_history.stage_template)
    task = Task.objects.create(
        project=project,
        related_stage=stage_history,
        title=f"{stage_history.stage_name} - {project.project_number}",
        assigned_employee=assignee,
        assigned_by=actor if getattr(actor, "is_authenticated", False) else None,
        priority="High" if stage_history.stage_template.wait_type in {"client", "ward", "municipality"} else "Normal",
        due_date=stage_history.due_date,
        status="Assigned",
        comments=stage_history.internal_comments,
    )
    if assignee:
        notify_user(
            assignee,
            f"Task assigned: {task.title}",
            f"You have a new task for project {project.project_number}.",
            project=project,
            level="success",
            link=reverse("project-detail", kwargs={"pk": project.pk}),
        )
    log_audit(actor, "task.created", project=project, obj=task, summary=task.title)
    return task


def create_document_revision(
    *,
    project: Project,
    category,
    uploaded_file,
    actor,
    display_name: str,
    checklist_item: DocumentChecklistItem | None = None,
    approval_status: str = "Pending",
    confidentiality_level: str = "Internal",
    remarks: str = "",
    checked_by=None,
) -> ProjectDocument:
    document_key = slugify(f"{category.code}-{display_name}") or slugify(display_name) or "document"
    next_revision = (
        ProjectDocument.objects.filter(project=project, document_key=document_key)
        .aggregate(max_revision=Max("revision_number"))
        .get("max_revision")
        or 0
    ) + 1
    document = ProjectDocument.objects.create(
        project=project,
        category=category,
        checklist_item=checklist_item,
        document_key=document_key,
        display_name=display_name,
        original_filename=getattr(uploaded_file, "name", display_name),
        revision_number=next_revision,
        file=uploaded_file,
        uploaded_by=actor if getattr(actor, "is_authenticated", False) else None,
        checked_by=checked_by,
        approval_status=approval_status,
        confidentiality_level=confidentiality_level,
        remarks=remarks,
    )
    ProjectDocument.objects.filter(project=project, document_key=document_key).exclude(pk=document.pk).update(is_current=False)
    document.is_current = True
    document.save(update_fields=["is_current", "updated_at"])
    if checklist_item:
        checklist_item.received = True
        checklist_item.original_seen = True
        checklist_item.scanned = True
        checklist_item.verified = approval_status in {"Checked", "Approved"}
        checklist_item.uploaded_document = document
        if not checklist_item.received_date:
            checklist_item.received_date = timezone.localdate()
        if checked_by:
            checklist_item.verified_by = checked_by
        checklist_item.save(
            update_fields=[
                "received",
                "original_seen",
                "scanned",
                "verified",
                "uploaded_document",
                "received_date",
                "verified_by",
                "updated_at",
            ]
        )
    log_audit(actor, "document.uploaded", project=project, obj=document, summary=display_name)
    return document


def approve_checklist_exception(project: Project, checklist_item: DocumentChecklistItem, actor, reason: str) -> DocumentChecklistItem:
    checklist_item.exception_approved_by = actor
    checklist_item.exception_approved_at = timezone.now()
    checklist_item.exception_reason = reason
    checklist_item.save(update_fields=["exception_approved_by", "exception_approved_at", "exception_reason", "updated_at"])
    log_audit(
        actor,
        "checklist.exception.approved",
        project=project,
        obj=checklist_item,
        summary=reason,
    )
    return checklist_item


def advance_project_stage(
    *,
    project: Project,
    actor,
    target_stage: WorkflowStageTemplate | None = None,
    assigned_employee=None,
    due_date=None,
    comments: str = "",
    override_missing_documents: bool = False,
    override_reason: str = "",
):
    current_stage = project.current_stage_template
    if target_stage is None:
        target_stage = next_stage_template(project.service_type, current_stage=current_stage)
    if target_stage is None:
        raise ValidationError("No further workflow stage is configured for this service.")

    missing = required_documents_missing(project)
    if missing and target_stage.requires_document_completion and not override_missing_documents:
        missing_names = ", ".join(item.name for item in missing)
        raise ValidationError(
            f"Mandatory documents are still missing: {missing_names}. A manager can approve an exception with a reason."
        )

    with transaction.atomic():
        if missing and override_missing_documents:
            for item in missing:
                approve_checklist_exception(project, item, actor, override_reason or "Manager override")

        if project.current_stage_record and not project.current_stage_record.completed_at:
            project.current_stage_record.completed_at = timezone.now()
            project.current_stage_record.completed_by = actor if getattr(actor, "is_authenticated", False) else None
            project.current_stage_record.status = "Completed"
            project.current_stage_record.save(
                update_fields=["completed_at", "completed_by", "status", "updated_at"]
            )

        assignee = assigned_employee or resolve_employee_for_stage(target_stage)
        stage_history = ProjectStageHistory.objects.create(
            project=project,
            stage_template=target_stage,
            stage_name=target_stage.name,
            stage_order=target_stage.order,
            status=target_stage.default_status,
            assigned_employee=assignee,
            started_at=timezone.now(),
            due_date=due_date or timezone.localdate() + timedelta(days=target_stage.due_days_default),
            internal_comments=comments,
        )
        project.current_stage_template = target_stage
        project.current_stage_record = stage_history
        project.current_responsible_employee = assignee
        project.status = target_stage.default_status
        if target_stage.is_terminal:
            project.closed_at = timezone.now()
        project.save(
            update_fields=[
                "current_stage_template",
                "current_stage_record",
                "current_responsible_employee",
                "status",
                "closed_at",
                "updated_at",
            ]
        )
        create_task_for_stage(project, stage_history, actor=actor, assignee=assignee)
        if assignee:
            notify_user(
                assignee,
                f"Stage updated: {project.project_number}",
                f"{project.client.full_name} moved to {target_stage.name}.",
                project=project,
                level="info",
                link=reverse("project-detail", kwargs={"pk": project.pk}),
            )
        log_summary = comments or f"Moved to {target_stage.name}"
        if missing and override_missing_documents:
            log_summary = f"{log_summary}. Exception approved: {override_reason}"
        log_audit(actor, "project.stage.changed", project=project, obj=stage_history, summary=log_summary)
        return stage_history


def create_project_initial_state(project: Project, actor=None):
    return initialize_project_workflow(project, actor=actor)


def mark_project_completed(project: Project, actor=None):
    project.status = "Completed"
    project.closed_at = timezone.now()
    project.save(update_fields=["status", "closed_at", "updated_at"])
    log_audit(actor, "project.completed", project=project, obj=project, summary="Project completed")


def available_staff_for_groups(*group_names: str):
    return User.objects.filter(is_active=True, groups__name__in=group_names).distinct().order_by("first_name", "last_name")
