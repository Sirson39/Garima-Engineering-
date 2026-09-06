from django.urls import path

from workflows.views import WorkflowCatalogView


urlpatterns = [
    path("workflows/", WorkflowCatalogView.as_view(), name="workflow-catalog"),
]

