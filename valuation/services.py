from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import OrganizationMembership, OrganizationModule
from .models import ValuationActivity, ValuationRequest


VALUATION_TEMPLATE_CODES = {"engineering-consultancy", "valuation-management"}
DEFAULT_DOCUMENT_TYPES = (
    "Bank request letter",
    "Land ownership certificate (Lalpurja)",
    "Owner citizenship certificate",
    "Borrower citizenship certificate",
    "Cadastral map (Napi Naksha)",
    "Trace map",
    "Field book or plot register",
    "Four-boundary certificate (Char Killa)",
    "Land revenue receipt",
    "Municipal or property-tax clearance",
    "Building permit",
    "Approved building drawings",
    "Building completion certificate",
    "Floor plans and area schedule",
    "Ownership transfer or partition documents",
    "Site photographs",
    "Previous valuation report",
    "Other supporting documents",
)
ALLOWED_TRANSITIONS = {
    ValuationRequest.STATUS_REQUEST_RECEIVED: {ValuationRequest.STATUS_DOCUMENTS_PENDING},
    ValuationRequest.STATUS_DOCUMENTS_PENDING: {ValuationRequest.STATUS_DOCUMENTS_VERIFIED, ValuationRequest.STATUS_CORRECTION_REQUIRED},
    ValuationRequest.STATUS_DOCUMENTS_VERIFIED: {ValuationRequest.STATUS_SITE_VISIT_SCHEDULED},
    ValuationRequest.STATUS_SITE_VISIT_SCHEDULED: {ValuationRequest.STATUS_SITE_INSPECTION_COMPLETED},
    ValuationRequest.STATUS_SITE_INSPECTION_COMPLETED: {ValuationRequest.STATUS_VALUATION_DRAFTED},
    ValuationRequest.STATUS_VALUATION_DRAFTED: {ValuationRequest.STATUS_INTERNAL_REVIEW},
    ValuationRequest.STATUS_INTERNAL_REVIEW: {ValuationRequest.STATUS_APPROVED, ValuationRequest.STATUS_CORRECTION_REQUIRED},
    ValuationRequest.STATUS_CORRECTION_REQUIRED: {ValuationRequest.STATUS_VALUATION_DRAFTED},
    ValuationRequest.STATUS_APPROVED: {ValuationRequest.STATUS_REPORT_ISSUED},
    ValuationRequest.STATUS_REPORT_ISSUED: {ValuationRequest.STATUS_ARCHIVED},
}


def valuation_organization_for(user, organization_id=None):
    if not user.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    memberships = OrganizationMembership.objects.filter(
        user=user,
        is_active=True,
        organization__is_active=True,
        organization__system_template__code__in=VALUATION_TEMPLATE_CODES,
    ).select_related("organization")
    if organization_id:
        memberships = memberships.filter(organization_id=organization_id)
    membership = memberships.first()
    if not membership:
        raise PermissionDenied("You do not have access to this valuation workspace.")
    if not OrganizationModule.objects.filter(
        organization=membership.organization,
        module__code="valuation-management",
        is_enabled=True,
    ).exists():
        raise PermissionDenied("Valuation Management is not enabled for this organization.")
    return membership.organization


def next_reference_number(organization):
    year = timezone.localdate().year
    prefix = (organization.organization_code or organization.slug or "ORG").upper().replace(" ", "-")[:24]
    base = f"{prefix}-VAL-{year}"
    existing = ValuationRequest.objects.filter(organization=organization, reference_number__startswith=f"{base}-").count()
    return f"{base}-{existing + 1:04d}"


def create_default_checklist(valuation_request):
    from .models import ValuationDocumentChecklist

    ValuationDocumentChecklist.objects.bulk_create(
        [
            ValuationDocumentChecklist(request=valuation_request, document_type=document_type)
            for document_type in DEFAULT_DOCUMENT_TYPES
        ]
    )


def user_can_manage_valuation(user, organization, action="view"):
    membership = OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
    ).select_related("organization_role").first()
    if not membership:
        return False
    if membership.role == OrganizationMembership.ROLE_ADMIN:
        return True
    role = membership.organization_role
    if not role:
        return False
    return role.permissions.filter(
        code__in=(f"valuation-management.{action}", f"valuation-requests.{action}")
    ).exists()


@transaction.atomic
def transition_request(*, request, actor, to_status, reason=""):
    if request.organization_id != actor.company_id:
        raise PermissionDenied("This valuation request belongs to another organization.")
    if not user_can_manage_valuation(actor, request.organization, "change"):
        raise PermissionDenied("You do not have permission to update valuation workflow status.")
    if to_status not in ALLOWED_TRANSITIONS.get(request.status, set()):
        raise ValidationError(f"Cannot move a valuation request from {request.get_status_display()} to the selected status.")
    previous = request.status
    request.status = to_status
    request.save(update_fields=["status", "updated_at"])
    ValuationActivity.objects.create(
        request=request,
        actor=actor,
        action="status_changed",
        from_status=previous,
        to_status=to_status,
        reason=reason,
    )
    return request
