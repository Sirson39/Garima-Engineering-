from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from .forms import ValuationBankForm, ValuationRequestForm
from .models import ValuationBank, ValuationDocumentChecklist, ValuationRequest
from .services import create_default_checklist, next_reference_number, transition_request, user_can_manage_valuation, valuation_organization_for


class ValuationAccessMixin(LoginRequiredMixin):
    valuation_permission = "view"

    def dispatch(self, request, *args, **kwargs):
        self.valuation_organization = valuation_organization_for(request.user)
        if not user_can_manage_valuation(request.user, self.valuation_organization, self.valuation_permission):
            raise PermissionDenied("You do not have permission to access this valuation area.")
        return super().dispatch(request, *args, **kwargs)


class ValuationDashboardView(ValuationAccessMixin, TemplateView):
    template_name = "valuation/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        requests = ValuationRequest.objects.filter(organization=self.valuation_organization)
        context.update({
            "valuation_organization": self.valuation_organization,
            "total_files": requests.count(),
            "new_requests": requests.filter(status=ValuationRequest.STATUS_REQUEST_RECEIVED).count(),
            "documents_pending": requests.filter(status=ValuationRequest.STATUS_DOCUMENTS_PENDING).count(),
            "draft_reports": requests.filter(status=ValuationRequest.STATUS_VALUATION_DRAFTED).count(),
            "under_review": requests.filter(status=ValuationRequest.STATUS_INTERNAL_REVIEW).count(),
            "corrections_required": requests.filter(status=ValuationRequest.STATUS_CORRECTION_REQUIRED).count(),
            "approved_reports": requests.filter(status=ValuationRequest.STATUS_APPROVED).count(),
            "issued_reports": requests.filter(status=ValuationRequest.STATUS_REPORT_ISSUED).count(),
        })
        return context


class ValuationRequestListView(ValuationAccessMixin, ListView):
    template_name = "valuation/request_list.html"
    context_object_name = "valuation_requests"

    def get_queryset(self):
        return ValuationRequest.objects.filter(organization=self.valuation_organization).select_related("bank", "assigned_engineer")


class ValuationRequestCreateView(ValuationAccessMixin, CreateView):
    valuation_permission = "create"
    model = ValuationRequest
    form_class = ValuationRequestForm
    template_name = "valuation/request_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.valuation_organization
        return kwargs

    def form_valid(self, form):
        form.instance.organization = self.valuation_organization
        form.instance.reference_number = next_reference_number(self.valuation_organization)
        form.instance.created_by = self.request.user
        with transaction.atomic():
            response = super().form_valid(form)
            create_default_checklist(self.object)
        messages.success(self.request, f"Valuation request {form.instance.reference_number} was created.")
        return response

    def get_success_url(self):
        return self.object.get_absolute_url()


class ValuationRequestDetailView(ValuationAccessMixin, DetailView):
    model = ValuationRequest
    template_name = "valuation/request_detail.html"
    context_object_name = "valuation_request"

    def get_queryset(self):
        return ValuationRequest.objects.filter(organization=self.valuation_organization).select_related("bank", "assigned_engineer", "assigned_site_inspector").prefetch_related("document_checklist", "activities", "review_comments")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = ValuationRequest.STATUS_CHOICES
        return context


class ValuationBankListView(ValuationAccessMixin, ListView):
    template_name = "valuation/bank_list.html"
    context_object_name = "banks"

    def get_queryset(self):
        return ValuationBank.objects.filter(organization=self.valuation_organization)


class ValuationBankCreateView(ValuationAccessMixin, CreateView):
    valuation_permission = "create"
    model = ValuationBank
    form_class = ValuationBankForm
    template_name = "valuation/bank_form.html"
    success_url = reverse_lazy("valuation-banks")

    def form_valid(self, form):
        form.instance.organization = self.valuation_organization
        messages.success(self.request, "Bank or financial institution was added.")
        return super().form_valid(form)


def transition_valuation_request(request, pk):
    organization = valuation_organization_for(request.user)
    if not user_can_manage_valuation(request.user, organization, "change"):
        raise PermissionDenied("You do not have permission to update valuation workflow status.")
    if request.method != "POST":
        return redirect("valuation-request-detail", pk=pk)
    valuation_request = get_object_or_404(ValuationRequest, pk=pk, organization=organization)
    try:
        transition_request(
            request=valuation_request,
            actor=request.user,
            to_status=request.POST.get("to_status", ""),
            reason=request.POST.get("reason", "").strip(),
        )
        messages.success(request, "Valuation workflow status updated.")
    except ValidationError as error:
        messages.error(request, str(error))
    return redirect("valuation-request-detail", pk=pk)
