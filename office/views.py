from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from accounts.models import OrganizationModule
from .forms import OfficeDepartmentForm
from .models import OfficeDepartment, OfficeStaffProfile
from .services import active_office_organization


class OfficeAccessMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        self.office_organization = active_office_organization(request.user)
        return super().dispatch(request, *args, **kwargs)


class OfficeDashboardView(OfficeAccessMixin, TemplateView):
    template_name = "office/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = self.office_organization
        context.update({
            "office_organization": organization,
            "staff_count": OfficeStaffProfile.objects.filter(organization=organization).count(),
            "active_staff_count": OfficeStaffProfile.objects.filter(organization=organization, employment_status="active").count(),
            "department_count": OfficeDepartment.objects.filter(organization=organization, is_active=True).count(),
            "enabled_modules": OrganizationModule.objects.filter(organization=organization, is_enabled=True).select_related("module"),
        })
        return context


class OfficeStaffListView(OfficeAccessMixin, TemplateView):
    template_name = "office/staff_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["office_staff"] = OfficeStaffProfile.objects.filter(
            organization=self.office_organization,
        ).select_related("user", "department", "manager__user")
        return context


class OfficeDepartmentListView(OfficeAccessMixin, TemplateView):
    template_name = "office/department_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["departments"] = OfficeDepartment.objects.filter(
            organization=self.office_organization,
        ).select_related("department_head", "parent")
        return context


class OfficeDepartmentCreateView(OfficeAccessMixin, CreateView):
    model = OfficeDepartment
    form_class = OfficeDepartmentForm
    template_name = "office/department_form.html"
    success_url = reverse_lazy("office-departments")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.office_organization
        return kwargs

    def form_valid(self, form):
        form.instance.organization = self.office_organization
        response = super().form_valid(form)
        messages.success(self.request, f"{form.instance.name} department was created.")
        return response
