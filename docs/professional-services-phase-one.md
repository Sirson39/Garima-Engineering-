# Professional Service Management: architecture audit and Phase 1

The audit was presented before implementation. This workspace remains part of the
existing Django application, PostgreSQL database, authentication, organization
selection, module catalog and provisioning transaction.

## Existing architecture and integration points

- `accounts` owns Company, SystemTemplate, TemplateModule, ModulePermission,
  OrganizationMembership and OrganizationRole. Provisioning copies template roles
  and their permissions into an organization and assigns its administrator.
- The `professional-services` template already exists as an unavailable placeholder.
  A new catalog migration activates only this template and adds six implemented
  modules. No other template or shared module definition is changed.
- Existing project/client models belong to the engineering workflow. New domain
  tables avoid changing their semantics or migrating existing customer data.
- Shared navigation is hard-coded. A template block allows this workspace to render
  catalog navigation filtered by active modules and the current membership's role.
- AuditLog has no organization foreign key. Professional Services audit writes always
  include server-derived organization metadata; its readers require that scope and
  restrict events to visible records. Writes and audit events share a transaction.
- The session's selected organization must be validated against active membership;
  `user.company`, Django staff/superuser flags and platform roles do not grant access.

## Phase 1 delivery

Models: ProfessionalClient (contact, industry, account manager, services used,
status, rate), ProfessionalService (code, duration, billing defaults, deliverables,
department), Engagement (number, client, service, managers, assigned team, dates,
amount, rate, progress, status), ProfessionalSettings (organization billing rate).
All domain records have an organization FK. Engagement numbers and service codes
are unique within the organization. Money/progress/date constraints and related
organization/member validation are enforced. Archive is a status; no delete API.
Assigned team is an access-control foundation, not the later planned-hours and
allocation workflow. Effective rates resolve engagement, client, service, organization
in that order; unset rates remain unset. Currency comes from the organization.

Additive migrations: `professional_services/0001_initial` and
`accounts/0016_seed_professional_services_catalog`. Catalog rollback is a no-op to
preserve configured roles and records. Apply with `python manage.py migrate`.

Pages under `/professional-services/`: dashboard; clients/services/engagements
list, create, detail and edit; settings; role assignment and permission inspection;
scoped audit activity. Dashboard shows active clients, active engagements, upcoming
and overdue engagement deadlines, engagement status, manager workload measured in
engagements, and recent visible client updates. Metrics requiring later phases are
not fabricated. Menus and dashboard sections require both module and permission.

JSON API under `/professional-services/api/`: `dashboard/`, `clients/`, `services/`,
`engagements/`, plus `<id>/` for each resource. GET lists are paginated; GET detail,
POST collection and PATCH detail use the same scope, validation and audit as forms.
Session authentication and CSRF protection apply. Unknown write fields (including
organization and roles) are rejected. Errors are JSON; DELETE is unsupported.

Permissions: module-specific view/create/change; explicit clients/engagements
view-all; settings change and role management. All default to denied. Ten roles are
registered: administrator, director, account manager, engagement manager, consultant,
reviewer, accounts officer, document controller, client portal user and auditor.
The portal role has no Phase 1 access. Platform administrators and superusers need
an explicit active organization membership/role just like everyone else. Internal
users require an engagement manager/account manager/team assignment unless their
role explicitly grants view-all. Disabling a module blocks its pages/API without
deleting data. Only role managers may change membership roles; roles/memberships
must belong to the same organization and self-demotion is prevented.

Validation: catalog/provisioning, real dashboard totals, HTML/JSON CRUD,
cross-organization IDs and foreign keys, inactive memberships/roles, assignment
revocation, no platform bypass, disabled modules, API CSRF, date/rate/progress
validation, uniqueness, audit scoping and unchanged existing template catalogs.

## Deferred phases

2: TeamAssignment with role/dates/hours/rates/allocation; tasks, approved immutable
timesheets, versioned deliverables and private documents/download auditing.
3: Expenses, simple invoices with restricted accounts actions and immutable issued
records, reports and organization-scoped notifications. No full accounting/payroll.
4: Service requests, proposals, agreements, retainers, client portal and resource
planning. Remaining navigation appears only as these modules become implemented.
The full Client -> Service Request -> Proposal -> Agreement -> Engagement -> Team
-> Tasks/Deliverables -> Client Approval -> Invoice -> Completed workflow is the
roadmap, not a claim that Phase 1 implements downstream work.
