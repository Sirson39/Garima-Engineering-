from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from core.models import OrganizationProfile
from projects.models import Client, Project
from projects.services import create_project_initial_state
from workflows.models import DocumentCategory, DocumentTemplate, NumberingScheme, ServiceType, WorkflowStageTemplate


User = get_user_model()

DEFAULT_PASSWORD = "Password123!"

ROLE_NAMES = [
    "System Administrator",
    "Director/Management",
    "Reception/Document Officer",
    "Project Manager",
    "Planning Engineer",
    "Structural Engineer",
    "Site Engineer",
    "Online Processing Officer",
    "Municipality File Handler",
    "Accounts Officer",
    "Read-only/Auditor",
]


CATEGORY_NAMES = [
    "Client documents",
    "Napi documents",
    "Government submissions",
    "Architectural plans",
    "Client-approved plans",
    "Ward-signed documents",
    "Structural drawings",
    "Site-visit photographs",
    "Municipality correspondence",
    "Asthayi documents",
    "Isthayi documents",
    "Final approved documents",
    "Payment documents",
    "Other documents",
]


NAYA_STAGES = [
    {"code": "NN-01", "name": "Client enquiry and project registration", "status": "New", "role": "Reception/Document Officer", "days": 2, "start": True},
    {"code": "NN-02", "name": "Required document collection", "status": "Documents Pending", "role": "Reception/Document Officer", "days": 2},
    {"code": "NN-03", "name": "Document scanning and verification", "status": "Documents Verification", "role": "Reception/Document Officer", "days": 2},
    {"code": "NN-04", "name": "Physical project file preparation", "status": "Documents Verification", "role": "Reception/Document Officer", "days": 1},
    {"code": "NN-05", "name": "Initial entry into the government online system", "status": "Ready for Online Entry", "role": "Online Processing Officer", "days": 2},
    {"code": "NN-06", "name": "Record government application/reference number and submission receipt", "status": "Online Processing", "role": "Online Processing Officer", "days": 1},
    {"code": "NN-07", "name": "Assign plan preparation to the planning engineer", "status": "Plan Preparation", "role": "Project Manager", "days": 1},
    {"code": "NN-08", "name": "Planning engineer prepares the plan", "status": "Plan Preparation", "role": "Planning Engineer", "days": 4},
    {"code": "NN-09", "name": "Record plan revisions", "status": "Plan Preparation", "role": "Planning Engineer", "days": 3},
    {"code": "NN-10", "name": "Submit plan to the client for acceptance", "status": "Waiting for Client Approval", "role": "Reception/Document Officer", "days": 2, "wait": "client"},
    {"code": "NN-11", "name": "Return to planning engineer for corrections", "status": "Plan Preparation", "role": "Planning Engineer", "days": 3},
    {"code": "NN-12", "name": "Record client acceptance date", "status": "Waiting for Client Approval", "role": "Reception/Document Officer", "days": 1, "wait": "client"},
    {"code": "NN-13", "name": "Instruct client to obtain the ward signature and stamp", "status": "Waiting for Ward", "role": "Reception/Document Officer", "days": 1, "wait": "ward"},
    {"code": "NN-14", "name": "Mark the project as Waiting for Client/Ward", "status": "Waiting for Ward", "role": "Reception/Document Officer", "days": 1, "wait": "ward"},
    {"code": "NN-15", "name": "Receive the ward-signed and stamped paper", "status": "Waiting for Ward", "role": "Reception/Document Officer", "days": 1, "wait": "ward"},
    {"code": "NN-16", "name": "Scan and upload the ward-signed paper", "status": "Documents Verification", "role": "Reception/Document Officer", "days": 1},
    {"code": "NN-17", "name": "Upload the signed paper to the government online system", "status": "Online Processing", "role": "Online Processing Officer", "days": 1},
    {"code": "NN-18", "name": "Assign the project to the structural engineer", "status": "Structural Work", "role": "Project Manager", "days": 1},
    {"code": "NN-19", "name": "Structural engineer prepares and finalises the structural documents", "status": "Structural Work", "role": "Structural Engineer", "days": 5},
    {"code": "NN-20", "name": "Record structural drawing revisions and technical review", "status": "Structural Work", "role": "Structural Engineer", "days": 3},
    {"code": "NN-21", "name": "Assign final online processing to the online processing officer", "status": "Online Processing", "role": "Project Manager", "days": 1},
    {"code": "NN-22", "name": "Complete and record Asthayi/Isthayi online processing", "status": "Online Processing", "role": "Online Processing Officer", "days": 3},
    {"code": "NN-23", "name": "Transfer the physical file to the municipality file handler", "status": "Ready for Municipality", "role": "Municipality File Handler", "days": 1},
    {"code": "NN-24", "name": "Record submission to the municipality", "status": "At Municipality", "role": "Municipality File Handler", "days": 1, "wait": "municipality"},
    {"code": "NN-25", "name": "Track the file while it is at the municipality", "status": "At Municipality", "role": "Municipality File Handler", "days": 3, "wait": "municipality"},
    {"code": "NN-26", "name": "Record any municipality comments or correction requests", "status": "Correction Required", "role": "Municipality File Handler", "days": 2},
    {"code": "NN-27", "name": "Reassign corrections to the responsible employee", "status": "Correction Required", "role": "Project Manager", "days": 2},
    {"code": "NN-28", "name": "Record the signatures/approval of the municipality authorities", "status": "Approved", "role": "Municipality File Handler", "days": 1},
    {"code": "NN-29", "name": "Upload the final approved documents", "status": "Approved", "role": "Reception/Document Officer", "days": 1},
    {"code": "NN-30", "name": "Deliver the final documents to the client", "status": "Delivered", "role": "Reception/Document Officer", "days": 1},
    {"code": "NN-31", "name": "Record payment status", "status": "Payment Pending", "role": "Accounts Officer", "days": 1, "wait": "payment"},
    {"code": "NN-32", "name": "Close and archive the project", "status": "Archived", "role": "Project Manager", "days": 1, "terminal": True},
]


