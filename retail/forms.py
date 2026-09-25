from decimal import Decimal

from django import forms
from django.forms import formset_factory

from accounts.models import OrganizationMembership, OrganizationRole
from .models import Category, Customer, Location, Product, RetailDocument, Supplier


def style_fields(form):
    for field in form.fields.values():
        field.widget.attrs["class"] = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-select" if isinstance(field.widget, forms.Select) else "form-control"
        if isinstance(field.widget, forms.Textarea):
            field.widget.attrs["rows"] = 3


class ScopedForm(forms.ModelForm):
    def __init__(self, *args, access, **kwargs):
        super().__init__(*args, **kwargs)
        self.access = access
        self.instance.organization = access.organization
        for field in self.fields.values():
            if isinstance(field, forms.ModelChoiceField):
                field.queryset = access.scope(field.queryset.model)
        style_fields(self)

    def clean(self):
        data = super().clean()
        model = self._meta.model
        keys = {Category: ["name"], Product: ["sku", "barcode"], Location: ["code"]}.get(model, [])
        for key in keys:
            if data.get(key) and self.access.scope(model).filter(**{key: data[key]}).exclude(pk=self.instance.pk).exists():
                self.add_error(key, "This value is already used in this organization.")
        return data


class ProductForm(ScopedForm):
    class Meta:
        model = Product
        fields = ["sku", "barcode", "name", "category", "description", "unit", "selling_price", "cost_price", "tax_rate", "reorder_level", "is_active"]
        help_texts = {"tax_rate": "Exclusive tax percentage. Set the rate appropriate for this product.", "reorder_level": "A stock balance at or below this quantity appears as low stock."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.access.allows("rt-products.cost"):
            self.fields.pop("cost_price")


class CategoryForm(ScopedForm):
    class Meta:
        model = Category
        fields = ["name"]


class LocationForm(ScopedForm):
    class Meta:
        model = Location
        fields = ["code", "name", "address", "is_active"]


class SupplierForm(ScopedForm):
    class Meta:
        model = Supplier
        fields = ["name", "contact_person", "email", "phone", "address", "tax_identifier", "notes", "is_active"]


class CustomerForm(ScopedForm):
    class Meta:
        model = Customer
        fields = SupplierForm.Meta.fields


class DocumentForm(ScopedForm):
    class Meta:
        model = RetailDocument
        fields = ["location", "supplier", "customer", "reference", "notes"]

    def __init__(self, *args, kind, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("customer" if kind == "purchase" else "supplier")
        self.fields["location"].queryset = self.fields["location"].queryset.filter(is_active=True)
        contact = self.fields["supplier" if kind == "purchase" else "customer"]
        contact.queryset = contact.queryset.filter(is_active=True)
        contact.required = kind == "purchase"
        if kind == "sale":
            contact.empty_label = "Walk-in customer"


class LineForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    unit_price = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False,
                                    help_text="Leave blank for the current product price.")
    discount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, label="Line discount")

    def __init__(self, *args, access, kind, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = access.scope(Product).filter(is_active=True)
        if kind == "sale" and not access.allows("rt-sales.price_override"):
            self.fields["unit_price"].disabled = True
            self.fields["discount"].disabled = True
        style_fields(self)

    def clean(self):
        data = super().clean()
        if self.fields["unit_price"].disabled:
            data["unit_price"] = None
            data["discount"] = Decimal("0")
        return data


class RequiredLineFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if not any(form.cleaned_data and not form.cleaned_data.get("DELETE") for form in self.forms):
            raise forms.ValidationError("Add at least one product.")


LineFormSet = formset_factory(LineForm, formset=RequiredLineFormSet, extra=1, can_delete=True,
                              max_num=100, validate_max=True, absolute_max=100)


class AdjustmentForm(forms.Form):
    location = forms.ModelChoiceField(queryset=Location.objects.none())
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    delta = forms.DecimalField(max_digits=14, decimal_places=3, label="Quantity change",
                              help_text="Positive adds stock; negative removes stock.")
    reason = forms.CharField(max_length=240, widget=forms.Textarea)

    def __init__(self, *args, access, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = access.scope(Location).filter(is_active=True)
        self.fields["product"].queryset = access.scope(Product).filter(is_active=True)
        style_fields(self)

    def clean_delta(self):
        value = self.cleaned_data["delta"]
        if not value:
            raise forms.ValidationError("Enter a nonzero quantity change.")
        return value


class PaymentForm(forms.Form):
    payment_method = forms.ChoiceField(choices=RetailDocument.PaymentMethod.choices)
    payment_received = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, label="Payment received / cash tendered")
    reference = forms.CharField(max_length=120, required=False, label="Payment reference")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)


class ReturnForm(forms.Form):
    reason = forms.CharField(max_length=240, widget=forms.Textarea)
    restock = forms.BooleanField(required=False, initial=True, label="Return all items to available stock")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)


class DateRangeForm(forms.Form):
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="From")
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Through")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise forms.ValidationError("The end date must be on or after the start date.")
        return data


class RoleForm(forms.Form):
    membership = forms.ModelChoiceField(queryset=OrganizationMembership.objects.none(), label="Organization member")
    organization_role = forms.ModelChoiceField(queryset=OrganizationRole.objects.none(), label="Retail role")

    def __init__(self, *args, access, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["membership"].queryset = OrganizationMembership.objects.filter(organization=access.organization, is_active=True, user__is_active=True).exclude(user=access.user).select_related("user")
        self.fields["membership"].label_from_instance = lambda member: member.user.display_name
        self.fields["organization_role"].queryset = OrganizationRole.objects.filter(organization=access.organization, is_active=True)
        style_fields(self)
