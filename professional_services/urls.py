from django.urls import path

from .views import AuditView, DashboardView, ResourceView, RolesView, SettingsView


urlpatterns = [
    path("", DashboardView.as_view(), name="ps-dashboard"),
    path("api/dashboard/", DashboardView.as_view(api=True), name="ps-api-dashboard"),
    path("settings/", SettingsView.as_view(), name="ps-settings"),
    path("roles/", RolesView.as_view(), name="ps-roles"),
    path("audit/", AuditView.as_view(), name="ps-audit"),
]
for resource in ("clients", "services", "engagements"):
    urlpatterns.extend([
        path(f"{resource}/", ResourceView.as_view(resource=resource), name=f"ps-{resource}"),
        path(f"{resource}/new/", ResourceView.as_view(resource=resource, mode="create"), name=f"ps-{resource}-create"),
        path(f"{resource}/<int:pk>/", ResourceView.as_view(resource=resource, mode="detail"), name=f"ps-{resource}-detail"),
        path(f"{resource}/<int:pk>/edit/", ResourceView.as_view(resource=resource, mode="edit"), name=f"ps-{resource}-edit"),
        path(f"api/{resource}/", ResourceView.as_view(resource=resource, api=True), name=f"ps-api-{resource}"),
        path(f"api/{resource}/<int:pk>/", ResourceView.as_view(resource=resource, mode="detail", api=True), name=f"ps-api-{resource}-detail"),
    ])
