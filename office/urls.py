from django.urls import path

from .views import OfficeDashboardView, OfficeDepartmentCreateView, OfficeDepartmentListView, OfficeStaffListView


urlpatterns = [
    path("", OfficeDashboardView.as_view(), name="office-dashboard"),
    path("staff/", OfficeStaffListView.as_view(), name="office-staff"),
    path("departments/", OfficeDepartmentListView.as_view(), name="office-departments"),
    path("departments/new/", OfficeDepartmentCreateView.as_view(), name="office-department-create"),
]
