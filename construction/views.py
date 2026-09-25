from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from accounts.models import User
from core.services import log_audit
from .forms import ConstructionProjectForm
from .models import ConstructionProject
from .services import active_construction_organization, construction_projects_for_user


class ConstructionAccessMixin(LoginRequiredMixin):
    def get_construction_organization(self):
        if not hasattr(self, "construction_organization"):
            self.construction_organization = active_construction_organization(self.request.user, self.request.session.get("organization_id"))
        return self.construction_organization


class ConstructionDashboardView(ConstructionAccessMixin, TemplateView):
    template_name = "construction/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = self.get_construction_organization()
        projects = construction_projects_for_user(self.request.user, organization)
        context.update({
            "page_title": "Construction dashboard",
            "construction_organization": organization,
            "projects": projects.select_related("project_manager")[:8],
            "project_count": projects.count(),
            "active_count": projects.filter(status=ConstructionProject.STATUS_ACTIVE).count(),
            "delayed_count": projects.filter(status=ConstructionProject.STATUS_ON_HOLD).count(),
            "contract_total": projects.aggregate(total=Sum("contract_value"))["total"] or 0,
            "status_counts": projects.values("status").annotate(total=Count("id")),
        })
        return context


class ConstructionProjectListView(ConstructionAccessMixin, ListView):
    template_name = "construction/project_list.html"
    context_object_name = "projects"
    paginate_by = 20

    def get_queryset(self):
        organization = self.get_construction_organization()
        queryset = construction_projects_for_user(self.request.user, organization).select_related("project_manager")
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        if query:
            queryset = queryset.filter(name__icontains=query) | queryset.filter(project_number__icontains=query)
        if status:
            queryset = queryset.filter(status=status)
        return queryset.order_by("project_number")


class ConstructionProjectCreateView(ConstructionAccessMixin, CreateView):
    model = ConstructionProject
    form_class = ConstructionProjectForm
    template_name = "construction/project_form.html"
    success_url = reverse_lazy("construction-project-list")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        organization = self.get_construction_organization()
        form.fields["project_manager"].queryset = User.objects.filter(
            organization_memberships__organization=organization,
            organization_memberships__is_active=True,
            is_active=True,
        ).distinct().order_by("first_name", "last_name", "email")
        return form

    def form_valid(self, form):
        organization = self.get_construction_organization()
        form.instance.organization = organization
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_audit(self.request.user, "construction.project.created", obj=self.object, summary=self.object.name)
        messages.success(self.request, f"Construction project {self.object.project_number} was created.")
        return response


class ConstructionProjectDetailView(ConstructionAccessMixin, DetailView):
    model = ConstructionProject
    template_name = "construction/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        return construction_projects_for_user(self.request.user, self.get_construction_organization()).select_related("project_manager")
