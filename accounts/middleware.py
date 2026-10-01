from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from accounts.workspace_access import active_membership


class EngineeringWorkspaceMiddleware:
    """Apply the selected membership to engineering pages and direct URL access."""

    employee_pages = {
        "dashboard", "engineer-dashboard", "staff-dashboard", "project-list", "project-detail",
        "tasks", "documents", "site-visits", "file-register", "government-records", "municipality-tracking",
        "project-document-upload", "project-comment-create", "document-download", "project-qr-image",
        "project-site-visit-create", "project-file-transfer-create", "project-government-record-create",
        "project-municipality-activity-create", "project-public",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.user._workspace_organization_id = request.session.get("organization_id") or request.user.company_id
            request.workspace_membership = active_membership(request.user)
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None
        name = request.resolver_match.url_name
        if name in {"login", "home", "garima-login", "logout", "password-change", "organization-select", "access-denied"}:
            return None
        view_class = getattr(view_func, "view_class", None)
        module = getattr(view_class, "__module__", getattr(view_func, "__module__", ""))
        is_workspace_page = module.startswith(("projects.", "core.views", "workflows.")) or name in {"users-roles", "organization-user-create"}
        if not is_workspace_page:
            return None
        if request.user.must_change_password:
            return redirect("password-change")
        membership = getattr(request, "workspace_membership", None)
        organization_id = request.user._workspace_organization_id
        if not membership:
            raise PermissionDenied("An active organization membership is required.")
        engineering = membership and membership.organization.system_template and membership.organization.system_template.code == "engineering-consultancy"
        if engineering and membership.role != "admin" and name not in self.employee_pages:
            raise PermissionDenied("Only your organization administrator can access this page.")
        return None
