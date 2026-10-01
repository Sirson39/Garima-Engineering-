from __future__ import annotations

import hashlib

from django.contrib.auth import login, logout
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import TemplateView
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import CreateView, FormView
from django.utils import timezone

from accounts.forms import GarimaAuthenticationForm, OrganizationUserForm, UnifiedAuthenticationForm
from accounts.models import OrganizationInvitation, OrganizationMembership, PlatformRole, User
from core.services import log_audit
from accounts.workspace_access import active_membership


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


class OrganizationInvitationView(FormView):
    template_name = "registration/organization_invitation.html"
    form_class = SetPasswordForm

    def dispatch(self, request, *args, **kwargs):
        digest = hashlib.sha256(kwargs["token"].encode()).hexdigest()
        self.invitation = get_object_or_404(
            OrganizationInvitation.objects.select_related("organization"),
            token_digest=digest,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        )
        if self.invitation.expires_at <= timezone.now():
            return render(
                request,
                self.template_name,
                {"expired": True, "organization": self.invitation.organization},
            )
        self.user = get_object_or_404(User, email__iexact=self.invitation.email)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"organization": self.invitation.organization, "invitation": self.invitation})
        return context

    def form_valid(self, form):
        with transaction.atomic():
            form.save()
            self.user.is_active = True
            self.user.must_change_password = False
            self.user.save(update_fields=["password", "is_active", "must_change_password"])
            membership = OrganizationMembership.objects.get(
                user=self.user,
                organization=self.invitation.organization,
            )
            membership.is_active = True
            membership.save(update_fields=["is_active"])
            self.invitation.accepted_at = timezone.now()
            self.invitation.save(update_fields=["accepted_at"])
            log_audit(
                self.user,
                "organization.invitation_accepted",
                obj=self.invitation.organization,
                summary=f"Accepted invitation for {self.invitation.organization.name}.",
            )
        login(self.request, self.user)
        self.request.session["organization_id"] = self.invitation.organization_id
        return redirect("dashboard")


def logout_view(request):
    logout(request)
    return redirect("login")


class OrganizationAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        self.membership = active_membership(
            self.request.user, self.request.session.get("organization_id") or self.request.user.company_id
        ) if self.request.user.is_authenticated else None
        return bool(self.membership and self.membership.role == "admin")


class UsersAndRolesView(OrganizationAdminRequiredMixin, TemplateView):
    template_name = "accounts/users_roles.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["memberships"] = OrganizationMembership.objects.filter(
            organization=self.membership.organization
        ).select_related("user").order_by("user__first_name", "user__last_name", "user__email")
        context["team_organization"] = self.membership.organization
        return context


class OrganizationUserCreateView(OrganizationAdminRequiredMixin, FormView):
    template_name = "accounts/organization_user_form.html"
    form_class = OrganizationUserForm
    success_url = reverse_lazy("users-roles")

    def form_valid(self, form):
        organization = self.membership.organization
        role = form.cleaned_data["role"]
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=form.cleaned_data["email"], email=form.cleaned_data["email"],
                    password=form.cleaned_data["initial_password"],
                    first_name=form.cleaned_data["first_name"], last_name=form.cleaned_data["last_name"],
                    company=organization, company_role=role, must_change_password=True,
                )
                OrganizationMembership.objects.create(user=user, organization=organization, role=role)
                log_audit(self.request.user, "organization.account_created", obj=user,
                          summary=f"Created {role} account in {organization.name}.",
                          metadata={"organization_id": organization.pk, "account_type": role})
        except IntegrityError:
            form.add_error("email", "This login email is already in use.")
            return self.form_invalid(form)
        messages.success(self.request, f"Account created for {user.email}. Share their login email and temporary password privately. They will change it on first login.")
        return super().form_valid(form)
