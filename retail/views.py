import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from accounts.models import OrganizationRole
from core.models import AuditLog
from .access import RetailAccess
from .forms import (AdjustmentForm, CategoryForm, CustomerForm, DateRangeForm, DocumentForm, LineFormSet,
                    LocationForm, PaymentForm, ProductForm, ReturnForm, RoleForm, SupplierForm)
from .models import Category, Customer, Location, Product, RetailDocument, StockBalance, StockMovement, Supplier
from .services import adjust_stock, audit, cancel_draft, lock_workspace, post_document, refund_sale, save_draft


RESOURCES = {
    "products": (Product, ProductForm, "Products", "product"),
    "categories": (Category, CategoryForm, "Categories", "category"),
    "locations": (Location, LocationForm, "Store locations", "location"),
    "suppliers": (Supplier, SupplierForm, "Suppliers", "supplier"),
    "customers": (Customer, CustomerForm, "Customers", "customer"),
}


class AccessView(View):
    permission = None
    api = False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required."}, status=401) if self.api else redirect(f"{reverse('login')}?next={request.path}")
        if request.user.must_change_password:
            return JsonResponse({"error": "Change your temporary password first."}, status=403) if self.api else redirect("password-change")
        try:
            self.access = RetailAccess(request)
            if self.permission:
                self.access.require(self.permission)
            return super().dispatch(request, *args, **kwargs)
        except (PermissionDenied, Http404) as exc:
            if not self.api:
                raise
            return JsonResponse({"error": str(exc) or "Not found."}, status=403 if isinstance(exc, PermissionDenied) else 404)

    def context(self, **kwargs):
        return {"retail_organization": self.access.organization, "retail_navigation": self.access.navigation(),
                "retail_permissions": self.access.permissions, **kwargs}


def document_totals(records):
    return records.aggregate(total=Sum("total"), tax=Sum("tax_total"))


def dashboard_data(access):
    today = timezone.localdate()
    metrics, sales, low_stock = [], [], []
    if access.allows("rt-sales.view"):
        posted = access.documents("sale").filter(status="posted", posted_at__date=today)
        returned = access.documents("return").filter(status="posted", posted_at__date=today)
        gross = document_totals(posted)["total"] or Decimal("0")
        refunds = document_totals(returned)["total"] or Decimal("0")
        metrics.extend([{"label": "Sales today", "value": gross, "money": True},
                        {"label": "Net receipts today", "value": gross - refunds, "money": True},
                        {"label": "Sales receipts today", "value": posted.count(), "money": False}])
        sales = list(access.documents("sale").values("id", "number", "status", "total", "created_at")[:6])
    if access.allows("rt-products.view"):
        metrics.append({"label": "Active products", "value": access.scope(Product).filter(is_active=True).count(), "money": False})
    if access.allows("rt-inventory.view"):
        balances = access.scope(StockBalance).filter(product__is_active=True, location__is_active=True, quantity__lte=F("product__reorder_level"))
        metrics.append({"label": "Low-stock items", "value": balances.count(), "money": False})
        low_stock = list(balances.values("product__sku", "product__name", "location__name", "quantity", "product__reorder_level")[:8])
    return {"metrics": metrics, "recent_sales": sales, "low_stock": low_stock}


class DashboardView(AccessView):
    permission = "rt-dashboard.view"

    def get(self, request):
        data = dashboard_data(self.access)
        if self.api:
            return JsonResponse(data)
        return render(request, "retail/dashboard.html", self.context(page_title="Retail overview", **data))


