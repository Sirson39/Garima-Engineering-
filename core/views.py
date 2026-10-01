from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView, UpdateView

from core.forms import OrganizationProfileForm
from core.models import Notification, OrganizationProfile
from core.services import build_dashboard_context


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        membership = getattr(self.request, "workspace_membership", None)
        if membership:
            return membership.role == "admin"
        return self.request.user.is_authenticated and self.request.user.is_staff


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get(self, request, *args, **kwargs):
        from accounts.models import Company

        selected_organization_id = request.session.get("organization_id") or request.user.company_id
        membership = getattr(request, "workspace_membership", None)
        if membership and membership.organization.system_template and membership.organization.system_template.code == "engineering-consultancy":
            if membership.role in {"engineer", "staff"}:
                return redirect(f"{membership.role}-dashboard")
        if Company.objects.filter(pk=selected_organization_id, system_template__code="retail-management").exists():
            return redirect("rt-dashboard")
        if Company.objects.filter(pk=selected_organization_id, system_template__code="professional-services").exists():
            return redirect("ps-dashboard")
        company = getattr(request.user, "company", None)
        if company and company.system_template and company.system_template.code == "general-office-management":
            return redirect(reverse("office-dashboard"))
        if company and company.system_template and company.system_template.code == "valuation-management":
            return redirect(reverse("valuation-dashboard"))
        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        company = getattr(self.request.user, "company", None)
        if company and company.system_template and company.system_template.code == "custom-organization":
            return ["core/custom_dashboard.html"]
        if company and company.system_template and company.system_template.code == "hospital-management":
            return ["core/hospital_dashboard.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = getattr(self.request.user, "company", None)
        if company and company.system_template and company.system_template.code == "custom-organization":
            from accounts.models import OrganizationConfiguration, OrganizationModule

            context["custom_organization"] = company
            context["custom_modules"] = OrganizationModule.objects.filter(
                organization=company,
                is_enabled=True,
            ).select_related("module")
            context["custom_configuration"] = OrganizationConfiguration.objects.filter(
                organization=company,
                status=OrganizationConfiguration.STATUS_PUBLISHED,
            ).select_related("starting_structure").first()
            context["recent_notifications"] = Notification.objects.filter(user=self.request.user).order_by("-created_at")[:8]
            return context
        if company and company.system_template and company.system_template.code == "hospital-management":
            from accounts.models import OrganizationModule

            context["hospital_organization"] = company
            context["hospital_modules"] = OrganizationModule.objects.filter(
                organization=company,
                is_enabled=True,
            ).select_related("module")
            context["recent_notifications"] = Notification.objects.filter(user=self.request.user).order_by("-created_at")[:8]
            return context
        context.update(build_dashboard_context(self.request.user))
        context["recent_notifications"] = Notification.objects.filter(user=self.request.user).order_by("-created_at")[:8]
        context["profile"] = OrganizationProfile.load()
        return context


class EmployeeDashboardView(LoginRequiredMixin, TemplateView):
    account_type = "engineer"

    def get(self, request, *args, **kwargs):
        from django.core.exceptions import PermissionDenied
        from accounts.workspace_access import active_membership

        self.membership = active_membership(request.user)
        if (not self.membership or self.membership.role != self.account_type or
                not self.membership.organization.system_template or
                self.membership.organization.system_template.code != "engineering-consultancy"):
            raise PermissionDenied
        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        return [f"core/{self.account_type}_dashboard.html"]

    def get_context_data(self, **kwargs):
        from django.utils import timezone
        from projects.models import Task, SiteVisit, DocumentChecklistItem, PhysicalFileTransfer
        from projects.services import project_queryset_for_user

        context = super().get_context_data(**kwargs)
        projects = project_queryset_for_user(self.request.user)
        tasks = Task.objects.filter(project__in=projects, assigned_employee=self.request.user, is_deleted=False)
        open_tasks = tasks.filter(status__in={"New", "Assigned", "In Progress", "Correction Required"})
        context.update({
            "team_organization": self.membership.organization,
            "project_count": projects.count(), "open_task_count": open_tasks.count(),
            "overdue_count": open_tasks.filter(due_date__lt=timezone.localdate()).count(),
            "my_tasks": open_tasks.select_related("project").order_by("due_date", "pk")[:8],
            "my_projects": projects.order_by("-updated_at")[:6],
        })
        if self.account_type == "engineer":
            context["my_visits"] = SiteVisit.objects.filter(
                project__in=projects, assigned_engineer=self.request.user, is_deleted=False,
            ).exclude(visit_status__in=["Completed", "Cancelled"]).select_related("project").order_by("scheduled_date")[:6]
        else:
            context["pending_documents"] = DocumentChecklistItem.objects.filter(
                project__in=projects, required=True, received=False, is_deleted=False,
            ).select_related("project")[:6]
            context["pending_handovers"] = PhysicalFileTransfer.objects.filter(
                project__in=projects, received_confirmation=False, is_deleted=False,
            ).count()
        return context


class ReportsView(LoginRequiredMixin, TemplateView):
    template_name = "core/reports.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_dashboard_context(self.request.user))
        return context


class SystemSettingsView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = OrganizationProfile
    form_class = OrganizationProfileForm
    template_name = "core/settings.html"
    success_url = reverse_lazy("system-settings")

    def get_object(self, queryset=None):
        return OrganizationProfile.load()

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "System settings updated successfully.")
        return super().form_valid(form)