AB_STAGES = [
    {"code": "AB-01", "name": "Client enquiry and project registration", "status": "New", "role": "Reception/Document Officer", "days": 2, "start": True},
    {"code": "AB-02", "name": "Required document collection", "status": "Documents Pending", "role": "Reception/Document Officer", "days": 2},
    {"code": "AB-03", "name": "Ask for the old Naksa when available", "status": "Documents Pending", "role": "Reception/Document Officer", "days": 1},
    {"code": "AB-04", "name": "Document scanning and verification", "status": "Documents Verification", "role": "Reception/Document Officer", "days": 2},
    {"code": "AB-05", "name": "Prepare the physical project file", "status": "Documents Verification", "role": "Reception/Document Officer", "days": 1},
    {"code": "AB-06", "name": "Assign a site visit to an engineer", "status": "Ready for Online Entry", "role": "Project Manager", "days": 1},
    {"code": "AB-07", "name": "Record site-visit date, assigned engineer and visit status", "status": "Site Visit", "role": "Site Engineer", "days": 1},
    {"code": "AB-08", "name": "Engineer visits the house/property", "status": "Site Visit", "role": "Site Engineer", "days": 1},
    {"code": "AB-09", "name": "Record site measurements, observations, notes and photographs", "status": "Site Visit", "role": "Site Engineer", "days": 2},
    {"code": "AB-10", "name": "Upload the site-visit information", "status": "Site Visit", "role": "Site Engineer", "days": 1},
    {"code": "AB-11", "name": "Assign preparation of the existing-building/as-built Naksa", "status": "Plan Preparation", "role": "Project Manager", "days": 1},
    {"code": "AB-12", "name": "Engineer prepares the new Naksa based on the existing building", "status": "Plan Preparation", "role": "Planning Engineer", "days": 5},
    {"code": "AB-13", "name": "Record all drawing revisions", "status": "Plan Preparation", "role": "Planning Engineer", "days": 3},
    {"code": "AB-14", "name": "Submit the drawing to the client for acceptance", "status": "Waiting for Client Approval", "role": "Reception/Document Officer", "days": 2, "wait": "client"},
    {"code": "AB-15", "name": "If corrections are requested, return it to the engineer", "status": "Plan Preparation", "role": "Planning Engineer", "days": 3},
    {"code": "AB-16", "name": "Record final client acceptance", "status": "Waiting for Client Approval", "role": "Reception/Document Officer", "days": 1, "wait": "client"},
    {"code": "AB-17", "name": "Instruct the client to obtain the ward signature and stamp", "status": "Waiting for Ward", "role": "Reception/Document Officer", "days": 1, "wait": "ward"},
    {"code": "AB-18", "name": "Mark the project as Waiting for Client/Ward", "status": "Waiting for Ward", "role": "Reception/Document Officer", "days": 1, "wait": "ward"},
    {"code": "AB-19", "name": "Receive and upload the ward-signed documents", "status": "Documents Verification", "role": "Reception/Document Officer", "days": 1},
    {"code": "AB-20", "name": "Complete the required government online processing", "status": "Online Processing", "role": "Online Processing Officer", "days": 3},
    {"code": "AB-21", "name": "Complete structural review and Asthayi/Isthayi stages when applicable", "status": "Structural Work", "role": "Structural Engineer", "days": 4},
    {"code": "AB-22", "name": "Transfer the physical file to the municipality file handler", "status": "Ready for Municipality", "role": "Municipality File Handler", "days": 1},
    {"code": "AB-23", "name": "Record municipality submission", "status": "At Municipality", "role": "Municipality File Handler", "days": 1, "wait": "municipality"},
    {"code": "AB-24", "name": "Track municipality comments, corrections and approvals", "status": "At Municipality", "role": "Municipality File Handler", "days": 3, "wait": "municipality"},
    {"code": "AB-25", "name": "Upload final approved documents", "status": "Approved", "role": "Reception/Document Officer", "days": 1},
    {"code": "AB-26", "name": "Deliver documents to the client", "status": "Delivered", "role": "Reception/Document Officer", "days": 1},
    {"code": "AB-27", "name": "Record payment status", "status": "Payment Pending", "role": "Accounts Officer", "days": 1, "wait": "payment"},
    {"code": "AB-28", "name": "Close and archive the project", "status": "Archived", "role": "Project Manager", "days": 1, "terminal": True},
]


