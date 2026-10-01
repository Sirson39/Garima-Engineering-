"""Membership-based access for individual organization accounts."""
from accounts.models import OrganizationMembership, User


def active_membership(user, organization_id=None):
    if not user or not user.is_authenticated:
        return None
    if organization_id is None:
        organization_id = getattr(user, "_workspace_organization_id", user.company_id)
    return OrganizationMembership.objects.select_related("organization__system_template").filter(
        user=user, user__is_active=True, organization_id=organization_id,
        is_active=True, organization__is_active=True,
    ).first()


def organization_employees(organization_id):
    return User.objects.filter(
        is_active=True, organization_memberships__organization_id=organization_id,
        organization_memberships__is_active=True,
        organization_memberships__organization__is_active=True,
    ).distinct().order_by("first_name", "last_name", "email") if organization_id else User.objects.none()
