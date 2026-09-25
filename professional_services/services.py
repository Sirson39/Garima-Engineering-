from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import CharField, Count, Q
from django.db.models.functions import Cast
from django.urls import reverse
from django.utils import timezone

from accounts.models import OrganizationMembership, TemplateNavigationItem, User
from core.models import AuditLog
from core.services import log_audit
from .models import Engagement, ProfessionalClient, ProfessionalService


TEMPLATE_CODE = "professional-services"


class WorkspaceAccess:
    """Server-side tenant, module and permission context; no platform-role bypass."""

    def __init__(self, request):
        self.user = request.user
        if not self.user.is_authenticated or not self.user.is_active:
            raise PermissionDenied("An active organization membership is required.")
        organization_id = request.session.get("organization_id") or self.user.company_id
        self.membership = OrganizationMembership.objects.filter(
            user=self.user, organization_id=organization_id, is_active=True,
            organization__is_active=True, organization__system_template__code=TEMPLATE_CODE,
            organization_role__is_active=True,
        ).select_related("organization__system_template", "organization_role").first()
        if not self.membership or self.membership.organization_role.organization_id != self.membership.organization_id:
            raise PermissionDenied("You do not have access to this professional services workspace.")
        self.organization = self.membership.organization
        self.modules = set(self.organization.enabled_modules.filter(
            is_enabled=True, module__is_active=True,
            module__template_modules__system_template=self.organization.system_template,
        ).values_list("module__code", flat=True))
        self.permissions = set(self.membership.organization_role.permissions.filter(
            module__code__in=self.modules,
        ).values_list("code", flat=True))

    def allows(self, code):
        return code in self.permissions

    def require(self, code):
        if not self.allows(code):
            raise PermissionDenied("Your role or enabled modules do not allow this action.")

    def engagements(self):
        records = Engagement.objects.filter(organization=self.organization)
        if not self.allows("ps-engagements.view"):
            return records.none()
        if not self.allows("ps-engagements.view_all"):
            records = records.filter(Q(account_manager=self.user) | Q(engagement_manager=self.user) | Q(assigned_team=self.user))
        return records.distinct()

    def clients(self):
        records = ProfessionalClient.objects.filter(organization=self.organization)
        if not self.allows("ps-clients.view"):
            return records.none()
        if not self.allows("ps-clients.view_all"):
            records = records.filter(Q(account_manager=self.user) | Q(engagements__in=self.engagements()))
        return records.distinct()

    def services(self):
        records = ProfessionalService.objects.filter(organization=self.organization)
        return records if self.allows("ps-services.view") else records.none()

    def staff(self):
        return User.objects.filter(is_active=True, organization_memberships__organization=self.organization,
                                   organization_memberships__is_active=True).distinct()

    def navigation(self):
        items = TemplateNavigationItem.objects.filter(
            system_template=self.organization.system_template, is_active=True,
            module__code__in=self.modules, required_permission__code__in=self.permissions,
        )
        return [{"label": item.label, "url": reverse(item.url_name), "url_name": item.url_name} for item in items]

    def audit_entries(self):
        entries = AuditLog.objects.filter(action__startswith="ps.", metadata__organization_id=self.organization.pk)
        if not self.allows("ps-audit.view"):
            return entries.none()
        def ids(records):
            return records.order_by().annotate(audit_key=Cast("pk", CharField())).values("audit_key")

        scope = (Q(object_type="ProfessionalClient", object_id__in=ids(self.clients()))
                 | Q(object_type="Engagement", object_id__in=ids(self.engagements()))
                 | Q(object_type="ProfessionalService", object_id__in=ids(self.services())))
        if self.allows("ps-roles.view"):
            scope |= Q(object_type__in=["ProfessionalSettings", "OrganizationMembership"])
        return entries.filter(scope).select_related("actor").order_by("-created_at", "-pk")


def access_for(request):
    if not hasattr(request, "professional_access"):
        request.professional_access = WorkspaceAccess(request)
    return request.professional_access


def record_activity(access, action, obj, changed_fields=()):
    return log_audit(
        access.user, f"ps.{action}", obj=obj, summary=f"{action.replace('.', ' ').capitalize()}: {obj}",
        metadata={"organization_id": access.organization.pk, "changed_fields": sorted(changed_fields)},
    )


def dashboard_data(access):
    today = timezone.localdate()
    engagements = access.engagements()
    open_engagements = engagements.exclude(status__in=["completed", "cancelled", "archived"])
    upcoming = open_engagements.filter(due_date__gte=today, due_date__lte=today + timedelta(days=30))
    metrics = []
    if access.allows("ps-clients.view"):
        metrics.append({"label": "Active clients", "value": access.clients().filter(status="active").count()})
    if access.allows("ps-engagements.view"):
        metrics.extend([
            {"label": "Active engagements", "value": engagements.filter(status="active").count()},
            {"label": "Deadlines in 30 days", "value": upcoming.count()},
            {"label": "Overdue engagements", "value": open_engagements.filter(due_date__lt=today).count()},
        ])
    labels = dict(Engagement.Status.choices)
    return {
        "metrics": metrics,
        "upcoming": list(upcoming.order_by("due_date").values("id", "number", "title", "due_date", "status")[:8]),
        "recent_clients": list(access.clients().order_by("-updated_at").values("id", "name", "status", "updated_at")[:6]),
        "status_counts": [{"status": labels[row["status"]], "total": row["total"]} for row in engagements.order_by().values("status").annotate(total=Count("id", distinct=True))],
        "workload": list(open_engagements.order_by().values("engagement_manager__first_name", "engagement_manager__last_name", "engagement_manager__username").annotate(total=Count("id", distinct=True)).order_by("-total")[:8]),
    }
