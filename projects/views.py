from __future__ import annotations

from io import BytesIO

import qrcode
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django import forms
from django.views.generic import CreateView, DetailView, FormView, ListView, View

from core.services import log_audit, notify_user
from projects.forms import (
    ClientForm,
    GovernmentRecordForm,
    MunicipalityActivityForm,
    PaymentForm,
    PhysicalFileTransferForm,
    ProjectCommentForm,
    ProjectDocumentUploadForm,
    ProjectForm,
    ProjectStageAdvanceForm,
    SiteVisitForm,
    TaskForm,
)
from projects.models import (
    Client,
    GovernmentRecord,
    MunicipalityActivity,
    Payment,
    PhysicalFileTransfer,
    Project,
    ProjectComment,
    ProjectDocument,
    SiteVisit,
    Task,
)
from projects.services import (
    advance_project_stage,
    create_document_revision,
    create_project_initial_state,
    project_queryset_for_user,
    required_documents_missing,
    user_can_access_project,
    user_has_role,
)


User = get_user_model()


class ProjectAccessMixin(LoginRequiredMixin):
    project = None
    lookup_url_kwarg = "pk"

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project.objects.select_related("client", "service_type", "current_responsible_employee", "current_stage_template", "current_stage_record"),
            pk=kwargs.get(self.lookup_url_kwarg),
            is_deleted=False,
        )
        if not user_can_access_project(request.user, self.project):
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


class BaseTableListView(LoginRequiredMixin, ListView):
    template_name = "projects/table_page.html"
    paginate_by = 15
    title = ""
    headers: list[str] = []
    create_url_name: str | None = None
    create_label = "Add new"
    empty_text = "No records found."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.title
        context["headers"] = self.headers
        context["rows"] = [self.row_for_object(obj) for obj in context["object_list"]]
        context["create_url"] = reverse(self.create_url_name) if self.create_url_name else ""
        context["create_label"] = self.create_label
        context["empty_text"] = self.empty_text
        return context

    def row_for_object(self, obj):
        raise NotImplementedError


class ProjectListView(BaseTableListView):
    model = Project
    title = "All Projects"
    headers = ["Project", "Client", "Service", "Stage", "Responsible", "Status", "Balance"]
    create_url_name = "project-create"

    def get_queryset(self):
        qs = project_queryset_for_user(self.request.user)
        q = self.request.GET.get("q", "").strip()
        service = self.request.GET.get("service")
        employee = self.request.GET.get("employee")
        status = self.request.GET.get("status")
        municipality = self.request.GET.get("municipality", "").strip()
        ward = self.request.GET.get("ward", "").strip()
        payment_status = self.request.GET.get("payment_status")
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")

        if q:
            qs = qs.filter(
                Q(project_number__icontains=q)
                | Q(client__full_name__icontains=q)
                | Q(client__mobile_number__icontains=q)
                | Q(client__citizenship_number__icontains=q)
                | Q(kitta_number__icontains=q)
                | Q(sheet_number__icontains=q)
                | Q(municipality__icontains=q)
                | Q(ward_number__icontains=q)
                | Q(government_application_number__icontains=q)
                | Q(current_responsible_employee__first_name__icontains=q)
                | Q(current_responsible_employee__last_name__icontains=q)
                | Q(current_file_holder__icontains=q)
            )
        if service:
            qs = qs.filter(service_type_id=service)
        if employee:
            qs = qs.filter(current_responsible_employee_id=employee)
        if status:
            qs = qs.filter(status=status)
        if municipality:
            qs = qs.filter(municipality__icontains=municipality)
        if ward:
            qs = qs.filter(ward_number__icontains=ward)
        if payment_status == "due":
            qs = qs.filter(remaining_balance__gt=0)
        elif payment_status == "paid":
            qs = qs.filter(remaining_balance__lte=0)
        if date_from:
            qs = qs.filter(registration_date__gte=date_from)
        if date_to:
            qs = qs.filter(registration_date__lte=date_to)

        return qs.select_related("client", "service_type", "current_responsible_employee", "current_stage_template").order_by("-updated_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from workflows.models import ServiceType

        context["service_types"] = ServiceType.objects.filter(is_active=True).order_by("name")
        context["employees"] = User.objects.filter(is_active=True, is_staff=True).order_by("first_name", "last_name")
        context["status_choices"] = Project._meta.get_field("status").choices
        context["selected"] = self.request.GET
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["query_params"] = query_params.urlencode()
        return context

    def row_for_object(self, project):
        detail_url = reverse("project-detail", kwargs={"pk": project.pk})
        return {
            "detail_url": detail_url,
            "cells": [
                format_html('<a href="{}" class="fw-semibold text-decoration-none">{}</a>', detail_url, project.project_number),
                project.client.full_name,
                project.service_type.name,
                format_html('<span class="badge text-bg-info">{}</span>', project.current_stage_template.name if project.current_stage_template else project.status),
                project.current_responsible_employee.display_name if project.current_responsible_employee else "Unassigned",
                format_html('<span class="badge text-bg-secondary">{}</span>', project.status),
                f"{project.remaining_balance:.2f}",
            ],
        }

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("HX-Request") == "true":
            return HttpResponse(
                render_to_string("projects/partials/project_table.html", context, request=self.request),
                content_type=self.content_type,
            )
        return super().render_to_response(context, **response_kwargs)


class ClientListView(BaseTableListView):
    model = Client
    title = "Clients"
    headers = ["Client", "Mobile", "Municipality", "Ward", "Projects"]
    create_url_name = "client-create"

    def get_queryset(self):
        qs = Client.objects.filter(is_deleted=False)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(full_name__icontains=q)
                | Q(mobile_number__icontains=q)
                | Q(citizenship_number__icontains=q)
                | Q(municipality__icontains=q)
                | Q(ward_number__icontains=q)
            )
        return qs.annotate(project_count=Count("projects")).order_by("full_name")

    def row_for_object(self, client):
        return {
            "cells": [
                client.full_name,
                client.mobile_number,
                client.municipality or "-",
                client.ward_number or "-",
                str(getattr(client, "project_count", client.projects.count())),
            ]
        }


