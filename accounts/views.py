from __future__ import annotations

from django.contrib.auth import logout
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from accounts.forms import GarimaAuthenticationForm
from accounts.models import User


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


def logout_view(request):
    logout(request)
    return redirect("login")


class UsersAndRolesView(LoginRequiredMixin, StaffRequiredMixin, TemplateView):
    template_name = "accounts/users_roles.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["users"] = User.objects.prefetch_related("groups").order_by("first_name", "last_name", "username")
        context["groups"] = Group.objects.annotate(user_count=Count("user")).order_by("name")
        return context