class MasterView(AccessView):
    resource = None
    mode = "list"

    @property
    def module(self):
        return "products" if self.resource == "categories" else self.resource

    def get(self, request, pk=None):
        self.access.require(f"rt-{self.module}.view")
        model, form_class, label, singular = RESOURCES[self.resource]
        records = self.access.scope(model)
        if self.mode != "list":
            self.access.require(f"rt-{self.module}.{'change' if pk else 'create'}")
            obj = get_object_or_404(records, pk=pk) if pk else None
            return self.form_page(form_class(instance=obj, access=self.access), singular, pk)
        query = request.GET.get("q", "").strip()[:200]
        if query:
            filters = Q(name__icontains=query)
            if self.resource == "products":
                filters |= Q(sku__icontains=query) | Q(barcode__icontains=query)
            records = records.filter(filters)
        if self.api:
            fields = ["id", "sku", "barcode", "name", "unit", "selling_price", "tax_rate", "is_active"]
            if self.access.allows("rt-products.cost"):
                fields.append("cost_price")
            page = Paginator(records, 30).get_page(request.GET.get("page"))
            return JsonResponse({"count": page.paginator.count, "page": page.number, "results": list(page.object_list.values(*fields))})
        return render(request, "retail/master_list.html", self.context(page_title=label, resource=self.resource, singular=singular,
                      page_obj=Paginator(records, 30).get_page(request.GET.get("page")),
                      can_create=self.access.allows(f"rt-{self.module}.create"), can_change=self.access.allows(f"rt-{self.module}.change")))

    def form_page(self, form, singular, pk=None, status=200):
        return render(self.request, "retail/form.html", self.context(form=form, page_title=f"{'Edit' if pk else 'New'} {singular}",
                      cancel_url=reverse(f"rt-{self.resource}")), status=status)

    def post(self, request, pk=None):
        if self.mode == "list" or self.api:
            return self.http_method_not_allowed(request)
        self.access.require(f"rt-{self.module}.view")
        self.access.require(f"rt-{self.module}.{'change' if pk else 'create'}")
        model, form_class, label, singular = RESOURCES[self.resource]
        obj = get_object_or_404(self.access.scope(model), pk=pk) if pk else None
        form = form_class(request.POST, instance=obj, access=self.access)
        if form.is_valid():
            try:
                with transaction.atomic():
                    lock_workspace(self.access)
                    obj = form.save()
                    if model is Product:
                        for location in self.access.scope(Location).filter(is_active=True):
                            StockBalance.objects.get_or_create(organization=self.access.organization, location=location, product=obj)
                    elif model is Location:
                        for product in self.access.scope(Product).filter(is_active=True):
                            StockBalance.objects.get_or_create(organization=self.access.organization, location=obj, product=product)
                    audit(self.access, f"{singular}.{'changed' if pk else 'created'}", obj)
            except (ValidationError, IntegrityError):
                form.add_error(None, "The record could not be saved. Check for duplicate codes or changed related records.")
            else:
                messages.success(request, f"{singular.capitalize()} saved.")
                return redirect(f"rt-{self.resource}")
        return self.form_page(form, singular, pk, status=400)


class InventoryView(AccessView):
    permission = "rt-inventory.view"

    def get(self, request):
        records = self.access.scope(StockBalance).select_related("product", "location")
        query = request.GET.get("q", "").strip()[:200]
        if query:
            records = records.filter(Q(product__name__icontains=query) | Q(product__sku__icontains=query) | Q(product__barcode__icontains=query))
        location = request.GET.get("location")
        if location:
            location = get_object_or_404(self.access.scope(Location), pk=location) if location.isdigit() else None
            records = records.filter(location=location)
        if request.GET.get("low") == "1":
            records = records.filter(quantity__lte=F("product__reorder_level"))
        page = Paginator(records, 30).get_page(request.GET.get("page"))
        if self.api:
            return JsonResponse({"count": page.paginator.count, "page": page.number,
                                 "results": list(page.object_list.values("product_id", "product__sku", "product__name", "location_id", "location__name", "quantity"))})
        return render(request, "retail/inventory.html", self.context(page_title="Inventory", page_obj=page,
                      locations=self.access.scope(Location), movements=self.access.scope(StockMovement).select_related("product", "location", "actor")[:12]))


