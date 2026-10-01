from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from core.models import OrganizationProfile
from workflows.models import DocumentCategory, DocumentTemplate, NumberingScheme, ServiceType, WorkflowStageTemplate


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


class Command(BaseCommand):
    help = "Initialize engineering workflow catalogs without creating accounts or permission groups."

    @transaction.atomic
    def handle(self, *args, **options):
        naya = ensure_service_type("NN", "Naya Naksa", "New building planning and approval workflow")
        abhilekh = ensure_service_type("AB", "Abhilekhikaran", "As-built / existing building workflow")
        ensure_numbering_scheme(naya, "NN")
        ensure_numbering_scheme(abhilekh, "AB")
        ensure_catalog(naya, NAYA_STAGES, NAYA_DOCS)
        ensure_catalog(abhilekh, AB_STAGES, AB_DOCS)
        self.stdout.write(self.style.SUCCESS("Workflow catalogs initialized. Create individual accounts from Engineers & Staff."))
