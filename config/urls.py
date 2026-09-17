from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import DashboardView, ReportsView, SystemSettingsView
from accounts.views import UnifiedLoginView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", UnifiedLoginView.as_view(), name="home"),
    path("workspace/", DashboardView.as_view(), name="dashboard"),
    path("", include("accounts.urls")),
    path("", include("projects.urls")),
    path("", include("workflows.urls")),
    path("reports/", ReportsView.as_view(), name="reports"),
    path("settings/", SystemSettingsView.as_view(), name="system-settings"),
    path("platform/", include("platform_admin.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
