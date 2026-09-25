from django.contrib.auth.views import LogoutView
from django.urls import path

from accounts.views import AccessDeniedView, FirstLoginPasswordChangeView, GarimaLoginView, OrganizationInvitationView, OrganizationSelectionView, OrganizationUserCreateView, UnifiedLoginView, UsersAndRolesView, logout_view


urlpatterns = [
    path("login/", UnifiedLoginView.as_view(), name="login"),
    path("garima-login/", GarimaLoginView.as_view(), name="garima-login"),
    path("choose-organization/", OrganizationSelectionView.as_view(), name="organization-select"),
    path("access-denied/", AccessDeniedView.as_view(), name="access-denied"),
    path("password-change/", FirstLoginPasswordChangeView.as_view(), name="password-change"),
    path("organization-invitations/<str:token>/", OrganizationInvitationView.as_view(), name="organization-invitation"),
    path("logout/", logout_view, name="logout"),
    path("users/", UsersAndRolesView.as_view(), name="users-roles"),
    path("users/new/", OrganizationUserCreateView.as_view(), name="organization-user-create"),
]
