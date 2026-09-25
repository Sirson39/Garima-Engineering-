from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import Company
from core.services import log_audit
from .models import Product, Location, RetailDocument, RetailLine, StockBalance, StockMovement


CENT = Decimal("0.01")


def rounded(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def audit(access, action, obj=None, summary="", metadata=None):
    return log_audit(access.user, f"retail.{action}", obj=obj, summary=summary or str(obj or action),
                     metadata={**(metadata or {}), "organization_id": access.organization.pk})


def lock_workspace(access):
    # A tenant lock also protects first-time balance creation and repeated submit.
    Company.objects.select_for_update().get(pk=access.organization.pk)


def move_stock(access, product, location, delta, reason, document=None):
    """Internal helper: callers must hold the workspace lock in an atomic block."""
    if product.organization_id != access.organization.pk or location.organization_id != access.organization.pk:
        raise ValidationError("Stock references must belong to this organization.")
    if not delta:
        raise ValidationError("Quantity must change.")
    balance, _ = StockBalance.objects.select_for_update().get_or_create(
        organization=access.organization, product=product, location=location,
    )
    new_quantity = balance.quantity + delta
    if new_quantity < 0:
        raise ValidationError(f"Insufficient stock for {product.sku} at {location.name}. Available: {balance.quantity}.")
    balance.quantity = new_quantity
    balance.save()
    return StockMovement.objects.create(organization=access.organization, product=product, location=location,
                                        quantity=delta, balance_after=new_quantity, reason=reason, actor=access.user, document=document)


@transaction.atomic
def adjust_stock(access, *, product, location, delta, reason):
    access.require("rt-inventory.adjust")
    access.require_modules("rt-products", "rt-locations")
    lock_workspace(access)
    product = get_object_or_404(access.scope(Product), pk=product.pk, is_active=True)
    location = get_object_or_404(access.scope(Location), pk=location.pk, is_active=True)
    if not reason.strip():
        raise ValidationError("A reason is required for stock adjustments.")
    movement = move_stock(access, product, location, delta, reason)
    audit(access, "stock.adjust", movement, f"{product.sku}: {delta:+} at {location.code}. {reason}")
    return movement


@transaction.atomic
def save_draft(access, form, line_data, *, kind, document_id=None):
    module = "purchases" if kind == "purchase" else "sales"
    access.require(f"rt-{module}.{'change' if document_id else 'create'}")
    access.require_modules("rt-products", "rt-locations", "rt-inventory")
    lock_workspace(access)
    if document_id:
        document = get_object_or_404(access.documents(kind).select_for_update(), pk=document_id)
        if document.status != "draft":
            raise ValidationError("Only drafts can be edited.")
        for name in form.Meta.fields:
            setattr(document, name, form.cleaned_data.get(name))
    else:
        document = form.save(commit=False)
        document.organization = access.organization
        document.kind = kind
        document.created_by = access.user
        document.currency_code = access.organization.currency_code
    document.save()
    document.lines.all().delete()  # Only a locked draft's lines are replaced.
    for data in line_data:
        if not data or data.get("DELETE"):
            continue
        product = get_object_or_404(access.scope(Product), pk=data["product"].pk, is_active=True)
        price = data.get("unit_price")
        default_price = product.cost_price if kind == "purchase" else product.selling_price
        price = default_price if price is None else price
        discount = data.get("discount") or Decimal("0")
        if kind == "sale" and (price != default_price or discount) and not access.allows("rt-sales.price_override"):
            raise ValidationError("Your role cannot override selling prices or discounts.")
        base = rounded(price * data["quantity"])
        if discount > base:
            raise ValidationError("A line discount cannot exceed its value.")
        subtotal = base - discount
        tax = rounded(subtotal * product.tax_rate / Decimal("100"))
        RetailLine.objects.create(organization=access.organization, document=document, product=product,
                                   product_name=product.name, sku=product.sku, quantity=data["quantity"],
                                   unit_price=price, discount=discount, tax_rate=product.tax_rate,
                                   subtotal=subtotal, tax=tax, total=subtotal + tax)
    if not document.lines.exists():
        raise ValidationError("Add at least one product.")
    totals = document.lines.aggregate(subtotal=Sum("subtotal"), tax_total=Sum("tax"), total=Sum("total"))
    for name, value in totals.items():
        setattr(document, name, rounded(value))
    document.save()
    audit(access, f"{kind}.draft_saved", document)
    return document


@transaction.atomic
def post_document(access, document_id, *, kind, payment_method="", payment_received=None, reference=""):
    module = "purchases" if kind == "purchase" else "sales"
    access.require(f"rt-{module}.post")
    access.require_modules("rt-inventory", "rt-products", "rt-locations")
    lock_workspace(access)
    document = get_object_or_404(access.documents(kind).select_for_update(), pk=document_id)
    if document.status == "posted":
        return document  # A retried submit must never deduct or receive twice.
    if document.status != "draft":
        raise ValidationError("A cancelled document cannot be posted.")
    if not document.location.is_active:
        raise ValidationError("The selected location is inactive.")
    if not document.lines.exists():
        raise ValidationError("Add at least one product.")
    if kind == "sale":
        if payment_method not in RetailDocument.PaymentMethod.values:
            raise ValidationError("Choose a payment method.")
        if payment_received is None or payment_received < document.total:
            raise ValidationError("Record full payment before posting the sale.")
        if payment_method != "cash" and payment_received != document.total:
            raise ValidationError("Card and bank payments must equal the amount due.")
        document.payment_method = payment_method
        document.payment_received = payment_received
        document.change_due = payment_received - document.total
        document.reference = reference
    for line in document.lines.select_related("product").order_by("product_id", "pk"):
        if not line.product.is_active:
            raise ValidationError(f"Product {line.sku} is inactive.")
        move_stock(access, line.product, document.location, line.quantity if kind == "purchase" else -line.quantity,
                   f"{document.get_kind_display()} {document.number}", document)
    document.status = "posted"
    document.posted_by = access.user
    document.posted_at = timezone.now()
    document.save()
    audit(access, f"{kind}.posted", document, f"{document.number}: {document.currency_code} {document.total}")
    return document


@transaction.atomic
def cancel_draft(access, document_id, *, kind):
    access.require(f"rt-{'purchases' if kind == 'purchase' else 'sales'}.change")
    lock_workspace(access)
    document = get_object_or_404(access.documents(kind).select_for_update(), pk=document_id)
    if document.status != "draft":
        raise ValidationError("Only drafts can be cancelled. Use a return for a posted sale.")
    document.status = "cancelled"
    document.save()
    audit(access, f"{kind}.cancelled", document)
    return document


@transaction.atomic
def refund_sale(access, sale_id, *, reason, restock):
    access.require("rt-sales.refund")
    access.require_modules("rt-inventory")
    lock_workspace(access)
    sale = get_object_or_404(access.documents("sale").select_for_update(), pk=sale_id)
    if sale.status != "posted" or access.scope(RetailDocument).filter(original_sale=sale).exists():
        raise ValidationError("Only a posted sale that has not already been returned can be refunded.")
    if not reason.strip():
        raise ValidationError("A return reason is required.")
    refund = RetailDocument.objects.create(
        organization=access.organization, kind="return", original_sale=sale, location=sale.location,
        customer=sale.customer, currency_code=sale.currency_code, notes=reason, restock=restock,
        created_by=access.user, subtotal=sale.subtotal, tax_total=sale.tax_total, total=sale.total,
        payment_method=sale.payment_method, payment_received=sale.total,
    )
    for line in sale.lines.select_related("product"):
        RetailLine.objects.create(organization=access.organization, document=refund, product=line.product,
                                  product_name=line.product_name, sku=line.sku, quantity=line.quantity,
                                  unit_price=line.unit_price, discount=line.discount, tax_rate=line.tax_rate,
                                  subtotal=line.subtotal, tax=line.tax, total=line.total)
        if restock:
            move_stock(access, line.product, sale.location, line.quantity, f"Return {refund.number}: {reason}"[:240], refund)
    refund.status = "posted"
    refund.posted_by = access.user
    refund.posted_at = timezone.now()
    refund.save()
    audit(access, "sale.refunded", refund, f"Full return of {sale.number}: {sale.currency_code} {sale.total}", {"original_sale_id": sale.pk, "restock": restock})
    return refund
