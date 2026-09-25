import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.forms.models import model_to_dict
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from accounts.models import OrganizationRole
from .forms import ClientForm, EngagementForm, RoleAssignmentForm, ServiceForm, SettingsForm
from .models import ProfessionalSettings
from .services import access_for, dashboard_data, record_activity


RESOURCES = {
    "clients": {"form": ClientForm, "label": "Clients", "singular": "client", "search": ["name", "email", "contact_person"]},
    "services": {"form": ServiceForm, "label": "Services", "singular": "service", "search": ["name", "code", "description"]},
    "engagements": {"form": EngagementForm, "label": "Engagements", "singular": "engagement", "search": ["number", "title"]},
}


class AccessView(View):
    api = False
    permission = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            if self.api:
                return JsonResponse({"error": "Authentication required."}, status=401)
            return redirect(f"{reverse('login')}?next={request.path}")
        if request.user.must_change_password:
            if self.api:
                return JsonResponse({"error": "Change your temporary password before accessing this workspace."}, status=403)
            return redirect("password-change")
        try:
            self.access = access_for(request)
            if self.permission:
                self.access.require(self.permission)
            return super().dispatch(request, *args, **kwargs)
        except (PermissionDenied, Http404) as exc:
            if not self.api:
                raise
            return JsonResponse({"error": str(exc) or "Not found."}, status=403 if isinstance(exc, PermissionDenied) else 404)

    def context(self, **kwargs):
        return {
            "ps_organization": self.access.organization,
            "ps_navigation": self.access.navigation(),
            "ps_permissions": self.access.permissions,
            **kwargs,
        }


class DashboardView(AccessView):
    permission = "ps-dashboard.view"

    def get(self, request):
        data = dashboard_data(self.access)
        if self.api:
            return JsonResponse(data)
        return render(request, "professional_services/dashboard.html", self.context(page_title="Professional services", **data))


def serialize_record(obj, form_class):
    result = {"id": obj.pk}
    for name in form_class.Meta.fields:
        field = obj._meta.get_field(name)
        if field.many_to_many:
            result[name] = list(getattr(obj, name).values_list("pk", flat=True))
        else:
            result[name] = getattr(obj, field.attname)
    result["status_label"] = obj.get_status_display()
    result["updated_at"] = obj.updated_at
    return result


