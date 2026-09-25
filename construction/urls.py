from django.urls import path

from .views import ConstructionDashboardView, ConstructionProjectCreateView, ConstructionProjectDetailView, ConstructionProjectListView


urlpatterns = [
    path("", ConstructionDashboardView.as_view(), name="construction-dashboard"),
    path("projects/", ConstructionProjectListView.as_view(), name="construction-project-list"),
    path("projects/new/", ConstructionProjectCreateView.as_view(), name="construction-project-create"),
    path("projects/<int:pk>/", ConstructionProjectDetailView.as_view(), name="construction-project-detail"),
]
