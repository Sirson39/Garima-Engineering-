import json
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client as HttpClient, RequestFactory, TestCase
from django.urls import reverse

from accounts.models import (Company, OrganizationMembership, OrganizationModule, OrganizationRole,
                             SystemTemplate, User)
from accounts.services import provision_organization
from core.models import AuditLog
from .access import RetailAccess
from .forms import DocumentForm
from .models import Category, Customer, Location, Product, RetailDocument, RetailLine, StockBalance, StockMovement, Supplier
from .services import adjust_stock, cancel_draft, post_document, refund_sale, save_draft


class RetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.template = SystemTemplate.objects.get(code="retail-management", version="1.0")
        cls.org = cls.make_org("Store A", "store-a")
        cls.other_org = cls.make_org("Store B", "store-b")
        cls.admin = cls.make_user("retail-admin", cls.org, "organization-admin")
        cls.cashier = cls.make_user("cashier", cls.org, "cashier")
        cls.other_admin = cls.make_user("other-retail-admin", cls.other_org, "organization-admin")
        cls.auditor = cls.make_user("retail-auditor", cls.org, "read-only-auditor")
        cls.category = Category.objects.create(organization=cls.org, name="Stationery")
        cls.location = Location.objects.create(organization=cls.org, code="MAIN", name="Main store")
        cls.other_location = Location.objects.create(organization=cls.other_org, code="MAIN", name="Private store B")
        cls.supplier = Supplier.objects.create(organization=cls.org, name="Paper supplier")
        cls.other_supplier = Supplier.objects.create(organization=cls.other_org, name="Private supplier B")
        cls.customer = Customer.objects.create(organization=cls.org, name="Regular customer")
        cls.other_customer = Customer.objects.create(organization=cls.other_org, name="Private customer B")
        cls.product = Product.objects.create(organization=cls.org, sku="NOTE-01", name="Notebook", barcode="123456", category=cls.category,
                                              selling_price="12.50", cost_price="7.20", tax_rate="10", reorder_level="3")
        cls.other_product = Product.objects.create(organization=cls.other_org, sku="NOTE-01", name="Private product B", barcode="123456")
        cls.access = cls.access_for(cls.admin)
        adjust_stock(cls.access, product=cls.product, location=cls.location, delta=Decimal("10"), reason="Opening stock")

    @classmethod
    def make_org(cls, name, slug):
        org = Company.objects.create(name=name, slug=slug, organization_code=slug, category=cls.template.category, system_template=cls.template)
        for item in cls.template.template_modules.all():
            OrganizationModule.objects.create(organization=org, module=item.module)
        for template_role in cls.template.role_templates.all():
            role = OrganizationRole.objects.create(organization=org, code=template_role.code, name=template_role.name, source_template_role=template_role)
            role.permissions.set(template_role.permissions.all())
        return org

    @classmethod
    def make_user(cls, username, org, role):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", company=org)
        OrganizationMembership.objects.create(user=user, organization=org, role="staff", organization_role=org.roles.get(code=role))
        return user

    @classmethod
    def access_for(cls, user, organization_id=None):
        request = RequestFactory().get("/retail/")
        request.user = user
        request.session = {"organization_id": organization_id or user.company_id}
        return RetailAccess(request)

    def setUp(self):
        self.client.force_login(self.admin)

    def draft(self, *, kind="sale", quantity="2", user=None, price=None, discount="0"):
        access = self.access_for(user or self.admin)
        form = DocumentForm({"location": self.location.pk, "supplier": self.supplier.pk}, access=access, kind=kind)
        self.assertTrue(form.is_valid(), form.errors)
        return save_draft(access, form, [{"product": self.product, "quantity": Decimal(quantity),
                                         "unit_price": Decimal(price) if price else None, "discount": Decimal(discount)}], kind=kind)

    def post_sale(self, sale, access=None, received=None):
        return post_document(access or self.access, sale.pk, kind="sale", payment_method="cash", payment_received=received or sale.total)

    def quantity(self):
        return StockBalance.objects.get(organization=self.org, product=self.product, location=self.location).quantity

    def form_payload(self, kind="sale", quantity="2"):
        return {"location": self.location.pk, "supplier": self.supplier.pk, "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "100", "lines-0-product": self.product.pk,
                "lines-0-quantity": quantity, "lines-0-unit_price": "", "lines-0-discount": ""}

    def test_catalog_and_other_templates(self):
        self.assertEqual(self.template.template_modules.count(), 11)
        self.assertEqual(self.template.role_templates.count(), 6)
        self.assertFalse(self.template.template_modules.get(module__code="rt-reports").required)
        self.assertEqual(SystemTemplate.objects.get(code="professional-services").template_modules.count(), 6)
        self.assertEqual(SystemTemplate.objects.get(code="engineering-consultancy").template_modules.count(), 19)

    def test_provisioning_with_optional_reports(self):
        org = provision_organization(actor=self.admin, organization_data={"name": "New shop", "slug": "new-shop", "organization_code": "new-shop"},
                                     template=self.template, module_codes=set(self.template.template_modules.values_list("module__code", flat=True)),
                                     branding_data={}, admin_data={"email": "shop-owner@example.test", "full_name": "Shop Owner"})
        self.assertEqual(org.enabled_modules.count(), 11)
        self.assertEqual(org.roles.count(), 6)
        self.assertEqual(org.memberships.get().organization_role.code, "organization-admin")

    def test_wizard_has_retail_modules_and_required_field_submission(self):
        self.admin.is_platform_admin = True
        self.admin.save()
        response = self.client.get(reverse("platform-company-create"))
        self.assertContains(response, "11 modules available")
        catalog = response.context["module_catalog_json"][str(self.template.pk)]
        self.assertEqual(len(catalog), 11)
        self.assertContains(response, "requiredInput.name='modules'")

    def test_all_pages_render(self):
        for route in ["rt-dashboard", "rt-products", "rt-categories", "rt-locations", "rt-suppliers", "rt-customers", "rt-inventory",
                      "rt-inventory-adjust", "rt-purchases", "rt-sales", "rt-reports", "rt-roles", "rt-audit", "rt-products-create",
                      "rt-categories-create", "rt-locations-create", "rt-suppliers-create", "rt-customers-create", "rt-purchases-create", "rt-sales-create"]:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Private")
                self.assertNotContains(response, "New Project")
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("rt-dashboard"))

    def test_scoped_json_and_cost_privacy(self):
        self.client.force_login(self.cashier)
        products = self.client.get(reverse("rt-api-products")).json()["results"]
        self.assertEqual([row["id"] for row in products], [self.product.pk])
        self.assertNotIn("cost_price", products[0])
        self.assertNotContains(self.client.get(reverse("rt-products")), "Cost price")
        balances = self.client.get(reverse("rt-api-inventory")).json()["results"]
        self.assertEqual(len(balances), 1)
        self.assertNotIn("cost_price", balances[0])

    def test_cashier_owns_sales_and_cannot_refund_or_adjust(self):
        owned = self.draft(user=self.cashier)
        other_sale = self.draft()
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("rt-api-sales")).json()["count"], 1)
        self.assertEqual(self.client.get(reverse("rt-api-sales-detail", args=[other_sale.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("rt-inventory-adjust")).status_code, 403)
        self.assertEqual(self.client.get(reverse("rt-purchases")).status_code, 403)
        self.assertEqual(self.client.post(reverse("rt-sales-refund", args=[owned.pk]), {"reason": "test"}).status_code, 403)

    def test_auditor_cannot_change_records(self):
        self.client.force_login(self.auditor)
        self.assertEqual(self.client.get(reverse("rt-products")).status_code, 200)
        self.assertEqual(self.client.get(reverse("rt-products-create")).status_code, 403)
        self.assertEqual(self.client.post(reverse("rt-sales-create"), self.form_payload()).status_code, 403)

    def test_tenant_selection_and_platform_flags(self):
        session = self.client.session
        session["organization_id"] = self.other_org.pk
        session.save()
        self.assertEqual(self.client.get(reverse("rt-api-products")).status_code, 403)
        for flag in ["is_staff", "is_superuser", "is_platform_admin"]:
            user = User.objects.create_user(username="retail-" + flag, company=self.org, **{flag: True})
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("rt-api-products")).status_code, 403)

    def test_inactive_and_cross_tenant_roles_denied(self):
        member = OrganizationMembership.objects.get(user=self.admin, organization=self.org)
        member.organization_role = self.other_org.roles.get(code="organization-admin")
        member.save()
        self.assertEqual(self.client.get(reverse("rt-api-products")).status_code, 403)
        member.organization_role = self.org.roles.get(code="organization-admin")
        member.is_active = False
        member.save()
        self.assertEqual(self.client.get(reverse("rt-api-products")).status_code, 403)

    def test_module_disable_preserves_records_and_blocks_posting(self):
        sale = self.draft()
        self.org.enabled_modules.filter(module__code="rt-inventory").update(is_enabled=False)
        self.assertEqual(self.client.get(reverse("rt-inventory")).status_code, 403)
        response = self.client.post(reverse("rt-sales-post", args=[sale.pk]), {"payment_method": "cash", "payment_received": "30"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.quantity(), Decimal("10"))
        self.assertNotContains(self.client.get(reverse("rt-dashboard")), 'href="/retail/inventory/"')

    def test_foreign_keys_are_scoped(self):
        for field, value in [("location", self.other_location.pk), ("customer", self.other_customer.pk), ("lines-0-product", self.other_product.pk)]:
            data = self.form_payload()
            data[field] = value
            response = self.client.post(reverse("rt-sales-create"), data)
            self.assertEqual(response.status_code, 400)
        data = self.form_payload()
        data["supplier"] = self.other_supplier.pk
        self.assertEqual(self.client.post(reverse("rt-purchases-create"), data).status_code, 400)
        self.assertFalse(RetailDocument.objects.exists())

    def test_master_creation_sets_tenant_and_zero_stock(self):
        response = self.client.post(reverse("rt-products-create"), {"name": "Pens", "sku": "PEN-01", "unit": "piece", "selling_price": "5",
                                    "cost_price": "2", "tax_rate": "0", "reorder_level": "4", "is_active": "on", "organization": self.other_org.pk})
        self.assertEqual(response.status_code, 302, response.content)
        product = Product.objects.get(sku="PEN-01")
        self.assertEqual(product.organization, self.org)
        self.assertEqual(StockBalance.objects.get(product=product, location=self.location).quantity, 0)

    def test_sku_barcode_and_model_tenant_validation(self):
        with self.assertRaises(ValidationError):
            Product.objects.create(organization=self.org, sku=self.product.sku, name="Duplicate")
        with self.assertRaises(ValidationError):
            Product.objects.create(organization=self.org, sku="OTHER", barcode=self.product.barcode, name="Duplicate barcode")
        other_category = Category.objects.create(organization=self.other_org, name="Private category")
        with self.assertRaises(ValidationError):
            Product.objects.create(organization=self.org, sku="BAD", name="Invalid", category=other_category)

    def test_purchase_receipt_and_duplicate_post(self):
        purchase = self.draft(kind="purchase", quantity="4")
        self.assertEqual(purchase.total, Decimal("31.68"))
        self.assertEqual(self.quantity(), Decimal("10"))
        post_document(self.access, purchase.pk, kind="purchase")
        post_document(self.access, purchase.pk, kind="purchase")
        self.assertEqual(self.quantity(), Decimal("14"))
        self.assertEqual(StockMovement.objects.filter(document=purchase).count(), 1)

    def test_sale_totals_cash_change_and_duplicate_post(self):
        sale = self.draft()
        self.assertEqual(sale.subtotal, Decimal("25.00"))
        self.assertEqual(sale.tax_total, Decimal("2.50"))
        self.assertEqual(sale.total, Decimal("27.50"))
        result = self.post_sale(sale, received=Decimal("30"))
        self.assertEqual(result.change_due, Decimal("2.50"))
        self.post_sale(sale, received=Decimal("30"))
        self.assertEqual(self.quantity(), Decimal("8"))
        self.assertEqual(StockMovement.objects.filter(document=sale).count(), 1)

    def test_invalid_payment_does_not_change_stock(self):
        sale = self.draft()
        for method, amount in [("cash", Decimal("1")), ("card", Decimal("30")), ("bank", Decimal("0")), ("unknown", sale.total)]:
            with self.assertRaises(ValidationError):
                post_document(self.access, sale.pk, kind="sale", payment_method=method, payment_received=amount)
        self.assertEqual(self.quantity(), Decimal("10"))

    def test_insufficient_stock_rolls_back_every_line(self):
        form = DocumentForm({"location": self.location.pk}, access=self.access, kind="sale")
        self.assertTrue(form.is_valid())
        sale = save_draft(self.access, form, [{"product": self.product, "quantity": Decimal("6")},
                                             {"product": self.product, "quantity": Decimal("6")}], kind="sale")
        with self.assertRaises(ValidationError):
            self.post_sale(sale)
        self.assertEqual(self.quantity(), Decimal("10"))
        self.assertEqual(StockMovement.objects.filter(document=sale).count(), 0)
        sale.refresh_from_db()
        self.assertEqual(sale.status, "draft")

    def test_adjustment_validation(self):
        with self.assertRaises(ValidationError):
            adjust_stock(self.access, product=self.product, location=self.location, delta=Decimal("-11"), reason="Count")
        with self.assertRaises(ValidationError):
            adjust_stock(self.access, product=self.product, location=self.location, delta=Decimal("1"), reason=" ")
        with self.assertRaises(PermissionDenied):
            adjust_stock(self.access_for(self.cashier), product=self.product, location=self.location, delta=Decimal("1"), reason="Count")
        adjust_stock(self.access, product=self.product, location=self.location, delta=Decimal("-1.5"), reason="Physical count")
        self.assertEqual(self.quantity(), Decimal("8.5"))

    def test_price_overrides_and_rounding(self):
        with self.assertRaises(ValidationError):
            self.draft(user=self.cashier, price="1")
        sale = self.draft(quantity="1.5", discount="0.75")
        self.assertEqual(sale.total, Decimal("19.80"))
        with self.assertRaises(ValidationError):
            self.draft(discount="30")

    def test_posted_documents_lines_and_ledger_are_immutable(self):
        sale = self.draft()
        line = sale.lines.get()
        self.post_sale(sale)
        sale.notes = "Overwrite"
        with self.assertRaises(ValidationError):
            sale.save()
        line.quantity = Decimal("1")
        with self.assertRaises(ValidationError):
            line.save()
        with self.assertRaises(ValidationError):
            line.delete()
        with self.assertRaises(ValidationError):
            sale.delete()
        movement = StockMovement.objects.get(document=sale)
        with self.assertRaises(ValidationError):
            movement.save()

    def test_full_return_restores_stock_and_preserves_sale(self):
        sale = self.draft()
        self.post_sale(sale)
        refund = refund_sale(self.access, sale.pk, reason="Unwanted goods", restock=True)
        self.assertEqual(self.quantity(), Decimal("10"))
        self.assertEqual(refund.total, sale.total)
        sale.refresh_from_db()
        self.assertEqual(sale.status, "posted")
        self.assertEqual(sale.total, Decimal("27.50"))
        with self.assertRaises(ValidationError):
            refund_sale(self.access, sale.pk, reason="Again", restock=True)
        self.assertEqual(self.quantity(), Decimal("10"))
        self.assertContains(self.client.get(reverse("rt-sales-detail", args=[sale.pk])), "Fully returned")

    def test_return_without_restock(self):
        sale = self.draft()
        self.post_sale(sale)
        refund_sale(self.access, sale.pk, reason="Damaged items", restock=False)
        self.assertEqual(self.quantity(), Decimal("8"))

    def test_cancel_draft_and_refuse_post(self):
        sale = self.draft()
        cancel_draft(self.access, sale.pk, kind="sale")
        with self.assertRaises(ValidationError):
            self.post_sale(sale)
        self.assertEqual(self.quantity(), Decimal("10"))

    def test_edited_draft_replaces_lines_without_changing_stock(self):
        sale = self.draft()
        response = self.client.post(reverse("rt-sales-edit", args=[sale.pk]), self.form_payload(quantity="3"))
        self.assertEqual(response.status_code, 302, response.content)
        sale.refresh_from_db()
        self.assertEqual(sale.lines.count(), 1)
        self.assertEqual(sale.total, Decimal("41.25"))
        self.assertEqual(self.quantity(), Decimal("10"))

    def test_product_changes_do_not_reprice_posted_receipts(self):
        sale = self.draft()
        self.post_sale(sale)
        self.product.name = "Renamed notebook"
        self.product.selling_price = Decimal("99")
        self.product.tax_rate = Decimal("15")
        self.product.save()
        line = sale.lines.get()
        self.assertEqual(line.product_name, "Notebook")
        self.assertEqual(line.unit_price, Decimal("12.50"))
        self.assertEqual(line.tax_rate, Decimal("10"))
        self.assertEqual(line.total, Decimal("27.50"))

    def test_csv_formula_text_is_escaped(self):
        sale = self.draft()
        sale.number = '=HYPERLINK("bad")'
        sale.save()
        self.post_sale(sale)
        response = self.client.get(reverse("rt-reports-export"))
        self.assertIn("'=HYPERLINK", response.content.decode())

    def test_foreign_document_ids_cannot_be_read_or_posted(self):
        other = RetailDocument.objects.create(organization=self.other_org, kind="sale", location=self.other_location,
                                               currency_code="NPR", created_by=self.other_admin)
        self.assertEqual(self.client.get(reverse("rt-api-sales-detail", args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("rt-sales-post", args=[other.pk]), {"payment_method": "cash", "payment_received": "0"}).status_code, 404)

    def test_html_sale_draft_post_and_return_flow(self):
        self.assertEqual(self.client.post(reverse("rt-sales-create"), self.form_payload()).status_code, 302)
        sale = RetailDocument.objects.get(kind="sale")
        self.assertContains(self.client.get(reverse("rt-sales-detail", args=[sale.pk])), "27.50")
        self.assertEqual(self.client.get(reverse("rt-sales-edit", args=[sale.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("rt-sales-post", args=[sale.pk]), {"payment_method": "cash", "payment_received": "30"}).status_code, 302)
        self.assertEqual(self.client.post(reverse("rt-sales-refund", args=[sale.pk]), {"reason": "Customer return", "restock": "on"}).status_code, 302)
        self.assertEqual(self.quantity(), Decimal("10"))

    def test_empty_and_invalid_line_forms(self):
        for change in [{"lines-0-quantity": "0"}, {"lines-0-quantity": "-1"}, {"lines-0-quantity": "abc"}, {"lines-TOTAL_FORMS": "0"}]:
            response = self.client.post(reverse("rt-sales-create"), {**self.form_payload(), **change})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(RetailDocument.objects.exists())

    def test_dashboard_and_reports_refunds_and_export_audit(self):
        sale = self.draft()
        self.post_sale(sale)
        refund_sale(self.access, sale.pk, reason="Return", restock=True)
        data = self.client.get(reverse("rt-api-dashboard")).json()
        metrics = {item["label"]: item["value"] for item in data["metrics"]}
        self.assertEqual(Decimal(metrics["Sales today"]), Decimal("27.50"))
        self.assertEqual(Decimal(metrics["Net receipts today"]), Decimal("0"))
        response = self.client.get(reverse("rt-reports-export"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("-27.50", response.content.decode())
        self.assertTrue(AuditLog.objects.filter(action="retail.report.downloaded", metadata__organization_id=self.org.pk).exists())
        self.assertEqual(self.client.get(reverse("rt-reports-export"), {"start": "bad"}).status_code, 400)

    def test_role_assignment_tenant_and_self_checks(self):
        member = OrganizationMembership.objects.get(user=self.cashier, organization=self.org)
        response = self.client.post(reverse("rt-roles"), {"membership": member.pk, "organization_role": self.org.roles.get(code="store-manager").pk})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("rt-roles"), {"membership": member.pk, "organization_role": self.other_org.roles.get(code="organization-admin").pk})
        self.assertEqual(response.status_code, 400)
        own_member = OrganizationMembership.objects.get(user=self.admin, organization=self.org)
        self.assertEqual(self.client.post(reverse("rt-roles"), {"membership": own_member.pk, "organization_role": member.organization_role_id}).status_code, 400)

    def test_audit_is_scoped_and_csrf_auth_protected(self):
        AuditLog.objects.create(action="retail.sale.posted", summary="Private other tenant", metadata={"organization_id": self.other_org.pk})
        self.assertNotContains(self.client.get(reverse("rt-audit")), "Private other tenant")
        anonymous = HttpClient()
        self.assertEqual(anonymous.get(reverse("rt-api-products")).status_code, 401)
        secured = HttpClient(enforce_csrf_checks=True)
        secured.force_login(self.admin)
        self.assertEqual(secured.post(reverse("rt-sales-create"), self.form_payload()).status_code, 403)