class ResourceView(AccessView):
    resource = None
    mode = "list"

    @property
    def config(self):
        return RESOURCES[self.resource]

    def records(self):
        self.access.require(f"ps-{self.resource}.view")
        records = getattr(self.access, self.resource)()
        if self.resource == "engagements":
            records = records.select_related("client", "service", "account_manager", "engagement_manager")
        elif self.resource == "clients":
            records = records.select_related("account_manager")
        query = self.request.GET.get("q", "").strip()[:200]
        if query and self.mode == "list":
            from django.db.models import Q
            filters = Q()
            for field in self.config["search"]:
                filters |= Q(**{f"{field}__icontains": query})
            records = records.filter(filters)
        status = self.request.GET.get("status", "")
        if status and self.mode == "list":
            records = records.filter(status=status)
        return records

    def get(self, request, pk=None):
        records = self.records()
        if self.mode in {"create", "edit"}:
            self.access.require(f"ps-{self.resource}.{'create' if self.mode == 'create' else 'change'}")
            obj = get_object_or_404(records, pk=pk) if pk else None
            initial = {}
            if not obj:
                if self.resource == "clients":
                    initial["account_manager"] = self.access.user
                elif self.resource == "engagements":
                    initial.update(account_manager=self.access.user, engagement_manager=self.access.user)
            form = self.config["form"](instance=obj, access=self.access, initial=initial)
            return self.form_response(form, obj)
        if pk is not None:
            obj = get_object_or_404(records, pk=pk)
            if self.api:
                return JsonResponse(serialize_record(obj, self.config["form"]))
            form = self.config["form"](instance=obj, access=self.access)
            fields = []
            for name, field in form.fields.items():
                model_field = obj._meta.get_field(name)
                if model_field.many_to_many:
                    value = ", ".join(str(item) for item in getattr(obj, name).all())
                else:
                    value = getattr(obj, f"get_{name}_display", lambda: getattr(obj, name))()
                fields.append((field.label, value))
            return render(request, "professional_services/detail.html", self.context(
                page_title=str(obj), record=obj, fields=fields, resource=self.resource, label=self.config["label"],
                can_change=self.access.allows(f"ps-{self.resource}.change"),
            ))
        page = Paginator(records, 20).get_page(request.GET.get("page"))
        if self.api:
            return JsonResponse({"count": page.paginator.count, "page": page.number, "pages": page.paginator.num_pages,
                                 "results": [serialize_record(obj, self.config["form"]) for obj in page]})
        return render(request, "professional_services/list.html", self.context(
            page_title=self.config["label"], resource=self.resource, singular=self.config["singular"],
            page_obj=page, status_choices=self.config["form"]._meta.model.Status.choices,
            can_create=self.access.allows(f"ps-{self.resource}.create"),
        ))

    def form_response(self, form, obj=None, status=200):
        return render(self.request, "professional_services/form.html", self.context(
            page_title=f"{'Edit' if obj else 'New'} {self.config['singular']}", form=form, record=obj,
            resource=self.resource, cancel_url=reverse(f"ps-{self.resource}"),
        ), status=status)

    def post(self, request, pk=None):
        if self.api and pk is not None:
            return self.http_method_not_allowed(request)
        if not self.api and self.mode not in {"create", "edit"}:
            return self.http_method_not_allowed(request)
        return self.write(request, pk)

    def patch(self, request, pk=None):
        if not self.api or pk is None:
            return self.http_method_not_allowed(request)
        return self.write(request, pk)

    def write(self, request, pk):
        records = self.records()
        action = "change" if pk is not None else "create"
        self.access.require(f"ps-{self.resource}.{action}")
        obj = get_object_or_404(records, pk=pk) if pk is not None else None
        form_class = self.config["form"]
        if self.api:
            if request.content_type != "application/json":
                return JsonResponse({"error": "Use application/json."}, status=415)
            try:
                supplied = json.loads(request.body)
            except (ValueError, UnicodeDecodeError):
                return JsonResponse({"error": "Invalid JSON."}, status=400)
            if not isinstance(supplied, dict):
                return JsonResponse({"error": "Expected a JSON object."}, status=400)
            if set(supplied) - set(form_class.Meta.fields):
                return JsonResponse({"error": "Unknown or read-only fields supplied."}, status=400)
            # PATCH preserves omitted fields, including many-to-many selections.
            data = model_to_dict(obj, fields=form_class.Meta.fields) if obj else {}
            for name, value in list(data.items()):
                if isinstance(value, list):
                    data[name] = [item.pk if hasattr(item, "pk") else item for item in value]
            if not obj:
                instance = form_class._meta.model()
                data["status"] = instance.status
                if self.resource == "services":
                    data["default_billing_method"] = instance.default_billing_method
                if self.resource == "clients":
                    data["account_manager"] = self.access.user.pk
                if self.resource == "engagements":
                    data.update(number=instance.number, status=instance.status, progress=0,
                                engagement_manager=self.access.user.pk)
            data.update(supplied)
        else:
            data = request.POST
        form = form_class(data=data, instance=obj, access=self.access)
        if form.is_valid():
            try:
                with transaction.atomic():
                    saved = form.save()
                    record_activity(self.access, f"{self.config['singular']}.{action}", saved, form.changed_data)
            except (ValidationError, IntegrityError):
                form.add_error(None, "The record could not be saved. Check for duplicate identifiers or changed organization members.")
            else:
                if self.api:
                    return JsonResponse(serialize_record(saved, form_class), status=200 if obj else 201)
                messages.success(request, f"{self.config['singular'].capitalize()} saved.")
                if not getattr(self.access, self.resource)().filter(pk=saved.pk).exists():
                    return redirect(f"ps-{self.resource}")
                return redirect(f"ps-{self.resource}-detail", pk=saved.pk)
        if self.api:
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        return self.form_response(form, obj, status=400)


class SettingsView(AccessView):
    permission = "ps-roles.settings"

    def get_form(self, data=None):
        instance = ProfessionalSettings.objects.filter(organization=self.access.organization).first()
        return SettingsForm(data, instance=instance, access=self.access)

    def get(self, request):
        return render(request, "professional_services/form.html", self.context(
            page_title="Billing defaults", form=self.get_form(), cancel_url=reverse("ps-dashboard"),
        ))

    def post(self, request):
        form = self.get_form(request.POST)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save()
                record_activity(self.access, "settings.change", obj, form.changed_data)
            messages.success(request, "Organization billing defaults saved.")
            return redirect("ps-settings")
        return render(request, "professional_services/form.html", self.context(
            page_title="Billing defaults", form=form, cancel_url=reverse("ps-dashboard"),
        ), status=400)


class RolesView(AccessView):
    permission = "ps-roles.view"

    def page(self, request, form=None, status=200):
        return render(request, "professional_services/roles.html", self.context(
            page_title="Roles and permissions",
            roles=OrganizationRole.objects.filter(organization=self.access.organization, is_active=True).prefetch_related("permissions"),
            memberships=self.access.organization.memberships.filter(is_active=True).select_related("user", "organization_role"),
            form=form or RoleAssignmentForm(access=self.access), can_manage=self.access.allows("ps-roles.manage"),
        ), status=status)

    def get(self, request):
        return self.page(request)

    def post(self, request):
        self.access.require("ps-roles.manage")
        form = RoleAssignmentForm(request.POST, access=self.access)
        if form.is_valid():
            with transaction.atomic():
                membership = form.cleaned_data["membership"]
                membership.organization_role = form.cleaned_data["organization_role"]
                membership.save(update_fields=["organization_role"])
                record_activity(self.access, "role.assign", membership, ["organization_role"])
            messages.success(request, "Workspace role assigned.")
            return redirect("ps-roles")
        return self.page(request, form, status=400)


class AuditView(AccessView):
    permission = "ps-audit.view"

    def get(self, request):
        page = Paginator(self.access.audit_entries(), 30).get_page(request.GET.get("page"))
        return render(request, "professional_services/audit.html", self.context(page_title="Audit activity", page_obj=page))
