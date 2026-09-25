from django.urls import path

from .views import (AdjustmentView, AuditView, DashboardView, DocumentActionView, DocumentsView,
                    InventoryView, MasterView, ReportsView, RolesView)


urlpatterns = [
    path("", DashboardView.as_view(), name="rt-dashboard"),
    path("inventory/", InventoryView.as_view(), name="rt-inventory"),
    path("inventory/adjust/", AdjustmentView.as_view(), name="rt-inventory-adjust"),
    path("reports/", ReportsView.as_view(), name="rt-reports"),
    path("reports/export/", ReportsView.as_view(export=True), name="rt-reports-export"),
    path("roles/", RolesView.as_view(), name="rt-roles"),
    path("audit/", AuditView.as_view(), name="rt-audit"),
    path("api/dashboard/", DashboardView.as_view(api=True), name="rt-api-dashboard"),
    path("api/products/", MasterView.as_view(resource="products", api=True), name="rt-api-products"),
    path("api/inventory/", InventoryView.as_view(api=True), name="rt-api-inventory"),
    path("api/sales/", DocumentsView.as_view(api=True), name="rt-api-sales"),
    path("api/sales/<int:pk>/", DocumentsView.as_view(mode="detail", api=True), name="rt-api-sales-detail"),
]
for resource in ("products", "categories", "locations", "suppliers", "customers"):
    urlpatterns.extend([
        path(f"{resource}/", MasterView.as_view(resource=resource), name=f"rt-{resource}"),
        path(f"{resource}/new/", MasterView.as_view(resource=resource, mode="create"), name=f"rt-{resource}-create"),
        path(f"{resource}/<int:pk>/edit/", MasterView.as_view(resource=resource, mode="edit"), name=f"rt-{resource}-edit"),
    ])
for module, kind in [("sales", "sale"), ("purchases", "purchase")]:
    urlpatterns.extend([
        path(f"{module}/", DocumentsView.as_view(kind=kind), name=f"rt-{module}"),
        path(f"{module}/new/", DocumentsView.as_view(kind=kind, mode="create"), name=f"rt-{module}-create"),
        path(f"{module}/<int:pk>/", DocumentsView.as_view(kind=kind, mode="detail"), name=f"rt-{module}-detail"),
        path(f"{module}/<int:pk>/edit/", DocumentsView.as_view(kind=kind, mode="edit"), name=f"rt-{module}-edit"),
    ])
    for action in (["post", "cancel", "refund"] if kind == "sale" else ["post", "cancel"]):
        urlpatterns.append(path(f"{module}/<int:pk>/{action}/", DocumentActionView.as_view(kind=kind, action=action), name=f"rt-{module}-{action}"))
