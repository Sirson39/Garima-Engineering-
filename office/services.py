from django.core.exceptions import PermissionDenied

from accounts.models import OrganizationMembership


def active_office_organization(user, organization_id=None):
    if not user.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    membership = OrganizationMembership.objects.filter(
        user=user,
        is_active=True,
        organization__is_active=True,
        organization__system_template__code="general-office-management",
    ).select_related("organization").first()
    if organization_id:
        membership = OrganizationMembership.objects.filter(
            user=user,
            organization_id=organization_id,
            is_active=True,
            organization__is_active=True,
            organization__system_template__code="general-office-management",
        ).select_related("organization").first()
    if not membership:
        raise PermissionDenied("You do not have access to this office workspace.")
    return membership.organization