class TaskListView(BaseTableListView):
    model = Task
    title = "My Tasks"
    headers = ["Task", "Project", "Assigned To", "Status", "Priority", "Due Date"]

    def get_queryset(self):
        qs = Task.objects.filter(is_deleted=False).select_related("project", "assigned_employee")
        if not self.request.user.is_staff:
            qs = qs.filter(assigned_employee=self.request.user)
        return qs.order_by("status", "due_date", "-updated_at")

    def row_for_object(self, task):
        project_url = reverse("project-detail", kwargs={"pk": task.project_id})
        return {
            "detail_url": project_url,
            "cells": [
                task.title,
                format_html('<a href="{}" class="text-decoration-none">{}</a>', project_url, task.project.project_number),
                task.assigned_employee.display_name if task.assigned_employee else "Unassigned",
                task.status,
                task.priority,
                task.due_date.isoformat() if task.due_date else "-",
            ],
        }


class GenericProjectRelatedListView(BaseTableListView):
    create_url_name = None
    queryset = None


class DocumentListView(BaseTableListView):
    model = ProjectDocument
    title = "Documents"
    headers = ["Project", "Document", "Category", "Revision", "Status", "Uploaded By", "Downloaded"]

    def get_queryset(self):
        qs = ProjectDocument.objects.filter(is_deleted=False).select_related("project", "category", "uploaded_by")
        if not self.request.user.is_staff:
            qs = qs.filter(project__in=project_queryset_for_user(self.request.user))
        return qs

    def row_for_object(self, doc):
        detail_url = reverse("project-detail", kwargs={"pk": doc.project_id})
        download_url = reverse("document-download", kwargs={"pk": doc.pk})
        return {
            "detail_url": detail_url,
            "cells": [
                format_html('<a href="{}" class="text-decoration-none">{}</a>', detail_url, doc.project.project_number),
                format_html('<a href="{}">{}</a>', download_url, doc.display_name),
                doc.category.name,
                str(doc.revision_number),
                doc.approval_status,
                doc.uploaded_by.display_name if doc.uploaded_by else "-",
                format_html('<a href="{}" class="btn btn-sm btn-outline-primary">Download</a>', download_url),
            ],
        }


