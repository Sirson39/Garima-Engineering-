from core.models import OrganizationProfile


def organization(request):
    membership = getattr(request, "workspace_membership", None)
    engineering = bool(membership and membership.organization.system_template and
                       membership.organization.system_template.code == "engineering-consultancy")
    return {
        "organization": OrganizationProfile.load(),
        "engineering_membership": membership if engineering else None,
        "engineering_employee": engineering and membership.role != "admin",
    }
