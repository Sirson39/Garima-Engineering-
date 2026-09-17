from django.urls import path

from platform_admin.views import AuditLogsView, BillingPlansView, CompanyCreateView, CompanyUpdateView, PlatformDashboardView, PlatformLandingView, PlatformLoginView, PlatformProfileView, PlatformSettingsView, SupportInboxView, toggle_company


urlpatterns = [
    path("login/", PlatformLoginView.as_view(), name="platform-login"),
    path("admin/", PlatformDashboardView.as_view(), name="platform-dashboard"),
    path("support/", SupportInboxView.as_view(), name="platform-support"),
    path("billing/", BillingPlansView.as_view(), name="platform-billing"),
    path("audit-logs/", AuditLogsView.as_view(), name="platform-audit-logs"),
    path("settings/", PlatformSettingsView.as_view(), name="platform-settings"),
    path("profile/", PlatformProfileView.as_view(), name="platform-profile"),
    path("", PlatformLandingView.as_view(), name="platform-landing"),
    path("companies/new/", CompanyCreateView.as_view(), name="platform-company-create"),
    path("companies/<int:pk>/edit/", CompanyUpdateView.as_view(), name="platform-company-edit"),
    path("companies/<int:pk>/toggle/", toggle_company, name="platform-company-toggle"),
]
