from __future__ import annotations

from django.contrib.auth import login, logout
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import TemplateView
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import CreateView, FormView

from accounts.forms import GarimaAuthenticationForm, OrganizationUserForm, UnifiedAuthenticationForm
from accounts.models import OrganizationMembership, PlatformRole, User


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


class GarimaLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = GarimaAuthenticationForm

    def get_success_url(self):
        next_url = self.get_redirect_url()
        return next_url or reverse_lazy("dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get("remember_me"):
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        else:
            self.request.session.set_expiry(0)
        return response


class UnifiedLoginView(LoginView):
    template_name = "registration/unified_login.html"
    authentication_form = UnifiedAuthenticationForm

    def get_success_url(self):
        user = self.request.user
        if user.must_change_password:
            return reverse_lazy("password-change")
        if user.is_superuser or PlatformRole.objects.filter(user=user, is_active=True, role="super_admin").exists():
            return reverse_lazy("platform-dashboard")
        memberships = list(
            OrganizationMembership.objects.filter(user=user, is_active=True, organization__is_active=True)
            .select_related("organization")
        )
        if len(memberships) == 1:
            self.request.session["organization_id"] = memberships[0].organization_id
            return reverse_lazy("dashboard")
        if len(memberships) > 1:
            return reverse_lazy("organization-select")
        return reverse_lazy("access-denied")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get("remember_me"):
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        else:
            self.request.session.set_expiry(0)
        return response


class FirstLoginPasswordChangeView(LoginRequiredMixin, FormView):
    template_name = "registration/first_login_password.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("dashboard")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = form.save()
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        login(self.request, user)
        if PlatformRole.objects.filter(user=user, is_active=True, role="super_admin").exists() or user.is_superuser:
            self.success_url = reverse_lazy("platform-dashboard")
        elif OrganizationMembership.objects.filter(user=user, is_active=True, organization__is_active=True).count() > 1:
            self.success_url = reverse_lazy("organization-select")
        return super().form_valid(form)


class OrganizationSelectionView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/organization_select.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["memberships"] = OrganizationMembership.objects.filter(
            user=self.request.user, is_active=True, organization__is_active=True
        ).select_related("organization")
        return context

    def post(self, request, *args, **kwargs):
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization_id=request.POST.get("organization_id"), is_active=True, organization__is_active=True
        ).first()
        if not membership:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        request.session["organization_id"] = membership.organization_id
        return redirect("dashboard")


class AccessDeniedView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/access_denied.html"


def logout_view(request):
    logout(request)
    return redirect("login")


class OrganizationAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (
            user.is_superuser
            or user.is_platform_admin
            or OrganizationMembership.objects.filter(user=user, role="admin", is_active=True).exists()
        )


class UsersAndRolesView(OrganizationAdminRequiredMixin, TemplateView):
    template_name = "accounts/users_roles.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        users = User.objects.prefetch_related("groups").order_by("first_name", "last_name", "username")
        if not (self.request.user.is_superuser or self.request.user.is_platform_admin):
            users = users.filter(company=self.request.user.company)
        context["users"] = users
        context["groups"] = Group.objects.annotate(user_count=Count("user")).order_by("name")
        return context


class OrganizationUserCreateView(OrganizationAdminRequiredMixin, FormView):
    template_name = "accounts/organization_user_form.html"
    form_class = OrganizationUserForm
    success_url = reverse_lazy("users-roles")

    def form_valid(self, form):
        organization = self.request.user.company
        if not organization:
            from django.core.exceptions import ValidationError

            form.add_error(None, ValidationError("Your account is not assigned to an organization."))
            return self.form_invalid(form)
        role = form.cleaned_data["role"]
        user = User.objects.create_user(
            username=form.cleaned_data["email"],
            email=form.cleaned_data["email"],
            company=organization,
            company_role=role,
            must_change_password=True,
        )
        user.set_password(form.cleaned_data["initial_password"])
        user.save(update_fields=["password"])
        OrganizationMembership.objects.create(user=user, organization=organization, role=role)
        messages.success(self.request, f"{user.email} was added as an {role.title()}.")
        return super().form_valid(form)
