from django.contrib.auth.views import LogoutView
from django.urls import path

from accounts.views import GarimaLoginView, UsersAndRolesView, logout_view


urlpatterns = [
    path("login/", GarimaLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
    path("users/", UsersAndRolesView.as_view(), name="users-roles"),
]

