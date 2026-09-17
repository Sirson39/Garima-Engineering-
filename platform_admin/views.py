from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db.models import Count, OuterRef, Subquery
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, TemplateView, UpdateView

from accounts.models import Company, OrganizationMembership, User
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
        messages.success(self.request, "Your profile settings were updated.")
        return super().form_valid(form)


class CompanyCreateView(PlatformAdminRequiredMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = "platform_admin/company_form.html"
    success_url = reverse_lazy("platform-dashboard")

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.created_by = self.request.user
            response = super().form_valid(form)
            password = form.cleaned_data["initial_password"]
            email = form.cleaned_data["admin_email"]
            user = User.objects.create_user(
                username=email,
                email=email,
                company=form.instance,
                company_role=User.ROLE_ADMIN,
                must_change_password=True,
            )
            user.set_password(password)
            user.save(update_fields=["password"])
            OrganizationMembership.objects.create(user=user, organization=form.instance, role="admin")
        messages.success(self.request, f"{form.instance.name} and its first Admin account were created.")
        return response


class CompanyUpdateView(PlatformAdminRequiredMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = "platform_admin/company_form.html"
    success_url = reverse_lazy("platform-dashboard")

    def form_valid(self, form):
        messages.success(self.request, f"{form.instance.name} was updated.")
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
    messages.success(request, f"{company.name} is now {'active' if company.is_active else 'inactive'}.")
    return redirect("platform-dashboard")
