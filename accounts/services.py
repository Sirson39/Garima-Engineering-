from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    Company,
    CustomStartingStructure,
    ModuleDefinition,
    OrganizationBranding,
    OrganizationConfiguration,
    OrganizationInvitation,
    OrganizationModule,
    OrganizationMembership,
    OrganizationRole,
    OrganizationTerminology,
    RoleTemplate,
    SystemTemplate,
    TemplateModule,
    User,
)
from core.services import log_audit


def generate_temporary_password() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(14))


class ProvisioningError(ValueError):
    """Raised when a template cannot safely provision an organization."""


def validate_module_selection(template: SystemTemplate, module_codes: set[str]) -> list[ModuleDefinition]:
    template_modules = {
        item.module.code: item
        for item in TemplateModule.objects.select_related("module").filter(system_template=template)
    }
    unknown = module_codes.difference(template_modules)
    if unknown:
        raise ProvisioningError(
            "These modules are not available for the selected template: "
            + ", ".join(sorted(unknown))
            + "."
        )

    selected = set(module_codes)
    for code, item in template_modules.items():
        if item.required and code not in selected:
            raise ProvisioningError(f"Required module '{item.module.name}' cannot be disabled.")

    for code in list(selected):
        module = template_modules[code].module
        for dependency in module.dependencies.select_related("required_module"):
            if dependency.required_module.code not in selected:
                raise ProvisioningError(
                    f"Module '{module.name}' requires '{dependency.required_module.name}'."
                )
        for conflict in module.conflicts.select_related("conflicting_module"):
            if conflict.conflicting_module.code in selected:
                raise ProvisioningError(
                    f"Modules '{module.name}' and '{conflict.conflicting_module.name}' "
                    "cannot be enabled together."
                )

    return [template_modules[code].module for code in sorted(selected)]


def _send_invitation(invitation_id: int, raw_token: str) -> None:
    invitation = OrganizationInvitation.objects.select_related("organization").get(pk=invitation_id)
    base_url = getattr(settings, "PUBLIC_APP_URL", "").rstrip("/")
    invite_url = f"{base_url}{reverse('organization-invitation', args=[raw_token])}"
    send_mail(
        subject=f"You have been invited to {invitation.organization.name}",
        message=(
            f"You have been invited to administer {invitation.organization.name}. "
            f"Open this secure invitation to create your password: {invite_url}\n\n"
            "This invitation expires in 48 hours and can only be used once."
        ),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@siru.local"),
        recipient_list=[invitation.email],
        fail_silently=True,
    )


@transaction.atomic
def provision_organization(
    *,
    actor,
    organization_data: dict,
    template: SystemTemplate,
    module_codes: set[str],
    branding_data: dict,
    admin_data: dict,
    custom_starting_structure: CustomStartingStructure | None = None,
):
    if User.objects.filter(email__iexact=admin_data["email"]).exists():
        raise ProvisioningError("The administrator email is already in use.")
    modules = validate_module_selection(template, module_codes)
    organization = Company.objects.create(
        **organization_data,
        category=template.category,
        system_template=template,
        applied_template_version=template.version,
        provisioning_status="provisioning",
        created_by=actor,
    )

    OrganizationBranding.objects.create(organization=organization, **branding_data)
    for module in modules:
        OrganizationModule.objects.create(organization=organization, module=module, enabled_by=actor)

    if template.code == "custom-organization":
        OrganizationConfiguration.objects.create(
            organization=organization,
            version=1,
            status=OrganizationConfiguration.STATUS_PUBLISHED,
            starting_structure=custom_starting_structure,
            created_by=actor,
            published_by=actor,
            published_at=timezone.now(),
            notes="Initial Custom workspace configuration.",
        )
        default_terms = {
            "client": "Client",
            "project": "Project",
            "task": "Task",
            "employee": "Employee",
            "department": "Department",
        }
        for internal_code, label in default_terms.items():
            OrganizationTerminology.objects.create(
                organization=organization,
                internal_code=internal_code,
                label=label,
                updated_by=actor,
            )

    role_map = {}
    for role_template in RoleTemplate.objects.prefetch_related("permissions").filter(system_template=template):
        role = OrganizationRole.objects.create(
            organization=organization,
            code=role_template.code,
            name=role_template.name,
            source_template_role=role_template,
        )
        role.permissions.set(role_template.permissions.all())
        role_map[role_template.code] = role

    admin_role = role_map.get("organization-admin") or role_map.get("admin")
    raw_token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation.objects.create(
        organization=organization,
        email=admin_data["email"],
        full_name=admin_data.get("full_name", ""),
        job_title=admin_data.get("job_title", ""),
        role=admin_role,
        token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
        invited_by=actor,
        expires_at=timezone.now() + timedelta(hours=48),
    )
    first_name, _, last_name = admin_data.get("full_name", "").partition(" ")
    temporary_password = admin_data.get("temporary_password") or generate_temporary_password()
    user = User(
        username=admin_data["email"],
        email=admin_data["email"],
        first_name=first_name,
        last_name=last_name,
        phone=admin_data.get("phone", ""),
        job_title=admin_data.get("job_title", ""),
        company=organization,
        company_role=User.ROLE_ADMIN,
    )
    user.set_password(temporary_password)
    user.is_active = True
    user.must_change_password = True
    user.save()
    if template.code == "general-office-management":
        from office.models import OfficeStaffProfile

        OfficeStaffProfile.objects.create(
            organization=organization,
            user=user,
            employee_id=f"ADMIN-{user.pk:04d}",
            employment_status=OfficeStaffProfile.EMPLOYMENT_ACTIVE,
            account_status="active",
        )
    OrganizationMembership.objects.create(
        user=user,
        organization=organization,
        role=OrganizationMembership.ROLE_ADMIN,
        organization_role=admin_role,
        is_active=True,
    )

    organization.provisioning_status = "ready"
    organization.save(update_fields=["provisioning_status", "updated_at"])
    log_audit(
        actor,
        "organization.provisioned",
        obj=organization,
        summary=f"Provisioned {organization.name} from {template.name} v{template.version}.",
        metadata={"template": template.code, "modules": sorted(module_codes), "invitation_id": invitation.pk},
    )
    transaction.on_commit(lambda: _send_invitation(invitation.pk, raw_token))
    # The raw password is returned only to the calling request so it can be
    # shown once to the platform administrator; only its hash is persisted.
    organization._temporary_admin_password = temporary_password
    organization._temporary_admin_email = admin_data["email"]
    return organization
