import json
import re
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import Client as HttpClient, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (Company, OrganizationMembership, OrganizationModule,
                             OrganizationRole, SystemTemplate, User)
from accounts.services import provision_organization
from core.models import AuditLog
from .models import Engagement, ProfessionalClient, ProfessionalService, ProfessionalSettings


class ProfessionalServicesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.template = SystemTemplate.objects.get(code="professional-services", version="1.0")
        cls.org = cls.make_org("Practice A", "practice-a")
        cls.other_org = cls.make_org("Practice B", "practice-b")
        cls.admin = cls.make_user("admin-a", cls.org, "organization-admin")
        cls.other_admin = cls.make_user("admin-b", cls.other_org, "organization-admin")
        cls.consultant = cls.make_user("consultant-a", cls.org, "consultant")
        cls.unassigned = cls.make_user("unassigned-a", cls.org, "consultant")
        cls.manager = cls.make_user("manager-a", cls.org, "account-manager")
        cls.customer = ProfessionalClient.objects.create(organization=cls.org, name="Visible client", status="active", account_manager=cls.admin)
        cls.other_customer = ProfessionalClient.objects.create(organization=cls.other_org, name="Confidential client B", account_manager=cls.other_admin)
        cls.service = ProfessionalService.objects.create(organization=cls.org, code="ADVISORY", name="Advisory")
        cls.other_service = ProfessionalService.objects.create(organization=cls.other_org, code="ADVISORY", name="Confidential service B")
        cls.engagement = Engagement.objects.create(
            organization=cls.org, number="ENG-001", title="Visible engagement", client=cls.customer,
            service=cls.service, engagement_manager=cls.admin, status="active", due_date=timezone.localdate() + timedelta(days=7),
        )
        cls.engagement.assigned_team.add(cls.consultant)
        cls.other_engagement = Engagement.objects.create(
            organization=cls.other_org, number="ENG-001", title="Confidential engagement B", client=cls.other_customer,
            service=cls.other_service, engagement_manager=cls.other_admin,
        )

    @classmethod
    def make_org(cls, name, slug):
        org = Company.objects.create(name=name, slug=slug, organization_code=slug,
                                     category=cls.template.category, system_template=cls.template)
        for item in cls.template.template_modules.all():
            OrganizationModule.objects.create(organization=org, module=item.module)
        for template_role in cls.template.role_templates.all():
            role = OrganizationRole.objects.create(organization=org, code=template_role.code,
                                                   name=template_role.name, source_template_role=template_role)
            role.permissions.set(template_role.permissions.all())
        return org

    @classmethod
    def make_user(cls, username, org, role):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", company=org)
        OrganizationMembership.objects.create(user=user, organization=org, role="staff",
                                                organization_role=org.roles.get(code=role))
        return user

    def setUp(self):
        self.client.force_login(self.admin)

    def api(self, resource, pk=None):
        return reverse(f"ps-api-{resource}" + ("-detail" if pk else ""), args=[pk] if pk else [])

    def post_json(self, resource, data):
        return self.client.post(self.api(resource), data=json.dumps(data), content_type="application/json")

    def patch_json(self, resource, pk, data):
        return self.client.patch(self.api(resource, pk), data=json.dumps(data), content_type="application/json")

    def engagement_payload(self):
        return {"number": "ENG-NEW", "title": "New engagement", "client": self.customer.pk, "service": self.service.pk,
                "engagement_manager": self.admin.pk, "billing_method": "hourly", "progress": 0, "status": "draft"}

    def test_catalog_and_other_templates_remain_separate(self):
        self.assertEqual(self.template.name, "Professional Service Management")
        self.assertEqual(self.template.template_modules.count(), 6)
        self.assertEqual(self.template.role_templates.count(), 10)
        self.assertEqual(self.template.role_templates.get(code="client-portal-user").permissions.count(), 0)
        for code, count in [("engineering-consultancy", 19), ("hospital-management", 14), ("valuation-management", 6)]:
            self.assertEqual(SystemTemplate.objects.get(code=code).template_modules.count(), count)

    def test_provisioning_copies_roles_modules_and_admin_permission(self):
        org = provision_organization(actor=self.admin, organization_data={"name": "New firm", "slug": "new-firm", "organization_code": "new-firm"},
                                     template=self.template, module_codes=set(self.template.template_modules.values_list("module__code", flat=True)),
                                     branding_data={}, admin_data={"email": "new-firm@example.test", "full_name": "New Owner"})
        self.assertEqual(org.roles.count(), 10)
        self.assertEqual(org.enabled_modules.count(), 6)
        membership = org.memberships.get()
        self.assertEqual(membership.organization_role.code, "organization-admin")
        self.assertTrue(membership.organization_role.permissions.filter(code="ps-engagements.create").exists())
        self.client.force_login(membership.user)
        self.assertRedirects(self.client.get(reverse("ps-dashboard")), reverse("password-change"))

    def test_wizard_catalog_is_an_object_and_template_card_is_enabled(self):
        self.admin.is_platform_admin = True
        self.admin.save(update_fields=["is_platform_admin"])
        response = self.client.get(reverse("platform-company-create"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        payload = re.search(r'<script id="module-catalog" type="application/json">(.*?)</script>', html, re.S).group(1)
        catalog = json.loads(payload)
        self.assertIsInstance(catalog, dict)
        self.assertEqual(len(catalog[str(self.template.pk)]), 6)
        card = re.search(r'<label class="platform-template-card [^>]*>.*?name="template_card" value="' + str(self.template.pk) + r'".*?</label>', html, re.S).group(0)
        # Isolate the label containing this radio rather than preceding cards.
        card = card[card.rfind('<label'):]
        self.assertNotIn("is-disabled", card)
        self.assertIn("6 modules available", card)

    def test_api_defaults_and_service_billing_method(self):
        self.service.default_billing_method = "retainer"
        self.service.save()
        response = self.post_json("engagements", {"title": "Retained advice", "client": self.customer.pk, "service": self.service.pk})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["billing_method"], "retainer")
        self.assertTrue(response.json()["number"].startswith("ENG-"))
        self.assertEqual(self.post_json("clients", {"name": "Prospect"}).status_code, 201)
        self.assertEqual(self.post_json("services", {"name": "Strategy", "code": "STRATEGY"}).status_code, 201)

    def test_manager_status_counts_do_not_duplicate_team_members(self):
        self.engagement.engagement_manager = self.manager
        self.engagement.save()
        self.engagement.assigned_team.add(self.unassigned)
        self.client.force_login(self.manager)
        result = self.client.get(reverse("ps-api-dashboard")).json()
        self.assertEqual(result["status_counts"], [{"status": "Active", "total": 1}])

    def test_pages_render_with_professional_navigation(self):
        for route in ("ps-dashboard", "ps-clients", "ps-services", "ps-engagements", "ps-clients-create", "ps-services-create",
                      "ps-engagements-create", "ps-roles", "ps-settings", "ps-audit"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Practice A")
                self.assertNotContains(response, "New Project")
                self.assertNotContains(response, "Confidential")
        for resource, pk in [("clients", self.customer.pk), ("services", self.service.pk), ("engagements", self.engagement.pk)]:
            for mode in ("detail", "edit"):
                self.assertEqual(self.client.get(reverse(f"ps-{resource}-{mode}", args=[pk])).status_code, 200)

    def test_selected_organization_routes_dashboard(self):
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("ps-dashboard"))
        OrganizationMembership.objects.create(user=self.admin, organization=self.other_org, role="staff",
                                                organization_role=self.other_org.roles.get(code="organization-admin"))
        session = self.client.session
        session["organization_id"] = self.other_org.pk
        session.save()
        response = self.client.get(reverse("ps-dashboard"))
        self.assertContains(response, "Practice B")
        self.assertNotContains(response, "Visible client")

    def test_query_or_body_cannot_select_organization(self):
        response = self.client.get(self.api("clients"), {"organization_id": self.other_org.pk, "role": "admin"})
        self.assertEqual([item["id"] for item in response.json()["results"]], [self.customer.pk])
        self.assertEqual(self.post_json("clients", {"name": "Spoof", "organization": self.other_org.pk}).status_code, 400)
        self.assertFalse(ProfessionalClient.objects.filter(name="Spoof").exists())

    def test_session_organization_requires_membership(self):
        session = self.client.session
        session["organization_id"] = self.other_org.pk
        session.save()
        self.assertEqual(self.client.get(reverse("ps-dashboard")).status_code, 403)
        self.assertEqual(self.client.get(self.api("clients")).status_code, 403)

    def test_cross_tenant_detail_and_edit_are_not_found(self):
        for resource, record in [("clients", self.other_customer), ("services", self.other_service), ("engagements", self.other_engagement)]:
            self.assertEqual(self.client.get(self.api(resource, record.pk)).status_code, 404)
            self.assertEqual(self.client.get(reverse(f"ps-{resource}-edit", args=[record.pk])).status_code, 404)
            self.assertEqual(self.patch_json(resource, record.pk, {"status": "archived"}).status_code, 404)

    def test_assignment_required_even_for_organization_member(self):
        self.client.force_login(self.unassigned)
        self.assertEqual(self.client.get(self.api("engagements")).json()["count"], 0)
        self.assertEqual(self.client.get(self.api("clients")).json()["count"], 0)
        self.assertEqual(self.client.get(self.api("engagements", self.engagement.pk)).status_code, 404)
        self.client.force_login(self.consultant)
        self.assertEqual(self.client.get(self.api("engagements")).json()["count"], 1)
        self.assertEqual(self.client.get(self.api("clients")).json()["count"], 1)
        self.engagement.assigned_team.remove(self.consultant)
        self.assertEqual(self.client.get(self.api("engagements", self.engagement.pk)).status_code, 404)

    def test_platform_and_superuser_flags_do_not_grant_access(self):
        for field in ("is_superuser", "is_platform_admin", "is_staff"):
            user = User.objects.create_user(username=field, company=self.org, **{field: True})
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.api("engagements")).status_code, 403)

    def test_inactive_or_cross_tenant_role_denied(self):
        member = OrganizationMembership.objects.get(user=self.admin, organization=self.org)
        member.organization_role = self.other_org.roles.get(code="organization-admin")
        member.save()
        self.assertEqual(self.client.get(self.api("clients")).status_code, 403)
        member.organization_role = self.org.roles.get(code="organization-admin")
        member.is_active = False
        member.save()
        self.assertEqual(self.client.get(self.api("clients")).status_code, 403)
        member.is_active = True
        member.save()
        member.organization_role.is_active = False
        member.organization_role.save()
        self.assertEqual(self.client.get(self.api("clients")).status_code, 403)

    def test_disabled_modules_hide_navigation_block_apis_and_preserve_records(self):
        self.org.enabled_modules.filter(module__code="ps-engagements").update(is_enabled=False)
        self.assertEqual(self.client.get(self.api("engagements")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ps-engagements")).status_code, 403)
        response = self.client.get(reverse("ps-dashboard"))
        self.assertNotContains(response, 'href="/professional-services/engagements/"')
        self.assertNotContains(response, "Active engagements")
        self.assertTrue(Engagement.objects.filter(pk=self.engagement.pk).exists())

    def test_consultant_is_read_only_and_buttons_are_hidden(self):
        self.client.force_login(self.consultant)
        self.assertEqual(self.post_json("engagements", self.engagement_payload()).status_code, 403)
        self.assertEqual(self.patch_json("engagements", self.engagement.pk, {"status": "archived"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("ps-roles")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("ps-dashboard")), "New engagement")

    def test_dashboard_totals_are_scoped_and_real(self):
        Engagement.objects.create(organization=self.org, title="Late work", client=self.customer, service=self.service,
                                   engagement_manager=self.admin, due_date=timezone.localdate() - timedelta(days=2), status="active")
        response = self.client.get(reverse("ps-api-dashboard")).json()
        metrics = {metric["label"]: metric["value"] for metric in response["metrics"]}
        self.assertEqual(metrics, {"Active clients": 1, "Active engagements": 2, "Deadlines in 30 days": 1, "Overdue engagements": 1})
        self.assertEqual(len(response["upcoming"]), 1)
        self.assertEqual(response["workload"][0]["total"], 2)
        self.client.force_login(self.unassigned)
        self.assertTrue(all(metric["value"] == 0 for metric in self.client.get(reverse("ps-api-dashboard")).json()["metrics"]))

    def test_create_and_patch_client_audit_and_many_to_many_preserved(self):
        response = self.post_json("clients", {"name": "New client", "status": "active", "services_used": [self.service.pk]})
        self.assertEqual(response.status_code, 201, response.content)
        pk = response.json()["id"]
        response = self.patch_json("clients", pk, {"contact_person": "New contact"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["services_used"], [self.service.pk])
        self.assertEqual(response.json()["name"], "New client")
        self.assertEqual(AuditLog.objects.filter(action__startswith="ps.client.", metadata__organization_id=self.org.pk).count(), 2)

    def test_create_service_and_engagement_api(self):
        response = self.post_json("services", {"name": "Review", "code": "REVIEW", "status": "active", "default_billing_method": "fixed"})
        self.assertEqual(response.status_code, 201, response.content)
        response = self.post_json("engagements", self.engagement_payload())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["number"], "ENG-NEW")
        self.assertEqual(Engagement.objects.get(pk=response.json()["id"]).organization, self.org)

    def test_html_create_edit_and_archive(self):
        response = self.client.post(reverse("ps-clients-create"), {"name": "HTML client", "status": "prospective", "account_manager": self.admin.pk})
        self.assertEqual(response.status_code, 302)
        record = ProfessionalClient.objects.get(name="HTML client")
        response = self.client.post(reverse("ps-clients-edit", args=[record.pk]), {"name": "HTML client", "status": "archived", "account_manager": self.admin.pk})
        self.assertEqual(response.status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.status, "archived")

    def test_cross_tenant_foreign_keys_and_team_are_rejected(self):
        for key, value in [("client", self.other_customer.pk), ("service", self.other_service.pk),
                           ("engagement_manager", self.other_admin.pk), ("assigned_team", [self.other_admin.pk])]:
            data = self.engagement_payload()
            data[key] = value
            response = self.post_json("engagements", data)
            self.assertEqual(response.status_code, 400, response.content)
            self.assertIn(key, response.json()["errors"])
        response = self.post_json("clients", {"name": "Invalid", "status": "active", "services_used": [self.other_service.pk]})
        self.assertEqual(response.status_code, 400)

    def test_invalid_dates_rates_progress_status_and_duplicate_number(self):
        for changes in [{"start_date": "2026-10-10", "due_date": "2026-10-01"}, {"billing_rate": "-1"},
                        {"progress": 101}, {"progress": -1}, {"contract_amount": "-2"}, {"status": "invented"}, {"number": "ENG-001"}]:
            response = self.post_json("engagements", {**self.engagement_payload(), **changes})
            self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Engagement.objects.filter(number="ENG-NEW").exists())

    def test_model_relationship_and_uniqueness_validation(self):
        self.engagement.client = self.other_customer
        with self.assertRaises(ValidationError):
            self.engagement.save()
        with self.assertRaises(ValidationError):
            ProfessionalService.objects.create(organization=self.org, code="ADVISORY", name="Duplicate")

    def test_rate_precedence_preserves_explicit_zero(self):
        ProfessionalSettings.objects.create(organization=self.org, default_rate=50)
        self.assertEqual(self.engagement.effective_rate, Decimal("50"))
        self.service.default_rate = Decimal("75")
        self.service.save()
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.effective_rate, Decimal("75"))
        self.customer.billing_rate = Decimal("90")
        self.customer.save()
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.effective_rate, Decimal("90"))
        self.engagement.billing_rate = Decimal("0")
        self.assertEqual(self.engagement.effective_rate, Decimal("0"))
        self.engagement.billing_method = "internal"
        self.engagement.billing_rate = Decimal("100")
        self.assertEqual(self.engagement.effective_rate, Decimal("0"))

    def test_role_assignment_enforces_organization_and_prevents_self_change(self):
        member = OrganizationMembership.objects.get(user=self.consultant, organization=self.org)
        admin_role = self.org.roles.get(code="organization-admin")
        response = self.client.post(reverse("ps-roles"), {"membership": member.pk, "organization_role": admin_role.pk})
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.organization_role, admin_role)
        response = self.client.post(reverse("ps-roles"), {"membership": member.pk, "organization_role": self.other_org.roles.get(code="organization-admin").pk})
        self.assertEqual(response.status_code, 400)
        self_member = OrganizationMembership.objects.get(user=self.admin, organization=self.org)
        response = self.client.post(reverse("ps-roles"), {"membership": self_member.pk, "organization_role": admin_role.pk})
        self.assertEqual(response.status_code, 400)

    def test_settings_and_audit_are_organization_scoped(self):
        self.assertEqual(self.client.post(reverse("ps-settings"), {"default_rate": "125.50"}).status_code, 302)
        self.assertEqual(ProfessionalSettings.objects.get(organization=self.org).default_rate, Decimal("125.50"))
        self.assertFalse(ProfessionalSettings.objects.filter(organization=self.other_org).exists())
        AuditLog.objects.create(action="ps.client.change", summary="Secret other organization", object_type="ProfessionalClient",
                                object_id=str(self.other_customer.pk), metadata={"organization_id": self.other_org.pk})
        self.assertNotContains(self.client.get(reverse("ps-audit")), "Secret other organization")

    def test_api_authentication_csrf_and_http_methods(self):
        anonymous = HttpClient()
        self.assertEqual(anonymous.get(self.api("clients")).status_code, 401)
        secured = HttpClient(enforce_csrf_checks=True)
        secured.force_login(self.admin)
        self.assertEqual(secured.post(self.api("clients"), data='{}', content_type="application/json").status_code, 403)
        self.assertEqual(self.client.delete(self.api("engagements", self.engagement.pk)).status_code, 405)
        self.assertEqual(self.client.post(self.api("clients"), data="{", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(self.api("clients"), data={"name": "wrong type"}).status_code, 415)

    def test_search_filters_and_pagination(self):
        for index in range(22):
            ProfessionalClient.objects.create(organization=self.org, name=f"Additional {index}", status="inactive")
        result = self.client.get(self.api("clients")).json()
        self.assertEqual(result["count"], 23)
        self.assertEqual(len(result["results"]), 20)
        self.assertEqual(len(self.client.get(self.api("clients"), {"page": 2}).json()["results"]), 3)
        result = self.client.get(self.api("clients"), {"q": "Visible", "status": "active"}).json()
        self.assertEqual(result["count"], 1)