class FileTransferListView(BaseTableListView):
    model = PhysicalFileTransfer
    title = "Physical File Register"
    headers = ["Project", "From", "To", "Location", "Transferred", "Purpose", "Received"]

    def get_queryset(self):
        qs = PhysicalFileTransfer.objects.filter(is_deleted=False).select_related("project")
        if not self.request.user.is_staff:
            qs = qs.filter(project__in=project_queryset_for_user(self.request.user))
        return qs

    def row_for_object(self, transfer):
        detail_url = reverse("project-detail", kwargs={"pk": transfer.project_id})
        return {
            "detail_url": detail_url,
            "cells": [
                format_html('<a href="{}">{}</a>', detail_url, transfer.project.project_number),
                transfer.file_transferred_from,
                transfer.file_transferred_to,
                transfer.current_location,
                timezone.localtime(transfer.transfer_date_time).strftime("%Y-%m-%d %H:%M"),
                transfer.purpose,
                "Yes" if transfer.received_confirmation else "No",
            ],
        }


class SiteVisitListView(BaseTableListView):
    model = SiteVisit
    title = "Site Visits"
    headers = ["Project", "Engineer", "Scheduled", "Actual", "Status", "Follow-up"]

    def get_queryset(self):
        qs = SiteVisit.objects.filter(is_deleted=False).select_related("project", "assigned_engineer")
        if not self.request.user.is_staff:
            qs = qs.filter(project__in=project_queryset_for_user(self.request.user))
        return qs

    def row_for_object(self, visit):
        detail_url = reverse("project-detail", kwargs={"pk": visit.project_id})
        return {
            "detail_url": detail_url,
            "cells": [
                format_html('<a href="{}">{}</a>', detail_url, visit.project.project_number),
                visit.assigned_engineer.display_name if visit.assigned_engineer else "-",
                visit.scheduled_date.isoformat() if visit.scheduled_date else "-",
                visit.actual_visit_date.isoformat() if visit.actual_visit_date else "-",
                visit.visit_status,
                "Yes" if visit.follow_up_required else "No",
            ],
        }


class GovernmentRecordListView(BaseTableListView):
    model = GovernmentRecord
    title = "Government Online Records"
    headers = ["Project", "Municipality", "App No.", "Submission Type", "Status", "Last Checked"]

    def get_queryset(self):
        qs = GovernmentRecord.objects.filter(is_deleted=False).select_related("project")
        if not self.request.user.is_staff:
            qs = qs.filter(project__in=project_queryset_for_user(self.request.user))
        return qs

    def row_for_object(self, record):
        detail_url = reverse("project-detail", kwargs={"pk": record.project_id})
        return {
            "detail_url": detail_url,
            "cells": [
                format_html('<a href="{}">{}</a>', detail_url, record.project.project_number),
                record.municipality or "-",
                record.government_application_number or "-",
                record.submission_type,
                record.current_online_status,
                record.last_checked_date.isoformat() if record.last_checked_date else "-",
            ],
        }


class MunicipalityActivityListView(BaseTableListView):
    model = MunicipalityActivity
    title = "Municipality Tracking"
    headers = ["Project", "Municipality", "Type", "Resolved", "Recorded At"]

    def get_queryset(self):
        qs = MunicipalityActivity.objects.filter(is_deleted=False).select_related("project")
        if not self.request.user.is_staff:
            qs = qs.filter(project__in=project_queryset_for_user(self.request.user))
        return qs

    def row_for_object(self, activity):
        detail_url = reverse("project-detail", kwargs={"pk": activity.project_id})
        return {
            "detail_url": detail_url,
            "cells": [
                format_html('<a href="{}">{}</a>', detail_url, activity.project.project_number),
                activity.municipality or "-",
                activity.activity_type,
                "Yes" if activity.is_resolved else "No",
                timezone.localtime(activity.recorded_at).strftime("%Y-%m-%d %H:%M"),
            ],
        }


