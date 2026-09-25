from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db.models import Count, OuterRef, Q, Subquery
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, TemplateView, UpdateView

from accounts.models import Company, CustomStartingStructure, ModuleDefinition, OrganizationMembership, SystemTemplate, TemplateModule, User
from accounts.services import ProvisioningError, provision_organization
from accounts.views import UnifiedLoginView
from core.models import AuditLog
from platform_admin.forms import CompanyForm, PlatformProfileForm


class PlatformLoginView(UnifiedLoginView):
    pass


class PlatformLandingView(UnifiedLoginView):
    pass


class PlatformAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy("platform-login")

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_superuser or user.is_platform_admin)


class PlatformDashboardView(PlatformAdminRequiredMixin, TemplateView):
    template_name = "platform_admin/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        admin_email = User.objects.filter(company=OuterRef("pk"), company_role=User.ROLE_ADMIN).order_by("id").values("email")[:1]
        companies = Company.objects.annotate(user_count=Count("users"), primary_admin_email=Subquery(admin_email)).order_by("name")
        context.update(
            {
                "page_title": "Platform Administration",
                "companies": companies,
                "company_count": companies.count(),
                "active_company_count": companies.filter(is_active=True).count(),
                "user_count": sum(company.user_count for company in companies),
                "support_request_count": None,
            }
        )
        context["new_admin_credentials"] = self.request.session.pop("new_admin_credentials", None)
        return context


class SupportInboxView(PlatformAdminRequiredMixin, TemplateView):
    template_name = "platform_admin/support.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Support Inbox", "support_is_configured": False})
        return context


class BillingPlansView(PlatformAdminRequiredMixin, TemplateView):
    template_name = "platform_admin/billing.html"


class AuditLogsView(PlatformAdminRequiredMixin, TemplateView):
    template_name = "platform_admin/audit_logs.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["audit_logs"] = AuditLog.objects.select_related("actor")[:100]
        return context


class PlatformSettingsView(PlatformAdminRequiredMixin, TemplateView):
    template_name = "platform_admin/settings.html"


class PlatformProfileView(PlatformAdminRequiredMixin, FormView):
    template_name = "platform_admin/profile.html"
    form_class = PlatformProfileForm
    success_url = reverse_lazy("platform-profile")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Your profile details are now up to date.", extra_tags="profile-updated")
        return super().form_valid(form)


class CompanyCreateView(PlatformAdminRequiredMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = "platform_admin/company_form.html"
    success_url = reverse_lazy("platform-dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module_catalog = {}
        category_map = {}
        for template in SystemTemplate.objects.filter(is_active=True).select_related("category"):
            category_map[str(template.pk)] = template.category_id
            if template.code == "custom-organization":
                modules = ModuleDefinition.objects.filter(is_active=True, available_for_custom=True)
                entries = [
                    {"code": module.code, "name": module.name, "required": module.is_core, "default": module.is_core}
                    for module in modules.order_by("is_core", "navigation_order", "name")
                ]
            else:
                entries = [
                    {"code": item.module.code, "name": item.module.name, "required": item.required, "default": item.enabled_by_default}
                    for item in TemplateModule.objects.filter(system_template=template).select_related("module").order_by("module__navigation_order", "module__name")
                ]
            module_catalog[str(template.pk)] = entries
        # json_script performs the encoding; pass objects so one JSON.parse in the
        # wizard returns a catalog, rather than an already-encoded string.
        context["module_catalog_json"] = module_catalog
        context["template_category_json"] = category_map
        context["custom_structure_defaults_json"] = {
            str(structure.pk): list(structure.structure_modules.filter(enabled_by_default=True).values_list("module__code", flat=True))
            for structure in CustomStartingStructure.objects.filter(is_active=True).prefetch_related("structure_modules__module")
        }
        return context

    def form_valid(self, form):
        try:
            organization = provision_organization(
                actor=self.request.user,
                organization_data={field: form.cleaned_data.get(field) for field in form.organization_fields},
                template=form.cleaned_data["system_template"],
                module_codes=set(form.cleaned_data.get("modules", [])),
                branding_data={
                    "primary_color": form.cleaned_data.get("primary_color") or "#245a78",
                    "accent_color": form.cleaned_data.get("accent_color") or "#3b82f6",
                    "report_header": form.cleaned_data.get("report_header", ""),
                    "report_footer": form.cleaned_data.get("report_footer", ""),
                    "date_format": form.cleaned_data.get("date_format") or "Y-m-d",
                    "number_format": form.cleaned_data.get("number_format") or "international",
                },
                admin_data={
                    "full_name": form.cleaned_data["admin_full_name"],
                    "email": form.cleaned_data["admin_email"],
                    "phone": form.cleaned_data.get("admin_phone", ""),
                    "job_title": form.cleaned_data.get("admin_job_title", ""),
                    "temporary_password": form.cleaned_data.get("admin_temporary_password", ""),
                },
                custom_starting_structure=form.cleaned_data.get("custom_starting_structure"),
            )
        except ProvisioningError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        self.request.session["new_admin_credentials"] = {
            "organization": organization.name,
            "email": organization._temporary_admin_email,
            "password": organization._temporary_admin_password,
        }
        messages.success(self.request, f"{organization.name} was created. Save the temporary administrator password shown below.", extra_tags="organization-created")
        return redirect(self.success_url)


class CompanyUpdateView(PlatformAdminRequiredMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = "platform_admin/company_form.html"
    success_url = reverse_lazy("platform-dashboard")

    def form_valid(self, form):
        messages.success(self.request, f"{form.instance.name} settings were saved.", extra_tags="organization-updated")
        return super().form_valid(form)


def toggle_company(request, pk):
    if not request.user.is_authenticated or not (request.user.is_superuser or request.user.is_platform_admin):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed

        return HttpResponseNotAllowed(["POST"])
    company = get_object_or_404(Company, pk=pk)
    company.is_active = not company.is_active
    company.save(update_fields=["is_active", "updated_at"])
    if company.is_active:
        messages.success(request, f"{company.name} workspace is active again.", extra_tags="organization-activated")
    else:
        messages.success(request, f"{company.name} workspace is now inactive.", extra_tags="organization-suspended")
    return redirect("platform-dashboard")


def remove_company(request, pk):
    if not request.user.is_authenticated or not (request.user.is_superuser or request.user.is_platform_admin):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed

        return HttpResponseNotAllowed(["POST"])
    with transaction.atomic():
        company = get_object_or_404(Company.objects.select_for_update(), pk=pk)
        company_name = company.name
        membership_user_ids = OrganizationMembership.objects.filter(organization=company).values("user_id")
        linked_users = User.objects.select_for_update().filter(
            Q(company=company) | Q(pk__in=membership_user_ids)
        )
        deleted_user_count = 0

        for user in linked_users:
            has_other_membership = OrganizationMembership.objects.filter(user=user).exclude(
                organization=company
            ).exists()
            # PlatformRole rows can be stale; platform access is authorized by these flags.
            is_protected = user.is_superuser or user.is_platform_admin or has_other_membership

            if is_protected:
                if user.company_id == company.pk:
                    User.objects.filter(pk=user.pk).update(company=None)
            else:
                user.delete()
                deleted_user_count += 1

        company.delete()

    account_word = "account" if deleted_user_count == 1 else "accounts"
    messages.success(
        request,
        f"{company_name} was permanently removed. {deleted_user_count} organization-only {account_word} and their login emails were deleted.",
        extra_tags="organization-removed",
    )
    return redirect("platform-dashboard")
