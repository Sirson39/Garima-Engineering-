from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from core.models import AuditTimestampModel


ZERO = Decimal("0")


def money(default=ZERO):
    return models.DecimalField(max_digits=14, decimal_places=2, default=default, validators=[MinValueValidator(ZERO)])


def quantity_field(default=ZERO):
    return models.DecimalField(max_digits=14, decimal_places=3, default=default, validators=[MinValueValidator(ZERO)])


def document_number():
    return f"RT-{uuid4().hex[:12].upper()}"


class RetailRecord(AuditTimestampModel):
    organization = models.ForeignKey("accounts.Company", on_delete=models.PROTECT, related_name="retail_%(class)s_records")

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(organization_id=self.organization_id).exists():
            raise ValidationError("An existing record cannot be moved to another organization.")
        for field in self._meta.fields:
            if field.is_relation and field.name != "organization" and getattr(self, field.attname):
                related = getattr(self, field.name)
                if hasattr(related, "organization_id") and related.organization_id != self.organization_id:
                    raise ValidationError({field.name: "Choose a record from this organization."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Category(RetailRecord):
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="rt_unique_category")]

    def __str__(self):
        return self.name


class Location(RetailRecord):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=160)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="rt_unique_location")]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Contact(RetailRecord):
    name = models.CharField(max_length=180)
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    tax_identifier = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name


class Supplier(Contact):
    pass


class Customer(Contact):
    pass


class Product(RetailRecord):
    sku = models.CharField(max_length=60)
    barcode = models.CharField(max_length=80, blank=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=30, default="piece")
    selling_price = money()
    cost_price = money()
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO,
                                   validators=[MinValueValidator(ZERO), MaxValueValidator(100)])
    reorder_level = quantity_field()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "sku"], name="rt_unique_sku"),
            models.UniqueConstraint(fields=["organization", "barcode"], condition=~models.Q(barcode=""), name="rt_unique_barcode"),
            models.CheckConstraint(condition=models.Q(selling_price__gte=0, cost_price__gte=0, reorder_level__gte=0, tax_rate__gte=0, tax_rate__lte=100), name="rt_valid_product_values"),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"


class StockBalance(RetailRecord):
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = quantity_field()

    class Meta:
        ordering = ["product__name", "location__name", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "location", "product"], name="rt_unique_stock_balance"),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="rt_stock_nonnegative"),
        ]


class RetailDocument(RetailRecord):
    class Kind(models.TextChoices):
        PURCHASE = "purchase", "Purchase receipt"
        SALE = "sale", "Sale"
        RETURN = "return", "Sales return"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        BANK = "bank", "Bank transfer"

    number = models.CharField(max_length=40, default=document_number)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.PROTECT)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.PROTECT)
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    original_sale = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="full_return")
    restock = models.BooleanField(default=True)
    currency_code = models.CharField(max_length=3)
    subtotal = money()
    tax_total = money()
    total = money()
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, blank=True)
    payment_received = money()
    change_due = money()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="retail_documents")
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="posted_retail_documents")
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="rt_unique_document_number"),
            models.CheckConstraint(condition=models.Q(subtotal__gte=0, tax_total__gte=0, total__gte=0, payment_received__gte=0, change_due__gte=0), name="rt_document_nonnegative"),
        ]
        indexes = [models.Index(fields=["organization", "kind", "status"])]

    def clean(self):
        super().clean()
        if self.kind == self.Kind.PURCHASE and not self.supplier_id:
            raise ValidationError({"supplier": "A supplier is required for a purchase receipt."})
        if self.kind == self.Kind.RETURN and not self.original_sale_id:
            raise ValidationError("A sales return must reference the original sale.")

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, organization_id=self.organization_id).exclude(status=self.Status.DRAFT).exists():
            raise ValidationError("Posted or cancelled records cannot be overwritten.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Retain retail documents; cancel drafts or record a sales return.")

    def __str__(self):
        return self.number


class RetailLine(RetailRecord):
    document = models.ForeignKey(RetailDocument, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=60)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    unit_price = money()
    discount = money()
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(ZERO), MaxValueValidator(100)])
    subtotal = money()
    tax = money()
    total = money()

    class Meta:
        ordering = ["pk"]
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_price__gte=0, discount__gte=0, subtotal__gte=0, tax__gte=0, total__gte=0, tax_rate__gte=0, tax_rate__lte=100), name="rt_valid_line_values")]

    def save(self, *args, **kwargs):
        if (self.pk and type(self).objects.filter(pk=self.pk).exclude(document__status=RetailDocument.Status.DRAFT).exists()) or RetailDocument.objects.filter(pk=self.document_id, organization_id=self.organization_id).exclude(status=RetailDocument.Status.DRAFT).exists():
            raise ValidationError("Lines on a posted or cancelled record cannot be changed.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if RetailDocument.objects.filter(pk=self.document_id, organization_id=self.organization_id).exclude(status=RetailDocument.Status.DRAFT).exists():
            raise ValidationError("Lines on a posted or cancelled record cannot be removed.")
        return super().delete(*args, **kwargs)


class StockMovement(RetailRecord):
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    document = models.ForeignKey(RetailDocument, null=True, blank=True, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    balance_after = quantity_field()
    reason = models.CharField(max_length=240)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(balance_after__gte=0) & ~models.Q(quantity=0), name="rt_valid_movement")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Stock movements are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Stock movements are append-only.")
