from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone


def log_audit(actor, action: str, project=None, obj=None, summary: str = "", metadata: dict | None = None):
    from core.models import AuditLog

    metadata = metadata or {}
    object_type = obj.__class__.__name__ if obj is not None else ""
    object_id = str(getattr(obj, "pk", "")) if obj is not None else ""
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        project=project,
        object_type=object_type,
        object_id=object_id,
        summary=summary,
        metadata=metadata,
    )


def notify_user(user, title: str, message: str, project=None, level: str = "info", link: str = ""):
    from core.models import Notification

    return Notification.objects.create(
        user=user,
        project=project,
        title=title,
        message=message,
        level=level,
        link=link,
    )


def notify_many(users, title: str, message: str, project=None, level: str = "info", link: str = ""):
    notifications = []
    for user in users:
        notifications.append(notify_user(user, title, message, project=project, level=level, link=link))
    return notifications


def build_dashboard_context(user):
    from projects.constants import PROJECT_STATUS_CHOICES
    from projects.models import DocumentChecklistItem, PhysicalFileTransfer, Project, Task

    if user.is_superuser or user.groups.filter(name__in={"System Administrator", "Director/Management"}).exists():
        project_scope = Project.objects.filter(is_deleted=False)
        task_scope = Task.objects.filter(is_deleted=False)
    else:
        project_scope = Project.objects.filter(is_deleted=False).filter(
            Q(created_by=user)
            | Q(current_responsible_employee=user)
            | Q(members=user)
        ).distinct()
        task_scope = Task.objects.filter(is_deleted=False).filter(assigned_employee=user)

    status_counts = {
        status: project_scope.filter(status=status).count() for status, _ in PROJECT_STATUS_CHOICES
    }
    missing_documents = DocumentChecklistItem.objects.filter(
        project__in=project_scope,
        required=True,
        received=False,
        is_deleted=False,
    ).count()
    physical_outside = PhysicalFileTransfer.objects.filter(
        project__in=project_scope,
        received_confirmation=False,
        is_deleted=False,
    ).count()
    today = timezone.localdate()
    today_tasks = task_scope.filter(
        due_date=today,
        status__in={"New", "Assigned", "In Progress", "Correction Required"},
    ).count()
    missing_projects = DocumentChecklistItem.objects.filter(
        project__in=project_scope,
        required=True,
        received=False,
        is_deleted=False,
    ).values("project_id").distinct().count()

    next_actions = {
        "New": "Review intake",
        "Documents Pending": "Collect missing documents",
        "Documents Verification": "Verify documents",
        "Ready for Online Entry": "Start online entry",
        "Plan Preparation": "Complete plan set",
        "Waiting for Client Approval": "Follow up with client",
        "Waiting for Ward": "Follow up with ward",
        "Structural Work": "Review structural design",
        "Online Processing": "Check online application",
        "Ready for Municipality": "Prepare municipality submission",
        "At Municipality": "Check municipality status",
        "Correction Required": "Resolve corrections",
        "Approved": "Prepare delivery",
        "Delivered": "Confirm handover",
        "Payment Pending": "Follow up payment",
        "Completed": "No action due",
    }
    status_classes = {
        "New": "status-new",
        "Documents Pending": "status-danger",
        "Documents Verification": "status-warning",
        "Ready for Online Entry": "status-blue",
        "Plan Preparation": "status-blue",
        "Waiting for Client Approval": "status-warning",
        "Waiting for Ward": "status-warning",
        "Structural Work": "status-blue",
        "Online Processing": "status-blue",
        "Ready for Municipality": "status-blue",
        "At Municipality": "status-warning",
        "Correction Required": "status-danger",
        "Approved": "status-success",
        "Delivered": "status-success",
        "Payment Pending": "status-warning",
        "Completed": "status-success",
    }
    recent_projects = list(project_scope.select_related("client", "service_type", "current_stage_template").order_by("-updated_at")[:5])
    recent_project_rows = [
        {
            "project": project,
            "next_action": next_actions.get(project.status, "Review project"),
            "status_class": status_classes.get(project.status, "status-new"),
        }
        for project in recent_projects
    ]

    return {
        "active_projects": project_scope.filter(status__in={"New", "Documents Pending", "Documents Verification", "Ready for Online Entry", "Plan Preparation", "Waiting for Client Approval", "Waiting for Ward", "Structural Work", "Online Processing", "Ready for Municipality", "At Municipality", "Correction Required", "Approved", "Delivered", "Payment Pending"}).count(),
        "active_naya_naksa": project_scope.filter(service_type__code="NN", is_deleted=False).count(),
        "active_abhilekhikaran": project_scope.filter(service_type__code="AB", is_deleted=False).count(),
        "project_count": project_scope.count(),
        "task_count": task_scope.count(),
        "today_tasks": today_tasks,
        "today": today,
        "overdue_tasks": task_scope.filter(status__in={"New", "Assigned", "In Progress", "Correction Required"}, due_date__lt=timezone.now().date()).count(),
        "waiting_client": project_scope.filter(status="Waiting for Client Approval").count(),
        "waiting_ward": project_scope.filter(status="Waiting for Ward").count(),
        "at_municipality": project_scope.filter(status="At Municipality").count(),
        "municipality_corrections": project_scope.filter(status="Correction Required").count(),
        "physical_files_outside": physical_outside,
        "missing_documents": missing_documents,
        "missing_projects": missing_projects,
        "status_counts": status_counts,
        "recent_projects": recent_projects,
        "recent_project_rows": recent_project_rows,
        "recent_tasks": task_scope.order_by("-updated_at")[:5],
    }


def get_organization_profile():
    from core.models import OrganizationProfile

    return OrganizationProfile.load()