NAYA_DOCS = [
    ("Client documents", "Lalpurja", True),
    ("Client documents", "Two passport-size photographs", True),
    ("Client documents", "Citizenship", True),
    ("Napi documents", "Napi Naksa", True),
    ("Client documents", "Tax clearance paper", True),
    ("Client documents", "Likhat", True),
    ("Other documents", "Other supporting documents", True),
]


AB_DOCS = [
    ("Client documents", "Lalpurja", True),
    ("Client documents", "Two passport-size photographs", True),
    ("Client documents", "Citizenship", True),
    ("Napi documents", "Napi Naksa", True),
    ("Client documents", "Tax clearance paper", True),
    ("Client documents", "Likhat", True),
    ("Napi documents", "Old Naksa, if available", False),
    ("Site-visit photographs", "Existing-building photographs", True),
    ("Site-visit photographs", "Site-visit documents", True),
    ("Site-visit photographs", "Site measurements", True),
    ("Other documents", "Other supporting documents", True),
]


def ensure_group(name: str) -> Group:
    group, _ = Group.objects.get_or_create(name=name)
    return group


def assign_permissions(group: Group, permissions):
    group.permissions.set(permissions)


def ensure_service_type(code: str, name: str, description: str) -> ServiceType:
    service_type, _ = ServiceType.objects.get_or_create(code=code, defaults={"name": name, "description": description})
    if service_type.name != name or service_type.description != description:
        service_type.name = name
        service_type.description = description
        service_type.save(update_fields=["name", "description", "updated_at"])
    return service_type


