from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView

from core.forms import OrganizationProfileForm
from core.models import Notification, OrganizationProfile
from core.services import build_dashboard_context


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_dashboard_context(self.request.user))
        context["recent_notifications"] = Notification.objects.filter(user=self.request.user).order_by("-created_at")[:8]
        context["profile"] = OrganizationProfile.load()
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

