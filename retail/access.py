from django.core.exceptions import PermissionDenied
from django.urls import reverse

from accounts.models import OrganizationMembership, TemplateNavigationItem
from .models import RetailDocument


class RetailAccess:
    def __init__(self, request):
        self.user = request.user
        if not self.user.is_authenticated or not self.user.is_active:
            raise PermissionDenied("An active retail membership is required.")
        self.membership = OrganizationMembership.objects.filter(
            user=self.user, organization_id=request.session.get("organization_id") or self.user.company_id,
            is_active=True, organization__is_active=True, organization__system_template__code="retail-management",
            organization_role__is_active=True,
        ).select_related("organization__system_template", "organization_role").first()
        if not self.membership or self.membership.organization_role.organization_id != self.membership.organization_id:
            raise PermissionDenied("You do not have access to this retail workspace.")
        self.organization = self.membership.organization
        self.modules = set(self.organization.enabled_modules.filter(
            is_enabled=True, module__is_active=True, module__template_modules__system_template=self.organization.system_template,
        ).values_list("module__code", flat=True))
        self.permissions = set(self.membership.organization_role.permissions.filter(module__code__in=self.modules).values_list("code", flat=True))

    def allows(self, permission):
        return permission in self.permissions

    def require(self, permission):
        if not self.allows(permission):
            raise PermissionDenied("Your role or enabled modules do not permit this action.")

    def require_modules(self, *codes):
        if not set(codes).issubset(self.modules):
            raise PermissionDenied("A module required for this operation is disabled.")

    def scope(self, model):
        return model.objects.filter(organization=self.organization)

    def documents(self, kind):
        module = "purchases" if kind == "purchase" else "sales"
        self.require(f"rt-{module}.view")
        records = self.scope(RetailDocument).filter(kind=kind)
        if module == "sales" and not self.allows("rt-sales.view_all"):
            records = records.filter(original_sale__created_by=self.user) if kind == "return" else records.filter(created_by=self.user)
        return records

    def navigation(self):
        return [{"label": item.label, "url": reverse(item.url_name), "url_name": item.url_name} for item in
                TemplateNavigationItem.objects.filter(system_template=self.organization.system_template, is_active=True,
                                                     module__code__in=self.modules, required_permission__code__in=self.permissions)]