class AdjustmentView(AccessView):
    permission = "rt-inventory.adjust"

    def get(self, request):
        return self.page(AdjustmentForm(access=self.access))

    def page(self, form, status=200):
        return render(self.request, "retail/form.html", self.context(page_title="Adjust stock", form=form, cancel_url=reverse("rt-inventory")), status=status)

    def post(self, request):
        form = AdjustmentForm(request.POST, access=self.access)
        if form.is_valid():
            try:
                adjust_stock(self.access, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                messages.success(request, "Stock adjustment recorded.")
                return redirect("rt-inventory")
        return self.page(form, 400)


class DocumentsView(AccessView):
    kind = "sale"
    mode = "list"

    @property
    def module(self):
        return "purchases" if self.kind == "purchase" else "sales"

    def get(self, request, pk=None):
        records = self.access.documents(self.kind).select_related("location", "customer", "supplier", "created_by")
        if self.mode in {"create", "edit"}:
            self.access.require(f"rt-{self.module}.{'change' if pk else 'create'}")
            self.access.require_modules("rt-products", "rt-inventory", "rt-locations")
            document = get_object_or_404(records, pk=pk, status="draft") if pk else None
            form = DocumentForm(instance=document, access=self.access, kind=self.kind)
            initial = list(document.lines.values("product", "quantity", "unit_price", "discount")) if document else []
            lines = LineFormSet(initial=initial, prefix="lines", form_kwargs={"access": self.access, "kind": self.kind})
            return self.editor(form, lines, document)
        if pk:
            document = get_object_or_404(records, pk=pk)
            if self.api:
                return JsonResponse({"id": document.pk, "number": document.number, "status": document.status,
                                     "total": document.total, "currency": document.currency_code,
                                     "lines": list(document.lines.values("sku", "product_name", "quantity", "unit_price", "discount", "tax", "total"))})
            return self.detail(document)
        query = request.GET.get("q", "").strip()[:100]
        if query:
            records = records.filter(number__icontains=query)
        if request.GET.get("status"):
            records = records.filter(status=request.GET["status"])
        page = Paginator(records, 30).get_page(request.GET.get("page"))
        if self.api:
            return JsonResponse({"count": page.paginator.count, "page": page.number,
                                 "results": list(page.object_list.values("id", "number", "status", "total", "currency_code", "created_at"))})
        return render(request, "retail/documents.html", self.context(page_title="Purchases" if self.kind == "purchase" else "Sales",
                      module=self.module, kind=self.kind, page_obj=page, can_create=self.access.allows(f"rt-{self.module}.create")))

    def editor(self, form, lines, document=None, status=200):
        return render(self.request, "retail/document_form.html", self.context(page_title=f"{'Edit' if document else 'New'} {'purchase receipt' if self.kind == 'purchase' else 'sale'}",
                      form=form, line_formset=lines, document=document, module=self.module), status=status)

    def detail(self, document, payment_form=None, return_form=None, error="", status=200):
        returned = self.access.scope(RetailDocument).filter(original_sale=document).first()
        return render(self.request, "retail/document_detail.html", self.context(page_title=document.number, document=document,
                      lines=document.lines.all(), module=self.module, returned=returned, error=error,
                      can_change=self.access.allows(f"rt-{self.module}.change"), can_post=self.access.allows(f"rt-{self.module}.post"),
                      can_refund=self.access.allows("rt-sales.refund"),
                      payment_form=payment_form or PaymentForm(initial={"payment_received": document.total}), return_form=return_form or ReturnForm()), status=status)

    def post(self, request, pk=None):
        if self.mode not in {"create", "edit"} or self.api:
            return self.http_method_not_allowed(request)
        self.access.require(f"rt-{self.module}.{'change' if pk else 'create'}")
        document = get_object_or_404(self.access.documents(self.kind), pk=pk, status="draft") if pk else None
        form = DocumentForm(request.POST, instance=document, access=self.access, kind=self.kind)
        lines = LineFormSet(request.POST, prefix="lines", form_kwargs={"access": self.access, "kind": self.kind})
        valid = form.is_valid()
        if lines.is_valid() and valid:
            try:
                document = save_draft(self.access, form, lines.cleaned_data, kind=self.kind, document_id=pk)
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                messages.success(request, "Draft saved. Review the totals before posting.")
                return redirect(f"rt-{self.module}-detail", pk=document.pk)
        return self.editor(form, lines, document, 400)


class DocumentActionView(DocumentsView):
    action = None

    def get(self, request, pk=None):
        return self.http_method_not_allowed(request)

    def post(self, request, pk):
        document = get_object_or_404(self.access.documents(self.kind), pk=pk)
        payment_form, return_form = None, None
        try:
            if self.action == "post":
                self.access.require(f"rt-{self.module}.post")
                data = {}
                if self.kind == "sale":
                    payment_form = PaymentForm(request.POST)
                    if not payment_form.is_valid():
                        return self.detail(document, payment_form=payment_form, status=400)
                    data = payment_form.cleaned_data
                post_document(self.access, pk, kind=self.kind, **data)
                messages.success(request, "Receipt posted and stock updated.")
            elif self.action == "cancel":
                cancel_draft(self.access, pk, kind=self.kind)
                messages.success(request, "Draft cancelled.")
            elif self.action == "refund":
                self.access.require("rt-sales.refund")
                return_form = ReturnForm(request.POST)
                if not return_form.is_valid():
                    return self.detail(document, return_form=return_form, status=400)
                refund_sale(self.access, pk, **return_form.cleaned_data)
                messages.success(request, "Full sales return and refund recorded.")
        except ValidationError as exc:
            return self.detail(document, payment_form=payment_form, return_form=return_form, error=" ".join(exc.messages), status=400)
        return redirect(f"rt-{self.module}-detail", pk=pk)


class ReportsView(AccessView):
    permission = "rt-reports.view"
    export = False

    def get(self, request):
        self.access.require("rt-sales.view")
        form = DateRangeForm(request.GET)
        sales = self.access.documents("sale").filter(status="posted")
        returns = self.access.documents("return").filter(status="posted")
        if form.is_valid():
            start = form.cleaned_data.get("start") or timezone.localdate().replace(day=1)
            end = form.cleaned_data.get("end") or timezone.localdate()
            if start > end:
                form.add_error(None, "The end date must be on or after the start date.")
            else:
                sales = sales.filter(posted_at__date__range=(start, end))
                returns = returns.filter(posted_at__date__range=(start, end))
        if form.errors:
            sales, returns = sales.none(), returns.none()
        gross = document_totals(sales)["total"] or Decimal("0")
        refunded = document_totals(returns)["total"] or Decimal("0")
        if self.export:
            self.access.require("rt-reports.export")
            if form.errors:
                return HttpResponse("Invalid report dates.", status=400)
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="retail-sales.csv"'
            writer = csv.writer(response)
            writer.writerow(["Receipt", "Type", "Date", "Currency", "Subtotal", "Tax", "Total"])
            for document in sales.order_by().union(returns.order_by()).order_by("posted_at"):
                sign = -1 if document.kind == "return" else 1
                row = [document.number, document.get_kind_display(), document.posted_at.isoformat(), document.currency_code,
                       document.subtotal * sign, document.tax_total * sign, document.total * sign]
                writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value for value in row])
            audit(self.access, "report.downloaded", summary=f"Sales CSV: {start} to {end}.")
            return response
        return render(request, "retail/reports.html", self.context(page_title="Sales reports", form=form, gross=gross, refunded=refunded,
                      net=gross - refunded, receipt_count=sales.count(), page_obj=Paginator(sales, 30).get_page(request.GET.get("page"))))