def ensure_numbering_scheme(service_type: ServiceType, service_code: str):
    scheme, _ = NumberingScheme.objects.get_or_create(
        service_type=service_type,
        defaults={
            "prefix": "GEC",
            "service_code": service_code,
            "year_label": OrganizationProfile.load().default_bs_year,
            "sequence_width": 4,
            "next_sequence": 1,
            "separator": "-",
            "format_template": "{prefix}-{service_code}-{year_label}-{sequence:04d}",
            "is_active": True,
        },
    )
    scheme.prefix = "GEC"
    scheme.service_code = service_code
    scheme.year_label = OrganizationProfile.load().default_bs_year
    scheme.sequence_width = 4
    scheme.separator = "-"
    scheme.format_template = "{prefix}-{service_code}-{year_label}-{sequence:04d}"
    scheme.is_active = True
    scheme.save()
    return scheme


def ensure_catalog(service_type: ServiceType, stages, docs):
    categories = {}
    for name in CATEGORY_NAMES:
        category, _ = DocumentCategory.objects.get_or_create(
            service_type=service_type,
            code=slugify(name),
            defaults={"name": name, "order": CATEGORY_NAMES.index(name)},
        )
        category.name = name
        category.order = CATEGORY_NAMES.index(name)
        category.is_active = True
        category.save(update_fields=["name", "order", "is_active", "updated_at"])
        categories[name] = category

    for order, stage in enumerate(stages, start=1):
        WorkflowStageTemplate.objects.update_or_create(
            service_type=service_type,
            code=stage["code"],
            defaults={
                "name": stage["name"],
                "order": order,
                "default_status": stage["status"],
                "wait_type": stage.get("wait", "internal"),
                "responsible_role_hint": stage["role"],
                "due_days_default": stage["days"],
                "requires_document_completion": not stage.get("start", False),
                "is_start": stage.get("start", False),
                "is_terminal": stage.get("terminal", False),
                "description": stage["name"],
            },
        )

    for order, (category_name, doc_name, required) in enumerate(docs, start=1):
        DocumentTemplate.objects.update_or_create(
            service_type=service_type,
            name=doc_name,
            defaults={
                "category": categories[category_name],
                "order": order,
                "required": required,
                "allow_exception": True,
                "must_be_seen_original": True,
                "must_be_scanned": True,
                "notes": "",
                "is_active": True,
            },
        )


def ensure_user(username: str, first_name: str, last_name: str, email: str, group: Group, password: str, is_staff: bool = True, is_superuser: bool = False):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "is_staff": is_staff,
            "is_superuser": is_superuser,
        },
    )
    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.is_active = True
    user.set_password(password)
    user.save()
    user.groups.add(group)
    return user


