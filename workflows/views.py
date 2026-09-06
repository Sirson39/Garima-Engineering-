from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView

from workflows.models import DocumentTemplate, NumberingScheme, ServiceType, WorkflowStageTemplate


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


class WorkflowCatalogView(LoginRequiredMixin, StaffRequiredMixin, TemplateView):
    template_name = "workflows/catalog.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["service_types"] = ServiceType.objects.filter(is_active=True).prefetch_related(
            "workflow_stages",
            "document_templates",
        )
        context["numbering_schemes"] = NumberingScheme.objects.select_related("service_type")
        context["stage_count"] = WorkflowStageTemplate.objects.count()
        context["document_template_count"] = DocumentTemplate.objects.count()
        return context

