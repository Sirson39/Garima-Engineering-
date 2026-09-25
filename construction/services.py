from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from accounts.models import Company, OrganizationMembership
from .models import ConstructionProject


def active_construction_organization(user, organization_id=None) -> Company:
    if not user.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    organization_id = organization_id or getattr(user, "company_id", None)
    membership = OrganizationMembership.objects.filter(
        user=user,
        organization_id=organization_id,
        is_active=True,
        organization__is_active=True,
        organization__system_template__code="construction-management",
    ).select_related("organization").first()
    if not membership:
        raise PermissionDenied("You do not have access to a construction organization.")
    return membership.organization


def construction_projects_for_user(user, organization):
    projects = ConstructionProject.objects.filter(organization=organization, is_deleted=False)
    if user.is_superuser:
        return projects
    if user.is_platform_admin:
        raise PermissionDenied("Platform administrators do not receive automatic access to private construction records.")
    if user.company_id != organization.pk:
        raise PermissionDenied("Organization access is required.")
    if user.company_role == "admin":
        return projects
    return projects.filter(Q(project_manager=user) | Q(memberships__user=user, memberships__is_active=True)).distinct()