class PaymentListView(BaseTableListView):
    model = Payment
    title = "Payments"
    headers = ["Project", "Date", "Method", "Received", "Balance", "Receipt"]

    def get_queryset(self):
        qs = Payment.objects.filter(is_deleted=False).select_related("project")
        if not self.request.user.is_staff:
            qs = qs.filter(project__in=project_queryset_for_user(self.request.user))
        return qs

    def row_for_object(self, payment):
        detail_url = reverse("project-detail", kwargs={"pk": payment.project_id})
        return {
            "detail_url": detail_url,
            "cells": [
                format_html('<a href="{}">{}</a>', detail_url, payment.project.project_number),
                payment.payment_date.isoformat() if payment.payment_date else "-",
                payment.payment_method,
                f"{payment.amount_received:.2f}",
                f"{payment.remaining_balance:.2f}",
                payment.receipt_number or "-",
            ],
        }


class ProjectDetailView(ProjectAccessMixin, DetailView):
    model = Project
    template_name = "projects/project_detail.html"

    def get_queryset(self):
        return Project.objects.select_related(
            "client",
            "service_type",
            "current_responsible_employee",
            "current_stage_template",
            "current_stage_record",
            "created_by",
            "updated_by",
        ).prefetch_related(
            "members",
            "documents__uploaded_by",
            "checklist_items__template",
            "checklist_items__uploaded_document",
            "tasks__assigned_employee",
            "stage_histories__assigned_employee",
            "site_visits__assigned_engineer",
            "government_records",
            "municipality_activities",
            "file_transfers",
            "payments",
            "comments__commenter",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        context["missing_documents"] = required_documents_missing(project)
        context["stage_form"] = ProjectStageAdvanceForm(project=project)
        context["document_count"] = project.documents.filter(is_deleted=False).count()
        context["task_count"] = project.tasks.filter(is_deleted=False).count()
        context["recent_documents"] = project.documents.filter(is_deleted=False).select_related("uploaded_by", "category")[:8]
        context["checklist_items"] = project.checklist_items.filter(is_deleted=False).select_related("template", "category", "verified_by", "uploaded_document")
        context["tasks"] = project.tasks.filter(is_deleted=False).select_related("assigned_employee", "related_stage")
        context["stage_histories"] = project.stage_histories.select_related("stage_template", "assigned_employee").order_by("stage_order", "started_at")
        context["site_visits"] = project.site_visits.filter(is_deleted=False).select_related("assigned_engineer")
        context["government_records"] = project.government_records.filter(is_deleted=False)
        context["municipality_activities"] = project.municipality_activities.filter(is_deleted=False)
        context["file_transfers"] = project.file_transfers.filter(is_deleted=False)
        context["payments"] = project.payments.filter(is_deleted=False)
        context["comments"] = project.comments.filter(is_deleted=False).select_related("commenter")
        context["audit_logs"] = project.audit_logs.select_related("actor")
        context["qr_url"] = self.request.build_absolute_uri(reverse("project-public", kwargs={"token": project.public_token}))
        context["qr_image_url"] = reverse("project-qr-image", kwargs={"pk": project.pk})
        context["progress_percent"] = project.progress_percent
        return context


class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    page_title = "New Project"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        return context

    def form_valid(self, form):
        from django.db import transaction

        with transaction.atomic():
            response = super().form_valid(form)
            self.object.created_by = self.request.user
            self.object.updated_by = self.request.user
            self.object.save()
            form.save_m2m()
            self.object.members.add(self.request.user)
            create_project_initial_state(self.object, actor=self.request.user)
            log_audit(self.request.user, "project.created", project=self.object, obj=self.object, summary="Project created")
            messages.success(self.request, f"Project {self.object.project_number} has been created.")
            return response

    def get_success_url(self):
        return reverse("project-detail", kwargs={"pk": self.object.pk})


class ClientCreateView(LoginRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = "projects/project_form.html"
    success_url = reverse_lazy("clients")
    page_title = "New Client"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Client saved successfully.")
        return super().form_valid(form)


class ProjectScopedFormView(LoginRequiredMixin, FormView):
    template_name = "projects/project_action_form.html"
    project = None
    page_title = None

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(Project.objects.select_related("client", "service_type"), pk=kwargs["pk"], is_deleted=False)
        if not user_can_access_project(request.user, self.project):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        context["project_action_title"] = self.page_title or self.model._meta.verbose_name.title()
        return context

    def get_success_url(self):
        return reverse("project-detail", kwargs={"pk": self.project.pk})


class ProjectDocumentUploadView(ProjectScopedFormView):
    form_class = ProjectDocumentUploadForm
    model = ProjectDocument
    page_title = "Upload Document"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["category"].queryset = self.project.service_type.document_categories.filter(is_active=True).order_by("order", "name")
        form.fields["checklist_item"].queryset = self.project.checklist_items.filter(is_deleted=False).order_by("template__order")
        form.fields["checked_by"].queryset = User.objects.filter(is_active=True, is_staff=True).order_by("first_name", "last_name")
        return form

    def form_valid(self, form):
        document = create_document_revision(
            project=self.project,
            category=form.cleaned_data["category"],
            uploaded_file=form.cleaned_data["file"],
            actor=self.request.user,
            display_name=form.cleaned_data["display_name"],
            checklist_item=form.cleaned_data["checklist_item"],
            approval_status=form.cleaned_data["approval_status"],
            confidentiality_level=form.cleaned_data["confidentiality_level"],
            remarks=form.cleaned_data["remarks"],
            checked_by=form.cleaned_data["checked_by"] or None,
        )
        messages.success(self.request, f"Document {document.display_name} uploaded as revision {document.revision_number}.")
        return redirect(self.get_success_url())


class ProjectStageAdvanceView(ProjectScopedFormView):
    form_class = ProjectStageAdvanceForm
    model = Project
    page_title = "Advance Workflow Stage"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        return kwargs

    def form_valid(self, form):
        if form.cleaned_data.get("override_missing_documents") and not user_has_role(self.request.user, "System Administrator", "Director/Management", "Project Manager"):
            form.add_error(None, "Only management users can approve document exceptions.")
            return self.form_invalid(form)
        try:
            stage = advance_project_stage(
                project=self.project,
                actor=self.request.user,
                target_stage=form.cleaned_data.get("target_stage"),
                assigned_employee=form.cleaned_data.get("assigned_employee"),
                due_date=form.cleaned_data.get("due_date"),
                comments=form.cleaned_data.get("comments", ""),
                override_missing_documents=form.cleaned_data.get("override_missing_documents", False),
                override_reason=form.cleaned_data.get("override_reason", ""),
            )
        except ValidationError as exc:
            form.add_error(None, exc.message)
            return self.form_invalid(form)
        messages.success(self.request, f"Project moved to {stage.stage_name}.")
        return redirect(self.get_success_url())


class ProjectScopedCreateView(ProjectScopedFormView):
    model = None

    def save_object(self, form):
        raise NotImplementedError

    def form_valid(self, form):
        self.object = self.save_object(form)
        messages.success(self.request, f"{self.model._meta.verbose_name.title()} saved successfully.")
        return redirect(self.get_success_url())


class TaskCreateView(ProjectScopedCreateView):
    model = Task
    form_class = TaskForm
    page_title = "Add Task"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["related_stage"].queryset = self.project.stage_histories.order_by("-started_at")
        form.fields["assigned_employee"].queryset = User.objects.filter(is_active=True, is_staff=True).order_by("first_name", "last_name")
        return form

    def save_object(self, form):
        task = form.save(commit=False)
        task.project = self.project
        task.assigned_by = self.request.user
        task.save()
        form.save_m2m()
        log_audit(self.request.user, "task.created", project=self.project, obj=task, summary=task.title)
        if task.assigned_employee:
            notify_user(
                task.assigned_employee,
                f"Task assigned: {task.title}",
                f"A new task was created for {self.project.project_number}.",
                project=self.project,
                level="success",
                link=reverse("project-detail", kwargs={"pk": self.project.pk}),
            )
        return task


class PhysicalFileTransferCreateView(ProjectScopedCreateView):
    model = PhysicalFileTransfer
    form_class = PhysicalFileTransferForm
    page_title = "Record File Handover"

    def save_object(self, form):
        transfer = form.save(commit=False)
        transfer.project = self.project
        transfer.recorded_by = self.request.user
        transfer.save()
        form.save_m2m()
        log_audit(self.request.user, "project.file_transferred", project=self.project, obj=transfer, summary=transfer.purpose)
        return transfer


class SiteVisitCreateView(ProjectScopedCreateView):
    model = SiteVisit
    form_class = SiteVisitForm
    page_title = "Add Site Visit"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["assigned_engineer"].queryset = User.objects.filter(is_active=True, is_staff=True).order_by("first_name", "last_name")
        form.fields["recorded_by"].widget = forms.HiddenInput()
        form.fields["recorded_by"].initial = self.request.user.pk
        return form

    def save_object(self, form):
        visit = form.save(commit=False)
        visit.project = self.project
        visit.recorded_by = self.request.user
        visit.save()
        log_audit(self.request.user, "site_visit.created", project=self.project, obj=visit, summary="Site visit recorded")
        return visit


class GovernmentRecordCreateView(ProjectScopedCreateView):
    model = GovernmentRecord
    form_class = GovernmentRecordForm
    page_title = "Government Record"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for field_name in ("submitted_by", "recorded_by"):
            form.fields[field_name].widget = forms.HiddenInput()
            form.fields[field_name].initial = self.request.user.pk
        return form

    def save_object(self, form):
        record = form.save(commit=False)
        record.project = self.project
        record.submitted_by = self.request.user
        record.recorded_by = self.request.user
        record.save()
        log_audit(self.request.user, "government_record.created", project=self.project, obj=record, summary=record.current_online_status)
        return record


class MunicipalityActivityCreateView(ProjectScopedCreateView):
    model = MunicipalityActivity
    form_class = MunicipalityActivityForm
    page_title = "Municipality Note"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["recorded_by"].widget = forms.HiddenInput()
        form.fields["recorded_by"].initial = self.request.user.pk
        return form

    def save_object(self, form):
        activity = form.save(commit=False)
        activity.project = self.project
        activity.recorded_by = self.request.user
        activity.save()
        log_audit(self.request.user, "municipality_activity.created", project=self.project, obj=activity, summary=activity.activity_type)
        return activity


class PaymentCreateView(ProjectScopedCreateView):
    model = Payment
    form_class = PaymentForm
    page_title = "Add Payment"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["received_by"].widget = forms.HiddenInput()
        form.fields["received_by"].initial = self.request.user.pk
        return form

    def save_object(self, form):
        payment = form.save(commit=False)
        payment.project = self.project
        payment.received_by = self.request.user
        payment.save()
        log_audit(self.request.user, "payment.created", project=self.project, obj=payment, summary=f"Payment {payment.amount_received}")
        return payment


class ProjectCommentCreateView(ProjectScopedCreateView):
    model = ProjectComment
    form_class = ProjectCommentForm
    page_title = "Add Comment"

    def save_object(self, form):
        comment = form.save(commit=False)
        comment.project = self.project
        comment.commenter = self.request.user
        comment.save()
        log_audit(self.request.user, "project.comment.created", project=self.project, obj=comment, summary=comment.visibility)
        return comment


class DocumentDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(ProjectDocument.objects.select_related("project"), pk=pk, is_deleted=False)
        if not user_can_access_project(request.user, document.project):
            raise Http404
        if not document.file:
            raise Http404
        log_audit(request.user, "document.downloaded", project=document.project, obj=document, summary=document.display_name)
        response = FileResponse(document.file.open("rb"), as_attachment=True, filename=document.original_filename)
        return response


class ProjectPublicView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "projects/project_public.html"
    slug_field = "public_token"
    slug_url_kwarg = "token"

    def get_queryset(self):
        return Project.objects.select_related("client", "service_type")

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        if not user_can_access_project(self.request.user, obj):
            raise Http404
        return obj


class ProjectQRCodeView(ProjectAccessMixin, View):
    def get(self, request, *args, **kwargs):
        data = request.build_absolute_uri(reverse("project-public", kwargs={"token": self.project.public_token}))
        qr = qrcode.QRCode(version=3, box_size=8, border=3)
        qr.add_data(data)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#0f5c7a", back_color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return HttpResponse(buffer.getvalue(), content_type="image/png")