class Command(BaseCommand):
    help = "Seed demo roles, workflows, and sample projects for Garima Engineering Consultancy."

    @transaction.atomic
    def handle(self, *args, **options):
        profile = OrganizationProfile.load()
        profile.company_name = "Garima Engineering Consultancy"
        profile.short_name = "GEC"
        profile.slogan = "Engineering consultancy management"
        profile.default_bs_year = "2083"
        profile.save()

        groups = {name: ensure_group(name) for name in ROLE_NAMES}
        internal_perm_groups = ["System Administrator", "Director/Management", "Project Manager"]
        all_perms = Permission.objects.all()
        view_perms = Permission.objects.filter(codename__startswith="view_")
        for group_name in internal_perm_groups:
            assign_permissions(groups[group_name], all_perms)
        assign_permissions(groups["Read-only/Auditor"], view_perms)

        users = {
            "admin": ensure_user("admin", "Admin", "User", "admin@gec.local", groups["System Administrator"], DEFAULT_PASSWORD, True, True),
            "manager": ensure_user("manager", "Mina", "Shrestha", "manager@gec.local", groups["Director/Management"], DEFAULT_PASSWORD),
            "reception": ensure_user("reception", "Rita", "Khadka", "reception@gec.local", groups["Reception/Document Officer"], DEFAULT_PASSWORD),
            "pm": ensure_user("pm", "Prakash", "Koirala", "pm@gec.local", groups["Project Manager"], DEFAULT_PASSWORD),
            "puja": ensure_user("puja", "Puja", "Karki", "puja@gec.local", groups["Planning Engineer"], DEFAULT_PASSWORD),
            "saroj": ensure_user("saroj", "Saroj", "Adhikari", "saroj@gec.local", groups["Online Processing Officer"], DEFAULT_PASSWORD),
            "ram": ensure_user("ram", "Ram", "Acharya", "ram@gec.local", groups["Municipality File Handler"], DEFAULT_PASSWORD),
            "structural": ensure_user("structural", "Sujan", "Sharma", "structural@gec.local", groups["Structural Engineer"], DEFAULT_PASSWORD),
            "site": ensure_user("site", "Sabina", "Thapa", "site@gec.local", groups["Site Engineer"], DEFAULT_PASSWORD),
            "accounts": ensure_user("accounts", "Anita", "Maharjan", "accounts@gec.local", groups["Accounts Officer"], DEFAULT_PASSWORD),
            "auditor": ensure_user("auditor", "Arjun", "Bista", "auditor@gec.local", groups["Read-only/Auditor"], DEFAULT_PASSWORD),
        }

        naya = ensure_service_type("NN", "Naya Naksa", "New building planning and approval workflow")
        abhilekh = ensure_service_type("AB", "Abhilekhikaran", "As-built / existing building workflow")
        ensure_numbering_scheme(naya, "NN")
        ensure_numbering_scheme(abhilekh, "AB")
        ensure_catalog(naya, NAYA_STAGES, NAYA_DOCS)
        ensure_catalog(abhilekh, AB_STAGES, AB_DOCS)

        client_1, _ = Client.objects.get_or_create(
            full_name="Suresh Adhikari",
            mobile_number="9841000001",
            defaults={
                "email": "suresh@example.com",
                "citizenship_number": "11-01-01-00001",
                "permanent_address": "Kathmandu",
                "current_address": "Kathmandu-10",
                "province": "Bagmati",
                "district": "Kathmandu",
                "municipality": "Kathmandu Metropolitan City",
                "ward_number": "10",
                "created_by": users["admin"],
            },
        )
        client_2, _ = Client.objects.get_or_create(
            full_name="Maya Shrestha",
            mobile_number="9841000002",
            defaults={
                "email": "maya@example.com",
                "citizenship_number": "11-01-01-00002",
                "permanent_address": "Lalitpur",
                "current_address": "Lalitpur-5",
                "province": "Bagmati",
                "district": "Lalitpur",
                "municipality": "Lalitpur Metropolitan City",
                "ward_number": "5",
                "created_by": users["admin"],
            },
        )

        if not Project.objects.filter(service_type=naya).exists():
            project = Project.objects.create(
                service_type=naya,
                client=client_1,
                registration_date_bs=profile.default_bs_year + "-01-15",
                property_location="Kathmandu-10, Samakhushi",
                kitta_number="1234",
                sheet_number="45",
                land_area="8 aana",
                province="Bagmati",
                district="Kathmandu",
                municipality="Kathmandu Metropolitan City",
                ward_number="10",
                government_application_number="GOV-NN-001",
                project_fee=Decimal("150000.00"),
                discount=Decimal("0.00"),
                current_file_holder="Reception",
                current_file_location="Reception",
                priority="High",
                status="New",
                created_by=users["admin"],
                updated_by=users["admin"],
                current_responsible_employee=users["reception"],
            )
            project.members.set(User.objects.filter(is_staff=True))
            create_project_initial_state(project, actor=users["admin"])

        if not Project.objects.filter(service_type=abhilekh).exists():
            project = Project.objects.create(
                service_type=abhilekh,
                client=client_2,
                registration_date_bs=profile.default_bs_year + "-02-05",
                property_location="Lalitpur-5, Jawalakhel",
                kitta_number="5678",
                sheet_number="22",
                land_area="12 aana",
                province="Bagmati",
                district="Lalitpur",
                municipality="Lalitpur Metropolitan City",
                ward_number="5",
                government_application_number="GOV-AB-001",
                project_fee=Decimal("180000.00"),
                discount=Decimal("5000.00"),
                current_file_holder="Reception",
                current_file_location="Reception",
                priority="Normal",
                status="New",
                created_by=users["admin"],
                updated_by=users["admin"],
                current_responsible_employee=users["reception"],
            )
            project.members.set(User.objects.filter(is_staff=True))
            create_project_initial_state(project, actor=users["admin"])

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