class RolesView(AccessView):
    permission = "rt-roles.view"

    def page(self, form=None, status=200):
        return render(self.request, "retail/roles.html", self.context(page_title="Roles and permissions", form=form or RoleForm(access=self.access),
                      roles=OrganizationRole.objects.filter(organization=self.access.organization, is_active=True).prefetch_related("permissions"),
                      memberships=self.access.organization.memberships.filter(is_active=True).select_related("user", "organization_role")), status=status)

    def get(self, request):
        return self.page()

    def post(self, request):
        self.access.require("rt-roles.manage")
        form = RoleForm(request.POST, access=self.access)
        if form.is_valid():
            with transaction.atomic():
                member = form.cleaned_data["membership"]
                previous = member.organization_role_id
                member.organization_role = form.cleaned_data["organization_role"]
                member.save(update_fields=["organization_role"])
                audit(self.access, "role.assigned", member, f"Role assigned: {member.organization_role.name}",
                      {"previous_role_id": previous, "role_id": member.organization_role_id, "member_user_id": member.user_id})
            messages.success(request, "Retail role assigned.")
            return redirect("rt-roles")
        return self.page(form, 400)


class AuditView(AccessView):
    permission = "rt-audit.view"

    def get(self, request):
        entries = AuditLog.objects.filter(action__startswith="retail.", metadata__organization_id=self.access.organization.pk).select_related("actor")
        # The audit permission is reserved for roles allowed to inspect the whole practice.
        return render(request, "retail/audit.html", self.context(page_title="Audit activity", page_obj=Paginator(entries, 30).get_page(request.GET.get("page"))))
